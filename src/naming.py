"""企業名の正規化とファイル名の生成。"""

from __future__ import annotations

import re
import unicodedata
from pathlib import PurePath

# 検索の邪魔になりやすい法人格表記。前後どちらに付いていても取り除く。
_LEGAL_SUFFIXES = [
    "株式会社", "有限会社", "合同会社", "合資会社", "合名会社",
    "(株)", "(有)", "(株)", "(有)",
    "Inc.", "Inc", "Corp.", "Corp", "Corporation", "Co., Ltd.", "Co.,Ltd.",
    "Co., Ltd", "Ltd.", "Ltd", "LLC", "K.K.", "KK",
]

# Windows のファイル名に使えない文字。パス区切り(\ と /)は必ず潰す。
# raw文字列のエスケープ解釈で \ が抜け落ちる事故があったため、re.escape で明示的に組み立てる。
_INVALID_FILENAME = re.compile("[" + re.escape("\\/:*?\"<>|") + "]")

# Windows の予約デバイス名(拡張子を付けてもファイルとして扱えない)
_RESERVED_NAMES = (
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


def strip_legal(name: str) -> str:
    """法人格表記を取り除く。取り除いた結果が空になる場合は元の名前を返す。"""
    s = name.strip()
    for suffix in _LEGAL_SUFFIXES:
        # 長いものから消したいので、含まれる限り繰り返し除去する
        for _ in range(2):
            if s.startswith(suffix):
                s = s[len(suffix):].strip()
            if s.endswith(suffix):
                s = s[: -len(suffix)].strip()
    return s or name.strip()


def tokens(name: str) -> list[str]:
    """ドメイン照合用のトークン。英数字部分を小文字で取り出す。"""
    normalized = unicodedata.normalize("NFKC", strip_legal(name)).lower()
    return [t for t in re.findall(r"[a-z0-9]+", normalized) if len(t) >= 3]


def safe_filename(name: str) -> str:
    """企業名をそのままファイル名に使えるようにする(日本語はそのまま残す)。

    Webサーバー経由で任意の文字列が来るため、パス区切り・「..」・予約名を
    確実に無害化する(書き込み側パストラバーサル対策)。
    """
    s = _INVALID_FILENAME.sub("_", name.strip())
    s = s.rstrip(". ")  # Windows は末尾のドット・空白を嫌う
    # パス成分として解釈される余地を一切残さない
    if s in ("", ".", "..") or PurePath(s).name != s:
        return "unnamed"
    if s.split(".")[0].upper() in _RESERVED_NAMES:
        s = "_" + s
    return s


# --- 企業リスト文字列の分解(GUI / Web 共通) ---
# 区切り文字は全角半角の取り違えバグを避けるため、ユニコードエスケープで明示する。
# 、=、 ，=， ；=； ／=／ ｜=｜
_STRONG_DELIM = re.compile(r"[\r\n\t,;/|、，；／｜]+")
# 行頭の列挙記号: ・ • - * ※ や「1.」「2)」「③」など
# ・=・ •=• ▪=▪ ◦=◦ ※=※ –—=ダッシュ （）=()
# ．=. 、=、 ①-⑳=①-⑳
_LEAD_MARK = re.compile(
    r"^\s*(?:[・•▪◦*※\-–—]"
    r"|[(（]?\d{1,3}[.\)、．）]"
    r"|[①-⑳])\s*"
)


def strip_lead_mark(text: str) -> str:
    """行頭の列挙記号(・ 1. ③ など)を取り除く。"""
    return _LEAD_MARK.sub("", text.strip()).strip()


def smart_split(raw: str) -> list[str]:
    """貼り付けテキストを企業名リストに整理する。

    強い区切り(改行・読点・スラッシュなど)を優先し、それが無い
    1行テキストに限り空白区切りを試す。空要素・重複は取り除く。
    """
    text = raw.strip()
    if not text:
        return []
    parts = [p for p in _STRONG_DELIM.split(text) if p and p.strip()]
    if len(parts) == 1:
        tokens = [t for t in re.split(r"[ 　]+", parts[0].strip()) if t]
        if len(tokens) >= 2:
            parts = tokens
    names: list[str] = []
    seen: set[str] = set()
    for p in parts:
        name = strip_lead_mark(p)
        # 「1、トヨタ」のような貼り付けで番号だけが1要素として残るのを捨てる
        if re.fullmatch(r"[0-90-9①-⑳]+", name):
            continue
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def read_company_list(path) -> list[str]:
    """companies.txt を読む。空行と # で始まる行は無視する。重複は先勝ちで除く。"""
    names: list[str] = []
    seen: set[str] = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            name = line.strip()
            if not name or name.startswith("#"):
                continue
            if name in seen:
                continue
            seen.add(name)
            names.append(name)
    return names
