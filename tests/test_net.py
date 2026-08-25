"""VISION.md 対応: 機能横断ルール「通信例外の文字列には秘密情報を含めない」。"""

from __future__ import annotations

import net


def test_scrub_masks_every_occurrence_of_each_secret():
    msg = "failed for key=SECRET123 (retry with SECRET123 again)"
    assert net.scrub(msg, "SECRET123") == "failed for key=*** (retry with *** again)"


def test_scrub_masks_multiple_distinct_secrets():
    msg = "search=SEARCHKEY removebg=BGKEY"
    result = net.scrub(msg, "SEARCHKEY", "BGKEY")
    assert "SEARCHKEY" not in result
    assert "BGKEY" not in result
    assert result == "search=*** removebg=***"


def test_scrub_ignores_empty_secrets():
    assert net.scrub("plain text", "", None or "") == "plain text"


def test_scrub_is_noop_without_secrets():
    assert net.scrub("plain text") == "plain text"
