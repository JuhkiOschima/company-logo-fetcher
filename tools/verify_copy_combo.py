r"""GUI が使う copy_for_powerpoint の形式組み合わせを PowerPoint 実機で最終確認する。

    .venv\Scripts\python.exe tools\verify_copy_combo.py
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from PIL import Image  # noqa: E402
import win32com.client  # noqa: E402

import clipboard  # noqa: E402
from check_clipboard import make_sample  # noqa: E402

MAGENTA = (255, 0, 255)


def near(a, b, tol=45):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def main() -> int:
    work = ROOT / "cache" / "paste_matrix"
    work.mkdir(parents=True, exist_ok=True)
    sample = work / "sample.png"
    make_sample().save(sample)

    written = clipboard.copy_for_powerpoint(sample)
    print(f"載せた形式: {', '.join(written)}")
    time.sleep(0.3)

    owned = False
    try:
        app = win32com.client.GetActiveObject("PowerPoint.Application")
    except Exception:
        app = win32com.client.Dispatch("PowerPoint.Application")
        owned = True
    app.Visible = True
    pres = app.Presentations.Add(WithWindow=-1)
    try:
        slide = pres.Slides.Add(1, 12)
        slide.FollowMasterBackground = 0
        slide.Background.Fill.Solid()
        slide.Background.Fill.ForeColor.RGB = 255 + 255 * 65536

        slide.Shapes.Paste()
        sh = slide.Shapes.Item(1)
        sh.LockAspectRatio = 0
        sh.Left, sh.Top, sh.Width, sh.Height = 100.0, 100.0, 400.0, 200.0

        out = work / "combo_check.png"
        slide_w = float(pres.PageSetup.SlideWidth)
        export_w = 1280
        export_h = round(export_w * float(pres.PageSetup.SlideHeight) / slide_w)
        slide.Export(str(out), "PNG", export_w, export_h)
        f = export_w / slide_w

        with Image.open(out) as shot:
            shot = shot.convert("RGB")
            corner = shot.getpixel((round((100 + 394) * f), round((100 + 6) * f)))
            semi = shot.getpixel((round((100 + 250) * f), round((100 + 100) * f)))

        ok_corner = near(corner, MAGENTA)
        ok_semi = near(semi, (147, 45, 227))
        print(f"透過部: {'保持' if ok_corner else f'NG {corner}'}")
        print(f"半透明部: {'フルアルファ' if ok_semi else f'NG {semi}'}")
        print("判定:", "PASS" if (ok_corner and ok_semi) else "FAIL")
        return 0 if (ok_corner and ok_semi) else 1
    finally:
        try:
            pres.Saved = True
            pres.Close()
        except Exception:
            pass
        if owned:
            try:
                app.Quit()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
