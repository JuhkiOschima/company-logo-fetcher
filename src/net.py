"""HTTPS まわりの共通設定。

社内プロキシがTLS検査を行う環境では、Python 標準の証明書バンドル(certifi)に
社内CAが含まれず SSL エラーになる。truststore で Windows の証明書ストアを
使うことで解決する。
"""

from __future__ import annotations


def setup_tls() -> str:
    """OSの証明書ストアを使うようにする。エントリポイントの最初で呼ぶ。"""
    try:
        import truststore
        truststore.inject_into_ssl()
        return "truststore(OS証明書ストア)"
    except ImportError:
        return "certifi(標準バンドル)"


def scrub(text: str, *secrets: str) -> str:
    """エラーメッセージ等から機微情報(APIキー等)を取り除く。"""
    for s in secrets:
        if s:
            text = text.replace(s, "***")
    return text
