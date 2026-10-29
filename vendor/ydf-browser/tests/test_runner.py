from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from ydf_browser.dsl import load_dsl_document
from ydf_browser.models import ExecutionReport, StepResult
from ydf_browser.runner import (
    SuiteRunSpec,
    _safe_path_part,
    archive_diagnostic_files,
    discover_dsl_files,
    filter_cases,
    run_suite_specs,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("", "unknown"), (".", "unknown"), ("..", "unknown"), ("report.v1", "report.v1")],
)
def test_safe_path_part_rejects_dot_segments_but_keeps_filename_dots(value: str, expected: str) -> None:
    assert _safe_path_part(value) == expected


def _write_dsl(path: Path, suite_code: str, *case_codes: str, policy: str = "continue") -> None:
    cases = "\n".join(
        f"""
  - code: {case_code}
    name: 用例 {case_code}
    tags: [smoke]
    steps:
      - action: open_menu
        menu_path: 项目管理>>项目立项
"""
        for case_code in case_codes
    )
    path.write_text(
        f"""
suite:
  code: {suite_code}
  name: 测试集 {suite_code}
  tenant: 财政一体化
  default_org: "049002"
  on_case_failure: {policy}
cases:
{cases}
""",
        encoding="utf-8",
    )


def test_discover_dsl_files_expands_directories_globs_and_deduplicates(tmp_path: Path) -> None:
    dsl_dir = tmp_path / "dsl"
    nested = dsl_dir / "nested"
    nested.mkdir(parents=True)
    first = dsl_dir / "a.yaml"
    second = dsl_dir / "b.yml"
    third = nested / "c.json"
    ignored = dsl_dir / "notes.txt"
    for path in (first, second, third, ignored):
        path.write_text("{}", encoding="utf-8")

    discovered = discover_dsl_files([str(dsl_dir), str(dsl_dir / "*.yaml"), str(first)])

    assert discovered == [first, second, third]


def test_discover_dsl_files_preserves_explicit_file_order(tmp_path: Path) -> None:
    first = tmp_path / "b.yaml"
    second = tmp_path / "a.yaml"
    for path in (first, second):
        path.write_text("{}", encoding="utf-8")

    discovered = discover_dsl_files([str(first), str(second)])

    assert discovered == [first, second]


def test_discover_dsl_files_deduplicates_at_first_position(tmp_path: Path) -> None:
    first = tmp_path / "b.yaml"
    second = tmp_path / "a.yaml"
    for path in (first, second):
        path.write_text("{}", encoding="utf-8")

    discovered = discover_dsl_files([str(first), str(second), str(first)])

    assert discovered == [first, second]


def test_discover_dsl_files_preserves_input_group_order_and_sorts_group_contents(tmp_path: Path) -> None:
    setup = tmp_path / "m-setup.yaml"
    cleanup = tmp_path / "a-cleanup.yaml"
    suite_dir = tmp_path / "suites"
    suite_dir.mkdir()
    suite_b = suite_dir / "b.yaml"
    suite_a = suite_dir / "a.yaml"
    for path in (setup, cleanup, suite_b, suite_a):
        path.write_text("{}", encoding="utf-8")

    discovered = discover_dsl_files([str(setup), str(suite_dir), str(cleanup)])

    assert discovered == [setup, suite_a, suite_b, cleanup]


def test_filter_cases_supports_exact_glob_grep_and_tags() -> None:
    document = load_dsl_document(
        {
            "suite": {"code": "suite-a", "name": "测试集", "tenant": "财政一体化", "default_org": "049002"},
            "cases": [
                {
                    "code": "create-project",
                    "name": "新增项目",
                    "tags": ["create", "smoke"],
                    "steps": [{"action": "open_menu", "menu_path": "项目管理>>项目立项"}],
                },
                {
                    "code": "export-project",
                    "name": "导出项目",
                    "tags": ["export"],
                    "steps": [{"action": "open_menu", "menu_path": "项目管理>>项目立项"}],
                },
            ],
        }
    )

    assert [case.code for case in filter_cases(document.cases, case_codes=["create-project"])] == ["create-project"]
    assert [case.code for case in filter_cases(document.cases, case_globs=["export-*"])] == ["export-project"]
    assert [case.code for case in filter_cases(document.cases, grep="新增")] == ["create-project"]
    assert [case.code for case in filter_cases(document.cases, tags=["smoke"])] == ["create-project"]


def test_run_suite_specs_uses_concurrency_and_records_report_metadata(tmp_path: Path) -> None:
    dsl_path = tmp_path / "suite.yaml"
    _write_dsl(dsl_path, "suite-a", "case-a", "case-b")
    document = load_dsl_document(dsl_path.read_text(encoding="utf-8"))
    active = 0
    max_active = 0
    lock = threading.Lock()

    def _run_case(spec):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return ExecutionReport(
            success=True,
            step_results=[StepResult(action="open_menu", success=True, message=spec.case.code)],
        )

    result = run_suite_specs(
        [SuiteRunSpec(dsl_path=dsl_path, suite=document.suite, cases=document.cases)],
        run_case=_run_case,
        concurrency=2,
        run_id="test-run",
        started_at="2026-05-03T10:00:00+08:00",
        metadata={"env": "ydf"},
    )

    assert result["success"] is True
    assert result["run"]["id"] == "test-run"
    assert result["run"]["env"] == "ydf"
    assert result["totals"] == {"suites": 1, "cases": 2, "passed": 2, "failed": 0, "skipped": 0}
    assert [item["status"] for item in result["suite_reports"][0]["case_reports"]] == ["passed", "passed"]
    assert max_active == 2


def test_run_suite_specs_copies_execution_performance_to_case_report(tmp_path: Path) -> None:
    dsl_path = tmp_path / "suite.yaml"
    _write_dsl(dsl_path, "suite-a", "case-a")
    document = load_dsl_document(dsl_path.read_text(encoding="utf-8"))

    def _run_case(_spec):
        return ExecutionReport(
            success=True,
            step_results=[StepResult(action="open_menu", success=True, message="ok")],
            performance={"cache_mode": "cold_ephemeral", "cold": {"duration_ms": 25}},
        )

    result = run_suite_specs(
        [SuiteRunSpec(dsl_path=dsl_path, suite=document.suite, cases=document.cases)],
        run_case=_run_case,
        concurrency=1,
        run_id="test-run",
        started_at="2026-05-03T10:00:00+08:00",
        metadata={},
    )

    case_report = result["suite_reports"][0]["case_reports"][0]
    assert case_report["performance"]["cache_mode"] == "cold_ephemeral"
    assert case_report["report"]["performance"]["cold"]["duration_ms"] == 25


def test_run_suite_specs_copies_bpr_sessions_to_case_report(tmp_path: Path) -> None:
    dsl_path = tmp_path / "suite.yaml"
    _write_dsl(dsl_path, "suite-a", "case-a")
    document = load_dsl_document(dsl_path.read_text(encoding="utf-8"))

    def _run_case(_spec):
        return ExecutionReport(
            success=True,
            step_results=[StepResult(action="bpr.stop", success=True, message="ok")],
            bpr_sessions=[
                {
                    "index": 1,
                    "name": "修改",
                    "bpr_id": "fake-bpr",
                    "start_step": 2,
                    "end_step": 2,
                    "range": "step 2",
                    "actions": [{"step_index": 2, "action": "toolbar.click"}],
                    "report_url": "https://example.yonyougov.top/iuap-ymc-server/proxy/server/bpr/open?pk=fake",
                    "success": True,
                }
            ],
        )

    result = run_suite_specs(
        [SuiteRunSpec(dsl_path=dsl_path, suite=document.suite, cases=document.cases)],
        run_case=_run_case,
        concurrency=1,
        run_id="test-run",
        started_at="2026-05-03T10:00:00+08:00",
        metadata={},
    )

    case_report = result["suite_reports"][0]["case_reports"][0]
    assert case_report["bpr_sessions"][0]["bpr_id"] == "fake-bpr"
    assert case_report["report"]["bpr_sessions"][0]["range"] == "step 2"


@pytest.mark.parametrize(
    ("outcome", "reason_code", "success"),
    [
        ("passed", None, True),
        ("assertion_failed", "assertion_mismatch", False),
        ("blocked", "target_unavailable", False),
        ("terminated", "timeout", False),
    ],
)
def test_run_suite_specs_aggregates_ai_observation_outcome(
    tmp_path: Path,
    outcome: str,
    reason_code: str | None,
    success: bool,
) -> None:
    dsl_path = tmp_path / "suite.yaml"
    _write_dsl(dsl_path, "suite-a", "case-a")
    document = load_dsl_document(dsl_path.read_text(encoding="utf-8"))
    observation = {"outcome": outcome, "evidence_refs": []}
    if reason_code:
        observation["reason_code"] = reason_code

    result = run_suite_specs(
        [SuiteRunSpec(dsl_path=dsl_path, suite=document.suite, cases=document.cases)],
        run_case=lambda _spec: ExecutionReport(
            success=success,
            step_results=[
                StepResult(
                    action="table.assert_empty",
                    success=success,
                    message=outcome,
                    observation=observation,
                )
            ],
        ),
        concurrency=1,
    )

    case_report = result["suite_reports"][0]["case_reports"][0]
    assert case_report["observation"] == observation
    assert result["run"]["observation"] == observation


@pytest.mark.parametrize("outcome", ["assertion_failed", "blocked"])
@pytest.mark.parametrize(
    ("policy", "expected_statuses"),
    [
        ("continue", ["failed", "passed"]),
        ("stop_suite", ["failed", "skipped"]),
        ("stop_run", ["failed", "skipped"]),
    ],
)
def test_run_suite_specs_applies_failure_policy_to_ai_outcomes(
    tmp_path: Path,
    outcome: str,
    policy: str,
    expected_statuses: list[str],
) -> None:
    dsl_path = tmp_path / "suite.yaml"
    _write_dsl(dsl_path, "suite-a", "case-a", "case-b", policy=policy)
    document = load_dsl_document(dsl_path.read_text(encoding="utf-8"))

    def _run_case(spec):
        success = spec.case.code == "case-b"
        return ExecutionReport(
            success=success,
            step_results=[
                StepResult(
                    action="table.assert_empty",
                    success=success,
                    message=spec.case.code,
                    observation={
                        "outcome": "passed" if success else outcome,
                        "evidence_refs": [],
                    },
                )
            ],
        )

    result = run_suite_specs(
        [SuiteRunSpec(dsl_path=dsl_path, suite=document.suite, cases=document.cases)],
        run_case=_run_case,
        concurrency=1,
    )

    assert [item["status"] for item in result["suite_reports"][0]["case_reports"]] == expected_statuses


def test_run_suite_specs_honors_stop_suite_failure_policy(tmp_path: Path) -> None:
    dsl_path = tmp_path / "suite.yaml"
    _write_dsl(dsl_path, "suite-a", "case-a", "case-b", "case-c", policy="stop_suite")
    document = load_dsl_document(dsl_path.read_text(encoding="utf-8"))

    def _run_case(spec):
        return ExecutionReport(
            success=spec.case.code != "case-b",
            step_results=[StepResult(action="open_menu", success=spec.case.code != "case-b", message=spec.case.code)],
            errors=[] if spec.case.code != "case-b" else ["系统提示: 保存失败"],
        )

    result = run_suite_specs(
        [SuiteRunSpec(dsl_path=dsl_path, suite=document.suite, cases=document.cases)],
        run_case=_run_case,
        concurrency=3,
        run_id="test-run",
        started_at="2026-05-03T10:00:00+08:00",
        metadata={},
    )

    case_reports = result["suite_reports"][0]["case_reports"]
    assert result["success"] is False
    assert [item["status"] for item in case_reports] == ["passed", "failed", "skipped"]
    assert case_reports[2]["skip_reason"] == "suite stopped after failed case: case-b"


def test_run_suite_specs_honors_stop_run_failure_policy(tmp_path: Path) -> None:
    first_path = tmp_path / "first.yaml"
    second_path = tmp_path / "second.yaml"
    _write_dsl(first_path, "suite-a", "case-a", policy="stop_run")
    _write_dsl(second_path, "suite-b", "case-b", policy="continue")
    first_doc = load_dsl_document(first_path.read_text(encoding="utf-8"))
    second_doc = load_dsl_document(second_path.read_text(encoding="utf-8"))

    def _run_case(_spec):
        return ExecutionReport(
            success=False,
            step_results=[StepResult(action="open_menu", success=False, message="没有找到指定的按钮")],
            errors=["没有找到指定的按钮"],
        )

    result = run_suite_specs(
        [
            SuiteRunSpec(dsl_path=first_path, suite=first_doc.suite, cases=first_doc.cases),
            SuiteRunSpec(dsl_path=second_path, suite=second_doc.suite, cases=second_doc.cases),
        ],
        run_case=_run_case,
        concurrency=2,
        run_id="test-run",
        started_at="2026-05-03T10:00:00+08:00",
        metadata={},
    )

    assert result["success"] is False
    assert result["totals"] == {"suites": 2, "cases": 2, "passed": 0, "failed": 1, "skipped": 1}
    assert result["suite_reports"][1]["case_reports"][0]["status"] == "skipped"
    assert result["suite_reports"][1]["case_reports"][0]["skip_reason"] == "run stopped after failed case: case-a"


def test_archive_diagnostic_files_copies_failed_step_artifacts_into_report_dir(tmp_path: Path) -> None:
    screenshot = tmp_path / "ydf-browser-toolbar-action-missing.png"
    screenshot.write_text("png-bytes", encoding="utf-8")
    result = {
        "suite_reports": [
            {
                "suite": {"code": "suite-a"},
                "case_reports": [
                    {
                        "case": {"code": "case-a"},
                        "report": {
                            "step_results": [
                                {
                                    "success": False,
                                    "data": {"diagnostic_files": [str(screenshot), str(tmp_path / "missing.png")]},
                                }
                            ]
                        },
                    }
                ],
            }
        ]
    }

    archive_diagnostic_files(result, tmp_path / "report")

    archived = result["suite_reports"][0]["case_reports"][0]["report"]["step_results"][0]["data"][
        "archived_diagnostic_files"
    ]
    archived_path = Path(archived[0])
    assert archived_path.read_text(encoding="utf-8") == "png-bytes"
    assert archived_path.parent.name == "case-a"
    assert len(archived) == 1
