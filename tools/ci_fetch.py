r"""GitHub Actions 上でロゴを取得し、docs/(共有ストック)を更新する。

ローカルの GUI/CLI と同じパイプラインを使い、次を更新する。
  - 取得結果 PNG   → docs/logos/
  - 一覧メタ       → docs/index.json
  - まとめ pptx    → docs/logos.pptx
  - API残数        → docs/quota.json
  - 直近の実行結果 → docs/last_run.json
  - ビューワー設定 → docs/config.json(リポジトリURL)

APIキーは環境変数(Actions の Secrets)から読む。値はログに出さない。

環境変数:
  SERPAPI_KEY / REMOVEBG_KEY : 必須
  COMPANIES : 取得する企業名(smart_split で分解。空なら取得なしで再生成のみ)
  RETRY     : 別の検索候補から取り直す企業名(1社)
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import net  # noqa: E402

net.setup_tls()

import bg_remove  # noqa: E402
import naming  # noqa: E402
import pipeline  # noqa: E402
import pptx_export  # noqa: E402
from config import Config, ConfigError  # noqa: E402
from report import LogoResult  # noqa: E402
from search import get_provider  # noqa: E402

DOCS = ROOT / "docs"
LOGOS = DOCS / "logos"
FETCH_LIMIT = 20


def build_config(require: bool = True) -> Config:
    cfg = Config()
    cfg.root = ROOT
    cfg.search.api_key = os.environ.get("SERPAPI_KEY", "")
    cfg.removebg.api_key = os.environ.get("REMOVEBG_KEY", "")
    cfg.output.dir = LOGOS
    cfg.cache_dir = ROOT / "ci-cache"
    if require:
        cfg.require_keys()
    return cfg


def safe_process(name: str, cfg: Config, provider, *, retry: bool) -> LogoResult:
    try:
        return pipeline.process_company(name, cfg, provider, retry=retry)
    except bg_remove.RemoveBgCreditError as e:
        raise  # クレジット不足は上位で「以降を中断」の判断に使う
    except Exception as e:
        msg = net.scrub(str(e), cfg.search.api_key, cfg.removebg.api_key)
        return LogoResult(company=name, error=f"{type(e).__name__}: {msg}")


def rebuild_index(cfg: Config, fetched: set[str]) -> None:
    """docs/index.json を作り直す。日付は「取得した日」を保つ。

    CI のチェックアウトではファイルの mtime が clone 時刻になってしまうため、
    既存 index.json の日付を引き継ぎ、今回取得した企業だけ今日の日付にする。
    """
    index_path = DOCS / "index.json"
    old: dict[str, dict] = {}
    if index_path.exists():
        try:
            old = {i["name"]: i for i in json.loads(index_path.read_text(encoding="utf-8"))}
        except (ValueError, KeyError, TypeError):
            old = {}
    today = time.strftime("%Y-%m-%d")
    items = []
    for p in sorted(LOGOS.glob("*.png")):
        meta = pipeline.CompanyCache(cfg.cache_dir, p.stem).load_meta()
        date = today if p.stem in fetched else (old.get(p.stem, {}).get("date") or today)
        items.append({
            "name": p.stem,
            "domain": meta.get("source_domain", ""),
            "date": date,
            # 画像内容のハッシュ。やり直しで画像が変わったとき、ブラウザ・CDNの
            # キャッシュを確実に無効化するために URL のクエリとして使う
            "v": hashlib.md5(p.read_bytes()).hexdigest()[:8],
        })
    items.sort(key=lambda i: (i["date"], i["name"]), reverse=True)
    index_path.write_text(
        json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


def write_quota(cfg: Config, provider) -> None:
    data: dict = {"updated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())}
    try:
        left, total = provider.quota()
        data["serpapi"] = {"left": left, "total": total}
    except Exception:
        pass
    try:
        free_calls, credits = bg_remove.quota(cfg.removebg.api_key)
        data["removebg"] = {"free": free_calls, "credits": credits}
    except Exception:
        pass
    (DOCS / "quota.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def write_config_json() -> None:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    url = f"https://github.com/{repo}" if repo else ""
    (DOCS / "config.json").write_text(
        json.dumps({"repo": url}, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    try:
        cfg = build_config()
    except ConfigError as e:
        print(f"[設定エラー] {e}", file=sys.stderr)
        return 1
    provider = get_provider(cfg.search.provider, cfg.search.api_key)
    LOGOS.mkdir(parents=True, exist_ok=True)

    companies = naming.smart_split(os.environ.get("COMPANIES", ""))
    companies = [n for n in companies if "\\" not in n and ".." not in n][:FETCH_LIMIT]
    # 改行・制御文字を除去(Actionsのログはコマンド解釈されるため、行頭偽装を防ぐ)
    retry_name = " ".join(os.environ.get("RETRY", "").split())

    # --- ストックからの削除(ビューワーの「ストックから削除」ボタン) ---
    delete_names = naming.smart_split(os.environ.get("DELETE", ""))
    delete_names = [n for n in delete_names if "\\" not in n and ".." not in n][:FETCH_LIMIT]
    deleted_results: list[LogoResult] = []
    for name in delete_names:
        safe = naming.safe_filename(name)
        png = LOGOS / f"{safe}.png"
        existed = png.exists()
        if existed:
            png.unlink()
        cache_dir = cfg.cache_dir / safe
        if cache_dir.is_dir():
            shutil.rmtree(cache_dir, ignore_errors=True)
        print(f"削除: {name}" + ("" if existed else "(ストックに存在しませんでした)"), flush=True)
        deleted_results.append(LogoResult(
            company=name, ok=existed,
            error="" if existed else "ストックに存在しませんでした"))

    results: list[LogoResult] = []
    fetched: set[str] = set()
    credit_stop = False

    todo: list[tuple[str, bool]] = [(n, False) for n in companies]
    if retry_name and "\\" not in retry_name and ".." not in retry_name:
        todo.append((retry_name, True))

    for name, is_retry in todo:
        if credit_stop:
            results.append(LogoResult(company=name, error="未処理(クレジット不足で中断)"))
            continue
        print(f"処理中: {name}" + ("(やり直し)" if is_retry else ""), flush=True)
        try:
            r = safe_process(name, cfg, provider, retry=is_retry)
        except bg_remove.RemoveBgCreditError as e:
            credit_stop = True
            r = LogoResult(company=name, error=str(e))
        results.append(r)
        if r.ok and not r.from_cache:
            fetched.add(r.company)  # キャッシュ利用は「取得した日」を更新しない

    rebuild_index(cfg, fetched)
    entries = [(p.stem, p) for p in sorted(LOGOS.glob("*.png"))]
    if entries:
        pptx_export.export(entries, DOCS / "logos.pptx")
    write_quota(cfg, provider)
    write_config_json()

    def _rdict(r: LogoResult, deleted: bool = False) -> dict:
        return {
            "name": r.company, "ok": r.ok, "domain": r.source_domain,
            "used_removebg": r.used_removebg, "from_cache": r.from_cache,
            "error": r.error, "deleted": deleted,
        }

    (DOCS / "last_run.json").write_text(json.dumps({
        "at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        # ビューワーが「自分の実行の結果が反映されたか」を突合するための識別子
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "results": [_rdict(r) for r in results] + [_rdict(r, True) for r in deleted_results],
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    ok = sum(1 for r in results if r.ok)
    print(f"完了: {ok}/{len(results)} 件成功、削除 {len(deleted_results)} 件"
          f"(ストック総数: {len(entries)}社)")
    for r in results:
        mark = "OK" if r.ok else "NG"
        print(f"  {mark} {r.company}" + (f" - {r.error}" if r.error else ""))
    # 取得失敗があっても index の再生成は済んでいるため、コミットは行わせる
    return 0


def rebuild_only() -> int:
    """PNGの合併結果から index.json と logos.pptx だけを作り直す。

    push競合時のリカバリー用(マージ後に呼ばれる)。quota.json や last_run.json は
    自分の実行の値を保つため触らない。APIキーも不要。
    """
    cfg = build_config(require=False)
    LOGOS.mkdir(parents=True, exist_ok=True)
    rebuild_index(cfg, set())
    entries = [(p.stem, p) for p in sorted(LOGOS.glob("*.png"))]
    if entries:
        pptx_export.export(entries, DOCS / "logos.pptx")
    print(f"index/pptx を再生成しました(ストック {len(entries)}社)")
    return 0


if __name__ == "__main__":
    if "--rebuild-only" in sys.argv:
        raise SystemExit(rebuild_only())
    raise SystemExit(main())
