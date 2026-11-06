from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .models import ActionStep, DslDocument, DslTestCase, DslTestSuite
from .variables import VARIABLE_PATTERN, resolve_variables, validate_runtime_variable_name, variable_path_conflicts

VALID_FAILURE_POLICIES = {"continue", "stop_suite", "stop_run"}

LEGACY_ACTIONS = {
    "open_row_detail",
    "click_button",
    "fill_field",
    "fill_grid_row",
    "assert_field",
    "assert_text",
    "save",
    "submit",
}

COMPONENT_STEP_KEYS = {"component", "operation", "target"}
OPEN_MENU_STEP_KEYS = {"action", "menu_path"}

OPEN_MENU_EXAMPLE = """正确写法示例:
  - action: open_menu
    menu_path: 项目库>>执行项目管理>>执行项目立项"""

ACTION_CLICK_EXAMPLE = """正确写法示例:
  - component: action
    operation: click
    target:
      fieldid: pageHeader_return"""

AMOUNT_UNIT_SET_EXAMPLE = """正确写法示例:
  - component: amount_unit
    operation: set
    target:
      value: 元"""

ATTACHMENT_UPLOAD_EXAMPLE = """正确写法示例:
  - component: attachment
    operation: upload
    target:
      attachments:
        - type: 询价
          file: tmp/attachments/询价.xlsx"""

BPR_START_EXAMPLE = """正确写法示例:
  - component: bpr
    operation: start
    target:
      name: 修改并取消"""

BPR_STOP_EXAMPLE = """正确写法示例:
  - component: bpr
    operation: stop
    target: {}"""

DIALOG_CANCEL_EXAMPLE = """正确写法示例:
  - component: dialog
    operation: cancel
    target:
      label: 取消"""

DIALOG_CLICK_EXAMPLE = """正确写法示例:
  - component: dialog
    operation: click
    target:
      label: 确认
      expect_download: true"""

DIALOG_CONFIRM_EXAMPLE = """正确写法示例:
  - component: dialog
    operation: confirm
    target:
      label: 确定"""

EDITABLE_TABLE_ADD_ROW_EXAMPLE = """正确写法示例:
  - component: editable_table
    operation: add_row
    target:
      label: 新增
      table: 支出明细
      editor: form"""

EDITABLE_TABLE_FILL_ROW_EXAMPLE = """正确写法示例:
  - component: editable_table
    operation: fill_row
    target:
      table: 支出明细
      row_number: -1
      fields:
        支出明细: Codex支出明细
        数量: "1"
        适用状态:
          - 草稿
          - 启用
"""

FORM_ASSERT_VALUES_EXAMPLE = """正确写法示例:
  - component: form
    operation: assert_values
    target:
      fields:
        项目名称: puqh测试项目1"""

FORM_CAPTURE_VALUES_EXAMPLE = """正确写法示例:
  - component: form
    operation: capture_values
    target:
      capture:
        tel: 手机号"""

FORM_FILL_EXAMPLE = """正确写法示例:
  - component: form
    operation: fill
    target:
      fields:
        项目名称: puqh测试项目1
        项目负责人: 吕晓雷
        # 仅适用于允许自由输入的页面参照；结构化目标仍执行参照选择
        支付摘要: 新支付用途
        账户状态:
          - 草稿
          - 启用"""

IMPORT_DOWNLOAD_TEMPLATE_EXAMPLE = """正确写法示例:
  - component: import
    operation: download_template
    target:
      label: 导入
      template: 默认模版"""

IMPORT_UPLOAD_EXAMPLE = """正确写法示例:
  - component: import
    operation: upload
    target:
      label: 导入
      file: examples/fixtures/payee_account/收款人账户管理导入模板.xlsx
      assert:
        status: success

  - component: import
    operation: upload
    target:
      fieldid: custom_import
      file: tmp/import/业务导入.xlsx
      assert:
        status: submitted
  - component: table
    operation: assert_row_values
    target:
      match:
        column: 地区
        equals: 南昌市
      fields:
        本次应拨付(万元): '56,942.32'"""

NOTIFICATION_ASSERT_EXAMPLE = """正确写法示例:
  - component: notification
    operation: assert
    target:
      type: error
      contains: 账户名称不能为空"""

NOTIFICATION_CLOSE_EXAMPLE = """正确写法示例:
  - component: notification
    operation: close
    target:
      type: error
      contains: 请联系管理员"""

WORKFLOW_PANEL_CLICK_EXAMPLE = """正确写法示例:
  - component: workflow_panel
    operation: click
    target:
      label: 撤回审批
"""

WORKFLOW_RESULT_ASSERT_EXAMPLE = """正确写法示例:
  - component: workflow_result
    operation: assert
    target:
      total: 2
      succeeded: 1
      failed: 1"""

WORKFLOW_RESULT_DETAILS_EXAMPLE = """正确写法示例:
  - component: workflow_result
    operation: details
    target: {}"""

WORKFLOW_RESULT_CONFIRM_EXAMPLE = """正确写法示例:
  - component: workflow_result
    operation: confirm
    target: {}"""

POPUP_REFERENCE_SELECT_EXAMPLE = """正确写法示例:
  - component: popup_reference
    operation: select
    target:
      title: 单位遴选
      value: 101001 江西省局本级（主管单位/单位经办）

  - component: popup_reference
    operation: select
    target:
      title: 选择指标
      filter:
        conditions:
          - field: 部门经济分类科目
            equals: 30101 基本工资
      match:
        column: 部门经济分类科目
        equals: 30101 基本工资

  - component: popup_reference
    operation: select
    target:
      title: 选择项目预算
      selections:
        - table: 项目预算
          row_number: 1
        - table: 预算编制科目
          row_number: 2"""

QUERY_SEARCH_EXAMPLE = """正确写法示例:
  - component: query
    operation: search
    target:
      conditions:
        - field: 项目负责人
          equals: 吕晓雷
        - field: 账户状态
          equals:
            - 草稿
            - 启用"""

QUERY_RESET_EXAMPLE = """正确写法示例:
  - component: query
    operation: reset
    target: {}"""

TAB_CLICK_EXAMPLE = """正确写法示例:
  - component: tab
    operation: click
    target:
      label: 全部"""

TABLE_ASSERT_COLUMN_VALUES_EXAMPLE = """正确写法示例:
  - component: table
    operation: assert_column_values
    target:
      column: 项目负责人
      equals: 吕晓雷"""

TABLE_ASSERT_COLUMNS_EXAMPLE = """正确写法示例:
  - component: table
    operation: assert_columns
    target:
      table: 三级模板明细
      present:
        - 一级绩效指标
        - 二级绩效指标
      absent:
        - 一级绩效指标分值
        - 二级绩效指标分值"""

TABLE_ASSERT_EMPTY_EXAMPLE = """正确写法示例:
  - component: table
    operation: assert_empty
    target:
      column: 项目名称"""

TABLE_ASSERT_ROW_VALUES_EXAMPLE = """正确写法示例:
  - component: table
    operation: assert_row_values
    target:
      match:
        column: 项目名称
        equals: puqh测试项目1
      fields:
        项目申报部门: 003 财务处"""

TABLE_CAPTURE_ROW_VALUES_EXAMPLE = """正确写法示例:
  - component: table
    operation: capture_row_values
    target:
      table: 明细表
      match:
        column: 项目名称
        equals: "ys测试{{random.suffix}}"
      capture:
        yjxm.project_code: 项目代码"""

TABLE_CLICK_CELL_LINK_EXAMPLE = """正确写法示例:
  - component: table
    operation: click_cell_link
    target:
      match:
        column: 序号
        equals: 1
      column: 任务编码
      link_text: "202600000000060" """

TABLE_ROW_ACTION_EXAMPLE = """正确写法示例:
  - component: table_row_action
    operation: click
    target:
      action: 详情
      match:
        conditions:
          - column: 项目名称
            equals: puqh测试项目1
          - column: 项目申报部门
            equals: 003 财务处"""

TABLE_ROW_SELECTION_EXAMPLE = """正确写法示例:
  - component: table_row_selection
    operation: select
    target:
      table: 消费明细
      row_number: 1

  - component: table_row_selection
    operation: select
    target:
      select_all: true

  - component: table_row_selection
    operation: select
    target:
      match:
        conditions:
          - column: 三级项目名称
            equals: tztj513004
          - column: 部门预算支出经济分类
            equals: 30101 基本工资

  - component: table_row_selection
    operation: select
    target:
      rows:
        - match:
            column: 项目代码
            equals: A
        - match:
            column: 项目代码
            equals: B"""

TOOLBAR_CLICK_EXAMPLE = """正确写法示例:
  - component: toolbar
    operation: click
    target:
      label: 新增"""

TRANSFER_DIALOG_SELECT_EXAMPLE = """正确写法示例:
  - component: transfer_dialog
    operation: select
    target:
      title: 支付任务类型配置
      left:
        matches:
          - column: 支付任务类型
            equals: 002 代缴个人所得税
      move: to_right
      confirm: true"""

TREE_SELECT_EXAMPLE = """正确写法示例:
  - component: tree
    operation: select
    target:
      name: 内部机构
      label: 001 办公室

  - component: tree
    operation: select
    target:
      name: 区划树
      labels:
        - 360000001 南昌市
        - 360100001 市本级

  - component: tree
    operation: select
    target:
      name: 内部机构
      node: root

  - component: tree
    operation: select
    target:
      name: 内部机构
      node: first_leaf"""


@dataclass(frozen=True, slots=True)
class TargetSchema:
    allowed_keys: frozenset[str]
    example: str


def _schema(keys: set[str], example: str) -> TargetSchema:
    return TargetSchema(allowed_keys=frozenset(keys), example=example)


COMPONENT_TARGET_SCHEMAS: dict[tuple[str, str], TargetSchema] = {
    ("action", "click"): _schema({"fieldid", "label"}, ACTION_CLICK_EXAMPLE),
    ("amount_unit", "set"): _schema({"value"}, AMOUNT_UNIT_SET_EXAMPLE),
    ("attachment", "upload"): _schema(
        {"attachments", "file", "path", "type", "attachment_type", "name"},
        ATTACHMENT_UPLOAD_EXAMPLE,
    ),
    ("bpr", "start"): _schema({"name", "description"}, BPR_START_EXAMPLE),
    ("bpr", "stop"): _schema({"name", "description"}, BPR_STOP_EXAMPLE),
    ("dialog", "cancel"): _schema(
        {"label", "expect_download", "download", "restore_previous", "restore_template"},
        DIALOG_CANCEL_EXAMPLE,
    ),
    ("dialog", "click"): _schema(
        {"label", "expect_download", "download", "restore_previous", "restore_template"},
        DIALOG_CLICK_EXAMPLE,
    ),
    ("dialog", "confirm"): _schema(
        {"label", "expect_download", "download", "restore_previous", "restore_template"},
        DIALOG_CONFIRM_EXAMPLE,
    ),
    ("editable_table", "add_row"): _schema(
        {"label", "action", "table", "name", "table_name", "editor"},
        EDITABLE_TABLE_ADD_ROW_EXAMPLE,
    ),
    ("editable_table", "fill_row"): _schema(
        {"table", "name", "table_name", "row_number", "row_index", "fields", "values", "field", "equals"},
        EDITABLE_TABLE_FILL_ROW_EXAMPLE,
    ),
    ("form", "assert_values"): _schema({"fields", "values", "field", "equals"}, FORM_ASSERT_VALUES_EXAMPLE),
    ("form", "capture_values"): _schema({"capture"}, FORM_CAPTURE_VALUES_EXAMPLE),
    ("form", "fill"): _schema({"fields", "values", "field", "equals"}, FORM_FILL_EXAMPLE),
    ("import", "download_template"): _schema(
        {"label", "template", "template_name", "name"},
        IMPORT_DOWNLOAD_TEMPLATE_EXAMPLE,
    ),
    ("import", "upload"): _schema({"label", "fieldid", "file", "files", "path", "assert"}, IMPORT_UPLOAD_EXAMPLE),
    ("notification", "assert"): _schema(
        {"type", "contains", "message_contains", "text_contains", "equals", "message"},
        NOTIFICATION_ASSERT_EXAMPLE,
    ),
    ("notification", "close"): _schema(
        {"type", "contains", "message_contains", "text_contains", "equals", "message", "label", "button"},
        NOTIFICATION_CLOSE_EXAMPLE,
    ),
    ("workflow_panel", "click"): _schema({"label"}, WORKFLOW_PANEL_CLICK_EXAMPLE),
    ("workflow_result", "assert"): _schema(
        {"total", "succeeded", "failed", "title", "message", "contains"},
        WORKFLOW_RESULT_ASSERT_EXAMPLE,
    ),
    ("workflow_result", "details"): _schema({"label"}, WORKFLOW_RESULT_DETAILS_EXAMPLE),
    ("workflow_result", "confirm"): _schema({"label"}, WORKFLOW_RESULT_CONFIRM_EXAMPLE),
    ("popup_reference", "select"): _schema(
        {
            "title",
            "label",
            "name",
            "filter",
            "value",
            "values",
            "match",
            "matches",
            "selection",
            "selections",
            "row_number",
            "row_numbers",
            "row_index",
            "rows",
            "first_available",
            "select_first_available",
            "table",
            "table_name",
            "tab",
            "tabs",
            "tree",
            "trees",
            "confirm",
            "confirm_label",
        },
        POPUP_REFERENCE_SELECT_EXAMPLE,
    ),
    ("query", "search"): _schema({"conditions", "button"}, QUERY_SEARCH_EXAMPLE),
    ("query", "reset"): _schema(set(), QUERY_RESET_EXAMPLE),
    ("tab", "click"): _schema({"label"}, TAB_CLICK_EXAMPLE),
    ("table", "assert_column_values"): _schema(
        {"table", "table_name", "column", "equals"},
        TABLE_ASSERT_COLUMN_VALUES_EXAMPLE,
    ),
    ("table", "assert_columns"): _schema({"table", "name", "table_name", "present", "absent"}, TABLE_ASSERT_COLUMNS_EXAMPLE),
    ("table", "assert_empty"): _schema({"column"}, TABLE_ASSERT_EMPTY_EXAMPLE),
    ("table", "capture_row_values"): _schema(
        {"table", "table_name", "match", "capture"},
        TABLE_CAPTURE_ROW_VALUES_EXAMPLE,
    ),
    ("table", "click_cell_link"): _schema(
        {
            "table",
            "table_name",
            "match",
            "row_number",
            "row_index",
            "first_available",
            "select_first_available",
            "column",
            "link_text",
        },
        TABLE_CLICK_CELL_LINK_EXAMPLE,
    ),
    ("table", "assert_row_values"): _schema(
        {"table", "table_name", "match", "fields", "values", "field", "equals"},
        TABLE_ASSERT_ROW_VALUES_EXAMPLE,
    ),
    ("table_row_action", "click"): _schema(
        {
            "action",
            "table",
            "table_name",
            "match",
            "row_number",
            "row_numbers",
            "row_index",
            "first_available",
            "select_first_available",
        },
        TABLE_ROW_ACTION_EXAMPLE,
    ),
    ("table_row_selection", "select"): _schema(
        {
            "table",
            "match",
            "row_number",
            "row_numbers",
            "row_index",
            "rows",
            "first_available",
            "select_first_available",
            "select_all",
        },
        TABLE_ROW_SELECTION_EXAMPLE,
    ),
    ("toolbar", "click"): _schema(
        {
            "label",
            "sub_label",
            "sub_action",
            "child_label",
            "child_action",
            "item",
            "option",
            "restore_previous",
            "restore_template",
        },
        TOOLBAR_CLICK_EXAMPLE,
    ),
    ("transfer_dialog", "select"): _schema(
        {"title", "label", "name", "move", "direction", "confirm", "items", "targets", "matches", "match", "left", "source", "equals", "column"},
        TRANSFER_DIALOG_SELECT_EXAMPLE,
    ),
    ("tree", "select"): _schema(
        {"label", "labels", "values", "node", "name", "component_name", "component_label", "region_label"},
        TREE_SELECT_EXAMPLE,
    ),
}

VALID_COMPONENT_OPERATIONS = set(COMPONENT_TARGET_SCHEMAS)


class DslFileError(ValueError):
    def __init__(self, dsl_file: str | Path, message: str) -> None:
        self.dsl_file = str(dsl_file)
        super().__init__(f"DSL 文件: {self.dsl_file}\n{message}")


class DslBatchError(ValueError):
    def __init__(self, errors: list[DslFileError]) -> None:
        self.errors = [{"dsl_file": error.dsl_file, "message": str(error)} for error in errors]
        message = "\n\n".join(str(error) for error in errors)
        if len(errors) > 1:
            message = f"DSL 校验失败，共 {len(errors)} 个文件有错误:\n\n{message}"
        super().__init__(message)


def load_dsl_documents_from_files(
    paths: list[Path],
    variables: dict[str, Any] | None = None,
    *,
    validate_bpr_state: bool = True,
) -> list[tuple[Path, DslDocument]]:
    documents: list[tuple[Path, DslDocument]] = []
    errors: list[DslFileError] = []
    for path in paths:
        try:
            document = load_dsl_document_from_file(path, variables=variables, validate_bpr_state=validate_bpr_state)
        except DslFileError as exc:
            errors.append(exc)
            continue
        documents.append((path, document))
    if errors:
        raise DslBatchError(errors)
    return documents


def load_dsl_from_file(
    path: str | Path,
    variables: dict[str, Any] | None = None,
    *,
    validate_bpr_state: bool = True,
) -> list[ActionStep]:
    file_path = Path(path)
    data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    return load_dsl(data, variables=variables, validate_bpr_state=validate_bpr_state)


def load_dsl_document_from_file(
    path: str | Path,
    variables: dict[str, Any] | None = None,
    *,
    validate_bpr_state: bool = True,
) -> DslDocument:
    file_path = Path(path)
    try:
        data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
        return load_dsl_document(data, variables=variables, validate_bpr_state=validate_bpr_state)
    except (ValueError, yaml.YAMLError, OSError) as exc:
        raise DslFileError(file_path, str(exc)) from exc


def load_dsl_document(
    payload: Any,
    variables: dict[str, Any] | None = None,
    *,
    validate_bpr_state: bool = True,
) -> DslDocument:
    payload = _parse_payload(payload)
    runtime_variables = _collect_runtime_capture_variables(payload, variables or {})
    payload = resolve_variables(payload, variables, runtime_variables=set(runtime_variables))
    if isinstance(payload, dict) and "cases" in payload:
        document = _load_suite_document(payload, validate_bpr_state=validate_bpr_state)
        document.suite.runtime_variables = runtime_variables
        document.suite.requires_runtime_serial = bool(runtime_variables)
        return document
    raise ValueError("旧式 steps DSL 已废弃，请使用 suite + cases + steps 格式")


def load_dsl(
    payload: Any,
    variables: dict[str, Any] | None = None,
    *,
    validate_bpr_state: bool = True,
) -> list[ActionStep]:
    payload = _parse_payload(payload)
    payload = resolve_variables(payload, variables)
    if isinstance(payload, dict) and "cases" in payload:
        raise ValueError("测试集 DSL 请使用 load_dsl_document 读取")
    steps = _extract_steps(payload)
    normalized: list[ActionStep] = []
    for item in steps:
        normalized.append(normalize_step(item))
    _validate_steps(normalized, "steps", validate_bpr_state=validate_bpr_state)
    return normalized


def _collect_runtime_capture_variables(payload: Any, external_variables: dict[str, Any]) -> list[str]:
    names: list[str] = []
    if not isinstance(payload, dict) or "cases" not in payload:
        return names
    cases = payload.get("cases")
    if not isinstance(cases, list):
        return names
    for case in cases:
        if not isinstance(case, dict):
            continue
        steps = case.get("steps") or case.get("actions") or []
        if not isinstance(steps, list):
            continue
        for step in steps:
            if not _is_runtime_capture_step(step):
                continue
            target = step.get("target") or {}
            capture = target.get("capture") if isinstance(target, dict) else None
            if not isinstance(capture, dict):
                continue
            for raw_name in capture:
                name = str(raw_name or "").strip()
                validate_runtime_variable_name(name)
                if variable_path_conflicts(external_variables, name):
                    raise ValueError(f"捕获变量不能与外部变量重名: {name}")
                if name not in names:
                    names.append(name)
    return sorted(names)


def _is_runtime_capture_step(step: Any) -> bool:
    if not isinstance(step, dict):
        return False
    component_operation = (str(step.get("component") or ""), str(step.get("operation") or ""))
    return component_operation in {("table", "capture_row_values"), ("form", "capture_values")}


def _is_table_capture_step(step: Any) -> bool:
    return (
        isinstance(step, dict)
        and str(step.get("component") or "") == "table"
        and str(step.get("operation") or "") == "capture_row_values"
    )


def _uses_runtime_variables(payload: Any, runtime_variables: set[str]) -> bool:
    if not runtime_variables:
        return False
    if isinstance(payload, dict):
        return any(_uses_runtime_variables(value, runtime_variables) for value in payload.values())
    if isinstance(payload, list):
        return any(_uses_runtime_variables(value, runtime_variables) for value in payload)
    if isinstance(payload, str):
        return any(match.group(1).strip() in runtime_variables for match in VARIABLE_PATTERN.finditer(payload))
    return False


def _parse_payload(payload: Any) -> Any:
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return yaml.safe_load(payload)
    return payload


def _extract_steps(payload: Any) -> list[Any]:
    if isinstance(payload, dict):
        steps = payload.get("steps") or payload.get("actions") or []
    elif isinstance(payload, list):
        steps = payload
    else:
        raise ValueError("DSL 必须是列表或包含 steps 的对象")
    if not isinstance(steps, list):
        raise ValueError("DSL steps 必须是列表")
    return steps


def _load_suite_document(payload: dict[str, Any], *, validate_bpr_state: bool = True) -> DslDocument:
    suite_payload = payload.get("suite") or {}
    if not isinstance(suite_payload, dict):
        raise ValueError("测试集 suite 必须是对象")
    cases_payload = payload.get("cases")
    if not isinstance(cases_payload, list) or not cases_payload:
        raise ValueError("测试集 cases 必须是非空列表")
    _reject_deprecated_suite_context_fields(suite_payload)
    suite_tenant = str(suite_payload.get("tenant") or "").strip()
    suite_default_org = str(suite_payload.get("default_org") or "").strip()
    suite_fiscal_year = str(suite_payload.get("fiscal_year") or "").strip()
    suite = DslTestSuite(
        code=_required_text(suite_payload, "code", "suite.code"),
        name=_required_text(suite_payload, "name", "suite.name"),
        description=str(suite_payload.get("description") or ""),
        tenant=suite_tenant,
        default_org=suite_default_org,
        fiscal_year=suite_fiscal_year,
        on_case_failure=_normalize_failure_policy(
            suite_payload.get("on_case_failure")
            or suite_payload.get("failure_strategy")
            or suite_payload.get("on_failure")
            or "continue",
            "suite.on_case_failure",
        ),
    )
    cases = [
        _load_case(
            item,
            index,
            suite_default_org=suite.default_org,
            validate_bpr_state=validate_bpr_state,
        )
        for index, item in enumerate(cases_payload, start=1)
    ]
    if not suite.tenant:
        raise ValueError("suite.tenant 必填")
    return DslDocument(suite=suite, cases=cases, is_suite=True)


def _load_case(
    payload: Any,
    index: int,
    *,
    suite_default_org: str = "",
    validate_bpr_state: bool = True,
) -> DslTestCase:
    if not isinstance(payload, dict):
        raise ValueError(f"测试用例必须是对象: cases[{index}]")
    _reject_deprecated_case_context_fields(payload, index)
    steps = [normalize_step(item) for item in _extract_steps(payload)]
    _validate_steps(steps, f"cases[{index}].steps", validate_bpr_state=validate_bpr_state)
    case_default_org = str(payload.get("default_org") or "").strip() or suite_default_org
    if not case_default_org:
        raise ValueError(f"suite.default_org 或 cases[{index}].default_org 必填")
    return DslTestCase(
        code=_required_text(payload, "code", f"cases[{index}].code"),
        name=_required_text(payload, "name", f"cases[{index}].name"),
        description=str(payload.get("description") or ""),
        user=str(payload.get("user") or ""),
        default_org=case_default_org,
        tags=_load_tags(payload.get("tags"), index),
        steps=steps,
    )


def _reject_deprecated_suite_context_fields(payload: dict[str, Any]) -> None:
    if "username" in payload or "password" in payload:
        raise ValueError("suite.username/password 已废弃，请只在 cases[].user 配置用户别名，真实用户名和密码只允许放在 env.users")
    deprecated_fields = (
        ("tenant_name", "suite.tenant_name 已废弃，请使用 suite.tenant"),
        ("tenantName", "suite.tenantName 已废弃，请使用 suite.tenant"),
        ("default_org_code", "suite.default_org_code 已废弃，请使用 suite.default_org"),
        ("default_org_name", "suite.default_org_name 已废弃，请使用 suite.default_org"),
        ("defaultOrg", "suite.defaultOrg 已废弃，请使用 suite.default_org"),
        ("defaultOrgCode", "suite.defaultOrgCode 已废弃，请使用 suite.default_org"),
        ("defaultOrgName", "suite.defaultOrgName 已废弃，请使用 suite.default_org"),
    )
    for key, message in deprecated_fields:
        if key in payload:
            raise ValueError(message)


def _reject_deprecated_case_context_fields(payload: dict[str, Any], index: int) -> None:
    if "username" in payload or "password" in payload:
        raise ValueError(f"cases[{index}].username/password 已废弃，请只配置 user 别名，真实用户名和密码只允许放在 env.users")
    deprecated_fields = (
        ("tenant", f"cases[{index}].tenant 已废弃，租户只能配置在 suite.tenant"),
        ("tenant_name", f"cases[{index}].tenant_name 已废弃，租户只能配置在 suite.tenant"),
        ("tenantName", f"cases[{index}].tenantName 已废弃，租户只能配置在 suite.tenant"),
        ("default_org_code", f"cases[{index}].default_org_code 已废弃，请使用 cases[{index}].default_org"),
        ("default_org_name", f"cases[{index}].default_org_name 已废弃，请使用 cases[{index}].default_org"),
        ("defaultOrg", f"cases[{index}].defaultOrg 已废弃，请使用 cases[{index}].default_org"),
        ("defaultOrgCode", f"cases[{index}].defaultOrgCode 已废弃，请使用 cases[{index}].default_org"),
        ("defaultOrgName", f"cases[{index}].defaultOrgName 已废弃，请使用 cases[{index}].default_org"),
    )
    for key, message in deprecated_fields:
        if key in payload:
            raise ValueError(message)


def _required_text(payload: dict[str, Any], key: str, label: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"测试集 DSL 缺少必填字段: {label}")
    return value


def _normalize_failure_policy(value: Any, label: str) -> str:
    text = str(value or "").strip().replace("-", "_")
    if text in {"skip", "continue_suite"}:
        text = "continue"
    if text not in VALID_FAILURE_POLICIES:
        raise ValueError(f"不支持的失败策略: {label}={value!r}")
    return text


def _load_tags(value: Any, index: int) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if not isinstance(value, list):
        raise ValueError(f"测试用例 tags 必须是列表或逗号分隔字符串: cases[{index}].tags")
    tags: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            tags.append(text)
    return tags


def normalize_step(item: Any) -> ActionStep:
    if not isinstance(item, dict):
        raise ValueError(f"非法 DSL step: {item!r}")
    if "action" in item:
        action = str(item["action"])
        if action in LEGACY_ACTIONS:
            raise ValueError(f"旧 DSL 已移除，请改用组件语义 DSL: {action}")
        if action != "open_menu":
            raise ValueError(f"不支持的页面级 DSL 动作: {action}")
        unsupported = _unsupported_keys(item, OPEN_MENU_STEP_KEYS)
        return ActionStep(
            kind="page",
            action=action,
            params={k: v for k, v in item.items() if k in OPEN_MENU_STEP_KEYS and k != "action"},
            extra_keys=unsupported,
        )
    if "component" in item and "operation" in item and "target" in item:
        unsupported = _unsupported_keys(item, COMPONENT_STEP_KEYS)
        target = item["target"]
        if not isinstance(target, dict):
            raise ValueError(f"组件 DSL 的 target 必须是对象: {item!r}")
        return ActionStep(
            kind="component",
            component=str(item["component"]),
            operation=str(item["operation"]),
            target=target,
            extra_keys=unsupported,
        )
    raise ValueError(f"非法 DSL step: {item!r}")


def _validate_steps(steps: list[ActionStep], path: str, *, validate_bpr_state: bool = True) -> None:
    errors: list[str] = []
    for index, step in enumerate(steps, start=1):
        step_path = f"{path}[{index}]"
        errors.extend(_validate_step(step, step_path))
    if validate_bpr_state:
        errors.extend(_validate_bpr_state(steps, path))
    errors.extend(_validate_submitted_import_assertions(steps, path))
    if errors:
        raise ValueError("DSL 语法校验失败:\n- " + "\n- ".join(errors))


def _validate_submitted_import_assertions(steps: list[ActionStep], path: str) -> list[str]:
    errors: list[str] = []
    for index, step in enumerate(steps):
        if not _is_submitted_import_step(step):
            continue
        step_path = f"{path}[{index + 1}]"
        if index == len(steps) - 1:
            errors.append(f"{step_path}: `assert.status: submitted` 不能是用例最后一步，必须增加后置业务断言")
            continue
        if not any(_is_business_assertion_step(item) for item in steps[index + 1 :]):
            errors.append(
                f"{step_path}: `assert.status: submitted` 后续必须包含业务断言，"
                "例如 table.assert_row_values、form.assert_values 或 notification.assert"
            )
    return errors


def _is_submitted_import_step(step: ActionStep) -> bool:
    assertion = step.target.get("assert") if isinstance(step.target, dict) else None
    return bool(
        step.kind == "component"
        and step.component == "import"
        and step.operation == "upload"
        and isinstance(assertion, dict)
        and str(assertion.get("status") or "").strip().lower() == "submitted"
    )


def _is_business_assertion_step(step: ActionStep) -> bool:
    return bool(
        step.kind == "component"
        and (step.component, step.operation)
        in {
            ("form", "assert_values"),
            ("notification", "assert"),
            ("workflow_result", "assert"),
            ("table", "assert_column_values"),
            ("table", "assert_columns"),
            ("table", "assert_empty"),
            ("table", "assert_row_values"),
        }
    )


def _validate_bpr_state(steps: list[ActionStep], path: str) -> list[str]:
    errors: list[str] = []
    active_start_index: int | None = None
    for index, step in enumerate(steps, start=1):
        if not _is_bpr_step(step):
            continue
        if step.operation == "start":
            if active_start_index is not None:
                errors.append(
                    f"{path}[{index}]: 不支持嵌套 BPR 录制，请先为 {path}[{active_start_index}] 补充 bpr.stop"
                )
                continue
            active_start_index = index
            continue
        if step.operation == "stop":
            if active_start_index is None:
                errors.append(f"{path}[{index}]: 没有正在录制的 BPR session，不能执行 bpr.stop")
                continue
            active_start_index = None
    if active_start_index is not None:
        errors.append(f"{path}[{active_start_index}]: BPR 录制缺少 bpr.stop")
    return errors


def _is_bpr_step(step: ActionStep) -> bool:
    return bool(step.kind == "component" and step.component == "bpr" and step.operation in {"start", "stop"})


def _validate_step(step: ActionStep, path: str) -> list[str]:
    errors: list[str] = []
    if step.extra_keys:
        label = step.action if step.kind == "page" else f"{step.component}.{step.operation}"
        if step.kind == "page":
            errors.append(_page_error(path, f"{label} 不支持属性: {_format_keys(step.extra_keys)}"))
        else:
            schema = COMPONENT_TARGET_SCHEMAS.get((str(step.component), str(step.operation)))
            if schema is not None:
                errors.append(_component_error(path, str(label), f"不支持属性: {_format_keys(step.extra_keys)}", schema))
            else:
                errors.append(f"{path}: {label} 不支持属性: {_format_keys(step.extra_keys)}")
    if step.kind == "page":
        if step.action == "open_menu" and not str(step.params.get("menu_path") or "").strip():
            errors.append(_page_error(path, "open_menu 缺少 menu_path"))
        return errors
    if step.kind != "component":
        errors.append(f"{path}: 不支持的 DSL step 类型: {step.kind}")
        return errors
    component_operation = (step.component, step.operation)
    if component_operation not in VALID_COMPONENT_OPERATIONS:
        errors.append(f"{path}: 不支持的组件 DSL: {step.component}.{step.operation}\n{TOOLBAR_CLICK_EXAMPLE}")
        return errors
    errors.extend(_validate_component_target(step.target, component_operation, path))
    if component_operation == ("table", "assert_row_values"):
        errors.extend(_validate_table_assert_row_values(step.target, path, COMPONENT_TARGET_SCHEMAS[component_operation]))
    return errors


def _validate_component_target(
    target: dict[str, Any],
    component_operation: tuple[str, str],
    path: str,
) -> list[str]:
    label = f"{component_operation[0]}.{component_operation[1]}"
    schema = COMPONENT_TARGET_SCHEMAS[component_operation]
    errors = _validate_target_keys(target, component_operation, path, schema)
    if component_operation == ("workflow_panel", "click"):
        if not isinstance(target.get("label"), str) or not target["label"].strip():
            errors.append(_component_error(path, label, "target.label 必须是非空字符串", schema))
    elif component_operation == ("query", "search"):
        errors.extend(_validate_query_search(target, path, schema))
    elif component_operation == ("table_row_action", "click"):
        errors.extend(_validate_table_row_action_click(target, path, schema))
    elif component_operation == ("tree", "select"):
        errors.extend(_validate_tree_select(target, path, schema))
    elif component_operation in {("tab", "click"), ("toolbar", "click")}:
        if not _has_text(target, "label"):
            errors.append(_component_error(path, label, "缺少 target.label", schema))
    elif component_operation == ("editable_table", "add_row"):
        errors.extend(_validate_editable_table_add_row(target, path, schema))
    elif component_operation == ("action", "click"):
        if not (_has_text(target, "fieldid") or _has_text(target, "label")):
            errors.append(_component_error(path, label, "缺少 target.fieldid 或 target.label", schema))
    elif component_operation == ("amount_unit", "set"):
        errors.extend(_validate_amount_unit_set(target, path, schema))
    elif component_operation == ("editable_table", "fill_row"):
        errors.extend(_validate_editable_table_fields_target(target, label, path, schema))
    elif component_operation in {("form", "fill"), ("form", "assert_values")}:
        errors.extend(_validate_fields_target(target, label, path, schema))
    elif component_operation == ("form", "capture_values"):
        errors.extend(_validate_capture_mapping(target, path, schema, label, source_label="来源字段"))
    elif component_operation == ("table", "assert_column_values"):
        if not _has_text(target, "column"):
            errors.append(_component_error(path, label, "缺少 target.column", schema))
        if target.get("equals") is None:
            errors.append(_component_error(path, label, "缺少 target.equals", schema))
    elif component_operation == ("table", "assert_columns"):
        errors.extend(_validate_table_assert_columns(target, path, schema))
    elif component_operation == ("table", "capture_row_values"):
        errors.extend(_validate_table_capture_row_values(target, path, schema))
    elif component_operation == ("table", "click_cell_link"):
        errors.extend(_validate_table_click_cell_link(target, path, schema))
    elif component_operation == ("table_row_selection", "select"):
        errors.extend(_validate_table_row_selection(target, path, schema))
    elif component_operation == ("attachment", "upload"):
        errors.extend(_validate_attachment_upload(target, path, schema))
    elif component_operation == ("import", "upload"):
        errors.extend(_validate_import_upload(target, path, schema))
    elif component_operation == ("notification", "close"):
        errors.extend(_validate_notification_close(target, path, schema))
    elif component_operation[0] == "workflow_result":
        errors.extend(_validate_workflow_result(target, component_operation[1], path, schema))
    elif component_operation == ("popup_reference", "select"):
        errors.extend(_validate_popup_reference_select(target, path, schema))
    elif component_operation == ("transfer_dialog", "select"):
        errors.extend(_validate_transfer_dialog_select(target, path, schema))
    return errors


def _validate_amount_unit_set(target: dict[str, Any], path: str, schema: TargetSchema) -> list[str]:
    value = str(target.get("value") or "").strip()
    if value in {"元", "万元"}:
        return []
    return [_component_error(path, "amount_unit.set", "金额单位只支持 `元` 和 `万元`", schema)]


def _validate_notification_close(target: dict[str, Any], path: str, schema: TargetSchema) -> list[str]:
    if any(
        _has_text(target, key)
        for key in ("type", "contains", "message_contains", "text_contains", "equals", "message")
    ):
        return []
    return [_component_error(path, "notification.close", "缺少提示匹配条件", schema)]


def _validate_workflow_result(
    target: dict[str, Any], operation: str, path: str, schema: TargetSchema
) -> list[str]:
    label = f"workflow_result.{operation}"
    if operation == "assert":
        count_keys = ("total", "succeeded", "failed")
        declared = [key for key in count_keys if key in target]
        if not declared:
            return [_component_error(path, label, "至少声明一个统计字段", schema)]
        errors: list[str] = []
        for key in declared:
            value = target.get(key)
            if not isinstance(value, int) or isinstance(value, bool):
                errors.append(_component_error(path, label, f"target.{key} 必须是整数", schema))
        for key in ("title", "message", "contains"):
            if key in target and not _has_text(target, key):
                errors.append(_component_error(path, label, f"target.{key} 必须是非空字符串", schema))
        return errors
    if "label" in target and not _has_text(target, "label"):
        return [_component_error(path, label, "target.label 必须是非空字符串", schema)]
    return []


def _validate_tree_select(target: dict[str, Any], path: str, schema: TargetSchema) -> list[str]:
    errors: list[str] = []
    has_explicit = _has_text(target, "label") or _has_non_empty_list(target, "labels") or _has_non_empty_list(target, "values")
    node = str(target.get("node") or "").strip()
    if node:
        if node not in {"root", "first_leaf"}:
            errors.append(_component_error(path, "tree.select", "target.node 只支持 root 或 first_leaf", schema))
        if has_explicit:
            errors.append(
                _component_error(
                    path,
                    "tree.select",
                    "target.node 不能和 target.label/target.labels/target.values 同时使用",
                    schema,
                )
            )
        return errors
    if not has_explicit:
        errors.append(_component_error(path, "tree.select", "缺少 target.label、target.labels 或 target.node", schema))
    return errors


def _validate_target_keys(
    target: dict[str, Any],
    component_operation: tuple[str, str],
    path: str,
    schema: TargetSchema,
) -> list[str]:
    unsupported = _unsupported_keys(target, set(schema.allowed_keys))
    if not unsupported:
        return []
    label = f"{component_operation[0]}.{component_operation[1]}"
    return [_component_error(path, label, f"target 不支持属性: {_format_keys(unsupported)}", schema)]


def _validate_query_search(target: dict[str, Any], path: str, schema: TargetSchema) -> list[str]:
    errors: list[str] = []
    if str(target.get("button") or "").strip() == "重置":
        errors.append(_component_error(path, "query.search", "target.button 不支持重置，请使用 query.reset", schema))
    if "conditions" not in target:
        errors.append(_component_error(path, "query.search", "缺少 target.conditions", schema))
        return errors
    raw = target.get("conditions")
    if not isinstance(raw, list):
        errors.append(_component_error(path, "query.search", "target.conditions 格式不对，必须是列表", schema))
        return errors
    for index, condition in enumerate(raw, start=1):
        condition_path = f"{path}: query.search target.conditions[{index}]"
        errors.extend(_validate_condition_item(condition, condition_path, field_key="field", schema=schema))
    return errors


def _validate_table_row_action_click(target: dict[str, Any], path: str, schema: TargetSchema) -> list[str]:
    errors: list[str] = []
    if not _has_text(target, "action"):
        errors.append(_component_error(path, "table_row_action.click", "缺少 target.action", schema))
    if _has_row_number_locator(target) or _wants_first_available(target):
        return errors
    match = target.get("match")
    if not isinstance(match, dict) or not match:
        errors.append(
            _component_error(
                path,
                "table_row_action.click",
                "缺少行定位属性: target.match / target.row_number / target.first_available",
                schema,
            )
        )
        return errors
    errors.extend(_validate_row_match(match, f"{path}: table_row_action.click target.match", schema))
    return errors


def _validate_editable_table_add_row(target: dict[str, Any], path: str, schema: TargetSchema) -> list[str]:
    raw_editor = target.get("editor")
    if raw_editor is None:
        return []
    editor = str(raw_editor).strip().lower()
    if editor not in {"auto", "form", "inline"}:
        return [
            _component_error(
                path,
                "editable_table.add_row",
                "target.editor 只支持 auto/form/inline",
                schema,
            )
        ]
    return []


def _validate_table_capture_row_values(target: dict[str, Any], path: str, schema: TargetSchema) -> list[str]:
    errors: list[str] = []
    match = target.get("match")
    if not isinstance(match, dict) or not match:
        errors.append(_component_error(path, "table.capture_row_values", "缺少 target.match", schema))
    else:
        errors.extend(_validate_row_match(match, f"{path}: table.capture_row_values target.match", schema))
    errors.extend(_validate_capture_mapping(target, path, schema, "table.capture_row_values", source_label="来源列"))
    return errors


def _validate_capture_mapping(
    target: dict[str, Any],
    path: str,
    schema: TargetSchema,
    label: str,
    *,
    source_label: str,
) -> list[str]:
    errors: list[str] = []
    capture = target.get("capture")
    if not isinstance(capture, dict) or not capture:
        errors.append(_component_error(path, label, f"缺少 target.capture，必须声明至少一个捕获变量和{source_label}", schema))
        return errors
    for raw_name, raw_source in capture.items():
        name = str(raw_name or "").strip()
        try:
            validate_runtime_variable_name(name)
        except ValueError as exc:
            errors.append(_component_error(path, label, str(exc), schema))
        if not isinstance(raw_source, str) or not raw_source.strip():
            errors.append(
                _component_error(
                    path,
                    label,
                    f"target.capture[{name or raw_name!r}] {source_label}必须是非空字符串",
                    schema,
                )
            )
    return errors


def _validate_table_row_selection(target: dict[str, Any], path: str, schema: TargetSchema) -> list[str]:
    if _wants_select_all(target):
        mixed = [
            key
            for key in (
                "match",
                "rows",
                "row_number",
                "row_numbers",
                "row_index",
                "first_available",
                "select_first_available",
            )
            if target.get(key) is not None
        ]
        if mixed:
            return [
                _component_error(
                    path,
                    "table_row_selection.select",
                    f"target.select_all 不能与行定位属性混用: {_format_keys(mixed)}",
                    schema,
                )
            ]
        return []
    if _has_row_number_locator(target) or _wants_first_available(target):
        return []
    if isinstance(target.get("match"), dict) and target["match"]:
        return _validate_row_match(target["match"], f"{path}: table_row_selection.select target.match", schema)
    rows = target.get("rows")
    if rows is None:
        return [
            _component_error(
                path,
                "table_row_selection.select",
                "缺少行定位属性: target.match / target.rows / target.row_number / target.first_available",
                schema,
            )
        ]
    if not isinstance(rows, list) or not rows:
        return [_component_error(path, "table_row_selection.select", "target.rows 格式不对，必须是非空列表", schema)]
    errors: list[str] = []
    for index, row in enumerate(rows, start=1):
        row_path = f"{path}: table_row_selection.select target.rows[{index}]"
        if not isinstance(row, dict):
            errors.append(_component_error(path, "table_row_selection.select", f"target.rows[{index}] 格式不对，必须是对象", schema))
            continue
        unsupported = _unsupported_keys(row, {"match"})
        if unsupported:
            errors.append(_nested_error(row_path, f"不支持属性: {_format_keys(unsupported)}", schema))
        match = row.get("match")
        if not isinstance(match, dict) or not match:
            errors.append(_nested_error(f"{row_path}.match", "格式不对，必须是对象", schema))
            continue
        errors.extend(_validate_row_match(match, f"{row_path}.match", schema))
    return errors


def _validate_table_click_cell_link(target: dict[str, Any], path: str, schema: TargetSchema) -> list[str]:
    errors: list[str] = []
    if not _has_text(target, "column"):
        errors.append(_component_error(path, "table.click_cell_link", "缺少 target.column", schema))
    if _has_row_number_locator(target) or _wants_first_available(target):
        return errors
    match = target.get("match")
    if not isinstance(match, dict) or not match:
        errors.append(
            _component_error(
                path,
                "table.click_cell_link",
                "缺少行定位属性: target.match / target.row_number / target.first_available",
                schema,
            )
        )
        return errors
    errors.extend(_validate_row_match(match, f"{path}: table.click_cell_link target.match", schema))
    return errors


def _validate_table_assert_row_values(target: dict[str, Any], path: str, schema: TargetSchema) -> list[str]:
    errors: list[str] = []
    match = target.get("match")
    if not isinstance(match, dict) or not match:
        errors.append(_component_error(path, "table.assert_row_values", "缺少 target.match", schema))
    else:
        errors.extend(_validate_row_match(match, f"{path}: table.assert_row_values target.match", schema))
    if not any(key in target for key in ("fields", "values", "field")):
        errors.append(_component_error(path, "table.assert_row_values", "缺少 target.fields", schema))
    else:
        errors.extend(_validate_fields_target(target, "table.assert_row_values", path, schema))
    return errors


def _validate_table_assert_columns(target: dict[str, Any], path: str, schema: TargetSchema) -> list[str]:
    errors: list[str] = []
    if "present" not in target and "absent" not in target:
        errors.append(_component_error(path, "table.assert_columns", "缺少 target.present 或 target.absent", schema))
        return errors
    for key in ("present", "absent"):
        if key not in target:
            continue
        value = target.get(key)
        if not isinstance(value, list) or not value or any(not str(item or "").strip() for item in value):
            errors.append(_component_error(path, "table.assert_columns", f"target.{key} 格式不对，必须是非空列表", schema))
    return errors


def _validate_fields_target(target: dict[str, Any], label: str, path: str, schema: TargetSchema) -> list[str]:
    errors: list[str] = []
    if "fields" in target:
        raw = target.get("fields")
    elif "values" in target:
        raw = target.get("values")
    elif "field" in target:
        if not _has_text(target, "field") or target.get("equals") is None:
            errors.append(_component_error(path, label, "target.field 写法格式不对，必须同时包含 field 和 equals", schema))
        return errors
    else:
        errors.append(_component_error(path, label, "缺少 target.fields", schema))
        return errors
    if isinstance(raw, dict):
        if not raw:
            errors.append(_component_error(path, label, "target.fields 不能为空", schema))
        else:
            errors.extend(_validate_field_assignment_lists(raw, f"{path}: {label} target.fields", schema))
            strict_reference_values = label in {"form.fill", "editable_table.fill_row"}
            errors.extend(
                _validate_popup_reference_field_values(
                    raw,
                    f"{path}: {label} target.fields",
                    schema,
                    strict_reference_values=strict_reference_values,
                )
            )
        return errors
    if not isinstance(raw, list):
        errors.append(_component_error(path, label, "target.fields 格式不对，必须是对象或列表", schema))
        return errors
    if not raw:
        errors.append(_component_error(path, label, "target.fields 不能为空", schema))
        return errors
    for index, item in enumerate(raw, start=1):
        errors.extend(_validate_condition_item(item, f"{path}: {label} target.fields[{index}]", field_key="field", schema=schema))
    return errors


def _validate_editable_table_fields_target(
    target: dict[str, Any],
    label: str,
    path: str,
    schema: TargetSchema,
) -> list[str]:
    errors: list[str] = []
    if "fields" in target:
        raw = target.get("fields")
    elif "values" in target:
        raw = target.get("values")
    elif "field" in target:
        if not _has_text(target, "field") or target.get("equals") is None:
            errors.append(_component_error(path, label, "target.field 写法格式不对，必须同时包含 field 和 equals", schema))
        return errors
    else:
        errors.append(_component_error(path, label, "缺少 target.fields", schema))
        return errors
    if isinstance(raw, dict):
        if not raw:
            errors.append(_component_error(path, label, "target.fields 不能为空", schema))
            return errors
        errors.extend(_validate_field_assignment_lists(raw, f"{path}: {label} target.fields", schema))
        popup_fields: dict[str, Any] = {}
        for field_name, value in raw.items():
            field_path = f"{path}: {label} target.fields.{field_name}"
            if _is_editable_table_column_group_wrapper(value):
                errors.extend(_validate_column_group_wrapper(value, field_path, schema))
                actual = value.get("value", value.get("equals")) if isinstance(value, dict) else None
                if isinstance(actual, dict):
                    popup_fields[str(field_name)] = actual
                continue
            popup_fields[str(field_name)] = value
        errors.extend(
            _validate_popup_reference_field_values(
                popup_fields,
                f"{path}: {label} target.fields",
                schema,
                strict_reference_values=True,
            )
        )
        return errors
    if not isinstance(raw, list):
        errors.append(_component_error(path, label, "target.fields 格式不对，必须是对象或列表", schema))
        return errors
    if not raw:
        errors.append(_component_error(path, label, "target.fields 不能为空", schema))
        return errors
    for index, item in enumerate(raw, start=1):
        item_path = f"{path}: {label} target.fields[{index}]"
        if not isinstance(item, dict):
            errors.append(_nested_error(item_path, "格式不对，必须是对象", schema))
            continue
        allowed = {"field", "equals", "value", "column_group"}
        unsupported = _unsupported_keys(item, allowed)
        if unsupported:
            errors.append(_nested_error(item_path, f"不支持属性: {_format_keys(unsupported)}", schema))
        if not str(item.get("field") or "").strip():
            errors.append(_nested_error(item_path, "格式不对，必须包含 field", schema))
        if "value" not in item and "equals" not in item:
            errors.append(_nested_error(item_path, "格式不对，必须包含 value 或 equals", schema))
        if "column_group" in item:
            errors.extend(_validate_column_group_value(item.get("column_group"), item_path, schema))
        actual = item.get("value", item.get("equals"))
        errors.extend(_validate_multi_select_assignment_list(actual, f"{item_path}.value", schema))
        if isinstance(actual, dict):
            errors.extend(_validate_popup_reference_select(actual, f"{item_path}.value", schema))
    return errors


def _is_editable_table_column_group_wrapper(value: Any) -> bool:
    return isinstance(value, dict) and "column_group" in value


def _validate_column_group_wrapper(value: Any, path: str, schema: TargetSchema) -> list[str]:
    if not isinstance(value, dict):
        return []
    errors = _validate_column_group_value(value.get("column_group"), path, schema)
    if "value" not in value and "equals" not in value:
        errors.append(_nested_error(path, "格式不对，必须包含 value 或 equals", schema))
    unsupported = _unsupported_keys(value, {"column_group", "value", "equals"})
    if unsupported:
        errors.append(_nested_error(path, f"不支持属性: {_format_keys(unsupported)}", schema))
    return errors


def _validate_column_group_value(value: Any, path: str, schema: TargetSchema) -> list[str]:
    if isinstance(value, str) and value.strip():
        return []
    if isinstance(value, list) and value and all(isinstance(item, str) and item.strip() for item in value):
        return []
    return [_nested_error(path, "column_group 格式不对，必须是非空字符串或非空字符串列表", schema)]


def _validate_popup_reference_field_values(
    fields: dict[str, Any],
    path: str,
    schema: TargetSchema,
    *,
    strict_reference_values: bool = False,
) -> list[str]:
    errors: list[str] = []
    for field_name, value in fields.items():
        if not isinstance(value, dict):
            continue
        if strict_reference_values:
            errors.extend(_validate_popup_reference_select(value, f"{path}.{field_name}", schema))
            continue
        raw_filter = value.get("filter")
        if not isinstance(raw_filter, dict) or "conditions" not in raw_filter:
            continue
        conditions = raw_filter.get("conditions")
        condition_path = f"{path}.{field_name}.filter.conditions"
        if isinstance(conditions, dict):
            conditions = [conditions]
        if not isinstance(conditions, list) or not conditions:
            errors.append(_nested_error(condition_path, "格式不对，必须是非空列表", schema))
            continue
        for index, condition in enumerate(conditions, start=1):
            errors.extend(_validate_condition_item(condition, f"{condition_path}[{index}]", field_key="field", schema=schema))
    return errors


POPUP_REFERENCE_SELECTION_KEYS = frozenset(
    {
        "filter",
        "value",
        "values",
        "match",
        "matches",
        "row_number",
        "row_numbers",
        "row_index",
        "rows",
        "first_available",
        "select_first_available",
        "table",
        "table_name",
        "tab",
        "tabs",
        "tree",
        "trees",
    }
)

POPUP_REFERENCE_TAB_KEYS = frozenset({"label", "value", "name"})
POPUP_REFERENCE_TAB_UNSAFE_KEYS = frozenset({"selector", "css", "xpath", "locator"})

POPUP_REFERENCE_TREE_KEYS = frozenset(
    {
        "label",
        "value",
        "node",
        "name",
        "component_name",
        "component_label",
        "region_label",
    }
)
POPUP_REFERENCE_TREE_UNSAFE_KEYS = frozenset({"selector", "css", "xpath", "locator"})


def _validate_popup_reference_select(target: dict[str, Any], path: str, schema: TargetSchema) -> list[str]:
    raw_selections = target.get("selections", target.get("selection"))
    if raw_selections is None:
        return _validate_popup_reference_single_selection(target, path, schema)
    if isinstance(raw_selections, dict):
        raw_selections = [raw_selections]
    if not isinstance(raw_selections, list) or not raw_selections:
        return [_component_error(path, "popup_reference.select", "target.selections 格式不对，必须是非空列表", schema)]
    errors: list[str] = []
    for index, selection in enumerate(raw_selections, start=1):
        selection_path = f"{path}: popup_reference.select target.selections[{index}]"
        if not isinstance(selection, dict):
            errors.append(_nested_error(selection_path, "格式不对，必须是对象", schema))
            continue
        unsupported = _unsupported_keys(selection, POPUP_REFERENCE_SELECTION_KEYS)
        if unsupported:
            errors.append(_nested_error(selection_path, f"不支持属性: {_format_keys(unsupported)}", schema))
        errors.extend(_validate_popup_reference_single_selection(selection, selection_path, schema))
    return errors


def _validate_popup_reference_single_selection(target: dict[str, Any], path: str, schema: TargetSchema) -> list[str]:
    errors: list[str] = []
    errors.extend(_validate_popup_reference_tab_context(target, path, schema))
    errors.extend(_validate_popup_reference_tree_context(target, path, schema))
    raw_filter = target.get("filter")
    if isinstance(raw_filter, dict) and "conditions" in raw_filter:
        conditions = raw_filter.get("conditions")
        condition_path = f"{path}: popup_reference.select target.filter.conditions"
        if isinstance(conditions, dict):
            conditions = [conditions]
        if not isinstance(conditions, list) or not conditions:
            errors.append(_nested_error(condition_path, "格式不对，必须是非空列表", schema))
        else:
            for index, condition in enumerate(conditions, start=1):
                errors.extend(_validate_condition_item(condition, f"{condition_path}[{index}]", field_key="field", schema=schema))
    elif raw_filter is not None and not isinstance(raw_filter, (str, int, float)):
        errors.append(_component_error(path, "popup_reference.select", "target.filter 格式不对，必须是文本或 conditions 对象", schema))

    if _has_row_number_locator(target) or _wants_first_available(target):
        return errors
    if "match" in target and not isinstance(target.get("match"), dict):
        errors.append(
            _component_error(
                path,
                "popup_reference.select",
                "target.match 格式不对，必须是包含 column 和 equals 的对象；列表/树候选请使用 target.value",
                schema,
            )
        )
        return errors
    if "value" in target:
        if not _is_scalar_popup_reference_value(target.get("value")):
            errors.append(_component_error(path, "popup_reference.select", "target.value 格式不对，必须是非空文本或数字", schema))
        return errors
    if "values" in target:
        raw_values = target.get("values")
        if not isinstance(raw_values, list) or not raw_values:
            errors.append(_component_error(path, "popup_reference.select", "target.values 格式不对，必须是非空列表", schema))
            return errors
        for index, item in enumerate(raw_values, start=1):
            if not _is_scalar_popup_reference_value(item):
                errors.append(
                    _component_error(
                        path,
                        "popup_reference.select",
                        f"target.values[{index}] 格式不对，必须是非空文本或数字",
                        schema,
                    )
                )
        return errors
    if isinstance(target.get("match"), dict) and target["match"]:
        errors.extend(_validate_row_match(target["match"], f"{path}: popup_reference.select target.match", schema))
        return errors
    matches = target.get("matches")
    if matches is not None:
        if not isinstance(matches, list) or not matches:
            errors.append(_component_error(path, "popup_reference.select", "target.matches 格式不对，必须是非空列表", schema))
            return errors
        for index, match in enumerate(matches, start=1):
            if not isinstance(match, dict):
                errors.append(_component_error(path, "popup_reference.select", f"target.matches[{index}] 格式不对，必须是对象", schema))
                continue
            errors.extend(_validate_row_match(match, f"{path}: popup_reference.select target.matches[{index}]", schema))
        return errors
    errors.append(
        _component_error(
            path,
            "popup_reference.select",
            (
                f"{_popup_reference_context_error_prefix(target)} 只用于限定参照候选范围，必须同时包含最终选择目标: "
                "target.value / target.values / target.match / target.matches / target.row_number / target.first_available / target.selections"
                if _popup_reference_has_context(target)
                else "缺少选择目标: target.value / target.values / target.match / target.matches / target.row_number / target.first_available / target.selections"
            ),
            schema,
        )
    )
    return errors


def _validate_popup_reference_tab_context(target: dict[str, Any], path: str, schema: TargetSchema) -> list[str]:
    errors: list[str] = []
    if "tab" in target:
        errors.extend(_validate_popup_reference_tab_target(target.get("tab"), f"{path}: popup_reference.select target.tab", schema))
    if "tabs" in target:
        raw_tabs = target.get("tabs")
        if _is_scalar_popup_reference_value(raw_tabs) or isinstance(raw_tabs, dict):
            errors.extend(_validate_popup_reference_tab_target(raw_tabs, f"{path}: popup_reference.select target.tabs", schema))
        elif not isinstance(raw_tabs, list) or not raw_tabs:
            errors.append(_nested_error(f"{path}: popup_reference.select target.tabs", "格式不对，必须是非空文本、对象或列表", schema))
        else:
            for index, item in enumerate(raw_tabs, start=1):
                errors.extend(_validate_popup_reference_tab_target(item, f"{path}: popup_reference.select target.tabs[{index}]", schema))
    return errors


def _validate_popup_reference_tab_target(raw: Any, path: str, schema: TargetSchema) -> list[str]:
    if _is_scalar_popup_reference_value(raw):
        return []
    if not isinstance(raw, dict) or not raw:
        return [_nested_error(path, "格式不对，必须是非空文本、数字或对象", schema)]
    unsafe = sorted(str(key) for key in raw if str(key) in POPUP_REFERENCE_TAB_UNSAFE_KEYS)
    if unsafe:
        return [_nested_error(path, f"不支持裸 DOM selector: {_format_keys(unsafe)}", schema)]
    unsupported = _unsupported_keys(raw, POPUP_REFERENCE_TAB_KEYS)
    if unsupported:
        return [_nested_error(path, f"不支持属性: {_format_keys(unsupported)}", schema)]
    if not any(str(raw.get(key) or "").strip() for key in ("label", "value", "name")):
        return [_nested_error(path, "缺少语义化页签目标: label / value / name", schema)]
    return []


def _validate_popup_reference_tree_context(target: dict[str, Any], path: str, schema: TargetSchema) -> list[str]:
    errors: list[str] = []
    if "tree" in target:
        errors.extend(_validate_popup_reference_tree_target(target.get("tree"), f"{path}: popup_reference.select target.tree", schema))
    if "trees" in target:
        raw_trees = target.get("trees")
        if not isinstance(raw_trees, list) or not raw_trees:
            errors.append(_nested_error(f"{path}: popup_reference.select target.trees", "格式不对，必须是非空列表", schema))
        else:
            for index, item in enumerate(raw_trees, start=1):
                errors.extend(_validate_popup_reference_tree_target(item, f"{path}: popup_reference.select target.trees[{index}]", schema))
    return errors


def _validate_popup_reference_tree_target(raw: Any, path: str, schema: TargetSchema) -> list[str]:
    if _is_scalar_popup_reference_value(raw):
        return []
    if not isinstance(raw, dict) or not raw:
        return [_nested_error(path, "格式不对，必须是非空文本、数字或对象", schema)]
    unsafe = sorted(str(key) for key in raw if str(key) in POPUP_REFERENCE_TREE_UNSAFE_KEYS)
    if unsafe:
        return [_nested_error(path, f"不支持裸 DOM selector: {_format_keys(unsafe)}", schema)]
    unsupported = _unsupported_keys(raw, POPUP_REFERENCE_TREE_KEYS)
    if unsupported:
        return [_nested_error(path, f"不支持属性: {_format_keys(unsupported)}", schema)]
    if not any(str(raw.get(key) or "").strip() for key in ("label", "value", "node", "name")):
        return [_nested_error(path, "缺少语义化树目标: label / value / node / name", schema)]
    return []


def _validate_attachment_upload(target: dict[str, Any], path: str, schema: TargetSchema) -> list[str]:
    if "attachments" in target:
        raw = target.get("attachments")
        if not isinstance(raw, list) or not raw:
            return [_component_error(path, "attachment.upload", "target.attachments 格式不对，必须是非空列表", schema)]
        errors: list[str] = []
        for index, item in enumerate(raw, start=1):
            if not isinstance(item, dict):
                errors.append(_component_error(path, "attachment.upload", f"target.attachments[{index}] 格式不对，必须是对象", schema))
                continue
            attachment_type = item.get("type") or item.get("attachment_type") or item.get("name")
            if not str(attachment_type or "").strip() or not str(item.get("file") or item.get("path") or "").strip():
                errors.append(_component_error(path, "attachment.upload", f"target.attachments[{index}] 必须包含 type 和 file", schema))
        return errors
    if not str(target.get("file") or target.get("path") or "").strip():
        return [_component_error(path, "attachment.upload", "缺少 target.attachments 或 target.file", schema)]
    if not str(target.get("type") or target.get("attachment_type") or target.get("name") or "").strip():
        return [_component_error(path, "attachment.upload", "单文件写法缺少 target.type", schema)]
    return []


def _validate_import_upload(target: dict[str, Any], path: str, schema: TargetSchema) -> list[str]:
    if any(key in target for key in ("file", "files", "path")):
        return []
    return [_component_error(path, "import.upload", "缺少 target.file 或 target.files", schema)]


def _validate_transfer_dialog_select(target: dict[str, Any], path: str, schema: TargetSchema) -> list[str]:
    if any(key in target for key in ("items", "targets", "matches", "match", "equals")):
        return []
    left = target.get("left") or target.get("source")
    if isinstance(left, dict) and any(key in left for key in ("items", "targets", "matches", "match")):
        return []
    return [_component_error(path, "transfer_dialog.select", "缺少 target.items 或 target.left.matches", schema)]


def _validate_row_match(match: dict[str, Any], path: str, schema: TargetSchema) -> list[str]:
    errors: list[str] = []
    allowed = {"column", "equals", "contains", "conditions", "all"}
    unsupported = _unsupported_keys(match, allowed)
    if unsupported:
        errors.append(_nested_error(path, f"不支持属性: {_format_keys(unsupported)}", schema))
    if "conditions" in match:
        raw_conditions = match.get("conditions")
    else:
        raw_conditions = match.get("all")
    if raw_conditions is not None:
        if isinstance(raw_conditions, dict):
            raw_conditions = [raw_conditions]
        if not isinstance(raw_conditions, list) or not raw_conditions:
            errors.append(_nested_error(f"{path}.conditions", "格式不对，必须是非空列表", schema))
            return errors
        for index, condition in enumerate(raw_conditions, start=1):
            errors.extend(_validate_condition_item(condition, f"{path}.conditions[{index}]", field_key="column", schema=schema))
        return errors
    if not (match.get("equals") is not None or match.get("contains") is not None):
        errors.append(_nested_error(path, "格式不对，必须包含 equals/contains 或 conditions", schema))
    return errors


def _validate_condition_item(item: Any, path: str, field_key: str, schema: TargetSchema) -> list[str]:
    if not isinstance(item, dict):
        return [_nested_error(path, "格式不对，必须是对象", schema)]
    errors: list[str] = []
    allowed = {field_key, "equals"}
    unsupported = _unsupported_keys(item, allowed)
    if unsupported:
        errors.append(_nested_error(path, f"不支持属性: {_format_keys(unsupported)}", schema))
    if not str(item.get(field_key) or "").strip() or item.get("equals") is None:
        errors.append(_nested_error(path, f"格式不对，必须包含 {field_key} 和 equals", schema))
    errors.extend(_validate_multi_select_assignment_list(item.get("equals"), f"{path}.equals", schema))
    return errors


def _validate_field_assignment_lists(fields: dict[str, Any], path: str, schema: TargetSchema) -> list[str]:
    errors: list[str] = []
    for field_name, value in fields.items():
        actual = value
        if _is_editable_table_column_group_wrapper(value):
            actual = value.get("value", value.get("equals"))
        errors.extend(_validate_multi_select_assignment_list(actual, f"{path}.{field_name}", schema))
    return errors


def _validate_multi_select_assignment_list(value: Any, path: str, schema: TargetSchema) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized = [" ".join(str(item or "").split()).strip() for item in value]
    duplicates = sorted({item for item in normalized if normalized.count(item) > 1})
    if not duplicates:
        return []
    return [_nested_error(path, f"多选目标列表包含重复值: {', '.join(duplicates)}", schema)]


def _page_error(path: str, detail: str) -> str:
    return f"{path}: {detail}\n{OPEN_MENU_EXAMPLE}"


def _component_error(path: str, label: str, detail: str, schema: TargetSchema) -> str:
    return f"{path}: {label} {detail}\n{schema.example}"


def _nested_error(path: str, detail: str, schema: TargetSchema) -> str:
    return f"{path} {detail}\n{schema.example}"


def _has_row_number_locator(target: dict[str, Any]) -> bool:
    return any(target.get(key) is not None for key in ("row_number", "row_numbers", "row_index"))


def _wants_first_available(target: dict[str, Any]) -> bool:
    return bool(target.get("first_available") or target.get("select_first_available"))


def _wants_select_all(target: dict[str, Any]) -> bool:
    return target.get("select_all") is True


def _has_text(target: dict[str, Any], key: str) -> bool:
    return str(target.get(key) or "").strip() != ""


def _has_non_empty_list(target: dict[str, Any], key: str) -> bool:
    value = target.get(key)
    return isinstance(value, list) and any(str(item or "").strip() for item in value)


def _is_scalar_popup_reference_value(value: Any) -> bool:
    return value is not None and not isinstance(value, (bool, dict, list, tuple, set)) and str(value).strip() != ""


def _popup_reference_has_tree_context(target: dict[str, Any]) -> bool:
    return "tree" in target or "trees" in target


def _popup_reference_has_tab_context(target: dict[str, Any]) -> bool:
    return "tab" in target or "tabs" in target


def _popup_reference_has_context(target: dict[str, Any]) -> bool:
    return _popup_reference_has_tab_context(target) or _popup_reference_has_tree_context(target)


def _popup_reference_context_error_prefix(target: dict[str, Any]) -> str:
    keys: list[str] = []
    if "tab" in target:
        keys.append("target.tab")
    if "tabs" in target:
        keys.append("target.tabs")
    if "tree" in target:
        keys.append("target.tree")
    if "trees" in target:
        keys.append("target.trees")
    return " / ".join(keys) or "target"


def _unsupported_keys(payload: dict[str, Any], allowed: set[str]) -> list[str]:
    return sorted(str(key) for key in payload if str(key) not in allowed)


def _format_keys(keys: list[str]) -> str:
    return ", ".join(keys)
