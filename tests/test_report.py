"""VISION.md 対応: 全体ルール「1社の失敗で全体を止めない」の出力側。"""

from __future__ import annotations

from pathlib import Path

import report


def make_result(company, ok=True, from_cache=False, error="", used_removebg=False):
    return report.LogoResult(
        company=company, ok=ok, from_cache=from_cache, error=error,
        used_removebg=used_removebg,
        png_path=Path(f"{company}.png") if ok else None,
    )


def test_status_label_reflects_cache_and_failure():
    assert make_result("A", ok=True).status_label == "成功"
    assert make_result("A", ok=True, from_cache=True).status_label == "成功(キャッシュ)"
    assert make_result("A", ok=False).status_label == "失敗"


def test_write_csv_includes_all_companies_even_mixed_results(tmp_path):
    results = [make_result("成功社"), make_result("失敗社", ok=False, error="候補なし")]
    out = tmp_path / "report.csv"
    report.write_csv(results, out)
    text = out.read_text(encoding="utf-8-sig")
    assert "成功社" in text and "失敗社" in text
    assert "候補なし" in text


def test_write_failed_lists_only_failed_companies(tmp_path):
    results = [make_result("成功社"), make_result("失敗社1", ok=False),
              make_result("失敗社2", ok=False)]
    out = tmp_path / "failed.txt"
    n = report.write_failed(results, out)
    assert n == 2
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines == ["失敗社1", "失敗社2"]


def test_write_failed_clears_stale_file_when_nothing_failed(tmp_path):
    out = tmp_path / "failed.txt"
    out.write_text("古い失敗\n", encoding="utf-8")
    n = report.write_failed([make_result("成功社")], out)
    assert n == 0
    assert out.read_text(encoding="utf-8") == ""


def test_summary_counts_cache_and_removebg_usage():
    results = [
        make_result("A", from_cache=True),
        make_result("B", used_removebg=True),
        make_result("C", ok=False, error="失敗理由"),
    ]
    text = report.summary(results)
    assert "2/3 件成功" in text
    assert "うちキャッシュ利用: 1 件" in text
    assert "remove.bg 呼び出し: 1 件" in text
    assert "失敗理由" in text
