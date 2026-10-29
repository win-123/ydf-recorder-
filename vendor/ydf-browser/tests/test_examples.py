from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from posixpath import isabs as is_posix_abs
from typing import Any

from ydf_browser.action_completion import (
    ActionCompletionObservation,
    ActionCompletionRequest,
    ActionNotification,
)
from ydf_browser.dsl import load_dsl_document_from_file
from ydf_browser.executor import WorkflowExecutor
from ydf_browser.gateway import MenuTarget


ROOT = Path(__file__).resolve().parents[1]
PAYEE_SUITE = ROOT / "examples" / "payee_account_management_regression.yaml"
PAYEE_MENU_PATH = "集中支付>>基础管理>>收款人账户管理"
QUERY_RESET_SUITE = ROOT / "examples" / "query_reset.yaml"
FUND_COUNTERPART_SUITE = ROOT / "examples" / "fund_counterpart_contract_v1.yaml"
WORKFLOW_RESULT_SUITE = ROOT / "examples" / "workflow_batch_result.yaml"


def test_material_reference_query_real_case_keeps_unsaved_assertions_and_repeat_query() -> None:
    document = load_dsl_document_from_file(
        ROOT / 'tests/real_cases/material_apply_reference_query_performance.yaml',
        variables={'tenant': '测试租户', 'user': '测试用户', 'default_org': '测试组织'},
    )
    reference, query = document.cases
    assert reference.steps[-1].operation == 'assert_row_values'
    assert reference.steps[-2].target['fields']['物资分类'] == {
        'tree': {'label': 'A05040101 复印纸'}, 'first_available': True,
    }
    assert query.steps[-3].to_dict() == query.steps[-2].to_dict()
    assert query.steps[-1].operation == 'assert_columns'
    assert not any(step.target.get('label') in {'保存', '提交', '保存并提交'}
                   for case in document.cases for step in case.steps)


def test_query_reset_example_sets_condition_before_reset() -> None:
    document = load_dsl_document_from_file(QUERY_RESET_SUITE)

    case = document.cases[0]
    search, reset = case.steps[-2:]
    assert search.component == "query"
    assert search.operation == "search"
    assert search.target == {
        "conditions": [{"field": "付款人账号", "equals": "ydf-browser-reset-check"}]
    }
    assert reset.component == "query"
    assert reset.operation == "reset"
    assert reset.target == {}


def test_workflow_batch_result_example_covers_partial_and_success_paths() -> None:
    document = load_dsl_document_from_file(WORKFLOW_RESULT_SUITE)

    assert [case.code for case in document.cases] == ["partial-failure", "all-success"]
    partial_operations = [(step.component, step.operation) for step in document.cases[0].steps if step.component]
    assert partial_operations == [
        ("toolbar", "click"),
        ("workflow_result", "assert"),
        ("workflow_result", "details"),
        ("dialog", "confirm"),
        ("workflow_result", "confirm"),
    ]
    assert document.cases[0].steps[2].target == {"total": 2, "succeeded": 1, "failed": 1}
    assert [(step.component, step.operation) for step in document.cases[1].steps if step.component] == [
        ("toolbar", "click"),
        ("notification", "assert"),
    ]


def test_fund_counterpart_contract_example_is_parameterized_and_cleanup_complete() -> None:
    document = load_dsl_document_from_file(FUND_COUNTERPART_SUITE)

    assert document.suite.tenant == "__PRIVATE_TENANT__"
    case = document.cases[0]
    assert case.user == "__PRIVATE_USER__"
    assert case.default_org == "__PRIVATE_DEFAULT_ORG__"
    operations = [(step.component, step.operation) for step in case.steps if step.component]
    assert operations == [
        ("toolbar", "click"),
        ("form", "fill"),
        ("toolbar", "click"),
        ("query", "search"),
        ("table", "assert_row_values"),
        ("table_row_action", "click"),
        ("form", "fill"),
        ("toolbar", "click"),
        ("query", "search"),
        ("table", "assert_row_values"),
        ("table_row_action", "click"),
        ("query", "search"),
        ("table", "assert_empty"),
    ]
    serialized = "\n".join(str(step.to_dict()) for step in case.steps)
    assert serialized.count("{{random.suffix}}") >= 10


def test_payee_account_management_example_has_regression_suite_shape() -> None:
    document = load_dsl_document_from_file(PAYEE_SUITE)

    assert document.is_suite is True
    assert document.suite.code == "payee_account_management_regression"
    assert document.suite.name == "收款人账户管理"
    assert [case.code for case in document.cases] == [
        "row-detail",
        "row-edit-cancel",
        "create-empty-save-warning",
        "query-by-account-name",
        "export-selected-row",
        "import-empty-template-failure",
    ]
    assert {case.default_org for case in document.cases} == {"049002"}
    assert all(case.user == "默认用户" for case in document.cases)
    assert all(case.steps[0].to_dict() == {"action": "open_menu", "menu_path": PAYEE_MENU_PATH} for case in document.cases)

    import_case = next(case for case in document.cases if case.code == "import-empty-template-failure")
    import_step = import_case.steps[-1]
    assert import_step.component == "import"
    assert import_step.operation == "upload"
    assert import_step.target["assert"] == {
        "status": "failure",
        "error_contains": "收款人信息不能为空",
    }
    import_file = import_step.target["file"]
    assert not is_posix_abs(import_file)
    assert (ROOT / import_file).is_file()


def test_payee_account_management_example_cases_execute_with_fake_runtime() -> None:
    document = load_dsl_document_from_file(PAYEE_SUITE)

    for case in document.cases:
        runtime = _PayeeRuntime()
        if case.code == "query-by-account-name":
            runtime.table_column_values["账户名称"] = ["Z03"]
        if case.code == "create-empty-save-warning":
            original_click_toolbar_action = runtime.click_toolbar_action

            def click_toolbar_action(label: str, sub_label: str | None = None) -> None:
                original_click_toolbar_action(label, sub_label=sub_label)
                if label == "保存":
                    runtime.notifications = [
                        {"type": "error", "message": "单据检查未通过: 面板-账户名称不能为空 面板-账号不能为空"}
                    ]
                else:
                    runtime.notifications = []

            runtime.click_toolbar_action = click_toolbar_action  # type: ignore[method-assign]
        if case.code == "import-empty-template-failure":
            runtime.next_import_upload_result = {
                "import_results": [
                    {
                        "file": "examples/fixtures/payee_account/收款人账户管理导入模板_1806195728602103815-3.xlsx",
                        "status": "failure",
                        "message": "收款人信息不能为空",
                    }
                ]
            }
        executor = WorkflowExecutor(gateway=_PayeeGateway(), runtime=runtime)

        report = executor.run(case.steps)

        assert report.success is True, case.code


@dataclass
class _PayeeGateway:
    menu_target: MenuTarget = field(
        default_factory=lambda: MenuTarget(
            menu_code="PAYEE_ACCOUNT",
            menu_name="收款人账户管理",
            path=["集中支付", "基础管理", "收款人账户管理"],
            service_code="payee_account",
            page_code="PAYEE_ACCOUNT",
            biz_obj_code="payeeAccount",
        )
    )

    def resolve_menu(self, menu_path: str) -> MenuTarget:
        assert menu_path == PAYEE_MENU_PATH
        return self.menu_target

    def fetch_template(self, menu_target: MenuTarget) -> dict[str, Any]:
        assert menu_target.menu_code == "PAYEE_ACCOUNT"
        return _payee_template()


@dataclass
class _PayeeRuntime:
    menu_opening_work_surfaces = False

    opened_menu: MenuTarget | None = None
    clicked_targets: list[str] = field(default_factory=list)
    row_action_clicks: list[str] = field(default_factory=list)
    focused_rows: list[dict[str, Any]] = field(default_factory=list)
    selected_rows: list[dict[str, Any]] = field(default_factory=list)
    query_filled_fields: list[dict[str, str]] = field(default_factory=list)
    table_column_values: dict[str, list[str]] = field(default_factory=dict)
    notifications: list[dict[str, str]] = field(default_factory=list)
    import_uploads: list[dict[str, Any]] = field(default_factory=list)
    next_import_upload_result: dict[str, Any] = field(default_factory=dict)
    downloaded_files: list[str] = field(default_factory=list)
    action_completion_clock: float = 0.0
    action_completion_active: bool = False

    def _acquire_action_completion(self) -> None:
        if self.action_completion_active:
            raise RuntimeError("已有动作正在等待完成")
        self.action_completion_active = True

    def _release_action_completion(self) -> None:
        self.action_completion_active = False

    def _prepare_action_completion(self, request: ActionCompletionRequest) -> None:
        return

    def _observe_action_completion(
        self,
        request: ActionCompletionRequest,
        stage: str = "",
    ) -> ActionCompletionObservation:
        observation = ActionCompletionObservation(
            notifications=tuple(
                ActionNotification(
                    type=str(item.get("type") or "info"),
                    message=str(item.get("message") or ""),
                )
                for item in self.collect_notifications()
            ),
            dom_signal="fixture_state",
        )
        if stage == "notifications":
            return ActionCompletionObservation(notifications=observation.notifications)
        if stage == "dynamic_template":
            return ActionCompletionObservation()
        if stage == "dom":
            return ActionCompletionObservation(dom_signal=observation.dom_signal)
        return observation

    def _action_completion_now(self) -> float:
        return self.action_completion_clock

    def _wait_action_completion_poll(self, timeout_ms: int) -> None:
        self.action_completion_clock += timeout_ms / 1000

    def open_menu(self, menu_target: MenuTarget) -> None:
        self.opened_menu = menu_target

    def capture_page_state(self) -> None:
        return None

    def capture_open_menu_work_surfaces(self, manifest) -> None:
        return None

    def wait_for_timeout(self, timeout_ms: int) -> None:
        return

    def collect_open_menu_page_errors(self) -> list[dict[str, Any]]:
        return []

    def inspect_menu_hosting(self, menu_target: MenuTarget) -> dict[str, str]:
        return {"mode": "unknown", "reason": "fixture runtime 无真实 frame 证据"}

    def ensure_menu_tab(self, menu_target: MenuTarget) -> None:
        assert menu_target.menu_name == "收款人账户管理"

    def prepare_binding(self, manifest) -> None:
        assert manifest.page.biz_obj_code == "payeeAccount"

    def capture_runtime_elements(self, manifest) -> list[dict[str, Any]]:
        return [
            _runtime_element("accountName", "账户名称", "textbox"),
            _runtime_element("query_btn", "查询", "button"),
            _runtime_element("add_btn", "新增", "button"),
            _runtime_element("save_btn", "保存", "button"),
            _runtime_element("cancel_btn", "取消", "button"),
            _runtime_element("export_btn", "导出", "button"),
            _runtime_element("detail_btn", "详情", "button"),
            _runtime_element("edit_btn", "编辑", "button"),
            _runtime_element("accountName_col", "账户名称", None),
        ]

    def click_toolbar_action(self, label: str, sub_label: str | None = None) -> None:
        self.clicked_targets.append(f"{label}>{sub_label}" if sub_label else label)
        if label == "导出":
            self.downloaded_files.append("/Users/ken/Downloads/收款人账户管理.xlsx")

    def fill_query_field(self, bound_element, value: str) -> None:
        self.query_filled_fields.append({"fieldid": bound_element.candidate.fieldid, "value": value})

    def click_query_action(self, label: str = "查询") -> None:
        self.clicked_targets.append(label)

    def focus_table_row(self, match: dict[str, Any], *, table_scope=None) -> None:
        self.focused_rows.append(match)

    def click_row_action(self, action_label: str) -> None:
        self.row_action_clicks.append(action_label)
        self.clicked_targets.append(action_label)

    def select_table_row(self, match: dict[str, Any], *, table_scope=None) -> None:
        self.selected_rows.append(match)

    def collect_table_column_values(self, column: str, *, table_scope=None) -> list[str]:
        return self.table_column_values.get(column, [])

    def collect_notifications(self) -> list[dict[str, str]]:
        return self.notifications

    def import_upload(self, label: str, files: list[str]) -> dict[str, Any]:
        self.import_uploads.append({"label": label, "files": files})
        if self.next_import_upload_result:
            return self.next_import_upload_result
        return {"import_results": [{"file": file, "status": "success", "message": "导入完成"} for file in files]}


def _payee_template() -> dict[str, Any]:
    return {
        "appCode": "Pay",
        "domainKey": "yondif-fp-be",
        "data": {
            "bizObjCode": "payeeAccount",
            "uidata": [
                {
                    "key": "root",
                    "divCode": "root",
                    "name": "RootPage",
                    "children": [
                        {
                            "key": "toolbar_root",
                            "divCode": "toolbar_root",
                            "nodeType": "toolbar",
                            "label": "按钮工具栏",
                            "parentKey": "root",
                            "children": [],
                        },
                        {
                            "key": "query_box",
                            "divCode": "seachBox",
                            "nodeType": "form",
                            "label": "查询区",
                            "name": "LCDQueryString",
                            "children": [
                                {
                                    "key": "account_name_query",
                                    "divCode": "accountName",
                                    "nodeType": "formItem",
                                    "label": "账户名称",
                                    "name": "TextInput",
                                    "dataField": "accountName",
                                }
                            ],
                        },
                        {
                            "key": "main_table",
                            "divCode": "main_table",
                            "nodeType": "table",
                            "label": "收款人账户表",
                            "children": [
                                {
                                    "key": "account_name_col",
                                    "divCode": "accountName_col",
                                    "nodeType": "column",
                                    "label": "账户名称",
                                    "name": "TableColumn",
                                    "dataField": "accountName",
                                }
                            ],
                        },
                    ],
                }
            ],
            "actionEL": {
                "add": _action("add_btn", "新增"),
                "save": _action("save_btn", "保存"),
                "cancel": _action("cancel_btn", "取消"),
                "export": _action("export_btn", "导出"),
                "detail": _action("detail_btn", "详情", parent="main_table"),
                "edit": _action("edit_btn", "编辑", parent="main_table"),
                "query": _action("query_btn", "查询"),
            },
        },
    }


def _action(fieldid: str, label: str, parent: str = "toolbar_root") -> dict[str, Any]:
    return {
        "key": fieldid,
        "divCode": fieldid,
        "nodeType": "leafItem",
        "label": label,
        "name": "Button",
        "rightflag": label,
        "parentKeys": ["root", parent],
    }


def _runtime_element(fieldid: str, text: str, role: str | None) -> dict[str, Any]:
    return {
        "fieldid": fieldid,
        "id": None,
        "name": None,
        "placeholder": None,
        "text": text,
        "role": role,
        "tag_name": "button" if role == "button" else "input",
        "visible": True,
        "selector": f'[fieldid="{fieldid}"]',
    }
