r"""CLI エントリポイント。企業リストを読み、1社ずつ処理してレポートを出す。

    .venv\Scripts\python.exe src\main.py [-i companies.txt] [--force] [-y]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import net                # noqa: E402
import paths              # noqa: E402

net.setup_tls()

import bg_remove          # noqa: E402
import config as config_mod  # noqa: E402
import naming             # noqa: E402
import pipeline           # noqa: E402
import pptx_export        # noqa: E402
import report             # noqa: E402
from search import get_provider  # noqa: E402

ROOT = paths.app_root()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="企業名リストからロゴを取得し、背景を消してトリミングする。"
    )
    p.add_argument("-i", "--input", default="companies.txt", help="企業名リスト(1行1社)")
    p.add_argument("-c", "--config", default="config.toml", help="設定ファイル")
    p.add_argument("--force", action="store_true",
                   help="キャッシュを無視して再取得する(APIを再度消費します)")
    p.add_argument("-y", "--yes", action="store_true", help="件数の確認を省略する")
    p.add_argument("--no-pptx", action="store_true", help="pptx を出力しない")
    p.add_argument("--gui", action="store_true", help="処理後にロゴ一覧GUIを開く")
    return p.parse_args(argv)


def confirm(count: int, force: bool) -> bool:
    print(f"これから {count} 件を処理します。")
    if force:
        print("  --force が指定されているため、キャッシュを使わず全件でAPIを呼びます。")
    print("  ※ 背景削除は1件につき remove.bg のクレジットを1消費します"
          "(取得画像がすでに透過の場合とキャッシュがある場合を除く)。")
    answer = input("続行しますか? [y/N]: ").strip().lower()
    return answer in ("y", "yes")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        cfg = config_mod.load(args.config, root=ROOT)
        cfg.require_keys()
    except config_mod.ConfigError as e:
        print(f"[設定エラー] {e}", file=sys.stderr)
        return 1

    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = ROOT / input_path
    if not input_path.exists():
        print(f"[エラー] 企業リストが見つかりません: {input_path}", file=sys.stderr)
        return 1

    companies = naming.read_company_list(input_path)
    if not companies:
        print("[エラー] 企業リストが空です。", file=sys.stderr)
        return 1

    if not args.yes and not confirm(len(companies), args.force):
        print("中止しました。")
        return 0

    provider = get_provider(cfg.search.provider, cfg.search.api_key)

    results: list[report.LogoResult] = []
    aborted = False
    for i, company in enumerate(companies, 1):
        print(f"[{i}/{len(companies)}] {company} ... ", end="", flush=True)
        try:
            r = pipeline.process_company(company, cfg, provider, force=args.force)
        except bg_remove.RemoveBgCreditError as e:
            print("中断")
            print(f"\n[中断] {e}")
            print("残りの企業は処理していません。failed.txt から再実行できます。")
            results.append(report.LogoResult(company=company, error=str(e)))
            results.extend(report.LogoResult(company=c, error="未処理(中断のため)")
                           for c in companies[i:])
            aborted = True
            break
        except Exception as e:  # 1社の失敗で全体を止めない
            r = report.LogoResult(company=company, error=f"{type(e).__name__}: {e}")

        if r.ok:
            note = "キャッシュ" if r.from_cache else ("remove.bg" if r.used_removebg else "透過済み画像")
            print(f"OK ({note})")
        else:
            print(f"NG - {r.error}")
        results.append(r)

    csv_path = cfg.output.dir / "report.csv"
    failed_path = cfg.output.dir / "failed.txt"
    report.write_csv(results, csv_path)
    report.write_failed(results, failed_path)

    entries = [(r.company, r.png_path) for r in results if r.ok and r.png_path]
    if entries and cfg.output.pptx and not args.no_pptx:
        pptx_path = pptx_export.export(entries, cfg.output.dir / "logos.pptx")
        print(f"\npptx を出力しました: {pptx_path}")

    print()
    print(report.summary(results))
    print(f"\n出力先: {cfg.output.dir}")
    print(f"レポート: {csv_path}")

    if hasattr(provider, "quota"):
        try:
            left, total = provider.quota()
            print(f"SerpAPI 今月の残り検索数: {left}/{total}")
        except Exception:
            pass  # 表示できなくても処理結果には影響しない
    try:
        free_calls, credits = bg_remove.quota(cfg.removebg.api_key)
        extra = f" +有料クレジット{credits:g}" if credits else ""
        print(f"remove.bg 残り無料回数: {free_calls}回{extra}")
    except Exception:
        pass

    if args.gui and not aborted:
        from gui.app import run as run_gui
        run_gui()
    return 1 if aborted else 0


if __name__ == "__main__":
    raise SystemExit(main())
