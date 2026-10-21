# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for SnapClick (standalone, single-file bundle).

Build (from the repo root):

    pyinstaller packaging/SnapClick.spec --noconfirm

Output: dist/SnapClick(.exe). The app stores its data in a
``snapclick-data/`` folder next to the executable, so the bundle is fully
portable — drop it in any folder and run.
"""
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent

block_cipher = None

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=[
        # platform backends are imported lazily inside factory functions
        "snapclick.core.platform.win32",
        "snapclick.core.platform.x11",
        "snapclick.core.platform._mss_screen",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "tkinter", "pydoc_data"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="SnapClick",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,           # GUI app: no console window on Windows
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
