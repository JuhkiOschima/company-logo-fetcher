"""サムネイル生成。透過が分かるよう市松模様の上に描く。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

THUMB_W = 220
THUMB_H = 110
_CHECKER = 10
_LIGHT = (245, 245, 245, 255)
_DARK = (220, 220, 220, 255)


def checkerboard(size: tuple[int, int]) -> Image.Image:
    board = Image.new("RGBA", size, _LIGHT)
    for y in range(0, size[1], _CHECKER):
        for x in range(0, size[0], _CHECKER):
            if (x // _CHECKER + y // _CHECKER) % 2:
                board.paste(_DARK, (x, y, min(x + _CHECKER, size[0]), min(y + _CHECKER, size[1])))
    return board


def make_thumbnail(png_path: Path) -> Image.Image:
    """透過PNGを市松模様に載せたサムネイルを返す。"""
    board = checkerboard((THUMB_W, THUMB_H))
    try:
        with Image.open(png_path) as im:
            im = im.convert("RGBA")
            scale = min((THUMB_W - 8) / im.width, (THUMB_H - 8) / im.height, 1.0)
            im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))),
                           Image.Resampling.LANCZOS)
            board.alpha_composite(im, ((THUMB_W - im.width) // 2, (THUMB_H - im.height) // 2))
    except OSError:
        pass
    return board
