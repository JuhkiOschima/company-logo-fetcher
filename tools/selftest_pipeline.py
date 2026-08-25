r"""APIを一切呼ばずにパイプライン全体を確認する自己テスト。

検索プロバイダとダウンロード処理を差し替え、透過を持つ画像を流し込むことで
「検索 → 候補選択 → 背景削除の判定 → トリミング → 保存 → pptx 出力」を通す。
remove.bg のクレジットも SerpAPI の検索回数も消費しない。

    .venv\Scripts\python.exe tools\selftest_pipeline.py
"""

import shutil
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image, ImageDraw  # noqa: E402

import config as config_mod  # noqa: E402
import downloader  # noqa: E402
import pipeline  # noqa: E402
import pptx_export  # noqa: E402
import report  # noqa: E402
from search.base import ImageCandidate  # noqa: E402

# OneDrive 配下は同期ロックで削除に失敗することがあるため、一時フォルダを使う
WORK = Path(tempfile.gettempdir()) / f"logo_selftest_{uuid.uuid4().hex[:8]}"


def make_logo(text: str, size=(600, 240)) -> Image.Image:
    """周囲に透明な余白を持つ、ロゴを模した画像。トリミングが効くか確認できる。"""
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([180, 90, 420, 150], radius=12, fill=(200, 40, 60, 255))
    d.text((196, 108), text, fill=(255, 255, 255, 255))
    return img


class StubProvider:
    name = "stub"

    def search_images(self, query: str, limit: int):
        return [
            ImageCandidate(url="https://example.com/tiny.jpg", title=query,
                           width=60, height=60, page_url="https://example.com/a"),
            ImageCandidate(url="https://example.co.jp/logo.png", title=f"{query} ロゴ",
                           width=600, height=240, page_url="https://example.co.jp/company"),
        ]


def stub_download(candidate, *, timeout=20):
    """上位候補だけ成功する。低スコア候補が選ばれていないことも確認できる。"""
    if candidate.url.endswith(".png"):
        img = make_logo("LOGO")
        return downloader.DownloadedImage(candidate=candidate, data=b"", image=img)
    raise downloader.DownloadError("スタブ: この候補は取得できません")


def main() -> int:
    shutil.rmtree(WORK, ignore_errors=True)

    cfg = config_mod.Config()
    cfg.root = ROOT
    cfg.cache_dir = WORK / "cache"
    cfg.output.dir = WORK / "output"
    cfg.search.api_key = "dummy"
    cfg.removebg.api_key = "dummy"

    downloader.download = stub_download          # ネットワークを使わない
    pipeline.downloader.download = stub_download

    companies = ["株式会社サンプル", "テスト工業", "Example Inc."]
    provider = StubProvider()

    print("--- 1回目(キャッシュなし) ---")
    results = [pipeline.process_company(c, cfg, provider) for c in companies]
    for r in results:
        size = Image.open(r.png_path).size if r.png_path else None
        print(f"  {r.company}: {r.status_label} 出力={size} 取得元={r.source_domain} "
              f"remove.bg={'使用' if r.used_removebg else '不使用'} {r.error}")

    trimmed = Image.open(results[0].png_path).size
    assert results[0].ok, "1社目が失敗しています"
    assert trimmed[0] < 600, f"トリミングされていません: {trimmed}"
    assert not results[0].used_removebg, "透過済み画像なのに remove.bg を呼んでいます"

    print("--- 2回目(キャッシュ利用。APIを呼ばないこと) ---")
    again = [pipeline.process_company(c, cfg, provider) for c in companies]
    assert all(r.from_cache for r in again), "キャッシュが効いていません"
    for r in again:
        print(f"  {r.company}: {r.status_label}")

    entries = [(r.company, r.png_path) for r in results if r.ok]
    pptx_path = pptx_export.export(entries, cfg.output.dir / "logos.pptx")
    report.write_csv(results, cfg.output.dir / "report.csv")
    report.write_failed(results, cfg.output.dir / "failed.txt")

    print()
    print(report.summary(results))
    print(f"\npptx: {pptx_path} ({pptx_path.stat().st_size} bytes)")
    print(f"出力一式: {cfg.output.dir}")
    print("\n自己テスト: すべて成功")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
