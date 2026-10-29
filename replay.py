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
import re
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

# 录制器对齐的最低 ydf-browser 版本（0.1.42：workflow_panel/workflow_result 新契约）
MIN_YDF_BROWSER_VERSION = "0.1.42"
# install_runtime 成功后写入的版本标记文件名
_VERSION_MARKER = ".ydf-browser-version"

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


def _frozen_resources_dir() -> Path | None:
    """打包态（PyInstaller）下应用 Resources 目录；非打包返回 None。

    布局差异（从可执行文件向上查找，命中含内置资源的目录）：
      macOS .app: <App>/Contents/Resources/app/YonDiFRecorder/<exe>
                  → Resources 目录里有 chromium/ 与 ydfbrowser-cli/
      Windows   : <dist>/app/YonDiFRecorder/<exe> 或 <dist>/<exe>
                  → 资源就在 exe 同级
    因此按「向上逐级找含 chromium/ 或 ydfbrowser-cli/ 的目录」判定，避免
    写死层级算错（曾把 app/YonDiFRecorder 误当 Resources，导致回放器找不到）。
    """
    if not getattr(sys, "frozen", False):
        return None
    exe = Path(sys.executable).resolve()
    cur = exe.parent
    for _ in range(6):
        if (cur / "ydfbrowser-cli").is_dir() or (cur / "chromium").is_dir():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    # 回退：按已知布局猜测
    for cand in (
        exe.parent.parent.parent,           # macOS .app: Contents/Resources
        exe.parent.parent / "Resources",
        exe.parent / "Resources",
        exe.parent,
    ):
        if cand.is_dir():
            return cand
    return exe.parent


def _runtime_base_candidates(root: Path | None = None) -> list[Path]:
    """运行时 venv / 版本标记的可能位置（打包态优先查应用 Resources）。"""
    bases: list[Path] = []
    res = _frozen_resources_dir()
    if res is not None:
        bases.append(res / "ydf-browser-runtime")
        bases.append(res / "app" / "ydf-browser-runtime")
    bases.append((root or RECORD_ROOT).resolve() / ".ydf-browser-runtime")
    return bases


def find_source_dir(root: Path | None = None) -> Path | None:
    """定位 ydf-browser 源码目录（子模块 → 项目内 → 兄弟目录 → 打包内 vendor）。"""
    base = (root or RECORD_ROOT).resolve()
    candidates = [
        base / "vendor" / "ydf-browser",
        base / "ydf-browser",
        base.parent / "ydf-browser",
    ]
    res = _frozen_resources_dir()
    if res is not None:
        candidates.append(res / "vendor" / "ydf-browser")
        candidates.append(res / "app" / "vendor" / "ydf-browser")
    for cand in candidates:
        if (cand / RUNTIME_MARKER / "__init__.py").is_file() and (cand / "pyproject.toml").is_file():
            return cand
    return None


def runtime_python(root: Path | None = None) -> Path | None:
    """运行时 venv 的 python 解释器路径（跨平台：bin/ 或 Scripts/）。"""
    for base in _runtime_base_candidates(root):
        for rel in ("bin/python", "bin/python3", "Scripts/python.exe"):
            p = base / rel
            if p.is_file():
                return p
    return None


def bundled_cli_command() -> Path | None:
    """打包态内置的 ydfbrowser-cli 独立可执行文件（PyInstaller 子产物）。"""
    res = _frozen_resources_dir()
    if res is None:
        return None
    for name in ("ydfbrowser-cli/ydfbrowser-cli", "ydfbrowser-cli/ydfbrowser-cli.exe"):
        p = res / name
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


def _version_tuple(value: str) -> tuple[int, ...]:
    """把版本字符串解析为可比较的整数元组（忽略无数字段，如 -beta 后缀）。"""
    parts: list[int] = []
    for piece in re.split(r"[.\-_+]", value.strip()):
        digits = ""
        for ch in piece:
            if ch.isdigit():
                digits += ch
            elif digits:
                break
        if digits:
            parts.append(int(digits))
    return tuple(parts) if parts else (0,)


def query_runtime_version(root: Path | None = None) -> str | None:
    """查询内嵌运行时的 ydf-browser 版本。

    优先读 install_runtime 写入的版本标记文件（零开销），
    否则派生子进程 ``import ydf_browser`` 查询。
    """
    base = None  # 版本标记按候选位置查找
    marker = None
    for cand_base in _runtime_base_candidates(root):
        cand_marker = cand_base / _VERSION_MARKER
        if cand_marker.is_file():
            marker = cand_marker
            break
    if marker is not None:
        text = marker.read_text(encoding="utf-8").strip()
        if text:
            return text
    py = runtime_python(root)
    if py is None:
        return None
    try:
        proc = subprocess.run(
            [str(py), "-c", "import ydf_browser; print(ydf_browser.__version__)"],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    out = (proc.stdout or "").strip()
    return out.splitlines()[-1].strip() if out else None


_version_check_cache: dict[str, str | None] = {}


def check_runtime_version(root: Path | None = None) -> str | None:
    """校验内嵌运行时版本是否满足最低要求。

    返回给用户的警告消息；达标 / 未使用内嵌运行时返回 None。
    结果按 root 缓存（同一进程内不重复派生子进程）。
    """
    key = str((root or RECORD_ROOT).resolve())
    if key in _version_check_cache:
        return _version_check_cache[key]
    has_marker = any(
        (base / _VERSION_MARKER).is_file()
        for base in _runtime_base_candidates(root)
    )
    if runtime_python(root) is None and not has_marker:
        # 未使用内嵌运行时（PATH / env / interpreter 形态），不校验
        _version_check_cache[key] = None
        return None
    ver = query_runtime_version(root)
    if ver is None:
        msg = (
            "无法确定 ydf-browser 运行时版本（运行时可能过旧或损坏），"
            "建议重新执行 `ydf-recorder install-ydf-browser`"
        )
    elif _version_tuple(ver) < _version_tuple(MIN_YDF_BROWSER_VERSION):
        msg = (
            f"ydf-browser 运行时版本 {ver} 低于最低要求 {MIN_YDF_BROWSER_VERSION}，"
            "DSL 契约可能不匹配，建议重新执行 `ydf-recorder install-ydf-browser`"
        )
    else:
        msg = None
    _version_check_cache[key] = msg
    return msg


def build_run_args(options: ReplayOptions) -> list[str]:
    """组装 ``ydf-browser run`` 的参数列表（不含可执行文件本身）。

    ydf-browser ≥0.1.42 的 CLI 以 ``--dsl`` 传入 DSL 文件（无位置参数）。
    """
    args = ["run", "--dsl", str(options.yaml_path), "--env", options.env_name]
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
    args = ["validate", "--dsl", str(options.yaml_path), "--env", options.env_name]
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

    # 1.5 打包态内置的 ydfbrowser-cli 独立可执行文件（桌面应用零依赖形态）
    bundled = bundled_cli_command()
    if bundled:
        return DiscoveryResult(command=[str(bundled)], source="bundled-cli")

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
    # 写入版本标记，供 replay/validate 前的快速版本校验使用（避免每次派生子进程）
    try:
        vproc = subprocess.run(
            [str(_venv_python_for(target)), "-c", "import ydf_browser; print(ydf_browser.__version__)"],
            capture_output=True, text=True, timeout=120,
        )
        if vproc.returncode == 0 and vproc.stdout.strip():
            ver = vproc.stdout.strip().splitlines()[-1].strip()
            (target / _VERSION_MARKER).write_text(ver + "\n", encoding="utf-8")
    except (OSError, subprocess.SubprocessError):
        pass  # 标记写失败不影响运行时就绪；版本校验会退化为子进程查询
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


def _replay_workdir() -> Path:
    """回放子进程的工作目录（ydf-browser 会在 ./reports/ 下写报告）。

    桌面应用从 Finder 启动时 cwd 可能是 ``/`` 或只读目录，导致报告写失败。
    统一落到 ``~/.ydf-recorder/replay/``，保证可写且集中。
    """
    base = Path.home() / ".ydf-recorder" / "replay"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError:
        return Path.home()
    return base


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
    proc = subprocess.Popen(
        argv,
        stdout=subprocess.PIPE,
        stderr=None,
        text=True,
        bufsize=1,
        cwd=str(_replay_workdir()),
    )
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


def resolve_config_path(explicit: str | None = None) -> Path | None:
    """解析回放配置文件：显式参数 → 用户配置（YDF_RECORDER_CONFIG）→ 内置配置。"""
    if explicit:
        return Path(explicit)
    env_cfg = os.environ.get("YDF_RECORDER_CONFIG", "").strip()
    if env_cfg and Path(env_cfg).is_file():
        return Path(env_cfg)
    res = _frozen_resources_dir()
    if res is not None:
        bundled = res / "config" / "env.yaml"
        if bundled.is_file():
            return bundled
    return default_config_path()


def _options_from_args(args, yaml_path: str) -> ReplayOptions:
    config = resolve_config_path(getattr(args, "config", None))
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


def _clear_stale_profile_lock() -> None:
    """清理 ydf-browser 持久化 profile 的残留 Singleton 锁。

    回放中途崩溃/被强杀后，``~/.ydf-browser/browser-profile/default/`` 里会
    留下 SingletonLock 等符号链接，导致下次启动 Chromium 直接失败
    （Failed to create a ProcessSingleton）。这里只在锁指向的进程已不存在时
    清理，避免误删正在运行的浏览器的锁。
    """
    import errno

    profile = Path.home() / ".ydf-browser" / "browser-profile" / "default"
    lock = profile / "SingletonLock"
    if not lock.is_symlink() and not lock.exists():
        return
    alive = False
    try:
        target = os.readlink(lock)  # 形如 "hostname-12345"
        pid_text = target.rsplit("-", 1)[-1]
        pid = int(pid_text)
        os.kill(pid, 0)
        alive = True
    except (OSError, ValueError, AttributeError) as exc:
        if isinstance(exc, OSError) and exc.errno == errno.EPERM:
            alive = True  # 进程存在但无权限探测 → 视为运行中
    if alive:
        return
    removed = []
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        p = profile / name
        try:
            if p.is_symlink() or p.exists():
                p.unlink()
                removed.append(name)
        except OSError:
            pass
    if removed:
        print(
            f"[ydf-recorder] 已清理残留浏览器锁: {'/'.join(removed)}",
            file=sys.stderr,
        )


def handle_replay(args) -> int:
    yaml_path = args.yaml
    if not Path(yaml_path).is_file():
        print(f"[ydf-recorder] error: YAML 文件不存在: {yaml_path}", file=sys.stderr)
        return 1
    _clear_stale_profile_lock()
    version_warn = check_runtime_version()
    if version_warn:
        print(f"[ydf-recorder] warn: {version_warn}", file=sys.stderr)
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
    version_warn = check_runtime_version()
    if version_warn:
        print(f"[ydf-recorder] warn: {version_warn}", file=sys.stderr)
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
