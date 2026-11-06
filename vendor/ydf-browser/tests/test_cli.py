from __future__ import annotations

import json
import multiprocessing
import os
import re
import signal
import subprocess
import sys
import time
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook

import ydf_browser.cli as cli_module
from ydf_browser.bpr_report import SERVER_SUMMARY_FIELDS, extract_server_summary
from ydf_browser.browser_profile import resolve_profile_path
from ydf_browser.cli import main
from ydf_browser.config import EndpointConfig, EnvironmentConfig, UserCredential
from ydf_browser.models import ExecutionReport, StepResult
from ydf_browser.runtime import (
    PlaywrightRuntime,
    build_accessibility_selector,
    build_login_probe_selectors,
    build_menu_open_urls,
    build_service_url,
    should_open_menu_in_new_tab,
)


def _suite_yaml(suite_code: str, case_code: str) -> str:
    return f"""
suite:
  code: {suite_code}
  name: {suite_code}
  tenant: 财政一体化
  default_org: "049002"
cases:
  - code: {case_code}
    name: {case_code}
    user: 默认用户
    steps:
      - action: open_menu
        menu_path: 项目管理>>项目立项
"""


def _cooperative_process(stop_event, ready_event) -> None:
    ready_event.set()
    while not stop_event.wait(0.01):
        pass


def _stubborn_process(_stop_event, ready_event) -> None:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    ready_event.set()
    while True:
        time.sleep(0.05)


def _help_text(capsys, *argv: str) -> str:
    with pytest.raises(SystemExit) as exc_info:
        main([*argv, "--help"])
    assert exc_info.value.code == 0
    return capsys.readouterr().out


def test_cli_help_describes_top_level_commands(capsys) -> None:
    output = _help_text(capsys)

    assert "run" in output
    assert "运行 YAML DSL 测试集" in output
    assert "validate" in output
    assert "校验 YAML DSL" in output
    assert "install-skill" in output
    assert "安装 agent skill" in output


def _write_skill_release(root: Path, marker: Path) -> None:
    (root / "skills" / "gov-ydfdev-browser").mkdir(parents=True)
    (root / "skills" / "gov-ydfdev-browser" / "SKILL.md").write_text("skill\n", encoding="utf-8")
    (root / "VERSION").write_text("0.1.25\n", encoding="utf-8")
    installer = root / "scripts" / "install-skill.sh"
    installer.parent.mkdir(parents=True)
    installer.write_text(f'#!/usr/bin/env sh\nprintf "%s\\n" "$*" > "{marker}"\n', encoding="utf-8")
    installer.chmod(0o755)


@pytest.mark.parametrize("anchor", ["source", "runtime"])
def test_cli_install_skill_delegates_to_bundled_platform_installer(
    tmp_path: Path,
    monkeypatch,
    anchor: str,
) -> None:
    release = tmp_path / "release"
    marker = tmp_path / "installer-args.txt"
    _write_skill_release(release, marker)
    if anchor == "source":
        monkeypatch.setattr(cli_module, "__file__", str(release / "ydf_browser" / "cli.py"))
        monkeypatch.setattr(cli_module.sys, "executable", str(tmp_path / "standalone" / "python"))
    else:
        monkeypatch.setattr(cli_module, "__file__", str(tmp_path / "standalone" / "ydf_browser" / "cli.py"))
        monkeypatch.setattr(cli_module.sys, "executable", str(release / "runtime" / ".venv" / "bin" / "python"))

    assert main(["install-skill"]) == 0
    assert marker.read_text(encoding="utf-8") == "all\n"


def test_cli_install_skill_fails_without_a_bundled_skill(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    monkeypatch.setattr(cli_module, "__file__", str(tmp_path / "site-packages" / "ydf_browser" / "cli.py"))
    monkeypatch.setattr(cli_module.sys, "executable", str(tmp_path / "venv" / "bin" / "python"))

    assert main(["install-skill"]) == 1
    output = capsys.readouterr()
    assert "找不到当前 runtime 内置的 gov-ydfdev-browser skill" in output.err
    assert not (tmp_path / "agents").exists()


def test_cli_run_help_describes_constraints_and_reports(capsys) -> None:
    output = _help_text(capsys, "run")
    normalized_output = " ".join(output.split())

    assert "--dsl-list" in output
    assert "严格串行" in output
    assert "--concurrency" in output
    assert "持久化 profile" in output
    assert "--pause-on-failure" in output
    assert "--ai-observe" in output
    assert "--report-file" in output
    assert "events.jsonl" in output
    assert "headless 默认 1440x900，显式值优先" in normalized_output


def test_cli_nested_help_describes_options_and_unsupported_profile_cleanup(capsys) -> None:
    validate_output = _help_text(capsys, "validate")
    profile_output = _help_text(capsys, "profile", "clear")

    assert "--dsl" in validate_output
    assert "待校验" in validate_output
    assert "清空整个持久化 profile" in profile_output
    assert "当前不支持局部清理" in profile_output


def test_cli_without_args_prints_top_level_help_and_returns_zero(capsys, monkeypatch) -> None:
    monkeypatch.setattr(cli_module, "ConfigLoader", lambda *_args, **_kwargs: pytest.fail("不应读取配置"))

    exit_code = main([])
    no_args = capsys.readouterr()

    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    explicit_help = capsys.readouterr()

    assert exit_code == 0
    assert no_args.out == explicit_help.out
    assert no_args.err == ""


def test_cli_incomplete_commands_remain_parse_errors(capsys) -> None:
    with pytest.raises(SystemExit) as unknown_info:
        main(["unknown"])
    unknown_error = capsys.readouterr()

    with pytest.raises(SystemExit) as incomplete_info:
        main(["menu"])
    incomplete_error = capsys.readouterr()

    assert unknown_info.value.code == 2
    assert "invalid choice" in unknown_error.err
    assert incomplete_info.value.code == 2
    assert "menu_command" in incomplete_error.err


def test_cli_template_fetch_prints_manifest_json(tmp_path, capsys, sample_template_payload: dict) -> None:
    template_path = tmp_path / "template.json"
    template_path.write_text(json.dumps(sample_template_payload, ensure_ascii=False), encoding="utf-8")

    exit_code = main(["template", "fetch", str(template_path)])

    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["success"] is True
    assert data["manifest"]["page"]["biz_obj_code"] == "pmProjectInfo"


def test_cli_run_executes_workflow_with_fixture_inputs(
    tmp_path,
    capsys,
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
    sample_dsl_path,
) -> None:
    template_path = tmp_path / "template.json"
    runtime_path = tmp_path / "runtime.json"
    template_path.write_text(json.dumps(sample_template_payload, ensure_ascii=False), encoding="utf-8")
    runtime_path.write_text(json.dumps(sample_runtime_elements, ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "run",
            "--dsl",
            str(sample_dsl_path),
            "--template-file",
            str(template_path),
            "--runtime-file",
            str(runtime_path),
            "--menu-path",
            "项目管理>>项目立项",
        ]
    )

    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    report = json.loads(Path(data["report_file"]).read_text(encoding="utf-8"))
    assert data["success"] is True
    assert report["suite_reports"][0]["case_reports"][0]["report"]["step_results"][-1]["success"] is True


def test_cli_ai_observe_adds_contract_metadata_without_changing_normal_report(
    tmp_path,
    capsys,
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
    sample_dsl_path,
) -> None:
    template_path = tmp_path / "template.json"
    runtime_path = tmp_path / "runtime.json"
    template_path.write_text(json.dumps(sample_template_payload, ensure_ascii=False), encoding="utf-8")
    runtime_path.write_text(json.dumps(sample_runtime_elements, ensure_ascii=False), encoding="utf-8")

    normal_report = tmp_path / "normal" / "report.json"
    normal_exit = main(
        [
            "run",
            "--dsl",
            str(sample_dsl_path),
            "--template-file",
            str(template_path),
            "--runtime-file",
            str(runtime_path),
            "--menu-path",
            "项目管理>>项目立项",
            "--report-file",
            str(normal_report),
        ]
    )
    capsys.readouterr()

    ai_report = tmp_path / "ai" / "report.json"
    ai_exit = main(
        [
            "run",
            "--ai-observe",
            "--dsl",
            str(sample_dsl_path),
            "--template-file",
            str(template_path),
            "--runtime-file",
            str(runtime_path),
            "--menu-path",
            "项目管理>>项目立项",
            "--report-file",
            str(ai_report),
        ]
    )
    capsys.readouterr()

    assert normal_exit == 0
    assert ai_exit == 0
    normal = json.loads(normal_report.read_text(encoding="utf-8"))
    ai = json.loads(ai_report.read_text(encoding="utf-8"))
    normal_step = normal["suite_reports"][0]["case_reports"][0]["report"]["step_results"][0]
    ai_step = ai["suite_reports"][0]["case_reports"][0]["report"]["step_results"][0]
    assert "contract_version" not in normal["run"]
    assert "worker_process" not in normal["run"]
    assert "observation" not in normal_step
    assert ai["run"]["contract_version"] == "1.3"
    assert ai["run"]["verification"] == {
        "entrypoint": "direct_cli",
        "verification_eligible": False,
        "status": "not_evaluated",
        "reason_code": "skill_helper_required",
    }
    assert ai["run"]["worker_process"]["pid"] != os.getpid()
    assert ai["run"]["worker_process"]["parent_pid"] == os.getpid()
    assert "business_assertion_receipts" in ai["run"]["capabilities"]["enabled"]
    assert "notification_request_associations" in ai["run"]["capabilities"]["enabled"]
    assert "verification_entrypoint" in ai["run"]["capabilities"]["enabled"]
    assert ai_step["observation"]["outcome"] == "passed"


def test_cli_ai_observe_emits_semantic_execution_order(
    tmp_path,
    capsys,
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    dsl_path = tmp_path / "suite.yaml"
    template_path = tmp_path / "template.json"
    runtime_path = tmp_path / "runtime.json"
    report_file = tmp_path / "run" / "report.json"
    dsl_path.write_text(_suite_yaml("semantic-events", "open-menu"), encoding="utf-8")
    template_path.write_text(json.dumps(sample_template_payload, ensure_ascii=False), encoding="utf-8")
    runtime_path.write_text(json.dumps(sample_runtime_elements, ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "run",
            "--ai-observe",
            "--dsl",
            str(dsl_path),
            "--template-file",
            str(template_path),
            "--runtime-file",
            str(runtime_path),
            "--menu-path",
            "项目管理>>项目立项",
            "--report-file",
            str(report_file),
        ]
    )

    assert exit_code == 0
    capsys.readouterr()
    events = [json.loads(line) for line in (report_file.parent / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [item["event"] for item in events] == [
        "run_started",
        "suite_started",
        "case_started",
        "step_started",
        "phase_started",
        "phase_completed",
        "step_completed",
        "case_completed",
        "suite_completed",
        "run_completed",
    ]


def test_cli_ai_observe_terminates_run_on_step_timeout(
    tmp_path,
    capsys,
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    dsl_path = tmp_path / "timeout.yaml"
    template_path = tmp_path / "template.json"
    runtime_path = tmp_path / "runtime.json"
    report_file = tmp_path / "run" / "report.json"
    dsl_path.write_text(
        """
suite:
  code: timeout
  name: 超时
  tenant: 财政一体化
  default_org: "049002"
cases:
  - code: slow-step
    name: 慢步骤
    user: 默认用户
    steps:
      - action: open_menu
        menu_path: 项目管理>>项目立项
      - component: form
        operation: fill
        target:
          fields:
            项目名称: value
""",
        encoding="utf-8",
    )
    template_path.write_text(json.dumps(sample_template_payload, ensure_ascii=False), encoding="utf-8")
    runtime_path.write_text(
        json.dumps(
            [item for item in sample_runtime_elements if item.get("fieldid") != "project_name"],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    started = time.monotonic()
    exit_code = main(
        [
            "run",
            "--ai-observe",
            "--step-timeout-seconds",
            "1",
            "--case-timeout-seconds",
            "3",
            "--run-timeout-seconds",
            "5",
            "--dsl",
            str(dsl_path),
            "--template-file",
            str(template_path),
            "--runtime-file",
            str(runtime_path),
            "--menu-path",
            "项目管理>>项目立项",
            "--report-file",
            str(report_file),
        ]
    )

    assert exit_code == 1
    assert time.monotonic() - started < 4
    capsys.readouterr()
    report = json.loads(report_file.read_text(encoding="utf-8"))
    assert report["run"]["observation"] == {
        "outcome": "terminated",
        "reason_code": "timeout",
        "operation_reason": "step_timeout",
    }
    assert report["run"]["worker_process"]["termination"] in {"cooperative", "terminated", "killed"}
    events = [json.loads(line) for line in (report_file.parent / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(item["event"] == "step_timed_out" for item in events)


@pytest.mark.parametrize(
    ("run_deadline", "case_deadline", "step_deadline", "expected"),
    [
        (20.0, 15.0, 11.0, "step_timeout"),
        (20.0, 11.0, None, "case_timeout"),
        (11.0, None, None, "run_timeout"),
        (20.0, 15.0, 12.0, None),
    ],
)
def test_expired_timeout_reason_uses_first_active_deadline(
    run_deadline: float,
    case_deadline: float | None,
    step_deadline: float | None,
    expected: str | None,
) -> None:
    assert (
        cli_module._expired_timeout_reason(
            11.0,
            run_deadline=run_deadline,
            case_deadline=case_deadline,
            step_deadline=step_deadline,
        )
        == expected
    )


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        (_cooperative_process, "cooperative"),
        (_stubborn_process, "killed"),
    ],
)
def test_request_worker_stop_escalates_only_when_needed(target, expected: str) -> None:
    context = multiprocessing.get_context("spawn")
    stop_event = context.Event()
    ready_event = context.Event()
    process = context.Process(target=target, args=(stop_event, ready_event))
    process.start()
    assert ready_event.wait(5)

    mode = cli_module._request_worker_stop(process, stop_event, grace_seconds=0.2)

    assert mode == expected
    assert stop_event.is_set()
    assert process.is_alive() is False


def test_cli_run_rejects_deprecated_default_org_argument(tmp_path, capsys, sample_dsl_path) -> None:
    exit_code = main(["run", "--dsl", str(sample_dsl_path), "--default-org", "049002"])

    assert exit_code == 1
    data = json.loads(capsys.readouterr().out)
    assert data["success"] is False
    assert "--default-org 已废弃" in data["error"]


def test_resolve_profile_path_uses_default_home(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("YDF_BROWSER_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("YDF_BROWSER_PROFILE_DIR", raising=False)

    assert resolve_profile_path() == tmp_path / "home" / "browser-profile" / "default"


def test_resolve_profile_path_prefers_profile_dir_override(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("YDF_BROWSER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("YDF_BROWSER_PROFILE_DIR", str(tmp_path / "custom-profile"))

    assert resolve_profile_path() == tmp_path / "custom-profile"


def test_cli_profile_clear_deletes_default_profile(tmp_path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("YDF_BROWSER_HOME", str(tmp_path / "home"))
    profile_dir = tmp_path / "home" / "browser-profile" / "default"
    (profile_dir / "Cache").mkdir(parents=True)
    (profile_dir / "Cache" / "entry").write_text("cached", encoding="utf-8")

    exit_code = main(["profile", "clear"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is True
    assert payload["profile"]["mode"] == "persistent"
    assert payload["profile"]["path"] == str(profile_dir)
    assert not profile_dir.exists()


def test_cli_profile_clear_rejects_locked_profile(tmp_path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("YDF_BROWSER_HOME", str(tmp_path / "home"))
    profile_dir = tmp_path / "home" / "browser-profile" / "default"
    profile_dir.mkdir(parents=True)
    (profile_dir / "SingletonLock").write_text("locked", encoding="utf-8")

    exit_code = main(["profile", "clear"])

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert "正在使用" in payload["error"]


def test_cli_profile_clear_rejects_cookie_only_mode(capsys) -> None:
    exit_code = main(["profile", "clear", "--cookies"])

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False


def test_cli_run_uses_persistent_profile_by_default(tmp_path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("YDF_BROWSER_HOME", str(tmp_path / "home"))
    dsl_path = tmp_path / "suite.yaml"
    dsl_path.write_text(_suite_yaml("profile", "case-a"), encoding="utf-8")
    base_env = EnvironmentConfig(
        env_name="ydf",
        base_url="https://example.yonyougov.top",
        sysid="yonbip",
        username="demo",
        password="secret",
        users={"默认用户": UserCredential(username="demo", password="secret")},
    )
    menu_target = cli_module.MenuTarget(
        menu_code="PM_INIT",
        menu_name="项目立项",
        path=["项目管理", "项目立项"],
        service_code="global00_-1_PM_INIT",
    )
    events: list[str] = []
    runtime_profile_dirs: list[object] = []

    class _ConfigLoader:
        def __init__(self, _path=None) -> None:
            pass

        def get_env(self, _name):
            return base_env

    class _Gateway:
        def __init__(self, env, session) -> None:
            self.env = env
            self.session = session

    class _Runtime:
        def __init__(self, env, session, headless=False, profile_dir=None, **_kwargs) -> None:
            self.env = env
            self.session = session
            self.profile_dir = profile_dir
            runtime_profile_dirs.append(profile_dir)

        def start(self) -> None:
            events.append("start")

        def clear_visible_cookies(self, base_url: str) -> None:
            events.append(f"clear:{base_url}")

        def open_menu(self, target) -> None:
            events.append(f"open:{target.menu_name}")

        def close_case_pages(self) -> None:
            events.append("close_case_pages")

        def stop(self) -> None:
            events.append("stop")

    class _Executor:
        def __init__(self, gateway, runtime, progress_logger=None, performance_enabled=False, **_kwargs) -> None:
            self.runtime = runtime

        def run(self, _steps):
            self.runtime.open_menu(menu_target)
            return ExecutionReport(success=True, menu_target=menu_target)

    def _login(*_args, **_kwargs):
        events.append("login")
        return SimpleNamespace(cookies=[])

    monkeypatch.setattr(cli_module, "ConfigLoader", _ConfigLoader)
    monkeypatch.setattr(cli_module, "_login_with_default_org_context", _login)
    _stub_session_reuse(monkeypatch)
    monkeypatch.setattr(cli_module, "YondifGateway", _Gateway)
    monkeypatch.setattr(cli_module, "PlaywrightRuntime", _Runtime)
    monkeypatch.setattr(cli_module, "WorkflowExecutor", _Executor)

    exit_code = main(["run", "--dsl", str(dsl_path), "--headless"])

    assert exit_code == 0
    profile_dir = tmp_path / "home" / "browser-profile" / "default"
    assert runtime_profile_dirs == [profile_dir]
    assert "clear:https://example.yonyougov.top" not in events
    assert events.index("start") < events.index("login")
    assert events[-2:] == ["close_case_pages", "stop"]
    summary = json.loads(capsys.readouterr().out)
    report = json.loads(Path(summary["report_file"]).read_text(encoding="utf-8"))
    assert report["run"]["profile"] == {
        "mode": "persistent",
        "path": str(profile_dir),
        "cookies_reset": "restore_authenticated_session",
    }


def test_cli_run_no_persistent_profile_uses_ephemeral_case_runtime(tmp_path, capsys, monkeypatch) -> None:
    dsl_path = tmp_path / "suite.yaml"
    dsl_path.write_text(_suite_yaml("profile", "case-a"), encoding="utf-8")
    base_env = EnvironmentConfig(
        env_name="ydf",
        base_url="https://example.yonyougov.top",
        sysid="yonbip",
        username="demo",
        password="secret",
        users={"默认用户": UserCredential(username="demo", password="secret")},
    )
    runtime_profile_dirs: list[object] = []

    class _ConfigLoader:
        def __init__(self, _path=None) -> None:
            pass

        def get_env(self, _name):
            return base_env

    class _Runtime:
        def __init__(self, env, session, headless=False, profile_dir=None, **_kwargs) -> None:
            runtime_profile_dirs.append(profile_dir)

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

    monkeypatch.setattr(cli_module, "ConfigLoader", _ConfigLoader)
    monkeypatch.setattr(cli_module, "_login_with_default_org_context", lambda *_args, **_kwargs: SimpleNamespace(cookies=[]))
    _stub_session_reuse(monkeypatch)
    monkeypatch.setattr(cli_module, "YondifGateway", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(cli_module, "PlaywrightRuntime", _Runtime)
    monkeypatch.setattr(cli_module, "WorkflowExecutor", lambda **_kwargs: SimpleNamespace(run=lambda _steps: ExecutionReport(success=True)))

    exit_code = main(["run", "--dsl", str(dsl_path), "--no-persistent-profile", "--headless"])

    assert exit_code == 0
    assert runtime_profile_dirs == [None]
    summary = json.loads(capsys.readouterr().out)
    report = json.loads(Path(summary["report_file"]).read_text(encoding="utf-8"))
    assert report["run"]["profile"] == {"mode": "ephemeral", "path": None, "cookies_reset": "not_applicable"}


def test_cli_run_without_dsl_starts_manual_session_and_keeps_forwarding(tmp_path, capsys, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    base_env = EnvironmentConfig(
        env_name="ydf",
        base_url="https://example.yonyougov.top",
        sysid="yonbip",
        username="demo",
        password="secret",
    )
    events: list[str] = []
    runtime_rules: list[list[dict[str, object]]] = []
    runtime_profiles: list[object] = []

    class _ConfigLoader:
        def __init__(self, _path=None) -> None:
            pass

        def get_env(self, _name):
            return base_env

    class _Runtime:
        def __init__(self, env, session, headless=False, request_forward_rules=None, profile_dir=None) -> None:
            assert env is base_env
            assert session.cookies == []
            assert headless is False
            runtime_rules.append([rule.to_dict() for rule in request_forward_rules or []])
            runtime_profiles.append(profile_dir)

        def start(self) -> None:
            events.append("start")

        def clear_visible_cookies(self, base_url: str) -> None:
            raise AssertionError("ephemeral manual session must not clear persistent cookies")

        def open_home(self) -> None:
            events.append("open_home")

        def wait_for_manual_session(self) -> str:
            events.append("wait")
            return "browser_closed"

        def stop(self) -> None:
            events.append("stop")

    def _login(*_args, **_kwargs):
        events.append("login")
        return SimpleNamespace(cookies=[])

    monkeypatch.setattr(cli_module, "ConfigLoader", _ConfigLoader)
    monkeypatch.setattr(cli_module, "_login_with_default_org_context", _login)
    _stub_session_reuse(monkeypatch)
    monkeypatch.setattr(cli_module, "PlaywrightRuntime", _Runtime)

    exit_code = main(
        [
            "run",
            "--no-persistent-profile",
            "--forward-strip-prefix",
            "/fbdi-be/**=http://127.0.0.1:62871",
        ]
    )

    assert exit_code == 0
    assert events == ["login", "start", "open_home", "wait", "stop"]
    assert runtime_profiles == [None]
    assert runtime_rules == [
        [{"pattern": "/fbdi-be/**", "target": "http://127.0.0.1:62871", "strip_prefix": True}]
    ]
    assert json.loads(capsys.readouterr().out) == {
        "success": True,
        "mode": "manual_browser_session",
        "exit_reason": "browser_closed",
    }
    assert list(tmp_path.iterdir()) == []


def test_cli_run_without_dsl_preserves_profile_before_session_restore(tmp_path, capsys, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("YDF_BROWSER_HOME", str(tmp_path / "home"))
    base_env = EnvironmentConfig(
        env_name="ydf",
        base_url="https://example.yonyougov.top",
        sysid="yonbip",
        username="demo",
        password="secret",
    )
    events: list[str] = []
    runtime_profiles: list[object] = []

    class _ConfigLoader:
        def __init__(self, _path=None) -> None:
            pass

        def get_env(self, _name):
            return base_env

    class _Runtime:
        def __init__(self, _env, _session, profile_dir=None, **_kwargs) -> None:
            runtime_profiles.append(profile_dir)

        def start(self) -> None:
            events.append("start")

        def clear_visible_cookies(self, base_url: str) -> None:
            assert base_url == base_env.base_url
            events.append("clear")

        def open_home(self) -> None:
            events.append("open_home")

        def wait_for_manual_session(self) -> str:
            events.append("wait")
            return "browser_closed"

        def stop(self) -> None:
            events.append("stop")

    def _login(*_args, **_kwargs):
        events.append("login")
        return SimpleNamespace(cookies=[])

    monkeypatch.setattr(cli_module, "ConfigLoader", _ConfigLoader)
    monkeypatch.setattr(cli_module, "_login_with_default_org_context", _login)
    _stub_session_reuse(monkeypatch)
    monkeypatch.setattr(cli_module, "PlaywrightRuntime", _Runtime)

    assert main(["run"]) == 0
    capsys.readouterr()

    assert events == ["start", "login", "open_home", "wait", "stop"]
    assert runtime_profiles == [tmp_path / "home" / "browser-profile" / "default"]


@pytest.mark.parametrize(
    "options",
    [
        ["--headless"],
        ["--pause-on-failure"],
        ["--case", "case-a"],
        ["--vars-file", "vars.yaml"],
        ["--template-file", "template.json"],
        ["--report-file", "report.json"],
        ["--concurrency", "1"],
        ["--report-dir", "reports"],
        ["--performance"],
        ["--ai-observe"],
    ],
)
def test_cli_run_without_dsl_rejects_options_without_manual_semantics(tmp_path, capsys, options) -> None:
    exit_code = main(["run", *options])

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert "手工浏览器会话" in payload["error"]
    assert list(tmp_path.iterdir()) == []


def test_cli_run_without_dsl_returns_user_interrupt(tmp_path, capsys, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    base_env = EnvironmentConfig(
        env_name="ydf",
        base_url="https://example.yonyougov.top",
        sysid="yonbip",
        username="demo",
        password="secret",
    )
    events: list[str] = []

    class _ConfigLoader:
        def __init__(self, _path=None) -> None:
            pass

        def get_env(self, _name):
            return base_env

    class _Runtime:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def start(self) -> None:
            events.append("start")

        def open_home(self) -> None:
            events.append("open_home")

        def wait_for_manual_session(self) -> str:
            raise KeyboardInterrupt

        def stop(self) -> None:
            events.append("stop")

    monkeypatch.setattr(cli_module, "ConfigLoader", _ConfigLoader)
    monkeypatch.setattr(cli_module, "_login_with_default_org_context", lambda *_args, **_kwargs: SimpleNamespace(cookies=[]))
    _stub_session_reuse(monkeypatch)
    monkeypatch.setattr(cli_module, "PlaywrightRuntime", _Runtime)

    assert main(["run"]) == 130
    assert events == ["start", "open_home", "stop"]
    assert json.loads(capsys.readouterr().out) == {
        "success": False,
        "mode": "manual_browser_session",
        "exit_reason": "user_interrupt",
    }


def test_cli_run_rejects_concurrency_with_persistent_profile(tmp_path, capsys, monkeypatch) -> None:
    dsl_path = tmp_path / "suite.yaml"
    dsl_path.write_text(_suite_yaml("profile", "case-a"), encoding="utf-8")
    base_env = EnvironmentConfig(env_name="ydf", base_url="https://example.yonyougov.top", sysid="yonbip", username="demo", password="secret")

    class _ConfigLoader:
        def __init__(self, _path=None) -> None:
            pass

        def get_env(self, _name):
            return base_env

    monkeypatch.setattr(cli_module, "ConfigLoader", _ConfigLoader)

    exit_code = main(["run", "--dsl", str(dsl_path), "--concurrency", "2"])

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert "持久化浏览器 profile 模式不支持并发" in payload["error"]


def test_cli_run_performance_flag_records_fixture_performance(
    tmp_path,
    capsys,
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
    sample_dsl_path,
) -> None:
    template_path = tmp_path / "template.json"
    runtime_path = tmp_path / "runtime.json"
    template_path.write_text(json.dumps(sample_template_payload, ensure_ascii=False), encoding="utf-8")
    runtime_path.write_text(json.dumps(sample_runtime_elements, ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "run",
            "--performance",
            "--dsl",
            str(sample_dsl_path),
            "--template-file",
            str(template_path),
            "--runtime-file",
            str(runtime_path),
            "--menu-path",
            "项目管理>>项目立项",
        ]
    )

    assert exit_code == 0
    summary = json.loads(capsys.readouterr().out)
    report = json.loads(Path(summary["report_file"]).read_text(encoding="utf-8"))
    run_performance = report["run"]["performance"]
    case_performance = report["suite_reports"][0]["case_reports"][0]["performance"]
    first_step = report["suite_reports"][0]["case_reports"][0]["report"]["step_results"][0]
    assert run_performance["enabled"] is True
    assert run_performance["cache_modes"] == ["cold_ephemeral", "warm_same_context_open_menu"]
    assert case_performance["network_available"] is False
    assert first_step["data"]["performance"]["duration_ms"] >= 0
    assert "performance_file" in summary
    assert Path(summary["performance_file"]).is_file()
    assert report["performance_file"] == summary["performance_file"]
    assert report["run"]["performance"]["file"] == summary["performance_file"]


def test_cli_run_suite_logs_suite_case_and_step_progress(
    tmp_path,
    capsys,
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    dsl_path = tmp_path / "suite.yaml"
    template_path = tmp_path / "template.json"
    runtime_path = tmp_path / "runtime.json"
    dsl_path.write_text(
        """
suite:
  code: smoke
  name: 冒烟测试集
  description: 验证进度日志
  tenant: 财政一体化
  default_org: "049002"
cases:
  - code: case-a
    name: 用例 A
    user: 默认用户
    steps:
      - action: open_menu
        menu_path: 项目管理>>项目立项
  - code: case-b
    name: 用例 B
    user: 默认用户
    steps:
      - action: open_menu
        menu_path: 项目管理>>项目立项
""",
        encoding="utf-8",
    )
    template_path.write_text(json.dumps(sample_template_payload, ensure_ascii=False), encoding="utf-8")
    runtime_path.write_text(json.dumps(sample_runtime_elements, ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "run",
            "--dsl",
            str(dsl_path),
            "--template-file",
            str(template_path),
            "--runtime-file",
            str(runtime_path),
            "--menu-path",
            "项目管理>>项目立项",
        ]
    )

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert exit_code == 0
    assert data["success"] is True
    assert re.search(r"\[ydf-browser\] time=\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} suite=smoke name=冒烟测试集 cases=2", captured.err)
    assert "case=1/2 code=case-a name=用例 A steps=1 user=默认用户" in captured.err
    assert "case=2/2 code=case-b name=用例 B steps=1 user=默认用户" in captured.err
    assert "suite=smoke case=1/2 code=case-a step=1/1 action=open_menu" in captured.err
    assert "suite=smoke case=2/2 code=case-b step=1/1 action=open_menu" in captured.err


def test_cli_run_single_steps_logs_case_and_step_progress(
    tmp_path,
    capsys,
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
    sample_dsl_path,
) -> None:
    template_path = tmp_path / "template.json"
    runtime_path = tmp_path / "runtime.json"
    template_path.write_text(json.dumps(sample_template_payload, ensure_ascii=False), encoding="utf-8")
    runtime_path.write_text(json.dumps(sample_runtime_elements, ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "run",
            "--dsl",
            str(sample_dsl_path),
            "--template-file",
            str(template_path),
            "--runtime-file",
            str(runtime_path),
            "--menu-path",
            "项目管理>>项目立项",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "suite=sample name=样例测试集 cases=1" in captured.err
    assert "case=1/1 code=sample-case name=样例用例 steps=2 user=默认用户" in captured.err
    assert "suite=sample case=1/1 code=sample-case step=1/2 action=open_menu" in captured.err
    assert "suite=sample case=1/1 code=sample-case step=2/2 action=toolbar.click" in captured.err


def test_cli_run_single_steps_logs_failure_summary_and_keeps_json_errors(
    tmp_path,
    capsys,
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    dsl_path = tmp_path / "workflow.yaml"
    template_path = tmp_path / "template.json"
    runtime_path = tmp_path / "runtime.json"
    dsl_path.write_text(
        """
suite:
  code: failure
  name: 失败测试集
  tenant: 财政一体化
  default_org: "049002"
cases:
  - code: fail-case
    name: 失败用例
    user: 默认用户
    steps:
      - action: open_menu
        menu_path: 项目管理>>项目立项
      - component: table
        operation: assert_column_values
        target:
          column: 金额
          equals: Codex
""",
        encoding="utf-8",
    )
    template_path.write_text(json.dumps(sample_template_payload, ensure_ascii=False), encoding="utf-8")
    runtime_path.write_text(
        json.dumps(
            [*sample_runtime_elements, {"fieldid": "main_table", "visible": True}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "run",
            "--dsl",
            str(dsl_path),
            "--template-file",
            str(template_path),
            "--runtime-file",
            str(runtime_path),
            "--menu-path",
            "项目管理>>项目立项",
        ]
    )

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    report = json.loads(Path(data["report_file"]).read_text(encoding="utf-8"))
    assert exit_code == 1
    assert data["success"] is False
    assert "表格列无可验证数据" in report["suite_reports"][0]["case_reports"][0]["report"]["errors"][0]
    assert "表格列无可验证数据" in data["first_failure"]["message"]
    assert "result=failed" in captured.err
    assert "error=表格列无可验证数据" in captured.err


def test_cli_run_rejects_invalid_dsl_before_execution(
    tmp_path,
    capsys,
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    dsl_path = tmp_path / "invalid.yaml"
    template_path = tmp_path / "template.json"
    runtime_path = tmp_path / "runtime.json"
    report_file = tmp_path / "report.json"
    html_report_file = report_file.with_suffix(".html")
    dsl_path.write_text(
        """
suite:
  code: invalid
  name: 非法 DSL
cases:
  - code: bad-assert
    name: 缺少 fields
    steps:
      - action: open_menu
        menu_path: 项目管理>>项目立项
      - component: table
        operation: assert_row_values
        target:
          match:
            column: 支出范围说明
            equals: xftest1
""",
        encoding="utf-8",
    )
    template_path.write_text(json.dumps(sample_template_payload, ensure_ascii=False), encoding="utf-8")
    runtime_path.write_text(json.dumps(sample_runtime_elements, ensure_ascii=False), encoding="utf-8")
    report_file.write_text('{"success": true, "totals": {"passed": 1}}', encoding="utf-8")
    html_report_file.write_text("通过", encoding="utf-8")

    exit_code = main(
        [
            "run",
            "--dsl",
            str(dsl_path),
            "--template-file",
            str(template_path),
            "--runtime-file",
            str(runtime_path),
            "--menu-path",
            "项目管理>>项目立项",
            "--report-file",
            str(report_file),
        ]
    )

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert exit_code == 1
    assert data["success"] is False
    assert "DSL 语法校验失败" in data["error"]
    assert "table.assert_row_values 缺少 target.fields" in data["error"]
    assert "DSL 语法校验失败:\n- cases[1].steps[2]" in captured.err
    assert "正确写法示例:\n  - component: table\n    operation: assert_row_values" in captured.err
    assert data["report_file"] == str(report_file)
    report = json.loads(report_file.read_text(encoding="utf-8"))
    assert report["success"] is False
    assert report["totals"]["failed"] == 1
    assert report["suite_reports"][0]["case_reports"][0]["status"] == "failed"
    html = html_report_file.read_text(encoding="utf-8")
    assert "未通过" in html
    assert "DSL 语法校验失败" in html
    assert "suite=invalid" not in captured.err


def test_cli_ai_observe_starts_contract_before_dsl_validation(tmp_path, capsys) -> None:
    dsl_path = tmp_path / "invalid.yaml"
    report_file = tmp_path / "report.json"
    dsl_path.write_text("steps:\n  - action: open_menu\n", encoding="utf-8")

    exit_code = main(
        [
            "run",
            "--ai-observe",
            "--dsl",
            str(dsl_path),
            "--template-file",
            "must-not-be-read-template.json",
            "--runtime-file",
            "must-not-be-read-runtime.json",
            "--report-file",
            str(report_file),
        ]
    )

    assert exit_code == 1
    summary = json.loads(capsys.readouterr().out)
    assert summary["success"] is False
    report = json.loads(report_file.read_text(encoding="utf-8"))
    assert report["run"]["observation"]["outcome"] == "blocked"
    assert report["run"]["observation"]["reason_code"] == "dsl_invalid"
    events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert events[0]["event"] == "run_started"
    assert events[0]["contract_version"] == "1.3"
    assert "network_text_bodies" in events[0]["capabilities"]["enabled"]
    assert events[0]["configuration"] == {
        "ai_observe": True,
        "concurrency": 1,
        "step_timeout_seconds": 120,
        "case_timeout_seconds": 900,
        "run_timeout_seconds": 1800,
        "max_network_body_bytes": 10 * 1024 * 1024,
        "max_network_case_bytes": 200 * 1024 * 1024,
    }


def test_cli_run_resolves_variables_from_env_file_vars_file_and_cli_override(
    tmp_path,
    capsys,
    monkeypatch,
) -> None:
    config_path = tmp_path / "env.yaml"
    vars_path = tmp_path / "vars.yaml"
    dsl_path = tmp_path / "suite.yaml"
    template_path = tmp_path / "template.json"
    runtime_path = tmp_path / "runtime.json"
    config_path.write_text(
        """
environments:
  ydf:
    base_url: https://example.yonyougov.top
    sysid: yonbip
    username: default-user
    password: default-password
    variables:
      user_alias: 配置用户
      default_org: "049002"
      budget:
        indicator_code: CONFIG-CODE
      run_id: CONFIG-RUN
""",
        encoding="utf-8",
    )
    vars_path.write_text(
        """
variables:
  user_alias: 文件用户
  budget:
    indicator_code: FILE-CODE
  run_id: FILE-RUN
""",
        encoding="utf-8",
    )
    dsl_path.write_text(
        """
suite:
  code: budget
  name: 预算指标
  tenant: 财政一体化
cases:
  - code: query-budget
    name: 查询预算指标
    user: "{{user_alias}}"
    default_org: "{{default_org}}"
    steps:
      - action: open_menu
        menu_path: 预算管理>>指标查询
      - component: query
        operation: search
        target:
          conditions:
            - field: 预算指标编码
              equals: "{{budget.indicator_code}}"
            - field: 运行批次
              equals: "{{run_id}}"
""",
        encoding="utf-8",
    )
    template_path.write_text("{}", encoding="utf-8")
    runtime_path.write_text("[]", encoding="utf-8")
    captured_steps: list[list[dict]] = []

    class _Executor:
        def __init__(self, gateway, runtime, progress_logger=None, **_kwargs) -> None:
            self.gateway = gateway
            self.runtime = runtime
            self.progress_logger = progress_logger

        def run(self, steps):
            step_payload = [step.to_dict() for step in steps]
            captured_steps.append(step_payload)
            return ExecutionReport(
                success=True,
                step_results=[
                    StepResult(action="capture", success=True, message="ok", data={"steps": step_payload})
                ],
            )

    monkeypatch.setattr(cli_module, "WorkflowExecutor", _Executor)

    exit_code = main(
        [
            "run",
            "--dsl",
            str(dsl_path),
            "--config",
            str(config_path),
            "--vars-file",
            str(vars_path),
            "--var",
            "user_alias=命令行用户",
            "--var",
            "budget.indicator_code=CLI-CODE",
            "--template-file",
            str(template_path),
            "--runtime-file",
            str(runtime_path),
            "--menu-path",
            "预算管理>>指标查询",
        ]
    )

    data = json.loads(capsys.readouterr().out)
    report = json.loads(Path(data["report_file"]).read_text(encoding="utf-8"))
    case_payload = report["suite_reports"][0]["case_reports"][0]["case"]
    assert exit_code == 0
    assert case_payload["user"] == "命令行用户"
    assert case_payload["default_org"] == "049002"
    assert captured_steps[0][1]["target"]["conditions"] == [
        {"field": "预算指标编码", "equals": "CLI-CODE"},
        {"field": "运行批次", "equals": "FILE-RUN"},
    ]


def test_cli_run_directory_filters_case_writes_report_and_prints_small_summary(
    tmp_path,
    capsys,
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    dsl_dir = tmp_path / "dsl"
    report_dir = tmp_path / "reports"
    dsl_dir.mkdir()
    dsl_path = dsl_dir / "suite.yaml"
    config_path = tmp_path / "env.yaml"
    template_path = tmp_path / "template.json"
    runtime_path = tmp_path / "runtime.json"
    config_path.write_text(
        """
environments:
  ydf:
    base_url: https://example.yonyougov.top
    sysid: yonbip
    username: default-user
    password: default-password
""",
        encoding="utf-8",
    )
    dsl_path.write_text(
        """
suite:
  code: smoke
  name: 冒烟测试集
  tenant: 财政一体化
  default_org: "049002"
cases:
  - code: case-a
    name: 用例 A
    steps:
      - action: open_menu
        menu_path: 项目管理>>项目立项
  - code: case-b
    name: 用例 B
    steps:
      - action: open_menu
        menu_path: 项目管理>>项目立项
""",
        encoding="utf-8",
    )
    template_path.write_text(json.dumps(sample_template_payload, ensure_ascii=False), encoding="utf-8")
    runtime_path.write_text(json.dumps(sample_runtime_elements, ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "run",
            "--dsl",
            str(dsl_dir),
            "--case",
            "case-b",
            "--report-dir",
            str(report_dir),
            "--config",
            str(config_path),
            "--template-file",
            str(template_path),
            "--runtime-file",
            str(runtime_path),
            "--menu-path",
            "项目管理>>项目立项",
        ]
    )

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    report_file = Path(summary["report_file"])
    html_report_file = Path(summary["html_report_file"])
    report_payload = json.loads(report_file.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert summary["success"] is True
    assert summary["totals"] == {"suites": 1, "cases": 1, "passed": 1, "failed": 0, "skipped": 0}
    assert "suite_reports" not in summary
    assert "manifest" not in captured.out
    assert report_file.is_file()
    assert html_report_file == report_file.with_suffix(".html")
    assert html_report_file.is_file()
    assert report_payload["html_report_file"] == str(html_report_file)
    html_report = html_report_file.read_text(encoding="utf-8")
    assert "验收总览" in html_report
    assert "https://example.yonyougov.top" in html_report
    assert Path(summary["events_file"]).is_file()
    assert report_file.parent.parent == report_dir
    assert [item["case"]["code"] for item in report_payload["suite_reports"][0]["case_reports"]] == ["case-b"]
    assert f"report={report_file}" in captured.err


def test_cli_run_custom_report_file_writes_matching_html_report(
    tmp_path,
    capsys,
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    dsl_path = tmp_path / "workflow.yaml"
    template_path = tmp_path / "template.json"
    runtime_path = tmp_path / "runtime.json"
    report_file = tmp_path / "custom-output.json"
    dsl_path.write_text(
        """
suite:
  code: custom-report
  name: 自定义报告
  tenant: 财政一体化
  default_org: "049002"
cases:
  - code: open-menu
    name: 打开菜单
    user: 默认用户
    steps:
      - action: open_menu
        menu_path: 项目管理>>项目立项
""",
        encoding="utf-8",
    )
    template_path.write_text(json.dumps(sample_template_payload, ensure_ascii=False), encoding="utf-8")
    runtime_path.write_text(json.dumps(sample_runtime_elements, ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "run",
            "--dsl",
            str(dsl_path),
            "--report-file",
            str(report_file),
            "--template-file",
            str(template_path),
            "--runtime-file",
            str(runtime_path),
            "--menu-path",
            "项目管理>>项目立项",
        ]
    )

    summary = json.loads(capsys.readouterr().out)
    html_report_file = report_file.with_suffix(".html")
    report_payload = json.loads(report_file.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert summary["report_file"] == str(report_file)
    assert summary["html_report_file"] == str(html_report_file)
    assert report_payload["html_report_file"] == str(html_report_file)
    assert html_report_file.is_file()


def test_cli_run_without_performance_does_not_write_performance_workbook(
    tmp_path,
    capsys,
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    dsl_path = tmp_path / "workflow.yaml"
    template_path = tmp_path / "template.json"
    runtime_path = tmp_path / "runtime.json"
    report_file = tmp_path / "report.json"
    dsl_path.write_text(
        """
suite:
  code: no-perf
  name: 非性能报告
  tenant: 财政一体化
  default_org: "049002"
cases:
  - code: open-menu
    name: 打开菜单
    steps:
      - action: open_menu
        menu_path: 项目管理>>项目立项
""",
        encoding="utf-8",
    )
    template_path.write_text(json.dumps(sample_template_payload, ensure_ascii=False), encoding="utf-8")
    runtime_path.write_text(json.dumps(sample_runtime_elements, ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "run",
            "--dsl",
            str(dsl_path),
            "--report-file",
            str(report_file),
            "--template-file",
            str(template_path),
            "--runtime-file",
            str(runtime_path),
            "--menu-path",
            "项目管理>>项目立项",
        ]
    )

    summary = json.loads(capsys.readouterr().out)
    report_payload = json.loads(report_file.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert "performance_file" not in summary
    assert "performance_file" not in report_payload
    assert not (tmp_path / "performance.xlsx").exists()


def test_cli_run_without_performance_filters_bpr_steps_and_writes_no_bpr_traces(
    tmp_path,
    capsys,
    monkeypatch,
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    dsl_path = tmp_path / "workflow.yaml"
    template_path = tmp_path / "template.json"
    runtime_path = tmp_path / "runtime.json"
    report_file = tmp_path / "report.json"
    dsl_path.write_text(
        """
suite:
  code: perf-off
  name: 性能关闭
  tenant: 财政一体化
  default_org: "049002"
cases:
  - code: controls-only
    name: 控制步骤
    steps:
      - component: bpr
        operation: start
        target:
          name: 保存录制
      - component: bpr
        operation: stop
        target: {}
""",
        encoding="utf-8",
    )
    template_path.write_text(json.dumps(sample_template_payload, ensure_ascii=False), encoding="utf-8")
    runtime_path.write_text(json.dumps(sample_runtime_elements, ensure_ascii=False), encoding="utf-8")

    observed_steps = []

    class _Executor:
        def __init__(self, gateway, runtime, progress_logger=None, **_kwargs) -> None:
            self.gateway = gateway
            self.runtime = runtime
            self.progress_logger = progress_logger

        def run(self, steps):
            observed_steps.extend(step.to_dict() for step in steps)
            return ExecutionReport(success=True, step_results=[])

    monkeypatch.setattr(cli_module, "WorkflowExecutor", _Executor)

    exit_code = main(
        [
            "run",
            "--dsl",
            str(dsl_path),
            "--report-file",
            str(report_file),
            "--template-file",
            str(template_path),
            "--runtime-file",
            str(runtime_path),
            "--menu-path",
            "项目管理>>项目立项",
        ]
    )

    summary = json.loads(capsys.readouterr().out)
    report_payload = json.loads(report_file.read_text(encoding="utf-8"))
    html = report_file.with_suffix(".html").read_text(encoding="utf-8")
    events = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    assert exit_code == 0
    assert observed_steps == []
    assert "performance_file" not in summary
    assert "performance_file" not in report_payload
    assert not (tmp_path / "performance.xlsx").exists()
    assert "bpr" not in json.dumps(report_payload, ensure_ascii=False).lower()
    assert "bpr" not in html.lower()
    assert "bpr" not in events.lower()


def test_cli_run_performance_rejects_invalid_bpr_state_before_execution(
    tmp_path,
    capsys,
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    dsl_path = tmp_path / "workflow.yaml"
    template_path = tmp_path / "template.json"
    runtime_path = tmp_path / "runtime.json"
    report_file = tmp_path / "report.json"
    dsl_path.write_text(
        """
suite:
  code: invalid-bpr
  name: BPR校验
  tenant: 财政一体化
  default_org: "049002"
cases:
  - code: bpr-case
    name: BPR用例
    steps:
      - component: bpr
        operation: start
        target: {}
""",
        encoding="utf-8",
    )
    template_path.write_text(json.dumps(sample_template_payload, ensure_ascii=False), encoding="utf-8")
    runtime_path.write_text(json.dumps(sample_runtime_elements, ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "run",
            "--performance",
            "--dsl",
            str(dsl_path),
            "--report-file",
            str(report_file),
            "--template-file",
            str(template_path),
            "--runtime-file",
            str(runtime_path),
            "--menu-path",
            "项目管理>>项目立项",
        ]
    )

    summary = json.loads(capsys.readouterr().out)
    report_payload = json.loads(report_file.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert "BPR 录制缺少 bpr.stop" in summary["error"]
    assert "BPR 录制缺少 bpr.stop" in report_payload["suite_reports"][0]["case_reports"][0]["errors"][0]


def test_cli_run_performance_export_failure_preserves_functional_result(
    tmp_path,
    capsys,
    monkeypatch,
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    dsl_path = tmp_path / "workflow.yaml"
    template_path = tmp_path / "template.json"
    runtime_path = tmp_path / "runtime.json"
    report_file = tmp_path / "report.json"
    dsl_path.write_text(
        """
suite:
  code: export-error
  name: 导出异常
  tenant: 财政一体化
  default_org: "049002"
cases:
  - code: open-menu
    name: 打开菜单
    steps:
      - action: open_menu
        menu_path: 项目管理>>项目立项
""",
        encoding="utf-8",
    )
    template_path.write_text(json.dumps(sample_template_payload, ensure_ascii=False), encoding="utf-8")
    runtime_path.write_text(json.dumps(sample_runtime_elements, ensure_ascii=False), encoding="utf-8")

    def _raise_export_error(_result, _output_path):
        raise RuntimeError("xlsx writer unavailable")

    monkeypatch.setattr(cli_module, "export_performance_xlsx", _raise_export_error)

    exit_code = main(
        [
            "run",
            "--performance",
            "--dsl",
            str(dsl_path),
            "--report-file",
            str(report_file),
            "--template-file",
            str(template_path),
            "--runtime-file",
            str(runtime_path),
            "--menu-path",
            "项目管理>>项目立项",
        ]
    )

    summary = json.loads(capsys.readouterr().out)
    report_payload = json.loads(report_file.read_text(encoding="utf-8"))
    html = report_file.with_suffix(".html").read_text(encoding="utf-8")
    assert exit_code == 0
    assert summary["success"] is True
    assert summary["performance_export_error"]["message"] == "xlsx writer unavailable"
    assert report_payload["performance_export_error"]["message"] == "xlsx writer unavailable"
    assert report_payload["run"]["performance"]["export_error"] == "xlsx writer unavailable"
    assert "xlsx writer unavailable" in html


def test_cli_run_enriches_bpr_before_writing_performance_workbook(
    tmp_path,
    capsys,
    monkeypatch,
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    dsl_path = tmp_path / "workflow.yaml"
    template_path = tmp_path / "template.json"
    runtime_path = tmp_path / "runtime.json"
    report_file = tmp_path / "report.json"
    dsl_path.write_text(_suite_yaml("perf-order", "open-menu"), encoding="utf-8")
    template_path.write_text(json.dumps(sample_template_payload, ensure_ascii=False), encoding="utf-8")
    runtime_path.write_text(json.dumps(sample_runtime_elements, ensure_ascii=False), encoding="utf-8")
    calls: list[tuple[str, object]] = []

    def _enrich(result, env, report_dir, *, headless) -> None:
        calls.append(("enrich", (result["success"], env, report_dir, headless)))
        result["suite_reports"][0]["case_reports"][0]["bpr_sessions"] = [
            {
                "index": 1,
                "start_ts": 1782046212123,
                "end_ts": 1782046212623,
                "report_file": str(tmp_path / "artifacts" / "perf-order" / "open-menu" / "bpr" / "1-fake.html"),
                "report_file_href": "artifacts/perf-order/open-menu/bpr/1-fake.html",
                "report_url": "https://example.test/bpr?pk=fake",
                "download_status": "downloaded",
                "summary_status": "parsed",
                "server_summary": {"totalCostTime": "125"},
            }
        ]

    def _export(_result, output_path) -> None:
        calls.append(("export", output_path))
        output_path.write_bytes(b"xlsx")

    monkeypatch.setattr(cli_module, "enrich_bpr_reports", _enrich, raising=False)
    monkeypatch.setattr(cli_module, "export_performance_xlsx", _export)

    exit_code = main(
        [
            "run",
            "--performance",
            "--dsl",
            str(dsl_path),
            "--report-file",
            str(report_file),
            "--template-file",
            str(template_path),
            "--runtime-file",
            str(runtime_path),
            "--menu-path",
            "项目管理>>项目立项",
        ]
    )

    capsys.readouterr()
    session = json.loads(report_file.read_text(encoding="utf-8"))["suite_reports"][0]["case_reports"][0]["bpr_sessions"][0]
    assert exit_code == 0
    assert session["start_ts"] == 1782046212123
    assert session["end_ts"] == 1782046212623
    assert session["report_file_href"] == "artifacts/perf-order/open-menu/bpr/1-fake.html"
    assert session["server_summary"] == {"totalCostTime": "125"}
    assert calls == [
        ("enrich", (True, None, tmp_path, False)),
        ("export", tmp_path / "performance.xlsx"),
    ]


def test_cli_performance_outputs_do_not_propagate_sensitive_sources(
    tmp_path,
    capsys,
    monkeypatch,
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    request_body = "REQUEST-BODY-MUST-NOT-LEAK"
    raw_fragment = "RAW-BPR-FRAGMENT-MUST-NOT-LEAK"
    source_fragment = "BPR-SOURCE-MUST-NOT-LEAK"
    unknown_summary = "UNKNOWN-SUMMARY-MUST-NOT-LEAK"
    bpr_username = "BPR-USERNAME-MUST-NOT-LEAK"
    bpr_password = "BPR-PASSWORD-MUST-NOT-LEAK"
    dsl_path = tmp_path / "workflow.yaml"
    config_path = tmp_path / "env.yaml"
    template_path = tmp_path / "template.json"
    runtime_path = tmp_path / "runtime.json"
    report_file = tmp_path / "report.json"
    dsl_path.write_text(_suite_yaml("safe-output", "open-menu"), encoding="utf-8")
    template_path.write_text(json.dumps(sample_template_payload, ensure_ascii=False), encoding="utf-8")
    runtime_path.write_text(json.dumps(sample_runtime_elements, ensure_ascii=False), encoding="utf-8")
    config_path.write_text(
        f"""environments:
  ydf:
    base_url: https://example.yonyougov.top
    username: business-user
    password: business-password
    bpr:
      username: {bpr_username}
      password: {bpr_password}
""",
        encoding="utf-8",
    )

    def _enrich(result, env, report_dir, *, headless) -> None:
        assert env.bpr.username == bpr_username
        assert env.bpr.password == bpr_password
        assert headless is False
        raw_path = report_dir / "artifacts" / "safe-output" / "open-menu" / "bpr" / "1-safe.html"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        cells = "".join(
            f'<td data-field="{field}">allowed-{index}</td>'
            for index, (field, _label) in enumerate(SERVER_SUMMARY_FIELDS)
        )
        raw_path.write_text(
            f'<html><div id="summary-posi"><table><tr>{cells}</tr>'
            f'<tr><td data-field="unknown">{unknown_summary}</td></tr></table></div>'
            f'<div>{raw_fragment}</div><script>{source_fragment};{bpr_username};{bpr_password}</script></html>',
            encoding="utf-8",
        )
        summary = extract_server_summary(raw_path)
        collector = PlaywrightRuntime(env, SimpleNamespace(), headless=True)
        collector.enable_performance_collection()
        collector.begin_performance_step({
            "suite_code": "safe-output",
            "case_code": "open-menu",
            "step_index": 1,
            "action": "open_menu",
        })

        class _Request:
            method = "POST"
            url = "https://example.yonyougov.top/api/list"
            resource_type = "xhr"
            post_data_buffer = request_body
            headers = {}
            failure = None

            @staticmethod
            def sizes():
                return {}

        request = _Request()
        response = SimpleNamespace(
            url=request.url,
            status=200,
            headers={"content-length": "1"},
            request=request,
        )
        collector._record_or_update_network_event(request, response=response, failed=False)
        network_summary = collector.collect_network_summary()
        network_events = collector.collect_network_events()
        collector.end_performance_step()
        assert network_summary["request_body_size"] == len(request_body.encode())
        assert network_summary["request_body_size_available"] is True
        assert network_events[0]["request_body_size"] == len(request_body.encode())
        assert network_events[0]["request_body_size_available"] is True
        assert request_body not in json.dumps(
            {"events": network_events, "summary": network_summary},
            ensure_ascii=False,
        )
        assert collector._console_events == []
        assert collector._page_errors == []
        case_report = result["suite_reports"][0]["case_reports"][0]
        step = case_report["report"]["step_results"][0]
        step.setdefault("data", {})["performance"] = {
            "duration_ms": 1,
            "network": network_summary,
            "memory": {"available": True, "used_js_heap_size": 1048576},
        }
        case_report["performance"] = {"network_events": network_events}
        case_report["bpr_sessions"] = [{
            "index": 1,
            "name": "安全录制",
            "success": True,
            "status": "success",
            "report_file": str(raw_path.resolve()),
            "report_file_href": "artifacts/safe-output/open-menu/bpr/1-safe.html",
            "report_url": "https://example.yonyougov.top/bpr?pk=safe",
            "download_status": "downloaded",
            "download_error": "",
            "summary_status": "parsed",
            "summary_error": "",
            "server_summary": summary,
        }]

    monkeypatch.setattr(cli_module, "enrich_bpr_reports", _enrich)

    exit_code = main([
        "run",
        "--performance",
        "--dsl", str(dsl_path),
        "--report-file", str(report_file),
        "--config", str(config_path),
        "--env", "ydf",
        "--template-file", str(template_path),
        "--runtime-file", str(runtime_path),
        "--menu-path", "项目管理>>项目立项",
    ])

    console = capsys.readouterr()
    report_text = report_file.read_text(encoding="utf-8")
    report_payload = json.loads(report_text)
    html = report_file.with_suffix(".html").read_text(encoding="utf-8")
    events = (tmp_path / "events.jsonl").read_text(encoding="utf-8")
    workbook = load_workbook(tmp_path / "performance.xlsx", data_only=True)
    workbook_text = repr([
        cell.value
        for sheet in workbook.worksheets
        for row in sheet.iter_rows()
        for cell in row
    ])
    outputs = "\n".join((report_text, html, events, console.out, console.err, workbook_text))
    session = report_payload["suite_reports"][0]["case_reports"][0]["bpr_sessions"][0]

    assert exit_code == 0
    for forbidden in (
        request_body,
        raw_fragment,
        source_fragment,
        unknown_summary,
        bpr_username,
        bpr_password,
    ):
        assert forbidden not in outputs
    assert tuple(session["server_summary"]) == tuple(field for field, _label in SERVER_SUMMARY_FIELDS)
    for value in session["server_summary"].values():
        assert value in report_text
        assert value in workbook_text


def test_cli_run_html_report_marks_git_unavailable_when_not_in_git_context(
    tmp_path,
    capsys,
    monkeypatch,
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    dsl_path = tmp_path / "workflow.yaml"
    config_path = tmp_path / "env.yaml"
    template_path = tmp_path / "template.json"
    runtime_path = tmp_path / "runtime.json"
    report_file = tmp_path / "report.json"
    config_path.write_text(
        """
environments:
  ydf:
    base_url: https://example.yonyougov.top
    sysid: yonbip
    username: default-user
    password: default-password
""",
        encoding="utf-8",
    )
    dsl_path.write_text(
        """
suite:
  code: git-report
  name: Git 报告
  tenant: 财政一体化
  default_org: "049002"
cases:
  - code: open-menu
    name: 打开菜单
    user: 默认用户
    steps:
      - action: open_menu
        menu_path: 项目管理>>项目立项
""",
        encoding="utf-8",
    )
    template_path.write_text(json.dumps(sample_template_payload, ensure_ascii=False), encoding="utf-8")
    runtime_path.write_text(json.dumps(sample_runtime_elements, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(cli_module, "_run_git_command", lambda _command: "")

    exit_code = main(
        [
            "run",
            "--dsl",
            str(dsl_path),
            "--report-file",
            str(report_file),
            "--config",
            str(config_path),
            "--template-file",
            str(template_path),
            "--runtime-file",
            str(runtime_path),
            "--menu-path",
            "项目管理>>项目立项",
        ]
    )

    summary = json.loads(capsys.readouterr().out)
    report_payload = json.loads(report_file.read_text(encoding="utf-8"))
    html_report = Path(summary["html_report_file"]).read_text(encoding="utf-8")
    assert exit_code == 0
    assert report_payload["run"]["git"]["available"] is False
    assert "不可用" in html_report
    assert "- @ - (clean)" not in html_report


def test_cli_run_accepts_multiple_dsl_values_after_one_flag(
    tmp_path,
    capsys,
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    first_dsl = tmp_path / "first.yaml"
    second_dsl = tmp_path / "second.yaml"
    template_path = tmp_path / "template.json"
    runtime_path = tmp_path / "runtime.json"
    report_dir = tmp_path / "reports"
    first_dsl.write_text(
        """
suite:
  code: first
  name: 第一个测试集
  tenant: 财政一体化
  default_org: "049002"
cases:
  - code: first-case
    name: 第一个用例
    user: 默认用户
    steps:
      - action: open_menu
        menu_path: 项目管理>>项目立项
""",
        encoding="utf-8",
    )
    second_dsl.write_text(
        """
suite:
  code: second
  name: 第二个测试集
  tenant: 财政一体化
  default_org: "049002"
cases:
  - code: second-case
    name: 第二个用例
    user: 默认用户
    steps:
      - action: open_menu
        menu_path: 项目管理>>项目立项
""",
        encoding="utf-8",
    )
    template_path.write_text(json.dumps(sample_template_payload, ensure_ascii=False), encoding="utf-8")
    runtime_path.write_text(json.dumps(sample_runtime_elements, ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "run",
            "--dsl",
            str(first_dsl),
            str(second_dsl),
            "--report-dir",
            str(report_dir),
            "--template-file",
            str(template_path),
            "--runtime-file",
            str(runtime_path),
            "--menu-path",
            "项目管理>>项目立项",
        ]
    )

    summary = json.loads(capsys.readouterr().out)
    report = json.loads(Path(summary["report_file"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert summary["totals"] == {"suites": 2, "cases": 2, "passed": 2, "failed": 0, "skipped": 0}
    assert [Path(item["dsl_file"]).name for item in report["suite_reports"]] == ["first.yaml", "second.yaml"]


def test_cli_run_dsl_list_executes_files_in_list_order(
    tmp_path,
    capsys,
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    dsl_dir = tmp_path / "suites"
    dsl_dir.mkdir()
    first_dsl = dsl_dir / "first.yaml"
    second_dsl = dsl_dir / "second.yaml"
    dsl_list = tmp_path / "suite-list.txt"
    template_path = tmp_path / "template.json"
    runtime_path = tmp_path / "runtime.json"
    report_dir = tmp_path / "reports"
    first_dsl.write_text(_suite_yaml("first", "first-case"), encoding="utf-8")
    second_dsl.write_text(_suite_yaml("second", "second-case"), encoding="utf-8")
    dsl_list.write_text("suites/second.yaml\nsuites/first.yaml\n", encoding="utf-8")
    template_path.write_text(json.dumps(sample_template_payload, ensure_ascii=False), encoding="utf-8")
    runtime_path.write_text(json.dumps(sample_runtime_elements, ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "run",
            "--dsl-list",
            str(dsl_list),
            "--report-dir",
            str(report_dir),
            "--template-file",
            str(template_path),
            "--runtime-file",
            str(runtime_path),
            "--menu-path",
            "项目管理>>项目立项",
        ]
    )

    summary = json.loads(capsys.readouterr().out)
    report = json.loads(Path(summary["report_file"]).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert [Path(item["dsl_file"]).name for item in report["suite_reports"]] == ["second.yaml", "first.yaml"]
    assert report["run"]["dsl_list"] == [str(dsl_list)]


@pytest.mark.parametrize("mixed_inputs", [False, True])
def test_cli_run_rejects_concurrency_with_dsl_list(tmp_path, capsys, mixed_inputs: bool) -> None:
    input_args = ["--dsl-list", str(tmp_path / "suites.txt")]
    if mixed_inputs:
        input_args[:0] = ["--dsl", str(tmp_path / "setup.yaml")]

    exit_code = main(
        [
            "run",
            *input_args,
            "--concurrency",
            "2",
            "--template-file",
            str(tmp_path / "template.json"),
            "--runtime-file",
            str(tmp_path / "runtime.json"),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert "--dsl-list 仅支持 --concurrency 1" in payload["error"]
    assert "严格串行执行" in payload["error"]


def test_cli_run_allows_concurrency_without_dsl_list(
    tmp_path,
    capsys,
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
    sample_dsl_path,
) -> None:
    template_path = tmp_path / "template.json"
    runtime_path = tmp_path / "runtime.json"
    template_path.write_text(json.dumps(sample_template_payload, ensure_ascii=False), encoding="utf-8")
    runtime_path.write_text(json.dumps(sample_runtime_elements, ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "run",
            "--dsl",
            str(sample_dsl_path),
            "--concurrency",
            "2",
            "--template-file",
            str(template_path),
            "--runtime-file",
            str(runtime_path),
            "--menu-path",
            "项目管理>>项目立项",
        ]
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["success"] is True


def test_cli_run_suite_prepares_each_identity_and_closes_case_pages(tmp_path, capsys, monkeypatch) -> None:
    dsl_path = tmp_path / "suite.yaml"
    dsl_path.write_text(
        """
suite:
  code: execute_project_init
  name: 执行项目立项
  description: 覆盖两个独立用例
  tenant: 财政一体化
  fiscal_year: "2027"
cases:
  - code: case-a
    name: 用例 A
    description: 第一个用例
    user: 张三
    default_org: "049002"
    steps:
      - action: open_menu
        menu_path: 项目管理>>项目立项
  - code: case-b
    name: 用例 B
    user: 李四
    default_org: "049003"
    steps:
      - action: open_menu
        menu_path: 项目管理>>项目立项
""",
        encoding="utf-8",
    )
    base_env = EnvironmentConfig(
        env_name="ydf",
        base_url="https://example.yonyougov.top",
        sysid="yonbip",
        username="base-user",
        password="base-password",
        endpoints=EndpointConfig(),
        users={
            "张三": UserCredential(username="alice", password="alice-secret"),
            "李四": UserCredential(username="bob", password="bob-secret"),
        },
    )
    logins: list[dict[str, str]] = []
    runtimes: list[object] = []

    class _ConfigLoader:
        def __init__(self, config_path=None) -> None:
            self.config_path = config_path

        def get_env(self, env_name: str) -> EnvironmentConfig:
            assert env_name == "ydf"
            return base_env

    class _Gateway:
        def __init__(self, env, session) -> None:
            self.env = env
            self.session = session

    class _Runtime:
        def __init__(self, env, session, headless=False, profile_dir=None) -> None:
            self.env = env
            self.session = session
            self.headless = headless
            self.profile_dir = profile_dir
            self.started = False
            self.stopped = False
            self.clear_cookie_urls: list[str] = []
            self.closed_case_pages = 0
            runtimes.append(self)

        def start(self) -> None:
            self.started = True

        def clear_visible_cookies(self, base_url: str) -> None:
            self.clear_cookie_urls.append(base_url)

        def close_case_pages(self) -> None:
            self.closed_case_pages += 1

        def stop(self) -> None:
            self.stopped = True

    class _Executor:
        def __init__(self, gateway, runtime, progress_logger=None, **_kwargs) -> None:
            self.gateway = gateway
            self.runtime = runtime
            self.progress_logger = progress_logger

        def run(self, steps):
            return ExecutionReport(
                success=True,
                step_results=[StepResult(action="open_menu", success=True, message="ok")],
            )

    def _login(env, default_org=None, menu_path=None, tenant_name=None, fiscal_year=None):
        logins.append(
            {
                "username": env.username,
                "password": env.password,
                "default_org": default_org or "",
                "menu_path": menu_path or "",
                "tenant_name": tenant_name or "",
                "fiscal_year": fiscal_year or "",
            }
        )
        return SimpleNamespace(cookies=[])

    monkeypatch.setattr(cli_module, "ConfigLoader", _ConfigLoader)
    monkeypatch.setattr(cli_module, "_login_with_default_org_context", _login)
    _stub_session_reuse(monkeypatch)
    monkeypatch.setattr(cli_module, "YondifGateway", _Gateway)
    monkeypatch.setattr(cli_module, "PlaywrightRuntime", _Runtime)
    monkeypatch.setattr(cli_module, "WorkflowExecutor", _Executor)

    exit_code = main(["run", "--dsl", str(dsl_path), "--headless"])

    assert exit_code == 0
    output = capsys.readouterr().out
    data = json.loads(output)
    report = json.loads(Path(data["report_file"]).read_text(encoding="utf-8"))
    assert data["success"] is True
    assert report["suite_reports"][0]["suite"]["code"] == "execute_project_init"
    assert [item["case"]["code"] for item in report["suite_reports"][0]["case_reports"]] == ["case-a", "case-b"]
    assert [item["case"]["user"] for item in report["suite_reports"][0]["case_reports"]] == ["张三", "李四"]
    assert "alice-secret" not in output
    assert "bob-secret" not in output
    assert logins == [
        {
            "username": "alice",
            "password": "alice-secret",
            "default_org": "049002",
            "menu_path": "",
            "tenant_name": "财政一体化",
            "fiscal_year": "2027",
        },
        {
            "username": "bob",
            "password": "bob-secret",
            "default_org": "049003",
            "menu_path": "",
            "tenant_name": "财政一体化",
            "fiscal_year": "2027",
        },
    ]
    assert len(runtimes) == 1
    assert runtimes[0].started is True
    assert runtimes[0].stopped is True
    assert runtimes[0].profile_dir is not None
    assert runtimes[0].clear_cookie_urls == []
    assert runtimes[0].closed_case_pages == 2


def test_login_with_default_org_context_switches_fiscal_year_after_final_login_before_menu(monkeypatch) -> None:
    events: list[str] = []

    env = EnvironmentConfig(
        env_name="ydf",
        base_url="https://example.yonyougov.top",
        sysid="yonbip",
        username="demo",
        password="demo",
        endpoints=EndpointConfig(),
    )

    class _Authenticator:
        def __init__(self, env) -> None:
            self.env = env

        def login(self, existing_session=None):
            assert (existing_session is not None) == ("login" in events)
            events.append("login")
            return SimpleNamespace(cookies=[])

    class _TenantContext:
        def __init__(self, env, session) -> None:
            pass

        def apply(self, tenant_name=None):
            events.append(f"tenant:{tenant_name}")
            return SimpleNamespace(tenant_id="tenant-a")

    class _DefaultOrgContext:
        def __init__(self, env, session) -> None:
            pass

        def apply(self, default_org=None):
            events.append(f"org:{default_org}")
            return SimpleNamespace(org_id="org-a")

    class _Verifier:
        def __init__(self, env, session) -> None:
            pass

        def verify(self, **kwargs):
            events.append(f"verify:{kwargs['expected_tenant_id']}:{kwargs['expected_org_id']}")

    class _FiscalYearContext:
        def __init__(self, env, session) -> None:
            pass

        def apply(self, fiscal_year=None):
            events.append(f"fiscal:{fiscal_year}")

    class _Gateway:
        def __init__(self, env, session) -> None:
            pass

        def resolve_menu(self, menu_path):
            events.append(f"menu:{menu_path}")

    monkeypatch.setattr(cli_module, "CasAuthenticator", _Authenticator)
    monkeypatch.setattr(cli_module, "TenantContext", _TenantContext)
    monkeypatch.setattr(cli_module, "DefaultOrgContext", _DefaultOrgContext)
    monkeypatch.setattr(cli_module, "UserContextVerifier", _Verifier)
    monkeypatch.setattr(cli_module, "FiscalYearContext", _FiscalYearContext)
    monkeypatch.setattr(cli_module, "YondifGateway", _Gateway)

    cli_module._login_with_default_org_context(
        env,
        "049002",
        menu_path="项目管理>>项目立项",
        tenant_name="财政一体化",
        fiscal_year="2027",
    )

    assert events == [
        "login",
        "tenant:财政一体化",
        "org:049002",
        "login",
        "verify:tenant-a:org-a",
        "fiscal:2027",
    ]


def test_cli_run_passes_request_forwarding_rules_to_real_runtime_and_report(
    tmp_path,
    capsys,
    monkeypatch,
) -> None:
    dsl_path = tmp_path / "suite.yaml"
    dsl_path.write_text(
        """
suite:
  code: local-debug
  name: 本地调试
  tenant: 财政一体化
  default_org: "049002"
cases:
  - code: open-menu
    name: 打开菜单
    user: 默认用户
    steps:
      - action: open_menu
        menu_path: 项目管理>>项目立项
""",
        encoding="utf-8",
    )
    base_env = EnvironmentConfig(
        env_name="ydf",
        base_url="https://example.yonyougov.top",
        sysid="yonbip",
        username="demo",
        password="secret",
        users={"默认用户": UserCredential(username="demo", password="secret")},
    )
    runtime_rules: list[list[dict[str, object]]] = []

    class _ConfigLoader:
        def __init__(self, config_path=None) -> None:
            pass

        def get_env(self, env_name: str) -> EnvironmentConfig:
            return base_env

    class _Gateway:
        def __init__(self, env, session) -> None:
            pass

    class _Runtime:
        def __init__(self, env, session, headless=False, request_forward_rules=None, profile_dir=None) -> None:
            runtime_rules.append([rule.to_dict() for rule in request_forward_rules or []])

        def start(self) -> None:
            pass

        def clear_visible_cookies(self, base_url: str) -> None:
            pass

        def close_case_pages(self) -> None:
            pass

        def stop(self) -> None:
            pass

    class _Executor:
        def __init__(self, gateway, runtime, progress_logger=None, **_kwargs) -> None:
            pass

        def run(self, steps):
            return ExecutionReport(
                success=True,
                step_results=[StepResult(action="open_menu", success=True, message="ok")],
            )

    monkeypatch.setattr(cli_module, "ConfigLoader", _ConfigLoader)
    monkeypatch.setattr(cli_module, "_login_with_default_org_context", lambda *_args, **_kwargs: SimpleNamespace(cookies=[]))
    _stub_session_reuse(monkeypatch)
    monkeypatch.setattr(cli_module, "YondifGateway", _Gateway)
    monkeypatch.setattr(cli_module, "PlaywrightRuntime", _Runtime)
    monkeypatch.setattr(cli_module, "WorkflowExecutor", _Executor)

    exit_code = main(
        [
            "run",
            "--dsl",
            str(dsl_path),
            "--headless",
            "--forward",
            "/yondif-bm-fe/**=https://localhost:3000",
            "--forward-strip-prefix",
            "/yondif-bm-be/**=http://localhost:62871",
        ]
    )

    assert exit_code == 0
    summary = json.loads(capsys.readouterr().out)
    report = json.loads(Path(summary["report_file"]).read_text(encoding="utf-8"))
    assert runtime_rules == [
        [
            {"pattern": "/yondif-bm-fe/**", "target": "https://localhost:3000", "strip_prefix": False},
            {"pattern": "/yondif-bm-be/**", "target": "http://localhost:62871", "strip_prefix": True},
        ]
    ]
    assert report["run"]["request_forwarding"] == {
        "enabled": True,
        "rules": runtime_rules[0],
    }


def test_cli_run_rejects_request_forwarding_in_fixture_mode(
    tmp_path,
    capsys,
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
    sample_dsl_path,
) -> None:
    template_path = tmp_path / "template.json"
    runtime_path = tmp_path / "runtime.json"
    template_path.write_text(json.dumps(sample_template_payload, ensure_ascii=False), encoding="utf-8")
    runtime_path.write_text(json.dumps(sample_runtime_elements, ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "run",
            "--dsl",
            str(sample_dsl_path),
            "--template-file",
            str(template_path),
            "--runtime-file",
            str(runtime_path),
            "--menu-path",
            "项目管理>>项目立项",
            "--forward",
            "/yondif-bm-fe/**=https://localhost:3000",
        ]
    )

    assert exit_code == 1
    data = json.loads(capsys.readouterr().out)
    assert data["success"] is False
    assert "请求转发仅支持真实浏览器 run" in data["error"]


def test_cli_request_forwarding_preserves_command_line_order() -> None:
    args = cli_module.build_parser().parse_args(
        [
            "run",
            "--dsl",
            "examples",
            "--forward-strip-prefix",
            "/yondif-bm-be/**=http://localhost:62871",
            "--forward",
            "/yondif-bm-be/**=http://localhost:7000",
        ]
    )

    assert args.request_forward_specs == [
        ("/yondif-bm-be/**=http://localhost:62871", True),
        ("/yondif-bm-be/**=http://localhost:7000", False),
    ]


def test_cli_run_performance_captures_warm_open_menu_without_rerunning_case(tmp_path, capsys, monkeypatch) -> None:
    dsl_path = tmp_path / "suite.yaml"
    dsl_path.write_text(
        """
suite:
  code: perf
  name: 性能测试集
  tenant: 财政一体化
  default_org: "049002"
cases:
  - code: case-a
    name: 用例 A
    user: 默认用户
    steps:
      - action: open_menu
        menu_path: 项目管理>>项目立项
      - component: toolbar
        operation: click
        target:
          label: 保存
""",
        encoding="utf-8",
    )
    base_env = EnvironmentConfig(
        env_name="ydf",
        base_url="https://example.yonyougov.top",
        sysid="yonbip",
        username="demo",
        password="secret",
        users={"默认用户": UserCredential(username="demo", password="secret")},
    )
    menu_target = cli_module.MenuTarget(
        menu_code="PM_INIT",
        menu_name="项目立项",
        path=["项目管理", "项目立项"],
        service_code="global00_-1_PM_INIT",
    )
    runtimes = []
    executor_runs = []

    class _ConfigLoader:
        def __init__(self, _path=None) -> None:
            pass

        def get_env(self, _name):
            return base_env

    class _Gateway:
        def __init__(self, env, session) -> None:
            self.env = env
            self.session = session

    class _Runtime:
        def __init__(self, env, session, headless=False, profile_dir=None, **_kwargs) -> None:
            self.env = env
            self.session = session
            self.headless = headless
            self.profile_dir = profile_dir
            self.opened_menus = []
            self.collect_calls = []
            runtimes.append(self)

        def enable_performance_collection(self) -> None:
            self.performance_enabled = True

        def start(self) -> None:
            self.started = True

        def clear_visible_cookies(self, _base_url: str) -> None:
            self.cookies_cleared = True

        def close_case_pages(self) -> None:
            self.pages_closed = True

        def stop(self) -> None:
            self.stopped = True

        def open_menu(self, target) -> None:
            self.opened_menus.append(target.menu_name)

        def collect_network_summary(self, reset=False):
            self.collect_calls.append(reset)
            return {"network_available": True, "request_count": 1, "failed_count": 0, "top_slow_requests": []}

    class _Executor:
        def __init__(self, gateway, runtime, progress_logger=None, performance_enabled=False, **_kwargs) -> None:
            self.gateway = gateway
            self.runtime = runtime
            self.progress_logger = progress_logger
            self.performance_enabled = performance_enabled

        def run(self, steps):
            executor_runs.append(list(steps))
            self.runtime.open_menu(menu_target)
            return ExecutionReport(
                success=True,
                menu_target=menu_target,
                step_results=[
                    StepResult(
                        action="open_menu",
                        success=True,
                        message="ok",
                        data={"performance": {"duration_ms": 80, "phases": {"browser_open_ms": 50}, "network": {"request_count": 1, "failed_count": 0}}},
                    ),
                    StepResult(action="toolbar.click", success=True, message="saved"),
                ],
                performance={"enabled": True, "cache_mode": "persistent_profile_case_open_menu", "network_available": True, "cold": {"duration_ms": 120}},
            )

    monkeypatch.setattr(cli_module, "ConfigLoader", _ConfigLoader)
    monkeypatch.setattr(cli_module, "_login_with_default_org_context", lambda *_args, **_kwargs: SimpleNamespace(cookies=[]))
    _stub_session_reuse(monkeypatch)
    monkeypatch.setattr(cli_module, "YondifGateway", _Gateway)
    monkeypatch.setattr(cli_module, "PlaywrightRuntime", _Runtime)
    monkeypatch.setattr(cli_module, "WorkflowExecutor", _Executor)

    exit_code = main(["run", "--performance", "--dsl", str(dsl_path), "--headless"])

    assert exit_code == 0
    summary = json.loads(capsys.readouterr().out)
    report = json.loads(Path(summary["report_file"]).read_text(encoding="utf-8"))
    assert len(executor_runs) == 1
    assert runtimes[0].opened_menus == ["项目立项", "项目立项"]
    assert runtimes[0].profile_dir is not None
    warm = report["suite_reports"][0]["case_reports"][0]["performance"]["warm_open_menu"]
    assert warm["cache_mode"] == "persistent_profile_same_case_reopen_menu"
    assert warm["cold_open_menu_ms"] == 50


def test_performance_summary_keeps_api_and_static_slow_requests_separate() -> None:
    result = {
        "suite_reports": [
            {
                "suite": {"code": "perf"},
                "case_reports": [
                    {
                        "duration_ms": 1000,
                        "case": {"code": "case-a"},
                        "report": {
                            "step_results": [
                                {
                                    "action": "open_menu",
                                    "data": {
                                        "performance": {
                                            "duration_ms": 300,
                                            "network": {
                                                "failed_count": 0,
                                                "top_slow_requests": [
                                                    {"url": "https://example.yonyougov.top/static/app.js", "duration_ms": 900},
                                                    {"url": "https://example.yonyougov.top/yondif-ams-be/api", "duration_ms": 500},
                                                ],
                                                "top_slow_api_requests": [
                                                    {"url": "https://example.yonyougov.top/yondif-ams-be/api", "duration_ms": 500}
                                                ],
                                                "top_slow_static_resources": [
                                                    {"url": "https://example.yonyougov.top/static/app.js", "duration_ms": 900}
                                                ],
                                            },
                                        }
                                    },
                                }
                            ]
                        },
                    }
                ],
            }
        ]
    }

    summary = cli_module._performance_summary(result)

    assert summary["top_slow_api_requests"][0]["url"] == "https://example.yonyougov.top/yondif-ams-be/api"
    assert summary["top_slow_static_resources"][0]["url"] == "https://example.yonyougov.top/static/app.js"
    assert summary["top_slow_requests"][0]["url"] == "https://example.yonyougov.top/static/app.js"


def test_cli_page_analyze_outputs_binding_and_page_state(
    tmp_path,
    capsys,
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_path = tmp_path / "template.json"
    runtime_path = tmp_path / "runtime.json"
    template_path.write_text(json.dumps(sample_template_payload, ensure_ascii=False), encoding="utf-8")
    runtime_path.write_text(json.dumps(sample_runtime_elements, ensure_ascii=False), encoding="utf-8")

    exit_code = main(
        [
            "page",
            "analyze",
            "项目管理>>项目立项",
            "--template-file",
            str(template_path),
            "--runtime-file",
            str(runtime_path),
        ]
    )

    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["success"] is True
    assert data["report"]["page_state"]["frame_count"] == 1
    assert data["report"]["step_results"][0]["data"]["bound_field_count"] >= 2


def test_cli_validate_reports_dsl_suite_summary(tmp_path, capsys) -> None:
    dsl_path = tmp_path / "workflow.yaml"
    dsl_path.write_text(
        """
suite:
  code: validate_smoke
  name: 校验测试集
  tenant: 财政一体化
  default_org: "049002"
cases:
  - code: case-a
    name: 用例 A
    user: 默认用户
    steps:
      - action: open_menu
        menu_path: 项目库>>项目建议>>项目建议
""",
        encoding="utf-8",
    )

    exit_code = main(["validate", "--dsl", str(dsl_path)])

    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["success"] is True
    assert data["totals"] == {"files": 1, "suites": 1, "cases": 1}
    assert data["dsl_files"][0]["suite"]["code"] == "validate_smoke"


def test_cli_validate_resolves_variables_from_env_local_and_cli_inputs(tmp_path, capsys, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "env.yaml").write_text(
        """
environments:
  ydf:
    variables:
      tenant_name: BASE-TENANT
      default_org: BASE-ORG
      suite_name: BASE-NAME
""",
        encoding="utf-8",
    )
    (config_dir / "env.local.yaml").write_text(
        """
environments:
  ydf:
    variables:
      tenant_name: LOCAL-TENANT
""",
        encoding="utf-8",
    )
    vars_path = tmp_path / "vars.yaml"
    vars_path.write_text(
        """
variables:
  default_org: FILE-ORG
  suite_name: FILE-NAME
""",
        encoding="utf-8",
    )
    dsl_path = tmp_path / "workflow.yaml"
    dsl_path.write_text(
        """
suite:
  code: validate_variables
  name: "{{suite_name}}"
  tenant: "{{tenant_name}}"
  default_org: "{{default_org}}"
cases:
  - code: case-a
    name: 用例 A
    user: 默认用户
    steps:
      - action: open_menu
        menu_path: 项目库>>项目建议>>项目建议
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "validate",
            "--dsl",
            str(dsl_path),
            "--vars-file",
            str(vars_path),
            "--var",
            "suite_name=CLI-NAME",
        ]
    )

    assert exit_code == 0
    suite = json.loads(capsys.readouterr().out)["dsl_files"][0]["suite"]
    assert suite["tenant"] == "LOCAL-TENANT"
    assert suite["default_org"] == "FILE-ORG"
    assert suite["name"] == "CLI-NAME"


def test_cli_validate_accepts_explicit_environment_config(tmp_path, capsys) -> None:
    config_path = tmp_path / "env.yaml"
    config_path.write_text(
        """
environments:
  custom:
    variables:
      tenant_name: CUSTOM-TENANT
""",
        encoding="utf-8",
    )
    dsl_path = tmp_path / "workflow.yaml"
    dsl_path.write_text(
        """
suite:
  code: validate_custom_env
  name: 校验指定环境
  tenant: "{{tenant_name}}"
  default_org: "049002"
cases:
  - code: case-a
    name: 用例 A
    user: 默认用户
    steps:
      - action: open_menu
        menu_path: 项目库>>项目建议>>项目建议
""",
        encoding="utf-8",
    )

    exit_code = main(
        ["validate", "--dsl", str(dsl_path), "--env", "custom", "--config", str(config_path)]
    )

    assert exit_code == 0
    suite = json.loads(capsys.readouterr().out)["dsl_files"][0]["suite"]
    assert suite["tenant"] == "CUSTOM-TENANT"


def test_cli_validate_dsl_list_reports_files_in_list_order(tmp_path, capsys) -> None:
    first_dsl = tmp_path / "first.yaml"
    second_dsl = tmp_path / "second.yaml"
    dsl_list = tmp_path / "suite-list.txt"
    first_dsl.write_text(_suite_yaml("first", "first-case"), encoding="utf-8")
    second_dsl.write_text(_suite_yaml("second", "second-case"), encoding="utf-8")
    dsl_list.write_text("second.yaml\nfirst.yaml\n", encoding="utf-8")

    exit_code = main(["validate", "--dsl-list", str(dsl_list)])

    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert [Path(item["path"]).name for item in data["dsl_files"]] == ["second.yaml", "first.yaml"]


def test_cli_validate_dsl_list_preserves_mixed_input_order(tmp_path, capsys) -> None:
    setup_dsl = tmp_path / "setup.yaml"
    middle_dsl = tmp_path / "middle.yaml"
    cleanup_dsl = tmp_path / "cleanup.yaml"
    dsl_list = tmp_path / "suite-list.txt"
    setup_dsl.write_text(_suite_yaml("setup", "setup-case"), encoding="utf-8")
    middle_dsl.write_text(_suite_yaml("middle", "middle-case"), encoding="utf-8")
    cleanup_dsl.write_text(_suite_yaml("cleanup", "cleanup-case"), encoding="utf-8")
    dsl_list.write_text("middle.yaml\n", encoding="utf-8")

    exit_code = main(["validate", "--dsl", str(setup_dsl), "--dsl-list", str(dsl_list), "--dsl", str(cleanup_dsl)])

    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert [Path(item["path"]).name for item in data["dsl_files"]] == ["setup.yaml", "middle.yaml", "cleanup.yaml"]


def test_cli_validate_dsl_list_ignores_comments_and_resolves_relative_paths(tmp_path, capsys) -> None:
    plan_dir = tmp_path / "plans"
    case_dir = plan_dir / "cases"
    case_dir.mkdir(parents=True)
    dsl_path = case_dir / "only.yaml"
    dsl_list = plan_dir / "suite-list.txt"
    dsl_path.write_text(_suite_yaml("only", "only-case"), encoding="utf-8")
    dsl_list.write_text("\n# 先跑核心用例\n  cases/only.yaml  \n", encoding="utf-8")

    exit_code = main(["validate", "--dsl-list", str(dsl_list)])

    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert [Path(item["path"]).name for item in data["dsl_files"]] == ["only.yaml"]


@pytest.mark.parametrize(
    ("entry", "create_entry"),
    [
        ("missing.yaml", False),
        ("bad-dir", True),
        ("notes.txt", True),
    ],
)
def test_cli_validate_dsl_list_reports_invalid_entries(tmp_path, capsys, entry: str, create_entry: bool) -> None:
    dsl_list = tmp_path / "suite-list.txt"
    if create_entry:
        target = tmp_path / entry
        if entry == "bad-dir":
            target.mkdir()
        else:
            target.write_text("not a dsl", encoding="utf-8")
    dsl_list.write_text(f"{entry}\n", encoding="utf-8")

    exit_code = main(["validate", "--dsl-list", str(dsl_list)])

    assert exit_code == 1
    data = json.loads(capsys.readouterr().out)
    assert "清单" in data["error"]
    assert "第 1 行" in data["error"]


def test_cli_validate_returns_error_for_invalid_dsl(tmp_path, capsys) -> None:
    dsl_path = tmp_path / "legacy.yaml"
    dsl_path.write_text(
        """
steps:
  - action: open_menu
    menu_path: 项目库>>项目建议>>项目建议
""",
        encoding="utf-8",
    )

    exit_code = main(["validate", "--dsl", str(dsl_path)])

    assert exit_code == 1
    data = json.loads(capsys.readouterr().out)
    assert data["success"] is False
    assert "旧式 steps DSL 已废弃" in data["error"]


@pytest.mark.parametrize("command", ["validate", "run"])
@pytest.mark.parametrize("input_kind", ["directory", "files", "list"])
@pytest.mark.parametrize("failure", ["variable", "schema", "yaml"])
def test_cli_validation_identifies_failing_file_and_location(
    tmp_path, capsys, monkeypatch, command, input_kind, failure
) -> None:
    dsl_dir = tmp_path / "inputs"
    dsl_dir.mkdir()
    valid_path = dsl_dir / "01-valid.yaml"
    invalid_path = dsl_dir / "02-invalid.yaml"
    valid_yaml = _suite_yaml("valid", "valid-case")
    valid_path.write_text(valid_yaml, encoding="utf-8")
    if failure == "variable":
        invalid_yaml = valid_yaml.replace("项目管理>>项目立项", '"{{pay_allo_no}}"')
        expected_error = "cases[1].steps[1].menu_path: 未定义 DSL 变量: pay_allo_no"
    elif failure == "schema":
        invalid_yaml = valid_yaml.replace("menu_path: 项目管理>>项目立项", "unexpected: true")
        expected_error = "cases[1].steps[1]"
    else:
        invalid_yaml = "suite: [\n"
        expected_error = "line 2, column 1"
    invalid_path.write_text(invalid_yaml, encoding="utf-8")
    if input_kind == "directory":
        inputs = ["--dsl", str(dsl_dir)]
    elif input_kind == "files":
        inputs = ["--dsl", str(valid_path), str(invalid_path)]
    else:
        dsl_list = tmp_path / "suites.txt"
        dsl_list.write_text(f"{valid_path}\n{invalid_path}\n", encoding="utf-8")
        inputs = ["--dsl-list", str(dsl_list)]
    report_file = tmp_path / "report.json"
    args = [command, *inputs]
    if command == "run":
        report_file.write_text('{"success": true}', encoding="utf-8")
        args.extend([
            "--template-file", "must-not-be-read-template.json",
            "--runtime-file", "must-not-be-read-runtime.json",
            "--report-file", str(report_file),
        ])

    def unexpected_execution(*args, **kwargs):
        pytest.fail("校验失败时不得执行用例")

    monkeypatch.setattr(cli_module, "_run_suite_specs_in_process", unexpected_execution)
    exit_code = main(args)

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert exit_code == 1
    assert data["success"] is False
    assert str(invalid_path) in data["error"]
    assert str(invalid_path) in captured.err
    assert expected_error in data["error"]
    if command == "run":
        assert data["first_failure"]["dsl_file"] == str(invalid_path)
        report = json.loads(report_file.read_text(encoding="utf-8"))
        suite_report = report["suite_reports"][0]
        assert suite_report["dsl_file"] == str(invalid_path)
        case_report = suite_report["case_reports"][0]
        assert case_report["dsl_file"] == str(invalid_path)
        assert case_report["report"]["errors"] == [data["error"]]
        assert str(invalid_path) in report_file.with_suffix(".html").read_text(encoding="utf-8")


@pytest.mark.parametrize("command", ["validate", "run", "ai-run"])
@pytest.mark.parametrize("input_kind", ["directory", "files", "list", "glob"])
def test_cli_validation_collects_errors_from_all_files(tmp_path, capsys, monkeypatch, command, input_kind) -> None:
    dsl_dir = tmp_path / "inputs"
    dsl_dir.mkdir()
    valid_yaml = _suite_yaml("valid", "valid-case")
    contents = {
        "01-variable.yaml": valid_yaml.replace("项目管理>>项目立项", '"{{missing_number}}"'),
        "02-valid.yaml": valid_yaml,
        "03-schema.yaml": valid_yaml.replace("menu_path: 项目管理>>项目立项", "unexpected: true"),
        "04-syntax.yaml": "suite: [\n",
        "05-valid.yaml": valid_yaml,
    }
    for name, content in contents.items():
        (dsl_dir / name).write_text(content, encoding="utf-8")
    paths = [dsl_dir / name for name in contents]
    invalid_paths = [paths[0], paths[2], paths[3]]
    if input_kind == "directory":
        inputs = ["--dsl", str(dsl_dir)]
    elif input_kind == "files":
        inputs = ["--dsl", *(str(path) for path in paths)]
    elif input_kind == "glob":
        inputs = ["--dsl", str(dsl_dir / "*.yaml")]
        invalid_paths = [path for path in cli_module.discover_dsl_files(inputs[1:]) if path in invalid_paths]
    else:
        dsl_list = tmp_path / "suites.txt"
        dsl_list.write_text("\n".join(str(path) for path in paths), encoding="utf-8")
        inputs = ["--dsl-list", str(dsl_list)]
    report_file = tmp_path / "report.json"
    args = ["run" if command == "ai-run" else command, *inputs]
    if command != "validate":
        if command == "run":
            report_file.write_text('{"success": true}', encoding="utf-8")
        args.extend([
            "--template-file", "must-not-be-read-template.json",
            "--runtime-file", "must-not-be-read-runtime.json",
            "--report-file", str(report_file),
        ])
        if command == "ai-run":
            args.append("--ai-observe")

    def unexpected_execution(*args, **kwargs):
        pytest.fail("任一文件校验失败时不得执行任何用例")

    monkeypatch.setattr(cli_module, "_run_suite_specs_in_process", unexpected_execution)
    monkeypatch.setattr(cli_module, "_run_ai_suite_supervised", unexpected_execution)
    exit_code = main(args)

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert exit_code == 1
    assert data["success"] is False
    errors = data["validation_errors"]
    assert [error["dsl_file"] for error in errors] == [str(path) for path in invalid_paths]
    messages = {Path(error["dsl_file"]).name: error["message"] for error in errors}
    assert "未定义 DSL 变量: missing_number" in messages["01-variable.yaml"]
    assert "cases[1].steps[1]" in messages["03-schema.yaml"]
    assert "line 2, column 1" in messages["04-syntax.yaml"]
    assert "3 个文件" in data["error"]
    for path in invalid_paths:
        assert str(path) in captured.err
        assert str(path) in data["error"]
    if command != "validate":
        assert data["first_failure"]["dsl_file"] == str(invalid_paths[0])
        report = json.loads(report_file.read_text(encoding="utf-8"))
        assert report["validation_errors"] == errors
        assert report["totals"] == {"suites": 3, "cases": 3, "passed": 0, "failed": 3, "skipped": 0}
        assert [suite["dsl_file"] for suite in report["suite_reports"]] == [str(path) for path in invalid_paths]
        for suite, error in zip(report["suite_reports"], errors):
            case = suite["case_reports"][0]
            assert case["dsl_file"] == error["dsl_file"]
            assert case["report"]["errors"] == [error["message"]]
        html = report_file.with_suffix(".html").read_text(encoding="utf-8")
        assert all(str(path) in html for path in invalid_paths)
        events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
        event = next(event for event in events if event["event"] == "run_validation_failed")
        assert event["validation_errors"] == errors
        if command == "ai-run":
            assert report["run"]["observation"]["reason_code"] == "dsl_invalid"


def test_cli_doctor_skip_config_checks_runtime_contract(capsys) -> None:
    exit_code = main(["doctor", "--skip-config"])

    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["success"] is True
    assert data["checks"]["cli"]["ok"] is True
    assert data["checks"]["python"]["ok"] is True
    assert "version" in data


def test_cli_doctor_exposes_ai_observation_contract(capsys) -> None:
    exit_code = main(["doctor", "--skip-config"])

    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["tool_version"] == data["version"]
    assert re.fullmatch(r"1\.\d+", data["contract_version"])
    assert set(data["capabilities"]["available"]) == {
        "semantic_events",
        "controlled_timeouts",
        "failure_evidence_bundle",
        "network_text_bodies",
        "network_redaction",
        "request_forward_provenance",
        "case_console_page_errors",
        "table_assertion_snapshot",
        "business_assertion_receipts",
        "notification_request_associations",
        "verification_entrypoint",
        "atomic_evidence_writes",
        "workflow_result",
        "workflow_panel",
        "step_page_observation",
    }


def test_run_parser_accepts_ai_observation_limits() -> None:
    args = cli_module.build_parser().parse_args(
        [
            "run",
            "--ai-observe",
            "--step-timeout-seconds",
            "30",
            "--case-timeout-seconds",
            "60",
            "--run-timeout-seconds",
            "90",
            "--max-network-body-bytes",
            "1024",
            "--max-network-case-bytes",
            "4096",
        ]
    )

    assert args.ai_observe is True
    assert args.step_timeout_seconds == 30
    assert args.case_timeout_seconds == 60
    assert args.run_timeout_seconds == 90
    assert args.max_network_body_bytes == 1024
    assert args.max_network_case_bytes == 4096


def test_run_parser_accepts_window_size() -> None:
    args = cli_module.build_parser().parse_args(["run", "--window-size", "1600x1000"])

    assert args.window_size == (1600, 1000)


def test_failure_pause_accepts_interactive_serial_real_run(monkeypatch) -> None:
    args = cli_module.build_parser().parse_args(
        [
            "run",
            "--dsl",
            "suite.yaml",
            "--pause-on-failure",
            "--no-persistent-profile",
            "--on-case-failure",
            "stop_run",
        ]
    )
    args._explicit_options = {"--pause-on-failure", "--no-persistent-profile", "--on-case-failure"}
    monkeypatch.setattr(cli_module.sys, "stdin", SimpleNamespace(isatty=lambda: True))

    validate = getattr(cli_module, "_validate_failure_pause_args", None)
    assert callable(validate)
    validate(args, fixture_mode=False)


@pytest.mark.parametrize(
    ("options", "fixture_mode", "message"),
    [
        (["--headless"], False, "--headless"),
        (["--template-file", "template.json", "--runtime-file", "runtime.json"], True, "fixture"),
        (["--concurrency", "2"], False, "--concurrency 1"),
        (["--ai-observe"], False, "--ai-observe"),
        (["--performance"], False, "--performance"),
        (["--on-case-failure", "continue"], False, "--on-case-failure stop_run"),
        (["--on-case-failure", "stop_suite"], False, "--on-case-failure stop_run"),
    ],
)
def test_failure_pause_rejects_incompatible_run_modes_before_browser_start(
    options: list[str],
    fixture_mode: bool,
    message: str,
    monkeypatch,
) -> None:
    args = cli_module.build_parser().parse_args(["run", "--dsl", "suite.yaml", "--pause-on-failure", *options])
    args._explicit_options = {
        token.split("=", 1)[0]
        for token in ["--pause-on-failure", *options]
        if token.startswith("--")
    }
    monkeypatch.setattr(cli_module.sys, "stdin", SimpleNamespace(isatty=lambda: True))

    validate = getattr(cli_module, "_validate_failure_pause_args", None)
    assert callable(validate)
    with pytest.raises(ValueError, match=re.escape(message)):
        validate(args, fixture_mode=fixture_mode)


def test_failure_pause_rejects_non_interactive_stdin(monkeypatch) -> None:
    args = cli_module.build_parser().parse_args(["run", "--dsl", "suite.yaml", "--pause-on-failure"])
    args._explicit_options = {"--pause-on-failure"}
    monkeypatch.setattr(cli_module.sys, "stdin", SimpleNamespace(isatty=lambda: False))

    validate = getattr(cli_module, "_validate_failure_pause_args", None)
    assert callable(validate)
    with pytest.raises(ValueError, match="交互式终端"):
        validate(args, fixture_mode=False)


def test_failure_pause_forces_loaded_suites_to_stop_run(tmp_path) -> None:
    dsl_path = tmp_path / "suite.yaml"
    dsl_path.write_text(_suite_yaml("pause-suite", "case-a"), encoding="utf-8")
    args = cli_module.build_parser().parse_args(["run", "--dsl", str(dsl_path), "--pause-on-failure"])

    specs = cli_module._load_suite_specs(args)

    assert [spec.suite.on_case_failure for spec in specs] == ["stop_run"]


def test_failure_pause_ctrl_c_returns_130_without_complete_report(tmp_path, capsys, monkeypatch) -> None:
    env = EnvironmentConfig(
        env_name="ydf",
        base_url="https://example.yonyougov.top",
        sysid="yonbip",
        username="demo",
        password="secret",
    )

    class _ConfigLoader:
        def __init__(self, _path=None) -> None:
            pass

        def get_env(self, _name):
            return env

    monkeypatch.setattr(cli_module.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(cli_module, "ConfigLoader", _ConfigLoader)
    monkeypatch.setattr(cli_module, "_load_suite_specs", lambda *_args, **_kwargs: [object()])
    monkeypatch.setattr(
        cli_module,
        "_run_suite_specs_in_process",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(KeyboardInterrupt()),
    )

    try:
        exit_code = main(
            [
                "run",
                "--dsl",
                "unused.yaml",
                "--pause-on-failure",
                "--report-dir",
                str(tmp_path / "reports"),
            ]
        )
    except KeyboardInterrupt:
        exit_code = None

    assert exit_code == 130
    assert json.loads(capsys.readouterr().out) == {
        "success": False,
        "mode": "failure_pause",
        "exit_reason": "user_interrupt",
    }
    assert list((tmp_path / "reports").rglob("report.json")) == []


@pytest.mark.parametrize("value", ["1600", "1600x", "x1000", "0x1000", "1600x0", "1600X1000", "abc"])
def test_parse_window_size_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError, match="窗口尺寸格式无效"):
        cli_module._parse_window_size(value)


def test_ai_observation_config_uses_contract_defaults() -> None:
    args = cli_module.build_parser().parse_args(["run", "--ai-observe"])

    assert cli_module._ai_observation_config(args) == {
        "step_timeout_seconds": 120,
        "case_timeout_seconds": 900,
        "run_timeout_seconds": 1800,
        "max_network_body_bytes": 10 * 1024 * 1024,
        "max_network_case_bytes": 200 * 1024 * 1024,
    }


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("--step-timeout-seconds", "30"),
        ("--case-timeout-seconds", "60"),
        ("--run-timeout-seconds", "90"),
        ("--max-network-body-bytes", "1024"),
        ("--max-network-case-bytes", "4096"),
    ],
)
def test_ai_observation_options_require_ai_observe(option: str, value: str) -> None:
    args = cli_module.build_parser().parse_args(["run", option, value])

    with pytest.raises(ValueError, match="只允许与 --ai-observe 同时使用"):
        cli_module._ai_observation_config(args)


@pytest.mark.parametrize(
    "options",
    [
        ["--step-timeout-seconds", "0"],
        ["--max-network-body-bytes", "-1"],
        ["--step-timeout-seconds", "61", "--case-timeout-seconds", "60"],
        ["--case-timeout-seconds", "91", "--run-timeout-seconds", "90"],
    ],
)
def test_ai_observation_config_rejects_invalid_limits(options: list[str]) -> None:
    args = cli_module.build_parser().parse_args(["run", "--ai-observe", *options])

    with pytest.raises(ValueError, match="AI 观察参数无效"):
        cli_module._ai_observation_config(args)


def test_cli_ai_observe_rejects_concurrency_with_blocked_report(tmp_path, capsys, monkeypatch) -> None:
    report_file = tmp_path / "report.json"

    def fail_if_loaded(*_args, **_kwargs):
        raise AssertionError("contract preflight must run before DSL loading")

    monkeypatch.setattr(cli_module, "_load_suite_specs", fail_if_loaded)

    exit_code = main(
        [
            "run",
            "--ai-observe",
            "--dsl",
            "unused-suite.yaml",
            "--concurrency",
            "2",
            "--template-file",
            "unused-template.json",
            "--runtime-file",
            "unused-runtime.json",
            "--report-file",
            str(report_file),
        ]
    )

    assert exit_code == 1
    summary = json.loads(capsys.readouterr().out)
    assert summary["success"] is False
    report = json.loads(report_file.read_text(encoding="utf-8"))
    assert report["run"]["observation"] == {
        "outcome": "blocked",
        "reason_code": "contract_incompatible",
        "operation_reason": "ai_observe_concurrency_unsupported",
    }


def test_prepare_report_paths_creates_ai_artifacts_directory(tmp_path) -> None:
    report_file = tmp_path / "run-a" / "report.json"
    args = cli_module.build_parser().parse_args(
        ["run", "--ai-observe", "--dsl", "suite.yaml", "--report-file", str(report_file)]
    )

    actual_report, events_file = cli_module._prepare_report_paths(args, "run-1")

    assert actual_report == report_file
    assert events_file == report_file.parent / "events.jsonl"
    assert (report_file.parent / "artifacts").is_dir()


def test_prepare_report_paths_refuses_to_overwrite_ai_evidence(tmp_path) -> None:
    report_file = tmp_path / "run-a" / "report.json"
    report_file.parent.mkdir()
    report_file.write_text('{"success": true}', encoding="utf-8")
    args = cli_module.build_parser().parse_args(
        ["run", "--ai-observe", "--dsl", "suite.yaml", "--report-file", str(report_file)]
    )

    with pytest.raises(ValueError, match="AI 观察证据目录已存在"):
        cli_module._prepare_report_paths(args, "run-2")

    assert json.loads(report_file.read_text(encoding="utf-8")) == {"success": True}


def test_prepare_report_paths_keeps_normal_mode_overwrite_compatibility(tmp_path) -> None:
    report_file = tmp_path / "report.json"
    report_file.write_text('{"success": true}', encoding="utf-8")
    args = cli_module.build_parser().parse_args(["run", "--dsl", "suite.yaml", "--report-file", str(report_file)])

    actual_report, events_file = cli_module._prepare_report_paths(args, "run-1")

    assert actual_report == report_file
    assert events_file == tmp_path / "events.jsonl"


def test_cli_doctor_treats_forward_target_http_error_as_reachable(monkeypatch, capsys) -> None:
    def fake_urlopen(url, timeout):
        raise urllib.error.HTTPError(url, 404, "Not Found", hdrs=None, fp=None)

    monkeypatch.setattr(cli_module.urllib.request, "urlopen", fake_urlopen)

    exit_code = main(["doctor", "--skip-config", "--forward-target", "http://127.0.0.1:62871"])

    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["checks"]["forward_targets"]["ok"] is True
    assert data["checks"]["forward_targets"]["targets"][0]["status"] == 404


def test_doctor_config_check_reports_resolved_config_path(tmp_path, monkeypatch) -> None:
    home = tmp_path / ".ydf-browser"
    config_path = home / "config" / "env.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        """
environments:
  ydf:
    base_url: https://example.yonyougov.top
    sysid: yonbip
    username: user
    password: pass
""",
        encoding="utf-8",
    )
    config_path.with_name("env.local.yaml").write_text(
        """
environments:
  ydf:
    base_url: https://local.yonyougov.top
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("YDF_BROWSER_HOME", str(home))
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)

    result = cli_module._doctor_config_check(None, "ydf")

    assert result["ok"] is True
    assert result["path"] == str(config_path)
    assert result["local_path"] == str(config_path.with_name("env.local.yaml"))
    assert result["local_exists"] is True
    assert result["base_url"] == "https://local.yonyougov.top"


def test_doctor_config_check_reports_missing_default_config_path(tmp_path, monkeypatch) -> None:
    home = tmp_path / ".ydf-browser"
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setenv("YDF_BROWSER_HOME", str(home))
    monkeypatch.chdir(work)

    result = cli_module._doctor_config_check(None, "ydf")

    assert result["ok"] is False
    assert result["path"] == str(home / "config" / "env.yaml")
    assert "配置文件不存在" in result["error"]


def test_cli_module_entrypoint_executes_main(tmp_path, sample_template_payload: dict) -> None:
    template_path = tmp_path / "template.json"
    template_path.write_text(json.dumps(sample_template_payload, ensure_ascii=False), encoding="utf-8")
    project_root = Path(__file__).resolve().parent.parent

    result = subprocess.run(
        [sys.executable, "-m", "ydf_browser.cli", "template", "fetch", str(template_path)],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(project_root),
    )

    assert result.returncode == 0
    assert '"success": true' in result.stdout


def test_build_service_url_uses_service_route() -> None:
    assert (
        build_service_url("https://tv5-ydf.yonyougov.top", "global00_-1_GX_PM3_INIT")
        == "https://tv5-ydf.yonyougov.top/#/service/global00_-1_GX_PM3_INIT"
    )


def test_build_menu_open_urls_prefers_service_route_only() -> None:
    assert build_menu_open_urls(
        "https://tv5-ydf.yonyougov.top",
        {
            "service_code": "global00_-1_GX_PM3_INIT",
            "service_url": "#/YonDiF!bootstrap/yondif-pvdf-fe/ucf-wh/BillRender?code=GX_PM3_INIT",
        },
    ) == ["https://tv5-ydf.yonyougov.top/#/service/global00_-1_GX_PM3_INIT"]


def test_build_login_probe_selectors_cover_username_password_and_submit() -> None:
    selectors = build_login_probe_selectors()

    assert any("邮箱/账号/用户手机号" in item for item in selectors["username"])
    assert any("密码" in item for item in selectors["password"])
    assert any("登录" in item for item in selectors["submit"])


def test_build_accessibility_selector_encodes_role_and_name() -> None:
    assert build_accessibility_selector("button", "新增") == "axrole=button::新增"


def test_should_open_menu_in_new_tab_when_switching_from_home_to_hash_service_route() -> None:
    assert should_open_menu_in_new_tab(
        "https://tv5-ydf.yonyougov.top/",
        "https://tv5-ydf.yonyougov.top/#/service/global00_-1_GX_PM3_INIT",
    )


def test_run_real_case_records_lightweight_setup_timing(monkeypatch) -> None:
    env = EnvironmentConfig(
        env_name="ydf",
        base_url="https://example.yonyougov.top",
        sysid="yonbip",
        username="demo",
        password="secret",
    )
    case = SimpleNamespace(default_org="", user="", steps=[])

    class _Runtime:
        _context = None

        def start(self) -> None:
            self._context = object()

        def clear_visible_cookies(self, _base_url: str) -> None:
            pass

        def close_case_pages(self) -> None:
            pass

    class _Executor:
        def __init__(self, **_kwargs) -> None:
            pass

        def run(self, _steps):
            return ExecutionReport(success=True)

    session = SimpleNamespace(
        cookies=[],
        _ydf_setup_timing={
            "login": {"duration_ms": 3, "success": True},
            "context": {"duration_ms": 4, "success": True},
        },
    )
    monkeypatch.setattr(cli_module, "_login_with_default_org_context", lambda *_args, **_kwargs: session)
    monkeypatch.setattr(cli_module, "YondifGateway", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(cli_module, "WorkflowExecutor", _Executor)

    report = cli_module._run_real_case(
        case,
        env,
        default_org=None,
        headless=True,
        shared_runtime=_Runtime(),
    )

    assert report.timing["setup"]["login"] == {"duration_ms": 3, "success": True}
    assert report.timing["setup"]["context"] == {"duration_ms": 4, "success": True}
    assert report.timing["setup"]["browser_start"]["success"] is True
    assert isinstance(report.timing["setup"]["browser_start"]["duration_ms"], int)


def test_run_real_case_pauses_failed_live_page_before_cleanup_and_records_timing(
    tmp_path,
    capsys,
    monkeypatch,
) -> None:
    env = EnvironmentConfig(
        env_name="ydf",
        base_url="https://example.yonyougov.top",
        sysid="yonbip",
        username="demo",
        password="secret",
    )
    case = SimpleNamespace(code="inspect-failure", name="核对失败现场", default_org="", user="", steps=[object(), object()])
    events: list[str] = []

    class _Stdin:
        @staticmethod
        def isatty() -> bool:
            return True

        @staticmethod
        def readline() -> str:
            assert events == ["execute"]
            events.append("readline")
            return "\n"

    class _Runtime:
        _context = object()

        def clear_visible_cookies(self, _base_url: str) -> None:
            pass

        def has_open_page(self) -> bool:
            return True

        def close_case_pages(self) -> None:
            events.append("close")

    class _Executor:
        def __init__(self, **_kwargs) -> None:
            pass

        def run(self, _steps):
            events.append("execute")
            return ExecutionReport(
                success=False,
                step_results=[
                    StepResult(action="open_menu", success=True, message="菜单已打开", data={"timing": {"duration_ms": 5}}),
                    StepResult(
                        action="table.assert_empty",
                        success=False,
                        message="表格仍有数据",
                        data={
                            "step_index": 2,
                            "error": {"type": "AssertionError", "message": "表格仍有数据"},
                            "timing": {"duration_ms": 7},
                        },
                    ),
                ],
                errors=["表格仍有数据"],
            )

    timestamps = iter(["2026-08-21T10:00:00+08:00", "2026-08-21T10:05:00+08:00"])
    monkeypatch.setattr(cli_module.sys, "stdin", _Stdin())
    monkeypatch.setattr(cli_module, "_now_iso", lambda: next(timestamps))
    monkeypatch.setattr(cli_module, "_login_with_default_org_context", lambda *_args, **_kwargs: SimpleNamespace(cookies=[]))
    monkeypatch.setattr(cli_module, "YondifGateway", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(cli_module, "WorkflowExecutor", _Executor)
    report_file = tmp_path / "report.json"

    report = cli_module._run_real_case(
        case,
        env,
        default_org=None,
        headless=False,
        shared_runtime=_Runtime(),
        pause_on_failure=True,
        report_file=report_file,
    )

    assert events == ["execute", "readline", "close"]
    assert report.success is False
    assert report.step_results[1].data["timing"]["duration_ms"] == 7
    pause = report.timing["failure_pause"]
    assert pause == {
        "case_code": "inspect-failure",
        "step_index": 2,
        "action": "table.assert_empty",
        "started_at": "2026-08-21T10:00:00+08:00",
        "ended_at": "2026-08-21T10:05:00+08:00",
        "duration_ms": pause["duration_ms"],
        "ended_by": "enter",
    }
    assert pause["duration_ms"] >= 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "inspect-failure" in captured.err
    assert "核对失败现场" in captured.err
    assert "step=2" in captured.err
    assert "table.assert_empty" in captured.err
    assert "表格仍有数据" in captured.err
    assert str(report_file) in captured.err
    assert "Enter" in captured.err


def test_failure_pause_ends_when_failed_page_is_closed_without_enter(tmp_path, capsys, monkeypatch) -> None:
    case = SimpleNamespace(code="inspect-close", name="关闭失败现场")
    report = ExecutionReport(
        success=False,
        step_results=[
            StepResult(
                action="notification.assert",
                success=False,
                message="页面断言失败",
                data={"step_index": 2, "error": {"type": "AssertionError", "message": "页面断言失败"}},
            )
        ],
        errors=["页面断言失败"],
    )

    class _Stdin:
        @staticmethod
        def readline() -> str:
            time.sleep(0.2)
            return "\n"

    class _ClosedRuntime:
        @staticmethod
        def has_open_page() -> bool:
            return False

    monkeypatch.setattr(cli_module.sys, "stdin", _Stdin())

    cli_module._pause_failed_case(case, report, tmp_path / "report.json", _ClosedRuntime())

    assert report.timing["failure_pause"]["ended_by"] == "browser_closed"
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "关闭浏览器" in captured.err


def test_run_real_case_does_not_pause_failed_case_without_live_page(monkeypatch) -> None:
    env = EnvironmentConfig(
        env_name="ydf",
        base_url="https://example.yonyougov.top",
        sysid="yonbip",
        username="demo",
        password="secret",
    )
    case = SimpleNamespace(code="closed-page", name="页面已关闭", default_org="", user="", steps=[object()])
    events: list[str] = []

    class _Stdin:
        @staticmethod
        def readline() -> str:
            raise AssertionError("没有活页面时不得等待 stdin")

    class _Runtime:
        _context = object()

        def clear_visible_cookies(self, _base_url: str) -> None:
            pass

        def has_open_page(self) -> bool:
            return False

        def close_case_pages(self) -> None:
            events.append("close")

    class _Executor:
        def __init__(self, **_kwargs) -> None:
            pass

        def run(self, _steps):
            return ExecutionReport(
                success=False,
                step_results=[StepResult(action="open_menu", success=False, message="页面已关闭")],
                errors=["页面已关闭"],
            )

    monkeypatch.setattr(cli_module.sys, "stdin", _Stdin())
    monkeypatch.setattr(cli_module, "_login_with_default_org_context", lambda *_args, **_kwargs: SimpleNamespace(cookies=[]))
    monkeypatch.setattr(cli_module, "YondifGateway", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(cli_module, "WorkflowExecutor", _Executor)

    report = cli_module._run_real_case(
        case,
        env,
        default_org=None,
        headless=False,
        shared_runtime=_Runtime(),
        pause_on_failure=True,
        report_file=Path("report.json"),
    )

    assert report.success is False
    assert "failure_pause" not in report.timing
    assert events == ["close"]


def test_run_real_case_preserves_setup_timing_when_login_fails(monkeypatch) -> None:
    env = EnvironmentConfig(
        env_name="ydf",
        base_url="https://example.yonyougov.top",
        sysid="yonbip",
        username="demo",
        password="secret",
    )
    case = SimpleNamespace(default_org="", user="", steps=[])

    class _Runtime:
        _context = None

        def start(self) -> None:
            self._context = object()

        def clear_visible_cookies(self, _base_url: str) -> None:
            pass

        def close_case_pages(self) -> None:
            pass

    def fail_login(*_args, **_kwargs):
        raise RuntimeError("登录失败")

    monkeypatch.setattr(cli_module, "_login_with_default_org_context", fail_login)

    report = cli_module._run_real_case(
        case,
        env,
        default_org=None,
        headless=True,
        shared_runtime=_Runtime(),
    )

    assert report.success is False
    assert report.errors == ["登录失败"]
    assert report.timing["setup"]["browser_start"]["success"] is True
    assert report.timing["setup"]["login"]["success"] is False
    assert report.timing["setup"]["login"]["error"] == {
        "type": "RuntimeError",
        "message": "登录失败",
    }


def test_run_real_case_resolves_first_menu_once_after_context_setup(monkeypatch) -> None:
    env = EnvironmentConfig(
        env_name="ydf",
        base_url="https://example.yonyougov.top",
        sysid="yonbip",
        username="demo",
        password="secret",
    )
    case = SimpleNamespace(
        default_org="049002",
        user="",
        steps=[SimpleNamespace(kind="page", action="open_menu", params={"menu_path": "项目管理>>项目立项"})],
    )
    events: list[str] = []

    class _Runtime:
        _context = object()

        def clear_visible_cookies(self, _base_url: str) -> None:
            pass

        def close_case_pages(self) -> None:
            pass

    class _Gateway:
        def resolve_menu(self, menu_path: str):
            events.append(f"resolve:{menu_path}")
            return object()

    class _Executor:
        def __init__(self, gateway, **_kwargs) -> None:
            self.gateway = gateway

        def run(self, steps):
            self.gateway.resolve_menu(steps[0].params["menu_path"])
            return ExecutionReport(success=True)

    def login_with_context(*_args, menu_path=None, **_kwargs):
        assert menu_path is None
        events.append("context-ready")
        return SimpleNamespace(cookies=[])

    monkeypatch.setattr(cli_module, "_login_with_default_org_context", login_with_context)
    monkeypatch.setattr(cli_module, "YondifGateway", lambda *_args, **_kwargs: _Gateway())
    monkeypatch.setattr(cli_module, "WorkflowExecutor", _Executor)

    report = cli_module._run_real_case(
        case,
        env,
        default_org=None,
        headless=True,
        fiscal_year="2027",
        shared_runtime=_Runtime(),
    )

    assert report.success is True
    assert events == ["context-ready", "resolve:项目管理>>项目立项"]


def _stub_session_reuse(monkeypatch):
    # These CLI lifecycle tests isolate authentication; the real preparation and
    # persistence contract is exercised in test_session_reuse.py.
    from contextlib import contextmanager

    @contextmanager
    def case(self, env, **context):
        yield cli_module._login_with_default_org_context(env, **context)

    monkeypatch.setattr(cli_module.SessionReuse, "case", case)
    monkeypatch.setattr(cli_module, "CookieBridge", lambda *args: None)


def test_cli_ocr_install_authorization_is_scoped(monkeypatch, capsys):
    monkeypatch.delenv('YDF_BROWSER_INSTALL_OCR', raising=False)
    seen = []
    def login(args):
        seen.append(os.environ.get('YDF_BROWSER_INSTALL_OCR'))
        return 0
    monkeypatch.setattr(cli_module, '_cmd_login', login)
    assert main(['--install-ocr', 'login']) == 0
    assert main(['login']) == 0
    assert seen == ['1', None]
    assert 'YDF_BROWSER_INSTALL_OCR' not in os.environ

@pytest.mark.parametrize('value', ['[]', '{"path":"root"}', '{"limit":501}', '{"offset":true}', '{"selector":"li"}', '{"path":[""]}'])
def test_reference_exploration_rejects_invalid_options(value):
    args = cli_module.build_parser().parse_args(['run', '--ai-observe', '--explore-reference', value])
    with pytest.raises(ValueError):
        cli_module._ai_observation_config(args)


def test_reference_exploration_requires_opt_in_and_validates_target():
    parser = cli_module.build_parser()
    args = parser.parse_args(['run', '--explore-reference', '{}'])
    with pytest.raises(ValueError, match='ai-observe'):
        cli_module._ai_observation_config(args)
    args = parser.parse_args(['run', '--ai-observe', '--explore-reference', '{"title":"参照","path":["01 分类"]}'])
    assert cli_module._ai_observation_config(args)['reference_exploration']['path'] == ['01 分类']
