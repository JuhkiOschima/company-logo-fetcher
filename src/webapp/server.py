r"""社内LAN向けのロゴ共有Webサーバー。

    .venv\Scripts\python.exe src\webapp\server.py
    (または「Webサーバー起動.bat」)

- `http://<このPC名>:8531/` を共有すると、他の人もブラウザからストックの
  検索・ダウンロード・新規取得ができる。
- APIキーはこのPCの config.toml から読むだけで、閲覧者には一切渡さない。
- 取得処理はサーバー内の単一ワーカーで直列に行い、API を保護する。
"""

from __future__ import annotations

import io
import queue as queue_mod
import socket
import sys
import threading
import time
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC))

import net  # noqa: E402
import paths  # noqa: E402

net.setup_tls()

from flask import Flask, abort, jsonify, render_template, request, send_file  # noqa: E402

import bg_remove  # noqa: E402
import config as config_mod  # noqa: E402
import naming  # noqa: E402
import pipeline  # noqa: E402
import pptx_export  # noqa: E402
from search import get_provider  # noqa: E402

ROOT = paths.app_root()
PORT = 8531
FETCH_LIMIT = 20            # 1回の依頼で受け付ける最大社数(暴発防止)
QUOTA_CACHE_SEC = 60
JOB_KEEP_SEC = 3600         # 完了・失敗ジョブを一覧に残す時間
PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

app = Flask(__name__)

cfg = config_mod.load(root=ROOT)
cfg.require_keys()
provider = get_provider(cfg.search.provider, cfg.search.api_key)

_lock = threading.Lock()
_jobs: dict[str, dict] = {}   # 企業名 -> {state, error, domain, retry, ts}
_queue: "queue_mod.Queue[str]" = queue_mod.Queue()
_credit_blocked = False

_pptx_lock = threading.Lock()  # logos.pptx の生成と配信の排他

_quota_lock = threading.Lock()
_quota_cache: dict = {"at": 0.0, "data": None, "epoch": 0}


# --- 取得ワーカー(直列処理) ---

def _worker() -> None:
    global _credit_blocked
    while True:
        name = _queue.get()
        with _lock:
            job = _jobs.get(name)
            if job is None:
                continue
            job["state"] = "running"
            job["ts"] = time.time()
            is_retry = bool(job.get("retry"))
        try:
            if _credit_blocked:
                raise bg_remove.RemoveBgCreditError(
                    "remove.bg のクレジット不足のため新規取得を停止中です。")
            result = pipeline.process_company(name, cfg, provider, retry=is_retry)
            with _lock:
                _jobs[name] = {
                    "state": "done" if result.ok else "failed",
                    "error": result.error,
                    "domain": result.source_domain,
                    "ts": time.time(),
                }
        except bg_remove.RemoveBgCreditError as e:
            _credit_blocked = True  # クレジット不足(402)のみ。レート制限(429)は対象外
            with _lock:
                _jobs[name] = {"state": "failed", "error": str(e), "domain": "", "ts": time.time()}
        except Exception as e:  # 1社の失敗でワーカーを止めない
            msg = net.scrub(str(e), cfg.search.api_key, cfg.removebg.api_key)
            with _lock:
                _jobs[name] = {"state": "failed", "error": msg, "domain": "", "ts": time.time()}
        if _queue.empty():
            _regen_pptx()
            _invalidate_quota()  # 次の照会で残数を取り直す


def _regen_pptx() -> None:
    with _pptx_lock:
        _regen_pptx_unlocked()


def _regen_pptx_unlocked() -> None:
    entries = [(p.stem, p) for p in sorted(cfg.output.dir.glob("*.png"))]
    if entries:
        try:
            pptx_export.export(entries, cfg.output.dir / "logos.pptx")
        except Exception:
            pass  # 生成失敗はストック閲覧に影響させない


def _invalidate_quota() -> None:
    with _quota_lock:
        _quota_cache["epoch"] += 1
        _quota_cache["at"] = 0.0


threading.Thread(target=_worker, daemon=True).start()


# --- 画面 ---

@app.get("/")
def index():
    return render_template("index.html")


# --- API ---

@app.get("/api/logos")
def api_logos():
    items = []
    for p in sorted(cfg.output.dir.glob("*.png"), key=lambda p: -p.stat().st_mtime):
        meta = pipeline.CompanyCache(cfg.cache_dir, p.stem).load_meta()
        items.append({
            "name": p.stem,
            "domain": meta.get("source_domain", ""),
            "date": time.strftime("%Y-%m-%d", time.localtime(p.stat().st_mtime)),
        })
    return jsonify(items)


@app.get("/logo/<name>")
def logo(name: str):
    # パストラバーサル対策: ファイル名以外の形は一切受け付けない
    if name != Path(name).name or "/" in name or "\\" in name or ".." in name:
        abort(404)
    if not name.endswith(".png"):
        abort(404)
    target = (cfg.output.dir / name).resolve()
    if target.parent != cfg.output.dir.resolve() or not target.exists():
        abort(404)
    # 書き込み途中のファイルを配信しないよう、メモリに読み切ってから返す
    # (書き込み側は一時ファイル+os.replace の原子的置き換え)
    data = target.read_bytes()
    return send_file(io.BytesIO(data), mimetype="image/png",
                     download_name=name, max_age=0)


@app.get("/pptx")
def pptx():
    path = cfg.output.dir / "logos.pptx"
    with _pptx_lock:
        if not path.exists():
            _regen_pptx_unlocked()
        if not path.exists():
            abort(404)
        data = path.read_bytes()  # 再生成と配信が重ならないようロック内で読み切る
    return send_file(io.BytesIO(data), mimetype=PPTX_MIME, download_name="logos.pptx")


@app.get("/api/quota")
def api_quota():
    global _credit_blocked
    now = time.time()
    with _quota_lock:
        cached = _quota_cache["data"]
        fresh = cached is not None and now - _quota_cache["at"] < QUOTA_CACHE_SEC
        epoch = _quota_cache["epoch"]

    if not fresh:
        data: dict = {"serpapi": None, "removebg": None}
        try:
            left, total = provider.quota()
            data["serpapi"] = {"left": left, "total": total}
        except Exception:
            pass
        try:
            free_calls, credits = bg_remove.quota(cfg.removebg.api_key)
            data["removebg"] = {"free": free_calls, "credits": credits}
            if _credit_blocked and (free_calls > 0 or credits > 0):
                _credit_blocked = False  # 月替わり等で枠が戻ったら自動復帰
        except Exception:
            pass
        with _quota_lock:
            # 照会中にワーカーが無効化していたら、この(古い)結果は保存しない
            if _quota_cache["epoch"] == epoch:
                _quota_cache["data"] = data
                _quota_cache["at"] = time.time()
        cached = data

    # credit_blocked はキャッシュに乗せず、常に現在値を返す
    payload = dict(cached or {"serpapi": None, "removebg": None})
    payload["credit_blocked"] = _credit_blocked
    return jsonify(payload)


@app.post("/api/fetch")
def api_fetch():
    payload = request.get_json(force=True, silent=True) or {}
    names = naming.smart_split(str(payload.get("text", "")))
    # パス区切りを含む「企業名」はあり得ないので黙って捨てずに弾く
    names = [n for n in names if "\\" not in n and ".." not in n]
    if len(names) > FETCH_LIMIT:
        return jsonify({
            "accepted": [],
            "error": f"一度に取得できるのは {FETCH_LIMIT} 社までです"
                     f"({len(names)}社を検出)。分けて実行してください。",
        }), 400
    accepted = []
    with _lock:
        for n in names:
            if _jobs.get(n, {}).get("state") in ("waiting", "running"):
                continue
            _jobs[n] = {"state": "waiting", "error": "", "domain": "",
                        "retry": False, "ts": time.time()}
            _queue.put(n)
            accepted.append(n)
    return jsonify({"accepted": accepted})


@app.post("/api/retry")
def api_retry():
    payload = request.get_json(force=True, silent=True) or {}
    name = str(payload.get("name", "")).strip()
    if not name or "\\" in name or ".." in name:
        abort(400)
    with _lock:
        if _jobs.get(name, {}).get("state") in ("waiting", "running"):
            return jsonify({"accepted": []})
        _jobs[name] = {"state": "waiting", "error": "", "domain": "",
                       "retry": True, "ts": time.time()}
        _queue.put(name)
    return jsonify({"accepted": [name]})


@app.get("/api/status")
def api_status():
    now = time.time()
    with _lock:
        # 古い完了・失敗ジョブは一覧から掃除する(表示とメモリの両方のため)
        stale = [k for k, v in _jobs.items()
                 if v["state"] in ("done", "failed") and now - v.get("ts", now) > JOB_KEEP_SEC]
        for k in stale:
            del _jobs[k]
        jobs = {k: dict(v) for k, v in _jobs.items()}
    busy = any(j["state"] in ("waiting", "running") for j in jobs.values())
    return jsonify({"busy": busy, "jobs": jobs, "credit_blocked": _credit_blocked})


def main() -> None:
    host = socket.gethostname()
    print("ロゴ共有サーバーを起動しました。")
    print(f"  自分で開く:   http://localhost:{PORT}/")
    print(f"  共有するURL:  http://{host}:{PORT}/")
    print("停止するにはこのウィンドウを閉じるか Ctrl+C を押してください。")
    app.run(host="0.0.0.0", port=PORT, threaded=True, debug=False)


if __name__ == "__main__":
    main()
