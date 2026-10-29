# -*- mode: python ; coding: utf-8 -*-
"""ydf-browser 回放 CLI 的 PyInstaller spec（桌面应用内嵌回放器）。

用法（在仓库根执行，或由 desktop/build_app.sh 调用）:
    pyinstaller desktop/ydfbrowser-cli.spec --noconfirm --distpath dist/pyi --workpath dist/_work

产物: dist/ydfbrowser-cli/ydfbrowser-cli（onedir），由 build_app.sh 拷贝到
.app/Contents/Resources/ydfbrowser-cli/，ydf_recorder.replay 打包态发现后
以子进程方式调用（discover_command → bundled-cli）。

要点:
  - collect_all("ydf_browser") 打包 ydf-browser 全量（含模板/契约资源）。
  - collect_all("playwright") 打包 node driver（回放要开浏览器）。
  - 构建环境已 --no-deps 安装 vendor/ydf-browser，playwright 与内嵌
    Chromium（chromium-1248）对齐，不再重复下载浏览器。
"""

import os

from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

yb_datas, yb_binaries, yb_hidden = collect_all("ydf_browser")
pw_datas, pw_binaries, pw_hidden = collect_all("playwright")

datas = list(yb_datas) + list(pw_datas)
binaries = list(yb_binaries) + list(pw_binaries)
hiddenimports = ["ydf_browser", "ydf_browser.cli"] + list(yb_hidden) + list(pw_hidden)

a = Analysis(
    [os.path.join(SPECPATH, "ydfbrowser_entry.py")],
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
    name="ydfbrowser-cli",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
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
    name="ydfbrowser-cli",
)
