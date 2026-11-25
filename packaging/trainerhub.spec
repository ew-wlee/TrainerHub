# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe: one self-contained TrainerHub.exe."""

from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
SRC = ROOT / "src"
RES = SRC / "trainerhub" / "resources"

datas = [
    (str(SRC / "trainerhub" / "ui" / "qss" / "app.qss"), "trainerhub/ui/qss"),
    (str(SRC / "trainerhub" / "i18n" / "zh_CN.json"), "trainerhub/i18n"),
    (str(SRC / "trainerhub" / "i18n" / "en_US.json"), "trainerhub/i18n"),
    (str(RES / "app_icon.svg"), "trainerhub/resources"),
    (str(RES / "app_mark.svg"), "trainerhub/resources"),
]

excludes = [
    "tkinter",
    "unittest",
    "pydoc_data",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtQuick",
    "PySide6.QtQml",
    "PySide6.Qt3DCore",
    "PySide6.QtMultimedia",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtPositioning",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtDesigner",
    "PySide6.QtPdf",
    "PySide6.QtSql",
]

a = Analysis(
    [str(SRC / "trainerhub" / "__main__.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=["PySide6.QtSvg"],
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="TrainerHub",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    icon=str(RES / "app_icon.ico") if (RES / "app_icon.ico").exists() else None,
)
