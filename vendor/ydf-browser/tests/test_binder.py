from ydf_browser.binder import bind_manifest, bind_runtime_form_field, bind_runtime_readable_form_field
from ydf_browser.models import ElementCandidate, PageManifest, PageMeta
from ydf_browser.template_parser import build_page_manifest


def test_bind_manifest_prefers_fieldid_matches(sample_template_payload: dict, sample_runtime_elements: list[dict]) -> None:
    manifest = build_page_manifest(sample_template_payload)
    for item in sample_runtime_elements:
        if item.get("fieldid") in {"project_name", "project_code"}:
            item["pointer_receivable"] = True

    binding = bind_manifest(manifest, sample_runtime_elements)

    project_name = binding.fields_by_key["project_name"]
    save_button = binding.actions_by_label["保存"]

    assert project_name.runtime.fieldid == "project_name"
    assert project_name.confidence == 1.0
    assert save_button.runtime.selector == '[fieldid="btn_save"]'


def test_bind_manifest_prefers_rule_based_fieldid_over_label_text() -> None:
    manifest = PageManifest(
        page=PageMeta(fieldid="root", biz_obj_code="pmProjectInfo", app_code=None, domain_key=None),
        fields=[
            ElementCandidate(
                key="pro_name",
                fieldid="proName",
                label="项目名称",
                title="",
                region_key="baseForm",
                region_fieldid="baseForm",
                element_type="formItem",
                component_name="YDFInput",
                data_field="proName",
                runtime_fieldids=["baseForm_proName"],
            )
        ],
    )
    runtime_elements = [
        {
            "fieldid": "unrelated",
            "label_text": "项目名称",
            "role": "textbox",
            "tag_name": "input",
            "visible": True,
            "editable": True,
            "selector": '[fieldid="unrelated"]',
        },
        {
            "fieldid": "baseForm_proName",
            "label_text": "",
            "role": "textbox",
            "tag_name": "input",
            "visible": True,
            "editable": True,
            "selector": '[fieldid="baseForm_proName"]',
        },
    ]

    binding = bind_manifest(manifest, runtime_elements)

    bound = binding.fields_by_key["pro_name"]
    assert bound.runtime.fieldid == "baseForm_proName"
    assert bound.confidence == 0.99
    assert "runtime_fieldid" in bound.reasons


def test_bind_manifest_reports_verified_form_contract_path_for_direct_identity() -> None:
    manifest = PageManifest(
        page=PageMeta(fieldid="root", biz_obj_code="pmProjectInfo", app_code=None, domain_key=None),
        fields=[
            ElementCandidate(
                key="pro_name",
                fieldid="proName",
                label="项目名称",
                title="",
                region_key="baseForm",
                region_fieldid="baseForm",
                element_type="formItem",
                component_name="YDFInput",
                data_field="proName",
                verified_runtime_fieldids=["proName"],
            )
        ],
    )

    binding = bind_manifest(
        manifest,
        [{
            "fieldid": "proName",
            "role": "textbox",
            "tag_name": "input",
            "visible": True,
            "editable": True,
            "pointer_receivable": True,
            "selector": '[fieldid="proName"]',
        }],
    )

    assert binding.fields_by_key["pro_name"].contract_path == {
        "contract_version": "1.0.1",
        "applicability": "verified",
        "rule_ids": ["PRS-FORM-001"],
        "fallback_reason": None,
    }


def test_bind_manifest_collapses_same_field_root_and_descendant_control() -> None:
    manifest = PageManifest(
        page=PageMeta(fieldid="root", biz_obj_code="pmProjectInfo", app_code=None, domain_key=None),
        fields=[
            ElementCandidate(
                key="pro_name",
                fieldid="proName",
                label="项目名称",
                title="",
                region_key="baseForm",
                region_fieldid="baseForm",
                element_type="formItem",
                component_name="YDFInput",
                data_field="proName",
                runtime_fieldids=["baseForm_proName"],
                verified_runtime_fieldids=["proName"],
            )
        ],
    )

    binding = bind_manifest(
        manifest,
        [
            {
                "fieldid": "proName",
                "tag_name": "div",
                "visible": True,
                "editable": True,
                "pointer_receivable": True,
                "selector": '[uikey="proName"]',
                "identity_root": "0:7",
            },
            {
                "fieldid": "proName",
                "tag_name": "label",
                "visible": True,
                "editable": True,
                "pointer_receivable": True,
                "selector": '[uikey="proName"]',
                "identity_root": "0:7",
            },
            {
                "fieldid": "baseForm_proName",
                "tag_name": "input",
                "role": "textbox",
                "visible": True,
                "editable": True,
                "pointer_receivable": True,
                "selector": '[fieldid="baseForm_proName"]',
                "identity_root": "0:7",
            },
            {
                "fieldid": "baseForm_proName",
                "tag_name": "input",
                "role": "textbox",
                "visible": True,
                "editable": True,
                "pointer_receivable": True,
                "selector": '[data-ydf-browser-runtime-id="unrelated-input"]',
                "identity_root": "0:8",
            },
        ],
    )

    assert binding.fields_by_key["pro_name"].runtime.tag_name == "input"
    assert binding.fields_by_key["pro_name"].runtime.fieldid == "baseForm_proName"
    assert binding.fields_by_key["pro_name"].contract_path["applicability"] == "verified"
    assert binding.incompatible_fields == {}

    ambiguous = bind_manifest(
        manifest,
        [
            {
                "fieldid": "proName",
                "tag_name": "div",
                "visible": True,
                "editable": True,
                "pointer_receivable": True,
                "selector": '[uikey="proName"]',
                "identity_root": "0:7",
            },
            {
                "fieldid": "proName",
                "tag_name": "label",
                "visible": True,
                "editable": True,
                "pointer_receivable": True,
                "selector": '[uikey="proName"]',
                "identity_root": "0:7",
            },
            {
                "fieldid": "baseForm_proName",
                "tag_name": "input",
                "role": "textbox",
                "visible": True,
                "editable": True,
                "pointer_receivable": True,
                "selector": '[data-ydf-browser-runtime-id="input-1"]',
                "identity_root": "0:7",
            },
            {
                "fieldid": "baseForm_proName",
                "tag_name": "input",
                "role": "textbox",
                "visible": True,
                "editable": True,
                "pointer_receivable": True,
                "selector": '[data-ydf-browser-runtime-id="input-2"]',
                "identity_root": "0:7",
            },
        ],
    )

    assert "pro_name" not in ambiguous.fields_by_key
    assert ambiguous.incompatible_fields["pro_name"]["applicability"] == "incompatible"


def test_bind_manifest_collapses_ydf_switch_wrappers_to_unique_button() -> None:
    manifest = PageManifest(
        page=PageMeta(fieldid="root", biz_obj_code="pmPurchasePlan", app_code=None, domain_key=None),
        fields=[
            ElementCandidate(
                key="is_use_est",
                fieldid="isUseEst",
                label="使用虚拟预算",
                title="",
                region_key="baseForm",
                region_fieldid="baseForm",
                element_type="formItem",
                component_name="YDFSwitch",
                data_field="isUseEst",
                verified_runtime_fieldids=["isUseEst"],
            )
        ],
    )
    wrappers = [
        {
            "fieldid": "isUseEst",
            "tag_name": tag_name,
            "visible": True,
            "editable": True,
            "pointer_receivable": True,
            "identity_root": "0:28",
        }
        for tag_name in ("div", "label", "div")
    ]
    switch_button = {
        "fieldid": "isUseEst",
        "tag_name": "button",
        "visible": True,
        "editable": True,
        "pointer_receivable": True,
        "identity_root": "0:28",
        "selector": '[data-ydf-browser-runtime-id="switch-button"]',
    }

    binding = bind_manifest(manifest, [*wrappers, switch_button])

    bound = binding.fields_by_key["is_use_est"]
    assert bound.runtime.tag_name == "button"
    assert bound.contract_path["applicability"] == "verified"

    ambiguous = bind_manifest(
        manifest,
        [
            *wrappers,
            switch_button,
            {
                **switch_button,
                "selector": '[data-ydf-browser-runtime-id="other-switch-button"]',
            },
        ],
    )

    assert "is_use_est" not in ambiguous.fields_by_key
    assert ambiguous.incompatible_fields["is_use_est"]["applicability"] == "incompatible"


def test_bind_manifest_collapses_modal_reference_wrappers_to_unique_button() -> None:
    manifest = PageManifest(
        page=PageMeta(fieldid="root", biz_obj_code="pmPurchasePlan", app_code=None, domain_key=None),
        fields=[
            ElementCandidate(
                key="pur_item",
                fieldid="purItemDirect",
                label="采购品目",
                title="",
                region_key="detailForm",
                region_fieldid="detailForm",
                element_type="formItem",
                component_name="YDFTableModalSelect",
                data_field="purItemCode",
                verified_runtime_fieldids=["purItemDirect"],
            )
        ],
    )
    wrappers = [
        {
            "fieldid": "purItemDirect",
            "tag_name": tag_name,
            "visible": True,
            "editable": True,
            "pointer_receivable": True,
            "identity_root": "0:40",
        }
        for tag_name in ("div", "label", "div")
    ]
    modal_button = {
        "fieldid": "purItemDirect",
        "tag_name": "button",
        "visible": True,
        "disabled": False,
        "editable": False,
        "pointer_receivable": True,
        "identity_root": "0:40",
        "selector": '[data-ydf-browser-runtime-id="modal-button"]',
    }

    binding = bind_manifest(manifest, [*wrappers, modal_button])

    bound = binding.fields_by_key["pur_item"]
    assert bound.runtime.tag_name == "button"
    assert bound.contract_path["applicability"] == "verified"

    ambiguous = bind_manifest(
        manifest,
        [
            *wrappers,
            modal_button,
            {
                **modal_button,
                "selector": '[data-ydf-browser-runtime-id="other-modal-button"]',
            },
        ],
    )

    assert "pur_item" not in ambiguous.fields_by_key
    assert ambiguous.incompatible_fields["pur_item"]["applicability"] == "incompatible"


def test_bind_manifest_collapses_ydf_select_wrapper_to_search_input() -> None:
    manifest = build_page_manifest(
        {
            "data": {
                "uidata": [{
                    "key": "root",
                    "divCode": "root",
                    "nodeType": "root",
                    "children": [{
                        "key": "main_form",
                        "divCode": "mainForm",
                        "nodeType": "form",
                        "name": "LCDPanel",
                        "children": [{
                            "key": "role_key",
                            "divCode": "roleDirect",
                            "nodeType": "formItem",
                            "name": "YDFSelect",
                            "label": "往来对象角色",
                            "dataField": "role",
                        }],
                    }],
                }]
            }
        }
    )
    binding = bind_manifest(
        manifest,
        [
            {
                "fieldid": "roleDirect",
                "tag_name": "div",
                "visible": True,
                "editable": True,
                "pointer_receivable": True,
                "identity_root": "0:7",
                "selector": '[uikey="roleDirect"]',
            },
            {
                "fieldid": "mainForm_role",
                "tag_name": "div",
                "visible": True,
                "editable": True,
                "pointer_receivable": True,
                "identity_root": "0:7",
                "selector": '[fieldid="mainForm_role"]',
            },
            {
                "fieldid": "mainForm_role_search_input",
                "tag_name": "input",
                "role": "combobox",
                "visible": True,
                "editable": True,
                "pointer_receivable": True,
                "identity_root": "0:7",
                "selector": '[fieldid="mainForm_role_search_input"]',
            },
        ],
    )

    bound = binding.fields_by_key["role_key"]
    assert bound.runtime.fieldid == "mainForm_role_search_input"
    assert bound.contract_path["applicability"] == "verified"

    ambiguous = bind_manifest(
        manifest,
        [
            {
                "fieldid": "roleDirect",
                "tag_name": "div",
                "visible": True,
                "editable": True,
                "pointer_receivable": True,
                "identity_root": "0:7",
            },
            *[
                {
                    "fieldid": "mainForm_role_search_input",
                    "tag_name": "input",
                    "role": "combobox",
                    "visible": True,
                    "editable": True,
                    "pointer_receivable": True,
                    "identity_root": "0:7",
                    "selector": f'[data-ydf-browser-runtime-id="input-{index}"]',
                }
                for index in (1, 2)
            ],
        ],
    )

    assert "role_key" not in ambiguous.fields_by_key
    assert ambiguous.incompatible_fields["role_key"]["applicability"] == "incompatible"


def test_bind_manifest_collapses_direct_identity_select_root_to_unique_search_input() -> None:
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
                                "key": "pay_form",
                                "divCode": "pay_form",
                                "nodeType": "form",
                                "name": "LCDPanel",
                                "children": [
                                    {
                                        "key": "set_mode_key",
                                        "divCode": "setModeInp",
                                        "nodeType": "formItem",
                                        "name": "YDFSelect",
                                        "label": "结算方式",
                                        "dataField": "setModeCode",
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        }
    )

    def search_input(**overrides: object) -> dict:
        item = {
            "fieldid": "setModeInp_search_input",
            "tag_name": "input",
            "role": "combobox",
            "visible": True,
            "editable": True,
            "pointer_receivable": True,
            "identity_root": "0:7",
        }
        item.update(overrides)
        return item

    wrappers = [
        {
            "fieldid": "setModeInp",
            "tag_name": tag_name,
            "visible": True,
            "editable": True,
            "pointer_receivable": True,
            "identity_root": "0:7",
        }
        for tag_name in ("div", "label")
    ]

    unique = bind_manifest(manifest, [*wrappers, search_input()])
    assert unique.fields_by_key["set_mode_key"].runtime.fieldid == "setModeInp_search_input"
    assert unique.fields_by_key["set_mode_key"].contract_path["applicability"] == "verified"
    assert unique.incompatible_fields == {}

    ambiguous = bind_manifest(
        manifest,
        [
            *wrappers,
            search_input(selector='[data-ydf-browser-runtime-id="search-input-1"]'),
            search_input(selector='[data-ydf-browser-runtime-id="search-input-2"]'),
        ],
    )
    assert "set_mode_key" not in ambiguous.fields_by_key
    assert ambiguous.incompatible_fields["set_mode_key"]["applicability"] == "incompatible"

    for attribute, value in (("visible", False), ("disabled", True), ("pointer_receivable", False)):
        unsafe = bind_manifest(manifest, [*wrappers, search_input(**{attribute: value})])
        assert "set_mode_key" not in unsafe.fields_by_key
        assert unsafe.incompatible_fields["set_mode_key"]["applicability"] == "incompatible"


def test_bind_manifest_select_uses_unique_identity_root_without_editable_input() -> None:
    candidate = ElementCandidate(
        key="state", fieldid="query_state", label="账户状态", title="",
        region_key="query", region_fieldid="query", element_type="formItem",
        component_name="YDFSelect", verified_runtime_fieldids=["state"],
    )
    manifest = PageManifest(PageMeta("root", None, None, None), query_fields=[candidate])
    root = {
        "fieldid": "state", "tag_name": "div", "visible": True, "editable": True,
        "pointer_receivable": True, "identity_root": "0:3", "is_identity_root": True,
    }
    label = {**root, "tag_name": "label", "is_identity_root": False}
    search_input = {
        **root, "tag_name": "input", "role": "combobox", "readonly": True,
        "editable": False, "is_identity_root": False,
    }

    binding = bind_manifest(manifest, [root, label, search_input])

    assert binding.fields_by_key["state"].runtime.is_identity_root is True
    assert binding.fields_by_key["state"].contract_path["applicability"] == "verified"
    for unsafe_root in (
        {**root, "visible": False}, {**root, "disabled": True},
        {**root, "readonly": True}, {**root, "pointer_receivable": False},
    ):
        unsafe = bind_manifest(manifest, [unsafe_root, label, search_input])
        assert "state" not in unsafe.fields_by_key

    ambiguous = bind_manifest(manifest, [root, label, search_input, {**root, "identity_root": "1:3"}])
    assert "state" not in ambiguous.fields_by_key
    for unusable_search in ({**search_input, "visible": False}, {**search_input, "disabled": True}):
        assert "state" not in bind_manifest(manifest, [root, label, unusable_search]).fields_by_key
    controls = [
        {**root, "tag_name": "input", "role": "combobox", "is_identity_root": False, "selector": selector}
        for selector in ("#first", "#second")
    ]
    assert "state" not in bind_manifest(manifest, [root, label, *controls]).fields_by_key


def test_bind_manifest_collapses_direct_identity_date_root_to_unique_input() -> None:
    direct_id = "2025042916094932627680310720055"
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
                                "key": "wdzqxx_pancel",
                                "divCode": "wdzqxx_pancel",
                                "nodeType": "form",
                                "name": "LCDPanel",
                                "children": [
                                    {
                                        "key": direct_id,
                                        "divCode": direct_id,
                                        "nodeType": "formItem",
                                        "name": "YDFDatePicker",
                                        "label": "关账日期",
                                        "dataField": "accountClosingDate",
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        }
    )
    wrappers = [
        {
            "fieldid": direct_id,
            "tag_name": tag_name,
            "visible": True,
            "editable": True,
            "pointer_receivable": True,
            "identity_root": "0:21",
        }
        for tag_name in ("div", "div", "label", "div")
    ]
    date_input = {
        "fieldid": f"{direct_id}_input",
        "tag_name": "input",
        "role": "textbox",
        "visible": True,
        "readonly": True,
        "editable": False,
        "pointer_receivable": True,
        "identity_root": "0:21",
    }

    binding = bind_manifest(manifest, [*wrappers, date_input])

    assert binding.fields_by_key[direct_id].runtime.tag_name == "div"
    assert binding.fields_by_key[direct_id].runtime.identity_root == "0:21"
    assert binding.fields_by_key[direct_id].reasons == [
        "platform_identity",
    ]
    assert binding.fields_by_key[direct_id].contract_path["applicability"] == "verified"
    assert binding.fields_by_key[direct_id].contract_path["fallback_reason"] is None
    assert binding.incompatible_fields == {}


def test_bind_manifest_tree_modal_prefers_unique_nested_search_input_over_trigger_button() -> None:
    manifest = build_page_manifest(
        {
            "data": {
                "uidata": [{
                    "key": "root",
                    "divCode": "root",
                    "nodeType": "root",
                    "children": [{
                        "key": "main_form",
                        "divCode": "mainForm",
                        "nodeType": "form",
                        "name": "LCDPanel",
                        "children": [{
                            "key": "mainForm_department",
                            "divCode": "mainForm_department",
                            "nodeType": "formItem",
                            "name": "YDFTreeModalSelect",
                            "label": "调研负责部门",
                            "dataField": "department",
                        }],
                    }],
                }]
            }
        }
    )
    wrappers = [
        {
            "fieldid": "mainForm_department",
            "tag_name": tag_name,
            "visible": True,
            "in_dialog": True,
            "editable": True,
            "pointer_receivable": True,
            "identity_root": "0:7",
        }
        for tag_name in ("div", "label", "div")
    ]
    nested_input = {
        "fieldid": "mainForm_department_input_search_input",
        "tag_name": "input",
        "role": "combobox",
        "visible": True,
        "in_dialog": True,
        "editable": True,
        "pointer_receivable": True,
        "identity_root": "0:7",
    }
    trigger_button = {
        "fieldid": "mainForm_department_btn",
        "tag_name": "button",
        "visible": True,
        "in_dialog": True,
        "editable": False,
        "pointer_receivable": True,
        "identity_root": "0:7",
    }

    binding = bind_manifest(manifest, [*wrappers, nested_input, trigger_button])

    bound = binding.fields_by_key["mainForm_department"]
    assert bound.runtime.fieldid == "mainForm_department_input_search_input"
    assert bound.contract_path["applicability"] == "verified"

    exact_button_binding = bind_manifest(
        manifest,
        [*wrappers, nested_input, {**trigger_button, "fieldid": "mainForm_department"}],
    )
    assert (
        exact_button_binding.fields_by_key["mainForm_department"].runtime.fieldid
        == "mainForm_department_input_search_input"
    )

    cross_root_binding = bind_manifest(
        manifest,
        [
            {**nested_input, "fieldid": "mainForm_department", "identity_root": "0:7"},
            {**trigger_button, "fieldid": "mainForm_department", "identity_root": "0:8"},
        ],
    )
    assert "mainForm_department" not in cross_root_binding.fields_by_key
    assert cross_root_binding.incompatible_fields["mainForm_department"]["applicability"] == "incompatible"

    missing_root_binding = bind_manifest(
        manifest,
        [
            {**nested_input, "fieldid": "mainForm_department", "identity_root": None},
            {**trigger_button, "fieldid": "mainForm_department", "identity_root": None},
        ],
    )
    assert "mainForm_department" not in missing_root_binding.fields_by_key
    assert missing_root_binding.incompatible_fields["mainForm_department"]["applicability"] == "incompatible"

    unknown_input = dict(nested_input, pointer_receivable=None)
    ambiguous = bind_manifest(manifest, [*wrappers, unknown_input, dict(unknown_input)])
    assert "mainForm_department" not in ambiguous.fields_by_key
    assert ambiguous.incompatible_fields["mainForm_department"]["applicability"] == "incompatible"


def test_bind_manifest_does_not_verify_unknown_pointer_receivability() -> None:
    manifest = PageManifest(
        page=PageMeta(fieldid="root", biz_obj_code="pmProjectInfo", app_code=None, domain_key=None),
        fields=[
            ElementCandidate(
                key="pro_name",
                fieldid="proName",
                label="项目名称",
                title="",
                region_key="baseForm",
                region_fieldid="baseForm",
                element_type="formItem",
                component_name="YDFInput",
                data_field="proName",
                verified_runtime_fieldids=["proName"],
            )
        ],
    )

    binding = bind_manifest(
        manifest,
        [{
            "fieldid": "proName",
            "role": "textbox",
            "tag_name": "input",
            "visible": True,
            "editable": True,
            "pointer_receivable": None,
            "selector": '[fieldid="proName"]',
        }],
    )

    bound = binding.fields_by_key["pro_name"]
    assert bound.contract_path == {
        "contract_version": "1.0.1",
        "applicability": "unverified",
        "rule_ids": ["PRS-FORM-001"],
        "fallback_reason": "component_variant_unverified",
    }


def test_bind_runtime_readable_form_field_uses_unique_exact_identity() -> None:
    candidate = ElementCandidate(
        key="pro_name",
        fieldid="proName",
        label="项目名称",
        title="",
        region_key="baseForm",
        region_fieldid="baseForm",
        element_type="formItem",
        component_name="YDFInput",
        data_field="proName",
        verified_runtime_fieldids=["pmProjectInfo_proName"],
    )

    bound = bind_runtime_readable_form_field(
        [candidate],
        [{
            "fieldid": "pmProjectInfo_proName",
            "text": "只读项目",
            "visible": True,
            "readonly": True,
            "editable": False,
            "selector": '[fieldid="pmProjectInfo_proName"]',
        }],
    )

    assert bound is not None
    assert bound.runtime.fieldid == "pmProjectInfo_proName"
    assert bound.reasons == ["platform_identity", "read_only_assertion"]


def test_bind_runtime_readable_form_field_rejects_background_identity_under_foreground() -> None:
    candidate = ElementCandidate(
        key="pro_name",
        fieldid="proName",
        label="项目名称",
        title="",
        region_key="baseForm",
        region_fieldid="baseForm",
        element_type="formItem",
        component_name="YDFInput",
        data_field="proName",
        verified_runtime_fieldids=["proName"],
    )

    bound = bind_runtime_readable_form_field(
        [candidate],
        [
            {"fieldid": "proName", "visible": True, "readonly": True},
            {"fieldid": "dialogField", "visible": True, "in_dialog": True},
        ],
    )

    assert bound is None


def test_bind_manifest_ignores_hidden_dialog_when_binding_visible_page_field() -> None:
    manifest = PageManifest(
        page=PageMeta(fieldid="root", biz_obj_code="pmProjectInfo", app_code=None, domain_key=None),
        fields=[
            ElementCandidate(
                key="pro_name",
                fieldid="proName",
                label="项目名称",
                title="",
                region_key="baseForm",
                region_fieldid="baseForm",
                element_type="formItem",
                component_name="YDFInput",
                data_field="proName",
                verified_runtime_fieldids=["proName"],
            )
        ],
    )

    binding = bind_manifest(
        manifest,
        [
            {"fieldid": "proName", "visible": True, "editable": True, "pointer_receivable": True},
            {"fieldid": "dialogField", "visible": False, "in_dialog": True},
        ],
    )

    assert binding.fields_by_key["pro_name"].runtime.fieldid == "proName"


def test_bind_manifest_does_not_fallback_when_exact_identity_is_not_usable() -> None:
    manifest = PageManifest(
        page=PageMeta(fieldid="root", biz_obj_code="pmProjectInfo", app_code=None, domain_key=None),
        fields=[
            ElementCandidate(
                key="pro_name",
                fieldid="proName",
                label="项目名称",
                title="",
                region_key="baseForm",
                region_fieldid="baseForm",
                element_type="formItem",
                component_name="YDFInput",
                data_field="proName",
                verified_runtime_fieldids=["proName"],
            )
        ],
    )

    binding = bind_manifest(
        manifest,
        [
            {
                "fieldid": "proName",
                "label_text": "项目名称",
                "role": "textbox",
                "tag_name": "input",
                "visible": True,
                "disabled": True,
                "editable": False,
                "selector": '[fieldid="proName"]',
            },
            {
                "fieldid": "otherName",
                "label_text": "项目名称",
                "role": "textbox",
                "tag_name": "input",
                "visible": True,
                "editable": True,
                "selector": '[fieldid="otherName"]',
            },
        ],
    )

    assert binding.missing_fields == ["项目名称"]
    assert not binding.bound_fields


def test_bind_manifest_records_missing_candidates(sample_template_payload: dict, sample_runtime_elements: list[dict]) -> None:
    manifest = build_page_manifest(sample_template_payload)
    runtime_without_submit = [item for item in sample_runtime_elements if item.get("fieldid") != "btn_submit"]

    binding = bind_manifest(manifest, runtime_without_submit)

    assert "提交" in binding.missing_actions


def test_bind_manifest_matches_by_data_field_and_placeholder(sample_template_payload: dict) -> None:
    manifest = build_page_manifest(sample_template_payload)
    runtime_elements = [
        {
            "fieldid": None,
            "id": "input-auto-1",
            "name": "projectCode",
            "placeholder": "项目编码",
            "text": "",
            "role": "textbox",
            "tag_name": "input",
            "visible": True,
            "selector": 'input[name="projectCode"]',
        }
    ]

    binding = bind_manifest(manifest, runtime_elements)

    project_code = binding.fields_by_key["project_code"]
    assert project_code.runtime.name == "projectCode"
    assert project_code.confidence >= 0.78
    assert "data_field:name" in project_code.reasons or "placeholder" in project_code.reasons


def test_bind_manifest_matches_by_runtime_accessibility_metadata(sample_template_payload: dict) -> None:
    manifest = build_page_manifest(sample_template_payload)
    runtime_elements = [
        {
            "fieldid": None,
            "id": None,
            "name": None,
            "placeholder": None,
            "text": "",
            "label_text": "项目编码",
            "aria_label": "项目编码",
            "title_attr": "项目编码",
            "role": "textbox",
            "tag_name": "div",
            "visible": True,
            "selector": 'div[data-testid="project-code"]',
        }
    ]

    binding = bind_manifest(manifest, runtime_elements)

    project_code = binding.fields_by_key["project_code"]
    assert project_code.runtime.aria_label == "项目编码"
    assert project_code.confidence >= 0.78
    assert any(reason in project_code.reasons for reason in ("label_text", "aria_label", "title_attr"))


def test_bind_manifest_rejects_background_exact_identity_instead_of_choosing_similar_field() -> None:
    manifest = PageManifest(
        page=PageMeta(fieldid="root", biz_obj_code="pmProjectInfo", app_code=None, domain_key=None),
        fields=[
            ElementCandidate(
                key="project_code_key",
                fieldid="proCode",
                label="项目代码",
                title="",
                region_key="main",
                region_fieldid="main",
                element_type="formItem",
                component_name="YDFInput",
                data_field="proCode",
            )
        ],
    )
    runtime_elements = [
        {
            "fieldid": "proCode",
            "label_text": "财政项目代码",
            "role": "textbox",
            "tag_name": "input",
            "visible": True,
            "editable": True,
            "selector": '[fieldid="proCode"]',
            "in_dialog": False,
        },
        {
            "fieldid": "dialog_proCode",
            "label_text": "项目代码",
            "role": "textbox",
            "tag_name": "input",
            "visible": True,
            "editable": True,
            "selector": '[uikey="project_code_key"] input',
            "in_dialog": True,
        },
    ]

    binding = bind_manifest(manifest, runtime_elements)

    assert "项目代码" in binding.missing_fields


def test_bind_manifest_does_not_mark_query_identity_conflict_as_form_incompatible() -> None:
    manifest = PageManifest(
        page=PageMeta(fieldid="root", biz_obj_code="pmProjectInfo", app_code=None, domain_key=None),
        query_fields=[
            ElementCandidate(
                key="query_project_name",
                fieldid="query_project_name",
                label="项目名称",
                title="",
                region_key="query_form",
                region_fieldid="query_form",
                element_type="formItem",
                component_name="YDFInput",
                data_field="projectName",
                verified_runtime_fieldids=["query_project_name"],
            )
        ],
    )
    runtime_elements = [
        {
            "fieldid": "query_project_name",
            "role": "textbox",
            "tag_name": "input",
            "visible": True,
            "editable": True,
            "in_dialog": False,
            "selector": '[fieldid="query_project_name"]',
        },
        {
            "fieldid": "dialog_project_name",
            "label_text": "项目名称",
            "role": "textbox",
            "tag_name": "input",
            "visible": True,
            "editable": True,
            "in_dialog": True,
            "selector": '[fieldid="dialog_project_name"]',
        },
    ]

    binding = bind_manifest(manifest, runtime_elements)

    assert binding.incompatible_fields == {}


def test_bind_manifest_rejects_label_text_match_when_runtime_text_names_another_field() -> None:
    manifest = PageManifest(
        page=PageMeta(fieldid="root", biz_obj_code="payVoucherBill", app_code=None, domain_key=None),
        fields=[
            ElementCandidate(
                key="payee_name_key",
                fieldid="payeeAcctName",
                label="收款人全称",
                title="",
                region_key="main",
                region_fieldid="main",
                element_type="formItem",
                component_name="YDFReferSelect",
                data_field="payeeAcctName",
            )
        ],
    )
    runtime_elements = [
        {
            "fieldid": "20230426173406342911827918929_drag",
            "name": "开户银行",
            "text": "开户银行",
            "label_text": "收款人全称",
            "role": None,
            "tag_name": "div",
            "visible": True,
            "editable": True,
            "selector": '[fieldid="bank_drag"]',
            "in_dialog": True,
        },
        {
            "fieldid": "payeeAcctName_drag",
            "name": "收款人全称",
            "text": "收款人全称",
            "label_text": "",
            "role": None,
            "tag_name": "div",
            "visible": True,
            "editable": True,
            "selector": '[fieldid="payeeAcctName_drag"]',
            "in_dialog": False,
        },
    ]

    binding = bind_manifest(manifest, runtime_elements)

    assert binding.fields_by_key["payee_name_key"].runtime.selector == '[fieldid="payeeAcctName_drag"]'


def test_bind_manifest_does_not_bind_short_action_to_unrelated_longer_text(sample_template_payload: dict) -> None:
    manifest = build_page_manifest(sample_template_payload)
    runtime_elements = [
        {
            "fieldid": "dashboard_empty_btn",
            "id": None,
            "name": None,
            "placeholder": None,
            "text": "保存草稿",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="dashboard_empty_btn"]',
        }
    ]

    binding = bind_manifest(manifest, runtime_elements)

    assert "保存" in binding.missing_actions


def test_bind_manifest_matches_label_with_display_suffix(sample_template_payload: dict) -> None:
    manifest = build_page_manifest(sample_template_payload)
    runtime_elements = [
        {
            "fieldid": "project_code_runtime",
            "id": None,
            "name": None,
            "placeholder": None,
            "text": "项目编码(只读)",
            "label_text": "",
            "aria_label": None,
            "title_attr": "项目编码(只读)",
            "role": None,
            "tag_name": "div",
            "visible": True,
            "selector": '[fieldid="project_code_runtime"]',
        }
    ]

    binding = bind_manifest(manifest, runtime_elements)

    project_code = binding.fields_by_key["project_code"]
    assert project_code.runtime.selector == '[fieldid="project_code_runtime"]'
    assert "提交" in binding.missing_actions


def test_bind_manifest_does_not_bind_form_field_to_background_table_header(
    sample_template_payload: dict,
) -> None:
    sample_template_payload["data"]["uidata"][0]["children"] = [
        {
            "key": "edit_card",
            "divCode": "editCard",
            "nodeType": "card",
            "label": "新增弹窗",
            "children": [
                {
                    "key": "isvalid",
                    "divCode": "isvalid",
                    "nodeType": "formItem",
                    "label": "是否启用",
                    "name": "YDFSelect",
                    "dataField": "isvalid",
                }
            ],
        }
    ]
    manifest = build_page_manifest(sample_template_payload)
    runtime_elements = [
        {
            "fieldid": "table_isvalid",
            "id": None,
            "name": None,
            "placeholder": None,
            "text": "是否启用",
            "role": None,
            "tag_name": "th",
            "visible": True,
            "selector": '[fieldid="table_isvalid"]',
            "in_table": True,
        },
        {
            "fieldid": None,
            "id": None,
            "name": "isvalid",
            "placeholder": "",
            "text": "",
            "role": "combobox",
            "tag_name": "input",
            "visible": True,
            "selector": '.wui-modal input[name="isvalid"]',
            "in_dialog": True,
        },
    ]

    binding = bind_manifest(manifest, runtime_elements)

    assert binding.fields_by_key["isvalid"].runtime.selector == '.wui-modal input[name="isvalid"]'


def test_bind_manifest_does_not_bind_form_checkbox_to_table_or_tree_checkbox(sample_template_payload: dict) -> None:
    sample_template_payload["data"]["uidata"][0]["children"] = [
        {
            "key": "edit_card",
            "divCode": "editCard",
            "nodeType": "card",
            "label": "预算信息",
            "children": [
                {
                    "key": "hide_zero",
                    "divCode": "hideZero",
                    "nodeType": "formItem",
                    "label": "隐藏0金额行",
                    "name": "YDFCheckbox",
                    "dataField": "hideZero",
                }
            ],
        }
    ]
    manifest = build_page_manifest(sample_template_payload)
    runtime_elements = [
        {
            "fieldid": "hideZero",
            "id": None,
            "name": "hideZero",
            "placeholder": None,
            "text": "隐藏0金额行",
            "role": "checkbox",
            "tag_name": "input",
            "visible": True,
            "selector": '.wui-table [fieldid="hideZero"] input[type="checkbox"]',
            "in_table": True,
            "editable": True,
        },
        {
            "fieldid": None,
            "id": None,
            "name": None,
            "placeholder": None,
            "text": "隐藏0金额行",
            "label_text": "隐藏0金额行",
            "role": "checkbox",
            "tag_name": "span",
            "visible": True,
            "selector": '.wui-tree [role="checkbox"]',
            "editable": True,
        },
    ]

    binding = bind_manifest(manifest, runtime_elements)

    assert "隐藏0金额行" in binding.missing_fields
    assert "hide_zero" not in binding.fields_by_key


def test_bind_runtime_form_field_prefers_dialog_editable_control_over_table_header() -> None:
    runtime_elements = [
        {
            "fieldid": "table_pre_estimate",
            "id": None,
            "name": None,
            "placeholder": None,
            "text": "是否事前评估",
            "role": None,
            "tag_name": "th",
            "visible": True,
            "selector": '[fieldid="table_pre_estimate"]',
            "in_table": True,
            "editable": False,
        },
        {
            "fieldid": None,
            "id": None,
            "name": "isPreEstimate",
            "placeholder": "",
            "text": "",
            "label_text": "是否事前评估:",
            "role": "combobox",
            "tag_name": "div",
            "visible": True,
            "selector": '.w-modal .w-select-selection[aria-controls="preEstimate"]',
            "in_dialog": True,
            "editable": True,
        },
    ]

    bound = bind_runtime_form_field("是否事前评估", runtime_elements)

    assert bound is not None
    assert bound.runtime.selector == '.w-modal .w-select-selection[aria-controls="preEstimate"]'
    assert bound.candidate.raw["runtime_only"] is True
    assert "label_text:normalized" in bound.reasons


def test_bind_runtime_form_field_prefers_actual_control_over_uikey_wrapper() -> None:
    bound = bind_runtime_form_field(
        "资金往来对象名称",
        [
            {
                "fieldid": "counterpartName",
                "text": "资金往来对象名称",
                "label_text": "资金往来对象名称",
                "tag_name": "label",
                "visible": True,
                "in_dialog": True,
                "editable": True,
                "selector": '[uikey="counterpartName"]',
            },
            {
                "fieldid": "counterpartName",
                "label_text": "资金往来对象名称",
                "tag_name": "input",
                "role": "textbox",
                "visible": True,
                "in_dialog": True,
                "editable": True,
                "selector": '[data-ydf-browser-runtime-id="input"]',
            },
        ],
    )

    assert bound is not None
    assert bound.runtime.tag_name == "input"


def test_bind_runtime_form_field_prefers_actual_control_over_modal_select_wrapper() -> None:
    bound = bind_runtime_form_field(
        "姓名",
        [
            {
                "fieldid": "perinfo_query_perName",
                "label_text": "姓名",
                "tag_name": "input",
                "visible": True,
                "editable": True,
                "selector": '[fieldid="perinfo_query_perName"]',
            },
            {
                "fieldid": "runtime_status_wrapper",
                "label_text": "姓名",
                "text": "人员状态",
                "tag_name": "div",
                "visible": True,
                "in_dialog": True,
                "editable": True,
                "selector": '[class*="YDFTreeModalSelect"]',
            },
        ],
    )

    assert bound is not None
    assert bound.runtime.selector == '[fieldid="perinfo_query_perName"]'


def test_bind_runtime_form_field_prefers_dialog_when_background_has_same_label() -> None:
    runtime_elements = [
        {
            "fieldid": "background_pre_estimate",
            "id": None,
            "name": "isPreEstimateBackground",
            "placeholder": "",
            "text": "",
            "label_text": "是否事前评估",
            "role": "combobox",
            "tag_name": "input",
            "visible": True,
            "selector": '[fieldid="background_pre_estimate"] input',
            "in_dialog": False,
            "editable": True,
        },
        {
            "fieldid": None,
            "id": None,
            "name": "isPreEstimateDialog",
            "placeholder": "",
            "text": "",
            "label_text": "是否事前评估",
            "role": "combobox",
            "tag_name": "input",
            "visible": True,
            "selector": '.wui-modal input[name="isPreEstimateDialog"]',
            "in_dialog": True,
            "editable": True,
        },
    ]

    bound = bind_runtime_form_field("是否事前评估", runtime_elements)

    assert bound is not None
    assert bound.runtime.selector == '.wui-modal input[name="isPreEstimateDialog"]'
