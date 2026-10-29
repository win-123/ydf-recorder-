"""PyInstaller 打包入口（桌面应用）。

macOS 上真正的首次配置向导在 ``desktop/launcher.sh``（原生对话框）；
Windows / Linux 没有 bash 启动器，所以这里提供一个跨平台的兜底：

- 打包后（frozen）且找不到配置时，写出配置模板到
  ``~/.ydf-recorder/env.yaml``，用系统默认编辑器打开，提示填好后重新启动。
- 非打包运行（源码/dev/测试）不触发，行为与 ``cli.main`` 完全一致。
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

CONFIG_TEMPLATE = """\
# YonDiF Recorder 配置文件（首次自动生成）
# 请把下面 5 个尖括号占位符替换成真实值后保存，再重新启动程序。
# 想重新生成模板：直接删除本文件后再次启动。
environments:
  ydf:
    base_url: "http://<你的服务器地址:端口>"
    username: "<登录用户名>"
    password: "<登录密码>"
    tenant: "<租户编码，如 ppksggwz>"
    default_org: "<默认组织编码，如 2661013488172269586>"
    fiscal_year: ""          # 业务年度，可留空
"""


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _exe_dir() -> Path:
    return Path(sys.executable).resolve().parent


def _setup_bundled_browser() -> None:
    """把内置 Chromium 目录告诉 Playwright（Windows/Linux 分发形态用）。"""
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        return
    base = _exe_dir()
    for cand in (
        base / "chromium",  # Windows: chromium 放在 exe 旁边
        base.parent / "Resources" / "chromium",
        base / "Resources" / "chromium",
        base.parent.parent / "chromium",  # macOS .app: Contents/Resources/chromium
    ):
        if cand.is_dir():
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(cand)
            return



def _open_with_default_editor(path: Path) -> None:
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-t", str(path)])  # noqa: S603,S607
        else:
            subprocess.Popen(["xdg-open", str(path)])  # noqa: S603,S607
    except Exception:  # pragma: no cover - 打不开编辑器不影响提示
        pass


def _bootstrap_config_on_first_run() -> None:
    """打包后首次运行：生成配置模板并提示用户填写。"""
    if not _is_frozen():
        return  # 源码运行不干预
    if os.environ.get("YDF_RECORDER_CONFIG"):
        return  # 启动器已指定配置

    cfg = Path.home() / ".ydf-recorder" / "env.yaml"
    if cfg.exists():
        os.environ["YDF_RECORDER_CONFIG"] = str(cfg)
        return

    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(CONFIG_TEMPLATE, encoding="utf-8")
    try:
        cfg.chmod(0o600)
    except OSError:
        pass

    print("=" * 68)
    print("首次运行：已生成配置文件模板")
    print(f"   {cfg}")
    print()
    print("请填写 base_url / username / password / tenant / default_org 后")
    print("重新启动本程序（文件已用默认编辑器打开）。")
    print("=" * 68)
    _open_with_default_editor(cfg)
    raise SystemExit(3)


def _default_args_for_double_click(argv: list[str]) -> list[str]:
    """双击 .exe（无任何参数）时补上默认参数，做到“双击即录”。"""
    if not _is_frozen() or len(argv) > 1:
        return []
    if sys.platform != "win32":
        return []  # macOS/Linux 由启动器脚本传参
    out_dir = Path.home() / "Downloads" / "ydf-recordings"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    extra = ["--env", "ydf", "--output", str(out_dir / f"suite_{ts}.yaml")]

    try:
        menu = input("要自动打开的菜单路径（用 >> 分隔，可留空直接回车）：").strip()
    except (EOFError, KeyboardInterrupt):
        menu = ""
    if menu:
        extra += ["--menu-path", menu]
    return extra


def main() -> int:
    _setup_bundled_browser()
    _bootstrap_config_on_first_run()
    extra = _default_args_for_double_click(list(sys.argv))
    if extra:
        sys.argv = [sys.argv[0], *extra]
    from ydf_recorder.cli import main as cli_main

    return cli_main()


if __name__ == "__main__":
    sys.exit(main())
