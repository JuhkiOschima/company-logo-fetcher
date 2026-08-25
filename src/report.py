"""処理結果の保持とレポート出力。"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class LogoResult:
    """1社分の処理結果。"""

    company: str
    ok: bool = False
    png_path: Path | None = None
    source_url: str = ""
    source_domain: str = ""
    used_removebg: bool = False
    from_cache: bool = False
    error: str = ""
    tried_candidates: list[str] = field(default_factory=list)

    @property
    def status_label(self) -> str:
        if not self.ok:
            return "失敗"
        return "成功(キャッシュ)" if self.from_cache else "成功"


def write_csv(results: list[LogoResult], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Excel で開くことを想定し BOM 付き UTF-8 にする
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["企業名", "結果", "出力ファイル", "画像URL", "取得元ドメイン",
                         "remove.bg使用", "エラー"])
        for r in results:
            writer.writerow([
                r.company,
                r.status_label,
                r.png_path.name if r.png_path else "",
                r.source_url,
                r.source_domain,
                "はい" if r.used_removebg else "いいえ",
                r.error,
            ])


def write_failed(results: list[LogoResult], path: Path) -> int:
    """失敗した企業名だけを書き出す。そのまま再実行の入力に使える。"""
    failed = [r.company for r in results if not r.ok]
    path.parent.mkdir(parents=True, exist_ok=True)
    if not failed:
        # 前回の失敗リストが残っていると紛らわしいので空にしておく
        path.write_text("", encoding="utf-8")
        return 0
    path.write_text("\n".join(failed) + "\n", encoding="utf-8")
    return len(failed)


def summary(results: list[LogoResult]) -> str:
    ok = sum(1 for r in results if r.ok)
    cached = sum(1 for r in results if r.ok and r.from_cache)
    used_api = sum(1 for r in results if r.used_removebg)
    lines = [
        f"完了: {ok}/{len(results)} 件成功",
        f"  うちキャッシュ利用: {cached} 件(APIを呼んでいません)",
        f"  remove.bg 呼び出し: {used_api} 件",
    ]
    failed = [r for r in results if not r.ok]
    if failed:
        lines.append("  失敗:")
        lines.extend(f"    - {r.company}: {r.error}" for r in failed)
    return "\n".join(lines)
