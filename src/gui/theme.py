"""画面全体のフォント定義。

サイズを変えたいときはここだけを直せばよい。
既定のボタン・ラベル(ttk ウィジェット)にもまとめて適用する。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

FAMILY = "Meiryo UI"

HEADING = (FAMILY, 13, "bold")   # 「① 企業名を入力」などの見出し
BODY = (FAMILY, 12)              # 入力欄・ボタン・一般テキスト
COMPANY = (FAMILY, 12, "bold")   # カードの企業名
CAPTION = (FAMILY, 10)           # 補足説明・取得元などの小さめの文字


def apply(root: tk.Misc) -> None:
    """ttk の既定スタイルと Tk 標準フォントに本文サイズを適用する。"""
    style = ttk.Style(root)
    for name in ("TLabel", "TButton", "TEntry", "TCheckbutton", "TRadiobutton"):
        style.configure(name, font=BODY)
    # メッセージボックス等が使う Tk 標準フォントも合わせる
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont"):
        try:
            tkfont.nametofont(name).configure(family=FAMILY, size=BODY[1])
        except tk.TclError:
            pass
