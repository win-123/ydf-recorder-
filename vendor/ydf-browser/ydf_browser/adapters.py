from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

RegionPredicate = Callable[[dict[str, Any]], bool]
SelectorBuilder = Callable[..., list[str]]


@dataclass(frozen=True, slots=True)
class RegionRule:
    name: str
    region_type: str
    matches: RegionPredicate


@dataclass(frozen=True, slots=True)
class SelectorRule:
    name: str
    build: SelectorBuilder


def selector_builder(build: SelectorBuilder) -> SelectorRule:
    return SelectorRule(name=getattr(build, "__name__", "selector"), build=build)


@dataclass(slots=True)
class RenderAdapterRegistry:
    region_rules: list[RegionRule] = field(default_factory=list)
    selector_builders: Mapping[str, SelectorRule | SelectorBuilder] = field(default_factory=dict)

    def classify_region(self, node: dict[str, Any]) -> str | None:
        for rule in self.region_rules:
            if rule.matches(node):
                return rule.region_type
        return None

    def selectors(self, name: str, *args: Any, **kwargs: Any) -> list[str]:
        raw_builder = self.selector_builders.get(name)
        if raw_builder is None:
            raise KeyError(f"未注册渲染选择器规则: {name}")
        builder = raw_builder.build if isinstance(raw_builder, SelectorRule) else raw_builder
        return list(builder(*args, **kwargs))


def default_render_adapter_registry() -> RenderAdapterRegistry:
    return RenderAdapterRegistry(
        region_rules=[
            RegionRule("root", "page_root", _is_page_root),
            RegionRule("query-string", "query_box", _is_query_box),
            RegionRule("tab-toolbar", "tab_bar", _is_tab_toolbar),
            RegionRule("form-tabs", "tab_bar", _is_form_tab_container),
            RegionRule("step-toolbar", "step_bar", _is_step_toolbar),
            RegionRule("action-toolbar", "top_action_bar", _is_top_action_bar),
            RegionRule("table-action-toolbar", "table_action_bar", _is_table_action_bar),
            RegionRule("content-card", "content_card", _is_content_card),
            RegionRule("tree", "tree", _is_tree),
            RegionRule("main-table", "main_table", _is_main_table),
            RegionRule("dialog-page", "dialog_page", _is_dialog_page),
        ],
        selector_builders={
            "tree.node": selector_builder(_tree_node_selectors),
            "query.expand": selector_builder(_query_expand_selectors),
            "query.action": selector_builder(_query_action_selectors),
            "query.reset": selector_builder(_query_reset_selectors),
            "query.reset_identity": selector_builder(_query_reset_identity_selectors),
            "query.reset_text": selector_builder(_query_reset_text_selectors),
            "query.choice": selector_builder(_query_choice_selectors),
            "query.choice_tree_closed_switcher": selector_builder(_query_choice_tree_closed_switcher_selectors),
            "toolbar.more": selector_builder(_toolbar_more_selectors),
            "toolbar.action": selector_builder(_toolbar_action_selectors),
            "toolbar.exact_text": selector_builder(_toolbar_exact_text_selectors),
            "toolbar.dropdown_item": selector_builder(_toolbar_dropdown_item_selectors),
            "tree.closed_switcher": selector_builder(_tree_closed_switcher_selectors),
            "table.data_row": selector_builder(_table_data_row_selectors),
            "table.tree_expand": selector_builder(_table_tree_expand_selectors),
            "row.selection_checkbox": selector_builder(_row_selection_checkbox_selectors),
            "row.action": selector_builder(_row_action_selectors),
            "tab.action": selector_builder(_tab_action_selectors),
            "tab.exact_text": selector_builder(_tab_exact_text_selectors),
            "editable_table.add_row": selector_builder(_editable_table_add_row_selectors),
            "fieldid.action": selector_builder(_fieldid_action_selectors),
            "popup_reference.dialog": selector_builder(_popup_reference_dialog_selectors),
            "popup_reference.trigger": selector_builder(_popup_reference_trigger_selectors),
            "popup_reference.filter": selector_builder(_popup_reference_filter_selectors),
            "popup_reference.filter_submit": selector_builder(_popup_reference_filter_submit_selectors),
            "popup_reference.tree_node": selector_builder(_popup_reference_tree_node_selectors),
            "popup_reference.tree_closed_switcher": selector_builder(_popup_reference_tree_closed_switcher_selectors),
            "popup_reference.option": selector_builder(_popup_reference_option_selectors),
            "popup_reference.table_row": selector_builder(_popup_reference_table_row_selectors),
            "popup_reference.confirm": selector_builder(_popup_reference_confirm_selectors),
            "transfer_dialog.dialog": selector_builder(_transfer_dialog_dialog_selectors),
            "transfer_dialog.move_to_target": selector_builder(_transfer_dialog_move_to_target_selectors),
            "transfer_dialog.confirm": selector_builder(_transfer_dialog_confirm_selectors),
        },
    )


def _is_page_root(node: dict[str, Any]) -> bool:
    return node.get("divCode") == "root" or node.get("nodeType") == "root"


def _is_query_box(node: dict[str, Any]) -> bool:
    return node.get("divCode") in {"queryBox", "seachBox", "searchBox"} or node.get("name") == "LCDQueryString"


def _is_tab_toolbar(node: dict[str, Any]) -> bool:
    if node.get("nodeType") != "toolbar":
        return False
    props = node.get("props") or {}
    if props.get("type") == "tab":
        return True
    component_name = str(node.get("name") or "").lower()
    toolbar_type = str(node.get("type") or props.get("type") or "").lower()
    return component_name == "ydfstepsnext" and toolbar_type == "capsule"


def _is_form_tab_container(node: dict[str, Any]) -> bool:
    node_type = str(node.get("nodeType") or "")
    component_name = str(node.get("name") or "")
    label = str(node.get("label") or node.get("title") or "")
    normalized_type = node_type.lower()
    normalized_name = component_name.lower()
    if normalized_type in {"tabs", "tab", "tabbar", "tab_bar"}:
        return True
    if normalized_name in {"tabs", "ydftabs", "wuitabs", "lcdtabs", "tabbar"}:
        return True
    return "页签" in label and normalized_type not in {"table", "column"}


def _is_step_toolbar(node: dict[str, Any]) -> bool:
    return node.get("nodeType") == "toolbar" and "步骤" in str(node.get("label") or node.get("title") or "")


def _is_top_action_bar(node: dict[str, Any]) -> bool:
    return _is_action_toolbar(node) and node.get("parentKey") == "root"


def _is_table_action_bar(node: dict[str, Any]) -> bool:
    return _is_action_toolbar(node) and node.get("parentKey") != "root"


def _is_action_toolbar(node: dict[str, Any]) -> bool:
    if node.get("nodeType") != "toolbar":
        return False
    label = str(node.get("label") or node.get("title") or "")
    component_name = str(node.get("name") or "").lower()
    return "按钮工具栏" in label or label in {"按钮", "底部工具栏"} or component_name == "lcdbtntoolbar"


def _is_content_card(node: dict[str, Any]) -> bool:
    return node.get("nodeType") == "card" or (node.get("nodeType") == "form" and node.get("name") == "LCDPanel")


def _is_tree(node: dict[str, Any]) -> bool:
    return node.get("nodeType") == "tree"


def _is_main_table(node: dict[str, Any]) -> bool:
    return node.get("nodeType") == "table"


def _is_dialog_page(node: dict[str, Any]) -> bool:
    return node.get("name") == "LCDPage"


def _query_expand_selectors() -> list[str]:
    return [
        "button.query-collapse-icon:has(.icon-xiangxia)",
        "button.wui-button.query-collapse-icon.wui-button-icon-only",
        "button.query-collapse-icon",
        "button:has(.icon-xiangxia)",
    ]


def _query_action_selectors(action_label: str = "查询", fieldids: list[str] | None = None) -> list[str]:
    fieldid = {
        "查询": "query_btn",
        "搜索": "query_btn",
        "重置": "reset_btn",
    }.get(action_label, "")
    selectors: list[str] = []
    for item in fieldids or []:
        selectors.extend(_fieldid_action_selectors(str(item)))
    if action_label in {"查询", "搜索"}:
        selectors.extend(
            [
                "button.lcd-query-string-config-query",
                "button.wui-button-icon-only:has(.icon-sousuo)",
                "button:has(.icon-sousuo)",
                ".lcd-query-string-config-query",
            ]
        )
    if fieldid:
        selectors.extend(
            [
                f'[fieldid="{fieldid}"]',
                f'[data-fieldid="{fieldid}"]',
                f'button[fieldid="{fieldid}"]',
                f'button[data-fieldid="{fieldid}"]',
            ]
        )
    labels = [action_label]
    if action_label == "查询":
        labels.append("搜索")
    if action_label == "搜索":
        labels.append("查询")
    for label in labels:
        selectors.extend(
            [
                f'#queryBox button:has-text("{label}")',
                f'[fieldid="queryBox"] button:has-text("{label}")',
                f'[data-fieldid="queryBox"] button:has-text("{label}")',
                f'button:has-text("{label}")',
                f'[role="button"]:has-text("{label}")',
                f'[title="{label}"]',
                f'[aria-label="{label}"]',
                f'text="{label}"',
            ]
        )
    selectors.extend(
        [
            'button[class*="search"]',
            '[role="button"][class*="search"]',
            '[class*="search"] button',
            '[class*="search"][role="button"]',
        ]
    )
    return selectors


def _query_reset_selectors(query_region_fieldid: str) -> list[str]:
    roots = [
        f'[fieldid="{query_region_fieldid}"]',
        f'[data-fieldid="{query_region_fieldid}"]',
        f'[fieldid="{query_region_fieldid}_drag"]',
        f'[data-fieldid="{query_region_fieldid}_drag"]',
    ]
    targets = _query_reset_identity_selectors() + _query_reset_text_selectors()
    return [f"{root} {target}" for target in targets for root in roots]


def _query_reset_identity_selectors() -> list[str]:
    return [
        '[fieldid="reset_btn"]',
        '[data-fieldid="reset_btn"]',
        'button[fieldid="reset_btn"]',
        'button[data-fieldid="reset_btn"]',
    ]


def _query_reset_text_selectors() -> list[str]:
    return [
        'button:text-is("重置")',
        'button:has-text("重置")',
        '[role="button"]:text-is("重置")',
        '[role="button"]:has-text("重置")',
        'a:text-is("重置")',
        'a:has-text("重置")',
    ]


def _query_choice_selectors(value: str) -> list[str]:
    return [
        f'.w-select-dropdown [class*="item"]:has-text("{value}")',
        f'.w-select-dropdown [class*="option"]:has-text("{value}")',
        f'.w-select-dropdown [role="option"]:has-text("{value}")',
        f'.w-select-dropdown li:has-text("{value}")',
        f'.w-select-dropdown :text-is("{value}")',
        f'.w-select-dropdown [title="{value}"]',
        f'.wui-select-dropdown [class*="item"]:has-text("{value}")',
        f'.wui-select-dropdown [class*="option"]:has-text("{value}")',
        f'.wui-select-dropdown [class*="menu-item"]:has-text("{value}")',
        f'.wui-select-dropdown [class*="menu"][class*="item"]:has-text("{value}")',
        f'.wui-select-dropdown [role="option"]:has-text("{value}")',
        f'.wui-select-dropdown li:has-text("{value}")',
        f'.wui-select-dropdown [class*="content"]:has-text("{value}")',
        f'.wui-select-dropdown .wui-select-tree-title:has-text("{value}")',
        f'.wui-select-dropdown .wui-select-tree-node-content-wrapper:has-text("{value}")',
        f'.wui-select-dropdown :text-is("{value}")',
        f'.wui-select-dropdown [title="{value}"]',
        f'.wui-select-dropdown [role="treeitem"]:has-text("{value}")',
        f'.wui-select-dropdown .wui-select-tree-treenode:has-text("{value}")',
        f'.wui-select-dropdown .wui-tree-treenode:has-text("{value}")',
        f'.wui-select-dropdown .wui-tree-node-content-wrapper:has-text("{value}")',
        f'.wui-select-item-option:has-text("{value}")',
        f'.ant-select-item-option:has-text("{value}")',
        f'[role="listbox"] [role="option"]:has-text("{value}")',
        f'[class*="popup"] [role="treeitem"]:has-text("{value}")',
        f'[class*="popup"] [role="option"]:has-text("{value}")',
        f'[class*="popup"] [title="{value}"]',
        f'[class*="refer"] [title="{value}"]',
        f'[class*="ref"] [title="{value}"]',
        f'[class*="refer"]:has-text("{value}") tr:has-text("{value}")',
        f'[class*="ref"]:has-text("{value}") tr:has-text("{value}")',
        f'[class*="refer"]:has-text("{value}") [role="row"]:has-text("{value}")',
        f'[class*="ref"]:has-text("{value}") [role="row"]:has-text("{value}")',
        f'[class*="popup"] .wui-table-row:has-text("{value}")',
        f'[class*="popup"] .ant-table-row:has-text("{value}")',
        f'[class*="dropdown"] .wui-table-row:has-text("{value}")',
        f'[class*="dropdown"] .ant-table-row:has-text("{value}")',
        f'.u-select-dropdown:has-text("{value}") [title="{value}"]',
        f'[class*="dropdown"] [title="{value}"]',
        f'[class*="dropdown"] [role="option"]:has-text("{value}")',
        f'[class*="dropdown"] [role="treeitem"]:has-text("{value}")',
        f'[class*="dropdown"] [class*="item"]:has-text("{value}")',
    ]


def _query_choice_tree_closed_switcher_selectors() -> list[str]:
    popup_prefixes = [
        ".w-select-dropdown",
        ".wui-select-dropdown",
        '[class*="popup"]',
        '[class*="dropdown"]',
    ]
    switchers = [
        "span.wui-tree-switcher.wui-tree-center_close",
        "span.wui-tree-switcher[class*='close']",
        ".wui-tree-treenode-close > span.wui-tree-switcher",
        ".wui-tree-treenode-close .wui-tree-switcher",
        "span.wui-select-tree-switcher.wui-select-tree-switcher_close",
        "span.wui-select-tree-switcher[class*='close']",
        ".wui-select-tree-treenode-switcher-close > span.wui-select-tree-switcher",
        ".wui-select-tree-treenode-switcher-close .wui-select-tree-switcher",
    ]
    return [f"{prefix} {switcher}" for prefix in popup_prefixes for switcher in switchers]


def _toolbar_more_selectors() -> list[str]:
    return [
        '[fieldid="more"]',
        '[data-fieldid="more"]',
        'button:has-text("更多")',
        '[role="button"]:has-text("更多")',
        '[title="更多"]:has-text("更多")',
    ]


def _toolbar_action_selectors(action_label: str) -> list[str]:
    fieldid = guess_action_fieldid(action_label)
    selectors: list[str] = []
    if fieldid:
        selectors.extend(
            [
                f'[fieldid="{fieldid}"]',
                f'[data-fieldid="{fieldid}"]',
            ]
        )
    selectors.extend(
        [
            f'button:text-is("{action_label}")',
            f'[role="button"]:text-is("{action_label}")',
            f'button:has-text("{action_label}")',
            f'[title="{action_label}"]',
            f'[role="menuitem"]:text-is("{action_label}")',
            f'[role="menuitem"]:has-text("{action_label}")',
            f'.ant-dropdown-menu-item:text-is("{action_label}")',
            f'.ant-dropdown-menu-item:has-text("{action_label}")',
            f'.wui-dropdown-menu-item:text-is("{action_label}")',
            f'.wui-dropdown-menu-item:has-text("{action_label}")',
            f'.u-dropdown-menu-item:text-is("{action_label}")',
            f'.u-dropdown-menu-item:has-text("{action_label}")',
            f'[class*="dropdown"][class*="menu"] [class*="item"]:text-is("{action_label}")',
            f'[class*="dropdown"][class*="menu"] [class*="item"]:has-text("{action_label}")',
        ]
    )
    return selectors


def _toolbar_exact_text_selectors() -> list[str]:
    return [
        "button",
        '[role="button"]',
        '[role="menuitem"]',
        ".ant-dropdown-menu-item",
        ".wui-dropdown-menu-item",
        ".u-dropdown-menu-item",
        '[class*="dropdown"][class*="menu"] [class*="item"]',
    ]


def _toolbar_dropdown_item_selectors() -> list[str]:
    return [
        ".ant-dropdown:visible .ant-dropdown-menu-item",
        ".ant-dropdown:visible [role=\"menuitem\"]",
        ".ant-popover:visible .ant-dropdown-menu-item",
        ".ant-popover:visible [role=\"menuitem\"]",
        ".ant-popover:visible [class*=\"item\"]",
        ".wui-dropdown:visible .wui-dropdown-menu-item",
        ".wui-dropdown:visible [role=\"menuitem\"]",
        ".wui-popover:visible .wui-dropdown-menu-item",
        ".wui-popover:visible [role=\"menuitem\"]",
        ".wui-popover:visible [class*=\"item\"]",
        ".u-dropdown:visible .u-dropdown-menu-item",
        ".u-dropdown:visible [role=\"menuitem\"]",
        ".u-popover:visible .u-dropdown-menu-item",
        ".u-popover:visible [role=\"menuitem\"]",
        ".u-popover:visible [class*=\"item\"]",
        '[class*="dropdown"]:visible [class*="menu"] [class*="item"]',
        '[class*="dropdown"]:visible [role="menuitem"]',
        '[class*="popover"]:visible [class*="menu"] [class*="item"]',
        '[class*="popover"]:visible [role="menuitem"]',
        '[class*="popover"]:visible [class*="item"]',
    ]


def _tree_node_selectors(label: str) -> list[str]:
    return [
        f'text="{label}"',
        f'.wui-tree-title:text-is("{label}")',
        f'a.wui-tree-node-content-wrapper:has-text("{label}")',
        f'a:has-text("{label}")',
        f'[title="{label}"]',
        f'span:has-text("{label}")',
        f'div:has-text("{label}")',
    ]


def _tree_closed_switcher_selectors() -> list[str]:
    return [
        "li.wui-tree-treenode-close span.wui-tree-switcher",
        "span.wui-tree-switcher.wui-tree-center_close",
        "span.wui-tree-switcher[class*=\"_close\"]",
    ]


def _table_data_row_selectors() -> list[str]:
    return [
        "tbody tr",
        ".ant-table-tbody tr",
        ".wui-table-tbody tr",
        ".u-table-tbody tr",
        '[role="row"]:has(td)',
        'div[role="row"][aria-rowindex]',
        ".ant-table-row",
    ]


def _table_tree_expand_selectors() -> list[str]:
    return [
        "tbody tr td.wui-table-row-has-expandIcon:has(.uf-triangle-right)",
        "tbody tr td.wui-table-row-has-expandIcon .expand-icon-con:has(.uf-triangle-right)",
        "tbody tr td.wui-table-row-has-expandIcon .switcher-icon:has(.uf-triangle-right)",
        "tbody tr td.wui-table-row-has-expandIcon .uf-triangle-right",
        "tbody tr .wui-table-row-expand-icon-collapsed",
        "tbody tr .ant-table-row-expand-icon-collapsed",
        "tbody tr .u-table-row-expand-icon-collapsed",
        "tbody tr [class*='table-row-expand-icon'][class*='collapsed']",
        "tbody tr [class*='uf-triangle-right']",
        "tbody tr [class*='tree-switcher'][class*='close']",
        "tbody tr [class*='tree-switcher'][class*='collapsed']",
        "tbody tr [class*='switcher'][class*='close']",
        "tbody tr [class*='switcher'][class*='collapsed']",
        "tbody tr button[aria-expanded='false']",
        ".wui-table-row [class*='tree-switcher'][class*='close']",
        ".ant-table-row [class*='tree-switcher'][class*='close']",
        ".wui-table-row [class*='expand-icon'][class*='collapsed']",
        ".ant-table-row [class*='expand-icon'][class*='collapsed']",
        "[role='row'] [class*='tree-switcher'][class*='close']",
        "[role='row'] [class*='expand-icon'][class*='collapsed']",
    ]


def _row_selection_checkbox_selectors() -> list[str]:
    return [
        'td:first-child input[type="checkbox"]',
        'td:first-child [role="checkbox"]',
        'td:first-child label[class*="checkbox"]',
        'td:first-child span[class*="checkbox"]',
        '[class*="selection-column"] input[type="checkbox"]',
        '[class*="selection-column"] [role="checkbox"]',
        '[class*="selection-column"] label[class*="checkbox"]',
        '[class*="selection-column"] span[class*="checkbox"]',
        '[class*="selection"] input[type="checkbox"]',
        '[class*="selection"] [class*="checkbox"]',
        'input[type="checkbox"]',
        '[role="checkbox"]',
    ]


def _row_action_selectors(action_label: str) -> list[str]:
    selectors: list[str] = []
    fieldid = guess_row_action_fieldid(action_label)
    if fieldid:
        selectors.extend(
            [
                f'[fieldid="{fieldid}"]',
                f'[data-fieldid="{fieldid}"]',
            ]
        )
    selectors.extend(
        [
            f'button:has-text("{action_label}")',
            f'[role="button"]:has-text("{action_label}")',
            f'text="{action_label}"',
        ]
    )
    return selectors


def _tab_action_selectors(action_label: str, fieldid: str | None = None) -> list[str]:
    selectors: list[str] = []
    if fieldid:
        selectors.extend(
            [
                f'[fieldid="{fieldid}"]',
                f'[data-fieldid="{fieldid}"]',
            ]
        )
    selectors.extend(
        [
            f'[role="tab"]:text-is("{action_label}")',
            f'[role="tab"]:has-text("{action_label}")',
            f'.ant-tabs-tab:text-is("{action_label}")',
            f'.ant-tabs-tab:has-text("{action_label}")',
            f'.wui-tabs-tab:text-is("{action_label}")',
            f'.wui-tabs-tab:has-text("{action_label}")',
            f'.u-tabs-tab:text-is("{action_label}")',
            f'.u-tabs-tab:has-text("{action_label}")',
            f'[class*="tabs"][class*="tab"]:text-is("{action_label}")',
            f'[class*="Tabs"][class*="Tab"]:text-is("{action_label}")',
            f'[class*="capsule"]:text-is("{action_label}")',
            f'[class*="Capsule"]:text-is("{action_label}")',
            f'[class*="step"]:text-is("{action_label}")',
            f'[class*="Step"]:text-is("{action_label}")',
        ]
    )
    return selectors


def _tab_exact_text_selectors() -> list[str]:
    return [
        '[role="tab"]',
        ".ant-tabs-tab",
        ".wui-tabs-tab",
        ".u-tabs-tab",
        '[class*="tabs"][class*="tab"]',
        '[class*="Tabs"][class*="Tab"]',
        '[class*="capsule"]',
        '[class*="Capsule"]',
        '[class*="step"]',
        '[class*="Step"]',
    ]


def _editable_table_add_row_selectors(label: str = "新增") -> list[str]:
    return [
        f'.ant-table-footer a:text-is("{label}")',
        f'.ant-table-footer button:text-is("{label}")',
        f'.wui-table-footer a:text-is("{label}")',
        f'.wui-table-footer button:text-is("{label}")',
        f'.u-table-footer a:text-is("{label}")',
        f'.u-table-footer button:text-is("{label}")',
        f'tfoot a:text-is("{label}")',
        f'tfoot button:text-is("{label}")',
        f'[class*="table"][class*="footer"] a:text-is("{label}")',
        f'[class*="table"][class*="footer"] button:text-is("{label}")',
        f'table a:text-is("{label}")',
        f'table button:text-is("{label}")',
    ]


def _fieldid_action_selectors(fieldid: str) -> list[str]:
    return [
        f'[fieldid="{fieldid}"]',
        f'[data-fieldid="{fieldid}"]',
        f'button[fieldid="{fieldid}"]',
        f'button[data-fieldid="{fieldid}"]',
        f'[role="button"][fieldid="{fieldid}"]',
        f'[role="button"][data-fieldid="{fieldid}"]',
    ]


def _popup_reference_dialog_selectors() -> list[str]:
    return [
        ".yy-ydf-modal:visible",
        ".ant-modal:visible",
        ".wui-modal:visible",
        ".w-modal:visible",
        ".yy-modal:visible",
        ".u-modal:visible",
        '[role="dialog"]:visible',
        '[class*="modal"]:visible',
        '[class*="Modal"]:visible',
        ".refer-modal:visible",
        ".ref-modal:visible",
        '[class*="refer"]:visible',
        '[class*="ref"]:visible',
    ]


def _popup_reference_trigger_selectors() -> list[str]:
    return [
        "button",
        '[role="button"]',
        ".wui-input-suffix",
        ".ant-input-suffix",
        ".u-input-group-addon",
        ".w-select-arrow",
        ".wui-select-arrow",
        ".ant-select-arrow",
        ".u-select-arrow",
        '[class*="input-suffix"]',
        '[class*="select-arrow"]',
        '[class*="suffix"]',
        '[class*="refer"]',
        '[class*="ref"]',
        '[class*="icon-sousuo"]',
        '[class*="icon-search"]',
        '[class*="icon-fangdajing"]',
        '[class*="icon-canzhao"]',
        '[class*="search"]',
    ]


def _popup_reference_filter_selectors() -> list[str]:
    return [
        'input[placeholder*="搜索"]:not([type="hidden"])',
        'input[placeholder*="关键字"]:not([type="hidden"])',
        'input[placeholder*="过滤"]:not([type="hidden"])',
        'input[placeholder*="查询"]:not([type="hidden"])',
        'input[placeholder*="请输入"]:not([type="hidden"])',
        'input:not([type="hidden"]):not([readonly]):not([type="radio"]):not([type="checkbox"])',
        "textarea",
        '[contenteditable="true"]',
        '[role="textbox"]',
    ]


def _popup_reference_filter_submit_selectors() -> list[str]:
    return [
        ".ant-input-search-button",
        ".wui-input-search-button",
        ".u-input-search-button",
        'button:has(.icon-sousuo)',
        'button:has([class*="search"])',
        '[role="button"]:has(.icon-sousuo)',
        '[role="button"]:has([class*="search"])',
        '[class*="search-icon"]',
        '[class*="SearchIcon"]',
        '[class*="sousuo"]',
        'button:text-is("查询")',
        '[role="button"]:text-is("查询")',
        'button:text-is("搜索")',
        '[role="button"]:text-is("搜索")',
    ]


def _popup_reference_tree_node_selectors(value: str) -> list[str]:
    return [
        f'.wui-tree [title="{value}"]',
        f'.wui-tree-treenode [title="{value}"]',
        f'.wui-select-tree [title="{value}"]',
        f'.wui-select-tree-treenode [title="{value}"]',
        f'.ant-tree [title="{value}"]',
        f'.ant-tree-treenode [title="{value}"]',
        f'.u-tree [title="{value}"]',
        f'[role="tree"] [title="{value}"]',
        f'[role="tree-node"] [title="{value}"]',
        f'[role="treeitem"]:has-text("{value}")',
        f'.wui-tree-node-content-wrapper:has-text("{value}")',
        f'.wui-tree-title:has-text("{value}")',
        f'.wui-tree-treenode:has-text("{value}")',
        f'.wui-select-tree-node-content-wrapper:has-text("{value}")',
        f'.wui-select-tree-title:has-text("{value}")',
        f'.ant-tree-node-content-wrapper:has-text("{value}")',
        f'.ant-tree-title:has-text("{value}")',
        f'.ant-tree-treenode:has-text("{value}")',
        f'.u-tree-node-content-wrapper:has-text("{value}")',
        f'[class*="tree"] [class*="title"]:has-text("{value}")',
        f'[class*="tree"] [class*="node"]:has-text("{value}")',
    ]


def _popup_reference_tree_closed_switcher_selectors() -> list[str]:
    return [
        "span.wui-tree-switcher.wui-tree-center_close",
        "span.wui-tree-switcher[class*='close']",
        ".wui-tree-treenode-close > span.wui-tree-switcher",
        ".wui-tree-treenode-close .wui-tree-switcher",
        ".ant-tree-switcher_close",
        ".ant-tree-treenode-switcher-close .ant-tree-switcher",
        '[class*="tree-switcher"][class*="close"]',
        '[class*="treenode"][class*="close"] [class*="switcher"]',
    ]


def _popup_reference_option_selectors(value: str) -> list[str]:
    return [
        f'[role="option"]:has-text("{value}")',
        f'.wui-select-item-option:has-text("{value}")',
        f'.ant-select-item-option:has-text("{value}")',
        f'.u-select-item-option:has-text("{value}")',
        f'.wui-list-item:has-text("{value}")',
        f'.ant-list-item:has-text("{value}")',
        f'.u-list-item:has-text("{value}")',
        f'[class*="list"] [class*="item"]:has-text("{value}")',
        f'[class*="List"] [class*="Item"]:has-text("{value}")',
        f'[class*="menu"] [class*="item"]:has-text("{value}")',
        f'li:has-text("{value}")',
        f'[title="{value}"]',
    ]


def _popup_reference_table_row_selectors(value: str) -> list[str]:
    return [
        f'tr:has-text("{value}")',
        f'tbody tr:has-text("{value}")',
        f'.wui-table-row:has-text("{value}")',
        f'.ant-table-row:has-text("{value}")',
        f'.u-table-row:has-text("{value}")',
        f'[role="row"]:has-text("{value}")',
        f'[class*="table"] [class*="row"]:has-text("{value}")',
        f'[class*="Table"] [class*="Row"]:has-text("{value}")',
    ]


def _popup_reference_confirm_selectors(label: str = "确定") -> list[str]:
    return [
        f'.ant-modal-footer button:text-is("{label}")',
        f'.wui-modal-footer button:text-is("{label}")',
        f'.w-modal-footer button:text-is("{label}")',
        f'.yy-modal-footer button:text-is("{label}")',
        f'.u-modal-footer button:text-is("{label}")',
        f'[class*="modal-footer"] button:text-is("{label}")',
        f'[class*="ModalFooter"] button:text-is("{label}")',
        f'[class*="footer"] button:text-is("{label}")',
        f'[class*="Footer"] button:text-is("{label}")',
    ]


def _transfer_dialog_dialog_selectors() -> list[str]:
    return [
        ".ant-modal:visible",
        ".wui-modal:visible",
        ".yy-modal:visible",
        ".u-modal:visible",
        '[role="dialog"]:visible',
        '[class*="modal"]:visible',
    ]


def _transfer_dialog_move_to_target_selectors() -> list[str]:
    return [
        '.ant-transfer-operation button:not([disabled]):has(.anticon-right)',
        '.ant-transfer-operation button:not([disabled]):has(.anticon-double-right)',
        '.wui-transfer-operation button:not([disabled]):has([class*="right"])',
        '.u-transfer-operation button:not([disabled]):has([class*="right"])',
        '[class*="transfer-operation"] button:not([disabled]):has([class*="right"])',
        '[class*="transfer-operation"] button:not([disabled])[aria-label*="right"]',
        '[class*="transfer-operation"] button:not([disabled])[title*="右"]',
        '[class*="transfer-operation"] button:not([disabled]):has-text(">")',
        '[class*="transfer-operation"] button:not([disabled]):has-text("移入")',
        '[class*="transfer-operation"] button:not([disabled]):has-text("添加")',
        'button:not([disabled])[aria-label*="right"]',
        'button:not([disabled])[title*="右"]',
        'button:not([disabled]):has-text("移入")',
        'button:not([disabled]):has-text("添加")',
    ]


def _transfer_dialog_confirm_selectors(label: str = "确定") -> list[str]:
    labels = [label]
    if label == "确定":
        labels.append("确认")
    if label == "确认":
        labels.append("确定")
    selectors: list[str] = []
    for item in dict.fromkeys(labels):
        selectors.extend(
            [
                f'button:text-is("{item}")',
                f'[role="button"]:text-is("{item}")',
                f'.ant-modal-footer button:text-is("{item}")',
                f'.wui-modal-footer button:text-is("{item}")',
                f'.yy-modal-footer button:text-is("{item}")',
                f'.u-modal-footer button:text-is("{item}")',
            ]
        )
    return selectors


def guess_row_action_fieldid(action_label: str) -> str:
    return {
        "详情": "xq_btn",
        "编辑": "bj_btn",
        "删除": "sc_btn",
        "启用": "rowBtnEnable",
        "停用": "rowBtnDisable",
    }.get(action_label, "")


def guess_action_fieldid(action_label: str) -> str:
    return {
        "新增": "xz_btn",
        "复制新增": "fzxz_btn",
        "删除": "th_btn",
        "启用": "qy_btn",
        "停用": "ty_btn",
        "导出": "dc_btn",
        "项目导出": "btnExportAndAttach",
        "批量替换": "kzsz_btn",
        "详情": "xq_btn",
        "编辑": "bj_btn",
    }.get(action_label, guess_row_action_fieldid(action_label))
