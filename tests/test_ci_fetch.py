"""VISION.md 対応:
- 機能別ルール(GitHub版)「画像URLには内容ハッシュ(?v=)を付与する」
- index.json の日付は「取得した日」を保つ(キャッシュ利用では更新しない)

tools/ci_fetch.py の LOGOS/DOCS はモジュール直下の実パスを指すため、
本物の docs/ を汚さないよう monkeypatch で一時ディレクトリに差し替える。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))

import ci_fetch  # noqa: E402
from config import Config  # noqa: E402


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    docs = tmp_path / "docs"
    logos = docs / "logos"
    logos.mkdir(parents=True)
    monkeypatch.setattr(ci_fetch, "DOCS", docs)
    monkeypatch.setattr(ci_fetch, "LOGOS", logos)
    cfg = Config()
    cfg.cache_dir = tmp_path / "ci-cache"
    return cfg, logos, docs


def _write_png(path: Path, color=(1, 2, 3, 255)):
    from PIL import Image
    Image.new("RGBA", (10, 10), color).save(path)


def test_v_hash_is_present_and_deterministic(isolated):
    cfg, logos, docs = isolated
    _write_png(logos / "A社.png")

    ci_fetch.rebuild_index(cfg, fetched=set())
    index = json.loads((docs / "index.json").read_text(encoding="utf-8"))

    assert len(index) == 1
    assert len(index[0]["v"]) == 8
    assert all(c in "0123456789abcdef" for c in index[0]["v"])


def test_v_hash_changes_when_image_content_changes(isolated):
    cfg, logos, docs = isolated
    png = logos / "A社.png"
    _write_png(png, color=(1, 2, 3, 255))
    ci_fetch.rebuild_index(cfg, fetched=set())
    before = json.loads((docs / "index.json").read_text(encoding="utf-8"))[0]["v"]

    _write_png(png, color=(9, 9, 9, 255))  # やり直しで画像内容が変わった状態を再現
    ci_fetch.rebuild_index(cfg, fetched=set())
    after = json.loads((docs / "index.json").read_text(encoding="utf-8"))[0]["v"]

    assert before != after


def test_date_is_kept_for_untouched_companies(isolated):
    cfg, logos, docs = isolated
    _write_png(logos / "A社.png")
    _write_png(logos / "B社.png")

    ci_fetch.rebuild_index(cfg, fetched={"A社", "B社"})
    first = {i["name"]: i["date"] for i in json.loads((docs / "index.json").read_text(encoding="utf-8"))}

    # 2回目は A社 だけ新規取得。B社の日付は変わらないはず
    ci_fetch.rebuild_index(cfg, fetched={"A社"})
    second = {i["name"]: i["date"] for i in json.loads((docs / "index.json").read_text(encoding="utf-8"))}

    assert second["B社"] == first["B社"]


def test_cache_hit_company_does_not_get_todays_date_by_default(isolated):
    """from_cache のときは fetched に入れない、という main() 側の契約を rebuild_index 側で検証する。"""
    cfg, logos, docs = isolated
    _write_png(logos / "既存社.png")
    ci_fetch.rebuild_index(cfg, fetched=set())
    before = json.loads((docs / "index.json").read_text(encoding="utf-8"))[0]["date"]

    ci_fetch.rebuild_index(cfg, fetched=set())  # fetched に含めない = キャッシュ利用相当
    after = json.loads((docs / "index.json").read_text(encoding="utf-8"))[0]["date"]

    assert before == after
