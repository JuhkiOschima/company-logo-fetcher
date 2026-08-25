"""SerpAPI(Google Images エンジン)による画像検索。

無料枠は 250 検索/月。1社につき1検索を消費する。

注意: SerpAPI はキーをURLクエリで受け取る仕様のため、requests の例外文字列に
キーが混入し得る。外に出すメッセージは必ず net.scrub でマスクする。
"""

from __future__ import annotations

import requests

from net import scrub
from .base import ImageCandidate, SearchError

ENDPOINT = "https://serpapi.com/search.json"
ACCOUNT_ENDPOINT = "https://serpapi.com/account.json"
TIMEOUT = 30


class SerpApiProvider:
    name = "serpapi"

    def __init__(self, api_key: str, *, timeout: int = TIMEOUT) -> None:
        self._api_key = api_key
        self._timeout = timeout

    def _fail(self, message: str) -> SearchError:
        return SearchError(scrub(message, self._api_key))

    def search_images(self, query: str, limit: int) -> list[ImageCandidate]:
        params = {
            "engine": "google_images",
            "q": query,
            "api_key": self._api_key,
            "hl": "ja",
            "gl": "jp",
        }
        try:
            res = requests.get(ENDPOINT, params=params, timeout=self._timeout)
        except requests.RequestException as e:
            raise self._fail(f"検索リクエストに失敗しました: {e}") from None

        if res.status_code == 401:
            raise self._fail("SerpAPI の認証に失敗しました。APIキーを確認してください。")
        if res.status_code == 429:
            raise self._fail("SerpAPI の利用上限に達しました(無料枠は 250 検索/月)。")
        if res.status_code != 200:
            raise self._fail(f"SerpAPI がエラーを返しました (HTTP {res.status_code})")

        data = res.json()
        if "error" in data:
            raise self._fail(f"SerpAPI エラー: {data['error']}")

        results = data.get("images_results") or []
        candidates: list[ImageCandidate] = []
        for item in results[:limit]:
            url = item.get("original")
            if not url:
                continue
            candidates.append(
                ImageCandidate(
                    url=url,
                    title=item.get("title", ""),
                    width=item.get("original_width"),
                    height=item.get("original_height"),
                    source=item.get("source", ""),
                    page_url=item.get("link", ""),
                )
            )
        if not candidates:
            raise self._fail("検索結果が0件でした。")
        return candidates

    def quota(self) -> tuple[int, int]:
        """今月の残り検索数と月間上限を返す。この呼び出しは検索数を消費しない。"""
        try:
            res = requests.get(ACCOUNT_ENDPOINT, params={"api_key": self._api_key}, timeout=15)
        except requests.RequestException as e:
            raise self._fail(f"アカウント情報の取得に失敗しました: {e}") from None
        if res.status_code != 200:
            raise self._fail(f"アカウント情報の取得に失敗しました (HTTP {res.status_code})")
        data = res.json()
        left = data.get("plan_searches_left")
        total = data.get("searches_per_month")
        if left is None or total is None:
            raise self._fail("アカウント情報の形式が想定外でした。")
        return int(left), int(total)
