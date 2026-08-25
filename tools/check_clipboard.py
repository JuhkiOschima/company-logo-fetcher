r"""Phase 0 検証: 透過PNGがクリップボード経由で PowerPoint に貼れるか確かめる。

使い方:
    .venv\Scripts\python.exe tools\check_clipboard.py [モード番号]

モード:
    1 : PNG のみ                          ← 本命(CF_DIBV5 を載せないのが要点)
    2 : PNG + CF_DIBV5                    ← 検証済み: 背景が黒くなる(NG)
    3 : CF_DIBV5 のみ
    4 : image/png + PNG
    5 : ファイルとしてコピー(CF_HDROP)   ← 保険。画像ファイルの挿入として貼られる
    6 : PNG + CF_DIB(白背景)             ← 透過が無理な場合に黒より白を選ぶ妥協案

実行後、PowerPoint のスライド上で Ctrl+V して結果を確認する。
    OK … 円の外側が透けてスライドの地色が見える
    NG … 円の外側が黒または白の四角で塗り潰される
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image, ImageDraw  # noqa: E402

import clipboard  # noqa: E402

MODES = {
    "1": ("PNG のみ", dict(use_png=True)),
    "2": ("PNG + CF_DIBV5", dict(use_png=True, use_dibv5=True)),
    "3": ("CF_DIBV5 のみ", dict(use_png=False, use_dibv5=True)),
    "4": ("image/png + PNG", dict(use_png=True, use_png_mime=True)),
    "5": ("ファイルとしてコピー(CF_HDROP)", dict(use_png=False, use_file=True)),
    "6": ("PNG + CF_DIB(白背景)", dict(use_png=True, use_dib_white=True)),
}


def make_sample() -> Image.Image:
    """背景が完全透過で、半透明部分も含むテスト画像。

    透過が失われると円の外側が四角く塗られ、
    半透明が失われると青い円と赤い円の重なりが紫にならない。
    """
    scale = 4
    w, h = 400, 200
    img = Image.new("RGBA", (w * scale, h * scale), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([10 * scale, 10 * scale, 190 * scale, 190 * scale], fill=(220, 50, 50, 255))
    d.ellipse([120 * scale, 40 * scale, 320 * scale, 160 * scale], fill=(40, 90, 200, 128))
    d.line([340 * scale, 20 * scale, 380 * scale, 180 * scale], fill=(20, 20, 20, 255), width=3 * scale)
    return img.resize((w, h), Image.Resampling.LANCZOS)


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "1"
    if mode not in MODES:
        print(f"不明なモード: {mode}\n指定できるのは {', '.join(MODES)} です。")
        return 1

    label, kwargs = MODES[mode]
    img = make_sample()

    out_dir = ROOT / "cache"
    out_dir.mkdir(exist_ok=True)
    sample_path = out_dir / "clipboard_test.png"
    img.save(sample_path)

    if kwargs.pop("use_file", False):
        kwargs["file_path"] = sample_path

    written = clipboard.copy_image(img, **kwargs)

    print(f"モード {mode}: {label}")
    print(f"クリップボードに載せた形式: {', '.join(written)}")
    print(f"元画像(参考): {sample_path}")
    print()
    print("PowerPoint のスライドで Ctrl+V を押し、次を確認してください。")
    print("  OK … 円の外側が透けてスライドの地色が見える")
    print("  NG … 円の外側が黒または白の四角で塗られる")
    print("  ※ 赤い円と青い円の重なりが紫に見えれば、半透明も保持されています。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
