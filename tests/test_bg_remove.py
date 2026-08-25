"""VISION.md 対応: 機能横断ルール「クレジット不足(402)とレート制限(429)を区別する」。"""

from __future__ import annotations

import pytest

import bg_remove


class FakeResponse:
    def __init__(self, status_code, content=b"", json_data=None):
        self.status_code = status_code
        self.content = content
        self._json = json_data or {}

    def json(self):
        return self._json


def test_402_raises_credit_error(monkeypatch):
    monkeypatch.setattr(bg_remove.requests, "post", lambda *a, **k: FakeResponse(402))
    with pytest.raises(bg_remove.RemoveBgCreditError):
        bg_remove.remove_background(b"img", "key")


def test_429_raises_rate_limit_error_not_credit_error(monkeypatch):
    monkeypatch.setattr(bg_remove.requests, "post", lambda *a, **k: FakeResponse(429))
    with pytest.raises(bg_remove.RemoveBgRateLimitError):
        bg_remove.remove_background(b"img", "key")
    # 429 は恒久停止の判断(RemoveBgCreditError)に使ってはいけない
    with pytest.raises(bg_remove.RemoveBgError):
        bg_remove.remove_background(b"img", "key")


def test_403_raises_generic_auth_error(monkeypatch):
    monkeypatch.setattr(bg_remove.requests, "post", lambda *a, **k: FakeResponse(403))
    with pytest.raises(bg_remove.RemoveBgError) as exc:
        bg_remove.remove_background(b"img", "key")
    assert not isinstance(exc.value, bg_remove.RemoveBgCreditError)
    assert not isinstance(exc.value, bg_remove.RemoveBgRateLimitError)


def test_200_returns_content(monkeypatch):
    monkeypatch.setattr(bg_remove.requests, "post",
                        lambda *a, **k: FakeResponse(200, content=b"PNGDATA"))
    assert bg_remove.remove_background(b"img", "key") == b"PNGDATA"


def test_quota_parses_free_calls_and_credits(monkeypatch):
    payload = {"data": {"attributes": {"api": {"free_calls": 42}, "credits": {"total": 1.5}}}}
    monkeypatch.setattr(bg_remove.requests, "get", lambda *a, **k: FakeResponse(200, json_data=payload))
    assert bg_remove.quota("key") == (42, 1.5)


def test_quota_defaults_credits_to_zero_when_absent(monkeypatch):
    payload = {"data": {"attributes": {"api": {"free_calls": 10}}}}
    monkeypatch.setattr(bg_remove.requests, "get", lambda *a, **k: FakeResponse(200, json_data=payload))
    assert bg_remove.quota("key") == (10, 0.0)
