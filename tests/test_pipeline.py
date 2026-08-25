"""VISION.md 対応:
- 機能横断ルール「キャッシュがあればAPIを呼ばない」
- 機能横断ルール「『やり直し』は前回使った候補の次から」

外部ネットワーク(検索API・remove.bg・実ダウンロード)は一切呼ばず、
downloader.download / bg_remove.remove_background をスタブに差し替えて検証する。
"""

from __future__ import annotations

import json

import pytest
from PIL import Image

import bg_remove
import downloader
import pipeline
from config import Config
from search.base import ImageCandidate


class StubProvider:
    """呼ばれた回数を記録するだけの検索プロバイダ。"""

    name = "stub"

    def __init__(self, candidates):
        self._candidates = candidates
        self.calls = 0

    def search_images(self, query, limit):
        self.calls += 1
        return list(self._candidates)


@pytest.fixture
def cfg(tmp_path):
    c = Config()
    c.root = tmp_path
    c.cache_dir = tmp_path / "cache"
    c.output.dir = tmp_path / "output"
    c.search.api_key = "dummy"
    c.removebg.api_key = "dummy"
    return c


def _transparent_image():
    # has_transparency() が True と判定する、十分な面積の透明領域を持つ画像
    img = Image.new("RGBA", (300, 100), (0, 0, 0, 0))
    for x in range(100, 200):
        for y in range(30, 70):
            img.putpixel((x, y), (200, 30, 30, 255))
    return img


def _opaque_image():
    return Image.new("RGB", (300, 100), (10, 20, 30))


def test_no_removebg_call_when_source_already_transparent(monkeypatch, cfg):
    candidate = ImageCandidate(url="https://a.com/logo.png", width=300, height=100)
    monkeypatch.setattr(downloader, "download",
                        lambda c, **k: downloader.DownloadedImage(c, b"", _transparent_image()))
    monkeypatch.setattr(bg_remove, "remove_background",
                        lambda *a, **k: pytest.fail("remove.bg should not be called"))

    result = pipeline.process_company("A社", cfg, StubProvider([candidate]))

    assert result.ok is True
    assert result.used_removebg is False


def test_removebg_is_called_for_opaque_source(monkeypatch, cfg):
    candidate = ImageCandidate(url="https://a.com/logo.png", width=300, height=100)
    monkeypatch.setattr(downloader, "download",
                        lambda c, **k: downloader.DownloadedImage(c, b"raw", _opaque_image()))

    calls = []

    def fake_remove(data, key, **kwargs):
        calls.append(data)
        import io
        buf = io.BytesIO()
        _transparent_image().save(buf, format="PNG")
        return buf.getvalue()

    monkeypatch.setattr(bg_remove, "remove_background", fake_remove)

    result = pipeline.process_company("A社", cfg, StubProvider([candidate]))

    assert result.ok is True
    assert result.used_removebg is True
    assert len(calls) == 1


def test_second_call_uses_cache_and_calls_no_api(monkeypatch, cfg):
    candidate = ImageCandidate(url="https://a.com/logo.png", width=300, height=100)
    monkeypatch.setattr(downloader, "download",
                        lambda c, **k: downloader.DownloadedImage(c, b"", _transparent_image()))
    provider = StubProvider([candidate])

    first = pipeline.process_company("A社", cfg, provider)
    assert first.ok and provider.calls == 1

    # 2回目呼び出しでは検索を一切呼ばない(from_cache になる)
    monkeypatch.setattr(downloader, "download",
                        lambda c, **k: pytest.fail("download should not be called on cache hit"))
    second = pipeline.process_company("A社", cfg, provider)

    assert second.ok is True
    assert second.from_cache is True
    assert provider.calls == 1  # 増えていない


def test_retry_resumes_from_used_rank_plus_one(monkeypatch, cfg):
    bad = ImageCandidate(url="https://a.com/bad.png", width=300, height=100)
    good = ImageCandidate(url="https://a.com/good.png", width=300, height=100)
    provider = StubProvider([bad, good])

    def download_only_second(cand, **k):
        if cand is bad:
            raise downloader.DownloadError("疑似的な取得失敗")
        return downloader.DownloadedImage(cand, b"", _transparent_image())

    monkeypatch.setattr(downloader, "download", download_only_second)
    first = pipeline.process_company("A社", cfg, provider)
    assert first.ok and first.source_url.endswith("good.png")

    # meta.json に used_rank=1(2番目の候補)が記録されているはず
    cache = pipeline.CompanyCache(cfg.cache_dir, "A社")
    assert cache.load_meta()["used_rank"] == 1

    # やり直し: used_rank+1 = 2 から始まるため、候補が尽きて失敗するのが正しい
    provider.calls = 0
    retried = pipeline.process_company("A社", cfg, provider, retry=True)
    assert retried.ok is False
    assert provider.calls == 0  # 検索候補はキャッシュ済みなので再検索しない


def test_build_query_strips_legal_suffix_by_default(cfg):
    assert pipeline.build_query("株式会社NTTデータ", cfg) == "NTTデータ ロゴ"


def test_build_query_keeps_legal_suffix_when_disabled(cfg):
    cfg.search.strip_legal_suffix = False
    assert pipeline.build_query("株式会社NTTデータ", cfg) == "株式会社NTTデータ ロゴ"


def test_one_company_failure_does_not_raise(monkeypatch, cfg):
    """全体を止めない: 検索自体が失敗しても例外にせず LogoResult.error に記録する。"""
    from search.base import SearchError

    class FailingProvider:
        name = "failing"

        def search_images(self, query, limit):
            raise SearchError("検索に失敗しました")

    result = pipeline.process_company("A社", cfg, FailingProvider())
    assert result.ok is False
    assert "検索に失敗しました" in result.error


def test_atomic_save_leaves_no_tmp_file_behind(monkeypatch, cfg):
    candidate = ImageCandidate(url="https://a.com/logo.png", width=300, height=100)
    monkeypatch.setattr(downloader, "download",
                        lambda c, **k: downloader.DownloadedImage(c, b"", _transparent_image()))

    result = pipeline.process_company("A社", cfg, StubProvider([candidate]))

    assert result.ok
    assert result.png_path.exists()
    assert not result.png_path.with_name(result.png_path.name + ".tmp").exists()
