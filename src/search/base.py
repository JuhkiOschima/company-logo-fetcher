"""検索プロバイダの共通インターフェース。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse


class SearchError(Exception):
    """検索の失敗。APIキーの値はメッセージに含めない。"""


@dataclass
class ImageCandidate:
    """検索結果の1件。ダウンロード前の候補。"""

    url: str
    title: str = ""
    width: int | None = None
    height: int | None = None
    source: str = ""          # 掲載元サイト名(プロバイダが返すもの)
    page_url: str = ""        # 画像が掲載されているページ

    @property
    def domain(self) -> str:
        host = urlparse(self.page_url or self.url).netloc.lower()
        return host[4:] if host.startswith("www.") else host

    @property
    def extension(self) -> str:
        path = urlparse(self.url).path.lower()
        _, _, ext = path.rpartition(".")
        return ext if 0 < len(ext) <= 4 else ""


class SearchProvider(Protocol):
    """画像検索プロバイダ。"""

    name: str

    def search_images(self, query: str, limit: int) -> list[ImageCandidate]:
        """クエリで画像を検索し、上位 limit 件の候補を返す。"""
        ...
