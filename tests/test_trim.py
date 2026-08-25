"""VISION.md 対応: 機能別ルール(トリミング)。

- アルファしきい値超の外接矩形+余白付与
- 長辺は上限超のときだけ縮小(拡大しない)
"""

from __future__ import annotations

from PIL import Image

import trim


def test_alpha_bbox_finds_the_opaque_region(transparent_logo):
    box = trim.alpha_bbox(transparent_logo)
    assert box == (150, 100, 251, 141)


def test_alpha_bbox_is_none_for_fully_transparent_image(fully_transparent):
    assert trim.alpha_bbox(fully_transparent) is None


def test_trim_crops_to_content_and_shrinks_the_canvas(transparent_logo):
    result = trim.trim(transparent_logo)
    assert result.size[0] < transparent_logo.size[0]
    assert result.size[1] < transparent_logo.size[1]


def test_trim_adds_padding_proportional_to_long_edge(transparent_logo):
    no_pad = trim.trim(transparent_logo, padding_ratio=0)
    with_pad = trim.trim(transparent_logo, padding_ratio=0.10)
    assert with_pad.size[0] > no_pad.size[0]
    assert with_pad.size[1] > no_pad.size[1]


def test_trim_returns_original_when_fully_transparent(fully_transparent):
    result = trim.trim(fully_transparent)
    assert result.size == fully_transparent.size


def test_limit_size_shrinks_when_over_the_cap():
    img = Image.new("RGBA", (2000, 1000), (0, 0, 0, 0))
    result = trim.limit_size(img, 1000)
    assert max(result.size) == 1000
    assert result.size[0] / result.size[1] == img.size[0] / img.size[1]


def test_limit_size_never_upscales():
    img = Image.new("RGBA", (100, 50), (0, 0, 0, 0))
    result = trim.limit_size(img, 1024)
    assert result.size == img.size


def test_limit_size_disabled_with_non_positive_cap():
    img = Image.new("RGBA", (2000, 1000), (0, 0, 0, 0))
    assert trim.limit_size(img, 0).size == img.size
