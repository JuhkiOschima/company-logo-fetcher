"""アプリアイコン(.ico)を生成する。

図案の意図:
  市松模様(= 透過)の上に、ロゴを模した青いマーク(シンボル + ワードマーク)を置き、
  「ロゴの背景を透明にするツール」であることを一目で示す。
  16px でも潰れないよう、要素は大きな塊3つ(円・角丸バー・市松地)に絞っている。
"""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent

_BLUE = (0, 95, 184, 255)
_CHECK_LIGHT = (255, 255, 255, 255)
_CHECK_DARK = (214, 222, 230, 255)


def draw(size: int = 256) -> Image.Image:
    """指定サイズのアイコンを描く。

    小さいサイズでは市松模様が潰れて汚くなるため、32px 以下は
    青地に白マークの反転図案にする(サイズごとに描き分けるのは
    アイコン制作では一般的な手法)。
    """
    small = size <= 32
    # 小サイズは4倍で描いてから縮小し、輪郭を滑らかにする
    scale = 8 if small else 1
    canvas = size * scale
    s = canvas / 256
    img = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    box = [8 * s, 8 * s, canvas - 8 * s, canvas - 8 * s]
    radius = 52 * s

    if small:
        d.rounded_rectangle(box, radius=radius, fill=_BLUE)
        mark = _CHECK_LIGHT
    else:
        # 市松模様の地を角丸でくり抜く
        board = Image.new("RGBA", (canvas, canvas), _CHECK_LIGHT)
        bd = ImageDraw.Draw(board)
        cell = 32 * s
        n = int(canvas / cell) + 1
        for iy in range(n):
            for ix in range(n):
                if (ix + iy) % 2:
                    bd.rectangle([ix * cell, iy * cell, (ix + 1) * cell, (iy + 1) * cell],
                                 fill=_CHECK_DARK)
        mask = Image.new("L", (canvas, canvas), 0)
        ImageDraw.Draw(mask).rounded_rectangle(box, radius=radius, fill=255)
        img.paste(board, (0, 0), mask)
        mark = _BLUE

    # ロゴを模したマーク(シンボルの円 + ワードマークのバー)
    d = ImageDraw.Draw(img)
    d.ellipse([40 * s, 90 * s, 118 * s, 168 * s], fill=mark)
    d.rounded_rectangle([136 * s, 108 * s, 216 * s, 150 * s], radius=21 * s, fill=mark)

    if scale != 1:
        img = img.resize((size, size), Image.Resampling.LANCZOS)
    return img


def main() -> None:
    out = ROOT / "tools" / "logo_tool.ico"
    sizes = [16, 24, 32, 48, 64, 128, 256]
    # サイズごとに描き分けた画像を1つの .ico にまとめる
    images = [draw(s) for s in sizes]
    images[-1].save(out, format="ICO", sizes=[(s, s) for s in sizes],
                    append_images=images[:-1])
    print(f"アイコン生成: {out}({', '.join(f'{s}px' for s in sizes)})")


if __name__ == "__main__":
    main()
