"""remove.bg による背景透過。

APIキーは呼び出し側から受け取るだけで、値をログ・例外メッセージに出さない。
従量課金のため、呼び出しは1画像につき1回に限る(リトライしない)。
"""

from __future__ import annotations

import io

import requests
from PIL import Image

ENDPOINT = "https://api.remove.bg/v1.0/removebg"
TIMEOUT = 60


class RemoveBgError(Exception):
    pass


class RemoveBgCreditError(RemoveBgError):
    """クレジット不足。これ以上呼んでも無駄なので処理全体を止める判断に使う。"""


class RemoveBgRateLimitError(RemoveBgError):
    """レート制限。時間をおけば回復する(クレジット不足と区別し、恒久停止にしない)。"""


def remove_background(image_bytes: bytes, api_key: str, *, size: str = "preview",
                      timeout: int = TIMEOUT) -> bytes:
    """画像バイト列を remove.bg に渡し、透過PNGのバイト列を返す。

    呼び出しごとにクレジットを消費するため、失敗しても自動リトライはしない。
    """
    try:
        res = requests.post(
            ENDPOINT,
            files={"image_file": ("image", image_bytes)},
            data={"size": size, "format": "png"},
            headers={"X-Api-Key": api_key},
            timeout=timeout,
        )
    except requests.RequestException as e:
        raise RemoveBgError(f"remove.bg への接続に失敗しました: {e}") from e

    if res.status_code == 200:
        return res.content

    if res.status_code == 403:
        raise RemoveBgError("remove.bg の認証に失敗しました。APIキーを確認してください。")
    if res.status_code == 402:
        raise RemoveBgCreditError("remove.bg のクレジットが不足しています。")
    if res.status_code == 429:
        raise RemoveBgRateLimitError("remove.bg のレート制限に達しました。時間をおいて再実行してください。")

    detail = ""
    try:
        errors = res.json().get("errors") or []
        if errors:
            detail = f": {errors[0].get('title', '')}"
    except ValueError:
        pass
    raise RemoveBgError(f"remove.bg がエラーを返しました (HTTP {res.status_code}){detail}")


def to_image(png_bytes: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(png_bytes))
    img.load()
    return img.convert("RGBA")


ACCOUNT_ENDPOINT = "https://api.remove.bg/v1.0/account"


def quota(api_key: str, *, timeout: int = 15) -> tuple[int, float]:
    """残りの無料API回数と有料クレジット残高を返す。この呼び出しは無料。"""
    try:
        res = requests.get(ACCOUNT_ENDPOINT, headers={"X-Api-Key": api_key}, timeout=timeout)
    except requests.RequestException as e:
        raise RemoveBgError(f"アカウント情報の取得に失敗しました: {e}") from None
    if res.status_code != 200:
        raise RemoveBgError(f"アカウント情報の取得に失敗しました (HTTP {res.status_code})")
    attrs = (res.json().get("data") or {}).get("attributes") or {}
    free_calls = (attrs.get("api") or {}).get("free_calls")
    credits = (attrs.get("credits") or {}).get("total")
    if free_calls is None:
        raise RemoveBgError("アカウント情報の形式が想定外でした。")
    return int(free_calls), float(credits or 0)
