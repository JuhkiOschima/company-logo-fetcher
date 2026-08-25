r"""クリップボード形式 × 貼り付け方法の全組み合わせを PowerPoint で自動検証する。

やること:
  1. PowerPoint を COM で起動(既に起動中ならそれに接続)し、検証用の
     新規プレゼンテーションを1つ作る(ユーザーが開いているファイルには触らない)。
  2. スライド背景を純マゼンタ (255,0,255) にする。
  3. 各モードでクリップボードに画像を載せ、貼り付け、スライドをPNGに書き出す。
  4. 書き出した画像の画素を検査して「透過が保たれたか」を機械判定する。
     - 透過部分がマゼンタに見える  → 透過保持 (PASS)
     - 黒/白で塗られる            → アルファ破棄 (FAIL)
     - 半透明部分の混色も検査し、フルアルファか2値かも判定する。

    .venv\Scripts\python.exe tools\pptx_paste_matrix.py
"""

import json
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from PIL import Image  # noqa: E402

import clipboard  # noqa: E402
from check_clipboard import make_sample  # noqa: E402

import win32com.client  # noqa: E402

DIR = ROOT / "cache" / "paste_matrix"
MAGENTA = (255, 0, 255)

# 検査点(画像内座標 400x200)と期待値
#   corner  : 完全透過の領域
#   red     : 不透明の赤い円の中心
#   semi_bg : 半透明の青がスライド背景の上に直接乗る領域
#   overlap : 半透明の青が赤い円の上に乗る領域
POINTS = {
    "corner": (394, 6),
    "red": (100, 100),
    "semi_bg": (250, 100),
    "overlap": (165, 100),
}
EXPECT_RED = (220, 50, 50)
EXPECT_SEMI_BG_BLEND = (147, 45, 227)   # 0.5*青 + 0.5*マゼンタ
EXPECT_OVERLAP_BLEND = (130, 70, 125)   # 0.5*青 + 0.5*赤
PURE_BLUE = (40, 90, 200)


def near(a, b, tol=45):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def classify_corner(px):
    if near(px, MAGENTA):
        return "透過保持"
    if near(px, (0, 0, 0)):
        return "黒塗り"
    if near(px, (255, 255, 255)):
        return "白塗り"
    return f"不明 {px}"


def main() -> int:
    DIR.mkdir(parents=True, exist_ok=True)
    img = make_sample()
    sample_path = DIR / "sample.png"
    img.save(sample_path)

    # --- PowerPoint への接続 ---
    owned = False
    try:
        app = win32com.client.GetActiveObject("PowerPoint.Application")
    except Exception:
        app = win32com.client.Dispatch("PowerPoint.Application")
        owned = True
    app.Visible = True
    try:
        app.DisplayAlerts = 1  # ppAlertsNone
    except Exception:
        pass

    pres = app.Presentations.Add(WithWindow=-1)
    try:
        slide = pres.Slides.Add(1, 12)  # ppLayoutBlank
        slide.FollowMasterBackground = 0
        slide.Background.Fill.Solid()
        slide.Background.Fill.ForeColor.RGB = 255 + 255 * 65536  # マゼンタ

        slide_w = float(pres.PageSetup.SlideWidth)
        slide_h = float(pres.PageSetup.SlideHeight)
        export_w = 1280
        export_h = round(export_w * slide_h / slide_w)
        f = export_w / slide_w  # pt → px

        def clear_shapes():
            while slide.Shapes.Count:
                slide.Shapes.Item(1).Delete()

        def run_case(tag, label, setup_clipboard, paste):
            clear_shapes()
            row = {"tag": tag, "label": label, "pasted": False,
                   "corner": "-", "semi": "-", "verdict": "-", "error": ""}
            try:
                if setup_clipboard:
                    setup_clipboard()
                    time.sleep(0.3)
                paste()
            except Exception as e:
                row["error"] = str(e).splitlines()[0][:120]
            if slide.Shapes.Count == 0:
                row["verdict"] = "貼り付け不可"
                return row
            row["pasted"] = True
            sh = slide.Shapes.Item(1)
            try:
                sh.LockAspectRatio = 0
                sh.Left, sh.Top, sh.Width, sh.Height = 100.0, 100.0, 400.0, 200.0
            except Exception as e:
                row["error"] = f"配置失敗: {e}"
                return row
            out = DIR / f"{tag}.png"
            slide.Export(str(out), "PNG", export_w, export_h)

            with Image.open(out) as shot:
                shot = shot.convert("RGB")
                px = {}
                for name, (ix, iy) in POINTS.items():
                    x = round((100 + ix) * f)
                    y = round((100 + iy) * f)
                    px[name] = shot.getpixel((x, y))

            row["corner"] = classify_corner(px["corner"])
            if not near(px["red"], EXPECT_RED):
                row["error"] = (row["error"] + f" 赤の検査点が想定外 {px['red']}").strip()

            if near(px["semi_bg"], EXPECT_SEMI_BG_BLEND):
                row["semi"] = "フルアルファ"
            elif near(px["semi_bg"], PURE_BLUE):
                row["semi"] = "アルファ喪失"
            elif near(px["semi_bg"], MAGENTA):
                row["semi"] = "2値化(半透明→全透過)"
            else:
                row["semi"] = f"不明 {px['semi_bg']}"

            row["verdict"] = "PASS" if (row["corner"] == "透過保持") else "FAIL"
            return row

        cb = clipboard

        cases = [
            ("A0_addpicture", "AddPicture(ファイル挿入・基準)", None,
             lambda: slide.Shapes.AddPicture(str(sample_path), 0, -1, 100, 100, 400, 200)),
            ("A1_png_paste", "PNGのみ + 通常貼り付け",
             lambda: cb.copy_image(img), lambda: slide.Shapes.Paste()),
            ("A2_png_special", "PNGのみ + PasteSpecial(PNG)",
             lambda: cb.copy_image(img), lambda: slide.Shapes.PasteSpecial(6)),
            ("A3_mime_paste", "image/pngのみ + 通常貼り付け",
             lambda: cb.copy_image(img, use_png=False, use_png_mime=True),
             lambda: slide.Shapes.Paste()),
            ("A4_png_mime", "PNG+image/png + 通常貼り付け",
             lambda: cb.copy_image(img, use_png_mime=True),
             lambda: slide.Shapes.Paste()),
            ("A5_hdrop", "ファイルコピー(CF_HDROP) + 通常貼り付け",
             lambda: cb.copy_image(img, use_png=False, file_path=sample_path),
             lambda: slide.Shapes.Paste()),
            ("A6_png_hdrop", "PNG+CF_HDROP + 通常貼り付け",
             lambda: cb.copy_image(img, file_path=sample_path),
             lambda: slide.Shapes.Paste()),
            ("A7_dibv5", "CF_DIBV5のみ + 通常貼り付け",
             lambda: cb.copy_image(img, use_png=False, use_dibv5=True),
             lambda: slide.Shapes.Paste()),
            ("A8_png_dibwhite", "PNG+CF_DIB(白背景) + 通常貼り付け",
             lambda: cb.copy_image(img, use_dib_white=True),
             lambda: slide.Shapes.Paste()),
        ]

        results = []
        for tag, label, setup, paste in cases:
            row = run_case(tag, label, setup, paste)
            results.append(row)
            print(f"{row['verdict']:<8} {tag:<16} {label}")
            print(f"         透過部={row['corner']} / 半透明部={row['semi']}"
                  + (f" / err={row['error']}" if row["error"] else ""))

        clear_shapes()
        (DIR / "results.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n詳細とスクリーンショット: {DIR}")
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
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
