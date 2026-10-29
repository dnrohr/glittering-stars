# -*- mode: python ; coding: utf-8 -*-
"""Reproducible one-folder Windows desktop build.

Build with: powershell -ExecutionPolicy Bypass -File packaging/build_windows.ps1
The Qt hook's bundled ICU data is omitted because Qt resolves the Windows 10+
system ICU implementation. The PyInstaller-collected ICU 78 build is ABI
incompatible with the Qt binaries in the tested Windows environment.
"""
from pathlib import Path
from glob import glob
from PyInstaller.utils.hooks import collect_submodules, collect_all

ROOT = Path(SPECPATH).resolve().parent
datas = [
    (str(ROOT / "settings.json"), "."),
    (str(ROOT / "packaging" / "THIRD_PARTY_NOTICES.txt"), "."),
]
datas += [(path, "licenses") for path in glob(str(ROOT / "packaging" / "licenses" / "*"))]
rtmidi_datas, rtmidi_binaries, rtmidi_hidden = collect_all("rtmidi")
mido_hidden = collect_submodules("mido.backends")
datas += rtmidi_datas
binaries = rtmidi_binaries
hiddenimports = list(set(rtmidi_hidden + mido_hidden))

a = Analysis(
    [str(ROOT / "desktop.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

# Qt's Qt6Core imports the Windows system ICU. The ICU 78 DLLs found through
# unrelated packages can shadow it and fail at launch (`ucnv_open_78`).
ICU_DLLS = {"icuuc.dll", "icudt78.dll"}
a.binaries = [entry for entry in a.binaries
              if Path(entry[0].replace("\\", "/")).name.casefold() not in ICU_DLLS]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GlitteringStars",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="GlitteringStars",
)
