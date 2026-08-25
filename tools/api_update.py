r"""指定ファイルを GitHub の Git Data API で1コミットとしてリモートに反映する。

社内ネットワークでは git push(git-receive-pack)や大きめの Contents API PUT が
403 になることがあるため、疎通が安定している git/blobs 経由で更新する。

    .venv\Scripts\python.exe tools\api_update.py <owner>/<repo> <branch> <メッセージ> <file...>

ローカルの作業ツリーの内容をそのまま送る(ローカルコミットとは独立)。
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import time
from pathlib import Path

GH = r"C:\Program Files\GitHub CLI\gh.exe"


def gh_api(path: str, method: str = "GET", payload: dict | None = None, tries: int = 3) -> dict:
    args = [GH, "api", path]
    if method != "GET":
        args += ["-X", method]
    input_data = None
    if payload is not None:
        args += ["--input", "-"]
        input_data = json.dumps(payload).encode("utf-8")
    for i in range(tries):
        r = subprocess.run(args, input=input_data, capture_output=True)
        if r.returncode == 0:
            return json.loads(r.stdout.decode("utf-8"))
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"gh api {method} {path} 失敗:\n{r.stderr.decode('utf-8', 'replace')}")


def main() -> int:
    if len(sys.argv) < 5:
        print(__doc__, file=sys.stderr)
        return 1
    repo, branch, message = sys.argv[1], sys.argv[2], sys.argv[3]
    files = sys.argv[4:]

    head = gh_api(f"repos/{repo}/git/ref/heads/{branch}")
    parent_sha = head["object"]["sha"]
    parent_commit = gh_api(f"repos/{repo}/git/commits/{parent_sha}")
    base_tree = parent_commit["tree"]["sha"]
    print(f"リモート先端: {parent_sha[:10]}")

    tree_items = []
    for f in files:
        p = Path(f)
        content = p.read_bytes()
        blob = gh_api(f"repos/{repo}/git/blobs", "POST",
                      {"content": base64.b64encode(content).decode("ascii"),
                       "encoding": "base64"})
        tree_items.append({"path": f.replace("\\", "/"), "mode": "100644",
                           "type": "blob", "sha": blob["sha"]})
        print(f"  blob作成: {f} ({len(content)} bytes)")

    tree = gh_api(f"repos/{repo}/git/trees", "POST",
                  {"base_tree": base_tree, "tree": tree_items})
    commit = gh_api(f"repos/{repo}/git/commits", "POST",
                    {"message": message, "tree": tree["sha"], "parents": [parent_sha]})
    gh_api(f"repos/{repo}/git/refs/heads/{branch}", "PATCH",
           {"sha": commit["sha"], "force": False})
    print(f"完了: https://github.com/{repo}/commit/{commit['sha'][:10]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
