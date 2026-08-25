"""検索候補のスコアリングとダウンロード。

検索結果の1位が必ずしも適切なロゴとは限らないため、
「ロゴらしさ」で並べ替えてから上位を試す。
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import requests
from PIL import Image, UnidentifiedImageError

import naming
from search.base import ImageCandidate

TIMEOUT = 20
MAX_BYTES = 15 * 1024 * 1024  # 15MB を超える画像はロゴとして扱わない
USER_AGENT = "logo-fetcher/0.1"

# Pillow で開けない形式は remove.bg にも渡せないため候補から外す
UNSUPPORTED_EXT = {"svg", "ico", "avif"}

# ロゴが置かれていることが多く、信頼できる掲載元
TRUSTED_DOMAINS = ("wikipedia.org", "wikimedia.org", "prtimes.jp")


class DownloadError(Exception):
    pass


@dataclass
class DownloadedImage:
    candidate: ImageCandidate
    data: bytes
    image: Image.Image


def score(candidate: ImageCandidate, company: str) -> float:
    """候補の「ロゴらしさ」。大きいほど良い。"""
    s = 0.0

    # 縦横比: ロゴは横長が多い。極端な縦長・巨大な正方形は減点。
    w, h = candidate.width, candidate.height
    if w and h and h > 0:
        ratio = w / h
        if 1.2 <= ratio <= 5.0:
            s += 3.0
        elif 0.9 <= ratio < 1.2:
            s += 1.5           # 正方形のシンボルマークもあり得る
        elif ratio > 8.0 or ratio < 0.5:
            s -= 2.0

        # 解像度: 小さすぎると使えず、大きすぎると写真の可能性が高い
        long_edge = max(w, h)
        if 200 <= long_edge <= 2000:
            s += 2.0
        elif long_edge < 100:
            s -= 3.0
        elif long_edge > 4000:
            s -= 1.0

    # ファイル形式: 透過を持ちうる形式を優遇
    ext = candidate.extension
    if ext in ("png", "webp"):
        s += 2.0
    elif ext in ("jpg", "jpeg"):
        s -= 0.5
    elif ext in UNSUPPORTED_EXT:
        s -= 10.0              # 実質的に除外

    # 掲載元ドメイン: 企業自身のサイトか、信頼できるサイトか
    domain = candidate.domain
    if any(domain.endswith(d) for d in TRUSTED_DOMAINS):
        s += 2.0
    for token in naming.tokens(company):
        if token in domain:
            s += 3.0
            break

    # タイトルに「ロゴ」相当の語があれば加点
    title = candidate.title.lower()
    if "ロゴ" in candidate.title or "logo" in title:
        s += 1.0

    return s


def rank(candidates: list[ImageCandidate], company: str) -> list[ImageCandidate]:
    """スコア降順に並べ替える。処理できない形式は除外する。"""
    usable = [c for c in candidates if c.extension not in UNSUPPORTED_EXT]
    return sorted(usable, key=lambda c: score(c, company), reverse=True)


def download(candidate: ImageCandidate, *, timeout: int = TIMEOUT) -> DownloadedImage:
    """候補をダウンロードし、実際に画像として開けることまで確認する。"""
    try:
        res = requests.get(
            candidate.url,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
            stream=True,
        )
    except requests.RequestException as e:
        raise DownloadError(f"取得に失敗: {e}") from e

    if res.status_code != 200:
        raise DownloadError(f"取得に失敗 (HTTP {res.status_code})")

    content_type = res.headers.get("Content-Type", "")
    if content_type and not content_type.startswith("image/"):
        raise DownloadError(f"画像ではありません (Content-Type: {content_type})")

    data = bytearray()
    for chunk in res.iter_content(8192):
        data.extend(chunk)
        if len(data) > MAX_BYTES:
            raise DownloadError("画像が大きすぎます (15MB超)")
    data = bytes(data)

    # Content-Type を信用せず、実際に開けるかで判定する
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError) as e:
        raise DownloadError(f"画像として読み込めません: {e}") from e

    return DownloadedImage(candidate=candidate, data=data, image=img)


def has_transparency(img: Image.Image, *, min_ratio: float = 0.02) -> bool:
    """既に透過を持っているか。持っていれば remove.bg を呼ばずに済む。"""
    if img.mode not in ("RGBA", "LA", "P"):
        return False
    rgba = img.convert("RGBA")
    alpha = rgba.getchannel("A")
    if alpha.getextrema()[0] >= 250:
        return False
    transparent = sum(count for value, count in enumerate(alpha.histogram()) if value < 250)
    return transparent / (rgba.width * rgba.height) >= min_ratio
