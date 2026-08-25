"""透過PNGを Windows のクリップボードへ転送する。

Windows のクリップボードは同じ画像を複数の形式で同時に保持でき、
貼り付け側(PowerPoint など)がどれを選ぶかはアプリ依存である。

実測(2026-08-25, 本環境の PowerPoint):
    PNG + CF_DIBV5 を同時に載せると CF_DIBV5 が選ばれ、アルファが破棄されて
    背景が黒く塗られた。よって CF_DIBV5 を「載せない」ことが重要になる。

そのため形式の組み合わせを呼び出し側から選べるようにしてある。
"""

from __future__ import annotations

import io
import struct
from pathlib import Path

from PIL import Image

try:
    import win32clipboard
except ImportError as e:  # pragma: no cover - Windows 以外では動かさない
    raise RuntimeError("pywin32 が必要です: pip install pywin32") from e


CF_DIB = 8
CF_DIBV5 = 17
CF_HDROP = 15

# BITMAPV5HEADER の定数
_BI_BITFIELDS = 3
_LCS_sRGB = 0x73524742  # 'sRGB'
_LCS_GM_IMAGES = 4


def _to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _to_dibv5_bytes(img: Image.Image) -> bytes:
    """RGBA 画像を CF_DIBV5 用のバイト列(ヘッダ + BGRA ボトムアップ)にする。"""
    img = img.convert("RGBA")
    w, h = img.size
    flipped = img.transpose(Image.Transpose.FLIP_TOP_BOTTOM)  # DIB はボトムアップ
    pixels = flipped.tobytes("raw", "BGRA")

    header = struct.pack(
        "<IiiHHIIiiII" "IIII" "I" "36s" "III" "I" "III",
        124, w, h, 1, 32, _BI_BITFIELDS,
        len(pixels), 0, 0, 0, 0,
        0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000,
        _LCS_sRGB,
        b"\x00" * 36,
        0, 0, 0,
        _LCS_GM_IMAGES,
        0, 0, 0,
    )
    assert len(header) == 124, f"BITMAPV5HEADER の長さが不正: {len(header)}"
    return header + pixels


def _to_dib_bytes_on_white(img: Image.Image) -> bytes:
    """透過を白で塗り潰した CF_DIB(アルファなし)。透過非対応アプリ向けの保険。"""
    img = img.convert("RGBA")
    white = Image.new("RGBA", img.size, (255, 255, 255, 255))
    merged = Image.alpha_composite(white, img).convert("RGB")
    buf = io.BytesIO()
    merged.save(buf, format="BMP")
    return buf.getvalue()[14:]  # BMP ファイルヘッダ14バイトを除いたものが CF_DIB


def _to_hdrop_bytes(paths: list[Path]) -> bytes:
    """CF_HDROP(エクスプローラでファイルをコピーしたのと同じ状態)。

    PowerPoint に貼ると「画像ファイルの挿入」として扱われ、
    PNG のアルファがそのまま保持される見込み。
    """
    # DROPFILES 構造体(20バイト) + ワイド文字のパス列 + 終端の二重 NUL
    header = struct.pack("<IiiII", 20, 0, 0, 0, 1)  # pFiles, x, y, fNC, fWide
    body = "".join(f"{p.resolve()}\0" for p in paths) + "\0"
    return header + body.encode("utf-16-le")


def copy_image(
    img: Image.Image,
    *,
    use_png: bool = True,
    use_png_mime: bool = False,
    use_dibv5: bool = False,
    use_dib_white: bool = False,
    file_path: Path | None = None,
) -> list[str]:
    """画像をクリップボードに載せる。載せた形式名のリストを返す。

    既定では "PNG" 形式のみを載せる。CF_DIBV5 を同時に載せると
    PowerPoint がそちらを選んで透過を失うため、既定では載せない。
    """
    formats: list[tuple[int, bytes, str]] = []
    if use_png:
        formats.append((win32clipboard.RegisterClipboardFormat("PNG"),
                        _to_png_bytes(img), "PNG"))
    if use_png_mime:
        formats.append((win32clipboard.RegisterClipboardFormat("image/png"),
                        _to_png_bytes(img), "image/png"))
    if use_dibv5:
        formats.append((CF_DIBV5, _to_dibv5_bytes(img), "CF_DIBV5"))
    if use_dib_white:
        formats.append((CF_DIB, _to_dib_bytes_on_white(img), "CF_DIB(白背景)"))
    if file_path is not None:
        formats.append((CF_HDROP, _to_hdrop_bytes([Path(file_path)]), "CF_HDROP(ファイル)"))

    if not formats:
        raise ValueError("載せる形式が1つも指定されていません")

    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        for fmt_id, data, _name in formats:
            win32clipboard.SetClipboardData(fmt_id, data)
    finally:
        win32clipboard.CloseClipboard()

    return [name for _id, _data, name in formats]


def copy_png_file(path: str | Path, **kwargs) -> list[str]:
    """透過PNGファイルをクリップボードに載せる。"""
    path = Path(path)
    with Image.open(path) as img:
        return copy_image(img.convert("RGBA"), **kwargs)


def copy_for_powerpoint(path: str | Path) -> list[str]:
    """PowerPoint への貼り付けに最適な組み合わせで透過PNGをコピーする。

    実機検証(2026-08-25, tools/pptx_paste_matrix.py)の結果:
      - "PNG" 形式のみ           → 透過・半透明ともフル保持で貼れる (PASS)
      - PNG + CF_HDROP           → PASS(PowerPoint は PNG を優先)
      - PNG + CF_DIB(白背景)     → PASS(同上)
      - CF_DIBV5 を含む組み合わせ → 黒塗りになるため絶対に載せない

    ここでは PNG(PowerPoint 用)+ CF_HDROP(エクスプローラー等へのファイル
    貼り付け用)+ CF_DIB 白背景(透過非対応の古いアプリ用の保険)を載せる。
    """
    return copy_png_file(path, use_dib_white=True, file_path=Path(path))
