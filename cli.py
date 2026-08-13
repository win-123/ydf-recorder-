"""ydf-recorder CLI — 录制浏览器操作并生成 ydf-browser DSL YAML。

独立的 CLI 入口（与 ydf-browser 解耦）。产出的 YAML 包含 DSL 必填上下文
（``suite.tenant`` / ``default_org``、``case.user``），``menu_path`` 通过反查
service_tree 得到中文菜单路径。

用法:
  # 自动登录 + 自动打开菜单后录制
  ydf-recorder --env ydf --menu-path "项目管理>>项目库>>项目建议" --output suite.yaml

  # 自动登录但不打开菜单（手动导航）
  ydf-recorder --env ydf --output suite.yaml

  # 跳过自动登录（手动登录）
  ydf-recorder --env ydf --no-login --output suite.yaml

  # 从已有事件文件转换
  ydf-recorder --from-events events.json --output suite.yaml
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from ._version import __version__
from .cdp import RecorderRuntime
from .config import RecorderEnv, load_recorder_env
from .converter import build_dsl_document, dsl_to_yaml, load_events_from_json, load_events_from_jsonl
from .models import RecordedEvent, RecordingSession


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ydf-recorder")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command")

    # ── bump 子命令 ──
    bump_parser = subparsers.add_parser(
        "bump", help="设置/升级版本号，生成 tar.gz 发布包",
        description=(
            "设置或升级版本号，自动更新 _version.py 并构建 .tar.gz 发布包。\n"
            "\n"
            "示例:\n"
            "  ydf-recorder bump 1.2.3          # 直接指定版本号，生成 tar.gz\n"
            "  ydf-recorder bump patch          # 0.1.0 → 0.1.1\n"
            "  ydf-recorder bump minor          # 0.1.0 → 0.2.0\n"
            "  ydf-recorder bump major          # 0.1.0 → 1.0.0\n"
            "  ydf-recorder bump 1.2.3 --no-build   # 只改版本号，不构建\n"
            "  ydf-recorder bump patch --no-build   # 只改版本号，不构建"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    bump_parser.add_argument(
        "version",
        help=(
            "版本号：可直接指定（如 1.2.3），"
            "或用 patch/minor/major 自动递增"
        ),
    )
    bump_parser.add_argument(
        "--no-build", dest="no_build", action="store_true", default=False,
        help="不构建 .tar.gz 发布包",
    )
    bump_parser.add_argument(
        "--no-install", dest="no_install", action="store_true", default=False,
        help="不执行安装（默认使用 uv pip install 或 pip install）",
    )

    # ── record 子命令（默认行为，向后兼容） ──
    record_parser = subparsers.add_parser(
        "record", help="录制浏览器操作并生成 DSL YAML",
        description="录制浏览器操作并生成 ydf-browser DSL YAML",
    )
    _add_record_args(record_parser)

    # ── 无子命令时，顶层参数也支持录制（向后兼容） ──
    _add_record_args(parser)

    return parser


def _add_record_args(parser: argparse.ArgumentParser) -> None:
    """为 parser 添加录制相关的参数。"""
    parser.add_argument("--env", default="ydf", help="环境名称（对应 config/env.yaml 中的 key）")
    parser.add_argument("--config", help="配置文件路径")
    parser.add_argument("--output", default=None, help="输出 YAML 文件路径（默认: <suite_code>.yaml）")
    parser.add_argument(
        "--from-events", dest="from_events", default=None, metavar="EVENTS_FILE",
        help="从已有事件文件（JSON/JSONL）转换，不启动浏览器",
    )
    parser.add_argument("--suite-code", default="recorded_suite", help="测试集代码")
    parser.add_argument("--suite-name", default="录制测试集", help="测试集名称")
    parser.add_argument("--tenant", default="", help="租户名称（默认取 env.tenant）")
    parser.add_argument(
        "--default-org", dest="default_org", default="",
        help="默认组织编码（默认取 env.default_org）",
    )
    parser.add_argument(
        "--fiscal-year", dest="fiscal_year", default="",
        help="业务年度（默认取 env.fiscal_year，如 2027）",
    )
    parser.add_argument(
        "--user", dest="user", default="",
        help="用例用户别名（默认取 env.default_user / '默认用户'）",
    )
    parser.add_argument(
        "--menu-path", dest="menu_path", default="",
        metavar="MENU_PATH",
        help="录制前自动打开的菜单路径（如 '项目管理>>项目库>>项目建议'），"
             "用 >> 分隔。不指定则不自动打开菜单",
    )
    parser.add_argument(
        "--no-login", dest="no_login", action="store_true", default=False,
        help="跳过自动登录，手动在浏览器中登录",
    )
    parser.add_argument(
        "--headed", action="store_true", default=True,
        help="显示浏览器窗口（录制时默认开启）",
    )
    parser.add_argument(
        "--abstract-values", dest="abstract_values", action="store_true", default=False,
        help="自动将硬编码值替换为 {{random.*}} 变量",
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "bump":
        return _cmd_bump(args)

    # record 子命令或无子命令（向后兼容）
    try:
        return _cmd_record(args)
    except Exception as exc:
        error_message = str(exc)
        _print_human_error(error_message)
        _print_json({"success": False, "error": error_message})
        return 1


def console_main() -> None:
    raise SystemExit(main())


# ── 版本管理 ──────────────────────────────────────────────

_VERSION_FILE = Path(__file__).resolve().parent / "_version.py"


def _detect_uv() -> str | None:
    """检测 uv 是否可用，返回 uv 可执行路径或 None。"""
    import shutil
    # 优先检查 UV 环境变量（uv venv 激活时会设置）
    uv_env = os.environ.get("UV")
    if uv_env and shutil.which(uv_env):
        return uv_env
    return shutil.which("uv")


def _pip_install_editable(project_root: Path) -> subprocess.CompletedProcess:
    """以可编辑模式安装项目，自动兼容 uv / pip。"""
    import subprocess
    uv = _detect_uv()
    if uv:
        _log_progress(f"bump: uv pip install -e {project_root}")
        return subprocess.run(
            [uv, "pip", "install", "-e", str(project_root)],
            capture_output=True, text=True,
        )
    # 回退到传统 pip
    _log_progress(f"bump: pip install -e {project_root}")
    return subprocess.run(
        [sys.executable, "-m", "pip", "install", "-e", str(project_root)],
        capture_output=True, text=True,
    )


def _build_sdist(project_root: Path) -> tuple[subprocess.CompletedProcess, Path]:
    """在临时副本中构建 .tar.gz 发布包，保护源文件不被构建过程删除。

    由于 pyproject.toml 中 ``package-dir`` 将 ``.`` 映射为包目录，
    直接在源目录上运行 ``uv build`` 或 ``python -m build`` 可能导致
    构建后端清理源文件。因此在临时目录中复制源码后构建，
    构建完成后将 ``.tar.gz`` 复制回源目录的 ``dist/``。

    Returns:
        (构建结果, 临时构建目录路径)
    """
    import shutil
    import subprocess
    import tempfile

    # 需要复制到临时目录的文件模式
    COPY_GLOBS = ["*.py", "*.toml", "*.cfg", "*.md", "*.txt", "*.ini"]
    COPY_DIRS = ["config", "ydf_recorder.egg-info"]

    # 创建临时目录
    tmp_root = Path(tempfile.mkdtemp(prefix="ydf-recorder-build-"))
    _log_progress(f"bump: 构建临时目录 → {tmp_root}")

    try:
        # 复制源文件
        for glob in COPY_GLOBS:
            for src in project_root.glob(glob):
                if src.is_file():
                    shutil.copy2(src, tmp_root / src.name)
        # 复制子目录
        for dir_name in COPY_DIRS:
            src_dir = project_root / dir_name
            if src_dir.is_dir():
                shutil.copytree(src_dir, tmp_root / dir_name, dirs_exist_ok=True)

        # 在临时目录中构建
        uv = _detect_uv()
        if uv:
            _log_progress("bump: uv build --sdist …")
            result = subprocess.run(
                [uv, "build", "--sdist"],
                cwd=str(tmp_root),
                capture_output=True, text=True,
            )
        else:
            _log_progress("bump: python -m build --sdist …")
            result = subprocess.run(
                [sys.executable, "-m", "build", "--sdist"],
                cwd=str(tmp_root),
                capture_output=True, text=True,
            )

        if result.returncode == 0:
            # 将 .tar.gz 从临时目录的 dist/ 复制回源目录的 dist/
            tmp_dist = tmp_root / "dist"
            orig_dist = project_root / "dist"
            orig_dist.mkdir(parents=True, exist_ok=True)
            if tmp_dist.is_dir():
                for tarball in tmp_dist.glob("*.tar.gz"):
                    shutil.copy2(tarball, orig_dist / tarball.name)
                    _log_progress(f"bump: 发布包已复制 → {orig_dist / tarball.name}")

        return result, tmp_root

    except Exception:
        # 出错时也返回临时目录路径，方便调用方清理
        return result if 'result' in locals() else None, tmp_root


def _cmd_bump(args: argparse.Namespace) -> int:
    """设置/升级版本号，并构建 .tar.gz 发布包。"""
    import re
    import subprocess

    current = __version__
    raw = args.version.strip()

    # ── 计算新版本号 ──
    if raw in ("patch", "minor", "major"):
        parts = current.split(".")
        if len(parts) != 3:
            _print_human_error(f"当前版本号格式异常: {current}（期望 x.y.z）")
            return 1
        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
        if raw == "major":
            major += 1
            minor = 0
            patch = 0
        elif raw == "minor":
            minor += 1
            patch = 0
        else:
            patch += 1
        new_version = f"{major}.{minor}.{patch}"
    else:
        # 直接指定版本号，校验格式
        if not re.match(r"^\d+\.\d+\.\d+$", raw):
            _print_human_error(
                f"版本号格式错误: {raw}\n"
                "应为 x.y.z 格式（如 1.2.3），或使用 patch/minor/major 自动递增"
            )
            return 1
        new_version = raw

    # ── 写入 _version.py ──
    new_content = (
        '"""recorder 版本号（独立于 ydf-browser）。\n\n'
        '单独成文件以避免 ``__init__`` ↔ ``cli`` 之间的循环导入。\n'
        '"""\n\n'
        f'__version__ = "{new_version}"\n'
    )
    _VERSION_FILE.write_text(new_content, encoding="utf-8")
    _log_progress(f"bump: {current} → {new_version}")

    # ── 重新安装（确保版本号生效） ──
    if not args.no_install:
        project_root = _VERSION_FILE.parent
        result = _pip_install_editable(project_root)
        if result.returncode != 0:
            _print_human_error(result.stderr or result.stdout)
            return 1
        _log_progress(f"bump: 安装完成，版本 {new_version} 已生效")
    else:
        _log_progress("bump: --no-install，跳过重新安装")

    # ── 构建 .tar.gz 发布包 ──
    tarball_path = None
    if not args.no_build:
        project_root = _VERSION_FILE.parent
        _log_progress("bump: 构建 .tar.gz 发布包 …")

        # 只清理源目录下的旧产物（build/ 和 dist/），不删除源文件
        build_dir = project_root / "build"
        dist_dir = project_root / "dist"
        if build_dir.exists():
            import shutil
            shutil.rmtree(build_dir)
        if dist_dir.exists():
            import shutil
            shutil.rmtree(dist_dir)

        # 在临时副本中构建，保护源文件
        result, tmp_root = _build_sdist(project_root)
        if result is None or result.returncode != 0:
            _print_human_error(f"构建失败:\n{result.stderr if result else '未知错误'}")
            # 清理临时目录
            import shutil as _shutil
            _shutil.rmtree(tmp_root, ignore_errors=True)
            return 1

        # 清理临时目录
        import shutil as _shutil
        _shutil.rmtree(tmp_root, ignore_errors=True)
        _log_progress(f"bump: 临时目录已清理")

        # 查找生成的 .tar.gz
        if dist_dir.exists():
            tarballs = sorted(dist_dir.glob("*.tar.gz"))
            if tarballs:
                tarball_path = tarballs[-1]
                _log_progress(f"bump: 发布包已生成 → {tarball_path}")
            else:
                _print_human_error("构建完成但未找到 .tar.gz 文件")
                return 1
        else:
            _print_human_error("构建完成但 dist/ 目录不存在")
            return 1
    else:
        _log_progress("bump: --no-build，跳过构建")

    _print_json({
        "success": True,
        "old_version": current,
        "new_version": new_version,
        "tarball": str(tarball_path) if tarball_path else None,
    })
    return 0


# ── 上下文解析 ────────────────────────────────────────────

def _resolve_context(args: argparse.Namespace, env: RecorderEnv) -> tuple[str, str, str]:
    """解析 tenant/default_org/user：CLI 参数优先，env 兜底；缺必填项则报错。

    Returns:
        (tenant, default_org, user)
    """
    tenant = (args.tenant or env.tenant).strip()
    default_org = (args.default_org or env.default_org).strip()
    user = (args.user or env.default_user).strip() or "默认用户"
    _require_context(tenant, "tenant", "--tenant", "env.tenant")
    _require_context(default_org, "default_org", "--default-org", "env.default_org")
    return tenant, default_org, user


def _require_context(value: str, name: str, *sources: str) -> None:
    if not str(value or "").strip():
        raise ValueError(f"{name} 必填：请通过 {' / '.join(sources)} 提供")


def _extract_service_code_from_raw(raw_events: list[dict]) -> str | None:
    """从原始事件（dict）中提取首个 navigation 的 serviceCode。"""
    for raw in raw_events:
        if raw.get("type") != "navigation":
            continue
        url = (raw.get("context") or {}).get("url") or (raw.get("target") or {}).get("value") or ""
        match = re.search(r"/service/([^/?#]+)", url)
        if match:
            return match.group(1)
    return None


# ── 命令实现 ──────────────────────────────────────────────

def _cmd_record(args: argparse.Namespace) -> int:
    """录制浏览器操作并生成 DSL YAML。"""
    output_path = args.output or f"{args.suite_code}.yaml"

    if args.from_events:
        return _convert_from_events(args, output_path)

    return _record_from_browser(args, output_path)


def _convert_from_events(args: argparse.Namespace, output_path: str) -> int:
    events_file = args.from_events
    if events_file.endswith(".jsonl"):
        events = load_events_from_jsonl(events_file)
    else:
        events = load_events_from_json(events_file)

    _log_progress(f"record: 从 {events_file} 加载了 {len(events)} 个事件")

    # env 仅用于上下文兜底，缺失不致命
    try:
        env = load_recorder_env(args.config, args.env)
    except Exception:
        env = RecorderEnv(env_name=args.env, base_url="")
    tenant, default_org, user = _resolve_context(args, env)
    fiscal_year = (args.fiscal_year or env.fiscal_year).strip()

    session = RecordingSession(
        suite_code=args.suite_code,
        suite_name=args.suite_name,
        tenant=tenant,
        default_org=default_org,
        fiscal_year=fiscal_year,
        user=user,
        events=events,
    )
    document = build_dsl_document(session, abstract=args.abstract_values)
    yaml_content = dsl_to_yaml(document)

    Path(output_path).write_text(yaml_content, encoding="utf-8")
    _print_json({
        "success": True,
        "output": str(Path(output_path).resolve()),
        "suite_code": args.suite_code,
        "steps": len(document.cases[0].steps) if document.cases else 0,
        "events": len(events),
    })
    _log_progress(f"record: DSL 已写入 {output_path}")
    return 0


def _record_from_browser(args: argparse.Namespace, output_path: str) -> int:
    env = load_recorder_env(args.config, args.env)
    tenant, default_org, user = _resolve_context(args, env)

    # CLI 参数覆盖 env 配置
    fiscal_year = (args.fiscal_year or env.fiscal_year).strip()
    if fiscal_year:
        env.fiscal_year = fiscal_year
    menu_path_arg = (args.menu_path or "").strip()
    auto_login = not args.no_login

    if auto_login and env.username and env.password:
        _log_progress(f"record: 启动浏览器，目标环境 {env.base_url}（自动登录 user={env.username}）")
    else:
        _log_progress(f"record: 启动浏览器，目标环境 {env.base_url}（手动登录）")
    if menu_path_arg:
        _log_progress(f"record: 录制前自动打开菜单: {menu_path_arg}")
    _log_progress("record: 操作页面，完成后点击 'Stop Recording' 按钮")

    recorder = RecorderRuntime(
        env,
        menu_path=menu_path_arg,
        auto_login=auto_login,
    )
    menu_path: str | None = menu_path_arg or None
    raw_events: list[dict] = []
    try:
        recorder.start()
        raw_events = recorder.wait_for_stop()
        # 反查中文菜单路径（需 context 存活，必须在 stop 前）
        # 如果用户未指定 --menu-path，从录制事件中提取 serviceCode 反查
        if not menu_path:
            service_code = _extract_service_code_from_raw(raw_events)
            if service_code:
                resolved = recorder.resolve_menu_path(service_code)
                if resolved:
                    menu_path = resolved
                    _log_progress(f"record: menu_path 反查成功 {service_code} → {menu_path}")
                else:
                    menu_path = service_code  # 占位：至少保留信息，过 DSL 校验
                    _log_progress(
                        f"record: ⚠️ menu_path 反查失败（serviceCode={service_code}），"
                        f"已用 serviceCode 占位，请手动改为中文菜单路径（如 预算管理>>项目库>>...）"
                    )
    finally:
        recorder.stop()

    events = [RecordedEvent.from_dict(e) for e in raw_events]

    page_title = args.suite_name
    for e in events:
        if e.context.title and e.context.title != page_title:
            page_title = e.context.title
            break

    session = RecordingSession(
        suite_code=args.suite_code,
        suite_name=page_title,
        tenant=tenant,
        default_org=default_org,
        fiscal_year=fiscal_year,
        user=user,
        events=events,
        menu_path=menu_path,
        page_url=events[0].context.url if events else "",
        page_title=page_title,
    )

    document = build_dsl_document(session, abstract=args.abstract_values)
    yaml_content = dsl_to_yaml(document)

    Path(output_path).write_text(yaml_content, encoding="utf-8")
    # dump 完整事件，便于事后诊断与重转（--from-events）
    events_dump = Path(output_path).with_suffix(".events.json")
    events_dump.write_text(json.dumps(raw_events, ensure_ascii=False, indent=2), encoding="utf-8")
    _print_json({
        "success": True,
        "output": str(Path(output_path).resolve()),
        "events_dump": str(events_dump.resolve()),
        "suite_code": args.suite_code,
        "suite_name": page_title,
        "menu_path": menu_path,
        "steps": len(document.cases[0].steps) if document.cases else 0,
        "events": len(events),
    })
    _log_progress(
        f"record: {len(events)} 个事件 → "
        f"{len(document.cases[0].steps) if document.cases else 0} 个步骤 → {output_path}"
    )
    return 0


# ── 工具函数 ──────────────────────────────────────────────

def _log_progress(message: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[ydf-recorder] time={now} {message}", file=sys.stderr, flush=True)


def _print_human_error(message: str) -> None:
    print("[ydf-recorder] error:", file=sys.stderr)
    print(message, file=sys.stderr, flush=True)


def _print_json(payload: dict) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    console_main()
