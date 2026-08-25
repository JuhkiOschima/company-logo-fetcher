# -*- mode: python ; coding: utf-8 -*-
# GUI(LogoTool.exe)と CLI(LogoToolCLI.exe)を1つのフォルダに同居させるビルド定義。
#   ビルド: .venv\Scripts\pyinstaller LogoTool.spec --noconfirm

from PyInstaller.utils.hooks import collect_data_files

# python-pptx は既定テンプレート(default.pptx)をパッケージ内データとして持つ
datas = collect_data_files("pptx")

common = dict(
    pathex=["src"],
    binaries=[],
    datas=datas + [("tools/logo_tool.ico", ".")],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=["pyinstaller", "pip", "setuptools"],
    noarchive=False,
)

a_gui = Analysis(["src/gui/app.py"], **common)
a_cli = Analysis(["src/main.py"], **common)

pyz_gui = PYZ(a_gui.pure)
pyz_cli = PYZ(a_cli.pure)

exe_gui = EXE(
    pyz_gui, a_gui.scripts, [],
    exclude_binaries=True,
    name="LogoTool",
    icon="tools/logo_tool.ico",
    console=False,
    disable_windowed_traceback=False,
)
exe_cli = EXE(
    pyz_cli, a_cli.scripts, [],
    exclude_binaries=True,
    name="LogoToolCLI",
    icon="tools/logo_tool.ico",
    console=True,
)

coll = COLLECT(
    exe_gui, a_gui.binaries, a_gui.datas,
    exe_cli, a_cli.binaries, a_cli.datas,
    name="LogoTool",
)
