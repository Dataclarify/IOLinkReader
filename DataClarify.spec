# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for DataClarify.io Downtime Tracker
# Build: pyinstaller DataClarify.spec --clean
#   or:  build.bat  (also creates the distributable ZIP)

from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []

# Streamlit — must collect everything (static assets, templates, etc.)
tmp = collect_all("streamlit")
datas += tmp[0]; binaries += tmp[1]; hiddenimports += tmp[2]

# pymodbus
tmp = collect_all("pymodbus")
datas += tmp[0]; binaries += tmp[1]; hiddenimports += tmp[2]

# altair — Streamlit's built-in charting library
tmp = collect_all("altair")
datas += tmp[0]; binaries += tmp[1]; hiddenimports += tmp[2]

# Application source files — included as data so Streamlit can exec app.py
# and so local imports (db, poller, etc.) resolve at runtime
datas += [
    ("app.py",       "."),
    ("config.py",    "."),
    ("db.py",        "."),
    ("demo.py",      "."),
    ("poller.py",    "."),
    ("shared_state.py", "."),
    ("diagnose.py",  "."),
]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + [
        "streamlit.runtime.scriptrunner.magic_funcs",
        "streamlit.runtime.caching.storage.dummy_cache_storage",
        "pymodbus.client",
        "pymodbus.client.tcp",
        "pandas",
        "numpy",
        "sqlalchemy",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DataClarify",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="DataClarify",
)
