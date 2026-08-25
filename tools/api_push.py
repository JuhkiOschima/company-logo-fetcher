r"""git push (git-receive-pack への POST)が社内プロキシで塞がれているため、
GitHub の Git Data API(通常のJSON POST。gh api 経由で疎通確認済み)を使って
ローカルの HEAD コミットの中身を、そのままリモートへ1コミットとして作る。

一回限りの初回投入用スクリプト(リポジトリに含めない)。
    .venv\Scripts\python.exe tools\api_push.py <owner>/<repo> <branch>
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys

GH = r"C:\Program Files\GitHub CLI\gh.exe"


def run_git(*args: str) -> bytes:
    return subprocess.run(["git", *args], capture_output=True, check=True).stdout


def gh_api(path: str, method: str = "GET", payload: dict | None = None) -> dict:
    args = [GH, "api", path, "-X", method]
    input_data = None
    if payload is not None:
        args += ["--input", "-"]
        input_data = json.dumps(payload).encode("utf-8")
    r = subprocess.run(args, input=input_data, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"gh api {method} {path} 失敗:\n{r.stderr.decode('utf-8', 'replace')}")
    return json.loads(r.stdout.decode("utf-8"))


def list_tree(ref: str) -> list[tuple[str, str, str]]:
    """(path, blob_sha, mode) のリスト。"""
    raw = run_git("ls-tree", "-r", ref).decode("utf-8")
    out = []
    for line in raw.splitlines():
        meta, path = line.split("\t", 1)
        mode, _type, sha = meta.split(" ")
        out.append((path, sha, mode))
    return out


def main() -> int:
    if len(sys.argv) != 3:
        print("使い方: api_push.py <owner>/<repo> <branch>", file=sys.stderr)
        return 1
    repo, branch = sys.argv[1], sys.argv[2]

    # 完全に空のリポジトリでは git/blobs が 409 になるため、
    # Contents API で1ファイルだけ置いてブランチを初期化してから本編を積む。
    print("初期化コミットを作成中...")
    init = gh_api(f"repos/{repo}/contents/.init", "PUT", {
        "message": "初期化",
        "content": base64.b64encode(b"temporary").decode("ascii"),
        "branch": branch,
    })
    parent_sha = init["commit"]["sha"]

    entries = list_tree("HEAD")
    print(f"対象ファイル数: {len(entries)}")

    tree_items = []
    for i, (path, local_sha, mode) in enumerate(entries, 1):
        content = run_git("cat-file", "blob", local_sha)
        b64 = base64.b64encode(content).decode("ascii")
        blob = gh_api(f"repos/{repo}/git/blobs", "POST",
                      {"content": b64, "encoding": "base64"})
        tree_items.append({"path": path, "mode": mode, "type": "blob", "sha": blob["sha"]})
        print(f"  [{i}/{len(entries)}] blob作成: {path} ({len(content)} bytes)")

    print("ツリー作成中...")
    tree = gh_api(f"repos/{repo}/git/trees", "POST", {"tree": tree_items})

    subject = run_git("log", "-1", "--format=%s").decode("utf-8").strip()
    body = run_git("log", "-1", "--format=%b").decode("utf-8").strip()
    message = subject + ("\n\n" + body if body else "")
    print("コミット作成中...")
    commit = gh_api(f"repos/{repo}/git/commits", "POST",
                    {"message": message, "tree": tree["sha"], "parents": [parent_sha]})

    print(f"ブランチ {branch} を更新中...")
    gh_api(f"repos/{repo}/git/refs/heads/{branch}", "PATCH",
          {"sha": commit["sha"], "force": True})

    print(f"\n完了: https://github.com/{repo}/commit/{commit['sha']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
