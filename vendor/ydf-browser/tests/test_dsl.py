import json
from pathlib import Path

import pytest

from ydf_browser.dsl import (
    COMPONENT_TARGET_SCHEMAS,
    VALID_COMPONENT_OPERATIONS,
    load_dsl,
    load_dsl_document,
)


def _suite_payload(steps, *, code: str = "suite", name: str = "测试集", case_code: str = "case") -> dict:
    return {
        "suite": {
            "code": code,
            "name": name,
            "tenant": "财政一体化",
            "default_org": "049002",
        },
        "cases": [
            {
                "code": case_code,
                "name": "用例",
                "user": "默认用户",
                "steps": steps,
            }
        ],
    }


def test_dsl_schema_documents_editable_table_column_group() -> None:
    schema = json.loads(Path("schemas/dsl.schema.json").read_text(encoding="utf-8"))
    assert schema["$defs"]["multiSelectExactAssignmentValue"]["then"]["uniqueItems"] is True
    assert "editableTableFillRowTarget" in schema["$defs"]
    assert "columnGroup" in schema["$defs"]
    fill_row_branch = [
        branch
        for branch in schema["$defs"]["step"]["oneOf"][1]["allOf"]
        if branch.get("then", {}).get("properties", {}).get("target", {}).get("$ref")
        == "#/$defs/editableTableFillRowTarget"
    ]
    assert fill_row_branch


def test_dsl_schema_applies_exact_assignment_values_to_query_and_form() -> None:
    schema = json.loads(Path("schemas/dsl.schema.json").read_text(encoding="utf-8"))
    refs = {
        branch.get("then", {}).get("properties", {}).get("target", {}).get("$ref")
        for branch in schema["$defs"]["step"]["oneOf"][1]["allOf"]
    }

    assert "#/$defs/querySearchTarget" in refs
    assert "#/$defs/formFillTarget" in refs
    assert schema["$defs"]["queryCondition"]["properties"]["equals"] == {
        "$ref": "#/$defs/multiSelectExactAssignmentValue"
    }
    assert schema["$defs"]["formFillFields"]["oneOf"][0]["additionalProperties"] == {
        "$ref": "#/$defs/multiSelectExactAssignmentValue"
    }


def test_load_dsl_supports_page_and_component_steps() -> None:
    steps = load_dsl(
        {
            "steps": [
                {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
                {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
            ]
        }
    )

    assert len(steps) == 2
    assert steps[0].kind == "page"
    assert steps[0].action == "open_menu"
    assert steps[1].kind == "component"
    assert steps[1].component == "toolbar"
    assert steps[1].operation == "click"
    assert steps[1].target == {"label": "保存"}


def test_load_dsl_document_accepts_tree_select_labels_for_multiselect() -> None:
    document = load_dsl_document(
        _suite_payload(
            [
                {
                    "component": "tree",
                    "operation": "select",
                    "target": {
                        "name": "区划树",
                        "labels": ["360000001 南昌市", "360100001 市本级"],
                    },
                }
            ]
        )
    )

    target = document.cases[0].steps[0].target
    assert target == {"name": "区划树", "labels": ["360000001 南昌市", "360100001 市本级"]}


def test_load_dsl_document_accepts_notification_close_target() -> None:
    document = load_dsl_document(
        _suite_payload(
            [
                {
                    "component": "notification",
                    "operation": "close",
                    "target": {
                        "type": "error",
                        "contains": "请联系管理员",
                        "label": "确定",
                    },
                }
            ]
        )
    )

    step = document.cases[0].steps[0]
    assert step.component == "notification"
    assert step.operation == "close"
    assert step.target == {"type": "error", "contains": "请联系管理员", "label": "确定"}


def test_load_dsl_document_accepts_amount_unit_set() -> None:
    document = load_dsl_document(
        _suite_payload(
            [
                {
                    "component": "amount_unit",
                    "operation": "set",
                    "target": {"value": "元"},
                }
            ]
        )
    )

    step = document.cases[0].steps[0]
    assert step.component == "amount_unit"
    assert step.operation == "set"
    assert step.target == {"value": "元"}


def test_load_dsl_document_accepts_workflow_result_operations() -> None:
    document = load_dsl_document(
        _suite_payload(
            [
                {
                    "component": "workflow_result",
                    "operation": "assert",
                    "target": {"total": 2, "succeeded": 1, "failed": 1},
                },
                {"component": "workflow_result", "operation": "details", "target": {}},
                {"component": "dialog", "operation": "confirm", "target": {"label": "确定"}},
                {"component": "workflow_result", "operation": "confirm", "target": {}},
            ]
        )
    )

    assert [(step.component, step.operation) for step in document.cases[0].steps] == [
        ("workflow_result", "assert"),
        ("workflow_result", "details"),
        ("dialog", "confirm"),
        ("workflow_result", "confirm"),
    ]


def test_load_dsl_document_accepts_workflow_panel_click() -> None:
    document = load_dsl_document(_suite_payload([
        {"component": "workflow_panel", "operation": "click", "target": {"label": "撤回审批"}},
    ]))
    step = document.cases[0].steps[0]
    assert (step.component, step.operation, step.target) == (
        "workflow_panel", "click", {"label": "撤回审批"},
    )


@pytest.mark.parametrize("target", [{}, {"label": " "}, {"label": 1}, {"label": True},
                                   {"label": "撤回审批", "selector": "#action"}])
def test_load_dsl_document_rejects_invalid_workflow_panel_target(target) -> None:
    with pytest.raises(ValueError, match="workflow_panel.click"):
        load_dsl_document(_suite_payload([
            {"component": "workflow_panel", "operation": "click", "target": target},
        ]))


@pytest.mark.parametrize(
    ("target", "message"),
    [
        ({}, "至少声明一个统计字段"),
        ({"total": "2"}, "必须是整数"),
        ({"total": True}, "必须是整数"),
    ],
)
def test_load_dsl_document_rejects_invalid_workflow_result_assert_target(target, message) -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            _suite_payload(
                [
                    {
                        "component": "workflow_result",
                        "operation": "assert",
                        "target": target,
                    }
                ]
            )
        )

    assert message in str(exc.value)


def test_load_dsl_document_rejects_workflow_result_unknown_target_key() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            _suite_payload(
                [
                    {
                        "component": "workflow_result",
                        "operation": "details",
                        "target": {"selector": ".error-content"},
                    }
                ]
            )
        )

    assert "workflow_result.details" in str(exc.value)
    assert "selector" in str(exc.value)


def test_dsl_json_schema_documents_workflow_result_targets() -> None:
    schema = json.loads(Path("schemas/dsl.schema.json").read_text(encoding="utf-8"))
    assert "workflow_result" in schema["$defs"]["step"]["oneOf"][1]["properties"]["component"]["enum"]
    assert "workflowResultAssertTarget" in schema["$defs"]
    assert "workflowResultDetailsTarget" in schema["$defs"]
    assert "workflowResultConfirmTarget" in schema["$defs"]


def test_dsl_json_schema_constrains_workflow_panel_operation_and_target() -> None:
    schema = json.loads(Path("schemas/dsl.schema.json").read_text(encoding="utf-8"))
    target = schema["$defs"]["workflowPanelClickTarget"]
    assert target["required"] == ["label"]
    assert target["additionalProperties"] is False
    assert target["properties"]["label"]["type"] == "string"
    branches = schema["$defs"]["step"]["oneOf"][1]["allOf"]
    panel = next(branch for branch in branches
                 if branch["if"]["properties"].get("component", {}).get("const") == "workflow_panel")
    assert panel["then"]["properties"]["operation"] == {"const": "click"}


def test_load_dsl_document_accepts_submitted_import_with_later_business_assertion() -> None:
    document = load_dsl_document(
        _suite_payload(
            [
                {
                    "component": "import",
                    "operation": "upload",
                    "target": {
                        "label": "导入并测算",
                        "fieldid": "custom_import",
                        "file": "/tmp/direct.xlsx",
                        "assert": {"status": "submitted"},
                    },
                },
                {"component": "tab", "operation": "click", "target": {"label": "测算结果"}},
                {
                    "component": "table",
                    "operation": "assert_row_values",
                    "target": {
                        "match": {"column": "地区", "equals": "南昌市"},
                        "fields": {"本次应拨付(万元)": "56,942.32"},
                    },
                },
            ]
        )
    )

    assert document.cases[0].steps[0].target["fieldid"] == "custom_import"
    assert document.cases[0].steps[0].target["assert"]["status"] == "submitted"


@pytest.mark.parametrize(
    ("steps", "message"),
    [
        (
            [
                {
                    "component": "import",
                    "operation": "upload",
                    "target": {
                        "file": "/tmp/direct.xlsx",
                        "assert": {"status": "submitted"},
                    },
                }
            ],
            "不能是用例最后一步",
        ),
        (
            [
                {
                    "component": "import",
                    "operation": "upload",
                    "target": {
                        "file": "/tmp/direct.xlsx",
                        "assert": {"status": "submitted"},
                    },
                },
                {"component": "tab", "operation": "click", "target": {"label": "测算结果"}},
            ],
            "后续必须包含业务断言",
        ),
    ],
)
def test_load_dsl_document_rejects_submitted_import_without_business_assertion(steps, message) -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(_suite_payload(steps))

    assert message in str(exc.value)


def test_load_dsl_document_accepts_form_capture_values() -> None:
    document = load_dsl_document(
        _suite_payload(
            [
                {
                    "component": "form",
                    "operation": "capture_values",
                    "target": {"capture": {"tel": "手机号"}},
                }
            ]
        )
    )

    step = document.cases[0].steps[0]
    assert step.component == "form"
    assert step.operation == "capture_values"
    assert step.target == {"capture": {"tel": "手机号"}}


@pytest.mark.parametrize(
    ("target", "message"),
    [
        ({}, "缺少 target.capture"),
        ({"capture": {}}, "缺少 target.capture"),
        ({"capture": {"random.suffix": "手机号"}}, "random 为系统保留变量命名空间"),
        ({"capture": {"tel": ""}}, "来源字段必须是非空字符串"),
        ({"capture": {"tel": {"field": "手机号"}}}, "来源字段必须是非空字符串"),
    ],
)
def test_load_dsl_document_rejects_invalid_form_capture_values(target, message) -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            _suite_payload(
                [
                    {
                        "component": "form",
                        "operation": "capture_values",
                        "target": target,
                    }
                ]
            )
        )

    assert message in str(exc.value)


def test_load_dsl_document_accepts_bpr_start_and_stop() -> None:
    document = load_dsl_document(
        _suite_payload(
            [
                {
                    "component": "bpr",
                    "operation": "start",
                    "target": {"name": "修改并取消"},
                },
                {
                    "component": "bpr",
                    "operation": "stop",
                    "target": {},
                },
            ]
        )
    )

    start_step, stop_step = document.cases[0].steps
    assert start_step.component == "bpr"
    assert start_step.operation == "start"
    assert start_step.target == {"name": "修改并取消"}
    assert stop_step.component == "bpr"
    assert stop_step.operation == "stop"
    assert stop_step.target == {}


def test_form_fill_preserves_free_text_and_structured_reference_targets() -> None:
    fields = {"支付摘要": "新支付用途", "收款人全称": {"first_available": True}}
    document = load_dsl_document(_suite_payload([
        {"component": "form", "operation": "fill", "target": {"fields": fields}},
    ]))
    assert document.cases[0].steps[0].target["fields"] == fields
    assert "支付摘要: 新支付用途" in COMPONENT_TARGET_SCHEMAS[("form", "fill")].example


def test_load_dsl_document_accepts_editable_table_column_group_field_wrapper() -> None:
    document = load_dsl_document(
        _suite_payload(
            [
                {
                    "component": "editable_table",
                    "operation": "fill_row",
                    "target": {
                        "table": "三级项目同步",
                        "row_number": 1,
                        "fields": {
                            "普通列名A": "值A",
                            "当年财政拨款(万元)": {
                                "column_group": "全年执行决算金额",
                                "value": 3,
                            },
                            "项目目录": {
                                "column_group": ["项目信息", "基础信息"],
                                "value": {"tree": {"label": "101 综合司01"}, "first_available": True},
                            },
                        },
                    },
                }
            ]
        )
    )

    target = document.cases[0].steps[0].target
    assert target["fields"]["当年财政拨款(万元)"] == {
        "column_group": "全年执行决算金额",
        "value": 3,
    }
    assert target["fields"]["项目目录"]["column_group"] == ["项目信息", "基础信息"]


def test_load_dsl_document_accepts_editable_table_column_group_list_item() -> None:
    document = load_dsl_document(
        _suite_payload(
            [
                {
                    "component": "editable_table",
                    "operation": "fill_row",
                    "target": {
                        "fields": [
                            {
                                "field": "当年财政拨款(万元)",
                                "column_group": "全年执行决算金额",
                                "equals": 3,
                            }
                        ]
                    },
                }
            ]
        )
    )

    assert document.cases[0].steps[0].target["fields"] == [
        {"field": "当年财政拨款(万元)", "column_group": "全年执行决算金额", "equals": 3}
    ]


@pytest.mark.parametrize(
    ("field_value", "message"),
    [
        ({"column_group": "全年执行决算金额"}, "必须包含 value 或 equals"),
        ({"column_group": [], "value": 3}, "column_group 格式不对"),
        ({"column_group": ["全年执行决算金额", ""], "value": 3}, "column_group 格式不对"),
    ],
)
def test_load_dsl_document_rejects_invalid_editable_table_column_group_wrapper(field_value, message) -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            _suite_payload(
                [
                    {
                        "component": "editable_table",
                        "operation": "fill_row",
                        "target": {"fields": {"当年财政拨款(万元)": field_value}},
                    }
                ]
            )
        )

    assert message in str(exc.value)


def test_load_dsl_document_rejects_nested_bpr_start() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            _suite_payload(
                [
                    {"component": "bpr", "operation": "start", "target": {}},
                    {"component": "bpr", "operation": "start", "target": {}},
                    {"component": "bpr", "operation": "stop", "target": {}},
                ]
            )
        )

    message = str(exc.value)
    assert "不支持嵌套 BPR 录制" in message
    assert "cases[1].steps[2]" in message


def test_load_dsl_document_rejects_bpr_stop_without_active_session() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(_suite_payload([{"component": "bpr", "operation": "stop", "target": {}}]))

    message = str(exc.value)
    assert "没有正在录制的 BPR session" in message
    assert "cases[1].steps[1]" in message


def test_load_dsl_document_rejects_missing_bpr_stop() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(_suite_payload([{"component": "bpr", "operation": "start", "target": {}}]))

    message = str(exc.value)
    assert "BPR 录制缺少 bpr.stop" in message
    assert "cases[1].steps[1]" in message


def test_load_dsl_document_can_skip_bpr_state_validation_for_non_performance_run() -> None:
    document = load_dsl_document(
        _suite_payload([{"component": "bpr", "operation": "start", "target": {}}]),
        validate_bpr_state=False,
    )

    assert document.cases[0].steps[0].component == "bpr"
    assert document.cases[0].steps[0].operation == "start"


@pytest.mark.parametrize("target", [{"value": "美元"}, {"label": "设置金额单位", "value": "元"}])
def test_load_dsl_document_rejects_invalid_amount_unit_set(target: dict) -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            _suite_payload(
                [
                    {
                        "component": "amount_unit",
                        "operation": "set",
                        "target": target,
                    }
                ]
            )
        )

    assert "金额单位只支持 `元` 和 `万元`" in str(exc.value) or "amount_unit.set target 不支持属性: label" in str(exc.value)


def test_load_dsl_document_rejects_notification_close_without_match_condition() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            _suite_payload(
                [
                    {
                        "component": "notification",
                        "operation": "close",
                        "target": {"label": "确定"},
                    }
                ]
            )
        )

    message = str(exc.value)
    assert "notification.close" in message
    assert "缺少提示匹配条件" in message


@pytest.mark.parametrize("node", ["root", "first_leaf"])
def test_load_dsl_document_accepts_tree_select_node_shortcuts(node: str) -> None:
    document = load_dsl_document(
        _suite_payload(
            [
                {
                    "component": "tree",
                    "operation": "select",
                    "target": {
                        "name": "内部机构",
                        "node": node,
                    },
                }
            ]
        )
    )

    target = document.cases[0].steps[0].target
    assert target == {"name": "内部机构", "node": node}


def test_load_dsl_document_rejects_tree_select_node_with_explicit_label() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            _suite_payload(
                [
                    {
                        "component": "tree",
                        "operation": "select",
                        "target": {
                            "name": "内部机构",
                            "node": "root",
                            "label": "001 办公室",
                        },
                    }
                ]
            )
        )

    assert "target.node 不能和 target.label/target.labels/target.values 同时使用" in str(exc.value)


def test_load_dsl_document_rejects_unknown_tree_select_node_shortcut() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            _suite_payload(
                [
                    {
                        "component": "tree",
                        "operation": "select",
                        "target": {
                            "node": "last_leaf",
                        },
                    }
                ]
            )
        )

    assert "target.node 只支持 root 或 first_leaf" in str(exc.value)


def test_load_dsl_document_supports_test_suite_cases() -> None:
    document = load_dsl_document(
        {
            "suite": {
                "code": "execute_project_init",
                "name": "执行项目立项",
                "description": "覆盖执行项目立项主链路",
                "tenant": "财政一体化",
                "fiscal_year": "2027",
                "on_case_failure": "stop_suite",
            },
            "cases": [
                {
                    "code": "query-by-manager",
                    "name": "按项目负责人查询",
                    "description": "验证查询和表格断言",
                    "user": "张三",
                    "default_org": "049002",
                    "tags": ["query", "smoke"],
                    "steps": [
                        {"action": "open_menu", "menu_path": "项目库>>执行项目管理>>执行项目立项"},
                        {
                            "component": "query",
                            "operation": "search",
                            "target": {"conditions": [{"field": "项目负责人", "equals": "孙丽娜"}]},
                        },
                    ],
                }
            ],
        }
    )

    assert document.is_suite is True
    assert document.suite.code == "execute_project_init"
    assert document.suite.name == "执行项目立项"
    assert document.suite.tenant == "财政一体化"
    assert document.suite.fiscal_year == "2027"
    assert document.suite.on_case_failure == "stop_suite"
    assert document.suite.to_dict()["fiscal_year"] == "2027"
    assert len(document.cases) == 1
    case = document.cases[0]
    assert case.code == "query-by-manager"
    assert case.name == "按项目负责人查询"
    assert case.description == "验证查询和表格断言"
    assert case.user == "张三"
    assert case.default_org == "049002"
    assert case.tags == ["query", "smoke"]
    assert [step.to_dict() for step in case.steps] == [
        {"action": "open_menu", "menu_path": "项目库>>执行项目管理>>执行项目立项"},
        {
            "component": "query",
            "operation": "search",
            "target": {"conditions": [{"field": "项目负责人", "equals": "孙丽娜"}]},
        },
    ]


def test_load_dsl_document_rejects_legacy_steps_document() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document({"steps": [{"action": "open_menu", "menu_path": "项目管理>>项目立项"}]})

    assert "旧式 steps DSL 已废弃" in str(exc.value)
    assert "suite + cases + steps" in str(exc.value)


@pytest.mark.parametrize(
    ("suite_payload", "message"),
    [
        ({"code": "missing-tenant", "name": "缺租户", "default_org": "049002"}, "suite.tenant 必填"),
        ({"code": "missing-org", "name": "缺组织", "tenant": "财政一体化"}, "suite.default_org 或 cases[1].default_org 必填"),
    ],
)
def test_load_dsl_document_requires_suite_tenant_and_dsl_default_org(suite_payload, message) -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            {
                "suite": suite_payload,
                "cases": [
                    {
                        "code": "case-a",
                        "name": "用例 A",
                        "user": "默认用户",
                        "steps": [{"action": "open_menu", "menu_path": "项目管理>>项目立项"}],
                    }
                ],
            }
        )

    assert message in str(exc.value)


def test_load_dsl_document_ignores_missing_suite_fiscal_year() -> None:
    document = load_dsl_document(
        {
            "suite": {
                "code": "no-fiscal-year",
                "name": "无业务年度",
                "tenant": "财政一体化",
                "default_org": "049002",
            },
            "cases": [
                {
                    "code": "case-a",
                    "name": "用例 A",
                    "user": "默认用户",
                    "steps": [{"action": "open_menu", "menu_path": "项目管理>>项目立项"}],
                }
            ],
        }
    )

    assert document.suite.fiscal_year == ""
    assert document.suite.to_dict()["fiscal_year"] == ""


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {
                "suite": {
                    "code": "tenant-alias",
                    "name": "租户别名",
                    "tenant_name": "财政一体化",
                    "default_org": "049002",
                },
                "cases": [
                    {
                        "code": "case-a",
                        "name": "用例 A",
                        "user": "默认用户",
                        "steps": [{"action": "open_menu", "menu_path": "项目管理>>项目立项"}],
                    }
                ],
            },
            "suite.tenant_name 已废弃",
        ),
        (
            {
                "suite": {"code": "org-alias", "name": "组织别名", "tenant": "财政一体化"},
                "cases": [
                    {
                        "code": "case-a",
                        "name": "用例 A",
                        "user": "默认用户",
                        "default_org_code": "049002",
                        "steps": [{"action": "open_menu", "menu_path": "项目管理>>项目立项"}],
                    }
                ],
            },
            "cases[1].default_org_code 已废弃",
        ),
        (
            {
                "suite": {"code": "credentials", "name": "凭据", "tenant": "财政一体化", "default_org": "049002"},
                "cases": [
                    {
                        "code": "case-a",
                        "name": "用例 A",
                        "username": "real-user",
                        "password": "secret",
                        "steps": [{"action": "open_menu", "menu_path": "项目管理>>项目立项"}],
                    }
                ],
            },
            "cases[1].username/password 已废弃",
        ),
        (
            {
                "suite": {
                    "code": "suite-credentials",
                    "name": "套件凭据",
                    "tenant": "财政一体化",
                    "default_org": "049002",
                    "username": "real-user",
                },
                "cases": [
                    {
                        "code": "case-a",
                        "name": "用例 A",
                        "user": "默认用户",
                        "steps": [{"action": "open_menu", "menu_path": "项目管理>>项目立项"}],
                    }
                ],
            },
            "suite.username/password 已废弃",
        ),
        (
            {
                "suite": {"code": "case-tenant", "name": "用例租户", "tenant": "财政一体化", "default_org": "049002"},
                "cases": [
                    {
                        "code": "case-a",
                        "name": "用例 A",
                        "user": "默认用户",
                        "tenant": "单位内控",
                        "steps": [{"action": "open_menu", "menu_path": "项目管理>>项目立项"}],
                    }
                ],
            },
            "cases[1].tenant 已废弃",
        ),
    ],
)
def test_load_dsl_document_rejects_deprecated_context_fields(payload, message) -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(payload)

    assert message in str(exc.value)


def test_load_dsl_document_uses_case_default_org_over_suite_default_org() -> None:
    document = load_dsl_document(
        {
            "suite": {
                "code": "org-precedence",
                "name": "组织优先级",
                "tenant": "财政一体化",
                "default_org": "049002",
            },
            "cases": [
                {
                    "code": "case-a",
                    "name": "用例 A",
                    "user": "默认用户",
                    "default_org": "049003",
                    "steps": [{"action": "open_menu", "menu_path": "项目管理>>项目立项"}],
                }
            ],
        }
    )

    assert document.suite.default_org == "049002"
    assert document.cases[0].default_org == "049003"


def test_load_dsl_document_resolves_external_variables_recursively() -> None:
    document = load_dsl_document(
        {
            "suite": {"code": "budget", "name": "预算指标", "tenant": "{{tenant}}"},
            "cases": [
                {
                    "code": "query-budget",
                    "name": "查询预算指标",
                    "user": "{{users.operator}}",
                    "default_org": "{{org_code}}",
                    "steps": [
                        {"action": "open_menu", "menu_path": "预算管理>>指标查询"},
                        {
                            "component": "query",
                            "operation": "search",
                            "target": {
                                "conditions": [
                                    {"field": "预算指标编码", "equals": "{{budget.indicator_code}}"},
                                    {"field": "备注", "equals": "运行批次-{{run_id}}"},
                                ]
                            },
                        },
                        {
                            "component": "table_row_selection",
                            "operation": "select",
                            "target": {"row_numbers": "{{row_numbers}}"},
                        },
                    ],
                }
            ],
        },
        variables={
            "users": {"operator": "默认用户"},
            "tenant": "财政一体化",
            "org_code": "049002",
            "budget": {"indicator_code": "3600000001"},
            "run_id": "20260508",
            "row_numbers": [1, 2],
        },
    )

    case = document.cases[0]
    assert case.user == "默认用户"
    assert case.default_org == "049002"
    assert case.steps[1].target["conditions"] == [
        {"field": "预算指标编码", "equals": "3600000001"},
        {"field": "备注", "equals": "运行批次-20260508"},
    ]
    assert case.steps[2].target == {"row_numbers": [1, 2]}


def test_load_dsl_document_accepts_table_row_selection_match_conditions() -> None:
    document = load_dsl_document(
        _suite_payload(
            [
                {"action": "open_menu", "menu_path": "预算管理>>指标查询"},
                {
                    "component": "table_row_selection",
                    "operation": "select",
                    "target": {
                        "match": {
                            "conditions": [
                                {"column": "三级项目名称", "equals": "tztj513004"},
                                {"column": "部门预算支出经济分类", "equals": "30101 基本工资"},
                            ]
                        }
                    },
                },
            ]
        )
    )

    assert document.cases[0].steps[1].target["match"]["conditions"] == [
        {"column": "三级项目名称", "equals": "tztj513004"},
        {"column": "部门预算支出经济分类", "equals": "30101 基本工资"},
    ]


def test_load_dsl_document_accepts_table_row_selection_rows() -> None:
    document = load_dsl_document(
        _suite_payload(
            [
                {"action": "open_menu", "menu_path": "预算管理>>指标查询"},
                {
                    "component": "table_row_selection",
                    "operation": "select",
                    "target": {
                        "rows": [
                            {"match": {"column": "项目代码", "equals": "A"}},
                            {"match": {"column": "项目代码", "equals": "B"}},
                        ]
                    },
                },
            ]
        )
    )

    assert document.cases[0].steps[1].target["rows"] == [
        {"match": {"column": "项目代码", "equals": "A"}},
        {"match": {"column": "项目代码", "equals": "B"}},
    ]


def test_load_dsl_document_accepts_table_row_selection_table_with_row_number() -> None:
    document = load_dsl_document(
        _suite_payload(
            [
                {"action": "open_menu", "menu_path": "预算管理>>指标查询"},
                {
                    "component": "table_row_selection",
                    "operation": "select",
                    "target": {"table": "消费明细", "row_number": 1},
                },
            ]
        )
    )

    assert document.cases[0].steps[1].target == {"table": "消费明细", "row_number": 1}


def test_load_dsl_document_accepts_table_row_selection_select_all() -> None:
    document = load_dsl_document(
        _suite_payload(
            [
                {"action": "open_menu", "menu_path": "预算管理>>指标查询"},
                {
                    "component": "table_row_selection",
                    "operation": "select",
                    "target": {"select_all": True},
                },
            ]
        )
    )

    assert document.cases[0].steps[1].target == {"select_all": True}


def test_load_dsl_document_rejects_table_row_selection_select_all_with_row_locator() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            _suite_payload(
                [
                    {"action": "open_menu", "menu_path": "预算管理>>指标查询"},
                    {
                        "component": "table_row_selection",
                        "operation": "select",
                        "target": {"select_all": True, "row_number": 1},
                    },
                ]
            )
        )

    assert "target.select_all 不能与行定位属性混用" in str(exc.value)


def test_load_dsl_document_rejects_table_row_selection_matches() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            _suite_payload(
                [
                    {"action": "open_menu", "menu_path": "预算管理>>指标查询"},
                    {
                        "component": "table_row_selection",
                        "operation": "select",
                        "target": {
                            "matches": [
                                {"column": "项目代码", "equals": "A"},
                                {"column": "项目代码", "equals": "B"},
                            ]
                        },
                    },
                ]
            )
        )

    assert "table_row_selection.select target 不支持属性: matches" in str(exc.value)


def test_load_dsl_document_supports_popup_reference_select() -> None:
    document = load_dsl_document(
        {
            "suite": {"code": "reference", "name": "按钮参照", "tenant": "财政一体化", "default_org": "049002"},
            "cases": [
                {
                    "code": "select-reference",
                    "name": "选择指标",
                    "steps": [
                        {
                            "component": "popup_reference",
                            "operation": "select",
                            "target": {
                                "title": "选择指标",
                                "filter": {
                                    "conditions": [
                                        {"field": "部门经济分类科目", "equals": "30101 基本工资"}
                                    ]
                                },
                                "match": {"column": "部门经济分类科目", "equals": "30101 基本工资"},
                            },
                        },
                        {
                            "component": "popup_reference",
                            "operation": "select",
                            "target": {"title": "选择指标", "row_number": 1},
                        },
                    ],
                }
            ],
        }
    )

    assert document.cases[0].steps[0].component == "popup_reference"
    assert document.cases[0].steps[0].target["match"] == {
        "column": "部门经济分类科目",
        "equals": "30101 基本工资",
    }
    assert document.cases[0].steps[1].target == {"title": "选择指标", "row_number": 1}


def test_load_dsl_document_preserves_popup_reference_match_contains() -> None:
    document = load_dsl_document(
        {
            "suite": {"code": "reference", "name": "按钮参照", "tenant": "财政一体化", "default_org": "049002"},
            "cases": [
                {
                    "code": "select-reference",
                    "name": "选择人员",
                    "steps": [
                        {
                            "component": "popup_reference",
                            "operation": "select",
                            "target": {
                                "title": "添加",
                                "filter": {"conditions": [{"field": "用户名称", "equals": "财会"}]},
                                "match": {"column": "用户名称", "contains": "财会"},
                            },
                        },
                    ],
                }
            ],
        }
    )

    assert document.cases[0].steps[0].target["match"] == {"column": "用户名称", "contains": "财会"}


def test_load_dsl_document_supports_popup_reference_sequential_table_selections() -> None:
    document = load_dsl_document(
        {
            "suite": {"code": "reference", "name": "主子表参照", "tenant": "财政一体化", "default_org": "049002"},
            "cases": [
                {
                    "code": "select-master-detail-reference",
                    "name": "选择主子表参照",
                    "steps": [
                        {
                            "component": "popup_reference",
                            "operation": "select",
                            "target": {
                                "title": "选择项目预算",
                                "selections": [
                                    {"table": "项目预算", "row_number": 1},
                                    {"table": "预算编制科目", "row_number": 2},
                                ],
                                "confirm": True,
                            },
                        }
                    ],
                }
            ],
        }
    )

    assert document.cases[0].steps[0].target["selections"] == [
        {"table": "项目预算", "row_number": 1},
        {"table": "预算编制科目", "row_number": 2},
    ]


def test_load_dsl_document_supports_popup_reference_tree_context_targets() -> None:
    document = load_dsl_document(
        _suite_payload(
            [
                {
                    "component": "form",
                    "operation": "fill",
                    "target": {
                        "fields": {
                            "项目负责人": {
                                "tree": {"label": "101 综合司01"},
                                "match": {"column": "人员名称", "equals": "人员二十一"},
                            }
                        }
                    },
                },
                {
                    "component": "popup_reference",
                    "operation": "select",
                    "target": {
                        "title": "项目负责人",
                        "tree": "101 综合司01",
                        "first_available": True,
                        "confirm_label": "保存",
                    },
                },
                {
                    "component": "popup_reference",
                    "operation": "select",
                    "target": {
                        "title": "项目负责人",
                        "selections": [
                            {
                                "tree": {"name": "部门树", "label": "101 综合司01"},
                                "match": {"column": "人员名称", "equals": "人员二十一"},
                            }
                        ],
                    },
                },
            ]
        )
    )

    fields = document.cases[0].steps[0].target["fields"]
    assert fields["项目负责人"]["tree"] == {"label": "101 综合司01"}
    assert document.cases[0].steps[1].target["tree"] == "101 综合司01"
    assert document.cases[0].steps[2].target["selections"][0]["tree"] == {
        "name": "部门树",
        "label": "101 综合司01",
    }


def test_load_dsl_document_supports_popup_reference_tab_context_targets() -> None:
    document = load_dsl_document(
        _suite_payload(
            [
                {
                    "component": "form",
                    "operation": "fill",
                    "target": {
                        "fields": {
                            "收款方户名": {
                                "tab": "本单位人员账户",
                                "filter": "苏康涯",
                                "match": {"column": "户名", "equals": "苏康涯"},
                            }
                        }
                    },
                },
                {
                    "component": "editable_table",
                    "operation": "fill_row",
                    "target": {
                        "table": "汇款转账",
                        "row_number": -1,
                        "fields": {
                            "收款方户名": {
                                "tabs": [{"label": "本单位人员账户"}],
                                "filter": "苏康涯",
                                "match": {"column": "户名", "equals": "苏康涯"},
                            }
                        },
                    },
                },
                {
                    "component": "popup_reference",
                    "operation": "select",
                    "target": {
                        "title": "收款方户名",
                        "tab": {"name": "本单位人员账户"},
                        "value": "苏康涯",
                    },
                },
            ]
        )
    )

    steps = document.cases[0].steps
    assert steps[0].target["fields"]["收款方户名"]["tab"] == "本单位人员账户"
    assert steps[1].target["fields"]["收款方户名"]["tabs"] == [{"label": "本单位人员账户"}]
    assert steps[2].target["tab"] == {"name": "本单位人员账户"}


def test_load_dsl_document_rejects_popup_reference_tree_without_final_selection() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            _suite_payload(
                [
                    {
                        "component": "form",
                        "operation": "fill",
                        "target": {"fields": {"项目负责人": {"tree": "101 综合司01"}}},
                    }
                ]
            )
        )

    message = str(exc.value)
    assert "项目负责人" in message
    assert "tree 只用于限定参照候选范围" in message


def test_load_dsl_document_rejects_popup_reference_tab_without_final_selection() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            _suite_payload(
                [
                    {
                        "component": "form",
                        "operation": "fill",
                        "target": {"fields": {"收款方户名": {"tab": "本单位人员账户"}}},
                    }
                ]
            )
        )

    message = str(exc.value)
    assert "收款方户名" in message
    assert "tab 只用于限定参照候选范围" in message


def test_load_dsl_document_rejects_popup_reference_tree_raw_selector() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            _suite_payload(
                [
                    {
                        "component": "popup_reference",
                        "operation": "select",
                        "target": {
                            "title": "项目负责人",
                            "tree": {"selector": ".wui-tree-node"},
                            "match": {"column": "人员名称", "equals": "人员二十一"},
                        },
                    }
                ]
            )
        )

    message = str(exc.value)
    assert "target.tree" in message
    assert "不支持裸 DOM selector" in message


def test_load_dsl_document_rejects_popup_reference_tab_raw_selector() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            _suite_payload(
                [
                    {
                        "component": "popup_reference",
                        "operation": "select",
                        "target": {
                            "title": "收款方户名",
                            "tab": {"selector": ".w-tabs-tab"},
                            "match": {"column": "户名", "equals": "苏康涯"},
                        },
                    }
                ]
            )
        )

    message = str(exc.value)
    assert "target.tab" in message
    assert "不支持裸 DOM selector" in message


def test_load_dsl_document_supports_popup_reference_value_and_values() -> None:
    document = load_dsl_document(
        {
            "suite": {"code": "reference", "name": "列表树参照", "tenant": "财政一体化", "default_org": "049002"},
            "cases": [
                {
                    "code": "select-reference-value",
                    "name": "选择列表树候选",
                    "steps": [
                        {
                            "component": "popup_reference",
                            "operation": "select",
                            "target": {
                                "title": "单位遴选",
                                "value": "101001 江西省局本级（主管单位/单位经办）",
                            },
                        },
                        {
                            "component": "popup_reference",
                            "operation": "select",
                            "target": {
                                "title": "预算项目",
                                "values": [
                                    "360000241010010000008 二级采购项目",
                                    "360000241010010000009 三级采购项目",
                                ],
                            },
                        },
                    ],
                }
            ],
        }
    )

    assert document.cases[0].steps[0].target["value"] == "101001 江西省局本级（主管单位/单位经办）"
    assert document.cases[0].steps[1].target["values"] == [
        "360000241010010000008 二级采购项目",
        "360000241010010000009 三级采购项目",
    ]


def test_load_dsl_document_rejects_scalar_popup_reference_match() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            _suite_payload(
                [
                    {
                        "component": "popup_reference",
                        "operation": "select",
                        "target": {
                            "title": "单位遴选",
                            "match": "101001 江西省局本级（主管单位/单位经办）",
                        },
                    }
                ]
            )
        )

    message = str(exc.value)
    assert "popup_reference.select target.match 格式不对" in message
    assert "列表/树候选请使用 target.value" in message


def test_load_dsl_document_rejects_empty_or_non_scalar_popup_reference_values() -> None:
    for values in ([], ["101001 江西省局本级（主管单位/单位经办）", {"equals": "101002"}]):
        with pytest.raises(ValueError) as exc:
            load_dsl_document(
                _suite_payload(
                    [
                        {
                            "component": "popup_reference",
                            "operation": "select",
                            "target": {"title": "单位遴选", "values": values},
                        }
                    ]
                )
            )

        message = str(exc.value)
        assert "target.values" in message


def test_load_dsl_document_accepts_popup_reference_value_semantics() -> None:
    document = load_dsl_document(
        {
            "suite": {"code": "dwzbgl_xz", "name": "单位指标管理", "tenant": "财政一体化", "default_org": "049002"},
            "cases": [
                {
                    "code": "add_bill",
                    "name": "新增追加单",
                    "steps": [
                        {
                            "component": "editable_table",
                            "operation": "fill_row",
                            "target": {
                                "table": "指标信息",
                                "row_number": 1,
                                "fields": {"政府预算支出经济分类": "50101 工资奖金津补贴"},
                            },
                        }
                    ],
                }
            ],
        }
    )

    fill_step = document.cases[0].steps[-1]
    assert fill_step.component == "editable_table"
    assert fill_step.operation == "fill_row"
    assert fill_step.target["fields"]["政府预算支出经济分类"] == "50101 工资奖金津补贴"


def test_load_dsl_document_accepts_editable_table_add_row_form_editor() -> None:
    document = load_dsl_document(
        _suite_payload(
            [
                {
                    "component": "editable_table",
                    "operation": "add_row",
                    "target": {"table": "计划明细", "label": "新增", "editor": "form"},
                }
            ]
        )
    )

    step = document.cases[0].steps[0]
    assert step.component == "editable_table"
    assert step.operation == "add_row"
    assert step.target["editor"] == "form"


def test_load_dsl_document_rejects_invalid_editable_table_add_row_editor() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            _suite_payload(
                [
                    {
                        "component": "editable_table",
                        "operation": "add_row",
                        "target": {"table": "计划明细", "label": "新增", "editor": "side_panel"},
                    }
                ]
            )
        )

    assert "editable_table.add_row target.editor 只支持 auto/form/inline" in str(exc.value)


def test_load_dsl_document_reports_missing_external_variable() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            {
                "suite": {"code": "budget", "name": "预算指标", "tenant": "财政一体化", "default_org": "049002"},
                "cases": [
                    {
                        "code": "query-budget",
                        "name": "查询预算指标",
                        "steps": [
                            {
                                "component": "query",
                                "operation": "search",
                                "target": {"conditions": [{"field": "预算指标编码", "equals": "{{budget_code}}"}]},
                            }
                        ],
                    }
                ],
            },
            variables={},
        )

    assert "未定义 DSL 变量: budget_code" in str(exc.value)
    assert "cases[1].steps[1].target.conditions[1].equals" in str(exc.value)


@pytest.mark.parametrize(
    ("value", "variables", "message"),
    [
        ("{{missing}}", {}, "未定义 DSL 变量: missing"),
        ("编号-{{missing}}", {}, "未定义 DSL 变量: missing"),
        ("${removed}", {}, "不支持 ${} 变量语法"),
        ("编号-{{object}}", {"object": {}}, "DSL 变量不能用于字符串拼接: object"),
    ],
)
def test_load_dsl_document_locates_variable_errors_in_later_cases(value, variables, message) -> None:
    payload = _suite_payload([{"action": "open_menu", "menu_path": "项目管理>>项目立项"}])
    payload["cases"].append({
        "code": "second-case",
        "name": "第二个用例",
        "steps": [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "form", "operation": "fill", "target": {"fields": {"说明": value}}},
        ],
    })

    with pytest.raises(ValueError) as exc:
        load_dsl_document(payload, variables=variables)

    assert f"cases[2].steps[2].target.fields.说明: {message}" in str(exc.value)


def test_load_dsl_document_supports_chinese_variable_names() -> None:
    document = load_dsl_document(
        {
            "suite": {"code": "budget", "name": "预算指标", "tenant": "财政一体化", "default_org": "049002"},
            "cases": [
                {
                    "code": "query-budget",
                    "name": "查询预算指标",
                    "user": "{{账号名}}",
                    "steps": [
                        {
                            "component": "query",
                            "operation": "search",
                            "target": {"conditions": [{"field": "预算指标编码", "equals": "{{预算.指标编码}}"}]},
                        }
                    ],
                }
            ],
        },
        variables={"账号名": "默认用户", "预算": {"指标编码": "3600000001"}},
    )

    assert document.cases[0].user == "默认用户"
    assert document.cases[0].steps[0].target["conditions"][0]["equals"] == "3600000001"


def test_load_dsl_document_keeps_random_tokens_for_executor() -> None:
    document = load_dsl_document(
        {
            "suite": {"code": "budget", "name": "预算指标", "tenant": "财政一体化", "default_org": "049002"},
            "cases": [
                {
                    "code": "create-budget",
                    "name": "新增预算指标",
                    "steps": [
                        {
                            "component": "form",
                            "operation": "fill",
                            "target": {"fields": {"指标名称": "测试指标{{random.suffix}}"}},
                        }
                    ],
                }
            ],
        },
        variables={},
    )

    assert document.cases[0].steps[0].target["fields"]["指标名称"] == "测试指标{{random.suffix}}"


def test_load_dsl_document_rejects_removed_dollar_variable_syntax() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            {
                "suite": {"code": "budget", "name": "预算指标", "tenant": "财政一体化", "default_org": "049002"},
                "cases": [
                    {
                        "code": "query-budget",
                        "name": "查询预算指标",
                        "steps": [
                            {
                                "component": "query",
                                "operation": "search",
                                "target": {"conditions": [{"field": "预算指标编码", "equals": "${budget_code}"}]},
                            }
                        ],
                    }
                ],
            },
            variables={"budget_code": "3600000001"},
        )

    assert "不支持 ${} 变量语法" in str(exc.value)


def test_load_dsl_document_rejects_reserved_random_variable_namespace() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            {"steps": [{"action": "open_menu", "menu_path": "项目管理>>项目立项"}]},
            variables={"random": {"suffix": "fixed"}},
        )

    assert "random 为系统保留变量命名空间" in str(exc.value)


def test_load_dsl_document_wraps_legacy_steps_as_single_case() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document({"steps": [{"action": "open_menu", "menu_path": "项目管理>>项目立项"}]})

    assert "旧式 steps DSL 已废弃" in str(exc.value)


def test_load_dsl_document_rejects_table_assert_row_values_without_fields() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            {
                "suite": {"code": "catalog", "name": "项目目录", "tenant": "财政一体化", "default_org": "049002"},
                "cases": [
                    {
                        "code": "assert-row",
                        "name": "校验行",
                        "steps": [
                            {"action": "open_menu", "menu_path": "项目目录管理"},
                            {
                                "component": "table",
                                "operation": "assert_row_values",
                                "target": {"match": {"column": "支出范围说明", "equals": "xftest1"}},
                            },
                        ],
                    }
                ],
            }
        )

    message = str(exc.value)
    assert "DSL 语法校验失败" in message
    assert "cases[1].steps[2]" in message
    assert "table.assert_row_values 缺少 target.fields" in message


def test_load_dsl_document_accepts_table_value_assertion_table_scope() -> None:
    document = load_dsl_document(
        _suite_payload(
            [
                {
                    "component": "table",
                    "operation": "assert_column_values",
                    "target": {
                        "table": "授权明细",
                        "column": "可授权金额",
                        "equals": "400.00",
                    },
                },
                {
                    "component": "table",
                    "operation": "assert_row_values",
                    "target": {
                        "table_name": "授权明细",
                        "match": {"column": "被授权人名称", "equals": "人员二十二"},
                        "fields": {"可授权金额": "400.00"},
                    },
                },
            ]
        )
    )

    assert document.cases[0].steps[0].target["table"] == "授权明细"
    assert document.cases[0].steps[1].target["table_name"] == "授权明细"


def test_load_dsl_document_accepts_table_assert_columns_absent() -> None:
    document = load_dsl_document(
        {
            "suite": {"code": "columns", "name": "Columns", "tenant": "财政一体化", "default_org": "049002"},
            "cases": [
                {
                    "code": "missing-columns",
                    "name": "不存在列",
                    "steps": [
                        {"action": "open_menu", "menu_path": "预算绩效>>绩效模板>>模板库"},
                        {
                            "component": "table",
                            "operation": "assert_columns",
                            "target": {
                                "table": "三级模板明细",
                                "absent": ["一级绩效指标分值", "二级绩效指标分值"],
                            },
                        },
                    ],
                }
            ],
        }
    )

    step = document.cases[0].steps[1]
    assert step.component == "table"
    assert step.operation == "assert_columns"
    assert step.target == {"table": "三级模板明细", "absent": ["一级绩效指标分值", "二级绩效指标分值"]}


def test_load_dsl_document_accepts_table_assert_columns_present_and_absent() -> None:
    document = load_dsl_document(
        {
            "suite": {"code": "columns", "name": "Columns", "tenant": "财政一体化", "default_org": "049002"},
            "cases": [
                {
                    "code": "columns",
                    "name": "列集合",
                    "steps": [
                        {
                            "component": "table",
                            "operation": "assert_columns",
                            "target": {
                                "name": "三级模板明细",
                                "present": ["一级绩效指标", "二级绩效指标"],
                                "absent": ["一级绩效指标分值"],
                            },
                        }
                    ],
                }
            ],
        }
    )

    assert document.cases[0].steps[0].target["present"] == ["一级绩效指标", "二级绩效指标"]
    assert document.cases[0].steps[0].target["absent"] == ["一级绩效指标分值"]


def test_load_dsl_document_rejects_table_assert_columns_without_present_or_absent() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            {
                "suite": {"code": "columns", "name": "Columns", "tenant": "财政一体化"},
                "cases": [
                    {
                        "code": "bad-columns",
                        "name": "缺少列断言",
                        "steps": [
                            {
                                "component": "table",
                                "operation": "assert_columns",
                                "target": {"table": "三级模板明细"},
                            }
                        ],
                    }
                ],
            }
        )

    message = str(exc.value)
    assert "table.assert_columns" in message
    assert "缺少 target.present 或 target.absent" in message


def test_load_dsl_document_rejects_table_assert_columns_bad_list_format() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            {
                "suite": {"code": "columns", "name": "Columns", "tenant": "财政一体化"},
                "cases": [
                    {
                        "code": "bad-columns",
                        "name": "列格式错误",
                        "steps": [
                            {
                                "component": "table",
                                "operation": "assert_columns",
                                "target": {"present": "一级绩效指标", "absent": []},
                            }
                        ],
                    }
                ],
            }
        )

    message = str(exc.value)
    assert "table.assert_columns" in message
    assert "target.present 格式不对，必须是非空列表" in message
    assert "target.absent 格式不对，必须是非空列表" in message


def test_load_dsl_document_accepts_popup_reference_filter_conditions() -> None:
    document = load_dsl_document(
        _suite_payload(
            [
                {
                    "component": "editable_table",
                    "operation": "fill_row",
                    "target": {
                        "table": "收款人信息",
                        "row_number": 1,
                        "fields": {
                            "收款人全称": {
                                "filter": {
                                    "conditions": [
                                        {"field": "收款人账号", "equals": "666666666"},
                                        {"field": "收款人全称", "equals": "测试收款人"},
                                    ]
                                },
                                "match": {"column": "收款人账号", "equals": "666666666"},
                            }
                        },
                    },
                }
            ]
        )
    )

    value = document.cases[0].steps[0].target["fields"]["收款人全称"]
    assert value["filter"]["conditions"] == [
        {"field": "收款人账号", "equals": "666666666"},
        {"field": "收款人全称", "equals": "测试收款人"},
    ]


def test_load_dsl_document_accepts_popup_reference_list_values() -> None:
    document = load_dsl_document(
        _suite_payload(
            [
                {
                    "component": "form",
                    "operation": "fill",
                    "target": {
                        "fields": {
                            "预算项目": [
                                "360000241010010000008 二级采购项目",
                                "360000241010010000009 三级采购项目",
                            ]
                        }
                    },
                }
            ]
        )
    )

    assert document.cases[0].steps[0].target["fields"]["预算项目"] == [
        "360000241010010000008 二级采购项目",
        "360000241010010000009 三级采购项目",
    ]


def test_load_dsl_document_accepts_form_field_popup_reference_row_number_and_first_available() -> None:
    document = load_dsl_document(
        _suite_payload(
            [
                {
                    "component": "form",
                    "operation": "fill",
                    "target": {
                        "fields": {
                            "支付摘要": {"filter": "自动化测试", "row_number": 1},
                            "收款人全称": {"filter": "自动化测试", "first_available": True},
                        }
                    },
                }
            ]
        )
    )

    fields = document.cases[0].steps[0].target["fields"]
    assert fields["支付摘要"] == {"filter": "自动化测试", "row_number": 1}
    assert fields["收款人全称"] == {"filter": "自动化测试", "first_available": True}


def test_load_dsl_document_rejects_form_field_popup_reference_without_selection_target() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            _suite_payload(
                [
                    {
                        "component": "form",
                        "operation": "fill",
                        "target": {"fields": {"支付摘要": {"filter": "自动化测试"}}},
                    }
                ]
            )
        )

    message = str(exc.value)
    assert "支付摘要" in message
    assert "缺少选择目标" in message


def test_load_dsl_document_rejects_malformed_popup_reference_filter_conditions() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            _suite_payload(
                [
                    {
                        "component": "editable_table",
                        "operation": "fill_row",
                        "target": {
                            "table": "收款人信息",
                            "row_number": 1,
                            "fields": {
                                "收款人全称": {
                                    "filter": {"conditions": [{"field": "收款人账号"}]},
                                    "match": {"column": "收款人账号", "equals": "666666666"},
                                }
                            },
                        },
                    }
                ]
            )
        )

    message = str(exc.value)
    assert "filter.conditions[1]" in message
    assert "field 和 equals" in message


def test_load_dsl_document_rejects_query_search_without_conditions_shape() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            {
                "suite": {"code": "query", "name": "查询", "tenant": "财政一体化", "default_org": "049002"},
                "cases": [
                    {
                        "code": "bad-query",
                        "name": "错误查询写法",
                        "steps": [
                            {
                                "component": "query",
                                "operation": "search",
                                "target": {"项目负责人": "吕晓雷"},
                            }
                        ],
                    }
                ],
            }
        )

    message = str(exc.value)
    assert "DSL 语法校验失败" in message
    assert "cases[1].steps[1]" in message
    assert "query.search target 不支持属性: 项目负责人" in message
    assert "query.search 缺少 target.conditions" in message
    assert "正确写法示例" in message
    assert "conditions" in message
    assert "field: 项目负责人" in message


def test_load_dsl_document_accepts_query_reset_with_empty_target() -> None:
    document = load_dsl_document(
        _suite_payload(
            [
                {
                    "component": "query",
                    "operation": "reset",
                    "target": {},
                }
            ]
        )
    )

    step = document.cases[0].steps[0]
    assert step.component == "query"
    assert step.operation == "reset"
    assert step.target == {}


def test_load_dsl_document_rejects_query_reset_target_properties() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            _suite_payload(
                [
                    {
                        "component": "query",
                        "operation": "reset",
                        "target": {"button": "重置"},
                    }
                ]
            )
        )

    message = str(exc.value)
    assert "query.reset target 不支持属性: button" in message
    assert "operation: reset" in message
    assert "target: {}" in message


def test_load_dsl_document_rejects_query_search_reset_button() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            _suite_payload(
                [
                    {
                        "component": "query",
                        "operation": "search",
                        "target": {"conditions": [], "button": "重置"},
                    }
                ]
            )
        )

    assert "query.search target.button 不支持重置，请使用 query.reset" in str(exc.value)


def test_dsl_schema_documents_query_reset_empty_target() -> None:
    schema = json.loads(Path("schemas/dsl.schema.json").read_text(encoding="utf-8"))
    refs = {
        branch.get("then", {}).get("properties", {}).get("target", {}).get("$ref")
        for branch in schema["$defs"]["step"]["oneOf"][1]["allOf"]
    }

    assert "#/$defs/queryResetTarget" in refs
    assert schema["$defs"]["queryResetTarget"] == {
        "type": "object",
        "additionalProperties": False,
        "maxProperties": 0,
    }


def test_load_dsl_document_rejects_table_row_action_without_row_locator() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            {
                "suite": {"code": "row-action", "name": "行按钮", "tenant": "财政一体化", "default_org": "049002"},
                "cases": [
                    {
                        "code": "bad-row-action",
                        "name": "缺少行定位",
                        "steps": [
                            {
                                "component": "table_row_action",
                                "operation": "click",
                                "target": {"action": "详情"},
                            }
                        ],
                    }
                ],
            }
        )

    message = str(exc.value)
    assert "DSL 语法校验失败" in message
    assert "cases[1].steps[1]" in message
    assert "table_row_action.click 缺少行定位属性" in message
    assert "正确写法示例" in message
    assert "match" in message
    assert "conditions" in message
    assert "column: 项目名称" in message


def test_load_dsl_document_accepts_table_row_action_table_scope() -> None:
    document = load_dsl_document(
        _suite_payload(
            [
                {
                    "component": "table_row_action",
                    "operation": "click",
                    "target": {"action": "选择库存", "table": "物资信息", "row_number": 1},
                },
                {
                    "component": "table_row_action",
                    "operation": "click",
                    "target": {
                        "action": "选择库存",
                        "table_name": "物资信息",
                        "match": {"column": "物资名称", "equals": "复印纸"},
                    },
                },
            ],
            code="row-action",
            name="行按钮",
        )
    )

    assert document.cases[0].steps[0].target == {"action": "选择库存", "table": "物资信息", "row_number": 1}
    assert document.cases[0].steps[1].target["table_name"] == "物资信息"


def test_load_dsl_document_accepts_table_cell_link_click() -> None:
    document = load_dsl_document(
        _suite_payload(
            [
                {
                    "component": "table",
                    "operation": "click_cell_link",
                    "target": {
                        "table": "表格",
                        "match": {"column": "序号", "equals": 1},
                        "column": "任务编码",
                        "link_text": "202600000000060",
                    },
                },
                {
                    "component": "table",
                    "operation": "click_cell_link",
                    "target": {"row_number": 1, "column": "任务编码"},
                },
            ],
            code="cell-link",
            name="单元格链接",
        )
    )

    assert document.cases[0].steps[0].target["column"] == "任务编码"
    assert document.cases[0].steps[0].target["link_text"] == "202600000000060"
    assert document.cases[0].steps[1].target == {"row_number": 1, "column": "任务编码"}


def test_load_dsl_document_rejects_table_cell_link_without_column() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            _suite_payload(
                [
                    {
                        "component": "table",
                        "operation": "click_cell_link",
                        "target": {"match": {"column": "序号", "equals": 1}},
                    }
                ],
                code="cell-link",
                name="单元格链接",
            )
        )

    assert "table.click_cell_link 缺少 target.column" in str(exc.value)


def test_load_dsl_document_rejects_table_cell_link_without_row_locator() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            _suite_payload(
                [
                    {
                        "component": "table",
                        "operation": "click_cell_link",
                        "target": {"column": "任务编码"},
                    }
                ],
                code="cell-link",
                name="单元格链接",
            )
        )

    assert "table.click_cell_link 缺少行定位属性" in str(exc.value)


def test_load_dsl_document_rejects_table_row_action_table_without_row_locator() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            _suite_payload(
                [
                    {
                        "component": "table_row_action",
                        "operation": "click",
                        "target": {"action": "选择库存", "table": "物资信息"},
                    }
                ],
                code="row-action",
                name="行按钮",
            )
        )

    message = str(exc.value)
    assert "table_row_action.click 缺少行定位属性" in message
    assert "target.table" not in message


def test_load_dsl_document_rejects_unsupported_target_properties() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            {
                "suite": {"code": "toolbar", "name": "工具栏", "tenant": "财政一体化", "default_org": "049002"},
                "cases": [
                    {
                        "code": "bad-toolbar",
                        "name": "未知属性",
                        "steps": [
                            {
                                "component": "toolbar",
                                "operation": "click",
                                "target": {"label": "新增", "foo": "bar"},
                            }
                        ],
                    }
                ],
            }
        )

    message = str(exc.value)
    assert "DSL 语法校验失败" in message
    assert "cases[1].steps[1]" in message
    assert "toolbar.click target 不支持属性: foo" in message


def test_load_dsl_document_rejects_unsupported_step_properties_with_path() -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            {
                "suite": {"code": "toolbar", "name": "工具栏", "tenant": "财政一体化", "default_org": "049002"},
                "cases": [
                    {
                        "code": "bad-step",
                        "name": "step 未知属性",
                        "steps": [
                            {
                                "component": "toolbar",
                                "operation": "click",
                                "timeout": 3000,
                                "target": {"label": "新增"},
                            }
                        ],
                    }
                ],
            }
        )

    message = str(exc.value)
    assert "DSL 语法校验失败" in message
    assert "cases[1].steps[1]" in message
    assert "toolbar.click 不支持属性: timeout" in message


def test_all_component_operations_have_strict_schema_and_examples() -> None:
    assert set(COMPONENT_TARGET_SCHEMAS) == VALID_COMPONENT_OPERATIONS
    for component, operation in sorted(VALID_COMPONENT_OPERATIONS):
        schema = COMPONENT_TARGET_SCHEMAS[(component, operation)]
        if (component, operation) != ("query", "reset"):
            assert schema.allowed_keys, f"{component}.{operation} should declare target keys"
        assert "正确写法示例:" in schema.example
        assert f"component: {component}" in schema.example
        assert f"operation: {operation}" in schema.example


@pytest.mark.parametrize("component_operation", sorted(VALID_COMPONENT_OPERATIONS))
def test_all_component_operation_unsupported_target_errors_include_examples(component_operation) -> None:
    component, operation = component_operation
    schema = COMPONENT_TARGET_SCHEMAS[component_operation]

    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            {
                "suite": {"code": "schema", "name": "Schema", "tenant": "财政一体化", "default_org": "049002"},
                "cases": [
                    {
                        "code": "bad-target",
                        "name": "未知 target 属性",
                        "steps": [
                            {
                                "component": component,
                                "operation": operation,
                                "target": {"__unsupported__": True},
                            }
                        ],
                    }
                ],
            }
        )

    message = str(exc.value)
    assert "DSL 语法校验失败" in message
    assert f"{component}.{operation} target 不支持属性: __unsupported__" in message
    assert schema.example in message


@pytest.mark.parametrize(
    ("component_operation", "target"),
    [
        (("action", "click"), {}),
        (("attachment", "upload"), {}),
        (("editable_table", "fill_row"), {}),
        (("form", "assert_values"), {}),
        (("form", "capture_values"), {}),
        (("form", "fill"), {}),
        (("import", "upload"), {}),
        (("notification", "close"), {}),
        (("popup_reference", "select"), {}),
        (("query", "search"), {"conditions": {"field": "项目负责人", "equals": "吕晓雷"}}),
        (("tab", "click"), {}),
        (("table", "assert_columns"), {}),
        (("table", "assert_column_values"), {}),
        (("table", "assert_row_values"), {}),
        (("table_row_action", "click"), {"action": "详情"}),
        (("table_row_selection", "select"), {}),
        (("toolbar", "click"), {}),
        (("transfer_dialog", "select"), {}),
        (("tree", "select"), {}),
    ],
)
def test_required_or_bad_format_component_errors_include_examples(component_operation, target) -> None:
    component, operation = component_operation
    schema = COMPONENT_TARGET_SCHEMAS[component_operation]

    with pytest.raises(ValueError) as exc:
        load_dsl_document(
            {
                "suite": {"code": "schema", "name": "Schema", "tenant": "财政一体化", "default_org": "049002"},
                "cases": [
                    {
                        "code": "bad-required",
                        "name": "缺少必填或格式错误",
                        "steps": [{"component": component, "operation": operation, "target": target}],
                    }
                ],
            }
        )

    message = str(exc.value)
    assert "DSL 语法校验失败" in message
    assert f"{component}.{operation}" in message
    assert schema.example in message


@pytest.mark.parametrize(
    "payload",
    [
        [{"action": "click_button", "target": "保存"}],
        [{"action": "open_row_detail", "tree_node": "001 办公室", "project_code": "1"}],
        [{"action": "fill_field", "field": "项目名称", "value": "AI"}],
    ],
)
def test_load_dsl_rejects_removed_legacy_actions(payload) -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl(payload)

    assert "旧 DSL" in str(exc.value)


@pytest.mark.parametrize(
    "step",
    [
        {
            "component": "query",
            "operation": "search",
            "target": {"conditions": [{"field": "账户状态", "equals": ["草稿", "草稿"]}]},
        },
        {
            "component": "form",
            "operation": "fill",
            "target": {"fields": {"账户状态": ["草稿", "草稿"]}},
        },
        {
            "component": "editable_table",
            "operation": "fill_row",
            "target": {"row_number": 1, "fields": {"账户状态": ["草稿", "草稿"]}},
        },
    ],
)
def test_load_dsl_document_rejects_duplicate_multi_select_values(step) -> None:
    with pytest.raises(ValueError) as exc:
        load_dsl_document(_suite_payload([step]))

    assert "重复值" in str(exc.value)


@pytest.mark.parametrize("value", ["草稿", ["启用", "草稿"], []])
def test_load_dsl_document_accepts_exact_multi_select_assignment_values(value) -> None:
    document = load_dsl_document(
        _suite_payload(
            [
                {
                    "component": "query",
                    "operation": "search",
                    "target": {"conditions": [{"field": "账户状态", "equals": value}]},
                }
            ]
        )
    )

    assert document.cases[0].steps[0].target["conditions"][0]["equals"] == value


def test_popup_reference_discover_is_not_test_dsl():
    with pytest.raises(ValueError):
        load_dsl({'steps': [{'component': 'popup_reference', 'operation': 'discover', 'target': {}}]})
