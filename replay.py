"""内嵌 ydf-browser 运行时：发现、安装、校验与回放。

设计原则（依赖隔离）：
  ydf-browser 把 playwright 钉死在 ==1.61.0，而 recorder 只约束 >=1.52。
  为避免同 venv 依赖互相污染，本模块**不 import ydf-browser**，而是：
    1. 从 ydf-browser 源码目录（git submodule ``vendor/ydf-browser``，或退化到
       兄弟目录 ``../ydf-browser``）构建独立的运行时 venv
       （``.ydf-browser-runtime/``）；
    2. 以子进程方式调用 ``<venv python> -m ydf_browser.cli``；
    3. 解析其 stdout 末行的 JSON 摘要（run/validate 均以 _print_json 收尾）。

ydf-browser 来源目录的查找顺序（找到第一个含 ``ydf_browser/__init__.py`` 且有
``pyproject.toml`` 的目录即命中）：
    <recorder>/vendor/ydf-browser   ← git submodule（推荐，正式形态）
    <recorder>/ydf-browser          ← 主项目内直接存放
    <recorder>/../ydf-browser       ← 兄弟目录（当前开发布局，向后兼容）

运行时可执行文件的发现顺序：
    1. 环境变量 ``YDF_BROWSER_BIN``（显式覆盖；值为 python 解释器时自动补 -m）
    2. 运行时 venv ``.ydf-browser-runtime/bin/python``
    3. PATH 上的 ``ydf-browser`` 控制台脚本
    4. 当前解释器可 import 的 ``ydf_browser``（同 venv 安装形态）
"""

from __future__ import annotations

import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# 本文件位于仓库根（package-dir 把根目录映射为 ydf_recorder 包）
RECORD_ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = RECORD_ROOT / ".ydf-browser-runtime"
RUNTIME_MARKER = "ydf_browser"  # 源码目录内的包名

# ── 数据结构 ────────────────────────────────────────────────


@dataclass
class DiscoveryResult:
    """运行时可执行文件的发现结果。"""

    command: list[str] | None = None
    source: str = ""  # 发现来源说明（env/venv/path/interpreter）
    hint: str = ""  # 未发现时的操作指引

    @property
    def found(self) -> bool:
        return bool(self.command)


@dataclass
class ReplayOptions:
    """replay/validate 的公共参数（与 ydf-browser CLI 对齐）。"""

    yaml_path: str = ""
    env_name: str = "ydf"
    config: str | None = None
    headless: bool = False
    force_login: bool = False
    case_codes: list[str] = field(default_factory=list)
    case_globs: list[str] = field(default_factory=list)
    grep: str | None = None
    tags: list[str] = field(default_factory=list)
    vars_files: list[str] = field(default_factory=list)
    no_persistent_profile: bool = False


# ── 纯函数（便于测试）─────────────────────────────────────


def find_source_dir(root: Path | None = None) -> Path | None:
    """定位 ydf-browser 源码目录（子模块 → 项目内 → 兄弟目录）。"""
    base = (root or RECORD_ROOT).resolve()
    candidates = [
        base / "vendor" / "ydf-browser",
        base / "ydf-browser",
        base.parent / "ydf-browser",
    ]
    for cand in candidates:
        if (cand / RUNTIME_MARKER / "__init__.py").is_file() and (cand / "pyproject.toml").is_file():
            return cand
    return None


def runtime_python(root: Path | None = None) -> Path | None:
    """运行时 venv 的 python 解释器路径（跨平台：bin/ 或 Scripts/）。"""
    base = (root or RECORD_ROOT).resolve() / ".ydf-browser-runtime"
    for rel in ("bin/python", "bin/python3", "Scripts/python.exe"):
        p = base / rel
        if p.is_file():
            return p
    return None


def default_config_path(root: Path | None = None) -> Path | None:
    """recorder 自带 config/env.yaml（与 ydf-browser schema 兼容）存在则返回。"""
    p = (root or RECORD_ROOT).resolve() / "config" / "env.yaml"
    return p if p.is_file() else None


def _venv_python_for(target_dir: Path) -> Path:
    suffix = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    return target_dir / suffix


def build_install_steps(source_dir: Path, target_dir: Path, with_browsers: bool = False) -> list[list[str]]:
    """生成安装运行时 venv 的命令序列（纯函数，便于测试与展示）。"""
    steps = [
        [sys.executable, "-m", "venv", str(target_dir)],
    ]
    venv_py = _venv_python_for(target_dir)
    steps.append([str(venv_py), "-m", "pip", "install", str(source_dir)])
    if with_browsers:
        steps.append([str(venv_py), "-m", "playwright", "install", "chromium"])
    steps.append([str(venv_py), "-c", "import ydf_browser; print(ydf_browser.__version__)"])
    return steps


def _bin_command(bin_value: str) -> list[str]:
    """把 YDF_BROWSER_BIN 的值转成 argv。值为 python 解释器时补 -m ydf_browser.cli。"""
    parts = shlex.split(bin_value)
    if not parts:
        return []
    exe = Path(parts[0]).name.lower()
    if exe.startswith("python"):
        return parts + ["-m", RUNTIME_MARKER + ".cli"]
    return parts


def build_run_args(options: ReplayOptions) -> list[str]:
    """组装 ``ydf-browser run`` 的参数列表（不含可执行文件本身）。"""
    args = ["run", str(options.yaml_path), "--env", options.env_name]
    if options.config:
        args += ["--config", str(options.config)]
    if options.headless:
        args.append("--headless")
    if options.force_login:
        args.append("--force-login")
    for code in options.case_codes:
        args += ["--case", code]
    for glob in options.case_globs:
        args += ["--case-glob", glob]
    if options.grep:
        args += ["--grep", options.grep]
    for tag in options.tags:
        args += ["--tag", tag]
    for vf in options.vars_files:
        args += ["--vars-file", vf]
    if options.no_persistent_profile:
        args.append("--no-persistent-profile")
    return args


def build_validate_args(options: ReplayOptions) -> list[str]:
    """组装 ``ydf-browser validate`` 的参数列表（不开浏览器，纯 YAML 校验）。"""
    args = ["validate", str(options.yaml_path), "--env", options.env_name]
    if options.config:
        args += ["--config", str(options.config)]
    for code in options.case_codes:
        args += ["--case", code]
    for glob in options.case_globs:
        args += ["--case-glob", glob]
    if options.grep:
        args += ["--grep", options.grep]
    for tag in options.tags:
        args += ["--tag", tag]
    for vf in options.vars_files:
        args += ["--vars-file", vf]
    return args


def parse_summary_json(output: str) -> dict | None:
    """从命令 stdout 中提取最后一行合法的 JSON 对象（ydf-browser 的摘要）。"""
    for line in reversed(output.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(payload, dict):
            return payload
    return None


# ── 发现与安装（有副作用）─────────────────────────────────


def discover_command(
    root: Path | None = None,
    env: dict | None = None,
    which_fn=None,
    importable_fn=None,
) -> DiscoveryResult:
    """按优先级定位可执行 ydf-browser 的命令。所有外部依赖可注入以便测试。"""
    env = env if env is not None else dict(os.environ)
    which_fn = which_fn or shutil.which
    importable_fn = importable_fn or (lambda name: importlib.util.find_spec(name) is not None)

    # 1. 显式覆盖
    bin_value = env.get("YDF_BROWSER_BIN", "").strip()
    if bin_value:
        return DiscoveryResult(command=_bin_command(bin_value), source="env:YDF_BROWSER_BIN")

    # 2. 运行时 venv
    venv_py = runtime_python(root)
    if venv_py:
        return DiscoveryResult(command=[str(venv_py), "-m", RUNTIME_MARKER + ".cli"], source="runtime-venv")

    # 3. PATH 上的控制台脚本
    on_path = which_fn("ydf-browser")
    if on_path:
        return DiscoveryResult(command=[on_path], source="PATH")

    # 4. 当前解释器可直接 import（同 venv 安装）
    if importable_fn(RUNTIME_MARKER):
        return DiscoveryResult(command=[sys.executable, "-m", RUNTIME_MARKER + ".cli"], source="interpreter")

    # 未发现：给出与实际状态匹配的指引
    source_dir = find_source_dir(root)
    if source_dir:
        return DiscoveryResult(
            hint=f"已找到 ydf-browser 源码目录 {source_dir}，执行 `ydf-recorder install-ydf-browser` 构建运行时 venv 后重试",
        )
    return DiscoveryResult(
        hint=(
            "未找到 ydf-browser。先把它挂为子模块："
            "`git submodule add <ydf-browser-repo-url> vendor/ydf-browser`，"
            "再执行 `ydf-recorder install-ydf-browser`；"
            "或设置 YDF_BROWSER_BIN 指向已安装的 ydf-browser 可执行文件"
        ),
    )


def install_runtime(source_dir: Path | None = None, with_browsers: bool = False) -> int:
    """从源码目录构建运行时 venv。返回进程退出码。"""
    src = source_dir or find_source_dir()
    if not src:
        print("[ydf-recorder] error: 未找到 ydf-browser 源码目录（vendor/ydf-browser 或 ../ydf-browser）", file=sys.stderr)
        return 1
    target = RUNTIME_DIR
    steps = build_install_steps(src, target, with_browsers=with_browsers)
    for i, argv in enumerate(steps, 1):
        desc = " ".join(argv[1:3]) if i == 1 else argv[-1][:80]
        print(f"[ydf-recorder] install-ydf-browser [{i}/{len(steps)}] {desc}", file=sys.stderr, flush=True)
        try:
            proc = subprocess.run(argv)
        except FileNotFoundError as exc:
            print(f"[ydf-recorder] error: 命令无法执行: {exc}", file=sys.stderr)
            return 1
        if proc.returncode != 0:
            print(f"[ydf-recorder] error: 步骤失败（exit={proc.returncode}）: {' '.join(argv)}", file=sys.stderr)
            return proc.returncode
    print(f"[ydf-recorder] install-ydf-browser: 运行时就绪 → {target}", file=sys.stderr)
    return 0


# ── 执行（子进程封装）─────────────────────────────────────


def run_validate(options: ReplayOptions, summary_only: bool = False) -> tuple[int, dict | None]:
    """执行 ``ydf-browser validate``（纯 YAML 校验，不开浏览器）。返回 (exit_code, summary)。"""
    discovery = discover_command()
    if not discovery.found:
        print(f"[ydf-recorder] error: {discovery.hint}", file=sys.stderr)
        return 1, None
    argv = discovery.command + build_validate_args(options)
    proc = subprocess.run(argv, capture_output=True, text=True)
    summary = parse_summary_json(proc.stdout)
    if summary_only and summary is not None:
        print(json.dumps(summary, ensure_ascii=False))
    else:
        if proc.stdout:
            sys.stdout.write(proc.stdout)
        if proc.stderr:
            sys.stderr.write(proc.stderr)
    return proc.returncode, summary


def run_replay(options: ReplayOptions, summary_only: bool = False) -> tuple[int, dict | None]:
    """执行 ``ydf-browser run`` 真实回放。流式透传 stdout，末尾解析 JSON 摘要。

    返回 (exit_code, summary)。summary 形如
    ``{success, run_id, totals, report_file, html_report_file, first_failure?}``。
    """
    discovery = discover_command()
    if not discovery.found:
        print(f"[ydf-recorder] error: {discovery.hint}", file=sys.stderr)
        return 1, None
    argv = discovery.command + build_run_args(options)
    print(f"[ydf-recorder] replay: {' '.join(argv)}", file=sys.stderr, flush=True)

    collected: list[str] = []
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=None, text=True, bufsize=1)
    assert proc.stdout is not None
    for line in proc.stdout:
        collected.append(line)
        if not summary_only:
            sys.stdout.write(line)
            sys.stdout.flush()
    proc.stdout.close()
    code = proc.wait()
    summary = parse_summary_json("".join(collected))
    if summary is not None:
        print(json.dumps(summary, ensure_ascii=False))
    return code, summary


# ── CLI 处理器（由 cli.py 分发）───────────────────────────


def _options_from_args(args, yaml_path: str) -> ReplayOptions:
    config = getattr(args, "config", None) or default_config_path()
    return ReplayOptions(
        yaml_path=yaml_path,
        env_name=getattr(args, "env", "ydf"),
        config=config,
        headless=getattr(args, "headless", False),
        force_login=getattr(args, "force_login", False),
        case_codes=list(getattr(args, "case", None) or []),
        case_globs=list(getattr(args, "case_glob", None) or []),
        grep=getattr(args, "grep", None),
        tags=list(getattr(args, "tag", None) or []),
        vars_files=list(getattr(args, "vars_file", None) or []),
        no_persistent_profile=getattr(args, "no_persistent_profile", False),
    )


def handle_replay(args) -> int:
    yaml_path = args.yaml
    if not Path(yaml_path).is_file():
        print(f"[ydf-recorder] error: YAML 文件不存在: {yaml_path}", file=sys.stderr)
        return 1
    code, summary = run_replay(_options_from_args(args, yaml_path), summary_only=args.summary_only)
    if summary is None:
        print("[ydf-recorder] replay: 未解析到结果摘要（可能中途失败，见上方输出）", file=sys.stderr)
        return code or 1
    if summary.get("success"):
        totals = summary.get("totals") or {}
        print(
            f"[ydf-recorder] replay: 成功 "
            f"total={totals.get('total')} passed={totals.get('passed')} failed={totals.get('failed')}",
            file=sys.stderr,
        )
    else:
        failure = summary.get("first_failure") or {}
        print(
            f"[ydf-recorder] replay: 失败 case={failure.get('case_code')} "
            f"step={failure.get('step_index')} reason={failure.get('message')}",
            file=sys.stderr,
        )
    return code


def handle_validate(args) -> int:
    yaml_path = args.yaml
    if not Path(yaml_path).is_file():
        print(f"[ydf-recorder] error: YAML 文件不存在: {yaml_path}", file=sys.stderr)
        return 1
    code, summary = run_validate(_options_from_args(args, yaml_path), summary_only=args.summary_only)
    if summary is not None and summary.get("success"):
        totals = summary.get("totals") or {}
        print(
            f"[ydf-recorder] validate: 通过 files={totals.get('files')} cases={totals.get('cases')}",
            file=sys.stderr,
        )
    elif summary is None:
        print("[ydf-recorder] validate: 未解析到结果（YAML 可能有语法错误，见上方输出）", file=sys.stderr)
    return code


def handle_install(args) -> int:
    source = Path(args.source).resolve() if getattr(args, "source", None) else None
    if source is not None and not (source / RUNTIME_MARKER / "__init__.py").is_file():
        print(f"[ydf-recorder] error: --source 不是有效的 ydf-browser 源码目录: {source}", file=sys.stderr)
        return 1
    return install_runtime(source_dir=source, with_browsers=args.with_browsers)
