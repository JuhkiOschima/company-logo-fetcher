"""画像検索プロバイダ。

検索APIは提供終了・料金改定が起きやすいため、プロバイダを差し替え可能にしてある。
新しいプロバイダを足すときは base.SearchProvider を満たすクラスをこの階層に置き、
get_provider() の分岐に追加する。
"""

from __future__ import annotations

from .base import ImageCandidate, SearchError, SearchProvider

__all__ = ["ImageCandidate", "SearchError", "SearchProvider", "get_provider"]


def get_provider(name: str, api_key: str) -> SearchProvider:
    if name == "serpapi":
        from .serpapi import SerpApiProvider

        return SerpApiProvider(api_key)
    raise SearchError(f"未対応の検索プロバイダです: {name}")
