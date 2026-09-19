# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification: builds dist/Omniconv/ containing

    Omniconv.exe   windowed GUI (no console)
    omniconv.exe   console CLI

Run from the repository root:  pyinstaller packaging/windows/omniconv.spec
The converters are imported dynamically by name, so every backend module
is listed as a hidden import; PyInstaller would otherwise leave them out.
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parent.parent
sys.path.insert(0, str(ROOT))
ICON = str(ROOT / "omniconv" / "data" / "omniconv.ico") if sys.platform == "win32" else None

hidden = collect_submodules("omniconv")
for optional in ("PIL", "pillow_heif", "pymupdf", "fitz", "pypdf", "reportlab", "markdown", "openpyxl", "tomli_w", "yaml", "fontTools", "brotli", "msgpack", "cairosvg"):
    try:
        __import__(optional)
    except Exception:
        continue
    hidden += collect_submodules(optional)

datas = [(str(ROOT / "omniconv" / "data"), "omniconv/data")]
for optional in ("pymupdf", "pillow_heif", "reportlab"):
    try:
        __import__(optional)
        datas += collect_data_files(optional)
    except Exception:
        pass

# Nothing in Omniconv needs the scientific stack; excluding it keeps a build
# small even on a machine where these packages happen to be installed.
excludes = ["gi", "tkinter", "PyQt5", "PyQt6", "IPython", "matplotlib", "numpy", "scipy", "pandas", "sympy", "test", "unittest"]

a_gui = Analysis([str(ROOT / "packaging" / "windows" / "entry_gui.py")], pathex=[str(ROOT)], datas=datas, hiddenimports=hidden, excludes=excludes, noarchive=False)
# The console binary keeps Qt too: "omniconv gui" must work from a terminal,
# and both executables share one _internal folder, so the files are not duplicated.
a_cli = Analysis([str(ROOT / "packaging" / "windows" / "entry_cli.py")], pathex=[str(ROOT)], datas=datas, hiddenimports=hidden, excludes=excludes, noarchive=False)

pyz_gui = PYZ(a_gui.pure)
pyz_cli = PYZ(a_cli.pure)

exe_gui = EXE(pyz_gui, a_gui.scripts, [], exclude_binaries=True, name="Omniconv", console=False, icon=ICON, upx=False)
exe_cli = EXE(pyz_cli, a_cli.scripts, [], exclude_binaries=True, name="omniconv", console=True, icon=ICON, upx=False)

coll = COLLECT(exe_gui, exe_cli, a_gui.binaries, a_gui.datas, a_cli.binaries, a_cli.datas, name="Omniconv", upx=False)
