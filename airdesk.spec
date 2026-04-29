# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for AirDesk.

Build with:
    source .venv312/bin/activate
    pyinstaller airdesk.spec --clean
"""

import os
import sys
from pathlib import Path

# Locate the mediapipe package so we can bundle its native libs.
import mediapipe
mediapipe_root = Path(mediapipe.__file__).parent

block_cipher = None

a = Analysis(
    ["airdesk/main.py"],
    pathex=["."],
    binaries=[],
    datas=[
        # Bundle the hand-landmarker model.
        ("airdesk/assets/hand_landmarker.task", "airdesk/assets"),
        # Bundle the full mediapipe package (native libs + data).
        (str(mediapipe_root), "mediapipe"),
    ],
    hiddenimports=[
        "mediapipe",
        "mediapipe.python",
        "mediapipe.python._framework_bindings",
        "mediapipe.tasks",
        "mediapipe.tasks.python",
        "mediapipe.tasks.python.vision",
        "cv2",
        "numpy",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "scipy",
        "pandas",
        "IPython",
        "jupyter",
        "notebook",
    ],
    noarchive=False,
    optimize=1,  # strip assert statements
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AirDesk",
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=False,
    console=False,   # No terminal window
    target_arch="arm64",  # Apple Silicon
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=True,
    upx=False,
    name="AirDesk",
)

app = BUNDLE(
    coll,
    name="AirDesk.app",
    icon=None,  # TODO: add an .icns icon file
    bundle_identifier="com.airdesk.app",
    info_plist={
        "CFBundleName": "AirDesk",
        "CFBundleDisplayName": "AirDesk",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
        "NSCameraUsageDescription": "AirDesk uses your camera to track hand gestures for cursor control.",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "13.0",
    },
)
