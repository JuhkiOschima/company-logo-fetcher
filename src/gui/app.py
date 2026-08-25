r"""ロゴ取得GUI。企業名の入力 → 取得 → クリックでコピーまで1画面で完結する。

    .venv\Scripts\pythonw.exe src\gui\app.py

- 上部の入力欄に企業名(1行1社。複数行貼り付け可)→「ロゴを取得」
- サムネイルまたは「コピー」でクリップボードへ(PowerPoint で Ctrl+V)
- 「やり直し」で次の検索候補から取り直す(remove.bg のクレジットを消費し得る)
"""

from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

SRC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC))

import paths  # noqa: E402

ROOT = paths.app_root()

import net  # noqa: E402

net.setup_tls()

from PIL import ImageTk  # noqa: E402

import bg_remove  # noqa: E402
import clipboard  # noqa: E402
import config as config_mod  # noqa: E402
import naming  # noqa: E402
import pipeline  # noqa: E402
import pptx_export  # noqa: E402
import report as report_mod  # noqa: E402
from gui import theme, thumbs  # noqa: E402
from gui.input_panel import LinedInput, smart_split  # noqa: E402
from report import LogoResult  # noqa: E402
from search import get_provider  # noqa: E402

COLUMNS = 3
DONE = None  # 一括処理完了を知らせるキューの印
QUOTA = "quota"  # 残り検索数の更新を知らせるキューの印


class Card:
    """1社分の表示。"""

    def __init__(self, app: "App", parent: ttk.Frame, company: str, index: int) -> None:
        self.app = app
        self.company = company
        self.png_path = app.cfg.output.dir / f"{naming.safe_filename(company)}.png"

        # 配置(grid)は App 側が絞り込み結果に応じて行う
        self.frame = ttk.Frame(parent, padding=6, relief="groove", borderwidth=1)

        self.thumb_label = ttk.Label(self.frame, cursor="hand2")
        self.thumb_label.pack()
        self.thumb_label.bind("<Button-1>", lambda _e: self.copy())

        ttk.Label(self.frame, text=company, font=theme.COMPANY).pack(pady=(4, 0))
        self.status = ttk.Label(self.frame, text="", font=theme.CAPTION, foreground="#666666")
        self.status.pack()

        row = ttk.Frame(self.frame)
        row.pack(pady=(4, 0))
        self.copy_btn = ttk.Button(row, text="コピー", command=self.copy, width=10)
        self.copy_btn.pack(side="left", padx=2)
        self.retry_btn = ttk.Button(row, text="やり直し", command=self.retry, width=10)
        self.retry_btn.pack(side="left", padx=2)

        self.refresh()

    def refresh(self) -> None:
        photo = ImageTk.PhotoImage(thumbs.make_thumbnail(self.png_path))
        self.thumb_label.configure(image=photo)
        self.thumb_label.image = photo  # GC 対策で参照を保持
        if self.png_path.exists():
            meta = pipeline.CompanyCache(self.app.cfg.cache_dir, self.company).load_meta()
            domain = meta.get("source_domain", "")
            self.status.configure(text=f"取得元: {domain}" if domain else "取得済み")
            self.copy_btn.state(["!disabled"])
        else:
            self.status.configure(text="未取得")
            self.copy_btn.state(["disabled"])

    def copy(self) -> None:
        if not self.png_path.exists():
            return
        try:
            clipboard.copy_for_powerpoint(self.png_path)
        except Exception as e:
            messagebox.showerror("コピー失敗", str(e))
            return
        self.app.set_status(
            f"「{self.company}」をコピーしました。PowerPoint で Ctrl+V で貼り付けられます。")

    def retry(self) -> None:
        if self.app.provider is None:
            self.app.warn_no_keys()
            return
        if not messagebox.askyesno(
                "やり直し",
                f"「{self.company}」を次の検索候補から取り直します。\n"
                "取得画像によっては remove.bg のクレジットを1消費します。よろしいですか?"):
            return
        self.app.set_all_busy(True)
        self.app.set_status(f"「{self.company}」を再取得しています…")
        self.app.run_retry(self)

    def set_busy(self, busy: bool) -> None:
        state = ["disabled"] if busy else ["!disabled"]
        self.copy_btn.state(state)
        self.retry_btn.state(state)


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("企業ロゴ取得ツール")
        root.minsize(720, 520)
        self.queue: "queue.Queue[tuple[Card | None, object]]" = queue.Queue()
        self.busy = False

        try:
            self.cfg = config_mod.load(root=ROOT)
        except config_mod.ConfigError as e:
            messagebox.showerror("設定エラー", str(e))
            raise SystemExit(1) from e

        self.provider = None
        try:
            self.cfg.require_keys()
            self.provider = get_provider(self.cfg.search.provider, self.cfg.search.api_key)
        except config_mod.ConfigError:
            pass  # コピー専用モード。取得操作時に案内する。

        # --- ① 入力エリア ---
        top = ttk.Frame(root, padding=(10, 8, 10, 0))
        top.pack(fill="x")
        ttk.Label(top, text="① 企業名を入力(1行に1社。リストを貼り付けると自動で整理されます)",
                  font=theme.HEADING).pack(anchor="w")
        self.input = LinedInput(top, on_change=self._update_fetch_bar)
        self.input.pack(fill="x", pady=(4, 4))

        bar = ttk.Frame(top)
        bar.pack(fill="x")
        self.quota_label = ttk.Label(bar, text="", font=theme.CAPTION, foreground="#666666")
        self.quota_label.pack(side="left")
        self.fetch_btn = ttk.Button(bar, text="ロゴを取得", width=18, command=self.start_fetch)
        self.fetch_btn.pack(side="right")

        # --- ② ロゴ一覧 ---
        ttk.Separator(root).pack(fill="x", pady=6)
        head = ttk.Frame(root, padding=(10, 0))
        head.pack(fill="x")
        ttk.Label(head, text="② ロゴ一覧(クリックでコピー → PowerPoint に Ctrl+V)",
                  font=theme.HEADING).pack(side="left")

        # 企業名での絞り込み
        search = ttk.Frame(head)
        search.pack(side="right")
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *_: self._apply_filter())
        self.filter_entry = ttk.Entry(search, textvariable=self.filter_var, width=20,
                                      font=theme.BODY)
        self.filter_entry.pack(side="left")
        self.filter_entry.bind("<Escape>", lambda _e: self.clear_filter())
        self.clear_filter_btn = ttk.Button(search, text="×", width=3,
                                           command=self.clear_filter)
        self.clear_filter_btn.pack(side="left", padx=(2, 0))
        self.filter_hint = ttk.Label(head, text="🔍 企業名で絞り込み",
                                     font=theme.CAPTION, foreground="#999999")
        self.filter_hint.pack(side="right", padx=(0, 6))

        # 一覧はスクロールできるようにする(社数が増えても全件見られる)
        list_area = ttk.Frame(root)
        list_area.pack(fill="both", expand=True)
        self.list_canvas = tk.Canvas(list_area, highlightthickness=0,
                                     background=self._bg_color())
        list_bar = ttk.Scrollbar(list_area, orient="vertical", command=self.list_canvas.yview)
        self.list_canvas.configure(yscrollcommand=list_bar.set)
        self.list_canvas.pack(side="left", fill="both", expand=True)
        list_bar.pack(side="right", fill="y")

        self.grid_frame = ttk.Frame(self.list_canvas, padding=8)
        self._grid_window = self.list_canvas.create_window((0, 0), window=self.grid_frame,
                                                           anchor="nw")
        self.grid_frame.bind(
            "<Configure>",
            lambda _e: self.list_canvas.configure(scrollregion=self.list_canvas.bbox("all")))
        self.list_canvas.bind(
            "<Configure>",
            lambda e: self.list_canvas.itemconfigure(self._grid_window, width=e.width))
        # ホイールはウィンドウ全体で受け、一覧の上にいるときだけ動かす
        root.bind_all("<MouseWheel>", self._on_list_wheel)

        self.empty_label = ttk.Label(self.grid_frame, text="", font=theme.BODY,
                                     foreground="#888888")

        bottom = ttk.Frame(root, padding=(10, 0, 10, 8))
        bottom.pack(fill="x")
        buttons = ttk.Frame(bottom)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="全ロゴ入り pptx を開く", command=self.open_pptx).pack(side="left")
        ttk.Button(buttons, text="出力フォルダを開く", command=self.open_folder).pack(side="left", padx=6)
        ttk.Label(bottom,
                  text="※「全ロゴ入り pptx」= 全社のロゴを1枚のスライドに並べた PowerPoint。"
                       "1社ずつコピーせず、まとめてロゴを出力したいときはこちらが便利です。",
                  font=theme.CAPTION, foreground="#666666").pack(anchor="w", pady=(2, 0))

        self.status_var = tk.StringVar(value="企業名を入力して「ロゴを取得」を押してください。")
        ttk.Label(root, textvariable=self.status_var, padding=(8, 4),
                  relief="sunken", anchor="w").pack(fill="x", side="bottom")

        self.cards: list[Card] = []
        self.input.set_companies(self._initial_companies())
        self._build_cards()
        self._update_fetch_bar()
        self._refresh_quota()
        root.after(100, self._poll)

    # --- 画面の組み立て ---

    def _initial_companies(self) -> list[str]:
        list_path = ROOT / "companies.txt"
        return naming.read_company_list(list_path) if list_path.exists() else []

    def _all_companies(self) -> list[str]:
        """入力欄の企業に、出力フォルダにロゴだけある企業も足した一覧。"""
        companies = list(self.input.companies())
        known = {naming.safe_filename(c) for c in companies}
        for p in sorted(self.cfg.output.dir.glob("*.png")):
            if p.stem not in known:
                companies.append(p.stem)
        return companies

    def _build_cards(self) -> None:
        for card in self.cards:
            card.frame.destroy()
        self.cards = [Card(self, self.grid_frame, c, i)
                      for i, c in enumerate(self._all_companies())]
        self._apply_filter()

    def _bg_color(self) -> str:
        try:
            return ttk.Style().lookup("TFrame", "background") or "#f0f0f0"
        except tk.TclError:
            return "#f0f0f0"

    def clear_filter(self) -> str:
        self.filter_var.set("")
        return "break"

    def _apply_filter(self) -> None:
        """絞り込み語に一致するカードだけを並べ直す。"""
        if not hasattr(self, "empty_label"):
            return  # 画面構築の途中
        word = self.filter_var.get().strip().lower()
        shown = 0
        for card in self.cards:
            if word and word not in card.company.lower():
                card.frame.grid_forget()
                continue
            card.frame.grid(row=shown // COLUMNS, column=shown % COLUMNS,
                            padx=6, pady=6, sticky="n")
            shown += 1

        self.filter_hint.configure(text="" if word else "🔍 企業名で絞り込み")
        if self.cards and shown == 0:
            self.empty_label.configure(text=f"「{self.filter_var.get().strip()}」に一致する企業はありません。")
            self.empty_label.grid(row=0, column=0, sticky="w", padx=6, pady=8)
        else:
            self.empty_label.grid_forget()
        self.list_canvas.yview_moveto(0)

    def _on_list_wheel(self, event: tk.Event) -> None:
        """一覧の上でホイールを回したときだけスクロールする。"""
        if not hasattr(self, "list_canvas"):
            return
        widget = self.root.winfo_containing(event.x_root, event.y_root)
        while widget is not None:
            if widget is self.list_canvas:
                break
            if widget is self.input:  # 入力欄は自前のスクロールを持つ
                return
            widget = getattr(widget, "master", None)
        else:
            return
        bbox = self.list_canvas.bbox("all")
        if bbox and bbox[3] > self.list_canvas.winfo_height():
            self.list_canvas.yview_scroll(-1 * int(event.delta / 120), "units")

    def _update_fetch_bar(self) -> None:
        if not hasattr(self, "fetch_btn"):
            return  # 画面構築の途中(入力欄の初期化時)はまだボタンがない
        if not self.busy:
            self.fetch_btn.state(["!disabled"] if self.input.companies() else ["disabled"])

    # --- 一括取得 ---

    def start_fetch(self) -> None:
        names = self.input.companies()
        if not names or self.busy:
            return
        # 保険: 行内に区切り文字が残っていたら、ここでも1行1社に分解する
        flat: list[str] = []
        seen: set[str] = set()
        for n in names:
            for x in (smart_split(n) or [n]):
                if x not in seen:
                    seen.add(x)
                    flat.append(x)
        if flat != names:
            names = flat
            self.input.set_companies(names)  # 整理後の姿を画面にも反映する
        if self.provider is None:
            self.warn_no_keys()
            return
        new = [n for n in names
               if not (self.cfg.output.dir / f"{naming.safe_filename(n)}.png").exists()]
        detail = (f"新規 {len(new)}社を取得します(SerpAPI {len(new)}検索、"
                  f"remove.bg 最大 {len(new)}クレジットを消費)。\n"
                  if new else "")
        if not messagebox.askyesno(
                "ロゴを取得",
                f"{len(names)}社を処理します。\n{detail}"
                "取得済みの企業はキャッシュを使うためAPIを消費しません。よろしいですか?"):
            return

        (ROOT / "companies.txt").write_text("\n".join(names) + "\n", encoding="utf-8")
        self._build_cards()
        self.set_all_busy(True)
        self.set_status("取得を開始しました…")
        threading.Thread(target=self._fetch_worker, args=(names,), daemon=True).start()

    def _fetch_worker(self, names: list[str]) -> None:
        results: list[LogoResult] = []
        credit_error = False
        for name in names:
            if credit_error:
                r = LogoResult(company=name, error="未処理(クレジット不足で中断)")
            else:
                try:
                    r = pipeline.process_company(name, self.cfg, self.provider)
                except bg_remove.RemoveBgCreditError as e:
                    credit_error = True
                    r = LogoResult(company=name, error=str(e))
                except Exception as e:
                    r = LogoResult(company=name, error=net.scrub(
                        str(e), self.cfg.search.api_key, self.cfg.removebg.api_key))
            results.append(r)
            self.queue.put((self._card_of(name), r))
        self.queue.put((DONE, results))

    def _card_of(self, company: str) -> Card | None:
        return next((c for c in self.cards if c.company == company), None)

    # --- やり直し(1社) ---

    def run_retry(self, card: Card) -> None:
        def work() -> None:
            try:
                # 前回使った候補の次(meta の used_rank+1)から取り直す
                result = pipeline.process_company(
                    card.company, self.cfg, self.provider, retry=True)
            except Exception as e:
                result = LogoResult(company=card.company, error=net.scrub(
                    str(e), self.cfg.search.api_key, self.cfg.removebg.api_key))
            self.queue.put((card, result))
            self.queue.put((DONE, None))

        threading.Thread(target=work, daemon=True).start()

    # --- 進捗の反映 ---

    def _poll(self) -> None:
        try:
            while True:
                card, payload = self.queue.get_nowait()
                if card is QUOTA:
                    self.quota_label.configure(text=payload)
                    continue
                if card is DONE:
                    self._on_done(payload)
                    continue
                if card is not None:
                    card.refresh()
                result = payload
                if isinstance(result, LogoResult):
                    if result.ok:
                        note = "キャッシュ" if result.from_cache else result.source_domain
                        self.set_status(f"「{result.company}」OK({note})")
                    else:
                        self.set_status(f"「{result.company}」失敗: {result.error}")
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _on_done(self, results: list[LogoResult] | None) -> None:
        self.set_all_busy(False)
        self._regen_pptx()
        if results:
            report_mod.write_csv(results, self.cfg.output.dir / "report.csv")
            report_mod.write_failed(results, self.cfg.output.dir / "failed.txt")
            ok = sum(1 for r in results if r.ok)
            failed = [r.company for r in results if not r.ok]
            text = f"完了: {ok}/{len(results)}社成功。"
            if failed:
                text += " 失敗: " + "、".join(failed) + "(やり直しで再取得できます)"
            else:
                text += " サムネイルをクリックしてコピーしてください。"
            self.set_status(text)
        self._update_fetch_bar()
        self._refresh_quota()

    def _refresh_quota(self) -> None:
        """API残数(SerpAPI 検索・remove.bg クレジット)を裏で取得して表示する。

        どちらの照会も無料で、検索数・クレジットを消費しない。
        """
        has_removebg = bool(self.cfg.removebg.api_key.strip())
        if self.provider is None and not has_removebg:
            return

        def work() -> None:
            parts = []
            if self.provider is not None and hasattr(self.provider, "quota"):
                try:
                    left, total = self.provider.quota()
                    parts.append(f"SerpAPI 残り検索: {left}/{total}")
                except Exception:
                    pass  # 取得できないときは静かに非表示にする
            if has_removebg:
                try:
                    free_calls, credits = bg_remove.quota(self.cfg.removebg.api_key)
                    text = f"remove.bg 残り無料: {free_calls}回"
                    if credits:
                        text += f" +クレジット{credits:g}"
                    parts.append(text)
                except Exception:
                    pass
            self.queue.put((QUOTA, "  |  ".join(parts)))

        threading.Thread(target=work, daemon=True).start()

    # --- 共通部品 ---

    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def set_all_busy(self, busy: bool) -> None:
        self.busy = busy
        self.fetch_btn.state(["disabled"] if busy else ["!disabled"])
        self.input.set_enabled(not busy)
        for c in self.cards:
            c.set_busy(busy)
        if not busy:
            self._update_fetch_bar()

    def warn_no_keys(self) -> None:
        messagebox.showwarning(
            "APIキー未設定",
            "config.toml にAPIキーが設定されていないため、取得できません。\n"
            "config.example.toml を config.toml にコピーしてキーを記入してください。")

    def _regen_pptx(self) -> None:
        entries = [(c.company, c.png_path) for c in self.cards if c.png_path.exists()]
        if entries:
            try:
                pptx_export.export(entries, self.cfg.output.dir / "logos.pptx")
            except Exception:
                pass  # 開いたまま等で保存できなくても、コピー機能には影響しない

    def open_pptx(self) -> None:
        path = self.cfg.output.dir / "logos.pptx"
        if path.exists():
            os.startfile(path)  # noqa: S606
        else:
            messagebox.showinfo("pptx なし", "logos.pptx がまだ作られていません。")

    def open_folder(self) -> None:
        os.startfile(self.cfg.output.dir)  # noqa: S606


def _apply_window_icon(root: tk.Tk) -> None:
    """ウィンドウ左上とタスクバーのアイコンを本アプリのものにする。

    Tk は既定で自前のアイコンを使うため、exe に埋め込んだアイコンとは別に
    ウィンドウへ明示的に設定する必要がある。
    """
    try:
        from ctypes import windll
        # これを設定しないと、タスクバーで python.exe のアイコンにまとめられてしまう
        windll.shell32.SetCurrentProcessExplicitAppUserModelID(paths.APP_ID)
    except Exception:
        pass
    ico = paths.resource_path("logo_tool.ico")
    if ico.exists():
        try:
            root.iconbitmap(default=str(ico))
        except tk.TclError:
            pass


def run() -> None:
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)  # 高DPIでぼやけないように
    except Exception:
        pass
    root = tk.Tk()
    _apply_window_icon(root)
    theme.apply(root)
    App(root)
    root.mainloop()


if __name__ == "__main__":
    run()
