"""pytest共通フィクスチャ。

VISION.md の `[unit test]` タグが付いた設計思想を検証するテスト群で使う、
最小限の合成画像・設定ヘルパーを提供する。
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

import pytest  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402


@pytest.fixture
def transparent_logo() -> Image.Image:
    """中央に不透明な四角、周囲に十分な透明の余白を持つ合成ロゴ。"""
    img = Image.new("RGBA", (400, 300), (0, 0, 0, 0))
    ImageDraw.Draw(img).rectangle([150, 100, 250, 140], fill=(255, 0, 0, 255))
    return img


@pytest.fixture
def opaque_photo() -> Image.Image:
    """透過を一切持たない不透明画像(remove.bg が必要なケース)。"""
    return Image.new("RGB", (300, 200), (10, 20, 30))


@pytest.fixture
def fully_transparent() -> Image.Image:
    """全面透明(bbox が取れない境界ケース)。"""
    return Image.new("RGBA", (100, 100), (0, 0, 0, 0))
