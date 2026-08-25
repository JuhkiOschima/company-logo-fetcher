"""VISION.md 対応: 機能別ルール(候補スコアリング)。

- 縦横比・解像度・ファイル形式・取得元ドメインの複合スコアで並べ替える
- 扱えない形式(SVG/ICO/AVIF)は候補から除外する
- remove.bg が受け付けない形式(GIF等)は PNG に変換してから渡す
"""

from __future__ import annotations

import io

from PIL import Image

import downloader
from search.base import ImageCandidate


def test_rank_prefers_official_domain_png_over_small_jpeg():
    candidates = [
        ImageCandidate(url="https://random.example/x.jpg", width=100, height=100),
        ImageCandidate(url="https://www.nttdata.com/logo.png", width=800, height=200,
                       page_url="https://www.nttdata.com/jp/"),
    ]
    ranked = downloader.rank(candidates, "株式会社NTTデータ")
    assert ranked[0].url.endswith("logo.png")


def test_rank_excludes_unsupported_extensions():
    candidates = [
        ImageCandidate(url="https://a.com/logo.svg", width=800, height=200),
        ImageCandidate(url="https://a.com/logo.ico", width=64, height=64),
        ImageCandidate(url="https://a.com/logo.png", width=800, height=200),
    ]
    ranked = downloader.rank(candidates, "A社")
    assert [c.extension for c in ranked] == ["png"]


def test_score_penalizes_extreme_aspect_ratio_and_tiny_images():
    wide_logo = ImageCandidate(url="https://a.com/x.png", width=800, height=200)
    tiny = ImageCandidate(url="https://a.com/y.png", width=40, height=40)
    assert downloader.score(wide_logo, "A社") > downloader.score(tiny, "A社")


def test_score_rewards_trusted_domains():
    wiki = ImageCandidate(url="https://x.com/a.png", width=800, height=200,
                          page_url="https://ja.wikipedia.org/wiki/A")
    unknown = ImageCandidate(url="https://x.com/a.png", width=800, height=200,
                             page_url="https://random-blog.example/a")
    assert downloader.score(wiki, "A社") > downloader.score(unknown, "A社")


def test_has_transparency_true_for_partly_transparent_rgba():
    img = Image.new("RGBA", (100, 100), (255, 255, 255, 255))
    img.putpixel((0, 0), (255, 255, 255, 0))
    for x in range(20):
        for y in range(20):
            img.putpixel((x, y), (255, 255, 255, 0))
    assert downloader.has_transparency(img) is True


def test_has_transparency_false_for_opaque_rgb(opaque_photo):
    assert downloader.has_transparency(opaque_photo) is False


def test_has_transparency_false_when_below_min_ratio():
    img = Image.new("RGBA", (100, 100), (255, 255, 255, 255))
    img.putpixel((0, 0), (255, 255, 255, 0))  # 1/10000 画素のみ透明
    assert downloader.has_transparency(img, min_ratio=0.02) is False


def _downloaded(fmt: str, **save_kwargs) -> downloader.DownloadedImage:
    buf = io.BytesIO()
    Image.new("RGB", (40, 20), (10, 20, 30)).save(buf, format=fmt, **save_kwargs)
    data = buf.getvalue()
    img = Image.open(io.BytesIO(data))
    img.load()
    return downloader.DownloadedImage(
        candidate=ImageCandidate(url=f"https://a.com/x.{fmt.lower()}"),
        data=data, image=img)


def test_to_removebg_bytes_keeps_supported_format_as_is():
    d = _downloaded("PNG")
    assert downloader.to_removebg_bytes(d) is d.data


def test_to_removebg_bytes_converts_gif_to_png():
    # 公式サイトのロゴが GIF のことがあり、そのままでは remove.bg が 400 を返す
    d = _downloaded("GIF")
    out = downloader.to_removebg_bytes(d)
    assert out != d.data
    assert Image.open(io.BytesIO(out)).format == "PNG"
