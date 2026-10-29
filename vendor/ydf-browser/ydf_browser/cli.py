from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
import multiprocessing
import os
import platform
import queue
import re
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import uuid
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from . import __version__
from .binder import bind_manifest
from .auth import CasAuthenticator
from .captcha import ocr_install_permission
from .bpr_report import enrich_bpr_reports
from .session_reuse import SessionReuse, CookieBridge
from .browser_profile import clear_profile, profile_payload, resolve_profile_path
from .config import ConfigLoader, default_config_path
from .dsl import load_dsl_document_from_file
from .executor import WorkflowExecutor
from .menu_opening import MenuOpening
from .fiscal_year_context import FiscalYearContext
from .gateway import YondifGateway
from .models import ActionStep, DslTestCase, DslTestSuite, ExecutionReport, MenuTarget, StepResult
from .observation import (
    AI_OBSERVATION_CAPABILITIES,
    AVAILABLE_CAPABILITIES,
    CONTRACT_VERSION,
    DEFAULT_CASE_TIMEOUT_SECONDS,
    DEFAULT_MAX_NETWORK_BODY_BYTES,
    DEFAULT_MAX_NETWORK_CASE_BYTES,
    DEFAULT_RUN_TIMEOUT_SECONDS,
    DEFAULT_STEP_TIMEOUT_SECONDS,
    ObservationSession,
    atomic_write_json,
)
from .performance_xlsx import export_performance_xlsx
from .org_context import DefaultOrgContext
from .report_html import render_html_report
from .request_forwarding import RequestForwardRule, parse_request_forward_specs, request_forwarding_payload
from .runner import DSL_SUFFIXES, SuiteRunSpec, archive_diagnostic_files, discover_dsl_files, filter_cases, run_suite_specs
from .runtime import FixtureGateway, FixtureRuntime, PlaywrightRuntime, load_json_file
from .tenant_context import TenantContext, UserContextVerifier
from .template_parser import build_page_manifest
from .updater import UpdateManager, default_home, load_update_state, skill_compatibility
from .variables import load_variables_file, merge_variables, parse_cli_variables, variable_keys


class _RequestForwardAction(argparse.Action):
    def __init__(self, option_strings, dest, strip_prefix: bool = False, **kwargs) -> None:
        self.strip_prefix = strip_prefix
        super().__init__(option_strings, dest, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None) -> None:
        specs = list(getattr(namespace, self.dest, None) or [])
        specs.append((str(values), self.strip_prefix))
        setattr(namespace, self.dest, specs)


class _DslInputAction(argparse.Action):
    def __init__(self, option_strings, dest, input_kind: str, **kwargs) -> None:
        self.input_kind = input_kind
        super().__init__(option_strings, dest, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None) -> None:
        specs = list(getattr(namespace, self.dest, None) or [])
        value_list = values if isinstance(values, list) else [values]
        specs.append({"kind": self.input_kind, "values": [str(value) for value in value_list]})
        setattr(namespace, self.dest, specs)


class _ArgumentHelpFormatter(argparse.ArgumentDefaultsHelpFormatter):
    def _get_help_string(self, action: argparse.Action) -> str:
        help_text = action.help or ""
        if "%(default)" not in help_text and action.default not in (None, False, [], argparse.SUPPRESS):
            return f"{help_text} (默认: %(default)s)"
        return help_text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ydf-browser",
        description="面向 YonDiF 单据页的 YAML DSL 浏览器自动化 CLI。",
        formatter_class=_ArgumentHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}", help="显示版本号并退出")
    parser.add_argument("--install-ocr", action="store_true", help="需要识别验证码图片且缺依赖时，授权自动安装 OCR 并继续")
    subparsers = parser.add_subparsers(dest="command")

    completion_parser = subparsers.add_parser("completion", help="生成 Shell 命令行补全")
    completion_parser.add_argument("shell", choices=["zsh"], help="目标 Shell")

    login_parser = subparsers.add_parser(
        "login",
        help="登录配置的 YonDiF 环境并保存会话",
        description="登录配置的 YonDiF 环境，并将会话信息保存到本地文件。",
        formatter_class=_ArgumentHelpFormatter,
    )
    login_parser.add_argument("--env", default="ydf", metavar="NAME", help="环境名称")
    login_parser.add_argument("--config", metavar="PATH", help="环境配置文件路径")
    login_parser.add_argument("--output", default=".ydf-browser/session.json", metavar="PATH", help="会话文件输出路径")

    menu_parser = subparsers.add_parser(
        "menu",
        help="打开 YonDiF 菜单页面",
        description="解析并打开 YonDiF 菜单页面。",
        formatter_class=_ArgumentHelpFormatter,
    )
    menu_sub = menu_parser.add_subparsers(dest="menu_command", required=True)
    open_parser = menu_sub.add_parser(
        "open",
        help="打开指定菜单并保持可见浏览器会话",
        description="登录环境后打开指定的 YonDiF 菜单页面。",
        formatter_class=_ArgumentHelpFormatter,
    )
    open_parser.add_argument("menu_path", metavar="MENU_PATH", help="菜单完整路径，例如 应用>>单据>>列表")
    open_parser.add_argument("--env", default="ydf", metavar="NAME", help="环境名称")
    open_parser.add_argument("--config", metavar="PATH", help="环境配置文件路径")
    open_parser.add_argument("--default-org", metavar="ORG", help="登录后使用的默认组织标识")

    template_parser = subparsers.add_parser(
        "template",
        help="获取并解析 YonDiF 页面模板",
        description="获取 YonDiF 页面模板并输出解析后的页面 manifest。",
        formatter_class=_ArgumentHelpFormatter,
    )
    template_sub = template_parser.add_subparsers(dest="template_command", required=True)
    fetch_parser = template_sub.add_parser(
        "fetch",
        help="从文件或菜单获取页面模板",
        description="从本地 JSON 文件或 YonDiF 菜单获取页面模板。",
        formatter_class=_ArgumentHelpFormatter,
    )
    fetch_parser.add_argument("source", metavar="SOURCE", help="本地模板 JSON 文件路径或菜单完整路径")
    fetch_parser.add_argument("--env", default="ydf", metavar="NAME", help="环境名称")
    fetch_parser.add_argument("--config", metavar="PATH", help="环境配置文件路径")

    page_parser = subparsers.add_parser(
        "page",
        help="分析页面模板与运行时 DOM 绑定",
        description="分析 YonDiF 页面模板、运行时元素和字段绑定结果。",
        formatter_class=_ArgumentHelpFormatter,
    )
    page_sub = page_parser.add_subparsers(dest="page_command", required=True)
    analyze_parser = page_sub.add_parser(
        "analyze",
        help="分析指定菜单的模板和运行时绑定",
        description="分析真实菜单，或使用模板/运行时 fixture 分析页面绑定。",
        formatter_class=_ArgumentHelpFormatter,
    )
    analyze_parser.add_argument("menu_path", nargs="?", metavar="MENU_PATH", help="菜单完整路径")
    analyze_parser.add_argument("--service-code", metavar="CODE", help="直接指定菜单服务编码")
    analyze_parser.add_argument("--template-file", metavar="PATH", help="fixture 模式的模板 JSON 文件")
    analyze_parser.add_argument("--runtime-file", metavar="PATH", help="fixture 模式的运行时元素 JSON 文件")
    analyze_parser.add_argument("--env", default="ydf", metavar="NAME", help="环境名称")
    analyze_parser.add_argument("--config", metavar="PATH", help="环境配置文件路径")
    analyze_parser.add_argument("--headless", action="store_true", help="以无头浏览器运行真实页面分析")
    analyze_parser.add_argument("--default-org", metavar="ORG", help="登录后使用的默认组织标识")

    validate_parser = subparsers.add_parser(
        "validate",
        help="校验 YAML DSL 测试集",
        description="在执行前加载并校验 YAML DSL，输出匹配到的套件和用例。",
        formatter_class=_ArgumentHelpFormatter,
    )
    validate_parser.add_argument(
        "--dsl",
        action=_DslInputAction,
        dest="dsl_input_specs",
        input_kind="dsl",
        nargs="+",
        metavar="PATH",
        help="待校验的 DSL 文件、目录或通配符，可重复指定",
    )
    validate_parser.add_argument(
        "--dsl-list",
        action=_DslInputAction,
        dest="dsl_input_specs",
        input_kind="dsl_list",
        metavar="FILE",
        help="待校验的 UTF-8 DSL 清单，一行一个路径，忽略空行和 # 注释",
    )
    validate_parser.add_argument("--env", default="ydf", metavar="NAME", help="环境名称")
    validate_parser.add_argument("--config", metavar="PATH", help="环境配置文件路径")
    validate_parser.add_argument("--vars-file", action="append", default=[], metavar="PATH", help="外部变量 YAML 文件，可重复指定")
    validate_parser.add_argument(
        "--var",
        dest="variable_overrides",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="命令行变量覆盖环境和变量文件中的同名值，可重复指定",
    )
    validate_parser.add_argument("--case", dest="case_codes", action="append", default=[], metavar="CODE", help="只校验指定用例编码，可重复指定")
    validate_parser.add_argument("--case-glob", dest="case_globs", action="append", default=[], metavar="PATTERN", help="按通配符筛选用例编码，可重复指定")
    validate_parser.add_argument("--grep", metavar="TEXT", help="按用例名称或内容文本筛选")
    validate_parser.add_argument("--tag", dest="tags", action="append", default=[], metavar="TAG", help="只校验带指定标签的用例，可重复指定")
    validate_parser.add_argument(
        "--on-case-failure",
        choices=["continue", "stop_suite", "stop_run"],
        help="覆盖 suite 的失败策略：继续、停止当前 suite 或停止整个 run",
    )

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="检查本地 runtime、配置和转发目标",
        description="检查 Python、Playwright、环境配置和可选的本地请求转发目标。",
        formatter_class=_ArgumentHelpFormatter,
    )
    doctor_parser.add_argument("--env", default="ydf", metavar="NAME", help="环境名称")
    doctor_parser.add_argument("--config", metavar="PATH", help="环境配置文件路径")
    doctor_parser.add_argument("--skip-config", action="store_true", help="跳过环境配置检查，仅检查 CLI 和 Playwright")
    doctor_parser.add_argument("--forward-target", action="append", default=[], metavar="URL", help="检查请求转发目标的连通性，可重复指定")

    subparsers.add_parser(
        "install-skill",
        help="安装 agent skill",
        description="安装当前 ydf-browser 内置的 gov-ydfdev-browser agent skill。",
        formatter_class=_ArgumentHelpFormatter,
    )

    update_parser = subparsers.add_parser(
        "update",
        help="强制检查并升级或回滚已安装 runtime",
        description="默认强制检查并安装更高 stable runtime；--check 只检查不安装，rollback 回滚到上一版本。",
        formatter_class=_ArgumentHelpFormatter,
    )
    update_parser.add_argument("--check", action="store_true", help="强制前台检查稳定更新，不安装新版本")
    update_sub = update_parser.add_subparsers(dest="update_command")
    update_sub.add_parser(
        "rollback",
        help="回滚到上一保留 runtime 版本",
        description="将后续命令切换到上一保留 runtime 版本。",
        formatter_class=_ArgumentHelpFormatter,
    )
    update_parser.set_defaults(update_command="check")

    profile_parser = subparsers.add_parser(
        "profile",
        help="管理 ydf-browser 的持久化浏览器 profile",
        description="管理 ydf-browser 默认使用的持久化浏览器 profile。",
        formatter_class=_ArgumentHelpFormatter,
    )
    profile_sub = profile_parser.add_subparsers(dest="profile_command", required=True)
    profile_clear = profile_sub.add_parser(
        "clear",
        help="清空整个持久化 profile",
        description="清空整个持久化 profile（由 ydf-browser 管理）；不清除认证会话缓存。重新认证请使用 run --force-login。",
        formatter_class=_ArgumentHelpFormatter,
    )
    profile_clear.add_argument("--cookies", action="store_true", help="当前不支持局部清理 cookies；请直接清空整个 profile")
    profile_clear.add_argument("--cache", action="store_true", help="当前不支持局部清理 cache；请直接清空整个 profile")
    profile_clear.add_argument("--storage", action="store_true", help="当前不支持局部清理 storage；请直接清空整个 profile")

    run_parser = subparsers.add_parser(
        "run",
        help="运行 YAML DSL 测试集",
        description="运行 YAML DSL 测试集，支持真实 YonDiF 页面、fixture、筛选、并发和结构化报告。",
        formatter_class=_ArgumentHelpFormatter,
    )

    input_group = run_parser.add_argument_group("输入与 fixture")
    input_group.add_argument(
        "--dsl",
        action=_DslInputAction,
        dest="dsl_input_specs",
        input_kind="dsl",
        nargs="+",
        metavar="PATH",
        help="一个或多个 DSL 文件、目录或通配符，可与 --dsl-list 混用并按参数出现顺序展开",
    )
    input_group.add_argument(
        "--dsl-list",
        action=_DslInputAction,
        dest="dsl_input_specs",
        input_kind="dsl_list",
        metavar="FILE",
        help="UTF-8 DSL 清单，一行一个路径；忽略空行和 # 注释，清单严格串行且不能与并发大于 1 同用",
    )
    input_group.add_argument("--template-file", metavar="PATH", help="fixture 模式的模板 JSON 文件，必须与 --runtime-file 和 --menu-path 一起提供")
    input_group.add_argument("--runtime-file", metavar="PATH", help="fixture 模式的运行时元素 JSON 文件，必须与 --template-file 和 --menu-path 一起提供")
    input_group.add_argument("--menu-path", metavar="MENU_PATH", help="fixture 模式使用的菜单完整路径")

    environment_group = run_parser.add_argument_group("环境与浏览器")
    environment_group.add_argument("--env", default="ydf", metavar="NAME", help="环境名称")
    environment_group.add_argument("--config", metavar="PATH", help="环境配置文件路径")
    environment_group.add_argument("--headless", action="store_true", help="以无头浏览器运行，不显示窗口")
    environment_group.add_argument("--force-login", action="store_true", help="本次真实运行（含手工会话）首次使用每个账号时强制重新登录，后续用例仍可复用")
    environment_group.add_argument("--no-persistent-profile", action="store_true", help="使用临时浏览器但仍复用认证会话；并发运行真实 case 时必须启用")
    environment_group.add_argument(
        "--window-size",
        type=_parse_window_size,
        metavar="WIDTHxHEIGHT",
        help="设置启动时 headed 窗口或 headless viewport 尺寸；headless 默认 1440x900，显式值优先",
    )
    environment_group.add_argument("--default-org", metavar="ORG", help="为真实页面运行指定默认组织标识")
    environment_group.add_argument("--vars-file", action="append", default=[], metavar="PATH", help="外部变量 YAML 文件，可重复指定")
    environment_group.add_argument(
        "--var",
        dest="variable_overrides",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="命令行变量覆盖环境和变量文件中的同名值，可重复指定",
    )

    filter_group = run_parser.add_argument_group("用例筛选与执行")
    filter_group.add_argument(
        "--concurrency",
        type=int,
        default=1,
        metavar="N",
        help="一次最多并发执行的 case 数；默认 1，必须为正数，持久化 profile、--dsl-list 和 --ai-observe 受并发限制",
    )
    filter_group.add_argument("--case", dest="case_codes", action="append", default=[], metavar="CODE", help="只运行指定用例编码，可重复指定")
    filter_group.add_argument("--case-glob", dest="case_globs", action="append", default=[], metavar="PATTERN", help="按通配符筛选用例编码，可重复指定")
    filter_group.add_argument("--grep", metavar="TEXT", help="按用例名称或内容文本筛选")
    filter_group.add_argument("--tag", dest="tags", action="append", default=[], metavar="TAG", help="只运行带指定标签的用例，可重复指定")
    filter_group.add_argument("--pause-on-failure", action="store_true", help="在真实、有头、串行、交互式运行的首个可检查失败处保留页面，按 Enter 或关闭失败页面/浏览器后清理并生成失败报告")
    filter_group.add_argument(
        "--on-case-failure",
        choices=["continue", "stop_suite", "stop_run"],
        help="覆盖 suite 的失败策略：继续、停止当前 suite 或停止整个 run",
    )

    observation_group = run_parser.add_argument_group("性能与 AI 观察")
    observation_group.add_argument("--performance", action="store_true", help="采集性能数据并生成 performance.xlsx，启用 BPR 性能录制")
    observation_group.add_argument("--ai-observe", action="store_true", help="启用 AI 开发观察、事件流和脱敏诊断证据；只支持并发 1")
    observation_group.add_argument("--explore-reference", metavar="JSON", help="仅配合 --ai-observe：成功用例结束后探索已打开参照；JSON 支持 title/path/filter/tree_fieldid/offset/limit，不选择或保存")
    observation_group.add_argument("--step-timeout-seconds", type=int, metavar="SECONDS", help="AI 观察单步超时，默认 120 秒；必须为正数")
    observation_group.add_argument("--case-timeout-seconds", type=int, metavar="SECONDS", help="AI 观察单个 case 超时，默认 900 秒；必须不小于步骤超时")
    observation_group.add_argument("--run-timeout-seconds", type=int, metavar="SECONDS", help="AI 观察整次 run 超时，默认 1800 秒；必须不小于 case 超时")
    observation_group.add_argument("--max-network-body-bytes", type=int, metavar="BYTES", help="AI 观察单个网络正文最大采集字节数，默认 10 MiB")
    observation_group.add_argument("--max-network-case-bytes", type=int, metavar="BYTES", help="AI 观察单个 case 最大网络采集字节数，默认 200 MiB")

    forwarding_group = run_parser.add_argument_group("请求转发")
    forwarding_group.add_argument(
        "--forward",
        action=_RequestForwardAction,
        dest="request_forward_specs",
        default=[],
        strip_prefix=False,
        metavar="PATH/**=TARGET",
        help="将匹配路径转发到目标地址并保留原路径前缀，可重复指定",
    )
    forwarding_group.add_argument(
        "--forward-strip-prefix",
        action=_RequestForwardAction,
        dest="request_forward_specs",
        strip_prefix=True,
        metavar="PATH/**=TARGET",
        help="将匹配路径转发到目标地址并移除匹配前缀，可重复指定；fixture 模式不可用",
    )

    report_group = run_parser.add_argument_group("报告输出")
    report_group.add_argument("--report-dir", default="reports", metavar="PATH", help="未指定 --report-file 时的报告根目录")
    report_group.add_argument("--report-file", metavar="PATH", help="确定性 report.json 路径；events.jsonl 和其它产物写入同目录")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "completion":
        from .shell_completion import zsh_completion

        print(zsh_completion(parser), end="")
        return 0
    args._explicit_options = {
        token.split("=", 1)[0]
        for token in (sys.argv[1:] if argv is None else argv)
        if token.startswith("--")
    }
    if args.command is None:
        parser.print_help()
        return 0
    with ocr_install_permission(args.install_ocr):
        try:
            _reject_deprecated_cli_args(args)
            if args.command == "login":
                return _cmd_login(args)
            if args.command == "menu" and args.menu_command == "open":
                return _cmd_menu_open(args)
            if args.command == "template" and args.template_command == "fetch":
                return _cmd_template_fetch(args)
            if args.command == "page" and args.page_command == "analyze":
                return _cmd_page_analyze(args)
            if args.command == "validate":
                return _cmd_validate(args)
            if args.command == "doctor":
                return _cmd_doctor(args)
            if args.command == "install-skill":
                return _cmd_install_skill()
            if args.command == "update":
                return _cmd_update(args)
            if args.command == "profile" and args.profile_command == "clear":
                return _cmd_profile_clear(args)
            if args.command == "run":
                return _cmd_run(args)
            raise ValueError(f"未知命令: {args.command}")
        except Exception as exc:
            error_message = str(exc)
            _print_human_error(error_message)
            _print_json({"success": False, "error": error_message})
            return 1


def console_main() -> None:
    raise SystemExit(main())


def _cmd_login(args: argparse.Namespace) -> int:
    env = ConfigLoader(args.config).get_env(args.env)
    authenticator = CasAuthenticator(env)
    session = authenticator.login()
    output = authenticator.save_session(session, args.output)
    _print_json({"success": True, "session_file": str(output)})
    return 0


def _cmd_install_skill() -> int:
    script_name = "install-skill.ps1" if os.name == "nt" else "install-skill.sh"
    seen: set[Path] = set()
    for anchor in (Path(__file__).resolve(), Path(sys.executable).resolve()):
        for root in anchor.parents:
            if root in seen:
                continue
            seen.add(root)
            script = root / "scripts" / script_name
            if not (
                (root / "VERSION").is_file()
                and (root / "skills" / "gov-ydfdev-browser" / "SKILL.md").is_file()
                and script.is_file()
            ):
                continue
            command = (
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "all"]
                if os.name == "nt"
                else [str(script), "all"]
            )
            return subprocess.run(command, check=False).returncode
    raise ValueError("找不到当前 runtime 内置的 gov-ydfdev-browser skill")


def _cmd_menu_open(args: argparse.Namespace) -> int:
    env = ConfigLoader(args.config).get_env(args.env)
    session = _login_with_default_org_context(env, args.default_org, menu_path=args.menu_path)
    gateway = YondifGateway(env, session)
    runtime = PlaywrightRuntime(env, session, headless=False)
    runtime.start()
    try:
        menu_target = gateway.resolve_menu(args.menu_path)
        runtime.open_menu(menu_target)
    finally:
        runtime.stop()
    _print_json({"success": True, "menu_target": menu_target.to_dict()})
    return 0


def _cmd_template_fetch(args: argparse.Namespace) -> int:
    source_path = Path(args.source)
    if source_path.exists():
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    else:
        env = ConfigLoader(args.config).get_env(args.env)
        authenticator = CasAuthenticator(env)
        session = authenticator.login()
        gateway = YondifGateway(env, session)
        payload = gateway.fetch_template(gateway.resolve_menu(args.source))
    manifest = build_page_manifest(payload)
    _print_json({"success": True, "manifest": manifest.to_dict()})
    return 0


def _cmd_page_analyze(args: argparse.Namespace) -> int:
    if args.template_file or args.runtime_file:
        if not (args.template_file and args.runtime_file and args.menu_path):
            raise ValueError("fixture 分析模式必须同时提供 menu_path、--template-file 和 --runtime-file")
        payload = load_json_file(args.template_file)
        runtime_elements = load_json_file(args.runtime_file)
        gateway = FixtureGateway(payload, args.menu_path)
        runtime = FixtureRuntime(runtime_elements)
        executor = WorkflowExecutor(gateway=gateway, runtime=runtime)
        report = executor.run([{"action": "open_menu", "menu_path": args.menu_path}])
        _print_json({"success": report.success, "report": report.to_dict()})
        return 0 if report.success else 1

    env = ConfigLoader(args.config).get_env(args.env)
    session = _login_with_default_org_context(env, args.default_org, menu_path=args.menu_path)
    gateway = YondifGateway(env, session)
    runtime = PlaywrightRuntime(env, session, headless=args.headless)
    runtime.start()
    try:
        menu_target = _resolve_analysis_target(args, gateway)
        template_payload = gateway.fetch_template(menu_target)
        manifest = build_page_manifest(template_payload)
        runtime.open_menu(menu_target)
        runtime_elements = runtime.capture_runtime_elements(manifest)
        binding = bind_manifest(manifest, runtime_elements)
        page_state = runtime.capture_page_state()
    finally:
        runtime.stop()
    _print_json(
        {
            "success": True,
            "menu_target": menu_target.to_dict(),
            "manifest": manifest.to_dict(),
            "binding": binding.to_dict(),
            "page_state": page_state,
            "runtime_element_count": len(runtime_elements),
        }
    )
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    env = ConfigLoader(args.config).get_env(args.env)
    variables = _load_external_variables(args, env)
    dsl_paths = discover_dsl_files(_dsl_inputs(args))
    dsl_files: list[dict[str, Any]] = []
    case_total = 0
    for dsl_path in dsl_paths:
        document = load_dsl_document_from_file(dsl_path, variables=variables, validate_bpr_state=True)
        cases = filter_cases(
            document.cases,
            case_codes=args.case_codes,
            case_globs=args.case_globs,
            grep=args.grep,
            tags=args.tags,
        )
        if not cases:
            continue
        suite = document.suite
        if args.on_case_failure:
            suite = replace(suite, on_case_failure=args.on_case_failure)
        case_total += len(cases)
        dsl_files.append(
            {
                "path": str(dsl_path),
                "suite": suite.to_dict(),
                "case_count": len(cases),
                "cases": [{"code": case.code, "name": case.name, "tags": case.tags} for case in cases],
            }
        )
    if not dsl_files:
        raise ValueError("没有匹配到可校验用例")
    _print_json(
        {
            "success": True,
            "totals": {"files": len(dsl_files), "suites": len(dsl_files), "cases": case_total},
            "dsl_files": dsl_files,
        }
    )
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    skill_details = skill_compatibility(load_update_state(default_home()).get("min_skill_version"))
    skill_details.pop("ok", None)
    checks: dict[str, dict[str, Any]] = {
        "cli": _check(True, version=__version__),
        "python": _check(
            sys.version_info >= (3, 11),
            executable=sys.executable,
            version=platform.python_version(),
            required=">=3.11",
        ),
        "platform": _check(True, system=platform.system(), machine=platform.machine()),
        "playwright": _doctor_playwright_check(),
        "update": _doctor_update_check(),
        "skill_compatibility": _check(True, **skill_details),
    }
    if not args.skip_config:
        checks["config"] = _doctor_config_check(args.config, args.env)
    if args.forward_target:
        checks["forward_targets"] = _doctor_forward_targets(args.forward_target)
    success = _doctor_success(checks)
    _print_json(
        {
            "success": success,
            "version": __version__,
            "tool_version": __version__,
            "contract_version": CONTRACT_VERSION,
            "capabilities": {"available": list(AVAILABLE_CAPABILITIES)},
            "checks": checks,
        }
    )
    return 0 if success else 1


def _cmd_update(args: argparse.Namespace) -> int:
    manager = UpdateManager()
    if args.update_command == "rollback":
        if args.check:
            raise ValueError("update --check 不能与 rollback 同时使用")
        result = manager.rollback()
    else:
        result = manager.check(force=True, install=not args.check)
    _print_json({"success": result.get("result") not in {"failed", "locked"}, **result})
    return 0 if result.get("result") not in {"failed", "locked"} else 1


def _cmd_profile_clear(args: argparse.Namespace) -> int:
    if args.cookies or args.cache or args.storage:
        raise ValueError("profile clear 只支持清空整个持久化浏览器 profile，不支持只清 cookies、cache 或 storage")
    profile_path = clear_profile(resolve_profile_path())
    _print_json({"success": True, "profile": profile_payload("persistent", profile_path)})
    return 0


def _check(ok: bool, **details: Any) -> dict[str, Any]:
    return {"ok": bool(ok), **details}


def _doctor_update_check() -> dict[str, Any]:
    state = load_update_state(default_home())
    return _check(True, **(state or {"result": "not_checked"}))


def _doctor_playwright_check() -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return _check(False, error=f"{exc.__class__.__name__}: {exc}")
    try:
        with sync_playwright() as playwright:
            executable_path = playwright.chromium.executable_path
    except Exception as exc:
        return _check(False, error=f"{exc.__class__.__name__}: {exc}")
    return _check(True, chromium_executable=executable_path)


def _doctor_config_check(config_path: str | None, env_name: str) -> dict[str, Any]:
    resolved_path = Path(config_path).expanduser() if config_path is not None else default_config_path()
    local_path = resolved_path.with_name("env.local.yaml")
    try:
        loader = ConfigLoader(resolved_path)
        env = loader.get_env(env_name)
    except Exception as exc:
        return _check(
            False,
            path=str(resolved_path),
            local_path=str(local_path),
            local_exists=local_path.exists(),
            error=f"{exc.__class__.__name__}: {exc}",
        )
    return _check(
        True,
        path=str(loader.config_path),
        local_path=str(loader.local_config_path),
        local_exists=loader.local_config_path.exists(),
        env_name=env.env_name,
        base_url=env.base_url,
        users=sorted(env.users),
    )


def _doctor_forward_targets(targets: list[str]) -> dict[str, Any]:
    results = []
    for target in targets:
        started = time.monotonic()
        try:
            with urllib.request.urlopen(target, timeout=2) as response:
                status = getattr(response, "status", 0)
            results.append({"target": target, "ok": True, "status": status, "duration_ms": _elapsed_ms(started)})
        except urllib.error.HTTPError as exc:
            results.append({"target": target, "ok": True, "status": exc.code, "duration_ms": _elapsed_ms(started)})
        except Exception as exc:
            results.append(
                {
                    "target": target,
                    "ok": False,
                    "error": f"{exc.__class__.__name__}: {exc}",
                    "duration_ms": _elapsed_ms(started),
                }
            )
    return {"ok": all(item["ok"] for item in results), "targets": results}


def _doctor_success(checks: dict[str, Any]) -> bool:
    for check in checks.values():
        if isinstance(check, dict):
            if not bool(check.get("ok")):
                return False
            continue
        return False
    return True


def _cmd_run(args: argparse.Namespace) -> int:
    if not getattr(args, "dsl_input_specs", None):
        return _cmd_manual_browser_session(args)
    fixture_mode = bool(args.template_file and args.runtime_file)
    if fixture_mode and getattr(args, "force_login", False):
        raise ValueError("--force-login 仅支持带 DSL 的真实运行")
    _validate_failure_pause_args(args, fixture_mode=fixture_mode)
    try:
        ai_observation_config = _ai_observation_config(args)
    except ValueError as exc:
        return _cmd_run_ai_contract_failed(args, exc, operation_reason="ai_observe_invalid_limits")
    if bool(getattr(args, "ai_observe", False)) and args.concurrency > 1:
        return _cmd_run_ai_contract_failed(
            args,
            ValueError("AI 观察模式仅支持 --concurrency 1"),
            operation_reason="ai_observe_concurrency_unsupported",
        )
    if _dsl_list_inputs(args) and args.concurrency > 1:
        raise ValueError("--dsl-list 仅支持 --concurrency 1，以保证清单中的 DSL 严格串行执行")
    persistent_profile = _persistent_profile_enabled(args, fixture_mode)
    profile_path = resolve_profile_path() if persistent_profile else None
    if persistent_profile and args.concurrency > 1:
        raise ValueError("持久化浏览器 profile 模式不支持并发，请使用 --no-persistent-profile 或将 --concurrency 设为 1")
    request_forward_rules = parse_request_forward_specs(getattr(args, "request_forward_specs", []) or [])
    if fixture_mode and request_forward_rules:
        raise ValueError("请求转发仅支持真实浏览器 run，fixture 模式不能使用 --forward 或 --forward-strip-prefix")
    env = ConfigLoader(args.config).get_env(args.env) if (not fixture_mode or args.config) else None
    variables = _load_external_variables(args, env)
    run_id = _make_run_id()
    started_at = _now_iso()
    report_file, events_file = _prepare_report_paths(args, run_id)
    event_logger = _event_logger_for_run(args, events_file, run_id, ai_observation_config)
    event_logger.write(
        "run_started" if bool(getattr(args, "ai_observe", False)) else "run_start",
        {"run_id": run_id, "dsl_inputs": _dsl_inputs(args)},
    )
    if isinstance(event_logger, ObservationSession):
        event_logger.start_heartbeat()
    try:
        suite_specs = _load_suite_specs(args, variables=variables)
    except Exception as exc:
        return _cmd_run_validation_failed(
            args,
            exc,
            variables=variables,
            env=env,
            run_id=run_id,
            started_at=started_at,
            report_file=report_file,
            events_file=events_file,
            event_logger=event_logger,
            request_forward_rules=request_forward_rules,
        )
    try:
        if isinstance(event_logger, ObservationSession):
            result = _run_ai_suite_supervised(
                args,
                suite_specs,
                env=env,
                variables=variables,
                request_forward_rules=request_forward_rules,
                fixture_mode=fixture_mode,
                persistent_profile=persistent_profile,
                profile_path=profile_path,
                window_size=args.window_size,
                run_id=run_id,
                started_at=started_at,
                event_logger=event_logger,
            )
        else:
            result = _run_suite_specs_in_process(
                args,
                suite_specs,
                env=env,
                variables=variables,
                request_forward_rules=request_forward_rules,
                fixture_mode=fixture_mode,
                persistent_profile=persistent_profile,
                profile_path=profile_path,
                window_size=args.window_size,
                run_id=run_id,
                started_at=started_at,
                event_logger=event_logger,
                report_file=report_file,
            )
    except KeyboardInterrupt:
        if not args.pause_on_failure:
            raise
        _print_json({"success": False, "mode": "failure_pause", "exit_reason": "user_interrupt"})
        return 130
    result["report_file"] = str(report_file)
    result["events_file"] = str(events_file)
    html_report_file = report_file.with_suffix(".html")
    result["html_report_file"] = str(html_report_file)
    if args.performance:
        enrich_bpr_reports(result, env, report_file.parent, headless=args.headless)
        result["run"]["performance"] = _run_performance_payload(_performance_summary(result), _dict_profile_mode(result["run"].get("profile")))
        _write_performance_workbook(result, report_file.with_name("performance.xlsx"))
    archive_diagnostic_files(result, report_file.parent)
    if isinstance(event_logger, ObservationSession):
        event_logger.stop_heartbeat()
        for suite_report in result.get("suite_reports", []):
            suite = suite_report.get("suite") or {}
            event_logger.set_scope(suite_id=suite.get("code"), case_id=None, step_id=None, phase=None)
            observation = suite_report.get("observation") or {
                "outcome": "passed" if suite_report.get("success") else "blocked"
            }
            event_logger.write(
                "suite_completed" if suite_report.get("success") else "suite_failed",
                {
                    **observation,
                    "totals": suite_report.get("totals"),
                    **(
                        {"capabilities": result["run"]["capabilities"]}
                        if isinstance(result.get("run", {}).get("capabilities"), dict)
                        else {}
                    ),
                },
            )
        event_logger.set_scope(suite_id=None, case_id=None, step_id=None, phase=None)
        observation = result["run"].get("observation") or {
            "outcome": "passed" if result["success"] else "blocked"
        }
        event_logger.write(
            "run_completed" if result["success"] else "run_failed",
            {
                **observation,
                "success": result["success"],
                "totals": result["totals"],
                **(
                    {"capabilities": result["run"]["capabilities"]}
                    if isinstance(result.get("run", {}).get("capabilities"), dict)
                    else {}
                ),
            },
        )
    else:
        event_logger.write("run_end", {"run_id": run_id, "success": result["success"], "totals": result["totals"]})
    _write_json_file(report_file, result)
    render_html_report(result, html_report_file)
    summary = _summary_payload(result, report_file, events_file, html_report_file)
    _log_progress(
        "run={run_id} result={result} suites={suites} cases={cases} passed={passed} "
        "failed={failed} skipped={skipped} report={report}".format(
            run_id=run_id,
            result="passed" if result["success"] else "failed",
            suites=result["totals"]["suites"],
            cases=result["totals"]["cases"],
            passed=result["totals"]["passed"],
            failed=result["totals"]["failed"],
            skipped=result["totals"]["skipped"],
            report=report_file,
        )
    )
    _print_json(summary)
    return 0 if result["success"] else 1


def _validate_failure_pause_args(args: argparse.Namespace, *, fixture_mode: bool) -> None:
    if not bool(getattr(args, "pause_on_failure", False)):
        return
    if args.headless:
        raise ValueError("--pause-on-failure 不支持 --headless")
    if fixture_mode:
        raise ValueError("--pause-on-failure 不支持 fixture 模式")
    if args.concurrency != 1:
        raise ValueError("--pause-on-failure 需要 --concurrency 1")
    if args.ai_observe:
        raise ValueError("--pause-on-failure 不支持 --ai-observe")
    if args.performance:
        raise ValueError("--pause-on-failure 不支持 --performance")
    if "--on-case-failure" in getattr(args, "_explicit_options", set()) and args.on_case_failure != "stop_run":
        raise ValueError("--pause-on-failure 只允许显式指定 --on-case-failure stop_run")
    isatty = getattr(sys.stdin, "isatty", None)
    if not callable(isatty) or not isatty():
        raise ValueError("--pause-on-failure 需要交互式终端")


def _cmd_manual_browser_session(args: argparse.Namespace) -> int:
    _reject_manual_browser_session_args(args)
    request_forward_rules = parse_request_forward_specs(getattr(args, "request_forward_specs", []) or [])
    env = ConfigLoader(args.config).get_env(args.env)
    persistent_profile = _persistent_profile_enabled(args, fixture_mode=False)
    profile_path = resolve_profile_path() if persistent_profile else None
    runtime = None
    runtime_kwargs = {"window_size": args.window_size} if args.window_size is not None else {}
    try:
        if persistent_profile:
            runtime = PlaywrightRuntime(
                env,
                requests.Session(),
                headless=False,
                request_forward_rules=request_forward_rules,
                profile_dir=profile_path,
                **runtime_kwargs,
            )
            runtime.start()
        with SessionReuse(force_login=args.force_login).case(env) as session:
            if runtime is None:
                runtime = PlaywrightRuntime(
                    env,
                    session,
                    headless=False,
                    request_forward_rules=request_forward_rules,
                    **runtime_kwargs,
                )
                runtime.start()
            else:
                runtime.session = session
            bridge = CookieBridge(env, session, runtime)
            try:
                runtime.open_home()
                _log_progress(
                    f"manual_browser_session started home={env.base_url.rstrip('/')}/ "
                    f"forwarding={'enabled' if request_forward_rules else 'disabled'}"
                )
                exit_reason = runtime.wait_for_manual_session()
            finally:
                if bridge is not None:
                    try:
                        runtime.sync_manual_session_cookies()
                    finally:
                        bridge.detach()
    except KeyboardInterrupt:
        _stop_manual_browser_runtime(runtime)
        _print_json({"success": False, "mode": "manual_browser_session", "exit_reason": "user_interrupt"})
        return 130
    except Exception:
        _stop_manual_browser_runtime(runtime)
        raise
    _stop_manual_browser_runtime(runtime)
    _print_json({"success": True, "mode": "manual_browser_session", "exit_reason": exit_reason})
    return 0


def _reject_manual_browser_session_args(args: argparse.Namespace) -> None:
    invalid_options = (
        (bool(args.headless), "--headless"),
        (bool(args.pause_on_failure), "--pause-on-failure"),
        (bool(args.template_file or args.runtime_file), "--template-file/--runtime-file"),
        (bool(args.menu_path), "--menu-path"),
        (bool(args.vars_file or args.variable_overrides), "--vars-file/--var"),
        (bool(args.case_codes or args.case_globs or args.grep or args.tags or args.on_case_failure), "DSL 过滤参数"),
        (bool(args.performance), "--performance"),
        (bool(args.ai_observe), "--ai-observe"),
        ("--concurrency" in getattr(args, "_explicit_options", set()), "--concurrency"),
        (bool(args.step_timeout_seconds or args.case_timeout_seconds or args.run_timeout_seconds), "AI 超时参数"),
        (bool(args.max_network_body_bytes or args.max_network_case_bytes), "AI 网络采集参数"),
        (bool(args.report_file), "--report-file"),
        ("--report-dir" in getattr(args, "_explicit_options", set()), "--report-dir"),
    )
    for enabled, option in invalid_options:
        if enabled:
            raise ValueError(f"无 DSL 的 run 进入手工浏览器会话时不支持 {option}")


def _parse_window_size(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"([1-9][0-9]*)x([1-9][0-9]*)", str(value).strip())
    if match is None:
        raise ValueError("窗口尺寸格式无效，应为 WIDTHxHEIGHT，且宽高必须为正整数")
    return int(match.group(1)), int(match.group(2))


def _stop_manual_browser_runtime(runtime) -> None:
    if runtime is None:
        return
    try:
        runtime.stop()
    except Exception:
        pass


def _run_suite_specs_in_process(
    args: argparse.Namespace,
    suite_specs: list[SuiteRunSpec],
    *,
    env,
    variables: dict[str, Any],
    request_forward_rules: list[RequestForwardRule],
    fixture_mode: bool,
    persistent_profile: bool,
    profile_path: Path | None,
    window_size: tuple[int, int] | None,
    run_id: str,
    started_at: str,
    event_logger,
    report_file: Path | None = None,
    cancellation_event=None,
) -> dict[str, Any]:
    shared_runtime = None
    if fixture_mode:
        template_payload = load_json_file(args.template_file)
        runtime_elements = load_json_file(args.runtime_file)

        def _run_case(spec):
            report = _run_fixture_case(
                spec.case,
                template_payload,
                runtime_elements,
                args.menu_path,
                progress_logger=_make_step_progress_logger(spec.suite, spec.case, spec.case_index, spec.total_cases),
                performance_enabled=args.performance,
                runtime_variables=spec.suite.runtime_variables,
                runtime_context=spec.runtime_context,
                observation_session=event_logger if isinstance(event_logger, ObservationSession) else None,
                cancellation_event=cancellation_event,
            )
            return _attach_ai_step_observations(report) if args.ai_observe else report

    else:
        if env is None:
            env = ConfigLoader(args.config).get_env(args.env)
        if persistent_profile:
            runtime_kwargs = {}
            if request_forward_rules:
                runtime_kwargs["request_forward_rules"] = request_forward_rules
            if isinstance(event_logger, ObservationSession):
                runtime_kwargs["observation_session"] = event_logger
            if window_size is not None:
                runtime_kwargs["window_size"] = window_size
            shared_runtime = PlaywrightRuntime(
                env,
                requests.Session(),
                headless=args.headless,
                profile_dir=profile_path,
                **runtime_kwargs,
            )

        session_reuse = SessionReuse(force_login=bool(getattr(args, "force_login", False)))

        def _run_case(spec):
            report = _run_real_case(
                spec.case,
                env,
                args.default_org,
                args.headless,
                progress_logger=_make_step_progress_logger(spec.suite, spec.case, spec.case_index, spec.total_cases),
                tenant_name=spec.suite.tenant,
                fiscal_year=spec.suite.fiscal_year,
                performance_enabled=args.performance,
                request_forward_rules=request_forward_rules,
                runtime_variables=spec.suite.runtime_variables,
                runtime_context=spec.runtime_context,
                profile=profile_payload("persistent", profile_path, reuse_session=True) if persistent_profile else profile_payload("ephemeral"),
                shared_runtime=shared_runtime,
                profile_path=profile_path if persistent_profile else None,
                window_size=window_size,
                observation_session=event_logger if isinstance(event_logger, ObservationSession) else None,
                cancellation_event=cancellation_event,
                pause_on_failure=bool(getattr(args, "pause_on_failure", False)),
                report_file=report_file,
                session_reuse=session_reuse,
            )
            return _attach_ai_step_observations(report) if args.ai_observe else report

    try:
        result = run_suite_specs(
            suite_specs,
            run_case=_run_case,
            concurrency=args.concurrency,
            run_id=run_id,
            started_at=started_at,
            metadata=_run_metadata(
                args,
                variables,
                env,
                request_forward_rules=request_forward_rules,
                fixture_mode=fixture_mode,
            ),
            on_suite_start=lambda spec: _on_suite_start(spec, event_logger),
            on_case_start=lambda spec: _on_case_start(spec, event_logger),
            on_case_result=lambda spec, report: _on_case_result(spec, report, event_logger),
        )
        if isinstance(event_logger, ObservationSession):
            result.setdefault("run", {})["capabilities"] = event_logger.capabilities()
        return result
    finally:
        if shared_runtime is not None:
            shared_runtime.stop()


def _run_ai_suite_supervised(
    args: argparse.Namespace,
    suite_specs: list[SuiteRunSpec],
    *,
    env,
    variables: dict[str, Any],
    request_forward_rules: list[RequestForwardRule],
    fixture_mode: bool,
    persistent_profile: bool,
    profile_path: Path | None,
    window_size: tuple[int, int] | None,
    run_id: str,
    started_at: str,
    event_logger: ObservationSession,
) -> dict[str, Any]:
    timeout_config = _ai_observation_config(args)
    run_started_monotonic = time.monotonic()
    run_deadline = run_started_monotonic + timeout_config["run_timeout_seconds"]
    case_deadline: float | None = None
    step_deadline: float | None = None
    active_scope: dict[str, Any] = {}
    active_target: dict[str, Any] = {}
    context = multiprocessing.get_context("spawn")
    event_queue = context.Queue()
    result_queue = context.Queue()
    cancellation_event = context.Event()
    process = context.Process(
        target=_run_ai_suite_worker,
        args=(
            args,
            suite_specs,
            env,
            variables,
            request_forward_rules,
            fixture_mode,
            persistent_profile,
            profile_path,
            window_size,
            run_id,
            started_at,
            event_queue,
            result_queue,
            cancellation_event,
        ),
        name="ydf-browser-ai-worker",
    )
    process.start()
    worker_result: dict[str, Any] | None = None
    while process.is_alive() or worker_result is None:
        try:
            message = event_queue.get(timeout=0.1)
            _write_remote_observation(event_logger, message)
            active_scope = dict(message.get("scope") or {})
            active_target = dict((message.get("payload") or {}).get("business_target") or active_target)
            event = message.get("event")
            now = time.monotonic()
            if event == "case_started":
                case_deadline = now + timeout_config["case_timeout_seconds"]
                step_deadline = None
            elif event == "step_started":
                step_deadline = now + timeout_config["step_timeout_seconds"]
            elif event in {"step_completed", "step_failed"}:
                step_deadline = None
            elif event in {"case_completed", "case_failed"}:
                case_deadline = None
                step_deadline = None
        except queue.Empty:
            pass
        timeout_reason = _expired_timeout_reason(
            time.monotonic(),
            run_deadline=run_deadline,
            case_deadline=case_deadline,
            step_deadline=step_deadline,
        )
        if timeout_reason is not None:
            scope_name = timeout_reason.removesuffix("_timeout")
            event_logger.set_scope(
                suite_id=active_scope.get("suite_id"),
                case_id=active_scope.get("case_id"),
                step_id=active_scope.get("step_id"),
                phase=active_scope.get("phase"),
            )
            event_logger.write(
                f"{scope_name}_timed_out",
                {
                    "outcome": "terminated",
                    "reason_code": "timeout",
                    "operation_reason": timeout_reason,
                    "business_target": active_target,
                },
            )
            termination_mode = _request_worker_stop(process, cancellation_event, grace_seconds=0.5)
            return _terminated_run_result(
                args,
                suite_specs,
                variables=variables,
                env=env,
                request_forward_rules=request_forward_rules,
                fixture_mode=fixture_mode,
                run_id=run_id,
                started_at=started_at,
                started_monotonic=run_started_monotonic,
                active_scope=active_scope,
                active_target=active_target,
                operation_reason=timeout_reason,
                worker_pid=process.pid,
                termination_mode=termination_mode,
            )
        try:
            worker_result = result_queue.get_nowait()
        except queue.Empty:
            if not process.is_alive():
                break
    process.join()
    while True:
        try:
            _write_remote_observation(event_logger, event_queue.get_nowait())
        except queue.Empty:
            break
    if worker_result is None:
        raise RuntimeError(f"AI 观察工作进程异常退出: exit_code={process.exitcode}")
    if not worker_result.get("ok"):
        raise RuntimeError(str(worker_result.get("error") or "AI 观察工作进程执行失败"))
    result = worker_result["result"]
    result["run"]["worker_process"] = {"pid": process.pid, "parent_pid": os.getpid()}
    return result


def _expired_timeout_reason(
    now: float,
    *,
    run_deadline: float,
    case_deadline: float | None,
    step_deadline: float | None,
) -> str | None:
    deadlines = [
        (deadline, reason)
        for deadline, reason in (
            (step_deadline, "step_timeout"),
            (case_deadline, "case_timeout"),
            (run_deadline, "run_timeout"),
        )
        if deadline is not None
    ]
    deadline, reason = min(deadlines)
    return reason if now >= deadline else None


def _terminated_run_result(
    args: argparse.Namespace,
    suite_specs: list[SuiteRunSpec],
    *,
    variables: dict[str, Any],
    env,
    request_forward_rules: list[RequestForwardRule],
    fixture_mode: bool,
    run_id: str,
    started_at: str,
    started_monotonic: float,
    active_scope: dict[str, Any],
    active_target: dict[str, Any],
    operation_reason: str,
    worker_pid: int | None,
    termination_mode: str,
) -> dict[str, Any]:
    message = f"AI 观察运行受控超时: {operation_reason}"
    observation = {
        "outcome": "terminated",
        "reason_code": "timeout",
        "operation_reason": operation_reason,
    }
    suite_reports: list[dict[str, Any]] = []
    failed = 0
    skipped = 0
    for suite_spec in suite_specs:
        case_reports: list[dict[str, Any]] = []
        for index, case in enumerate(suite_spec.cases, start=1):
            is_active = suite_spec.suite.code == active_scope.get("suite_id") and case.code == active_scope.get("case_id")
            if is_active:
                action = str(active_target.get("action") or "")
                if not action and active_target.get("component"):
                    action = f"{active_target.get('component')}.{active_target.get('operation')}"
                step = StepResult(
                    action=action or "case.timeout",
                    success=False,
                    message=message,
                    data={"error": {"type": "TimeoutError", "message": message}},
                    observation={**observation, "business_target": active_target, "evidence_refs": []},
                )
                report = ExecutionReport(success=False, step_results=[step], errors=[message])
                case_reports.append(
                    {
                        "dsl_file": str(suite_spec.dsl_path),
                        "suite_code": suite_spec.suite.code,
                        "case_index": index,
                        "total_cases": len(suite_spec.cases),
                        "case": case.to_dict(),
                        "success": False,
                        "status": "failed",
                        "started_at": started_at,
                        "ended_at": _now_iso(),
                        "duration_ms": _elapsed_ms(started_monotonic),
                        "report": report.to_dict(),
                        "errors": [message],
                        "observation": observation,
                    }
                )
                failed += 1
            else:
                case_reports.append(
                    {
                        "dsl_file": str(suite_spec.dsl_path),
                        "suite_code": suite_spec.suite.code,
                        "case_index": index,
                        "total_cases": len(suite_spec.cases),
                        "case": case.to_dict(),
                        "success": False,
                        "status": "skipped",
                        "skip_reason": message,
                        "report": None,
                        "errors": [],
                    }
                )
                skipped += 1
        suite_reports.append(
            {
                "dsl_file": str(suite_spec.dsl_path),
                "suite": suite_spec.suite.to_dict(),
                "success": False,
                "on_case_failure": suite_spec.suite.on_case_failure,
                "totals": {
                    "cases": len(case_reports),
                    "passed": 0,
                    "failed": sum(item["status"] == "failed" for item in case_reports),
                    "skipped": sum(item["status"] == "skipped" for item in case_reports),
                },
                "case_reports": case_reports,
            }
        )
    run_payload = {
        "id": run_id,
        "started_at": started_at,
        "ended_at": _now_iso(),
        "duration_ms": _elapsed_ms(started_monotonic),
        "concurrency": 1,
        **_run_metadata(
            args,
            variables,
            env,
            request_forward_rules=request_forward_rules,
            fixture_mode=fixture_mode,
        ),
        "worker_process": {
            "pid": worker_pid,
            "parent_pid": os.getpid(),
            "termination": termination_mode,
        },
        "observation": observation,
    }
    if active_target.get("component") == "workflow_result":
        capabilities = run_payload.get("capabilities")
        if isinstance(capabilities, dict) and "workflow_result" not in capabilities.get("enabled", []):
            capabilities.setdefault("enabled", []).append("workflow_result")
    return {
        "success": False,
        "run": run_payload,
        "totals": {"suites": len(suite_reports), "cases": failed + skipped, "passed": 0, "failed": failed, "skipped": skipped},
        "suite_reports": suite_reports,
    }


def _run_ai_suite_worker(
    args: argparse.Namespace,
    suite_specs: list[SuiteRunSpec],
    env,
    variables: dict[str, Any],
    request_forward_rules: list[RequestForwardRule],
    fixture_mode: bool,
    persistent_profile: bool,
    profile_path: Path | None,
    window_size: tuple[int, int] | None,
    run_id: str,
    started_at: str,
    event_queue,
    result_queue,
    cancellation_event,
) -> None:
    observation = ObservationSession(
        Path(args.report_file).expanduser().parent / "events.jsonl"
        if args.report_file
        else Path(args.report_dir).expanduser() / run_id / "events.jsonl",
        tool_version=__version__,
        run_id=run_id,
        configuration=_ai_observation_run_configuration(args, _ai_observation_config(args)),
        event_queue=event_queue,
    )
    try:
        result = _run_suite_specs_in_process(
            args,
            suite_specs,
            env=env,
            variables=variables,
            request_forward_rules=request_forward_rules,
            fixture_mode=fixture_mode,
            persistent_profile=persistent_profile,
            profile_path=profile_path,
            window_size=window_size,
            run_id=run_id,
            started_at=started_at,
            event_logger=observation,
            cancellation_event=cancellation_event,
        )
    except BaseException as exc:
        result_queue.put({"ok": False, "error": f"{exc.__class__.__name__}: {exc}", "traceback": traceback.format_exc()})
    else:
        result_queue.put({"ok": True, "result": result})


def _write_remote_observation(event_logger: ObservationSession, message: dict[str, Any]) -> None:
    scope = message.get("scope") or {}
    event_logger.set_scope(
        suite_id=scope.get("suite_id"),
        case_id=scope.get("case_id"),
        step_id=scope.get("step_id"),
        phase=scope.get("phase"),
    )
    event_logger.write(str(message["event"]), dict(message.get("payload") or {}))


def _request_worker_stop(process, cancellation_event, *, grace_seconds: float) -> str:
    cancellation_event.set()
    process.join(timeout=grace_seconds)
    if not process.is_alive():
        return "cooperative"
    process.terminate()
    process.join(timeout=grace_seconds)
    if not process.is_alive():
        return "terminated"
    process.kill()
    process.join(timeout=grace_seconds)
    if process.is_alive():
        raise RuntimeError("AI 观察工作进程无法终止")
    return "killed"


def _ai_observation_config(args: argparse.Namespace) -> dict[str, Any]:
    fields = {
        "step_timeout_seconds": DEFAULT_STEP_TIMEOUT_SECONDS,
        "case_timeout_seconds": DEFAULT_CASE_TIMEOUT_SECONDS,
        "run_timeout_seconds": DEFAULT_RUN_TIMEOUT_SECONDS,
        "max_network_body_bytes": DEFAULT_MAX_NETWORK_BODY_BYTES,
        "max_network_case_bytes": DEFAULT_MAX_NETWORK_CASE_BYTES,
    }
    explicit = {name: getattr(args, name, None) for name in fields}
    if not bool(getattr(args, "ai_observe", False)):
        if any(value is not None for value in explicit.values()) or getattr(args, "explore_reference", None) is not None:
            raise ValueError("AI 观察参数只允许与 --ai-observe 同时使用")
        return {}
    effective = {name: explicit[name] if explicit[name] is not None else default for name, default in fields.items()}
    if any(value <= 0 for value in effective.values()):
        raise ValueError("AI 观察参数无效：超时和网络容量必须为正数")
    if not (
        effective["step_timeout_seconds"]
        <= effective["case_timeout_seconds"]
        <= effective["run_timeout_seconds"]
    ):
        raise ValueError("AI 观察参数无效：步骤超时必须不大于用例超时，用例超时必须不大于运行超时")
    if getattr(args, "explore_reference", None) is not None:
        from .popup_reference.discovery import validate_exploration_target
        try:
            target = json.loads(args.explore_reference)
        except (ValueError, TypeError) as exc:
            raise ValueError("--explore-reference 必须是 JSON 对象") from exc
        effective["reference_exploration"] = validate_exploration_target(target)
    return effective


def _cmd_run_ai_contract_failed(
    args: argparse.Namespace,
    exc: Exception,
    *,
    operation_reason: str,
) -> int:
    run_id = _make_run_id()
    started_at = _now_iso()
    report_file, events_file = _prepare_report_paths(args, run_id)
    try:
        ai_observation_config = _ai_observation_config(args)
    except ValueError:
        ai_observation_config = None
    event_logger = _event_logger_for_run(args, events_file, run_id, ai_observation_config)
    event_logger.write("run_started", {"run_id": run_id, "dsl_inputs": _dsl_inputs(args), "ai_observe": True})
    return _cmd_run_validation_failed(
        args,
        exc,
        variables={},
        env=None,
        run_id=run_id,
        started_at=started_at,
        report_file=report_file,
        events_file=events_file,
        event_logger=event_logger,
        reason_code="contract_incompatible",
        operation_reason=operation_reason,
    )


def _event_logger_for_run(
    args: argparse.Namespace,
    events_file: Path,
    run_id: str,
    ai_observation_config: dict[str, int] | None,
):
    if not bool(getattr(args, "ai_observe", False)):
        return _EventLogger(events_file)
    configuration = _ai_observation_run_configuration(args, ai_observation_config)
    return ObservationSession(
        events_file,
        tool_version=__version__,
        run_id=run_id,
        configuration=configuration,
    )


def _ai_observation_run_configuration(
    args: argparse.Namespace,
    effective: dict[str, int] | None,
) -> dict[str, Any]:
    configuration: dict[str, Any] = {"ai_observe": True, "concurrency": args.concurrency}
    if effective is not None:
        configuration.update(effective)
        return configuration
    for name in (
        "step_timeout_seconds",
        "case_timeout_seconds",
        "run_timeout_seconds",
        "max_network_body_bytes",
        "max_network_case_bytes",
    ):
        value = getattr(args, name, None)
        if value is not None:
            configuration[name] = value
    return configuration


def _attach_ai_step_observations(report: ExecutionReport) -> ExecutionReport:
    for step in report.step_results:
        if step.observation is None:
            step.observation = {
                "outcome": "passed" if step.success else "blocked",
                "evidence_refs": [],
            }
    return report


def _cmd_run_validation_failed(
    args: argparse.Namespace,
    exc: Exception,
    *,
    variables: dict[str, Any],
    env,
    run_id: str,
    started_at: str,
    report_file: Path,
    events_file: Path,
    event_logger: "_EventLogger",
    request_forward_rules: list[RequestForwardRule] | None = None,
    reason_code: str = "dsl_invalid",
    operation_reason: str = "dsl_validation_failed",
) -> int:
    message = str(exc)
    html_report_file = report_file.with_suffix(".html")
    result = _validation_failure_result(
        args,
        message,
        run_id=run_id,
        started_at=started_at,
        variables=variables,
        env=env,
        request_forward_rules=request_forward_rules or [],
        observation=(
            {
                "outcome": "blocked",
                "reason_code": reason_code,
                "operation_reason": operation_reason,
            }
            if bool(getattr(args, "ai_observe", False))
            else None
        ),
    )
    result["report_file"] = str(report_file)
    result["events_file"] = str(events_file)
    result["html_report_file"] = str(html_report_file)
    if getattr(args, "performance", False):
        _write_performance_workbook(result, report_file.with_name("performance.xlsx"))
    if isinstance(event_logger, ObservationSession):
        event_logger.stop_heartbeat()
    event_logger.write("run_validation_failed", {"run_id": run_id, "error": message})
    event_logger.write("run_end", {"run_id": run_id, "success": False, "totals": result["totals"]})
    _write_json_file(report_file, result)
    render_html_report(result, html_report_file)
    summary = _summary_payload(result, report_file, events_file, html_report_file)
    summary["error"] = message
    _print_human_error(message)
    _log_progress(
        "run={run_id} result=failed suites={suites} cases={cases} passed={passed} "
        "failed={failed} skipped={skipped} report={report}".format(
            run_id=run_id,
            suites=result["totals"]["suites"],
            cases=result["totals"]["cases"],
            passed=result["totals"]["passed"],
            failed=result["totals"]["failed"],
            skipped=result["totals"]["skipped"],
            report=report_file,
        )
    )
    _print_json(summary)
    return 1


def _validation_failure_result(
    args: argparse.Namespace,
    message: str,
    *,
    run_id: str,
    started_at: str,
    variables: dict[str, Any],
    env,
    request_forward_rules: list[RequestForwardRule] | None = None,
    observation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    suite = DslTestSuite(code="dsl_validation", name="DSL 语法校验")
    case = DslTestCase(code="syntax-validation", name="DSL 语法校验失败")
    report = ExecutionReport(
        success=False,
        step_results=[
            StepResult(
                action="dsl.validate",
                success=False,
                message=message,
                data={"error": {"type": "ValueError", "message": message}},
            )
        ],
        errors=[message],
    )
    dsl_file = _first_dsl_input(args)
    case_report = {
        "dsl_file": dsl_file,
        "suite_code": suite.code,
        "case_index": 1,
        "total_cases": 1,
        "case": case.to_dict(),
        "success": False,
        "status": "failed",
        "started_at": started_at,
        "ended_at": _now_iso(),
        "duration_ms": 0,
        "report": report.to_dict(),
        "errors": [message],
    }
    suite_report = {
        "dsl_file": dsl_file,
        "suite": suite.to_dict(),
        "success": False,
        "on_case_failure": "stop_run",
        "totals": {"cases": 1, "passed": 0, "failed": 1, "skipped": 0},
        "case_reports": [case_report],
    }
    run_payload = {
        "id": run_id,
        "started_at": started_at,
        "ended_at": _now_iso(),
        "duration_ms": 0,
        "concurrency": args.concurrency,
        **_run_metadata(
            args,
            variables,
            env,
            request_forward_rules=request_forward_rules or [],
            fixture_mode=bool(getattr(args, "template_file", None) and getattr(args, "runtime_file", None)),
        ),
    }
    if observation is not None:
        run_payload["observation"] = observation
    return {
        "success": False,
        "run": run_payload,
        "totals": {"suites": 1, "cases": 1, "passed": 0, "failed": 1, "skipped": 0},
        "suite_reports": [suite_report],
    }


def _first_dsl_input(args: argparse.Namespace) -> str:
    inputs = _dsl_inputs(args)
    return inputs[0] if inputs else ""


def _load_suite_specs(args: argparse.Namespace, variables: dict[str, Any] | None = None) -> list[SuiteRunSpec]:
    dsl_paths = discover_dsl_files(_dsl_inputs(args))
    specs: list[SuiteRunSpec] = []
    performance_enabled = bool(getattr(args, "performance", False))
    for dsl_path in dsl_paths:
        document = load_dsl_document_from_file(
            dsl_path,
            variables=variables,
            validate_bpr_state=performance_enabled,
        )
        cases = filter_cases(
            document.cases,
            case_codes=args.case_codes,
            case_globs=args.case_globs,
            grep=args.grep,
            tags=args.tags,
        )
        if not cases:
            continue
        suite = document.suite
        if args.pause_on_failure:
            suite = replace(suite, on_case_failure="stop_run")
        elif args.on_case_failure:
            suite = replace(suite, on_case_failure=args.on_case_failure)
        if not performance_enabled:
            cases = [_without_bpr_control_steps(case) for case in cases]
        specs.append(SuiteRunSpec(dsl_path=dsl_path, suite=suite, cases=cases))
    if not specs:
        raise ValueError("没有匹配到可执行用例")
    return specs


def _without_bpr_control_steps(case: DslTestCase) -> DslTestCase:
    filtered_steps = [step for step in case.steps if not _is_bpr_control_step(step)]
    if len(filtered_steps) == len(case.steps):
        return case
    return replace(case, steps=filtered_steps)


def _is_bpr_control_step(step: ActionStep) -> bool:
    return bool(step.kind == "component" and step.component == "bpr" and step.operation in {"start", "stop"})


def _load_external_variables(args: argparse.Namespace, env=None) -> dict[str, Any]:
    variables: dict[str, Any] = {}
    if env is not None:
        variables = merge_variables(variables, env.variables)
    for vars_file in args.vars_file:
        variables = merge_variables(variables, load_variables_file(vars_file))
    variables = merge_variables(variables, parse_cli_variables(args.variable_overrides))
    return variables


def _make_run_id() -> str:
    return f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _elapsed_ms(started: float) -> int:
    return max(0, int(round((time.monotonic() - started) * 1000)))


def _prepare_report_paths(args: argparse.Namespace, run_id: str) -> tuple[Path, Path]:
    if args.report_file:
        report_file = Path(args.report_file).expanduser()
        run_dir = report_file.parent
    else:
        run_dir = Path(args.report_dir).expanduser() / run_id
        report_file = run_dir / "report.json"
    events_file = run_dir / "events.jsonl"
    artifacts_dir = run_dir / "artifacts"
    if bool(getattr(args, "ai_observe", False)):
        artifacts_have_content = artifacts_dir.is_dir() and any(artifacts_dir.iterdir())
        if report_file.exists() or events_file.exists() or artifacts_have_content:
            raise ValueError(f"AI 观察证据目录已存在，不能覆盖: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)
    if bool(getattr(args, "ai_observe", False)):
        artifacts_dir.mkdir(exist_ok=True)
    return report_file, events_file


def _run_metadata(
    args: argparse.Namespace,
    variables: dict[str, Any],
    env=None,
    request_forward_rules: list[RequestForwardRule] | None = None,
    fixture_mode: bool = False,
) -> dict[str, Any]:
    base_url = getattr(env, "base_url", "") if env is not None else ""
    metadata = {
        "cwd": str(Path.cwd()),
        "env": base_url or args.env,
        "env_name": args.env,
        "headless": bool(args.headless),
        "dsl_inputs": _dsl_inputs(args),
        "dsl_list": _dsl_list_inputs(args),
        "filters": {
            "case_codes": args.case_codes,
            "case_globs": args.case_globs,
            "grep": args.grep or "",
            "tags": args.tags,
        },
        "variables": {
            "keys": variable_keys(variables),
            "vars_files": args.vars_file,
            "override_keys": variable_keys(parse_cli_variables(args.variable_overrides)),
        },
        "request_forwarding": request_forwarding_payload(request_forward_rules or []),
        "git": _git_metadata(),
    }
    if bool(getattr(args, "ai_observe", False)):
        try:
            ai_config = _ai_observation_config(args)
        except ValueError:
            ai_config = None
        metadata.update(
            {
                "ai_observe": True,
                "tool_version": __version__,
                "contract_version": CONTRACT_VERSION,
                "capabilities": {
                    "available": list(AVAILABLE_CAPABILITIES),
                    "enabled": list(AI_OBSERVATION_CAPABILITIES),
                },
                "configuration": _ai_observation_run_configuration(args, ai_config),
                "verification": _ai_verification_entrypoint(),
            }
        )
    if not fixture_mode and getattr(args, "command", "") == "run":
        persistent_profile = _persistent_profile_enabled(args, fixture_mode)
        metadata["profile"] = profile_payload("persistent", resolve_profile_path(), reuse_session=True) if persistent_profile else profile_payload("ephemeral")
    if getattr(args, "performance", False):
        metadata["performance"] = _run_performance_payload({}, _dict_profile_mode(metadata.get("profile")))
    return metadata


def _ai_verification_entrypoint() -> dict[str, Any]:
    helper_sha256 = os.environ.get("YDF_BROWSER_AI_HELPER_SHA256", "").strip().lower()
    if re.fullmatch(r"[0-9a-f]{64}", helper_sha256):
        return {
            "entrypoint": "skill_helper",
            "verification_eligible": True,
            "helper_sha256": helper_sha256,
            "status": "not_evaluated",
        }
    return {
        "entrypoint": "direct_cli",
        "verification_eligible": False,
        "status": "not_evaluated",
        "reason_code": "skill_helper_required",
    }


def _run_performance_payload(summary: dict[str, Any], profile_mode: str = "") -> dict[str, Any]:
    return {
        "enabled": True,
        "cache_modes": _cache_modes_for_profile(profile_mode),
        "summary": summary,
    }


def _dict_profile_mode(profile: Any) -> str:
    return str(profile.get("mode") or "") if isinstance(profile, dict) else ""


def _cache_modes_for_profile(profile_mode: str) -> list[str]:
    if profile_mode == "persistent":
        return ["persistent_profile_case_open_menu", "persistent_profile_same_case_reopen_menu"]
    if profile_mode == "ephemeral":
        return ["ephemeral_case_open_menu", "ephemeral_same_context_reopen_menu"]
    return ["cold_ephemeral", "warm_same_context_open_menu"]


def _write_performance_workbook(result: dict[str, Any], performance_file: Path) -> None:
    performance = result.setdefault("run", {}).setdefault("performance", {"enabled": True})
    try:
        export_performance_xlsx(result, performance_file)
    except Exception as exc:
        error = {"type": exc.__class__.__name__, "message": str(exc)}
        result["performance_export_error"] = error
        if isinstance(performance, dict):
            performance["export_error"] = error["message"]
        return
    result["performance_file"] = str(performance_file)
    if isinstance(performance, dict):
        performance["file"] = str(performance_file)


def _performance_summary(result: dict[str, Any]) -> dict[str, Any]:
    case_durations: list[int] = []
    slowest_case: dict[str, Any] | None = None
    slowest_step: dict[str, Any] | None = None
    network_failed_count = 0
    top_requests: list[dict[str, Any]] = []
    top_api_requests: list[dict[str, Any]] = []
    top_static_resources: list[dict[str, Any]] = []
    warm_durations: list[int] = []
    for suite_report in result.get("suite_reports", []):
        suite_code = str((suite_report.get("suite") or {}).get("code") or suite_report.get("suite_code") or "")
        for case_report in suite_report.get("case_reports", []):
            duration_ms = int(case_report.get("duration_ms") or 0)
            case_durations.append(duration_ms)
            case_code = str((case_report.get("case") or {}).get("code") or "")
            if slowest_case is None or duration_ms > int(slowest_case.get("duration_ms") or 0):
                slowest_case = {"suite_code": suite_code, "case_code": case_code, "duration_ms": duration_ms}
            performance = case_report.get("performance") if isinstance(case_report, dict) else None
            if isinstance(performance, dict):
                warm = performance.get("warm_open_menu")
                if isinstance(warm, dict) and warm.get("success", True):
                    warm_durations.append(int(warm.get("duration_ms") or 0))
                    network = warm.get("network")
                    if isinstance(network, dict):
                        network_failed_count += int(network.get("failed_count") or 0)
                        top_requests.extend(_top_requests_from_network(network, suite_code, case_code, "warm_open_menu"))
                        top_api_requests.extend(_top_requests_from_network(network, suite_code, case_code, "warm_open_menu", "top_slow_api_requests"))
                        top_static_resources.extend(_top_requests_from_network(network, suite_code, case_code, "warm_open_menu", "top_slow_static_resources"))
            report = case_report.get("report")
            if not isinstance(report, dict):
                continue
            for step in report.get("step_results", []):
                data = step.get("data") if isinstance(step, dict) else None
                perf = data.get("performance") if isinstance(data, dict) else None
                if not isinstance(perf, dict):
                    continue
                step_duration = int(perf.get("duration_ms") or 0)
                action = str(step.get("action") or "")
                if slowest_step is None or step_duration > int(slowest_step.get("duration_ms") or 0):
                    slowest_step = {"suite_code": suite_code, "case_code": case_code, "action": action, "duration_ms": step_duration}
                network = perf.get("network")
                if isinstance(network, dict):
                    network_failed_count += int(network.get("failed_count") or 0)
                    top_requests.extend(_top_requests_from_network(network, suite_code, case_code, action))
                    top_api_requests.extend(_top_requests_from_network(network, suite_code, case_code, action, "top_slow_api_requests"))
                    top_static_resources.extend(_top_requests_from_network(network, suite_code, case_code, action, "top_slow_static_resources"))
    top_requests = sorted(top_requests, key=lambda item: int(item.get("duration_ms") or 0), reverse=True)[:5]
    top_api_requests = sorted(top_api_requests, key=lambda item: int(item.get("duration_ms") or 0), reverse=True)[:5]
    top_static_resources = sorted(top_static_resources, key=lambda item: int(item.get("duration_ms") or 0), reverse=True)[:5]
    return {
        "cold_case_avg_ms": int(round(sum(case_durations) / len(case_durations))) if case_durations else 0,
        "cold_case_max_ms": max(case_durations) if case_durations else 0,
        "warm_open_menu_avg_ms": int(round(sum(warm_durations) / len(warm_durations))) if warm_durations else 0,
        "slowest_case": slowest_case or {},
        "slowest_step": slowest_step or {},
        "network_failed_count": network_failed_count,
        "top_slow_requests": top_requests,
        "top_slow_api_requests": top_api_requests,
        "top_slow_static_resources": top_static_resources,
    }


def _top_requests_from_network(
    network: dict[str, Any],
    suite_code: str,
    case_code: str,
    action: str,
    key: str = "top_slow_requests",
) -> list[dict[str, Any]]:
    requests = []
    for item in network.get(key) or []:
        if not isinstance(item, dict):
            continue
        requests.append(
            {
                "suite_code": suite_code,
                "case_code": case_code,
                "action": action,
                "url": str(item.get("url") or ""),
                "method": str(item.get("method") or ""),
                "resource_type": str(item.get("resource_type") or ""),
                "status": int(item.get("status") or 0),
                "duration_ms": int(item.get("duration_ms") or 0),
                "failed": bool(item.get("failed")),
            }
        )
    return requests


def _git_metadata() -> dict[str, Any]:
    commit = _run_git_command(["git", "rev-parse", "HEAD"])
    branch = _run_git_command(["git", "branch", "--show-current"])
    if not commit:
        return {
            "available": False,
            "commit": "",
            "branch": "",
            "dirty": False,
        }
    status = _run_git_command(["git", "status", "--short"])
    return {
        "available": True,
        "commit": commit,
        "branch": branch,
        "dirty": bool(status),
    }


def _run_git_command(command: list[str]) -> str:
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=5)
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _dsl_inputs(args: argparse.Namespace) -> list[str]:
    inputs: list[str] = []
    for spec in getattr(args, "dsl_input_specs", None) or []:
        kind = spec.get("kind")
        values = spec.get("values") or []
        if kind == "dsl":
            inputs.extend(str(value) for value in values)
        elif kind == "dsl_list":
            for value in values:
                inputs.extend(_read_dsl_list_file(value))
    if not inputs:
        raise ValueError("请通过 --dsl 或 --dsl-list 指定 DSL 输入")
    return inputs


def _dsl_list_inputs(args: argparse.Namespace) -> list[str]:
    values: list[str] = []
    for spec in getattr(args, "dsl_input_specs", None) or []:
        if spec.get("kind") == "dsl_list":
            values.extend(str(value) for value in spec.get("values") or [])
    return values


def _read_dsl_list_file(path: str) -> list[str]:
    list_path = Path(path).expanduser()
    if not list_path.is_file():
        raise ValueError(f"DSL 清单文件不存在或不是文件: {list_path}")
    inputs: list[str] = []
    for line_no, raw_line in enumerate(list_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        item_path = Path(line).expanduser()
        if not item_path.is_absolute():
            item_path = list_path.parent / item_path
        if not item_path.exists():
            raise ValueError(f"DSL 清单 {list_path} 第 {line_no} 行无效: 未找到 DSL 文件 {line}")
        if not item_path.is_file():
            raise ValueError(f"DSL 清单 {list_path} 第 {line_no} 行无效: 不是 DSL 文件 {line}")
        if item_path.suffix.lower() not in DSL_SUFFIXES:
            raise ValueError(f"DSL 清单 {list_path} 第 {line_no} 行无效: 不支持的 DSL 文件类型 {line}")
        inputs.append(str(item_path))
    return inputs


class _EventLogger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def write(self, event: str, payload: dict[str, Any]) -> None:
        record = {"time": _now_iso(), "event": event, **payload}
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                json.dump(record, handle, ensure_ascii=False)
                handle.write("\n")


def _on_suite_start(spec, event_logger: _EventLogger) -> None:
    _log_suite_start(spec.suite, len(spec.cases))
    if isinstance(event_logger, ObservationSession):
        event_logger.set_scope(suite_id=spec.suite.code, case_id=None, step_id=None, phase=None)
        event_logger.write(
            "suite_started",
            {"dsl_file": str(spec.dsl_path), "suite": spec.suite.to_dict(), "cases": len(spec.cases)},
        )
        return
    event_logger.write(
        "suite_start",
        {"dsl_file": str(spec.dsl_path), "suite": spec.suite.to_dict(), "cases": len(spec.cases)},
    )


def _on_case_start(spec, event_logger: _EventLogger) -> None:
    _log_case_start(spec.case_index, spec.total_cases, spec.case)
    if isinstance(event_logger, ObservationSession):
        event_logger.set_scope(
            suite_id=spec.suite.code,
            case_id=spec.case.code,
            step_id=None,
            phase=None,
        )
        event_logger.write(
            "case_started",
            {
                "dsl_file": str(spec.dsl_path),
                "case_index": spec.case_index,
                "total_cases": spec.total_cases,
                "case": spec.case.to_dict(),
            },
        )
        return
    event_logger.write(
        "case_start",
        {
            "dsl_file": str(spec.dsl_path),
            "suite_code": spec.suite.code,
            "case_index": spec.case_index,
            "total_cases": spec.total_cases,
            "case": spec.case.to_dict(),
        },
    )


def _on_case_result(spec, report: ExecutionReport, event_logger: _EventLogger) -> None:
    _log_case_result(spec.case_index, spec.total_cases, spec.case, report)
    payload = {
        "dsl_file": str(spec.dsl_path),
        "suite_code": spec.suite.code,
        "case_index": spec.case_index,
        "total_cases": spec.total_cases,
        "case_code": spec.case.code,
        "success": report.success,
        "errors": report.errors,
    }
    if report.performance is not None:
        payload["performance"] = _case_performance_event_summary(report.performance)
    if report.bpr_sessions:
        payload["bpr_session_count"] = len(report.bpr_sessions)
    if isinstance(event_logger, ObservationSession):
        event_logger.set_scope(
            suite_id=spec.suite.code,
            case_id=spec.case.code,
            step_id=None,
            phase=None,
        )
        observation = next(
            (step.observation for step in reversed(report.step_results) if step.observation is not None),
            {"outcome": "passed" if report.success else "blocked"},
        )
        payload.update(observation)
        event_logger.write("case_completed" if report.success else "case_failed", payload)
    else:
        event_logger.write("case_result", payload)


def _case_performance_event_summary(performance: dict[str, Any]) -> dict[str, Any]:
    cold = performance.get("cold") if isinstance(performance, dict) else {}
    warm = performance.get("warm_open_menu") if isinstance(performance, dict) else {}
    return {
        "cache_mode": performance.get("cache_mode"),
        "network_available": bool(performance.get("network_available")),
        "cold_duration_ms": int((cold or {}).get("duration_ms") or 0) if isinstance(cold, dict) else 0,
        "warm_open_menu_duration_ms": int((warm or {}).get("duration_ms") or 0) if isinstance(warm, dict) else 0,
    }


def _has_bpr_sessions(result: dict[str, Any]) -> bool:
    for suite_report in result.get("suite_reports", []) or []:
        if not isinstance(suite_report, dict):
            continue
        for case_report in suite_report.get("case_reports", []) or []:
            if not isinstance(case_report, dict):
                continue
            if case_report.get("bpr_sessions"):
                return True
            report = case_report.get("report")
            if isinstance(report, dict) and report.get("bpr_sessions"):
                return True
    return False


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_json(path, payload)


def _summary_payload(result: dict[str, Any], report_file: Path, events_file: Path, html_report_file: Path) -> dict[str, Any]:
    summary = {
        "success": result["success"],
        "run_id": result["run"]["id"],
        "totals": result["totals"],
        "report_file": str(report_file),
        "events_file": str(events_file),
        "html_report_file": str(html_report_file),
    }
    first_failure = _first_failure(result)
    if first_failure:
        summary["first_failure"] = first_failure
    if result.get("performance_file"):
        summary["performance_file"] = str(result.get("performance_file"))
    if result.get("performance_export_error"):
        summary["performance_export_error"] = result["performance_export_error"]
    return summary


def _first_failure(result: dict[str, Any]) -> dict[str, str] | None:
    for suite_report in result.get("suite_reports", []):
        for case_report in suite_report.get("case_reports", []):
            if case_report.get("status") != "failed":
                continue
            return {
                "dsl_file": str(case_report.get("dsl_file") or ""),
                "suite_code": str(case_report.get("suite_code") or ""),
                "case_code": str((case_report.get("case") or {}).get("code") or ""),
                "message": str((case_report.get("errors") or [""])[0]),
            }
    return None


def _run_fixture_suite(
    suite: DslTestSuite,
    cases: list[DslTestCase],
    template_payload: dict,
    runtime_elements: list[dict],
    menu_path: str | None,
) -> dict:
    _log_suite_start(suite, len(cases))
    case_reports = []
    for index, case in enumerate(cases, start=1):
        _log_case_start(index, len(cases), case)
        report = _run_fixture_case(
            case,
            template_payload,
            runtime_elements,
            menu_path,
            progress_logger=_make_step_progress_logger(suite, case, index, len(cases)),
        )
        _log_case_result(index, len(cases), case, report)
        case_reports.append(_case_report_payload(case, report))
    return _suite_report_payload(suite, case_reports)


def _run_fixture_single_case(
    suite: DslTestSuite,
    case: DslTestCase,
    template_payload: dict,
    runtime_elements: list[dict],
    menu_path: str | None,
) -> ExecutionReport:
    _log_suite_start(suite, 1)
    _log_case_start(1, 1, case)
    report = _run_fixture_case(
        case,
        template_payload,
        runtime_elements,
        menu_path,
        progress_logger=_make_step_progress_logger(suite, case, 1, 1),
    )
    _log_case_result(1, 1, case, report)
    return report


def _run_fixture_case(
    case: DslTestCase,
    template_payload: dict,
    runtime_elements: list[dict],
    menu_path: str | None,
    progress_logger=None,
    performance_enabled: bool = False,
    runtime_variables: list[str] | None = None,
    runtime_context=None,
    observation_session=None,
    cancellation_event=None,
) -> ExecutionReport:
    gateway = FixtureGateway(template_payload, menu_path)
    runtime = FixtureRuntime(runtime_elements)
    executor_kwargs = {"gateway": gateway, "runtime": runtime, "progress_logger": progress_logger}
    if observation_session is not None:
        executor_kwargs["observation_session"] = observation_session
    if cancellation_event is not None:
        executor_kwargs["cancellation_event"] = cancellation_event
    if performance_enabled:
        executor_kwargs["performance_enabled"] = True
    if runtime_variables:
        executor_kwargs["runtime_variables"] = runtime_variables
        executor_kwargs["runtime_context"] = runtime_context
    executor = WorkflowExecutor(**executor_kwargs)
    return executor.run(case.steps)


def _run_real_suite(
    suite: DslTestSuite,
    cases: list[DslTestCase],
    env,
    default_org: str | None,
    headless: bool,
) -> dict:
    _log_suite_start(suite, len(cases))
    case_reports = []
    for index, case in enumerate(cases, start=1):
        _log_case_start(index, len(cases), case)
        report = _run_real_case(
            case,
            env,
            default_org,
            headless,
            progress_logger=_make_step_progress_logger(suite, case, index, len(cases)),
            tenant_name=suite.tenant,
            fiscal_year=suite.fiscal_year,
        )
        _log_case_result(index, len(cases), case, report)
        case_reports.append(_case_report_payload(case, report))
    return _suite_report_payload(suite, case_reports)


def _run_real_single_case(
    suite: DslTestSuite,
    case: DslTestCase,
    env,
    default_org: str | None,
    headless: bool,
) -> ExecutionReport:
    _log_suite_start(suite, 1)
    _log_case_start(1, 1, case)
    report = _run_real_case(
        case,
        env,
        default_org,
        headless,
        progress_logger=_make_step_progress_logger(suite, case, 1, 1),
        tenant_name=suite.tenant,
        fiscal_year=suite.fiscal_year,
    )
    _log_case_result(1, 1, case, report)
    return report


def _run_real_case(
    case: DslTestCase,
    env,
    default_org: str | None,
    headless: bool,
    progress_logger=None,
    tenant_name: str | None = None,
    fiscal_year: str | None = None,
    performance_enabled: bool = False,
    request_forward_rules: list[RequestForwardRule] | None = None,
    runtime_variables: list[str] | None = None,
    runtime_context=None,
    profile: dict[str, Any] | None = None,
    shared_runtime=None,
    profile_path: Path | None = None,
    window_size: tuple[int, int] | None = None,
    observation_session=None,
    cancellation_event=None,
    pause_on_failure: bool = False,
    report_file: Path | None = None,
    session_reuse: SessionReuse | None = None,
) -> ExecutionReport:
    case_env = _env_for_case(env, case)
    case_default_org = case.default_org
    setup_performance: dict[str, int] = {}
    setup_timing: dict[str, dict[str, Any]] = {}
    runtime = shared_runtime
    session_scope = ExitStack()
    report = None
    try:
        try:
            if runtime is not None:
                runtime.config = case_env
                if getattr(runtime, "_context", None) is None:
                    phase_started = time.monotonic()
                    try:
                        runtime.start()
                    except Exception as exc:
                        setup_timing["browser_start"] = {
                            "duration_ms": _elapsed_ms(phase_started),
                            "success": False,
                            "error": {"type": exc.__class__.__name__, "message": str(exc)},
                        }
                        raise
                    setup_timing["browser_start"] = {
                        "duration_ms": _elapsed_ms(phase_started),
                        "success": True,
                    }
                clear_cookies = getattr(runtime, "clear_visible_cookies", None)
                if clear_cookies is not None and session_reuse is None:
                    clear_cookies(case_env.base_url)
            phase_started = time.monotonic()
            try:
                if session_reuse is None:
                    session = _login_with_default_org_context(
                        case_env, case_default_org, tenant_name=tenant_name, fiscal_year=fiscal_year,
                    )
                else:
                    session = session_scope.enter_context(session_reuse.case(
                        case_env, default_org=case_default_org,
                        tenant_name=tenant_name, fiscal_year=fiscal_year,
                    ))
            except Exception as exc:
                setup_timing.update(dict(getattr(exc, "_ydf_setup_timing", {}) or {}))
                setup_timing.setdefault(
                    "login",
                    {
                        "duration_ms": _elapsed_ms(phase_started),
                        "success": False,
                        "error": {"type": exc.__class__.__name__, "message": str(exc)},
                    },
                )
                raise
            recorded_login_timing = dict(getattr(session, "_ydf_setup_timing", {}) or {})
            if recorded_login_timing:
                setup_timing.update(recorded_login_timing)
            else:
                setup_timing["login"] = {
                    "duration_ms": _elapsed_ms(phase_started),
                    "success": True,
                }
            gateway = YondifGateway(case_env, session)
            if runtime is None:
                runtime_kwargs = {}
                if request_forward_rules:
                    runtime_kwargs["request_forward_rules"] = request_forward_rules
                if observation_session is not None:
                    runtime_kwargs["observation_session"] = observation_session
                if window_size is not None:
                    runtime_kwargs["window_size"] = window_size
                runtime = PlaywrightRuntime(case_env, session, headless=headless, profile_dir=profile_path, **runtime_kwargs)
            else:
                runtime.session = session
                runtime.observation_session = observation_session
            if performance_enabled:
                enable_performance = getattr(runtime, "enable_performance_collection", None)
                if enable_performance is not None:
                    enable_performance()
            if shared_runtime is None:
                phase_started = time.monotonic()
                try:
                    runtime.start()
                except Exception as exc:
                    setup_timing["browser_start"] = {
                        "duration_ms": _elapsed_ms(phase_started),
                        "success": False,
                        "error": {"type": exc.__class__.__name__, "message": str(exc)},
                    }
                    raise
                setup_timing["browser_start"] = {
                    "duration_ms": _elapsed_ms(phase_started),
                    "success": True,
                }
        except Exception as exc:
            message = str(exc)
            report = ExecutionReport(
                success=False,
                step_results=[
                    StepResult(
                        action="case.setup",
                        success=False,
                        message=message,
                        data={"error": {"type": exc.__class__.__name__, "message": message}},
                    )
                ],
                errors=[message],
                timing={"setup": setup_timing},
                profile=profile,
            )
            return report
        if session_reuse is not None:
            CookieBridge(case_env, session, runtime)
        setup_performance.update(
            {
                f"{name}_ms": int(data.get("duration_ms") or 0)
                for name, data in setup_timing.items()
            }
        )
        executor_kwargs = {
            "gateway": gateway,
            "runtime": runtime,
            "progress_logger": progress_logger,
            "menu_opening": MenuOpening.for_browser(gateway, runtime),
        }
        if observation_session is not None:
            executor_kwargs["observation_session"] = observation_session
        if cancellation_event is not None:
            executor_kwargs["cancellation_event"] = cancellation_event
        if performance_enabled:
            executor_kwargs["performance_enabled"] = True
        if runtime_variables:
            executor_kwargs["runtime_variables"] = runtime_variables
            executor_kwargs["runtime_context"] = runtime_context
        executor = WorkflowExecutor(**executor_kwargs)
        report = executor.run(case.steps)
        report.profile = profile
        report.timing = {**report.timing, "setup": setup_timing}
        if pause_on_failure and not report.success and runtime.has_open_page():
            _pause_failed_case(case, report, report_file, runtime)
        if performance_enabled:
            performance = report.performance or {"enabled": True}
            performance["setup"] = setup_performance
            if isinstance(performance, dict) and profile is not None:
                performance["cache_mode"] = _case_open_cache_mode(profile)
            warm_open_menu = _capture_warm_open_menu(runtime, report, profile)
            if warm_open_menu is not None:
                performance["warm_open_menu"] = warm_open_menu
            report.performance = performance
        return report
    finally:
        try:
            session_scope.close()
        except Exception as exc:
            if report is None:
                raise
            message = f"认证会话收尾失败: {type(exc).__name__}"
            report.success = False
            report.errors.append(message)
            report.step_results.append(StepResult(
                action="case.session_finalize", success=False, message=message,
                data={"error": {"type": type(exc).__name__, "message": message}},
            ))
        finally:
            if shared_runtime is not None and runtime is not None:
                close_case_pages = getattr(runtime, "close_case_pages", None)
                if close_case_pages is not None:
                    close_case_pages()
            elif runtime is not None:
                runtime.stop()


def _pause_failed_case(case: DslTestCase, report: ExecutionReport, report_file: Path | None, runtime) -> None:
    failed_index, failed_step = next(
        ((index, step) for index, step in enumerate(report.step_results, start=1) if not step.success),
        (len(report.step_results), report.step_results[-1]),
    )
    step_index = int(failed_step.data.get("step_index") or failed_index)
    error = failed_step.data.get("error") or {}
    message = str(error.get("message") or failed_step.message or (report.errors[0] if report.errors else "用例失败"))
    started_at = _now_iso()
    started_monotonic = time.monotonic()
    _log_progress(
        "failure_pause case={code} name={name} step={step} action={action} error={error} report={report}; "
        "请检查浏览器失败现场，完成后按 Enter、关闭失败页面或关闭浏览器继续清理".format(
            code=case.code,
            name=case.name,
            step=step_index,
            action=failed_step.action,
            error=message,
            report=report_file or "",
        )
    )
    end_signals: queue.Queue[str] = queue.Queue(maxsize=1)

    def _read_stdin() -> None:
        try:
            end_signals.put("enter" if sys.stdin.readline() != "" else "eof")
        except BaseException:
            end_signals.put("eof")

    threading.Thread(target=_read_stdin, name="ydf-browser-failure-pause-stdin", daemon=True).start()
    while True:
        try:
            ended_by = end_signals.get(timeout=0.1)
            break
        except queue.Empty:
            if not runtime.has_open_page():
                ended_by = "browser_closed"
                break
    if ended_by == "eof":
        raise KeyboardInterrupt
    report.timing["failure_pause"] = {
        "case_code": case.code,
        "step_index": step_index,
        "action": failed_step.action,
        "started_at": started_at,
        "ended_at": _now_iso(),
        "duration_ms": _elapsed_ms(started_monotonic),
        "ended_by": ended_by,
    }


def _persistent_profile_enabled(args: argparse.Namespace, fixture_mode: bool) -> bool:
    return not fixture_mode and not bool(getattr(args, "no_persistent_profile", False))


def _env_for_case(env, case: DslTestCase):
    case_env = env.with_user(case.user) if case.user else env
    return case_env


def _reject_deprecated_cli_args(args: argparse.Namespace) -> None:
    if getattr(args, "default_org", None):
        raise ValueError("--default-org 已废弃，请在 DSL 中使用 suite.default_org 或 cases[].default_org")


def _capture_warm_open_menu(runtime, report: ExecutionReport, profile: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if report.menu_target is None:
        return None
    collect = getattr(runtime, "collect_network_summary", None)
    if collect is not None:
        try:
            collect(reset=True)
        except TypeError:
            collect()
        except Exception:
            pass
    started = time.monotonic()
    begin = getattr(runtime, "begin_performance_step", None)
    end = getattr(runtime, "end_performance_step", None)
    try:
        if begin is not None:
            begin({"step_context": "warm", "action": "warm_open_menu"})
        runtime.open_menu(report.menu_target)
        duration_ms = _elapsed_ms(started)
        network = _safe_collect_runtime_network(runtime)
        cold_open_menu_ms = _cold_open_menu_browser_ms(report)
        data: dict[str, Any] = {
            "success": True,
            "cache_mode": _same_case_reopen_cache_mode(profile),
            "duration_ms": duration_ms,
            "cold_open_menu_ms": cold_open_menu_ms,
            "delta_ms": duration_ms - cold_open_menu_ms if cold_open_menu_ms is not None else None,
            "network": network,
        }
        return data
    except Exception as exc:
        return {
            "success": False,
            "cache_mode": _same_case_reopen_cache_mode(profile),
            "duration_ms": _elapsed_ms(started),
            "error": {"type": exc.__class__.__name__, "message": str(exc)},
        }
    finally:
        if end is not None:
            end()


def _case_open_cache_mode(profile: dict[str, Any] | None) -> str:
    mode = _dict_profile_mode(profile)
    if mode == "persistent":
        return "persistent_profile_case_open_menu"
    if mode == "ephemeral":
        return "ephemeral_case_open_menu"
    return "cold_ephemeral"


def _same_case_reopen_cache_mode(profile: dict[str, Any] | None) -> str:
    mode = _dict_profile_mode(profile)
    if mode == "persistent":
        return "persistent_profile_same_case_reopen_menu"
    if mode == "ephemeral":
        return "ephemeral_same_context_reopen_menu"
    return "warm_same_context_open_menu"


def _safe_collect_runtime_network(runtime) -> dict[str, Any]:
    collect = getattr(runtime, "collect_network_summary", None)
    if collect is None:
        return _empty_network_summary()
    try:
        return dict(collect(reset=True) or {})
    except TypeError:
        return dict(collect() or {})
    except Exception:
        return _empty_network_summary()


def _empty_network_summary() -> dict[str, Any]:
    return {
        "network_available": False,
        "request_count": 0,
        "failed_count": 0,
        "api_request_count": 0,
        "static_resource_count": 0,
        "requests": [],
        "top_slow_requests": [],
        "top_slow_api_requests": [],
        "top_slow_static_resources": [],
    }


def _cold_open_menu_browser_ms(report: ExecutionReport) -> int | None:
    for step in report.step_results:
        if step.action != "open_menu":
            continue
        performance = step.data.get("performance") if isinstance(step.data, dict) else None
        if not isinstance(performance, dict):
            continue
        phases = performance.get("phases")
        if isinstance(phases, dict):
            return int(phases.get("browser_open_ms") or performance.get("duration_ms") or 0)
        return int(performance.get("duration_ms") or 0)
    return None


def _suite_report_payload(suite: DslTestSuite, case_reports: list[dict]) -> dict:
    return {
        "success": all(item["success"] for item in case_reports),
        "suite": suite.to_dict(),
        "case_reports": case_reports,
    }


def _case_report_payload(case: DslTestCase, report: ExecutionReport) -> dict:
    return {
        "case": case.to_dict(),
        "success": report.success,
        "report": report.to_dict(),
    }


def _log_suite_start(suite: DslTestSuite, total_cases: int) -> None:
    _log_progress(f"suite={suite.code} name={suite.name} cases={total_cases}")


def _log_case_start(case_index: int, total_cases: int, case: DslTestCase) -> None:
    user = case.user or "默认配置"
    _log_progress(
        f"case={case_index}/{total_cases} code={case.code} name={case.name} "
        f"steps={len(case.steps)} user={user}"
    )


def _log_case_result(case_index: int, total_cases: int, case: DslTestCase, report: ExecutionReport) -> None:
    status = "passed" if report.success else "failed"
    message = f"case={case_index}/{total_cases} code={case.code} result={status}"
    if report.errors:
        message = f"{message} error={str(report.errors[0])[:500]}"
    _log_progress(message)


def _make_step_progress_logger(
    suite: DslTestSuite,
    case: DslTestCase,
    case_index: int,
    total_cases: int,
):
    def _logger(step_index: int, total_steps: int, step) -> None:
        _log_progress(
            f"suite={suite.code} case={case_index}/{total_cases} code={case.code} "
            f"step={step_index}/{total_steps} action={_step_label(step)}"
        )

    return _logger


def _step_label(step) -> str:
    if getattr(step, "kind", "") == "component":
        return f"{step.component}.{step.operation}"
    return str(getattr(step, "action", "") or "unknown")


def _log_progress(message: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[ydf-browser] time={now} {message}", file=sys.stderr, flush=True)


def _print_human_error(message: str) -> None:
    print("[ydf-browser] error:", file=sys.stderr)
    print(message, file=sys.stderr, flush=True)


def _print_json(payload: dict) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


def _login_with_default_org_context(
    env,
    default_org: str | None = None,
    menu_path: str | None = None,
    tenant_name: str | None = None,
    fiscal_year: str | None = None,
):
    timing: dict[str, dict[str, Any]] = {}
    phase = "login"
    phase_started = time.monotonic()
    try:
        authenticator = CasAuthenticator(env)
        session = authenticator.login()
        timing["login"] = {"duration_ms": _elapsed_ms(phase_started), "success": True}
        phase = "context"
        phase_started = time.monotonic()
        tenant_match = TenantContext(env, session).apply(tenant_name)
        match = DefaultOrgContext(env, session).apply(default_org)
        if tenant_match is not None or match is not None:
            session = authenticator.login(existing_session=session)
            UserContextVerifier(env, session).verify(
                expected_tenant_id=tenant_match.tenant_id if tenant_match is not None else "",
                expected_org_id=match.org_id if match is not None else "",
            )
        FiscalYearContext(env, session).apply(fiscal_year)
        timing["context"] = {"duration_ms": _elapsed_ms(phase_started), "success": True}
    except Exception as exc:
        timing[phase] = {
            "duration_ms": _elapsed_ms(phase_started),
            "success": False,
            "error": {"type": exc.__class__.__name__, "message": str(exc)},
        }
        setattr(exc, "_ydf_setup_timing", timing)
        raise
    setattr(session, "_ydf_setup_timing", timing)
    return session


def _resolve_analysis_target(args: argparse.Namespace, gateway: YondifGateway) -> MenuTarget:
    if args.menu_path:
        menu_target = gateway.resolve_menu(args.menu_path)
        if args.service_code:
            menu_target.service_code = args.service_code
        return menu_target
    if not args.service_code:
        raise ValueError("真实分析模式必须提供 menu_path 或 --service-code")
    return MenuTarget(
        menu_code=args.service_code,
        menu_name=args.service_code,
        path=[args.service_code],
        service_code=args.service_code,
    )


if __name__ == "__main__":
    console_main()
