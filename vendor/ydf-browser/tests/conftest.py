from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def sample_template_payload() -> dict:
    return {
        "appCode": "PM",
        "domainKey": "yondif-bm-be",
        "data": {
            "bizObjCode": "pmProjectInfo",
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
                            "children": [
                                {
                                    "key": "save_btn",
                                    "divCode": "btn_save",
                                    "nodeType": "leafItem",
                                    "label": "保存",
                                    "name": "Button",
                                    "rightflag": "save",
                                },
                                {
                                    "key": "submit_btn",
                                    "divCode": "btn_submit",
                                    "nodeType": "leafItem",
                                    "label": "提交",
                                    "name": "Button",
                                    "rightflag": "submit",
                                },
                            ],
                        },
                        {
                            "key": "card_base",
                            "divCode": "card_base",
                            "nodeType": "card",
                            "label": "基本信息",
                            "children": [
                                {
                                    "key": "project_name",
                                    "divCode": "project_name",
                                    "nodeType": "formItem",
                                    "label": "项目名称",
                                    "name": "TextInput",
                                    "dataField": "projectName",
                                },
                                {
                                    "key": "project_code",
                                    "divCode": "project_code",
                                    "nodeType": "formItem",
                                    "label": "项目编码",
                                    "name": "TextInput",
                                    "dataField": "projectCode",
                                },
                            ],
                        },
                        {
                            "key": "org_tree_card",
                            "divCode": "org_tree_card",
                            "nodeType": "card",
                            "label": "组织树区域",
                            "children": [
                                {
                                    "key": "org_tree",
                                    "divCode": "topTree",
                                    "nodeType": "tree",
                                    "label": "内部机构",
                                    "name": "LCDTree",
                                    "children": [
                                        {
                                            "key": "org_tree_node_001",
                                            "divCode": "org_tree_node_001",
                                            "nodeType": "leafItem",
                                            "label": "001 办公室",
                                            "name": "TreeNode",
                                        }
                                    ],
                                }
                            ],
                        },
                        {
                            "key": "main_table",
                            "divCode": "main_table",
                            "nodeType": "table",
                            "label": "明细表",
                            "children": [
                                {
                                    "key": "project_code_col",
                                    "divCode": "project_code_col",
                                    "nodeType": "column",
                                    "label": "项目代码",
                                    "name": "TableColumn",
                                    "dataField": "projectCode",
                                },
                                {
                                    "key": "amount_col",
                                    "divCode": "amount_col",
                                    "nodeType": "column",
                                    "label": "金额",
                                    "name": "TableColumn",
                                    "dataField": "amount",
                                }
                            ],
                        },
                    ],
                }
            ],
            "actionEL": {
                "save": {
                    "key": "save_btn",
                    "divCode": "btn_save",
                    "nodeType": "leafItem",
                    "label": "保存",
                    "name": "Button",
                    "rightflag": "save",
                    "parentKeys": ["root", "toolbar_root"],
                },
                "detail": {
                    "key": "detail_btn",
                    "divCode": "xq_btn",
                    "nodeType": "leafItem",
                    "label": "详情",
                    "name": "Button",
                    "rightflag": "detail",
                    "parentKeys": ["root", "main_table"],
                },
            },
        },
    }


@pytest.fixture
def sample_runtime_elements() -> list[dict]:
    return [
        {
            "fieldid": "project_name",
            "id": "project_name_input",
            "text": "项目名称",
            "role": "textbox",
            "tag_name": "input",
            "visible": True,
            "selector": '[fieldid="project_name"] input',
        },
        {
            "fieldid": "project_code",
            "id": "project_code_input",
            "text": "项目编码",
            "role": "textbox",
            "tag_name": "input",
            "visible": True,
            "selector": '[fieldid="project_code"] input',
        },
        {
            "fieldid": "btn_save",
            "id": "save_button",
            "text": "保存",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="btn_save"]',
        },
        {
            "fieldid": "btn_submit",
            "id": "submit_button",
            "text": "提交",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="btn_submit"]',
        },
        {
            "fieldid": "project_code_col",
            "id": None,
            "text": "项目代码",
            "role": None,
            "tag_name": "th",
            "visible": True,
            "selector": '[fieldid="project_code_col"]',
        },
    ]


@pytest.fixture
def sample_dsl_path(tmp_path: Path) -> Path:
    payload = {
        "suite": {
            "code": "sample",
            "name": "样例测试集",
            "tenant": "财政一体化",
            "default_org": "049002",
        },
        "cases": [
            {
                "code": "sample-case",
                "name": "样例用例",
                "user": "默认用户",
                "steps": [
                    {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
                    {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
                ],
            }
        ],
    }
    target = tmp_path / "workflow.json"
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return target
