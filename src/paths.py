"""実行形態(通常の Python / PyInstaller の exe)によらず、
config.toml や output/ が置かれる「アプリのルート」を返す。"""

from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        # PyInstaller でビルドされた exe。exe の隣を作業フォルダとする。
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_path(name: str) -> Path:
    """同梱リソース(アイコン等)のパス。exe 化後は展開先から探す。"""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parent.parent / "tools"
    return base / name


APP_ID = "LogoTool.CompanyLogoFetcher"  # タスクバーで固有アイコンを出すための識別子
