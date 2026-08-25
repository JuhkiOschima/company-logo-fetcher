"""企業名の入力欄(罫線ノート風)。

- 1行 = 1社。行の下に薄い点線の罫線が入る
- Enter で次の行が増え、空の行で Backspace すると行が消える
- 様々な書式のリストを貼り付けると自動で1行1社に整理する(smart_split)
  対応する区切り: 改行 / タブ / 、 , ; / | ・空白、および行頭の番号(1. ①)や中黒
"""

from __future__ import annotations

import re
import tkinter as tk
from tkinter import ttk
from typing import Callable

from gui import theme

_FONT = theme.BODY
_PLACEHOLDER = "ここに企業名を入力(リストの貼り付けもできます)"
_PLACEHOLDER_COLOR = "#999999"
_TEXT_COLOR = "#222222"
_BORDER = "#c8c8c8"
_BORDER_FOCUS = "#0078d4"
_RULE_COLOR = "#d0d0d0"
_BG = "#ffffff"
_SELECT_BG = "#cce4f7"  # Ctrl+A で全行選択したときの背景
_VISIBLE_ROWS = 5
_ROW_H = 36

from naming import smart_split, strip_lead_mark  # noqa: F401  (smart_split は互換のため再輸出)


class _Row:
    """入力1行分(エントリと、その下の点線罫線)。"""

    def __init__(self, panel: "LinedInput", index: int) -> None:
        self.panel = panel
        self.frame = tk.Frame(panel.inner, bg=_BG)
        self.entry = tk.Entry(
            self.frame, font=_FONT, relief="flat", bd=0, highlightthickness=0,
            bg=_BG, fg=_TEXT_COLOR, insertbackground=_TEXT_COLOR, disabledbackground=_BG,
        )
        self.entry.pack(fill="x", padx=10, pady=(5, 2))
        self.rule = tk.Canvas(self.frame, height=2, bg=_BG, highlightthickness=0)
        self.rule.pack(fill="x")
        self.rule.bind("<Configure>", self._draw_rule)

        e = self.entry
        e.bind("<Return>", lambda _e: panel._on_return(self))
        e.bind("<BackSpace>", lambda _e: panel._on_backspace(self))
        e.bind("<Up>", lambda _e: panel._focus_neighbor(self, -1))
        e.bind("<Down>", lambda _e: panel._focus_neighbor(self, +1))
        e.bind("<<Paste>>", lambda _e: panel._on_paste(self))
        e.bind("<FocusIn>", lambda _e: panel._clear_placeholder(self))
        e.bind("<KeyRelease>", lambda _e: panel._notify())
        e.bind("<MouseWheel>", panel._on_wheel)
        # Ctrl+A で全行選択 → Delete/BackSpace や文字入力で全消去
        e.bind("<Control-a>", lambda _e: panel.select_all())
        e.bind("<Control-A>", lambda _e: panel.select_all())
        e.bind("<Key>", panel._on_key_while_all_selected)
        e.bind("<Button-1>", lambda _e: panel._clear_selection_marks())
        self.frame.pack(fill="x")
        if index is not None:
            self._reorder(index)

    def _reorder(self, index: int) -> None:
        siblings = self.panel.inner.pack_slaves()
        if index < len(siblings) - 1:
            self.frame.pack_configure(before=siblings[index])

    def _draw_rule(self, event: tk.Event) -> None:
        self.rule.delete("all")
        self.rule.create_line(10, 1, event.width - 10, 1, fill=_RULE_COLOR, dash=(2, 3))

    def get(self) -> str:
        if self.panel._placeholder_row is self:
            return ""
        return self.entry.get().strip()

    def set(self, text: str) -> None:
        self.entry.delete(0, "end")
        self.entry.insert(0, text)


class LinedInput(ttk.Frame):
    def __init__(self, parent: tk.Widget, on_change: Callable[[], None] | None = None) -> None:
        super().__init__(parent)
        self.on_change = on_change
        self.rows: list[_Row] = []
        self._placeholder_row: _Row | None = None
        self._enabled = True
        self._all_selected = False

        self.canvas = tk.Canvas(
            self, height=_VISIBLE_ROWS * _ROW_H, bg=_BG,
            highlightthickness=1, highlightbackground=_BORDER,
        )
        bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=bar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        bar.grid(row=0, column=1, sticky="ns")
        self.columnconfigure(0, weight=1)

        self.inner = tk.Frame(self.canvas, bg=_BG)
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>",
                        lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfigure(self._window, width=e.width))
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-1>", lambda _e: self._focus_last())

        self.set_companies([])

    # --- 値の出し入れ ---

    def companies(self) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        for row in self.rows:
            name = strip_lead_mark(row.get())
            if name and name not in seen:
                seen.add(name)
                names.append(name)
        return names

    def set_companies(self, names: list[str]) -> None:
        self._all_selected = False
        for row in self.rows:
            row.frame.destroy()
        self.rows = []
        self._placeholder_row = None
        if names:
            for i, n in enumerate(names):
                row = _Row(self, i)
                row.set(n)
                self.rows.append(row)
        else:
            row = _Row(self, 0)
            row.entry.configure(fg=_PLACEHOLDER_COLOR)
            row.set(_PLACEHOLDER)
            self._placeholder_row = row
            self.rows.append(row)
        self._notify()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        state = "normal" if enabled else "disabled"
        for row in self.rows:
            row.entry.configure(state=state)

    # --- 行の操作 ---

    def _insert_row(self, index: int) -> _Row:
        row = _Row(self, index)
        self.rows.insert(index, row)
        return row

    def _on_return(self, row: _Row) -> str:
        i = self.rows.index(row)
        new = self._insert_row(i + 1)
        new.entry.focus_set()
        self._scroll_to(new)
        return "break"

    def _on_backspace(self, row: _Row) -> str | None:
        if row.entry.get() == "" and len(self.rows) > 1:
            i = self.rows.index(row)
            row.frame.destroy()
            self.rows.remove(row)
            target = self.rows[max(0, i - 1)]
            target.entry.focus_set()
            target.entry.icursor("end")
            self._notify()
            return "break"
        return None

    def _focus_neighbor(self, row: _Row, delta: int) -> str:
        i = self.rows.index(row) + delta
        if 0 <= i < len(self.rows):
            self.rows[i].entry.focus_set()
            self.rows[i].entry.icursor("end")
            self._scroll_to(self.rows[i])
        return "break"

    def _focus_last(self) -> None:
        if self.rows and self._enabled:
            self.rows[-1].entry.focus_set()

    # --- 全選択・全消去 ---

    def select_all(self) -> str:
        """Ctrl+A。全行を選択状態にする(見た目で選択が分かるようにする)。

        この状態で Delete / BackSpace / 文字入力を行うと全行が消える。
        1行しかない場合は、その行の文字を選択するだけの通常動作にする。
        """
        if len(self.rows) <= 1:
            row = self.rows[0] if self.rows else None
            if row is not None:
                row.entry.select_range(0, "end")
                row.entry.icursor("end")
            return "break"

        self._all_selected = True
        for row in self.rows:
            row.entry.select_range(0, "end")
            row.entry.configure(bg=_SELECT_BG)
            row.frame.configure(bg=_SELECT_BG)
            row.rule.configure(bg=_SELECT_BG)
        return "break"

    def _clear_selection_marks(self) -> None:
        if not self._all_selected:
            return
        self._all_selected = False
        for row in self.rows:
            try:
                row.entry.configure(bg=_BG)
                row.frame.configure(bg=_BG)
                row.rule.configure(bg=_BG)
            except tk.TclError:
                pass

    def _on_key_while_all_selected(self, event: tk.Event) -> str | None:
        """全行選択中のキー入力。消去系なら全消去、文字入力なら置き換える。"""
        if not self._all_selected:
            return None
        if event.keysym in ("Control_L", "Control_R", "Shift_L", "Shift_R", "Alt_L", "Alt_R"):
            return None
        if event.state & 0x4 and event.keysym.lower() in ("a", "c", "x"):
            return None  # Ctrl+A/C/X はそのまま通す

        if event.keysym in ("Delete", "BackSpace"):
            self.set_companies([])
            self._focus_last()
            return "break"
        if event.char and event.char.isprintable():
            self.set_companies([])
            row = self.rows[0]
            self._clear_placeholder(row)
            row.entry.focus_set()
            row.entry.insert(0, event.char)
            self._notify()
            return "break"
        self._clear_selection_marks()
        return None

    # --- 貼り付けの自動整理 ---

    def _on_paste(self, row: _Row) -> str | None:
        try:
            pasted = self.selection_get(selection="CLIPBOARD")
        except tk.TclError:
            return "break"
        names = smart_split(pasted)
        if len(names) <= 1:
            self._clear_placeholder(row)
            row.entry.insert("insert", names[0] if names else "")
            self._notify()
            return "break"
        # 複数社 → 既存の内容と重複しないものを、この行の位置から流し込む
        self._clear_placeholder(row)
        existing = set(self.companies())
        fresh = [n for n in names if n not in existing]
        i = self.rows.index(row)
        for n in fresh:
            if row is not None and row.get() == "" and self._placeholder_row is not row:
                row.set(n)
                row = None
            else:
                i += 1
                self._insert_row(i).set(n)
        self._notify()
        return "break"

    # --- 表示まわり ---

    def _clear_placeholder(self, row: _Row) -> None:
        if self._placeholder_row is row:
            self._placeholder_row = None
            row.set("")
            row.entry.configure(fg=_TEXT_COLOR)

    def _scroll_to(self, row: _Row) -> None:
        self.canvas.update_idletasks()
        bbox = self.canvas.bbox("all")
        if bbox and bbox[3] > self.canvas.winfo_height():
            y = row.frame.winfo_y() / bbox[3]
            self.canvas.yview_moveto(max(0.0, y - 0.6))

    def _on_wheel(self, event: tk.Event) -> None:
        bbox = self.canvas.bbox("all")
        if bbox and bbox[3] > self.canvas.winfo_height():
            self.canvas.yview_scroll(-1 * int(event.delta / 120), "units")

    def _notify(self) -> None:
        if self.on_change is not None:
            self.on_change()
