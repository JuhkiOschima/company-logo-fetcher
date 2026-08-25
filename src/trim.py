"""透過部分を基準にした自動トリミングとリサイズ。"""

from __future__ import annotations

from PIL import Image

# この値未満のアルファは「背景」とみなす(0-255)
ALPHA_THRESHOLD = 10


def alpha_bbox(img: Image.Image, threshold: int = ALPHA_THRESHOLD) -> tuple[int, int, int, int] | None:
    """アルファがしきい値を超える画素の外接矩形。全面透明なら None。"""
    rgba = img.convert("RGBA")
    alpha = rgba.getchannel("A")
    # しきい値以下を 0、超えるものを 255 にした二値画像の外接矩形を取る
    mask = alpha.point(lambda a: 255 if a > threshold else 0)
    return mask.getbbox()


def trim(img: Image.Image, *, padding_ratio: float = 0.02,
         threshold: int = ALPHA_THRESHOLD) -> Image.Image:
    """余白を切り落とし、長辺に対する割合の余白を足し直す。"""
    rgba = img.convert("RGBA")
    box = alpha_bbox(rgba, threshold)
    if box is None:
        # 全面透明。切り出すものがないのでそのまま返す。
        return rgba

    cropped = rgba.crop(box)
    if padding_ratio <= 0:
        return cropped

    pad = max(1, round(max(cropped.size) * padding_ratio))
    padded = Image.new("RGBA", (cropped.width + pad * 2, cropped.height + pad * 2), (0, 0, 0, 0))
    padded.paste(cropped, (pad, pad))
    return padded


def limit_size(img: Image.Image, max_long_edge: int) -> Image.Image:
    """長辺が上限を超える場合だけ縮小する(拡大はしない)。"""
    if max_long_edge <= 0:
        return img
    long_edge = max(img.size)
    if long_edge <= max_long_edge:
        return img
    scale = max_long_edge / long_edge
    new_size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
    return img.resize(new_size, Image.Resampling.LANCZOS)


def process(img: Image.Image, *, padding_ratio: float = 0.02,
            max_long_edge: int = 1024) -> Image.Image:
    return limit_size(trim(img, padding_ratio=padding_ratio), max_long_edge)
