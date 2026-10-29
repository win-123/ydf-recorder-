# -*- mode: python ; coding: utf-8 -*-
"""ydf-recorder 桌面应用 PyInstaller spec（自包含，双击即用）。

用法（在仓库根执行，或由 desktop/build_app.sh / build_windows.bat 调用）:
    pyinstaller desktop/ydf-recorder.spec --noconfirm --distpath dist/pyi --workpath dist/_work

要点:
  - collect_all("playwright") 打包 playwright 的 node driver 与 package 包
    （recorder 的 CDP 注入/事件采集全依赖它，漏掉会启动即崩）。
  - config/env.example.yaml 打包进 bundle，首次启动复制到 ~/.ydf-recorder/。
  - onedir 模式（COLLECT），由外层 .app/.exe 结构承载双击体验。
"""

import os

from PyInstaller.utils.hooks import collect_all

# SPECPATH 由 PyInstaller 注入 = 本 spec 文件所在目录（desktop/）
ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

pw_datas, pw_binaries, pw_hidden = collect_all("playwright")

datas = list(pw_datas) + [
    (os.path.join(ROOT, "config", "env.example.yaml"), os.path.join("config")),
]
binaries = list(pw_binaries)
hiddenimports = [
    "ydf_recorder",
    "ydf_recorder.cli",
    "ydf_recorder.cdp",
    "ydf_recorder.inject",
    "ydf_recorder.replay",
    "ydf_recorder.auth",
    "ydf_recorder.menu_resolver",
] + list(pw_hidden)

a = Analysis(
    [os.path.join(SPECPATH, "entry.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "setuptools", "pip", "wheel"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="YonDiFRecorder",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # 保留控制台以便查看录制进度与报错（.app 外壳不影响双击体验）
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
    name="YonDiFRecorder",
)
