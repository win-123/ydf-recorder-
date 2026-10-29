import pytest

import ydf_browser.template_parser as template_parser_module
from ydf_browser.adapters import default_render_adapter_registry
from ydf_browser.template_parser import build_page_manifest


def test_build_page_manifest_extracts_regions_fields_and_actions(sample_template_payload: dict) -> None:
    manifest = build_page_manifest(sample_template_payload)

    assert manifest.page.biz_obj_code == "pmProjectInfo"
    assert {region.region_type for region in manifest.regions} >= {
        "page_root",
        "top_action_bar",
        "content_card",
        "main_table",
        "tree",
    }
    assert {field.fieldid for field in manifest.fields} == {"project_name", "project_code"}
    assert {button.label for button in manifest.actions} >= {"保存", "提交", "详情"}
    assert [column.label for column in manifest.table_columns] == ["项目代码", "金额"]
    assert [tree.label for tree in manifest.trees] == ["001 办公室"]


def test_build_page_manifest_rejects_payload_without_root() -> None:
    try:
        build_page_manifest({"data": {"uidata": []}})
    except ValueError as exc:
        assert "uidata" in str(exc)
    else:
        raise AssertionError("expected build_page_manifest to fail when root node is missing")


def test_build_page_manifest_detects_tree_without_fixed_div_code(sample_template_payload: dict) -> None:
    tree_node = sample_template_payload["data"]["uidata"][0]["children"][2]["children"][0]
    tree_node["divCode"] = "custom_tree_region"

    manifest = build_page_manifest(sample_template_payload)

    assert any(region.region_type == "tree" for region in manifest.regions)
    assert [tree.label for tree in manifest.trees] == ["001 办公室"]


def test_build_page_manifest_treats_lcd_form_as_bindable_region(sample_template_payload: dict) -> None:
    sample_template_payload["data"]["uidata"][0]["children"].append(
        {
            "key": "edit_form",
            "divCode": "pmProjectInfo",
            "nodeType": "form",
            "label": "基本信息",
            "name": "LCDPanel",
            "children": [
                {
                    "key": "internal_dep",
                    "divCode": "internalDepCode",
                    "nodeType": "formItem",
                    "label": "项目申报部门",
                    "name": "YDFTreeSelect",
                    "dataField": "internalDepCode",
                    "actions": {"onChange": [{"key": "syncInternalDep"}]},
                },
                {
                    "key": "end_time",
                    "divCode": "proEndTime",
                    "nodeType": "formItem",
                    "label": "项目结束时间",
                    "name": "YDFDatePicker",
                    "dataField": "proEndTime",
                },
            ],
        }
    )

    manifest = build_page_manifest(sample_template_payload)

    assert any(region.fieldid == "pmProjectInfo" and region.region_type == "content_card" for region in manifest.regions)
    assert {field.fieldid for field in manifest.fields} >= {
        "pmProjectInfo_internalDepCode",
        "pmProjectInfo_proEndTime",
    }


def test_build_page_manifest_treats_lcd_query_string_search_box_as_query_region(
    sample_template_payload: dict,
) -> None:
    sample_template_payload["data"]["uidata"][0]["children"].append(
        {
            "key": "search_box",
            "divCode": "seachBox",
            "nodeType": "form",
            "label": "查询区",
            "name": "LCDQueryString",
            "children": [
                {
                    "key": "mode_type_name",
                    "divCode": "modeTypeName",
                    "nodeType": "formItem",
                    "label": "分类名称",
                    "name": "TextInput",
                    "dataField": "modeTypeName",
                }
            ],
        }
    )

    manifest = build_page_manifest(sample_template_payload)

    assert any(region.fieldid == "seachBox" and region.region_type == "query_box" for region in manifest.regions)
    assert [field.fieldid for field in manifest.query_fields] == ["seachBox_modeTypeName"]
    assert "modeTypeName" not in {field.fieldid for field in manifest.fields}


def test_build_page_manifest_adds_rule_based_fieldids_for_common_ydf_components() -> None:
    manifest = build_page_manifest(
        {
            "data": {
                "uidata": [
                    {
                        "key": "root",
                        "divCode": "root",
                        "nodeType": "root",
                        "children": [
                            {
                                "key": "base_form",
                                "divCode": "baseForm",
                                "nodeType": "form",
                                "label": "基本信息",
                                "name": "LCDPanel",
                                "children": [
                                    {
                                        "key": "project_name",
                                        "divCode": "proName",
                                        "nodeType": "formItem",
                                        "label": "项目名称",
                                        "name": "YDFInput",
                                        "dataField": "proName",
                                    },
                                    {
                                        "key": "department",
                                        "divCode": "depart",
                                        "nodeType": "formItem",
                                        "label": "部门",
                                        "name": "YDFTreeModalSelect",
                                        "dataField": "depart",
                                    },
                                ],
                            },
                            {
                                "key": "query",
                                "divCode": "dataQueryArea",
                                "nodeType": "form",
                                "label": "查询区",
                                "name": "LCDQueryString",
                                "children": [
                                    {
                                        "key": "query_department",
                                        "divCode": "depart",
                                        "nodeType": "formItem",
                                        "label": "部门",
                                        "name": "YDFTableModalSelect",
                                        "dataField": "depart",
                                    }
                                ],
                            },
                            {
                                "key": "main_table",
                                "divCode": "userTable",
                                "nodeType": "table",
                                "label": "用户表",
                                "name": "LCDTable",
                                "children": [
                                    {
                                        "key": "code_col",
                                        "divCode": "code",
                                        "nodeType": "column",
                                        "label": "编码",
                                        "name": "YDFInput",
                                        "dataField": "code",
                                    }
                                ],
                            },
                            {
                                "key": "dept_tree",
                                "divCode": "deptTree",
                                "nodeType": "tree",
                                "label": "部门树",
                                "name": "LCDTree",
                            },
                            {
                                "key": "toolbar",
                                "divCode": "btnTools",
                                "nodeType": "toolbar",
                                "label": "按钮",
                                "name": "LCDBtnToolbar",
                                "children": [
                                    {
                                        "key": "save",
                                        "divCode": "btnSave",
                                        "nodeType": "leafItem",
                                        "label": "保存",
                                        "name": "YDFButton",
                                    }
                                ],
                            },
                        ],
                    }
                ]
            }
        }
    )

    project_name = next(field for field in manifest.fields if field.label == "项目名称")
    department = next(field for field in manifest.fields if field.label == "部门")
    query_department = next(field for field in manifest.query_fields if field.label == "部门")
    table = next(region for region in manifest.regions if region.label == "用户表")
    code_column = next(column for column in manifest.table_columns if column.label == "编码")
    tree = next(region for region in manifest.regions if region.label == "部门树")
    save = next(action for action in manifest.actions if action.label == "保存")

    assert "baseForm_proName" in project_name.runtime_fieldids
    assert {"baseForm_depart_input", "baseForm_depart_tree", "baseForm_depart_tree_search", "baseForm_depart_modal_ok"}.issubset(
        set(department.runtime_fieldids)
    )
    assert "baseForm_depart_input_search_input" in department.runtime_fieldids
    assert {"dataQueryArea_depart_input", "dataQueryArea_depart_table"}.issubset(
        set(query_department.runtime_fieldids)
    )
    assert "dataQueryArea_depart_input_search_input" not in query_department.runtime_fieldids
    assert table.runtime_fieldids == ["userTable_table"]
    assert "userTable_table_code" in code_column.runtime_fieldids
    assert "userTable_code" in code_column.runtime_fieldids
    assert "userTable_table_code" not in code_column.verified_runtime_fieldids
    assert "userTable_code" in code_column.verified_runtime_fieldids
    assert {"deptTree_search_input", "deptTree_search_suffix"}.issubset(set(tree.runtime_fieldids))
    assert save.runtime_fieldids == ["btnSave"]


def test_build_page_manifest_uses_uiparser_direct_fieldid_for_nested_widgets() -> None:
    manifest = build_page_manifest(
        {
            "data": {
                "uidata": [
                    {
                        "key": "root",
                        "divCode": "root",
                        "nodeType": "root",
                        "children": [
                            {
                                "key": "panel",
                                "divCode": "panel",
                                "nodeType": "form",
                                "name": "LCDPanel",
                                "children": [
                                    {
                                        "key": "name_key",
                                        "divCode": "name_div",
                                        "fieldid": "name_field",
                                        "nodeType": "formItem",
                                        "name": "YDFInput",
                                        "label": "名称",
                                        "dataField": "name",
                                    }
                                ],
                            },
                            {
                                "key": "leaf",
                                "divCode": "leaf_div",
                                "fieldid": "leaf_field",
                                "parseChild": 0,
                                "nodeType": "formItem",
                                "name": "YDFInput",
                                "label": "叶子",
                                "dataField": "leaf",
                            },
                        ],
                    }
                ]
            }
        }
    )

    fields = {field.label: field for field in manifest.fields}
    assert fields["名称"].fieldid == "name_field"
    assert fields["名称"].verified_runtime_fieldids == ["name_field"]
    assert fields["叶子"].fieldid == "leaf_div"
    assert fields["叶子"].verified_runtime_fieldids == ["leaf_div"]


@pytest.mark.parametrize(
    ("direct_id", "parent_id", "data_field", "component_name"),
    [
        ("setModeInp", "pay_form", "setModeCode", "YDFSelect"),
        ("proCatalogCode", "pmProjectInfo", "proCatalogCode", "YDFTreeSelect"),
        ("mb_form_manafeeExtrCode", "mb_form", "manaFeeExtrCode", "YDFSelect"),
        ("2025042916094932627680310720055", "wdzqxx_pancel", "accountClosingDate", "YDFDatePicker"),
    ],
)
def test_build_page_manifest_prefers_direct_identity_and_adds_component_suffixes(
    direct_id: str, parent_id: str, data_field: str, component_name: str
) -> None:
    manifest = build_page_manifest(
        {
            "data": {
                "uidata": [
                    {
                        "key": "root",
                        "divCode": "root",
                        "nodeType": "root",
                        "children": [
                            {
                                "key": "main_form",
                                "divCode": parent_id,
                                "nodeType": "form",
                                "name": "LCDPanel",
                                "children": [
                                    {
                                        "key": f"{direct_id}_key",
                                        "divCode": direct_id,
                                        "nodeType": "formItem",
                                        "name": component_name,
                                        "label": "目标字段",
                                        "dataField": data_field,
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        }
    )

    assert len(manifest.fields) == 1
    field = manifest.fields[0]
    assert direct_id in field.runtime_fieldids
    assert field.verified_runtime_fieldids == [direct_id]
    expected_suffixes = {f"{direct_id}_input", f"{direct_id}_suffix"}
    if component_name in {"YDFSelect", "YDFTreeSelect"}:
        expected_suffixes.add(f"{direct_id}_search_input")
        expected_suffixes.add(f"{parent_id}_{data_field}_search_input")
    assert expected_suffixes.issubset(set(field.runtime_fieldids))
    assert f"{parent_id}_{data_field}" in field.runtime_fieldids


def test_build_page_manifest_uses_viewpanel_parent_form_datafield_identity() -> None:
    manifest = build_page_manifest(
        {
            "data": {
                "uidata": [
                    {
                        "key": "root",
                        "divCode": "root",
                        "nodeType": "root",
                        "children": [
                            {
                                "key": "base_form",
                                "divCode": "baseForm",
                                "nodeType": "form",
                                "name": "LCDPanel",
                                "children": [
                                    {
                                        "key": "user_name",
                                        "nodeType": "formItem",
                                        "label": "用户名",
                                        "name": "YDFInput",
                                        "dataField": "userName",
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        }
    )

    field = manifest.fields[0]

    assert field.fieldid == "baseForm_userName"
    assert field.runtime_fieldids[0] == "baseForm_userName"
    assert field.verified_runtime_fieldids == []


def test_build_page_manifest_treats_tab_toolbar_as_tab_bar(sample_template_payload: dict) -> None:
    sample_template_payload["data"]["uidata"][0]["children"].insert(
        1,
        {
            "key": "suggest_tabs",
            "divCode": "stepBar",
            "nodeType": "toolbar",
            "label": "步骤条",
            "name": "YDFStepsNext",
            "props": {"type": "tab"},
            "children": [
                {
                    "key": "tab_build",
                    "divCode": "stepBuild",
                    "nodeType": "leafItem",
                    "label": "项目建设",
                    "name": "YDFStepNext",
                },
                {
                    "key": "tab_wait_submit",
                    "divCode": "stepWaitSubmit",
                    "nodeType": "leafItem",
                    "label": "待提交",
                    "name": "YDFStepNext",
                },
            ],
        },
    )

    manifest = build_page_manifest(sample_template_payload)

    assert any(region.fieldid == "stepBar" and region.region_type == "tab_bar" for region in manifest.regions)
    assert [tab.label for tab in manifest.tabs] == ["项目建设", "待提交"]
    assert "待提交" not in {action.label for action in manifest.actions}


def test_build_page_manifest_treats_capsule_step_toolbar_as_tab_bar(sample_template_payload: dict) -> None:
    sample_template_payload["data"]["uidata"][0]["children"].insert(
        1,
        {
            "key": "contract_status_tabs",
            "divCode": "tabBar",
            "nodeType": "toolbar",
            "label": "步骤条",
            "name": "YDFStepsNext",
            "type": "capsule",
            "props": {"limitNum": 9},
            "children": [
                {
                    "key": "tab_draft",
                    "divCode": "tabZC",
                    "nodeType": "leafItem",
                    "label": "草稿",
                    "name": "YDFStepNext",
                    "value": "tabZC",
                },
                {
                    "key": "tab_wait_submit",
                    "divCode": "tabDTJ",
                    "nodeType": "leafItem",
                    "label": "待提交",
                    "name": "YDFStepNext",
                    "value": "tabDTJ",
                },
                {
                    "key": "tab_submitted",
                    "divCode": "tabYTJ",
                    "nodeType": "leafItem",
                    "label": "已提交",
                    "name": "YDFStepNext",
                    "value": "tabYTJ",
                },
                {
                    "key": "tab_auditing",
                    "divCode": "tabSHZ",
                    "nodeType": "leafItem",
                    "label": "审核中",
                    "name": "YDFStepNext",
                    "value": "tabSHZ",
                },
                {
                    "key": "tab_final",
                    "divCode": "tabYZS",
                    "nodeType": "leafItem",
                    "label": "已终审",
                    "name": "YDFStepNext",
                    "value": "tabYZS",
                },
                {
                    "key": "tab_recorded",
                    "divCode": "tabYBA",
                    "nodeType": "leafItem",
                    "label": "已备案",
                    "name": "YDFStepNext",
                    "value": "tabYBA",
                },
                {
                    "key": "tab_all",
                    "divCode": "tabALL",
                    "nodeType": "leafItem",
                    "label": "全部",
                    "name": "YDFStepNext",
                    "value": "tabALL",
                },
            ],
        },
    )

    manifest = build_page_manifest(sample_template_payload)

    assert any(region.fieldid == "tabBar" and region.region_type == "tab_bar" for region in manifest.regions)
    assert [tab.label for tab in manifest.tabs] == ["草稿", "待提交", "已提交", "审核中", "已终审", "已备案", "全部"]
    assert [tab.fieldid for tab in manifest.tabs] == ["tabZC", "tabDTJ", "tabYTJ", "tabSHZ", "tabYZS", "tabYBA", "tabALL"]
    assert "草稿" not in {action.label for action in manifest.actions}


def test_build_page_manifest_treats_dropdown_button_without_actions_as_toolbar_action(
    sample_template_payload: dict,
) -> None:
    sample_template_payload["data"]["uidata"][0]["children"][0]["children"].append(
        {
            "key": "add_dropdown",
            "divCode": "add_dropdown",
            "nodeType": "leafItem",
            "label": "新增",
            "name": "YDFDropdownButton",
        }
    )

    manifest = build_page_manifest(sample_template_payload)

    assert any(action.label == "新增" and action.component_name == "YDFDropdownButton" for action in manifest.actions)
    assert all(field.label != "新增" for field in manifest.fields)


def test_build_page_manifest_treats_plain_button_toolbar_as_top_action_bar(
    sample_template_payload: dict,
) -> None:
    toolbar = sample_template_payload["data"]["uidata"][0]["children"][0]
    toolbar["label"] = "按钮"
    toolbar["divCode"] = "btn-tools"
    toolbar["children"] = [
        {
            "key": "add_dropdown",
            "divCode": "btn-dropdown",
            "nodeType": "leafItem",
            "label": "新增",
            "name": "YDFDropdownButton",
            "hide": 0,
        }
    ]
    sample_template_payload["data"]["actionEL"] = {}

    manifest = build_page_manifest(sample_template_payload)

    assert any(region.fieldid == "btn-tools" and region.region_type == "top_action_bar" for region in manifest.regions)
    assert any(
        action.label == "新增" and action.fieldid == "btn-dropdown" and action.component_name == "YDFDropdownButton"
        for action in manifest.actions
    )
    assert all(field.fieldid != "btn-dropdown" for field in manifest.fields)


def test_build_page_manifest_treats_plain_toolbar_leaf_as_toolbar_action(
    sample_template_payload: dict,
) -> None:
    sample_template_payload["data"]["uidata"][0]["children"][0]["children"].append(
        {
            "key": "training_plan_add",
            "divCode": "plan_detail_add",
            "nodeType": "leafItem",
            "label": "新增",
            "name": "YDFButton",
        }
    )

    manifest = build_page_manifest(sample_template_payload)

    assert any(action.label == "新增" and action.fieldid == "plan_detail_add" for action in manifest.actions)
    assert all(field.fieldid != "plan_detail_add" for field in manifest.fields)


def test_build_page_manifest_treats_lcd_bottom_toolbar_leaf_as_toolbar_action(
    sample_template_payload: dict,
) -> None:
    sample_template_payload["data"]["actionEL"] = {}
    sample_template_payload["data"]["uidata"][0]["children"] = [
        {
            "key": "lcdPanel",
            "divCode": "lcdPanel",
            "nodeType": "form",
            "label": "表单面板",
            "name": "LCDPanel",
            "children": [
                {
                    "key": "asset_type_code",
                    "divCode": "lcdPanel_eleCode",
                    "nodeType": "formItem",
                    "label": "物资分类编码",
                    "name": "YDFInput",
                    "dataField": "eleCode",
                }
            ],
        },
        {
            "key": "lcdBtnToolbarOfPage",
            "divCode": "lcdBtnToolbarOfPage",
            "nodeType": "toolbar",
            "label": "底部工具栏",
            "name": "LCDBtnToolbar",
            "parentKey": "root",
            "children": [
                {
                    "key": "btnSave",
                    "divCode": "btnSave",
                    "nodeType": "leafItem",
                    "label": "保存",
                    "name": "YDFButton",
                    "actions": {"onClick": [{"key": "ammTypeConfirm", "label": "确定"}]},
                }
            ],
        },
    ]

    manifest = build_page_manifest(sample_template_payload)

    assert any(
        region.fieldid == "lcdBtnToolbarOfPage" and region.region_type == "top_action_bar"
        for region in manifest.regions
    )
    assert any(action.label == "保存" and action.fieldid == "btnSave" for action in manifest.actions)
    assert all(field.fieldid != "btnSave" for field in manifest.fields)


def test_build_page_manifest_exposes_code_triggered_toolbar_action_alias(
    sample_template_payload: dict,
) -> None:
    sample_template_payload["data"]["uidata"][0]["children"][0]["children"].append(
        {
            "key": "setting_button",
            "divCode": "btnSetting",
            "nodeType": "leafItem",
            "label": "配置",
            "name": "YDFButton",
            "actions": {
                "onClick": [
                    {
                        "divCode": "setTypeData",
                        "key": "setTypeData",
                        "label": "设置支付任务类型",
                        "title": "设置支付任务类型",
                    }
                ]
            },
        }
    )

    manifest = build_page_manifest(sample_template_payload)

    action = next(item for item in manifest.actions if item.fieldid == "btnSetting")
    assert action.label == "配置"
    assert {"setTypeData", "设置支付任务类型"} <= set(action.action_keys)
    assert "设置支付任务类型" in action.aliases()


def test_build_page_manifest_treats_table_form_items_as_table_columns(sample_template_payload: dict) -> None:
    table_node = sample_template_payload["data"]["uidata"][0]["children"][3]
    table_node["children"] = [
        {
            "key": "pay_type_code",
            "divCode": "pay_type_code",
            "nodeType": "column",
            "label": "支付任务类型代码",
            "name": "YDFInput",
            "dataField": "payTypeCode",
        },
        {
            "key": "pay_type_name",
            "divCode": "pay_type_name",
            "nodeType": "formItem",
            "label": "支付任务类型名称",
            "name": "YDFInput",
            "dataField": "payTypeName",
        },
    ]

    manifest = build_page_manifest(sample_template_payload)

    assert [column.label for column in manifest.table_columns] == ["支付任务类型代码", "支付任务类型名称"]
    assert "支付任务类型名称" not in {field.label for field in manifest.fields}


def test_build_page_manifest_keeps_table_column_group_path(sample_template_payload: dict) -> None:
    table_node = sample_template_payload["data"]["uidata"][0]["children"][3]
    table_node["children"] = [
        {
            "key": "self_eval_group",
            "divCode": "self_eval_group",
            "nodeType": "column",
            "label": "全年执行自评金额",
            "name": "LCDColumnGroup",
            "children": [
                {
                    "key": "self_current",
                    "divCode": "self_current",
                    "nodeType": "column",
                    "label": "当年财政拨款(万元)",
                    "name": "YDFInputNumber",
                    "dataField": "currentAppropriation",
                }
            ],
        },
        {
            "key": "final_group",
            "divCode": "final_group",
            "nodeType": "column",
            "label": "全年执行决算金额",
            "name": "LCDColumnGroup",
            "children": [
                {
                    "key": "final_current",
                    "divCode": "final_current",
                    "nodeType": "column",
                    "label": "当年财政拨款(万元)",
                    "name": "YDFInputNumber",
                    "dataField": "finalCurrentAppropriation",
                }
            ],
        },
    ]

    manifest = build_page_manifest(sample_template_payload)

    leaf_columns = [column for column in manifest.table_columns if column.label == "当年财政拨款(万元)"]
    assert [column.data_field for column in leaf_columns] == ["currentAppropriation", "finalCurrentAppropriation"]
    assert [column.column_groups for column in leaf_columns] == [["全年执行自评金额"], ["全年执行决算金额"]]


def test_build_page_manifest_derives_flat_table_column_group_from_display_name(
    sample_template_payload: dict,
) -> None:
    table = sample_template_payload["data"]["uidata"][0]["children"][3]
    table["children"] = [
        {
            "key": "final_current",
            "divCode": "final_current",
            "nodeType": "formItem",
            "label": "全年执行决算金额-当年财政拨款",
            "title": "全年执行决算金额-当年财政拨款",
            "displayName": "全年执行决算金额（万元）.当年财政拨款",
            "name": "YDFInputNumber",
            "dataField": "currentAppropriationPostSync",
        }
    ]

    manifest = build_page_manifest(sample_template_payload)

    column = next(column for column in manifest.table_columns if column.data_field == "currentAppropriationPostSync")
    assert column.label == "当年财政拨款"
    assert column.title == "当年财政拨款"
    assert column.column_groups == ["全年执行决算金额"]


def test_build_page_manifest_treats_form_tabs_as_tab_bar(sample_template_payload: dict) -> None:
    sample_template_payload["data"]["uidata"][0]["children"].insert(
        1,
        {
            "key": "edit_tabs",
            "divCode": "editTabs",
            "nodeType": "container",
            "label": "新增页页签",
            "name": "YDFTabs",
            "children": [
                {
                    "key": "suggest_tab",
                    "divCode": "suggestTab",
                    "nodeType": "tabPane",
                    "label": "项目建议",
                    "name": "YDFTabPane",
                },
                {
                    "key": "detail_tab",
                    "divCode": "detailTab",
                    "nodeType": "tabPane",
                    "label": "支出明细",
                    "name": "YDFTabPane",
                },
                {
                    "key": "attach_tab",
                    "divCode": "attachTab",
                    "nodeType": "tabPane",
                    "label": "附件信息",
                    "name": "YDFTabPane",
                },
            ],
        },
    )

    manifest = build_page_manifest(sample_template_payload)

    assert any(region.fieldid == "editTabs" and region.region_type == "tab_bar" for region in manifest.regions)
    assert [tab.label for tab in manifest.tabs] == ["项目建议", "支出明细", "附件信息"]
    assert "支出明细" not in {action.label for action in manifest.actions}


def test_build_page_manifest_treats_lcd_tabs_child_cards_as_tab_actions(sample_template_payload: dict) -> None:
    sample_template_payload["data"]["uidata"][0]["children"].insert(
        1,
        {
            "key": "edit_tabs",
            "divCode": "dyq_tabs",
            "nodeType": "tabs",
            "label": "多页签",
            "name": "LCDTabs",
            "children": [
                {
                    "key": "suggest_card",
                    "divCode": "xmjy_card",
                    "nodeType": "card",
                    "label": "项目建议",
                    "name": "LCDCard",
                },
                {
                    "key": "detail_card",
                    "divCode": "zcmx_card",
                    "nodeType": "card",
                    "label": "支出明细",
                    "name": "LCDCard",
                },
                {
                    "key": "attach_card",
                    "divCode": "tab-pmBillAttachment",
                    "nodeType": "card",
                    "label": "附件信息",
                    "name": "LCDCard",
                },
            ],
        },
    )

    manifest = build_page_manifest(sample_template_payload)

    assert [tab.label for tab in manifest.tabs] == ["项目建议", "支出明细", "附件信息"]
    assert [tab.fieldid for tab in manifest.tabs] == ["xmjy_card_tab", "zcmx_card_tab", "tab-pmBillAttachment_tab"]


def test_build_page_manifest_derives_property_uri_from_entity_and_data_field(sample_template_payload: dict) -> None:
    root = sample_template_payload["data"]["uidata"][0]
    root["enty"] = {"info": {"uri": "PM.PM.pmProjectInfo"}}

    manifest = build_page_manifest(sample_template_payload)

    project_name = next(field for field in manifest.fields if field.fieldid == "project_name")
    assert project_name.entity_uri == "PM.PM.pmProjectInfo"
    assert project_name.property_uri == "PM.PM.pmProjectInfo.projectName"


def test_build_page_manifest_uses_render_adapter_registry_for_region_classification(
    sample_template_payload: dict,
    monkeypatch,
) -> None:
    sample_template_payload["data"]["uidata"][0]["children"].append(
        {
            "key": "adapter_query",
            "divCode": "adapterQuery",
            "nodeType": "form",
            "label": "适配器查询区",
            "children": [
                {
                    "key": "adapter_query_name",
                    "divCode": "adapterQueryName",
                    "nodeType": "formItem",
                    "label": "适配器字段",
                    "name": "TextInput",
                    "dataField": "adapterQueryName",
                }
            ],
        }
    )
    base_registry = default_render_adapter_registry()

    class Registry:
        def classify_region(self, node):
            if node.get("divCode") == "adapterQuery":
                return "query_box"
            return base_registry.classify_region(node)

    monkeypatch.setattr(template_parser_module, "RENDER_ADAPTERS", Registry())

    manifest = build_page_manifest(sample_template_payload)

    assert any(region.fieldid == "adapterQuery" and region.region_type == "query_box" for region in manifest.regions)
    assert any(field.fieldid == "adapterQuery_adapterQueryName" for field in manifest.query_fields)
