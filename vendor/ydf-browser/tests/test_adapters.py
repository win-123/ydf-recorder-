from ydf_browser.adapters import (
    RenderAdapterRegistry,
    default_render_adapter_registry,
    selector_builder,
)


def test_default_registry_classifies_template_regions_by_adapter_rules() -> None:
    registry = default_render_adapter_registry()

    assert registry.classify_region({"divCode": "seachBox", "name": "LCDQueryString"}) == "query_box"
    assert registry.classify_region({"nodeType": "tabs", "name": "LCDTabs", "label": "多页签"}) == "tab_bar"
    assert registry.classify_region(
        {"nodeType": "toolbar", "name": "YDFStepsNext", "label": "步骤条", "type": "capsule"}
    ) == "tab_bar"
    assert registry.classify_region({"nodeType": "toolbar", "label": "按钮", "parentKey": "root"}) == "top_action_bar"
    assert (
        registry.classify_region(
            {"nodeType": "toolbar", "name": "LCDBtnToolbar", "label": "底部工具栏", "parentKey": "root"}
        )
        == "top_action_bar"
    )
    assert registry.classify_region({"nodeType": "tree", "name": "YDFTree"}) == "tree"


def test_registry_allows_selector_rules_to_be_replaced_without_changing_runtime_callers() -> None:
    registry = RenderAdapterRegistry(
        selector_builders={
            "query.expand": selector_builder(lambda: ["button.custom-query-expand"]),
        }
    )

    assert registry.selectors("query.expand") == ["button.custom-query-expand"]


def test_query_reset_selectors_are_strictly_scoped_to_query_region() -> None:
    selectors = default_render_adapter_registry().selectors("query.reset", "dataQueryArea")

    assert selectors[0] == '[fieldid="dataQueryArea"] [fieldid="reset_btn"]'
    assert '[fieldid="dataQueryArea"] button:text-is("重置")' in selectors
    assert '[fieldid="dataQueryArea_drag"] button:text-is("重置")' in selectors
    assert '[fieldid="dataQueryArea_drag"] button:has-text("重置")' in selectors
    assert all("dataQueryArea" in selector for selector in selectors)
    assert all("更多" not in selector for selector in selectors)
    assert all('title="重置"' not in selector for selector in selectors)
    assert all('aria-label="重置"' not in selector for selector in selectors)
    assert default_render_adapter_registry().selectors("query.reset_identity") == [
        '[fieldid="reset_btn"]',
        '[data-fieldid="reset_btn"]',
        'button[fieldid="reset_btn"]',
        'button[data-fieldid="reset_btn"]',
    ]


def test_default_registry_exposes_core_component_selector_rules() -> None:
    registry = default_render_adapter_registry()

    assert registry.selectors("tree.node", "001 办公室")[0] == 'text="001 办公室"'
    assert registry.selectors("toolbar.action", "导出")[0] == '[fieldid="dc_btn"]'
    assert registry.selectors("row.action", "详情")[0] == '[fieldid="xq_btn"]'
    assert registry.selectors("query.action", "查询")[0] == "button.lcd-query-string-config-query"
    reset_selectors = registry.selectors("query.reset", "dataQueryArea")
    assert reset_selectors[0] == '[fieldid="dataQueryArea"] [fieldid="reset_btn"]'
    assert '[fieldid="dataQueryArea"] button:text-is("重置")' in reset_selectors
    assert all("dataQueryArea" in selector for selector in reset_selectors)
    assert all("更多" not in selector for selector in reset_selectors)
    assert 'text="001 办公室"' not in registry.selectors("query.choice", "001 办公室")
    assert registry.selectors("popup_reference.dialog")[0] == ".yy-ydf-modal:visible"
    assert '.wui-tree [title="C99000000 其他服务"]' in registry.selectors(
        "popup_reference.tree_node",
        "C99000000 其他服务",
    )
    assert '[title="C99000000 其他服务"]' not in registry.selectors(
        "popup_reference.tree_node",
        "C99000000 其他服务",
    )
    assert '[role="option"]:has-text("01 身份证")' in registry.selectors(
        "popup_reference.option",
        "01 身份证",
    )
    assert 'tr:has-text("001421072617")' in registry.selectors(
        "popup_reference.table_row",
        "001421072617",
    )
    popup_confirm_selectors = registry.selectors("popup_reference.confirm", "确认")
    assert '.wui-modal-footer button:text-is("确认")' in popup_confirm_selectors
    assert 'button:text-is("确认")' not in popup_confirm_selectors
    assert registry.selectors("transfer_dialog.dialog")[0] == ".ant-modal:visible"
    assert ".yy-modal:visible" in registry.selectors("transfer_dialog.dialog")
    assert 'button:text-is("确定")' in registry.selectors("transfer_dialog.confirm", "确定")
    assert any("right" in item.lower() for item in registry.selectors("transfer_dialog.move_to_target"))
