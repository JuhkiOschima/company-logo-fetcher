"""VISION.md 対応: 機能横断ルール「通信例外の文字列には秘密情報を含めない」。

SerpAPI はキーをURLクエリで受け取るため、requests の例外文字列にキーが
混入し得る、という具体的な動機に対応するテスト。
"""

from __future__ import annotations

import pytest
import requests

from search.serpapi import SerpApiProvider


class FakeResponse:
    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self._json = json_data or {}

    def json(self):
        return self._json


def test_connection_exception_message_is_scrubbed(monkeypatch):
    secret = "sk-real-secret-key-123"
    provider = SerpApiProvider(secret)

    def boom(*a, **k):
        # requests がキーをURLに含めて例外メッセージに出す典型例を再現
        raise requests.RequestException(f"failed for url with api_key={secret}")

    monkeypatch.setattr("search.serpapi.requests.get", boom)

    with pytest.raises(Exception) as exc:
        provider.search_images("トヨタ ロゴ", 5)
    assert secret not in str(exc.value)
    assert "***" in str(exc.value)


def test_zero_results_raises_without_leaking_key(monkeypatch):
    secret = "sk-another-secret"
    provider = SerpApiProvider(secret)
    monkeypatch.setattr("search.serpapi.requests.get",
                        lambda *a, **k: FakeResponse(200, {"images_results": []}))
    with pytest.raises(Exception) as exc:
        provider.search_images("A社 ロゴ", 5)
    assert secret not in str(exc.value)


def test_quota_parses_left_and_total(monkeypatch):
    provider = SerpApiProvider("key")
    monkeypatch.setattr(
        "search.serpapi.requests.get",
        lambda *a, **k: FakeResponse(200, {"plan_searches_left": 200, "searches_per_month": 250}),
    )
    assert provider.quota() == (200, 250)
