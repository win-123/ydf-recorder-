
from __future__ import annotations

from copy import deepcopy
import threading
import time

import pytest

from ydf_browser.dsl import load_dsl_document
from ydf_browser.executor import WorkflowExecutor
from ydf_browser.models import DslTestCase, DslTestSuite
from ydf_browser.runner import SuiteRunSpec, run_suite_specs
from ydf_browser.variables import RuntimeVariableContext, resolve_variables
from test_executor import FakeGateway, FakeRuntime


def _suite_payload(steps, *, cases=None):
    return {
        "suite": {"code": "suite", "name": "测试集", "tenant": "财政一体化", "default_org": "049002"},
        "cases": cases
        or [
            {
                "code": "case",
                "name": "用例",
                "user": "默认用户",
                "steps": steps,
            }
        ],
    }


def test_resolve_variables_preserves_declared_runtime_variables() -> None:
    payload = {"value": "{{project.code}}", "label": "编码-{{project.code}}"}

    resolved = resolve_variables(payload, runtime_variables={"project.code"})

    assert resolved == payload


def test_resolve_variables_rejects_undeclared_runtime_variable() -> None:
    with pytest.raises(ValueError) as exc:
        resolve_variables({"value": "{{project.code}}"})

    assert "未定义 DSL 变量: project.code" in str(exc.value)


def test_runtime_variable_context_supports_dotted_names() -> None:
    context = RuntimeVariableContext()

    context.set("project.code", "3600001")

    assert context.has("project.code")
    assert context.get("project.code") == "3600001"
    assert context.snapshot() == {"project": {"code": "3600001"}}


def test_load_dsl_document_accepts_table_capture_and_delayed_reference() -> None:
    document = load_dsl_document(
        _suite_payload(
            [
                {
                    "component": "table",
                    "operation": "capture_row_values",
                    "target": {
                        "match": {"column": "项目名称", "equals": "ys测试{{random.suffix}}"},
                        "capture": {"yjxm.project_code": "项目代码"},
                    },
                },
                {
                    "component": "table_row_selection",
                    "operation": "select",
                    "target": {"match": {"column": "项目代码", "equals": "{{yjxm.project_code}}"}},
                },
            ]
        )
    )

    assert document.suite.runtime_variables == ["yjxm.project_code"]
    assert document.suite.requires_runtime_serial is True
    assert document.cases[0].steps[1].target["match"]["equals"] == "{{yjxm.project_code}}"


def test_load_dsl_document_accepts_form_capture_and_delayed_reference() -> None:
    document = load_dsl_document(
        _suite_payload(
            [
                {
                    "component": "form",
                    "operation": "capture_values",
                    "target": {"capture": {"tel": "手机号"}},
                },
                {
                    "component": "table_row_selection",
                    "operation": "select",
                    "target": {"match": {"column": "手机号", "equals": "{{tel}}"}},
                },
            ]
        )
    )

    assert document.suite.runtime_variables == ["tel"]
    assert document.suite.requires_runtime_serial is True
    assert document.cases[0].steps[1].target["match"]["equals"] == "{{tel}}"


def test_load_dsl_document_rejects_table_capture_without_capture() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            _suite_payload(
                [
                    {
                        "component": "table",
                        "operation": "capture_row_values",
                        "target": {"match": {"column": "项目名称", "equals": "ys测试"}},
                    }
                ]
            )
        )

    assert "缺少 target.capture" in str(exc.value)


def test_load_dsl_document_rejects_random_capture_namespace() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            _suite_payload(
                [
                    {
                        "component": "table",
                        "operation": "capture_row_values",
                        "target": {
                            "match": {"column": "项目名称", "equals": "ys测试"},
                            "capture": {"random.suffix": "项目代码"},
                        },
                    }
                ]
            )
        )

    assert "random 为系统保留变量命名空间" in str(exc.value)


def test_load_dsl_document_rejects_capture_external_variable_conflict() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            _suite_payload(
                [
                    {
                        "component": "table",
                        "operation": "capture_row_values",
                        "target": {
                            "match": {"column": "项目名称", "equals": "ys测试"},
                            "capture": {"project.code": "项目代码"},
                        },
                    }
                ]
            ),
            variables={"project": {"code": "external"}},
        )

    assert "捕获变量不能与外部变量重名: project.code" in str(exc.value)


def _template_with_project_name_column(sample_template_payload: dict) -> dict:
    template = deepcopy(sample_template_payload)
    table_children = template["data"]["uidata"][0]["children"][3]["children"]
    table_children.append(
        {
            "key": "project_name_col",
            "divCode": "project_name_col",
            "nodeType": "column",
            "label": "项目名称",
            "name": "TableColumn",
            "dataField": "projectName",
        }
    )
    return template


def test_workflow_executor_captures_table_row_value_and_reuses_it(sample_template_payload, sample_runtime_elements) -> None:
    template = _template_with_project_name_column(sample_template_payload)
    runtime = FakeRuntime(sample_runtime_elements, table_column_values={"项目代码": ["3600001"], "项目名称": ["ys测试001"]})
    context = RuntimeVariableContext()
    executor = WorkflowExecutor(
        gateway=FakeGateway(template),
        runtime=runtime,
        runtime_variables={"yjxm.project_code"},
        runtime_context=context,
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table",
                "operation": "capture_row_values",
                "target": {
                    "match": {"column": "项目名称", "equals": "ys测试001"},
                    "capture": {"yjxm.project_code": "项目代码"},
                },
            },
            {
                "component": "table_row_selection",
                "operation": "select",
                "target": {"match": {"column": "项目代码", "equals": "{{yjxm.project_code}}"}},
            },
        ]
    )

    assert report.success is True
    assert context.get("yjxm.project_code") == "3600001"
    assert report.step_results[1].data["captured"] == {"yjxm.project_code": "3600001"}
    assert runtime.selected_rows[-1]["equals"] == "3600001"


def test_workflow_executor_captures_form_value_and_reuses_it(sample_template_payload, sample_runtime_elements) -> None:
    runtime = FakeRuntime(sample_runtime_elements, field_values={"project_code": "15500100121"})
    context = RuntimeVariableContext()
    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=runtime,
        runtime_variables={"tel"},
        runtime_context=context,
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "form",
                "operation": "capture_values",
                "target": {"capture": {"tel": "项目编码"}},
            },
            {
                "component": "table_row_selection",
                "operation": "select",
                "target": {"match": {"column": "项目代码", "equals": "{{tel}}"}},
            },
        ]
    )

    assert report.success is True
    assert context.get("tel") == "15500100121"
    assert report.step_results[1].action == "form.capture_values"
    assert report.step_results[1].data["captured"] == {"tel": "15500100121"}
    assert report.step_results[1].data["capture_sources"] == {"tel": "项目编码"}
    assert report.step_results[1].data["fields"][0]["fieldid"] == "project_code"
    assert runtime.selected_rows[-1]["equals"] == "15500100121"


def test_workflow_executor_form_capture_empty_value_does_not_write_partial_values(
    sample_template_payload, sample_runtime_elements
) -> None:
    runtime = FakeRuntime(sample_runtime_elements, field_values={"project_code": "15500100121"})
    context = RuntimeVariableContext()
    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=runtime,
        runtime_variables={"tel", "name"},
        runtime_context=context,
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "form",
                "operation": "capture_values",
                "target": {"capture": {"tel": "项目编码", "name": "项目名称"}},
            },
        ]
    )

    assert report.success is False
    assert "捕获值为空" in report.errors[0]
    assert context.has("tel") is False
    assert context.has("name") is False


def test_workflow_executor_form_capture_unbound_field_fails(sample_template_payload, sample_runtime_elements) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=runtime,
        runtime_variables={"tel"},
        runtime_context=RuntimeVariableContext(),
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "form",
                "operation": "capture_values",
                "target": {"capture": {"tel": "手机号"}},
            },
        ]
    )

    assert report.success is False
    assert "手机号" in report.errors[0]


def test_workflow_executor_fails_before_interaction_when_runtime_variable_missing(sample_template_payload, sample_runtime_elements) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=runtime,
        runtime_variables={"yjxm.project_code"},
        runtime_context=RuntimeVariableContext(),
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table_row_selection",
                "operation": "select",
                "target": {"match": {"column": "项目代码", "equals": "{{yjxm.project_code}}"}},
            },
        ]
    )

    assert report.success is False
    assert "未定义运行期变量: yjxm.project_code" in report.errors[0]
    assert runtime.selected_rows == []


def test_runner_serializes_runtime_variable_suite_cases(tmp_path) -> None:
    suite = DslTestSuite(
        code="serial",
        name="串行测试集",
        tenant="财政一体化",
        default_org="049002",
        runtime_variables=["project.code"],
        requires_runtime_serial=True,
    )
    cases = [DslTestCase(code=f"case{i}", name=f"用例{i}", default_org="049002") for i in range(3)]
    spec = SuiteRunSpec(dsl_path=tmp_path / "serial.yaml", suite=suite, cases=cases)
    running = 0
    max_running = 0
    lock = threading.Lock()

    def run_case(case_spec):
        nonlocal running, max_running
        assert case_spec.runtime_context is not None
        with lock:
            running += 1
            max_running = max(max_running, running)
        time.sleep(0.02)
        with lock:
            running -= 1
        from ydf_browser.models import ExecutionReport

        return ExecutionReport(success=True)

    result = run_suite_specs([spec], run_case=run_case, concurrency=3)

    assert result["success"] is True
    assert max_running == 1
