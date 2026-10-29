from __future__ import annotations

import asyncio
import inspect
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import requests

import ydf_browser.runtime as runtime_module
from ydf_browser.action_completion import ActionCompletion, ActionCompletionRequest, ActionNotification
from ydf_browser.browser_profile import cookie_visible_to_url
from ydf_browser.config import EnvironmentConfig
from ydf_browser.models import BoundElement, ElementCandidate, MenuTarget, PageManifest, PageMeta, Region, RuntimeElement
from ydf_browser.observation import ObservationSession
from ydf_browser.popup_reference import PopupReferenceResult
from ydf_browser.request_forwarding import parse_request_forward_rule, rewrite_forwarded_url
from ydf_browser.runtime import (
    FixtureRuntime,
    PlaywrightRuntime,
    build_query_expand_selectors,
    build_query_choice_selectors,
    build_tree_closed_switcher_selectors,
    build_table_tree_expand_selectors,
    build_row_hover_selectors,
    build_row_action_selectors,
    build_row_selection_checkbox_selectors,
    build_table_data_row_selectors,
    build_tab_action_selectors,
    build_tab_exact_text_selectors,
    build_editable_table_add_row_selectors,
    build_toolbar_action_selectors,
    build_toolbar_dropdown_item_selectors,
    build_toolbar_more_selectors,
    build_transfer_dialog_confirm_selectors,
    build_transfer_dialog_dialog_selectors,
    build_transfer_dialog_move_to_target_selectors,
    build_dialog_button_selectors,
    build_template_download_link_selectors,
    build_query_action_selectors,
    build_tree_node_selectors,
    _request_duration_ms,
    _response_body_size,
    _EDITABLE_TABLE_ADD_ROW_SCRIPT,
    _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT,
    _TREE_SHORTCUT_TARGET_SCRIPT,
    _TABLE_FIELDID_ROOT_SELECTOR_SCRIPT,
    _TABLE_HEADERS_SCRIPT,
    _TABLE_SELECTION_ROOT_SELECTOR_SCRIPT,
    _TABLE_COLUMN_VALUES_SCRIPT,
    _TABLE_ROW_VALUES_SCRIPT,
    _SCROLL_TABLE_HEADERS_RIGHT_SCRIPT,
    _extract_import_failure_message,
    _iter_editable_table_values,
    _leading_code,
    _normalize_import_filename,
    _resolve_import_file,
)
from ydf_browser.table_scope import (
    ResolvedTableScope,
    RuntimeTableScopeAdapter,
    TableScopeError,
    TableScopeRequest,
    TableScopeResolver,
)
from ydf_browser.template_parser import build_page_manifest
from ydf_browser.template_restoration import RuntimeTemplateAdapter, TemplateRestoration


def test_iter_editable_table_values_keeps_duplicate_column_items() -> None:
    assert list(_iter_editable_table_values({"备注": "测试"})) == [("备注", "备注", "测试")]
    assert list(
        _iter_editable_table_values(
            [
                {"key": "当年财政拨款(万元)#1", "column": "当年财政拨款(万元)", "value": 1},
                {"key": "当年财政拨款(万元)#2", "column": "当年财政拨款(万元)", "value": 2},
            ]
        )
    ) == [
        ("当年财政拨款(万元)#1", "当年财政拨款(万元)", 1),
        ("当年财政拨款(万元)#2", "当年财政拨款(万元)", 2),
    ]


class _FakeWorkflowFrame:
    def __init__(self, candidates: list[dict[str, Any]]) -> None:
        self.candidates = candidates
        self.evaluate_calls: list[str] = []

    def evaluate(self, script: str, *_args):
        self.evaluate_calls.append(script)
        return self.candidates


class _FakeWorkflowPage:
    def __init__(self, frames: list[_FakeWorkflowFrame]) -> None:
        self.frames = frames
        self.waits: list[int] = []

    def wait_for_timeout(self, timeout: int) -> None:
        self.waits.append(timeout)


class _FakeWorkflowAction:
    def __init__(self, on_click=None) -> None:
        self.clicked = False
        self._on_click = on_click

    def count(self) -> int:
        return 1

    def is_visible(self, timeout: int = 0) -> bool:
        return True

    def inner_text(self, timeout: int = 0) -> str:
        return "查看详情"

    def get_attribute(self, _name: str, timeout: int = 0) -> str:
        return ""

    def click(self, timeout: int = 0, **_kwargs) -> None:
        self.clicked = True
        if self._on_click is not None:
            self._on_click()


class _FakeWorkflowRoot:
    def __init__(self, action: _FakeWorkflowAction) -> None:
        self.visible = True
        self.action = action

    def count(self) -> int:
        return 1

    def is_visible(self, timeout: int = 0) -> bool:
        return self.visible

    def locator(self, _selector: str):
        return _FakeWorkflowLocatorGroup([self.action])


class _FakeWorkflowLocatorGroup:
    def __init__(self, matches: list[Any]) -> None:
        self.matches = matches

    @property
    def first(self):
        return self.matches[0]

    def count(self) -> int:
        return len(self.matches)

    def nth(self, index: int):
        return self.matches[index]


class _FakeWorkflowActionFrame:
    def __init__(self) -> None:
        self.root: _FakeWorkflowRoot | None = None
        self.details_visible = False
        self.details = [
            {
                "document_code": "CGJH-001",
                "error_reason": "预算不足",
                "error_code": "BUDGET-001",
            }
        ]
        action = _FakeWorkflowAction(on_click=self._open_details)
        self.root = _FakeWorkflowRoot(action)
        self.candidate = {
            "status": "observed",
            "selector": '[data-ydf-browser-workflow-result="result-action"]',
            "semantics": {"message": "提交请求已执行完毕，部分失败！"},
            "counts": {"total": 1, "succeeded": 0, "failed": 1},
            "actions": {
                "confirm": '[data-ydf-browser-workflow-result-action-target="confirm-action"]',
                "details": '[data-ydf-browser-workflow-result-action-target="details-action"]',
            },
        }
        self.candidate["actions"]["details"] = self.candidate["actions"]["details"]

    def _open_details(self) -> None:
        self.details_visible = True

    def evaluate(self, script: str, *_args):
        if script == runtime_module._WORKFLOW_RESULT_SCAN_SCRIPT:
            return [self.candidate]
        if script == runtime_module._WORKFLOW_RESULT_DETAILS_SCAN_SCRIPT:
            if not self.details_visible:
                return []
            return [{"status": "observed", "details": self.details}]
        return None

    def locator(self, selector: str):
        if selector == self.candidate["selector"]:
            return _FakeWorkflowLocatorGroup([self.root])
        if selector == self.candidate["actions"]["details"]:
            return _FakeWorkflowLocatorGroup([self.root.action])
        if selector == self.candidate["actions"]["confirm"]:
            return _FakeWorkflowLocatorGroup([_FakeWorkflowAction(on_click=lambda: setattr(self.root, "visible", False))])
        return _FakeWorkflowLocatorGroup([])


class _FakeWorkflowActionPage:
    def __init__(self, frame: _FakeWorkflowActionFrame) -> None:
        self.frames = [frame]
        self.waits: list[int] = []

    def wait_for_timeout(self, timeout: int) -> None:
        self.waits.append(timeout)


def test_playwright_runtime_opens_and_collects_workflow_result_details() -> None:
    frame = _FakeWorkflowActionFrame()
    runtime = object.__new__(PlaywrightRuntime)
    runtime._page = _FakeWorkflowActionPage(frame)
    runtime._last_workflow_result_snapshot = {**frame.candidate, "frame_index": 0}

    result = runtime.open_workflow_result_details(timeout_ms=500)

    assert result["details"] == frame.details
    assert frame.root.action.clicked is True


def test_playwright_runtime_confirms_workflow_result_only_after_root_disappears() -> None:
    frame = _FakeWorkflowActionFrame()
    runtime = object.__new__(PlaywrightRuntime)
    runtime._page = _FakeWorkflowActionPage(frame)
    runtime._last_workflow_result_snapshot = {**frame.candidate, "frame_index": 0}

    result = runtime.confirm_workflow_result(timeout_ms=500)

    assert result["closed"] is True
    assert frame.root.visible is False


def test_playwright_runtime_observes_workflow_result_from_combined_evidence() -> None:
    runtime = object.__new__(PlaywrightRuntime)
    runtime._page = _FakeWorkflowPage(
        [
            _FakeWorkflowFrame(
                [
                    {
                        "status": "observed",
                        "selector": '[data-ydf-browser-workflow-result="result-1"]',
                        "semantics": {"message": "提交请求已执行完毕，部分失败！"},
                        "counts": {"total": 2, "succeeded": 1, "failed": 1},
                        "actions": {"confirm": "确认", "details": "查看详情"},
                    }
                ]
            )
        ]
    )

    result = runtime.observe_workflow_result(timeout_ms=0)

    assert result is not None
    assert result["status"] == "observed"
    assert result["frame_index"] == 0
    assert result["counts"] == {"total": 2, "succeeded": 1, "failed": 1}
    assert result["semantics"]["message"] == "提交请求已执行完毕，部分失败！"


def test_playwright_runtime_does_not_promote_unrelated_error_content() -> None:
    runtime = object.__new__(PlaywrightRuntime)
    runtime._page = _FakeWorkflowPage(
        [
            _FakeWorkflowFrame(
                [
                    {
                        "status": "candidate",
                        "class_name": "error-content",
                        "semantic": False,
                        "text": "上传失败: 文件格式不正确",
                        "counts": {},
                        "actions": {},
                    }
                ]
            )
        ]
    )

    assert runtime.observe_workflow_result(timeout_ms=0) is None


def test_playwright_runtime_reports_unparseable_workflow_result_evidence() -> None:
    runtime = object.__new__(PlaywrightRuntime)
    runtime._page = _FakeWorkflowPage(
        [
            _FakeWorkflowFrame(
                [
                    {
                        "status": "evidence_unavailable",
                        "selector": '[data-ydf-browser-workflow-result="result-2"]',
                        "semantic": True,
                        "semantics": {"message": "提交请求已执行完毕，部分失败！"},
                        "text": "提交请求已执行完毕，部分失败！",
                        "counts": {},
                        "actions": {"confirm": "确认"},
                        "reason": "统计字段无法解析",
                    }
                ]
            )
        ]
    )

    result = runtime.observe_workflow_result(timeout_ms=0)

    assert result is not None
    assert result["status"] == "evidence_unavailable"
    assert result["reason"] == "统计字段无法解析"


class _FakePage:
    def __init__(self, on_close=None) -> None:
        self.goto_calls: list[str] = []
        self.event_handlers: dict[str, object] = {}
        self.url = ""
        self.frames = []
        self.closed = False
        self._on_close = on_close

    def on(self, event_name: str, handler) -> None:
        self.event_handlers[event_name] = handler

    def goto(self, url: str) -> None:
        self.goto_calls.append(url)
        self.url = url

    def wait_for_load_state(self, *_args, **_kwargs) -> None:
        return

    def wait_for_timeout(self, *_args, **_kwargs) -> None:
        return

    def title(self) -> str:
        return ""

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self._on_close is not None:
            self._on_close(self)


class _FakeMatch:
    def __init__(self, visible: bool) -> None:
        self.visible = visible
        self.clicked = False

    def is_visible(self, timeout: int = 0) -> bool:
        return self.visible

    def click(self, timeout: int = 0) -> None:
        self.clicked = True


class _FakeLocatorGroup:
    def __init__(self, matches: list[_FakeMatch]) -> None:
        self.matches = matches

    @property
    def first(self) -> _FakeMatch:
        return self.matches[0]

    def count(self) -> int:
        return len(self.matches)

    def nth(self, index: int) -> _FakeMatch:
        return self.matches[index]


class _FakeFormCheckboxRoot:
    def __init__(self, *, checked: bool | None) -> None:
        self.checked = checked

    def evaluate(self, script: str, *_args):
        if "switchSelector" in script:
            return False
        if "radioSelector" in script:
            return False
        if "checkboxSelector" in script:
            return self.checked
        return ""


class _FakeInputValueLocator:
    def __init__(self, value: str) -> None:
        self.value = value

    def input_value(self) -> str:
        return self.value

    def text_content(self) -> str:
        return ""


class _FakeRowCheckbox:
    def __init__(self) -> None:
        self.clicked = False

    def count(self) -> int:
        return 1

    def evaluate(self, _script: str) -> str:
        return "checked" if self.clicked else "unchecked"

    def click(self, timeout: int = 0, force: bool = False, **_kwargs) -> None:
        self.clicked = True


class _FakeUnconfirmedRowCheckbox:
    def __init__(self) -> None:
        self.click_count = 0

    def count(self) -> int:
        return 1

    def evaluate(self, _script: str) -> str:
        return "unchecked"

    def click(self, timeout: int = 0, force: bool = False) -> None:
        self.click_count += 1


class _FakeRowCheckboxGroup:
    def __init__(self, checkbox: _FakeRowCheckbox | _FakeUnconfirmedRowCheckbox | None) -> None:
        self.checkbox = checkbox

    @property
    def first(self) -> _FakeRowCheckbox | _FakeUnconfirmedRowCheckbox:
        if self.checkbox is None:
            raise IndexError("no checkbox")
        return self.checkbox

    def count(self) -> int:
        return 1 if self.checkbox is not None else 0


class _FakeMissingRowCheckboxGroup:
    @property
    def first(self):
        raise IndexError("no checkbox")

    def count(self) -> int:
        return 0


class _FakeAlignedCheckboxPage:
    def __init__(self, checkbox: _FakeRowCheckbox) -> None:
        self.checkbox = checkbox
        self.selectors: list[str] = []

    def locator(self, selector: str):
        self.selectors.append(selector)
        return _FakeRowCheckboxGroup(self.checkbox)


class _FakeAlignedCheckboxRow:
    def __init__(self, marker: str | None, *, selected_after_click: bool = True) -> None:
        self.marker = marker
        self.clicked = False
        self.selected_after_click = selected_after_click
        self.click_kwargs: dict[str, object] = {}

    def locator(self, _selector: str) -> _FakeMissingRowCheckboxGroup:
        return _FakeMissingRowCheckboxGroup()

    def evaluate(self, _script: str, marker: str | None = None):
        if marker is None:
            return self.clicked and self.selected_after_click
        return f'[data-ydf-browser-row-checkbox-target="{marker}"]' if self.marker is not None else ""

    def click(self, **_kwargs) -> None:
        self.clicked = True
        self.click_kwargs = dict(_kwargs)


class _FakeRepeatedCheckboxRow:
    def __init__(self) -> None:
        self.checkbox = _FakeUnconfirmedRowCheckbox()

    def locator(self, _selector: str) -> _FakeRowCheckboxGroup:
        return _FakeRowCheckboxGroup(self.checkbox)

    def evaluate(self, *args) -> str:
        if len(args) > 1:
            return ""
        return "unchecked"


class _FakeActionLocator:
    def __init__(self, text: str, *, in_table: bool = False) -> None:
        self.text = text
        self.in_table = in_table
        self.scroll_calls = 0
        self.clicked = False

    def is_visible(self, timeout: int = 0) -> bool:
        return True

    def bounding_box(self, timeout: int = 0) -> dict[str, int]:
        return {"x": 10, "y": 100, "width": 80, "height": 32}

    def scroll_into_view_if_needed(self, timeout: int = 0) -> None:
        self.scroll_calls += 1

    def evaluate(self, _script: str):
        if "Boolean(node.closest" in _script:
            return self.in_table
        if "scrollIntoView" in _script:
            self.scroll_calls += 1
            return None
        return True

    def inner_text(self, timeout: int = 0) -> str:
        return self.text

    def click(self, **_kwargs) -> None:
        self.clicked = True


class _FakeActionLocatorGroup:
    def __init__(self, matches: list[_FakeActionLocator]) -> None:
        self.matches = matches

    @property
    def first(self) -> _FakeActionLocator:
        return self.matches[0]

    def count(self) -> int:
        return len(self.matches)

    def nth(self, index: int) -> _FakeActionLocator:
        return self.matches[index]


class _FakeActionPage:
    frames: list[object] = []

    def __init__(self, selectors: dict[str, list[_FakeActionLocator]]) -> None:
        self.selectors = selectors

    def locator(self, selector: str) -> _FakeActionLocatorGroup:
        if " >> nth=" in selector:
            selector, raw_index = selector.rsplit(" >> nth=", 1)
            matches = self.selectors.get(selector, [])
            index = int(raw_index)
            return _FakeActionLocatorGroup(matches[index : index + 1])
        return _FakeActionLocatorGroup(self.selectors.get(selector, []))

    def wait_for_timeout(self, *_args, **_kwargs) -> None:
        return


class _FakeSelectableTableRow:
    def __init__(
        self,
        *,
        visible: bool,
        selectable: bool = True,
        text: str = "1 数据行",
        selected_after_click: bool = True,
        receives_pointer: bool = True,
    ) -> None:
        self.visible = visible
        self.text = text
        self.clicked = False
        self.selected_after_click = selected_after_click
        self.receives_pointer = receives_pointer
        self.checkbox = _FakeRowCheckbox() if selectable else None

    def is_visible(self, timeout: int = 0) -> bool:
        return self.visible

    def inner_text(self, timeout: int = 0) -> str:
        return self.text

    def locator(self, _selector: str) -> _FakeRowCheckboxGroup:
        return _FakeRowCheckboxGroup(self.checkbox)

    def evaluate(self, script: str) -> bool:
        if "elementFromPoint" in script:
            return self.visible and self.receives_pointer
        if "querySelector('td" in script:
            compact_text = "".join(self.text.split())
            if not self.text or "暂无数据" in self.text or "点击上方查询条件搜索数据" in self.text:
                return False
            return not (
                self.text.startswith(("小计", "合计", "汇总", "总计"))
                or compact_text.startswith(("小计", "合计", "汇总", "总计"))
            )
        return self.clicked and self.selected_after_click

    def click(self, timeout: int = 0, force: bool = False, **_kwargs) -> None:
        self.clicked = True


class _FakeSelectableTablePage:
    def __init__(self, rows_by_selector: dict[str, list[_FakeSelectableTableRow]]) -> None:
        self.rows_by_selector = rows_by_selector
        self.waits: list[int] = []

    def locator(self, selector: str) -> _FakeLocatorGroup:
        return _FakeLocatorGroup(self.rows_by_selector.get(selector, []))

    def wait_for_timeout(self, timeout: int) -> None:
        self.waits.append(timeout)


class _FakeCompositeMatchTableContext:
    def __init__(self, first_row: _FakeSelectableTableRow, target_row: _FakeSelectableTableRow) -> None:
        self.first_row = first_row
        self.target_row = target_row
        self.payloads: list[dict[str, object]] = []

    def evaluate(self, _script: str, payload: dict[str, object]) -> dict[str, str]:
        self.payloads.append(payload)
        raw_match = payload.get("match")
        conditions = raw_match.get("conditions") if isinstance(raw_match, dict) else None
        if isinstance(conditions, list) and len(conditions) == 2:
            return {"__selector": '[data-row="target"]'}
        return {"__selector": '[data-row="first"]'}

    def locator(self, selector: str) -> _FakeLocatorGroup:
        if selector == '[data-row="target"]':
            return _FakeLocatorGroup([self.target_row])
        if selector == '[data-row="first"]':
            return _FakeLocatorGroup([self.first_row])
        return _FakeLocatorGroup([])


class _FakeHeaderCheckbox:
    def __init__(self, state: str = "unchecked", visible: bool = True) -> None:
        self.state = state
        self.visible = visible
        self.clicks: list[dict[str, int | bool]] = []

    def is_visible(self, timeout: int = 0) -> bool:
        return self.visible

    def evaluate(self, _script: str) -> str:
        return self.state

    def click(self, timeout: int = 0, force: bool = False) -> None:
        self.clicks.append({"timeout": timeout, "force": force})


class _FakeScopedSelectableTablePage(_FakeSelectableTablePage):
    def __init__(
        self,
        rows_by_selector: dict[str, list[_FakeSelectableTableRow]],
        scoped_rows_by_selector: dict[str, list[_FakeSelectableTableRow]],
        fieldid: str | None = None,
        root_info: dict | None = None,
    ) -> None:
        super().__init__(rows_by_selector)
        self.scoped_context = _FakeSelectableTablePage(scoped_rows_by_selector)
        self.evaluated_payloads: list[dict] = []
        self.root_info = dict(root_info or {})
        self.root_selectors = {'[data-ydf-browser-table-selection-root="marker"]'}
        if fieldid:
            self.root_selectors.add(runtime_module._fieldid_selector(fieldid))

    def evaluate(self, _script: str, _payload: dict) -> dict[str, str]:
        self.evaluated_payloads.append(_payload)
        return {"selector": '[data-ydf-browser-table-selection-root="marker"]', **self.root_info}

    def locator(self, selector: str) -> _FakeLocatorGroup:
        if selector in self.root_selectors:
            return _FakeLocatorGroup([self.scoped_context])
        return super().locator(selector)


class _FakeForegroundFieldidTablePage(_FakeSelectableTablePage):
    def __init__(
        self,
        background_rows_by_selector: dict[str, list[_FakeSelectableTableRow]],
        foreground_rows_by_selector: dict[str, list[_FakeSelectableTableRow]],
    ) -> None:
        super().__init__({})
        self.background_context = _FakeSelectableTablePage(background_rows_by_selector)
        self.foreground_context = _FakeSelectableTablePage(foreground_rows_by_selector)
        self.evaluated_payloads: list[dict] = []

    def evaluate(self, script: str, payload: dict) -> dict[str, object]:
        self.evaluated_payloads.append(payload)
        if "receivableRowCount" in script and "b.receivableRows - a.receivableRows" in script:
            return {
                "selector": '[data-ydf-browser-table-selection-root="foreground"]',
                "fieldid": "table1_drag",
                "source": "fieldid_drag",
                "rows": 1,
                "selectableRows": 0,
                "receivableRows": 1,
            }
        return {
            "selector": '[data-ydf-browser-table-selection-root="background"]',
            "fieldid": "table1_drag",
            "source": "fieldid_drag",
            "rows": 5,
            "selectableRows": 5,
            "receivableRows": 0,
        }

    def locator(self, selector: str) -> _FakeLocatorGroup:
        if selector == '[data-ydf-browser-table-selection-root="background"]':
            return _FakeLocatorGroup([self.background_context])
        if selector == '[data-ydf-browser-table-selection-root="foreground"]':
            return _FakeLocatorGroup([self.foreground_context])
        return super().locator(selector)


class _FakeFieldidFallbackTablePage(_FakeSelectableTablePage):
    def __init__(
        self,
        fieldid_rows_by_selector: dict[str, list[_FakeSelectableTableRow]],
        named_rows_by_selector: dict[str, list[_FakeSelectableTableRow]],
    ) -> None:
        super().__init__({})
        self.fieldid_context = _FakeSelectableTablePage(fieldid_rows_by_selector)
        self.named_context = _FakeSelectableTablePage(named_rows_by_selector)

    def evaluate(self, script: str, payload: dict) -> dict[str, object]:
        if script == _TABLE_FIELDID_ROOT_SELECTOR_SCRIPT:
            return {
                "selector": '[data-ydf-browser-table-selection-root="fieldid"]',
                "fieldid": "detail_table",
                "source": "fieldid",
                "rows": 0,
                "selectableRows": 0,
            }
        if script == _TABLE_SELECTION_ROOT_SELECTOR_SCRIPT:
            return {
                "selector": '[data-ydf-browser-table-selection-root="name"]',
                "source": "table-name",
                "rows": 1,
                "selectableRows": 1,
            }
        return {"selector": ""}

    def locator(self, selector: str) -> _FakeLocatorGroup:
        if selector == '[data-ydf-browser-table-selection-root="fieldid"]':
            return _FakeLocatorGroup([self.fieldid_context])
        if selector == '[data-ydf-browser-table-selection-root="name"]':
            return _FakeLocatorGroup([self.named_context])
        return super().locator(selector)


class _FakeHeaderCollectionContext:
    def __init__(self, header_snapshots: list[list[str]], scroll_results: list[bool] | None = None) -> None:
        self.header_snapshots = [list(snapshot) for snapshot in header_snapshots]
        self.scroll_results = list(scroll_results or [])
        self.calls: list[dict[str, object]] = []
        self.waits: list[int] = []

    @property
    def first(self) -> "_FakeHeaderCollectionContext":
        return self

    def evaluate(self, script: str, payload=None):
        self.calls.append({"script": script, "payload": payload})
        if script == _TABLE_HEADERS_SCRIPT:
            return self.header_snapshots.pop(0) if self.header_snapshots else []
        if script == _SCROLL_TABLE_HEADERS_RIGHT_SCRIPT:
            if isinstance(payload, dict) and payload.get("rewindToLeft"):
                return False
            return self.scroll_results.pop(0) if self.scroll_results else False
        return None

    def wait_for_timeout(self, timeout: int) -> None:
        self.waits.append(timeout)


class _FakeHeaderCollectionPage(_FakeHeaderCollectionContext):
    def __init__(
        self,
        header_snapshots: list[list[str]],
        scroll_results: list[bool] | None = None,
        scoped_context: _FakeHeaderCollectionContext | None = None,
    ) -> None:
        super().__init__(header_snapshots, scroll_results)
        self.scoped_context = scoped_context
        self.evaluated_payloads: list[dict] = []

    def evaluate(self, script: str, payload=None):
        if script == _TABLE_FIELDID_ROOT_SELECTOR_SCRIPT:
            self.evaluated_payloads.append(payload)
            return {"selector": '[data-ydf-browser-table-selection-root="marker"]'}
        return super().evaluate(script, payload)

    def locator(self, selector: str) -> _FakeLocatorGroup:
        if selector == '[data-ydf-browser-table-selection-root="marker"]' and self.scoped_context is not None:
            return _FakeLocatorGroup([self.scoped_context])
        return _FakeLocatorGroup([])


class _FakeHeaderScrollRestorePage(_FakeHeaderCollectionPage):
    def __init__(self, header_snapshots: list[list[str]], scroll_results: list[bool], scroll_left: int) -> None:
        super().__init__(header_snapshots, scroll_results)
        self.scroll_left = scroll_left
        self.initial_scroll_left = scroll_left

    def evaluate(self, script: str, payload=None):
        if script == _SCROLL_TABLE_HEADERS_RIGHT_SCRIPT:
            if isinstance(payload, dict) and payload.get("restoreScrollLeft"):
                self.calls.append({"script": script, "payload": payload})
                self.scroll_left = self.initial_scroll_left
                return True
            if isinstance(payload, dict) and payload.get("rewindToLeft"):
                self.calls.append({"script": script, "payload": payload})
                moved = self.scroll_left > 0
                self.scroll_left = 0
                return moved
            self.scroll_left = 100
        return super().evaluate(script, payload)


class _FakeTableValueCollectionContext:
    def __init__(self, result) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []
        self.waits: list[int] = []

    @property
    def first(self) -> "_FakeTableValueCollectionContext":
        return self

    def evaluate(self, script: str, payload=None):
        self.calls.append({"script": script, "payload": payload})
        if script in {_TABLE_COLUMN_VALUES_SCRIPT, _TABLE_ROW_VALUES_SCRIPT}:
            return self.result
        if script in {_SCROLL_TABLE_HEADERS_RIGHT_SCRIPT, runtime_module._SCROLL_TABLE_RIGHT_SCRIPT}:
            return False
        return None

    def wait_for_timeout(self, timeout: int) -> None:
        self.waits.append(timeout)


class _FakeTableValueCollectionPage(_FakeTableValueCollectionContext):
    frames: list[object] = []

    def __init__(self, scoped_context: _FakeTableValueCollectionContext) -> None:
        super().__init__([])
        self.scoped_context = scoped_context
        self.evaluated_payloads: list[dict] = []

    def evaluate(self, script: str, payload=None):
        if script == _TABLE_FIELDID_ROOT_SELECTOR_SCRIPT:
            self.evaluated_payloads.append(payload)
            return {"selector": '[data-ydf-browser-table-selection-root="marker"]'}
        return super().evaluate(script, payload)

    def locator(self, selector: str) -> _FakeLocatorGroup:
        if selector == '[data-ydf-browser-table-selection-root="marker"]':
            return _FakeLocatorGroup([self.scoped_context])
        return _FakeLocatorGroup([])


class _FakeTableCellLinkClickContext:
    def __init__(self, result) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []
        self.waits: list[int] = []

    @property
    def first(self) -> "_FakeTableCellLinkClickContext":
        return self

    def evaluate(self, script: str, payload=None):
        self.calls.append({"script": script, "payload": payload})
        if script in {_SCROLL_TABLE_HEADERS_RIGHT_SCRIPT, runtime_module._SCROLL_TABLE_RIGHT_SCRIPT}:
            return False
        return self.result

    def wait_for_timeout(self, timeout: int) -> None:
        self.waits.append(timeout)


class _FakeTableCellLinkClickPage(_FakeTableValueCollectionPage):
    def __init__(self, scoped_context: _FakeTableCellLinkClickContext) -> None:
        self.scoped_context = scoped_context
        self.evaluated_payloads: list[dict] = []
        self.frames = []

    def wait_for_timeout(self, timeout: int) -> None:
        self.scoped_context.wait_for_timeout(timeout)


class _FakeRegionMatch:
    def __init__(self, visible: bool, in_viewport: bool) -> None:
        self.visible = visible
        self.in_viewport = in_viewport

    def is_visible(self, timeout: int = 0) -> bool:
        return self.visible

    def evaluate(self, _script: str) -> bool:
        return self.in_viewport


class _FakeRegionPage:
    def __init__(self, matches_by_selector: dict[str, list[_FakeRegionMatch]]) -> None:
        self.matches_by_selector = matches_by_selector
        self.frames: list["_FakeRegionPage"] = []

    def locator(self, selector: str) -> _FakeLocatorGroup:
        return _FakeLocatorGroup(self.matches_by_selector.get(selector, []))


def test_playwright_runtime_region_visibility_requires_viewport_intersection() -> None:
    runtime = object.__new__(PlaywrightRuntime)
    runtime._page = _FakeRegionPage(
        {
            '[fieldid="tree_top"], [data-fieldid="tree_top"]': [_FakeRegionMatch(True, True)],
            '[fieldid="tree_top_1"], [data-fieldid="tree_top_1"]': [_FakeRegionMatch(True, False)],
        }
    )

    assert runtime.is_region_visible("tree_top") is True
    assert runtime.is_region_visible("tree_top_1") is False


class _FakeTableScopeEvidencePage:
    frames: list = []

    def evaluate(self, script: str, arg=None):
        if script == runtime_module._TABLE_SCOPE_FOREGROUND_EXISTS_SCRIPT:
            return True
        if script == runtime_module._TABLE_SCOPE_TOKEN_VALID_SCRIPT:
            return arg == "dialog-token"
        if script == runtime_module._TABLE_SCOPE_REGION_EVIDENCE_SCRIPT:
            if arg["fieldid"] == "dialog_table_table":
                return {
                    "exists": True,
                    "visible": True,
                    "interactive": True,
                    "inForeground": True,
                    "columns": ["项目代码", "金额"],
                    "token": "dialog-token",
                }
            if arg["fieldid"] == "background_table":
                return {
                    "exists": True,
                    "visible": True,
                    "interactive": True,
                    "inForeground": False,
                    "columns": ["金额"],
                    "token": "background-token",
                }
            return {"exists": False}
        raise AssertionError("unexpected script")


class _FakeNavigatingTableScopePage:
    def __init__(self, stable_frame) -> None:
        self.frames = [stable_frame]

    def evaluate(self, _script: str, _arg=None):
        raise RuntimeError(
            "Frame.evaluate: Execution context was destroyed, most likely because of a navigation"
        )


class _FakeSplitTableScopeEvidencePage:
    frames: list = []

    def evaluate(self, script: str, arg=None):
        if script == runtime_module._TABLE_SCOPE_FOREGROUND_EXISTS_SCRIPT:
            return False
        if script == runtime_module._TABLE_SCOPE_REGION_EVIDENCE_SCRIPT:
            if arg["fieldid"] != "bg_table":
                return []
            return [
                {
                    "exists": True,
                    "visible": True,
                    "interactive": True,
                    "inForeground": False,
                    "columns": ["收入分成比例%", "说明"],
                    "rowCount": 0,
                    "area": 400,
                    "token": "header-root",
                },
                {
                    "exists": True,
                    "visible": True,
                    "interactive": True,
                    "inForeground": False,
                    "columns": [],
                    "rowCount": 3,
                    "area": 1200,
                    "token": "data-root",
                },
            ]
        raise AssertionError("unexpected script")


class _FakeHeaderlessTableScopeEvidencePage:
    frames: list = []

    def evaluate(self, script: str, arg=None):
        if script == runtime_module._TABLE_SCOPE_FOREGROUND_EXISTS_SCRIPT:
            return False
        if script == runtime_module._TABLE_SCOPE_REGION_EVIDENCE_SCRIPT:
            if arg["fieldid"] != "bg_table":
                return []
            return [
                {
                    "exists": True,
                    "visible": True,
                    "interactive": True,
                    "inForeground": False,
                    "columns": [],
                    "rowCount": 3,
                    "area": 1200,
                    "token": "headerless-root",
                }
            ]
        raise AssertionError("unexpected script")


class _FakeDuplicateHeaderTableScopeEvidencePage:
    frames: list = []

    def evaluate(self, script: str, arg=None):
        if script == runtime_module._TABLE_SCOPE_FOREGROUND_EXISTS_SCRIPT:
            return False
        if script == runtime_module._TABLE_SCOPE_REGION_EVIDENCE_SCRIPT:
            if arg["fieldid"] != "quantity_table":
                return []
            return [
                {
                    "exists": True,
                    "visible": True,
                    "interactive": True,
                    "inForeground": False,
                    "columns": ["*数量", "*数量"],
                    "rowCount": 1,
                    "area": 1200,
                    "token": "duplicate-header-root",
                }
            ]
        raise AssertionError("unexpected script")


class _FakeSplitSameNameHeaderIdentityPage:
    frames: list = []

    def __init__(self, identities: tuple[str, str]) -> None:
        self.identities = identities

    def evaluate(self, script: str, arg=None):
        if script == runtime_module._TABLE_SCOPE_FOREGROUND_EXISTS_SCRIPT:
            return False
        if script == runtime_module._TABLE_SCOPE_REGION_EVIDENCE_SCRIPT:
            if arg["fieldid"] != "quantity_table":
                return []
            return [
                {
                    "exists": True,
                    "visible": True,
                    "interactive": True,
                    "inForeground": False,
                    "columns": ["数量"],
                    "columnHeaders": [{"text": "数量", "identity": identity}],
                    "rowCount": 1,
                    "rowTexts": ["1"],
                    "area": 1200,
                    "token": f"root-{index}",
                }
                for index, identity in enumerate(self.identities)
            ]
        raise AssertionError("unexpected script")


class _FakeCrossForegroundSplitTableScopeEvidencePage:
    frames: list = []

    def evaluate(self, script: str, arg=None):
        if script == runtime_module._TABLE_SCOPE_FOREGROUND_EXISTS_SCRIPT:
            return True
        if script == runtime_module._TABLE_SCOPE_REGION_EVIDENCE_SCRIPT:
            if arg["fieldid"] != "bg_table":
                return []
            return [
                {
                    "exists": True,
                    "visible": True,
                    "interactive": True,
                    "inForeground": False,
                    "columns": ["收入分成比例%", "说明"],
                    "rowCount": 0,
                    "area": 400,
                    "token": "background-header-root",
                },
                {
                    "exists": True,
                    "visible": True,
                    "interactive": True,
                    "inForeground": True,
                    "columns": [],
                    "rowCount": 3,
                    "area": 1200,
                    "token": "foreground-data-root",
                },
            ]
        raise AssertionError("unexpected script")


class _FakeTableScopeAliasEvidencePage:
    frames: list = []

    def evaluate(self, script: str, arg=None):
        if script == runtime_module._TABLE_SCOPE_FOREGROUND_EXISTS_SCRIPT:
            return False
        if script == runtime_module._TABLE_SCOPE_REGION_EVIDENCE_SCRIPT:
            if arg["fieldid"] == "bg_table":
                return [{"exists": True, "visible": True, "interactive": True, "columns": ["项目分类编码"], "token": "background-root"}]
            if arg["fieldid"] == "bg_table_table":
                return [{"exists": True, "visible": True, "interactive": True, "columns": ["收入分成比例%", "说明"], "token": "detail-root"}]
            return []
        raise AssertionError("unexpected script")


class _FakeDistinctPhysicalTableScopeEvidencePage:
    frames: list = []

    def evaluate(self, script: str, arg=None):
        if script == runtime_module._TABLE_SCOPE_FOREGROUND_EXISTS_SCRIPT:
            return False
        if script == runtime_module._TABLE_SCOPE_REGION_EVIDENCE_SCRIPT:
            if arg["fieldid"] != "bg_table":
                return []
            return [
                {
                    "exists": True,
                    "visible": True,
                    "interactive": True,
                    "inForeground": False,
                    "columns": ["项目代码", "金额"],
                    "rowCount": 1,
                    "rowTexts": ["A 100"],
                    "area": 400,
                    "token": "first-root",
                },
                {
                    "exists": True,
                    "visible": True,
                    "interactive": True,
                    "inForeground": False,
                    "columns": ["项目代码", "金额"],
                    "rowCount": 1,
                    "rowTexts": ["B 200"],
                    "area": 400,
                    "token": "second-root",
                },
            ]
        raise AssertionError("unexpected script")


class _FakeDistinctAliasBusinessTableScopeEvidencePage:
    frames: list = []

    def evaluate(self, script: str, arg=None):
        if script == runtime_module._TABLE_SCOPE_FOREGROUND_EXISTS_SCRIPT:
            return False
        if script == runtime_module._TABLE_SCOPE_REGION_EVIDENCE_SCRIPT:
            if arg["fieldid"] == "bg_table":
                return [{
                    "exists": True,
                    "visible": True,
                    "interactive": True,
                    "inForeground": False,
                    "columns": ["项目代码", "金额"],
                    "rowCount": 1,
                    "rowTexts": ["A 100"],
                    "token": "alias-first-root",
                }]
            if arg["fieldid"] == "bg_table_table":
                return [{
                    "exists": True,
                    "visible": True,
                    "interactive": True,
                    "inForeground": False,
                    "columns": ["项目代码", "金额"],
                    "rowCount": 1,
                    "rowTexts": ["B 200"],
                    "token": "alias-second-root",
                }]
            return []
        raise AssertionError("unexpected script")


class _FakeEquivalentTableScopeAliasEvidencePage:
    frames: list = []

    def evaluate(self, script: str, arg=None):
        if script == runtime_module._TABLE_SCOPE_FOREGROUND_EXISTS_SCRIPT:
            return False
        if script == runtime_module._TABLE_SCOPE_REGION_EVIDENCE_SCRIPT:
            if arg["fieldid"] == "bg_table":
                return [{"exists": True, "visible": True, "interactive": True, "columns": ["项目分类编码", "管理费提取方式"], "rowCount": 2, "area": 800, "token": "region-root"}]
            if arg["fieldid"] == "bg_table_table":
                return [{"exists": True, "visible": True, "interactive": True, "columns": ["项目分类编码", "管理费提取方式"], "rowCount": 2, "area": 1200, "token": "runtime-root"}]
            return []
        raise AssertionError("unexpected script")


def test_playwright_runtime_reports_foreground_table_scope_evidence_and_token() -> None:
    runtime = object.__new__(PlaywrightRuntime)
    runtime._page = _FakeTableScopeEvidencePage()
    regions = [
        Region("background", "background_table", "背景表", "main_table", "table", "Table", None, True, 0),
        Region(
            "dialog",
            "dialog_table",
            "弹窗表",
            "main_table",
            "table",
            "Table",
            None,
            True,
            0,
            runtime_fieldids=["dialog_table_table"],
        ),
    ]

    evidence = runtime.inspect_table_scope_regions(regions)

    assert evidence[0].foreground is False
    assert evidence[1].runtime_fieldid == "dialog_table_table"
    assert evidence[1].foreground is True
    assert evidence[1].columns == ("项目代码", "金额")
    assert runtime.is_table_scope_token_valid(evidence[1].token) is True


def test_playwright_runtime_marks_existing_headerless_table_columns_as_observed(monkeypatch) -> None:
    runtime = object.__new__(PlaywrightRuntime)
    runtime._page = _FakeHeaderlessTableScopeEvidencePage()
    monkeypatch.setattr(runtime, "_collect_table_header_records", lambda **_kwargs: [])
    region = Region(
        "detail",
        "bg_table",
        "增加",
        "main_table",
        "table",
        "Table",
        None,
        True,
        0,
        runtime_fieldids=["bg_table_table"],
    )

    evidence = runtime.inspect_table_scope_regions([region])

    assert evidence[0].columns == ()
    assert evidence[0].columns_observed is True


def test_playwright_runtime_preserves_duplicate_logical_table_headers(monkeypatch) -> None:
    runtime = object.__new__(PlaywrightRuntime)
    runtime._page = _FakeDuplicateHeaderTableScopeEvidencePage()
    monkeypatch.setattr(
        runtime,
        "_collect_table_header_records",
        lambda **_kwargs: [("*数量", "text:数量:1")],
    )
    region = Region(
        "detail",
        "quantity_table",
        "数量信息",
        "main_table",
        "table",
        "Table",
        None,
        True,
        0,
    )

    evidence = runtime.inspect_table_scope_regions([region])

    assert evidence[0].columns == ("*数量", "*数量")
    assert "columns: headers," in runtime_module._TABLE_SCOPE_REGION_EVIDENCE_SCRIPT


def test_playwright_runtime_preserves_distinct_same_name_headers_across_split_roots(monkeypatch) -> None:
    runtime = object.__new__(PlaywrightRuntime)
    runtime._page = _FakeSplitSameNameHeaderIdentityPage(("requestedNum", "approvedNum"))
    monkeypatch.setattr(
        runtime,
        "_collect_table_header_records",
        lambda **_kwargs: [("数量", "requestedNum"), ("数量", "approvedNum")],
    )
    region = Region("detail", "quantity_table", "数量信息", "main_table", "table", "Table", None, True, 0)

    evidence = runtime.inspect_table_scope_regions([region])

    assert evidence[0].columns == ("数量", "数量")


def test_playwright_runtime_deduplicates_same_header_identity_across_split_roots(monkeypatch) -> None:
    runtime = object.__new__(PlaywrightRuntime)
    runtime._page = _FakeSplitSameNameHeaderIdentityPage(("num", "num"))
    monkeypatch.setattr(
        runtime,
        "_collect_table_header_records",
        lambda **_kwargs: [("数量", "num")],
    )
    region = Region("detail", "quantity_table", "数量信息", "main_table", "table", "Table", None, True, 0)

    evidence = runtime.inspect_table_scope_regions([region])

    assert evidence[0].columns == ("数量",)


def test_table_scope_region_evidence_deduplicates_fixed_header_clone(_popup_reference_page) -> None:
    page = _popup_reference_page
    page.set_content(
        """
        <style>table { width: 400px; } th { width: 120px; height: 32px; }</style>
        <table fieldid="quantity_table">
          <thead><tr>
            <th data-index="num">数量</th>
            <th data-index="num">数量</th>
          </tr></thead>
        </table>
        """
    )

    evidence = page.evaluate(
        runtime_module._TABLE_SCOPE_REGION_EVIDENCE_SCRIPT,
        {"fieldid": "quantity_table", "token": "scope"},
    )

    assert evidence[0]["columns"] == ["数量"]


def test_table_scope_region_evidence_preserves_distinct_same_name_columns(_popup_reference_page) -> None:
    page = _popup_reference_page
    page.set_content(
        """
        <style>table { width: 400px; } th { width: 120px; height: 32px; }</style>
        <table fieldid="quantity_table">
          <thead><tr>
            <th data-index="requestedNum">数量</th>
            <th data-index="approvedNum">数量</th>
          </tr></thead>
        </table>
        """
    )

    evidence = page.evaluate(
        runtime_module._TABLE_SCOPE_REGION_EVIDENCE_SCRIPT,
        {"fieldid": "quantity_table", "token": "scope"},
    )

    assert evidence[0]["columns"] == ["数量", "数量"]


def test_table_scope_region_evidence_uses_header_cell_owner_for_nested_wui_content(
    _popup_reference_page,
) -> None:
    page = _popup_reference_page
    page.set_content(
        """
        <style>table { width: 400px; } th { width: 120px; height: 32px; }</style>
        <table class="wui-table-header" fieldid="quantity_table">
          <thead><tr>
            <th data-col-key="num"><div class="wui-table-cell-content">数量</div></th>
          </tr></thead>
        </table>
        """
    )

    evidence = page.evaluate(
        runtime_module._TABLE_SCOPE_REGION_EVIDENCE_SCRIPT,
        {"fieldid": "quantity_table", "token": "scope"},
    )

    assert evidence[0]["columns"] == ["数量"]


def test_table_scope_region_evidence_deduplicates_same_identity_with_text_marker_difference(
    _popup_reference_page,
) -> None:
    page = _popup_reference_page
    page.set_content(
        """
        <style>table { width: 400px; } th { width: 120px; height: 32px; }</style>
        <table fieldid="quantity_table">
          <thead><tr>
            <th data-col-key="num">数量</th>
            <th data-col-key="num">*数量</th>
          </tr></thead>
        </table>
        """
    )

    evidence = page.evaluate(
        runtime_module._TABLE_SCOPE_REGION_EVIDENCE_SCRIPT,
        {"fieldid": "quantity_table", "token": "scope"},
    )

    assert evidence[0]["columns"] == ["数量"]


def test_table_scope_region_evidence_uses_div_fieldid_header_owner(
    _popup_reference_page,
) -> None:
    page = _popup_reference_page
    page.set_content(
        """
        <style>
          .wui-table-header { width: 400px; height: 40px; }
          .wui-table-cell, .wui-table-cell-content { width: 120px; height: 32px; }
        </style>
        <div class="wui-table-header" fieldid="quantity_table">
          <div class="wui-table-cell" fieldid="num">
            <div class="wui-table-cell-content">数量</div>
          </div>
        </div>
        """
    )

    evidence = page.evaluate(
        runtime_module._TABLE_SCOPE_REGION_EVIDENCE_SCRIPT,
        {"fieldid": "quantity_table", "token": "scope"},
    )

    assert evidence[0]["columns"] == ["数量"]


def test_table_headers_script_returns_distinct_identity_records_for_same_name_columns(
    _popup_reference_page,
) -> None:
    page = _popup_reference_page
    page.set_content(
        """
        <style>table { width: 400px; } th { width: 120px; height: 32px; }</style>
        <table><thead><tr>
          <th data-index="requestedNum">数量</th>
          <th data-index="approvedNum">数量</th>
        </tr></thead></table>
        """
    )

    records = page.evaluate(runtime_module._TABLE_HEADERS_SCRIPT, {"includeIdentity": True})

    assert records == [
        {"text": "数量", "identity": "data-index:requestedNum"},
        {"text": "数量", "identity": "data-index:approvedNum"},
    ]


def test_table_headers_script_deduplicates_same_identity_across_text_markers(
    _popup_reference_page,
) -> None:
    page = _popup_reference_page
    page.set_content(
        """
        <style>table { width: 400px; } th { width: 120px; height: 32px; }</style>
        <table><thead><tr>
          <th data-index="num">数量</th>
          <th data-index="num">*数量</th>
        </tr></thead></table>
        """
    )

    records = page.evaluate(runtime_module._TABLE_HEADERS_SCRIPT, {"includeIdentity": True})

    assert records == [{"text": "数量", "identity": "data-index:num"}]


def test_table_scope_merge_does_not_duplicate_text_only_header_identity(
    _popup_reference_page,
) -> None:
    page = _popup_reference_page
    page.set_content(
        """
        <style>table { width: 400px; } th { width: 120px; height: 32px; }</style>
        <table fieldid="quantity_table"><thead><tr><th>数量</th></tr></thead></table>
        """
    )

    item = page.evaluate(
        runtime_module._TABLE_SCOPE_REGION_EVIDENCE_SCRIPT,
        {"fieldid": "quantity_table", "token": "scope"},
    )[0]
    observed = runtime_module._table_header_records(item)
    collected_payload = page.evaluate(runtime_module._TABLE_HEADERS_SCRIPT, {"includeIdentity": True})
    collected = [(record["text"], record["identity"]) for record in collected_payload]

    assert observed[0][1] != collected[0][1]
    assert runtime_module._merge_collected_header_records(observed, collected) == observed


def test_playwright_runtime_ignores_navigating_context_when_collecting_table_scope_evidence() -> None:
    runtime = object.__new__(PlaywrightRuntime)
    runtime._page = _FakeNavigatingTableScopePage(_FakeTableScopeEvidencePage())
    region = Region(
        "dialog",
        "dialog_table",
        "弹窗表",
        "main_table",
        "table",
        "Table",
        None,
        True,
        0,
        runtime_fieldids=["dialog_table_table"],
    )

    evidence = runtime.inspect_table_scope_regions([region])

    assert evidence[0].runtime_fieldid == "dialog_table_table"
    assert evidence[0].foreground is True
    assert evidence[0].columns == ("项目代码", "金额")


def test_playwright_runtime_ignores_navigating_context_when_validating_table_scope_token() -> None:
    runtime = object.__new__(PlaywrightRuntime)
    runtime._page = _FakeNavigatingTableScopePage(_FakeTableScopeEvidencePage())

    assert runtime.is_table_scope_token_valid("dialog-token") is True


def test_playwright_runtime_merges_physical_roots_for_same_runtime_fieldid() -> None:
    runtime = object.__new__(PlaywrightRuntime)
    runtime._page = _FakeSplitTableScopeEvidencePage()
    region = Region(
        "detail",
        "bg_table",
        "增加",
        "main_table",
        "table",
        "Table",
        None,
        True,
        0,
        runtime_fieldids=["bg_table_table"],
    )

    evidence = runtime.inspect_table_scope_regions([region])

    assert [item.token for item in evidence] == ["data-root"]
    assert evidence[0].columns == ("收入分成比例%", "说明")


def test_playwright_runtime_does_not_merge_physical_roots_across_foreground_layers() -> None:
    runtime = object.__new__(PlaywrightRuntime)
    runtime._page = _FakeCrossForegroundSplitTableScopeEvidencePage()
    region = Region("detail", "bg_table", "增加", "main_table", "table", "Table", None, True, 0)

    evidence = runtime.inspect_table_scope_regions([region])

    assert [(item.token, item.foreground) for item in evidence] == [
        ("background-header-root", False),
        ("foreground-data-root", True),
    ]


def test_playwright_runtime_preserves_distinct_alias_evidence_without_header_override(monkeypatch) -> None:
    runtime = object.__new__(PlaywrightRuntime)
    runtime._page = _FakeTableScopeAliasEvidencePage()
    monkeypatch.setattr(
        runtime,
        "_collect_table_header_records",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("ambiguous aliases must not share headers")),
    )
    region = Region(
        "detail",
        "bg_table",
        "增加",
        "main_table",
        "table",
        "Table",
        None,
        True,
        0,
        runtime_fieldids=["bg_table_table"],
    )

    evidence = runtime.inspect_table_scope_regions([region])

    assert [(item.runtime_fieldid, item.token) for item in evidence] == [
        ("bg_table", "background-root"),
        ("bg_table_table", "detail-root"),
    ]


def test_playwright_runtime_preserves_distinct_physical_tables_with_same_fieldid() -> None:
    runtime = object.__new__(PlaywrightRuntime)
    runtime._page = _FakeDistinctPhysicalTableScopeEvidencePage()
    region = Region("detail", "bg_table", "增加", "main_table", "table", "Table", None, True, 0)

    evidence = runtime.inspect_table_scope_regions([region])

    assert [(item.runtime_fieldid, item.token) for item in evidence] == [
        ("bg_table", "first-root"),
        ("bg_table", "second-root"),
    ]


def test_playwright_runtime_preserves_distinct_alias_tables_with_different_business_rows() -> None:
    runtime = object.__new__(PlaywrightRuntime)
    runtime._page = _FakeDistinctAliasBusinessTableScopeEvidencePage()
    region = Region(
        "detail",
        "bg_table",
        "增加",
        "main_table",
        "table",
        "Table",
        None,
        True,
        0,
        runtime_fieldids=["bg_table_table"],
    )

    evidence = runtime.inspect_table_scope_regions([region])

    assert [(item.runtime_fieldid, item.token) for item in evidence] == [
        ("bg_table", "alias-first-root"),
        ("bg_table_table", "alias-second-root"),
    ]


def test_playwright_runtime_deduplicates_equivalent_fieldid_alias_roots() -> None:
    runtime = object.__new__(PlaywrightRuntime)
    runtime._page = _FakeEquivalentTableScopeAliasEvidencePage()
    region = Region(
        "list",
        "bg_table",
        "表格",
        "main_table",
        "table",
        "Table",
        None,
        True,
        0,
        runtime_fieldids=["bg_table_table"],
    )

    evidence = runtime.inspect_table_scope_regions([region])

    assert [(item.runtime_fieldid, item.token) for item in evidence] == [
        ("bg_table_table", "runtime-root")
    ]


def test_playwright_runtime_table_scope_collects_virtualized_headers(monkeypatch) -> None:
    runtime = object.__new__(PlaywrightRuntime)
    runtime._page = _FakeEquivalentTableScopeAliasEvidencePage()
    calls: list[str] = []
    monkeypatch.setattr(
        runtime,
        "_collect_table_header_records",
        lambda **kwargs: calls.append(kwargs["table_fieldid"])
        or [
            ("姓名", "data-index:name"),
            ("人员代码", "data-index:code"),
            ("证件号码", "data-index:idNumber"),
            ("人员状态", "data-index:status"),
        ],
    )
    region = Region(
        "list",
        "bg_table",
        "表格",
        "main_table",
        "table",
        "Table",
        None,
        True,
        0,
        runtime_fieldids=["bg_table_table"],
    )

    evidence = runtime.inspect_table_scope_regions([region], collect_columns=True)

    assert evidence[0].columns == ("姓名", "人员代码", "证件号码", "人员状态")
    assert calls == ["bg_table_table"]


def test_table_scope_evidence_inspects_table_ancestor_chain() -> None:
    assert "for (let ancestor = node" in runtime_module._TABLE_SCOPE_REGION_EVIDENCE_SCRIPT
    assert "ancestor.parentElement" in runtime_module._TABLE_SCOPE_REGION_EVIDENCE_SCRIPT


def test_table_scope_root_preserves_tokens_for_equivalent_aliases(_popup_reference_page) -> None:
    page = _popup_reference_page
    runtime, scope = _resolved_alias_table(page)
    second = page.evaluate(runtime_module._TABLE_SCOPE_REGION_EVIDENCE_SCRIPT,
                           {"fieldid": "ACTUAL", "token": "another-scan"})
    assert runtime.is_table_scope_token_valid(scope.token)
    assert all(runtime.is_table_scope_token_valid(item["token"]) for item in second)
    assert runtime.collect_table_column_values("金额", table_scope=scope) == ["10", "20"]


@pytest.mark.parametrize(
    ("container_style", "table_style", "visible"),
    [
        ("height:0;overflow:hidden", "", False),
        ("width:0;overflow:hidden", "", False),
        ("height:0;overflow:clip", "", False),
        ("height:0;overflow:auto", "", False),
        ("height:40px;overflow:hidden", "margin-top:80px", False),
        ("height:40px;overflow:hidden", "margin-top:-20px", True),
        ("height:40px;overflow:auto", "margin-top:80px", True),
        ("height:0;overflow:visible", "", True),
    ],
)
def test_table_scope_respects_ancestor_clipping(
    _popup_reference_page, container_style: str, table_style: str, visible: bool,
) -> None:
    page = _popup_reference_page
    page.set_content(f"""
        <style>table {{ width:400px; }} th, td {{ height:30px; }}</style>
        <table fieldid="detail"><thead><tr><th>部门经济分类</th></tr></thead>
          <tbody><tr><td>办公设备购置</td></tr></tbody></table>
        <div style="{container_style}">
          <table fieldid="auxiliary" style="{table_style}">
            <thead><tr><th>政府采购项目</th></tr></thead>
            <tbody><tr><td>辅助数据</td></tr></tbody></table>
        </div>
    """)
    runtime = object.__new__(PlaywrightRuntime)
    runtime._page = page
    manifest = PageManifest(
        page=PageMeta("root", None, None, None),
        regions=[
            Region("card", "card", "政府采购信息", "content_card", "card", "LCDCard", None, True, 0),
            Region("detail", "detail", "政府采购信息", "main_table", "table", "LCDTable", "card", True, 0),
            Region("auxiliary", "auxiliary", "政府采购项目表-高度0", "main_table", "table", "LCDTable", "card", True, 0),
        ],
    )
    auxiliary = runtime.inspect_table_scope_regions([manifest.regions[-1]])[0]
    assert auxiliary.visible is visible
    assert auxiliary.interactive is visible
    resolver = TableScopeResolver(RuntimeTableScopeAdapter(runtime))
    request = TableScopeRequest(target="政府采购信息")
    if visible:
        with pytest.raises(TableScopeError, match="无法唯一确定表格作用域") as exc_info:
            resolver.resolve(manifest, request)
        assert exc_info.value.code == "ambiguous"
    else:
        scope = resolver.resolve_for_execution(manifest, request)
        assert scope.region_fieldid == "detail"
        assert runtime.is_table_scope_token_valid(scope.token)
        with pytest.raises(TableScopeError) as exc_info:
            resolver.resolve(manifest, TableScopeRequest(target="auxiliary"))
        assert exc_info.value.code == "not-visible"


def test_table_scope_token_rejects_root_clipped_after_resolution(_popup_reference_page) -> None:
    page = _popup_reference_page
    page.set_content("""
        <div id="container" style="height:80px;overflow:hidden">
          <table fieldid="detail"><thead><tr><th>金额</th></tr></thead>
            <tbody><tr><td>10</td></tr></tbody></table>
        </div>
    """)
    runtime = object.__new__(PlaywrightRuntime)
    runtime._page = page
    region = Region("detail", "detail", "明细", "main_table", "table", "LCDTable", None, True, 0)
    token = runtime.inspect_table_scope_regions([region])[0].token
    assert runtime.is_table_scope_token_valid(token)

    page.locator("#container").evaluate("node => node.style.height = '0px'")

    assert runtime.is_table_scope_token_valid(token) is False


def test_clipped_foreground_layer_does_not_hide_visible_table(_popup_reference_page) -> None:
    page = _popup_reference_page
    page.set_content("""
        <table fieldid="detail"><thead><tr><th>金额</th></tr></thead>
          <tbody><tr><td>10</td></tr></tbody></table>
        <div style="height:0;overflow:hidden">
          <div role="dialog" style="width:400px;height:80px">已裁剪的弹层</div>
        </div>
    """)
    runtime = object.__new__(PlaywrightRuntime)
    runtime._page = page
    region = Region("detail", "detail", "明细", "main_table", "table", "LCDTable", None, True, 0)

    assert page.evaluate(runtime_module._TABLE_SCOPE_FOREGROUND_EXISTS_SCRIPT) is False
    assert runtime.inspect_table_scope_regions([region])[0].foreground is True


def test_notification_merge_dedupes_message_and_prefers_specific_type() -> None:
    runtime = object.__new__(PlaywrightRuntime)

    merged = runtime._merge_notifications(
        [{"type": "info", "message": "保存成功！"}],
        [{"type": "success", "message": "保存成功！"}],
    )

    assert merged == [{"type": "success", "message": "保存成功！"}]


def test_action_completion_returns_first_buffered_notification(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    monkeypatch.setattr(
        runtime,
        "_drain_buffered_notifications",
        lambda: [{"type": "success", "message": "保存成功"}],
    )
    monkeypatch.setattr(runtime, "_scan_notifications", lambda: [])
    monkeypatch.setattr(runtime, "begin_notification_capture", lambda: None)

    request = ActionCompletionRequest(action="toolbar.click")
    runtime._prepare_action_completion(request)
    observation = runtime._observe_action_completion(request)

    assert observation.notifications == (ActionNotification(type="success", message="保存成功"),)


def test_action_completion_stops_after_decisive_playwright_notification(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    monkeypatch.setattr(
        runtime,
        "_drain_buffered_notifications",
        lambda: [{"type": "success", "message": "保存成功"}],
    )
    monkeypatch.setattr(runtime, "_scan_notifications", lambda: [])
    monkeypatch.setattr(runtime, "begin_notification_capture", lambda: None)
    monkeypatch.setattr(
        runtime,
        "_dynamic_template_payload_matches_action",
        lambda *_args: (_ for _ in ()).throw(AssertionError("不应继续探测动态模板")),
    )
    monkeypatch.setattr(
        runtime,
        "_action_dom_completion_signal",
        lambda *_args: (_ for _ in ()).throw(AssertionError("不应继续扫描 DOM")),
    )

    result = ActionCompletion(runtime).execute(
        ActionCompletionRequest(action="toolbar.click"),
        lambda: None,
    )

    assert result.completion_signal == "notification"


def test_fixture_action_completion_requires_observed_click_state() -> None:
    runtime = FixtureRuntime(runtime_elements=[])
    completion = ActionCompletion(runtime)

    fallback = completion.execute(
        ActionCompletionRequest(action="action.click"),
        lambda: None,
    )
    verified = completion.execute(
        ActionCompletionRequest(action="action.click"),
        lambda: runtime.clicked_targets.append("保存"),
    )

    assert fallback.completion_signal == "compatibility_timeout"
    assert fallback.fallback_used is True
    assert verified.completion_signal == "fixture_state"
    assert verified.fallback_used is False


@pytest.mark.parametrize("notification", [
    {"type": "warning", "message": "请确认当前数据"},
    {"type": "success", "message": "扩展动作完成"},
])
def test_action_completion_does_not_accept_nonstandard_notification(monkeypatch, notification) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    monkeypatch.setattr(runtime, "_drain_buffered_notifications", lambda: [notification])
    monkeypatch.setattr(runtime, "_scan_notifications", lambda: [])
    monkeypatch.setattr(runtime, "begin_notification_capture", lambda: None)

    request = ActionCompletionRequest(action="toolbar.click")
    runtime._prepare_action_completion(request)
    observation = runtime._observe_action_completion(request)

    assert observation.notifications == (
        ActionNotification(type=notification["type"], message=notification["message"]),
    )


def test_action_completion_does_not_accept_notification_present_before_action(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    current = [{"type": "success", "message": "保存成功"}]
    monkeypatch.setattr(runtime, "_scan_notifications", lambda: list(current))
    monkeypatch.setattr(runtime, "_drain_buffered_notifications", lambda: [])
    monkeypatch.setattr(runtime, "begin_notification_capture", lambda: None)

    request = ActionCompletionRequest(action="toolbar.click")
    runtime._prepare_action_completion(request)
    observation = runtime._observe_action_completion(request)

    assert observation.notifications == ()


def test_action_completion_accepts_same_message_from_action_observer(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    notification = {"type": "success", "message": "保存成功"}
    monkeypatch.setattr(runtime, "_scan_notifications", lambda: [notification])
    monkeypatch.setattr(runtime, "_drain_buffered_notifications", lambda: [notification])
    monkeypatch.setattr(runtime, "begin_notification_capture", lambda: None)

    request = ActionCompletionRequest(action="toolbar.click")
    runtime._prepare_action_completion(request)
    observation = runtime._observe_action_completion(request)

    assert observation.notifications == (ActionNotification(type="success", message="保存成功"),)


def test_action_completion_returns_pending_dynamic_template(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    runtime._dynamic_template_payload = {"data": {"uidata": [{"divCode": "editRoot"}]}}
    monkeypatch.setattr(runtime, "_dynamic_template_payload_work_surface_ready", lambda _payload: True, raising=False)
    monkeypatch.setattr(runtime, "_drain_buffered_notifications", lambda: [])
    monkeypatch.setattr(runtime, "_scan_notifications", lambda: [])
    monkeypatch.setattr(runtime, "begin_notification_capture", lambda: None)

    request = ActionCompletionRequest(action="dialog.click", context={"target_page_id": "editRoot"})
    runtime._prepare_action_completion(request)
    observation = runtime._observe_action_completion(request)

    assert observation.dynamic_template is True
    assert observation.dynamic_template_fallback is False
    assert runtime._dynamic_template_payload is not None


def test_action_completion_returns_ready_targetless_toolbar_template_as_fallback(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    payload = {"data": {"pageId": "target", "uidata": [{"divCode": "editRoot"}]}}
    runtime._dynamic_template_payload = payload
    monkeypatch.setattr(runtime, "_drain_buffered_notifications", lambda: [])
    monkeypatch.setattr(runtime, "_scan_notifications", lambda: [])
    monkeypatch.setattr(
        runtime,
        "dynamic_template_payload_can_apply_as_fallback",
        lambda candidate: candidate is payload,
    )
    monkeypatch.setattr(runtime, "begin_notification_capture", lambda: None)

    request = ActionCompletionRequest(action="toolbar.click", context={"source_page_id": "root"})
    runtime._prepare_action_completion(request)
    observation = runtime._observe_action_completion(request)

    assert observation.dynamic_template is False
    assert observation.dynamic_template_fallback is True
    assert runtime.peek_dynamic_template_payload() is payload


@pytest.mark.parametrize("action", ["dialog.click", "toolbar.click"])
def test_action_completion_does_not_accept_dynamic_template_before_work_surface_is_ready(
    monkeypatch,
    action: str,
) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    runtime._dynamic_template_payload = {"data": {"uidata": [{"divCode": "editRoot"}]}}
    monkeypatch.setattr(runtime, "_dynamic_template_payload_work_surface_ready", lambda _payload: False, raising=False)
    monkeypatch.setattr(runtime, "_drain_buffered_notifications", lambda: [])
    monkeypatch.setattr(runtime, "_scan_notifications", lambda: [])
    monkeypatch.setattr(runtime, "begin_notification_capture", lambda: None)

    request = ActionCompletionRequest(action=action, context={"target_page_id": "editRoot"})
    runtime._prepare_action_completion(request)
    observation = runtime._observe_action_completion(request)

    assert observation.dynamic_template is False
    assert observation.dynamic_template_fallback is False


def test_action_completion_rejects_unrelated_dynamic_template_for_expected_target_page(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    runtime._dynamic_template_payload = {"data": {"uidata": [{"divCode": "other_page"}]}}
    monkeypatch.setattr(runtime, "_drain_buffered_notifications", lambda: [])
    monkeypatch.setattr(runtime, "_scan_notifications", lambda: [])
    monkeypatch.setattr(runtime, "begin_notification_capture", lambda: None)

    request = ActionCompletionRequest(action="toolbar.click", context={"target_page_id": "expected_page"})
    runtime._prepare_action_completion(request)
    observation = runtime._observe_action_completion(request)

    assert observation.dynamic_template is False
    assert observation.dynamic_template_fallback is False


def test_dynamic_template_work_surface_excludes_source_page_identity() -> None:
    seen: list[list[str]] = []

    class TargetFrame:
        def evaluate(self, _script: str, identities: list[str]) -> dict[str, bool]:
            seen.append(identities)
            return {"root": True, "interactive": True}

    runtime = _build_runtime()
    runtime._page = _FakePage()
    runtime._page.frames = [TargetFrame()]
    runtime._action_completion_context = {"source_page_id": "root", "target_page_id": "editRoot"}
    payload = {"data": {"pageId": "root", "uidata": [{"divCode": "editRoot"}]}}

    assert runtime._dynamic_template_payload_matches_action(payload) is True
    assert runtime._dynamic_template_payload_work_surface_ready(payload) is True
    assert seen == [["editRoot"]]


def test_dynamic_template_without_target_identity_only_allows_ready_non_source_fallback() -> None:
    seen: list[list[str]] = []

    class TargetFrame:
        def evaluate(self, _script: str, identities: list[str]) -> dict[str, bool]:
            seen.append(identities)
            return {"root": True, "interactive": True}

    runtime = _build_runtime()
    runtime._page = _FakePage()
    runtime._page.frames = [TargetFrame()]
    payload = {"data": {"pageId": "root", "uidata": [{"divCode": "editRoot"}]}}

    runtime._action_completion_context = {"source_page_id": "root"}

    assert runtime._dynamic_template_payload_matches_action(payload) is False
    assert runtime.dynamic_template_payload_can_apply_as_fallback(payload) is True
    assert seen == [["editRoot"]]
    assert runtime.dynamic_template_payload_can_apply_as_fallback({"data": {"pageId": "root"}}) is False


def test_dynamic_template_cached_field_readiness_is_revalidated_after_dom_change() -> None:
    dom_alive = True
    dom_editable = True
    calls: list[str] = []

    class CachedLocator:
        def __init__(self, selector: str) -> None:
            self.selector = selector

        def count(self) -> int:
            return int(dom_alive)

        def is_visible(self, *, timeout: int) -> bool:
            assert timeout == 300
            return dom_alive

        def is_enabled(self, *, timeout: int) -> bool:
            assert timeout == 300
            return dom_alive

        def is_editable(self, *, timeout: int) -> bool:
            assert timeout == 300
            assert self.selector == '[data-ydf-browser-runtime-id="field-1"]'
            return dom_alive and dom_editable

        def click(self, *, trial: bool, timeout: int) -> None:
            assert trial is True
            assert timeout == 300

    class TargetFrame:
        name = ""
        url = ""

        def evaluate(self, script: str, _argument: Any = None):
            if script == runtime_module._DYNAMIC_TEMPLATE_WORK_SURFACE_SCRIPT:
                calls.append("surface")
                return {"root": False, "interactive": False, "root_count": 0, "interactive_count": 0}
            if script == runtime_module._DOM_SCAN_SCRIPT:
                calls.append("scan")
                return [
                    {
                        "label_text": "资金往来对象编码",
                        "visible": True,
                        "editable": dom_editable,
                        "pointer_receivable": True,
                        "in_dialog": True,
                        "tag_name": "div",
                        "role": "",
                        "selector": '[data-ydf-browser-runtime-id="wrapper-1"]',
                    },
                    {
                        "label_text": "资金往来对象编码",
                        "visible": True,
                        "editable": dom_editable,
                        "pointer_receivable": True,
                        "in_dialog": True,
                        "tag_name": "input",
                        "role": "textbox",
                        "selector": '[data-ydf-browser-runtime-id="field-1"]',
                    },
                ] if dom_alive else []
            return {"root": False, "interactive": False}

        def locator(self, selector: str) -> CachedLocator:
            calls.append("cached")
            return CachedLocator(selector)

    runtime = _build_runtime()
    runtime._page = _FakePage()
    runtime._page.frames = [TargetFrame()]
    runtime._action_completion_context = {"source_page_id": "root", "target_page_id": "editRoot"}
    payload = {
        "data": {
            "uidata": [{
                "divCode": "editRoot",
                "children": [{
                    "nodeType": "formItem",
                    "fieldid": "counterpartCode",
                    "label": "资金往来对象编码",
                }],
            }]
        }
    }

    assert runtime._dynamic_template_payload_work_surface_ready(payload) is True
    assert runtime._dynamic_template_payload_work_surface_ready(payload) is True
    dom_editable = False
    assert runtime._dynamic_template_payload_work_surface_ready(payload) is False

    assert calls == ["surface", "scan", "cached", "cached", "surface", "scan"]


def test_dynamic_template_fallback_uses_platform_page_holder_identity() -> None:
    seen: list[list[str]] = []

    class TargetFrame:
        def evaluate(_self, script: str, identities: list[str]) -> dict[str, int | bool]:
            seen.append(identities)
            ready = "pagetarget-page" in identities and "node.id" in script
            return {"root": ready, "interactive": ready, "root_count": int(ready), "interactive_count": int(ready)}

    runtime = _build_runtime()
    runtime._page = _FakePage()
    runtime._page.frames = [TargetFrame()]
    runtime._action_completion_context = {"source_page_id": "root"}
    payload = {
        "data": {
            "pageId": "target-page",
            "pageCode": "target-page-code",
            "uidata": [{"divCode": "root"}],
        }
    }

    assert runtime.dynamic_template_payload_can_apply_as_fallback(payload) is True
    assert seen == [["target-page", "target-page-code", "pagetarget-page"]]


def test_dynamic_template_fallback_uses_direct_page_table_identity() -> None:
    seen: list[list[str]] = []
    scripts: list[str] = []

    class TargetFrame:
        def evaluate(_self, script: str, identities: list[str]) -> dict[str, int | bool]:
            scripts.append(script)
            seen.append(identities)
            ready = "ACCOUNT_TABLE" in identities and "node.id" in script
            return {"root": ready, "interactive": ready, "root_count": int(ready), "interactive_count": int(ready)}

    runtime = _build_runtime()
    runtime._page = _FakePage()
    runtime._page.frames = [TargetFrame()]
    runtime._action_completion_context = {"source_page_id": "root"}
    payload = {
        "data": {
            "pageId": "target-page",
            "pageCode": "target-page-code",
            "uidata": [
                {
                    "divCode": "root",
                    "children": [{"nodeType": "table", "divCode": "ACCOUNT_TABLE"}],
                }
            ],
        }
    }

    assert runtime.dynamic_template_payload_can_apply_as_fallback(payload) is True
    assert seen == [["target-page", "target-page-code", "pagetarget-page", "ACCOUNT_TABLE"]]
    assert "document.body" in scripts[0]
    assert '[class*="modal"]' in scripts[0]


def test_dynamic_template_fallback_waits_for_direct_page_field_render() -> None:
    seen: list[list[str]] = []

    class TargetFrame:
        def evaluate(_self, script: str, identities: list[str]) -> dict[str, int | bool]:
            seen.append(identities)
            ready = bool({"ACCOUNT_TABLE", "FORM_FIELD"}.intersection(identities))
            return {"root": ready, "interactive": ready, "root_count": int(ready), "interactive_count": int(ready)}

    runtime = _build_runtime()
    runtime._page = _FakePage()
    runtime._page.frames = [TargetFrame()]
    runtime._action_completion_context = {"source_page_id": "root"}
    payload = {
        "data": {
            "pageId": "target-page",
            "pageCode": "target-page-code",
            "uidata": [
                {
                    "divCode": "root",
                    "children": [
                        {"nodeType": "table", "divCode": "ACCOUNT_TABLE"},
                        {"nodeType": "formItem", "divCode": "FORM_FIELD"},
                    ],
                }
            ],
        }
    }

    assert runtime.dynamic_template_payload_can_apply_as_fallback(payload) is True
    assert seen == [
        ["target-page", "target-page-code", "pagetarget-page", "ACCOUNT_TABLE"],
        ["FORM_FIELD"],
    ]


def test_dynamic_template_fallback_uses_direct_page_field_without_table_identity() -> None:
    seen: list[list[str]] = []

    class TargetFrame:
        def evaluate(_self, _script: str, identities: list[str]) -> dict[str, int | bool]:
            seen.append(identities)
            ready = "FORM_FIELD" in identities
            return {"root": ready, "interactive": ready, "root_count": int(ready), "interactive_count": int(ready)}

    runtime = _build_runtime()
    runtime._page = _FakePage()
    runtime._page.frames = [TargetFrame()]
    runtime._action_completion_context = {"source_page_id": "root"}
    payload = {
        "data": {
            "pageId": "target-page",
            "pageCode": "target-page-code",
            "uidata": [{"divCode": "root", "children": [{"nodeType": "formItem", "divCode": "FORM_FIELD"}]}],
        }
    }

    assert runtime.dynamic_template_payload_can_apply_as_fallback(payload) is True
    assert seen == [["target-page", "target-page-code", "pagetarget-page", "FORM_FIELD"], ["FORM_FIELD"]]


def test_dynamic_template_fallback_uses_unique_interactive_field_label() -> None:
    seen: list[Any] = []

    class TargetFrame:
        def evaluate(_self, script: str, value: Any) -> dict[str, int | bool]:
            seen.append(value)
            ready = isinstance(value, str) and value == "资金往来对象编码"
            return {"root": ready, "interactive": ready, "root_count": int(ready), "interactive_count": int(ready)}

    runtime = _build_runtime()
    runtime._page = _FakePage()
    runtime._page.frames = [TargetFrame()]
    runtime._action_completion_context = {"source_page_id": "root"}
    payload = {
        "data": {
            "pageId": "target-page",
            "pageCode": "target-page-code",
            "uidata": [
                {
                    "divCode": "root",
                    "children": [{"nodeType": "formItem", "divCode": "FORM_FIELD", "label": "资金往来对象编码"}],
                }
            ],
        }
    }

    assert runtime.dynamic_template_payload_can_apply_as_fallback(payload) is True
    assert seen[-1] == "资金往来对象编码"


def test_dynamic_template_fallback_reuses_foreground_runtime_field_semantics() -> None:
    class TargetFrame:
        name = ""
        url = ""

        def evaluate(_self, script: str, _value: Any = None) -> Any:
            if script == runtime_module._DOM_SCAN_SCRIPT:
                return [
                    {
                        "label_text": "资金往来对象名称",
                        "visible": True,
                        "editable": True,
                        "pointer_receivable": True,
                        "in_dialog": True,
                    }
                ]
            return {"root": False, "interactive": False, "root_count": 0, "interactive_count": 0}

    runtime = _build_runtime()
    runtime._page = _FakePage()
    runtime._page.frames = [TargetFrame()]
    runtime._action_completion_context = {"source_page_id": "root"}
    payload = {
        "data": {
            "pageId": "target-page",
            "uidata": [{"divCode": "editRoot", "children": [{"nodeType": "formItem", "label": "资金往来对象名称"}]}],
        }
    }

    assert runtime.dynamic_template_payload_can_apply_as_fallback(payload) is True


def test_dynamic_template_fallback_checks_later_form_field_label_when_first_is_not_interactive() -> None:
    seen: list[Any] = []

    class TargetFrame:
        def evaluate(_self, _script: str, value: Any) -> dict[str, int | bool]:
            seen.append(value)
            ready = isinstance(value, str) and value == "字段名称"
            return {"root": ready, "interactive": ready, "root_count": int(ready), "interactive_count": int(ready)}

    runtime = _build_runtime()
    runtime._page = _FakePage()
    runtime._page.frames = [TargetFrame()]
    runtime._action_completion_context = {"source_page_id": "root"}
    payload = {
        "data": {
            "pageId": "target-page",
            "pageCode": "target-page-code",
            "uidata": [
                {
                    "divCode": "root",
                    "children": [
                        {"nodeType": "formItem", "divCode": "CODE_FIELD", "label": "编码"},
                        {"nodeType": "formItem", "divCode": "NAME_FIELD", "label": "字段名称"},
                    ],
                }
            ],
        }
    }

    assert runtime.dynamic_template_payload_can_apply_as_fallback(payload) is True
    assert seen[-1] == "字段名称"


def test_dynamic_template_fallback_checks_later_form_field_identity() -> None:
    seen: list[list[str]] = []

    class TargetFrame:
        def evaluate(_self, _script: str, identities: list[str]) -> dict[str, int | bool]:
            seen.append(identities)
            ready = "NAME_FIELD" in identities
            return {"root": ready, "interactive": ready, "root_count": int(ready), "interactive_count": int(ready)}

    runtime = _build_runtime()
    runtime._page = _FakePage()
    runtime._page.frames = [TargetFrame()]
    runtime._action_completion_context = {"source_page_id": "root"}
    payload = {
        "data": {
            "pageId": "target-page",
            "pageCode": "target-page-code",
            "uidata": [
                {
                    "divCode": "root",
                    "children": [
                        {"nodeType": "formItem", "divCode": "CODE_FIELD"},
                        {"nodeType": "formItem", "divCode": "NAME_FIELD"},
                    ],
                }
            ],
        }
    }

    assert runtime.dynamic_template_payload_can_apply_as_fallback(payload) is True
    assert ["NAME_FIELD"] in seen


@pytest.mark.parametrize("surface_count,hidden,expected", [(0, 0, False), (1, 0, True), (2, 0, False), (1, 1, False)])
def test_dynamic_template_readiness_uses_parsed_form_field_identity(monkeypatch, surface_count, hidden, expected) -> None:
    # The live form uses BasicDiv_reason, not the template item's numeric divCode.
    class TargetFrame:
        def evaluate(self, _script, identities):
            count = surface_count if "BasicDiv_reason" in identities else 0
            return {"root": bool(count), "interactive": bool(count),
                    "root_count": count, "interactive_count": count}

    runtime = _build_runtime()
    runtime._page = _FakePage()
    runtime._page.frames = [TargetFrame()]
    runtime._action_completion_context = {"source_page_id": "root"}
    monkeypatch.setattr(runtime, "_dynamic_template_payload_field_labels_ready", lambda *_args: False)
    payload = {"data": {"pageId": "edit-page", "uidata": [{
        "divCode": "root", "nodeType": "root", "children": [
            {"nodeType": "table", "divCode": "hidden_related_table"},
            {"nodeType": "form", "name": "LCDForm", "divCode": "BasicDiv", "children": [
                {"nodeType": "formItem", "name": "YDFTextArea", "divCode": "123456789",
                 "dataField": "reason", "label": "申请事由", "hide": hidden},
            ]},
        ],
    }]}}

    assert runtime.dynamic_template_payload_can_apply_as_fallback(payload) is expected


@pytest.mark.parametrize(
    "with_form,form_ready,surface_count,expected",
    [(False, False, 1, True), (True, False, 1, False), (False, False, 2, False), (True, True, 1, True)],
)
def test_dynamic_template_table_form_item_columns_do_not_block_ready_surface(
    monkeypatch, with_form, form_ready, surface_count, expected,
) -> None:
    class TargetFrame:
        def evaluate(self, _script, identities):
            ready = isinstance(identities, list) and (
                "purchase_details" in identities or form_ready and "actual_form_input" in identities
            )
            count = surface_count if ready else 0
            return {"root": ready, "interactive": ready, "root_count": count, "interactive_count": count}

    children = [{
        "divCode": "purchase_details", "nodeType": "table", "name": "LCDTable", "children": [{
            "divCode": "column_template_id", "nodeType": "formItem", "name": "YDFInput",
            "label": "采购品目", "dataField": "itemName",
        }],
    }]
    if with_form:
        children.append({
            "divCode": "actual_form_input", "nodeType": "formItem", "name": "YDFInput",
            "label": "备注", "dataField": "note",
        })
    payload = {"data": {"pageId": "selection_page", "uidata": [{
        "divCode": "root", "nodeType": "root", "children": children,
    }]}}
    runtime = _build_runtime()
    runtime._page = _FakePage()
    runtime._page.frames = [TargetFrame()]
    runtime._action_completion_context = {"source_page_id": "root"}
    monkeypatch.setattr(runtime, "_scan_frame", lambda *_args: [])

    assert runtime.dynamic_template_payload_can_apply_as_fallback(payload) is expected


@pytest.mark.parametrize("runtime_alias", [False, True])
@pytest.mark.parametrize(
    "readonly,extra_field,table_state,expected",
    [
        (1, None, "ready", True),
        (True, None, "ready", True),
        (1, "hidden", "ready", True),
        (1, "editable", "ready", False),
        (False, None, "ready", False),
        (None, None, "ready", False),
        ("false", None, "ready", False),
        (1, None, "missing", False),
        (1, None, "blocked", False),
        (1, None, "duplicate_frame", False),
    ],
)
def test_dynamic_template_readonly_form_installs_table_manifest(
    _popup_reference_page, readonly, extra_field, table_state, expected, runtime_alias,
) -> None:
    page = _popup_reference_page
    table_fieldid = "wzxx_table_table" if runtime_alias else "wzxx_table"
    table = f'<div fieldid="{table_fieldid}"><button>选择库存</button></div>'
    page.set_content(
        '<div fieldid="root"><div class="dis-editable">单据编号：LY001</div>'
        + (table if table_state != "missing" else "")
        + '<button>取消</button></div>'
    )
    if table_state == "blocked":
        page.evaluate("""() => {
            const overlay = document.createElement('div');
            overlay.style = 'position:fixed;inset:0;z-index:9999;background:white';
            document.body.appendChild(overlay);
        }""")
    elif table_state == "duplicate_frame":
        page.evaluate("""html => {
            const frame = document.createElement('iframe');
            frame.srcdoc = html;
            document.body.appendChild(frame);
        }""", table)
        page.frames[1].wait_for_selector(f'[fieldid="{table_fieldid}"]')
    fields = [{
        "divCode": "billCode", "nodeType": "formItem", "name": "YDFInput",
        "label": "单据编号", "props": {"readOnly": readonly},
    }]
    if extra_field:
        fields.append({
            "divCode": "remark", "nodeType": "formItem", "name": "YDFInput",
            "label": "备注", "hide": int(extra_field == "hidden"),
        })
    payload = {"data": {"pageId": "allocation-edit", "uidata": [{
        "divCode": "root", "nodeType": "root", "children": [
            {"divCode": "base_form", "nodeType": "form", "name": "LCDPanel", "children": fields},
            {"divCode": "wzxx_table", "nodeType": "table", "name": "LCDTable", "label": "物资信息"},
        ],
    }]}}
    runtime = _build_runtime()
    runtime._page = page
    restoration = TemplateRestoration(RuntimeTemplateAdapter(runtime))
    restoration.initialize(build_page_manifest({"data": {"uidata": [{"divCode": "listRoot"}]}}))

    def allocate_row():
        runtime._dynamic_template_payload = payload
        return {"action": "分配"}

    result = restoration.execute("table_row_action.click", allocate_row)

    assert bool(result.changes.get("dynamic_template")) is expected
    assert restoration.manifest.page.fieldid == ("root" if expected else "listRoot")
    if expected:
        assert any(region.label == "物资信息" for region in restoration.manifest.regions)
        assert runtime.peek_dynamic_template_payload() is None
    else:
        assert runtime.peek_dynamic_template_payload() is payload


def test_dynamic_template_column_label_does_not_prove_missing_table_is_ready(monkeypatch) -> None:
    class TargetFrame:
        def evaluate(self, _script, _identities):
            return {"root": False, "interactive": False, "root_count": 0, "interactive_count": 0}

    runtime = _build_runtime()
    runtime._page = _FakePage()
    runtime._page.frames = [TargetFrame()]
    runtime._action_completion_context = {"source_page_id": "root"}
    monkeypatch.setattr(runtime, "_scan_frame", lambda *_args: [{
        "label_text": "采购品目", "visible": True, "editable": True,
        "pointer_receivable": True, "in_dialog": True,
    }])
    payload = {"data": {"pageId": "selection_page", "uidata": [{
        "divCode": "root", "children": [{
            "divCode": "missing_table", "nodeType": "table", "name": "LCDTable", "children": [{
                "divCode": "column_template_id", "nodeType": "formItem", "name": "YDFInput",
                "label": "采购品目", "dataField": "itemName",
            }],
        }],
    }]}}

    assert runtime.dynamic_template_payload_can_apply_as_fallback(payload) is False


def test_dynamic_template_column_exclusion_preserves_same_identity_legacy_form_field() -> None:
    payload = {"data": {"uidata": [{"divCode": "root", "children": [
        {"divCode": "details", "nodeType": "table", "name": "LCDTable", "children": [{
            "divCode": "shared_field", "nodeType": "formItem", "name": "YDFInput",
            "label": "表格列", "dataField": "itemName",
        }]},
        {"fieldid": "shared_field", "nodeType": "formItem", "label": "普通表单字段"},
    ]}]}}

    assert runtime_module._dynamic_template_payload_form_field_identities(payload) == ["shared_field"]
    assert runtime_module._dynamic_template_payload_form_field_labels(payload) == ["普通表单字段"]


def test_dynamic_template_fallback_rejects_ambiguous_work_surfaces() -> None:
    class AmbiguousFrame:
        def evaluate(self, _script: str, _identities: list[str]) -> dict[str, int | bool]:
            return {"root": True, "interactive": True, "root_count": 2, "interactive_count": 2}

    runtime = _build_runtime()
    runtime._page = _FakePage()
    runtime._page.frames = [AmbiguousFrame()]
    runtime._action_completion_context = {"source_page_id": "root"}

    assert runtime.dynamic_template_payload_can_apply_as_fallback(
        {"data": {"pageId": "root", "uidata": [{"divCode": "editRoot"}]}}
    ) is False


@pytest.mark.parametrize(
    ("action", "before", "after", "signal"),
    [
        (
            "tab.click",
            {"foreground": "", "active_tabs": "基本信息", "active_tab_ids": "tab-basic", "table": "A", "busy": 0},
            {"foreground": "", "active_tabs": "明细信息", "active_tab_ids": "tab-detail", "table": "A", "busy": 0},
            "tab_active",
        ),
        (
            "query.search",
            {
                "foreground": "",
                "active_tabs": "列表",
                "target_table": "旧结果",
                "target_busy": 1,
            },
            {
                "foreground": "",
                "active_tabs": "列表",
                "target_table": "新结果",
                "target_busy": 0,
            },
            "target_component",
        ),
    ],
)
def test_action_completion_returns_dom_business_signal(
    monkeypatch,
    action: str,
    before: dict[str, object],
    after: dict[str, object],
    signal: str,
) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    states = iter([before, after])
    monkeypatch.setattr(runtime, "_capture_action_completion_state", lambda: next(states))
    monkeypatch.setattr(runtime, "_drain_buffered_notifications", lambda: [])
    monkeypatch.setattr(runtime, "_scan_notifications", lambda: [])
    monkeypatch.setattr(runtime, "begin_notification_capture", lambda: None)

    context = (
        {"target_table_fieldid": "main_table"}
        if action == "query.search"
        else {"tab": "明细信息", "tab_fieldid": "tab-detail"}
    )
    request = ActionCompletionRequest(action=action, context=context)
    runtime._prepare_action_completion(request)
    observation = runtime._observe_action_completion(request)

    assert observation.dom_signal == signal


@pytest.mark.parametrize("action", ["toolbar.click", "dialog.click", "action.click"])
@pytest.mark.parametrize("in_frame", [False, True])
def test_action_completion_tracks_clicked_form_closure(_popup_reference_page, monkeypatch, action, in_frame) -> None:
    page = _popup_reference_page
    page.set_content('''
        <button fieldid="save">保存</button>
        <div id="source" class="yy-ydf-modal-holder" style="position:fixed;top:100px;background:white">
          <div role="dialog"><button fieldid="confirm"
            onclick="document.querySelector('#source').remove()">确定</button></div>
        </div>
    ''')
    if in_frame:
        page.locator("#source").evaluate('''node => {
            node.innerHTML = '<iframe></iframe>';
            node.firstChild.srcdoc = `<div role="dialog"><button fieldid="confirm"
                onclick="parent.document.querySelector('#source').remove()">确定</button></div>`;
        }''')
        page.frame_locator("iframe").locator("button").wait_for()
    runtime = _build_runtime()
    runtime._page = page
    now = [0.0]
    monkeypatch.setattr(runtime, "_action_completion_now", lambda: now[0])
    monkeypatch.setattr(runtime, "_wait_action_completion_poll", lambda ms: now.__setitem__(0, now[0] + ms / 1000))
    clicks = {
        "toolbar.click": lambda: runtime.click_toolbar_action("确定", fieldid="confirm"),
        "dialog.click": lambda: runtime.click_dialog_button("确定"),
        "action.click": lambda: runtime.click_action_by_fieldid("confirm"),
    }
    result = ActionCompletion(runtime).execute(
        ActionCompletionRequest(action, {"action": "确定"}, deadline=1.0), clicks[action],
    )
    assert result.completion_signal == "foreground_closed"
    assert result.fallback_used is False
    assert result.wait_duration_ms < 1000
    assert page.locator("#source").count() == 0


@pytest.mark.parametrize("state", ["new", "ancestor", "error", "old", "disabled", "covered", "multiple", "unrelated_frame", "ordinary"])
def test_action_completion_confirmation_handoff(_popup_reference_page, monkeypatch, state) -> None:
    page = _popup_reference_page
    page.set_content('''<style>body { padding-top: 100px; }</style>
        <button fieldid="save" onclick="showConfirmation()">保存</button>
        <iframe style="position:absolute;top:400px"></iframe>''')
    page.evaluate('''state => {
        const html = `<div class="wui-modal ac-confirm" style="position:fixed;top:200px;background:white">
          <button class="wui-button-primary">确定</button><button>取消</button></div>`;
        if (state === 'old') document.body.insertAdjacentHTML('beforeend', html);
        window.showConfirmation = () => {
            if (state === 'old') return;
            if (state === 'unrelated_frame') { document.querySelector('iframe').srcdoc = html; return; }
            document.body.insertAdjacentHTML('beforeend', html);
            if (state === 'error') document.body.insertAdjacentHTML('beforeend',
                '<div role="alert" class="error">校验失败</div>');
            const dialog = document.querySelector('.ac-confirm');
            if (state === 'disabled') dialog.querySelector('button').disabled = true;
            if (state === 'ordinary') dialog.classList.remove('ac-confirm');
            if (state === 'multiple') document.body.insertAdjacentHTML('beforeend', html);
            if (state === 'covered') document.body.insertAdjacentHTML('beforeend',
                '<div style="position:fixed;inset:0;z-index:9999;background:white"></div>');
        };
    }''', state)
    if state == "ancestor":
        page.locator('button[fieldid="save"]').evaluate("node => node.remove()")
        page.locator("iframe").evaluate('''node => {
            node.srcdoc = '<button fieldid="save" style="margin-top:80px" onclick="parent.showConfirmation()">保存</button>';
        }''')
        page.frame_locator("iframe").locator("button").wait_for()
    runtime = _build_runtime()
    runtime._page = page
    now = [0.0]
    monkeypatch.setattr(runtime, "_action_completion_now", lambda: now[0])
    monkeypatch.setattr(runtime, "_wait_action_completion_poll", lambda ms: now.__setitem__(0, now[0] + ms / 1000))

    def execute():
        return ActionCompletion(runtime).execute(
            ActionCompletionRequest("toolbar.click", {"action": "保存"}, deadline=1.0),
            lambda: runtime.click_toolbar_action("保存", fieldid="save"),
        )

    if state in {"new", "ancestor", "error"}:
        result = execute()
        assert result.completion_signal == ("notification" if state == "error" else "confirmation_required")
        assert result.fallback_used is False
        assert bool(result.notifications) is (state == "error")
    else:
        with pytest.raises(TimeoutError, match="步骤期限"):
            execute()


@pytest.mark.parametrize("change", ["other", "text", "disabled_parent"])
def test_action_completion_requires_source_close_and_usable_return_surface(_popup_reference_page, monkeypatch, change) -> None:
    page = _popup_reference_page
    page.set_content('''
        <button id="save">保存</button><div id="other" role="dialog">其他窗口</div>
        <div id="source" class="yy-ydf-modal-holder" style="position:fixed;top:100px">
          <span id="title">明细</span><button fieldid="confirm" onclick="changeSurface()">确定</button>
        </div>
    ''')
    page.evaluate('''change => window.changeSurface = () => {
        if (change === 'other') document.querySelector('#other').remove();
        if (change === 'text') document.querySelector('#title').textContent = '已处理';
        if (change === 'disabled_parent') {
            document.querySelector('#save').disabled = true;
            document.querySelector('#source').remove();
        }
    }''', change)
    runtime = _build_runtime()
    runtime._page = page
    now = [0.0]
    monkeypatch.setattr(runtime, "_action_completion_now", lambda: now[0])
    monkeypatch.setattr(runtime, "_wait_action_completion_poll", lambda ms: now.__setitem__(0, now[0] + ms / 1000))
    with pytest.raises(TimeoutError, match="步骤期限"):
        ActionCompletion(runtime).execute(
            ActionCompletionRequest("toolbar.click", {"action": "确定"}, deadline=1.0),
            lambda: runtime.click_toolbar_action("确定", fieldid="confirm"),
        )


def test_action_completion_waits_for_save_after_confirmation_disappears(_popup_reference_page) -> None:
    page = _popup_reference_page
    page.set_content('''
        <button>保存</button>
        <div class="wui-modal ac-confirm" style="position:fixed;top:100px">
          <button onclick="this.parentElement.remove(); setTimeout(() => {
            document.body.insertAdjacentHTML('beforeend', '<div role=alert class=success>保存成功</div>');
          }, 1000)">确定</button>
        </div>
    ''')
    runtime = _build_runtime()
    runtime._page = page
    result = ActionCompletion(runtime).execute(
        ActionCompletionRequest("dialog.click", {"action": "确定"}, deadline=time.monotonic() + 5),
        lambda: runtime.click_dialog_button("确定"),
    )
    assert result.completion_signal == "notification"
    assert any(item.message == "保存成功" for item in result.notifications)


def test_action_completion_does_not_accept_generic_foreground_signature_change(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    states = iter(
        [
            {"foreground": "", "foreground_signature": "page:list", "active_tabs": "列表", "table": "A", "busy": 0},
            {"foreground": "新增窗口", "foreground_signature": "dialog:new", "active_tabs": "列表", "table": "A", "busy": 0},
        ]
    )
    monkeypatch.setattr(runtime, "_capture_action_completion_state", lambda: next(states))
    monkeypatch.setattr(runtime, "_drain_buffered_notifications", lambda: [])
    monkeypatch.setattr(runtime, "_scan_notifications", lambda: [])
    monkeypatch.setattr(runtime, "begin_notification_capture", lambda: None)

    request = ActionCompletionRequest(action="toolbar.click")
    runtime._prepare_action_completion(request)
    observation = runtime._observe_action_completion(request)

    assert observation.dom_signal == ""


def test_action_completion_accepts_explicit_foreground_identity(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    states = iter(
        [
            {"foreground": "", "foreground_signature": "page:list", "active_tabs": "列表", "table": "A", "busy": 0},
            {"foreground": "新增窗口", "foreground_signature": "frame-url::dialog:new", "active_tabs": "列表", "table": "A", "busy": 0},
        ]
    )
    monkeypatch.setattr(runtime, "_capture_action_completion_state", lambda: next(states))
    monkeypatch.setattr(runtime, "_drain_buffered_notifications", lambda: [])
    monkeypatch.setattr(runtime, "_scan_notifications", lambda: [])
    monkeypatch.setattr(runtime, "begin_notification_capture", lambda: None)

    request = ActionCompletionRequest(
        action="toolbar.click",
        context={"foreground_identity": "frame-url::dialog:new"},
    )
    runtime._prepare_action_completion(request)
    observation = runtime._observe_action_completion(request)

    assert observation.dom_signal == "foreground_state"


def test_action_completion_ignores_foreground_text_change_without_layer_change(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    states = iter(
        [
            {
                "foreground": "正在处理",
                "foreground_signature": "dialog:edit",
                "active_tabs": "列表",
                "table": "A",
                "busy": 0,
            },
            {
                "foreground": "保存中",
                "foreground_signature": "dialog:edit",
                "active_tabs": "列表",
                "table": "A",
                "busy": 0,
            },
        ]
    )
    monkeypatch.setattr(runtime, "_capture_action_completion_state", lambda: next(states))
    monkeypatch.setattr(runtime, "_drain_buffered_notifications", lambda: [])
    monkeypatch.setattr(runtime, "_scan_notifications", lambda: [])
    monkeypatch.setattr(runtime, "begin_notification_capture", lambda: None)

    request = ActionCompletionRequest(action="toolbar.click")
    runtime._prepare_action_completion(request)
    observation = runtime._observe_action_completion(request)

    assert observation.dom_signal == ""


def test_query_completion_ignores_global_busy_cycle_without_exact_target(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    states = iter(
        [
            {"foreground": "", "active_tabs": "列表", "table": "A", "busy": 0},
            {"foreground": "", "active_tabs": "列表", "table": "A", "busy": 1},
            {"foreground": "", "active_tabs": "列表", "table": "A", "busy": 0},
        ]
    )
    monkeypatch.setattr(runtime, "_capture_action_completion_state", lambda: next(states))
    monkeypatch.setattr(runtime, "_drain_buffered_notifications", lambda: [])
    monkeypatch.setattr(runtime, "_scan_notifications", lambda: [])
    monkeypatch.setattr(runtime, "begin_notification_capture", lambda: None)

    request = ActionCompletionRequest(action="query.search")
    runtime._prepare_action_completion(request)

    assert runtime._observe_action_completion(request).dom_signal == ""
    assert runtime._observe_action_completion(request).dom_signal == ""


def test_query_completion_uses_explicit_target_table_state(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    states = iter(
        [
            {
                "foreground": "",
                "active_tabs": "列表",
                "table": "背景旧结果",
                "target_table": "目标旧结果",
                "busy": 0,
                "target_busy": 0,
            },
            {
                "foreground": "",
                "active_tabs": "列表",
                "table": "背景新结果",
                "target_table": "目标旧结果",
                "busy": 0,
                "target_busy": 0,
            },
            {
                "foreground": "",
                "active_tabs": "列表",
                "table": "背景新结果",
                "target_table": "目标新结果",
                "busy": 0,
                "target_busy": 0,
            },
        ]
    )
    monkeypatch.setattr(runtime, "_capture_action_completion_state", lambda: next(states))
    monkeypatch.setattr(runtime, "_drain_buffered_notifications", lambda: [])
    monkeypatch.setattr(runtime, "_scan_notifications", lambda: [])
    monkeypatch.setattr(runtime, "begin_notification_capture", lambda: None)

    request = ActionCompletionRequest(
        action="query.search",
        context={"target_table_fieldid": "target_table"},
    )
    runtime._prepare_action_completion(request)

    assert runtime._observe_action_completion(request).dom_signal == ""
    assert runtime._observe_action_completion(request).dom_signal == "target_component"


@pytest.mark.parametrize(
    ('variant', 'expected'),
    [
        ('success', 'target_component'), ('entity_query', 'target_component'),
        ('pending', ''), ('old', ''), ('other_entity', ''), ('other_domain', ''),
        ('other_frame', ''), ('save', ''), ('http_error', ''), ('business_error', ''),
        ('not_ready', ''), ('busy', ''), ('missing_identity', ''), ('next_action', ''),
        ('network_error', ''), ('external_origin', ''), ('false_code', ''),
    ],
)
def test_query_completion_correlates_finished_response_for_unchanged_table(monkeypatch, variant, expected) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    frame = object()
    state = {'target_table': '同一批业务行', 'target_busy': int(variant == 'busy'),
             'target_ready': variant != 'not_ready'}
    monkeypatch.setattr(runtime, '_capture_action_completion_state', lambda: dict(state))
    monkeypatch.setattr(runtime, '_scan_notifications', lambda: [])
    monkeypatch.setattr(runtime, 'begin_notification_capture', lambda: None)
    identity = {'entity_uri': 'AMM.AMM.material', 'domain': 'material', 'busi_obj': 'material'}
    context = {'target_table_fieldid': 'table', 'target_table_query': identity}
    if variant == 'missing_identity':
        context.pop('target_table_query')
    response = SimpleNamespace(status=500 if variant == 'http_error' else 200,
                               json=lambda: {'code': False if variant == 'false_code' else 500 if variant == 'business_error' else 200,
                                             'data': {'recordList': []}})
    request = SimpleNamespace(
        url=f'https://example.yonyougov.top/{"other" if variant == "other_domain" else "material"}-be/bill/{"save" if variant == "save" else "list"}',
        method='POST', frame=object() if variant == 'other_frame' else frame,
        post_data_json={'busiObj': 'other' if variant == 'other_entity' else 'material'},
        response=lambda: response,
    )
    if variant == 'entity_query':
        request.url = 'https://example.yonyougov.top/material-be/ybill/query'
        request.post_data_json = {'fullName': 'AMM.AMM.material'}
    if variant == 'external_origin':
        request.url = 'https://other.test/material-be/bill/list'
    if variant == 'old':
        runtime._capture_network_request(request)
    runtime._acquire_action_completion()
    runtime._prepare_action_completion(ActionCompletionRequest('query.search', context=context))
    runtime._query_completion_frame = frame
    if variant != 'old':
        runtime._capture_network_request(request)
    if variant == 'network_error':
        runtime._capture_network_failure(request)
    elif variant != 'pending':
        runtime._capture_network_finished(request)
    if variant == 'next_action':
        runtime._release_action_completion()
        runtime._prepare_action_completion(ActionCompletionRequest('query.search', context=context))

    assert runtime._action_dom_completion_signal('query.search') == expected


@pytest.mark.parametrize(('content', 'ready'), [
    ('<tr><td>复印纸</td></tr>', True),
    ('<tr class="wui-table-placeholder"><td>暂无数据</td></tr>', True),
    ('', False), ('<tr><td>加载中...</td></tr>', False),
])
def test_query_completion_requires_observable_target_terminal_state(_popup_reference_page, content, ready) -> None:
    page = _popup_reference_page
    page.set_content(f'<table fieldid="target" style="width:400px;height:40px"><tbody>{content}</tbody></table>')
    runtime = _build_runtime()
    runtime._page = page
    runtime._action_completion_context = {'target_table_fieldid': 'target'}

    state = runtime._capture_action_completion_state()

    assert state['target_ready'] is ready
    assert runtime._query_completion_frame == page.main_frame


def test_query_completion_reuses_resolved_scope_despite_duplicate_fieldid_markers(_popup_reference_page) -> None:
    page = _popup_reference_page
    page.set_content('''
      <div fieldid="target">重复布局标记</div>
      <div class="wui-table" data-ydf-table-scope-token="chosen" fieldid="target">
        <table><tbody><tr><td>复印纸</td></tr></tbody></table>
      </div>''')
    runtime = _build_runtime()
    runtime._page = page
    runtime._action_completion_context = {'target_table_fieldid': 'target', 'target_table_token': 'chosen'}

    state = runtime._capture_action_completion_state()

    assert state['target_ready'] is True
    assert runtime._query_completion_frame == page.main_frame


def test_query_completion_observes_fast_response_during_click_wait(_popup_reference_page, request) -> None:
    page = _popup_reference_page.context.browser.new_page(viewport={"width": 1200, "height": 800})
    request.addfinalizer(page.close)
    page.route('**/bill', lambda route: route.fulfill(content_type='text/html; charset=utf-8', body='''
      <button fieldid="query_btn" style="margin-top:100px" onclick="query()">查询</button>
      <table fieldid="target" data-ydf-table-scope-token="chosen"><tbody><tr><td>复印纸</td></tr></tbody></table>
      <script>async function query(){await fetch('/material-be/bill/list',{method:'POST',
        headers:{'Content-Type':'application/json'},body:JSON.stringify({busiObj:'material'})});
        document.querySelector('tbody').innerHTML='<tr><td>复印纸</td></tr>';}</script>'''))
    page.route('**/material-be/bill/list', lambda route: route.fulfill(
        json={'code': 200, 'data': {'recordList': [{'name': '复印纸'}]}},
    ))
    page.goto('https://example.yonyougov.top/bill')
    runtime = _build_runtime()
    runtime._page = page
    page.on('request', runtime._capture_network_request)
    page.on('requestfinished', runtime._capture_network_finished)

    result = ActionCompletion(runtime).execute(ActionCompletionRequest('query.search', context={
        'target_table_fieldid': 'target', 'target_table_token': 'chosen',
        'target_table_query': {'entity_uri': 'AMM.AMM.material', 'domain': 'material', 'busi_obj': 'material'},
    }), runtime.click_query_action)

    assert result.completion_signal == 'target_component'
    assert result.fallback_used is False
    assert page.locator('tbody').inner_text() == '复印纸'


def test_capture_action_completion_state_includes_target_table_state() -> None:
    class CompletionFrame:
        url = "https://example.yonyougov.top/bill"

        def evaluate(self, _script: str, *_args):
            return {
                "foreground": "",
                "foreground_signature": "",
                "active_tabs": "列表",
                "table": "背景结果",
                "busy": 0,
                "target_table": "目标结果",
                "target_busy": 1,
            }

    runtime = _build_runtime()
    runtime._page = _FakePage()
    runtime._page.frames = [CompletionFrame()]
    runtime._action_completion_context = {"target_table_fieldid": "target_table"}

    state = runtime._capture_action_completion_state()

    assert state["target_table"] == "目标结果"
    assert state["target_busy"] == 1


def test_capture_action_completion_state_includes_exact_ydf_step_target_state() -> None:
    class CompletionFrame:
        url = "https://example.yonyougov.top/bill"

        def evaluate(self, script: str, *_args):
            assert "targetTabFieldid" in script
            assert ".wui-steps-item-wrap" in script
            assert ".wui-steps-item-process" in script
            return {
                "foreground": "",
                "foreground_signature": "",
                "active_tabs": "",
                "active_tab_ids": "",
                "table": "",
                "busy": 0,
                "target_table": "",
                "target_busy": 0,
                "target_step_active": True,
                "target_step_count": 1,
            }

    runtime = _build_runtime()
    runtime._page = _FakePage()
    runtime._page.frames = [CompletionFrame()]
    runtime._action_completion_context = {"tab_fieldid": "step_wait_submit"}

    state = runtime._capture_action_completion_state()

    assert state["target_step_active"] is True


def test_capture_action_completion_state_rejects_duplicate_ydf_steps_across_frames() -> None:
    class CompletionFrame:
        url = "https://example.yonyougov.top/bill"

        def __init__(self, state: dict[str, object]) -> None:
            self.state = state

        def evaluate(self, _script: str, *_args):
            return self.state

    runtime = _build_runtime()
    runtime._page = _FakePage()
    runtime._page.frames = [
        CompletionFrame({"target_step_active": None, "target_step_count": 2}),
        CompletionFrame({"target_step_active": True, "target_step_count": 1}),
    ]
    runtime._action_completion_context = {"tab_fieldid": "step_wait_submit"}

    state = runtime._capture_action_completion_state()

    assert state["target_step_active"] is None


def test_action_completion_accepts_exact_ydf_step_target_transition(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    states = iter(
        [
            {"foreground": "", "active_tabs": "", "active_tab_ids": "", "target_step_active": False},
            {"foreground": "", "active_tabs": "", "active_tab_ids": "", "target_step_active": True},
        ]
    )
    monkeypatch.setattr(runtime, "_capture_action_completion_state", lambda: next(states))
    monkeypatch.setattr(runtime, "_drain_buffered_notifications", lambda: [])
    monkeypatch.setattr(runtime, "_scan_notifications", lambda: [])
    monkeypatch.setattr(runtime, "begin_notification_capture", lambda: None)

    request = ActionCompletionRequest(
        action="tab.click",
        context={"tab": "待提交", "tab_fieldid": "step_wait_submit"},
    )
    runtime._prepare_action_completion(request)
    observation = runtime._observe_action_completion(request)

    assert observation.dom_signal == "tab_active"


def test_action_completion_does_not_accept_another_ydf_step_as_target_completion(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    states = iter(
        [
            {
                "foreground": "",
                "active_tabs": "草稿",
                "active_tab_ids": "step_draft",
                "target_step_active": False,
            },
            {
                "foreground": "",
                "active_tabs": "待提交",
                "active_tab_ids": "step_wait_submit",
                "target_step_active": False,
            },
        ]
    )
    monkeypatch.setattr(runtime, "_capture_action_completion_state", lambda: next(states))
    monkeypatch.setattr(runtime, "_drain_buffered_notifications", lambda: [])
    monkeypatch.setattr(runtime, "_scan_notifications", lambda: [])
    monkeypatch.setattr(runtime, "begin_notification_capture", lambda: None)

    request = ActionCompletionRequest(
        action="tab.click",
        context={"tab": "待提交", "tab_fieldid": "step_wait_submit"},
    )
    runtime._prepare_action_completion(request)
    observation = runtime._observe_action_completion(request)

    assert observation.dom_signal == ""


@pytest.mark.parametrize(
    ("tab_fieldid", "expected_signal"),
    [
        ("tab_wait_review", "tab_already_active"),
        ("", ""),
    ],
)
def test_action_completion_accepts_only_exact_bound_tab_already_active(
    monkeypatch,
    tab_fieldid: str,
    expected_signal: str,
) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    states = iter(
        [
            {"foreground": "", "active_tabs": "待审核", "active_tab_ids": "tab_wait_review"},
            {"foreground": "", "active_tabs": "待审核", "active_tab_ids": "tab_wait_review"},
        ]
    )
    monkeypatch.setattr(runtime, "_capture_action_completion_state", lambda: next(states))
    monkeypatch.setattr(runtime, "_drain_buffered_notifications", lambda: [])
    monkeypatch.setattr(runtime, "_scan_notifications", lambda: [])
    monkeypatch.setattr(runtime, "begin_notification_capture", lambda: None)

    request = ActionCompletionRequest(
        action="tab.click",
        context={"tab": "待审核", "tab_fieldid": tab_fieldid},
    )
    runtime._prepare_action_completion(request)
    observation = runtime._observe_action_completion(request)

    assert observation.dom_signal == expected_signal


def test_action_completion_accepts_exact_ydf_step_already_active(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    states = iter(
        [
            {"foreground": "", "active_tabs": "", "active_tab_ids": "", "target_step_active": True},
            {"foreground": "", "active_tabs": "", "active_tab_ids": "", "target_step_active": True},
        ]
    )
    monkeypatch.setattr(runtime, "_capture_action_completion_state", lambda: next(states))
    monkeypatch.setattr(runtime, "_drain_buffered_notifications", lambda: [])
    monkeypatch.setattr(runtime, "_scan_notifications", lambda: [])
    monkeypatch.setattr(runtime, "begin_notification_capture", lambda: None)

    request = ActionCompletionRequest(
        action="tab.click",
        context={"tab": "待审核", "tab_fieldid": "tab_wait_review"},
    )
    runtime._prepare_action_completion(request)
    observation = runtime._observe_action_completion(request)

    assert observation.dom_signal == "tab_already_active"



@pytest.mark.parametrize(
    ("wait_method", "args"),
    [
        ("_wait_for_editable_table_cell_backfill", ("",)),
        ("_wait_for_editable_table_cell_value", ("expected",)),
    ],
)
def test_editable_table_backfill_reads_and_sleeps_within_total_budget(
    monkeypatch,
    wait_method: str,
    args: tuple[str],
) -> None:
    now = [0.0]
    read_timeouts: list[int] = []
    sleeps: list[int] = []

    class _BudgetPage:
        def wait_for_timeout(self, timeout_ms: int) -> None:
            sleeps.append(timeout_ms)
            now[0] += timeout_ms / 1000

    class _Cell:
        def evaluate(self, _script: str, *, timeout: int) -> str:
            read_timeouts.append(timeout)
            return ""

    runtime = _build_runtime()
    runtime._page = _BudgetPage()
    monkeypatch.setattr(runtime_module.time, "monotonic", lambda: now[0])

    getattr(runtime, wait_method)(_Cell(), *args, timeout_ms=50)

    assert read_timeouts
    assert all(0 < timeout <= 50 for timeout in read_timeouts)
    assert sleeps
    assert sum(sleeps) <= 50


def test_scan_frame_preserves_pointer_receivability_and_identity_root() -> None:
    class ScanFrame:
        name = "main"
        url = "https://example.yonyougov.top/bill"

        def evaluate(self, script: str, frame_index: int):
            assert "elementFromPoint" in script
            assert frame_index == 2
            return [{"fieldid": "field", "pointer_receivable": True, "_identity_root_index": 3}]

    runtime = _build_runtime()

    items = runtime._scan_frame(ScanFrame(), 2)

    assert items == [{
        "fieldid": "field",
        "pointer_receivable": True,
        "identity_root": "2:3",
        "frame_name": "main",
        "frame_url": "https://example.yonyougov.top/bill",
    }]


def test_open_menu_does_not_wait_for_global_network_idle(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    monkeypatch.setattr(runtime, "_apply_api_session_cookies", lambda: None)
    monkeypatch.setattr(
        runtime,
        "_wait_ready",
        lambda: pytest.fail("菜单打开不得等待全页 networkidle"),
    )

    runtime.open_menu(
        MenuTarget(
            menu_code="PM_INIT",
            menu_name="项目立项",
            path=["项目管理", "项目立项"],
            service_code="global00_-1_PM_INIT",
        )
    )

    assert runtime._page.goto_calls == [
        "https://example.yonyougov.top/#/service/global00_-1_PM_INIT"
    ]


@pytest.mark.parametrize("method_name", ["click_tab_action", "click_query_action", "click_dialog_button"])
def test_component_business_actions_do_not_wait_for_global_network_idle(
    monkeypatch,
    method_name: str,
) -> None:
    runtime = _build_runtime()
    clicked: list[object] = []
    bound = object()
    monkeypatch.setattr(runtime, "_wait_ready", lambda: pytest.fail("组件动作不得等待全页 networkidle"))
    monkeypatch.setattr(runtime, "click", clicked.append)
    monkeypatch.setattr(runtime, "_resolve_visible_tab_action", lambda *_args, **_kwargs: bound)
    monkeypatch.setattr(runtime, "_find_first_visible_selector", lambda *_args, **_kwargs: "[data-action]")
    monkeypatch.setattr(runtime, "_build_visible_action_bound_element", lambda *_args, **_kwargs: bound)

    if method_name == "click_tab_action":
        runtime.click_tab_action("明细")
    elif method_name == "click_query_action":
        runtime.click_query_action("查询")
    else:
        runtime.click_dialog_button("确定")

    assert clicked == [bound]


class _FakeNotificationClosePage:
    def __init__(self, result: dict[str, object]) -> None:
        self.result = result
        self.payloads: list[dict[str, object]] = []
        self.scripts: list[str] = []
        self.waits: list[int] = []
        self.clicked_selectors: list[str] = []

    def evaluate(self, script: str, payload: dict[str, object] | None = None):
        self.scripts.append(script)
        if payload is not None:
            self.payloads.append(payload)
        assert ".ant-modal-confirm" in script
        assert "root.querySelectorAll" in script
        return self.result

    def locator(self, selector: str):
        page = self

        class _Locator:
            @property
            def first(self):
                return self

            def click(self, timeout: int = 0) -> None:
                page.clicked_selectors.append(selector)

        return _Locator()

    def wait_for_timeout(self, timeout: int) -> None:
        self.waits.append(timeout)


def test_playwright_runtime_close_notification_returns_close_result() -> None:
    runtime = _build_runtime()
    page = _FakeNotificationClosePage(
        {
            "closed": True,
            "closed_notification": {"type": "error", "message": "请联系管理员"},
            "remaining_notifications": [],
            "close_action": "close-icon",
        }
    )
    runtime._page = page

    result = runtime.close_notification(expected_type="error", contains="请联系管理员")

    assert result == {
        "closed_notification": {"type": "error", "message": "请联系管理员"},
        "remaining_notifications": [],
        "close_action": "close-icon",
    }
    assert page.payloads == [
        {
            "expectedType": "error",
            "contains": "请联系管理员",
            "equals": "",
            "message": "",
            "label": "",
        }
    ]
    assert page.waits == [300]


def test_playwright_runtime_close_notification_passes_explicit_button_label() -> None:
    runtime = _build_runtime()
    page = _FakeNotificationClosePage(
        {
            "closed": True,
            "closed_notification": {"type": "error", "message": "请联系管理员"},
            "remaining_notifications": [{"type": "warning", "message": "请确认当前数据"}],
            "close_action": "confirm-button:我知道了",
        }
    )
    runtime._page = page

    result = runtime.close_notification(expected_type="error", contains="请联系管理员", label="我知道了")

    assert result["close_action"] == "confirm-button:我知道了"
    assert result["remaining_notifications"] == [{"type": "warning", "message": "请确认当前数据"}]
    assert page.payloads[-1]["label"] == "我知道了"


def test_playwright_runtime_close_notification_covers_notice_close_icons() -> None:
    script = runtime_module._NOTIFICATION_CLOSE_SCRIPT

    assert ".ant-notification-notice-close" in script
    assert ".ant-notification-notice-close-icon" in script
    assert '[class*="notice-close"]' in script


def test_playwright_runtime_close_notification_reports_clicked_selector_when_still_visible(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakeNotificationClosePage(
        {
            "closed": True,
            "closed_notification": {"type": "error", "message": "异常信息：未配置业务规则,请联系管理员"},
            "remaining_notifications": [],
            "close_action": "close-icon:.ant-notification-notice-close",
        }
    )
    monkeypatch.setattr(
        runtime,
        "_scan_notifications",
        lambda: [{"type": "error", "message": "异常信息：未配置业务规则,请联系管理员"}],
    )

    with pytest.raises(RuntimeError) as exc:
        runtime.close_notification(expected_type="error", contains="请联系管理员")

    assert "页面提示关闭后仍可见" in str(exc.value)
    assert "close_action=close-icon:.ant-notification-notice-close" in str(exc.value)


def test_playwright_runtime_close_notification_clicks_marked_close_selector(monkeypatch) -> None:
    runtime = _build_runtime()
    selector = '[data-ydf-browser-notification-close-target="notification-close-1"]'
    page = _FakeNotificationClosePage(
        {
            "closed": True,
            "closed_notification": {"type": "error", "message": "异常信息：未配置业务规则,请联系管理员"},
            "remaining_notifications": [],
            "close_action": "close-icon:.wui-message-notice-close",
            "close_selector": selector,
        }
    )
    runtime._page = page
    monkeypatch.setattr(runtime, "_scan_notifications", lambda: [])

    runtime.close_notification(expected_type="error", contains="请联系管理员")

    assert page.clicked_selectors == [selector]


@pytest.mark.parametrize(
    ("reason", "message"),
    [
        ("not_found", "未找到匹配页面提示"),
        ("close_entry_missing", "未找到页面提示关闭入口"),
        ("still_visible", "页面提示关闭后仍可见"),
    ],
)
def test_playwright_runtime_close_notification_reports_failures(reason: str, message: str) -> None:
    runtime = _build_runtime()
    runtime._page = _FakeNotificationClosePage(
        {
            "closed": False,
            "reason": reason,
            "matched_notification": {"type": "error", "message": "请联系管理员"},
            "actual_notifications": [{"type": "error", "message": "请联系管理员"}],
            "diagnostic": "候选=无",
        }
    )

    with pytest.raises(RuntimeError) as exc:
        runtime.close_notification(expected_type="error", contains="请联系管理员")

    assert message in str(exc.value)
    assert "请联系管理员" in str(exc.value)


class _FakeTextLocator:
    def __init__(self, text: str, visible: bool = True) -> None:
        self.text = text
        self.visible = visible

    @property
    def first(self) -> "_FakeTextLocator":
        return self

    def count(self) -> int:
        return 1

    def nth(self, _index: int) -> "_FakeTextLocator":
        return self

    def is_visible(self, timeout: int = 0) -> bool:
        return self.visible

    def inner_text(self, timeout: int = 0) -> str:
        return self.text


class _FakeTextPage:
    def __init__(self, body_text: str, frames: list["_FakeTextPage"] | None = None) -> None:
        self.body_text = body_text
        self.frames = frames or []
        self.waits: list[int] = []

    def locator(self, selector: str) -> _FakeTextLocator:
        if selector == "body":
            return _FakeTextLocator(self.body_text)
        return _FakeTextLocator("", visible=False)

    def evaluate(self, _script: str) -> str:
        return self.body_text

    def wait_for_timeout(self, timeout: int) -> None:
        self.waits.append(timeout)


class _FakeAttachmentInput:
    def __init__(self) -> None:
        self.files: list[str] = []

    def set_input_files(self, file_path: str, timeout: int = 0) -> None:
        self.files.append(file_path)


class _FakeAttachmentPage:
    frames: list[object] = []

    def __init__(self, *, filename: str, states: list[dict[str, object]] | None = None) -> None:
        self.filename = filename
        self.states = list(states or [])
        self.input = _FakeAttachmentInput()
        self.waits: list[int] = []
        self.evaluate_payloads: list[object] = []
        self.locator_selectors: list[str] = []

    def evaluate(self, script: str, payload=None):
        self.evaluate_payloads.append(payload)
        if "view-switch" in script:
            return "card"
        if isinstance(payload, dict) and payload.get("filename"):
            if self.states:
                return self.states.pop(0)
            return {
                "completed": True,
                "signal": "file-row",
                "text": self.filename,
                "root_selector": '[fieldid="fjxx"]',
            }
        if "input[type=\"file\"]" in script or "input[type='file']" in script:
            return {
                "input_selector": '[data-ydf-browser-attachment-input="target"]',
                "root_selector": '[fieldid="fjxx"]',
                "label": "底稿附件",
                "fieldid": "fjxx",
                "allowed_extensions": ["pdf", "doc", "docx"],
            }
        return self.filename

    def locator(self, selector: str):
        self.locator_selectors.append(selector)
        return self.input

    def wait_for_timeout(self, timeout: int) -> None:
        self.waits.append(timeout)


class _FakeEditableCell:
    def __init__(self) -> None:
        self.clicked = False
        self.dblclicked = False
        self.scrolled = False
        self.actions: list[str] = []

    def scroll_into_view_if_needed(self, timeout: int = 0) -> None:
        self.scrolled = True

    def click(self, timeout: int = 0) -> None:
        self.clicked = True
        self.actions.append("click")

    def dblclick(self, timeout: int = 0) -> None:
        self.dblclicked = True
        self.actions.append("dblclick")

    def evaluate(self, _script: str, *_args):
        self.actions.append("evaluate")
        return None


class _FakeEditableSelectorContext:
    def __init__(self, name: str, selector: str = "") -> None:
        self.name = name
        self.selector = selector
        self.calls: list[dict[str, object]] = []

    def evaluate(self, script: str, payload=None):
        self.calls.append({"script": script, "payload": payload})
        if script == _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT:
            return self.selector
        if "window.__ydfEditableTableCellDebug" in script:
            return {"context": self.name}
        return None


class _FakeEditableSelectorPage(_FakeEditableSelectorContext):
    def __init__(self, selector: str, frames: list[_FakeEditableSelectorContext]) -> None:
        super().__init__("page", selector)
        self.frames = frames
        self.waits: list[int] = []

    def wait_for_timeout(self, timeout: int) -> None:
        self.waits.append(timeout)


class _FakeEditableAddRowContext:
    def __init__(
        self,
        name: str,
        result: dict[str, object] | list[dict[str, object] | None] | None = None,
    ) -> None:
        self.name = name
        self.result = result
        self.calls: list[dict[str, object]] = []

    def evaluate(self, script: str, payload=None):
        self.calls.append({"script": script, "payload": payload})
        if script == _EDITABLE_TABLE_ADD_ROW_SCRIPT:
            if isinstance(self.result, list):
                return self.result.pop(0) if self.result else None
            return self.result
        return None


class _FakeEditableAddRowPage(_FakeEditableAddRowContext):
    def __init__(
        self,
        result: dict[str, object] | list[dict[str, object] | None] | None,
        frames: list[_FakeEditableAddRowContext],
    ) -> None:
        super().__init__("page", result)
        self.frames = frames
        self.waits: list[int] = []

    def wait_for_timeout(self, timeout: int) -> None:
        self.waits.append(timeout)


def test_playwright_runtime_add_editable_table_row_searches_child_frames_first() -> None:
    runtime = _build_runtime()
    child = _FakeEditableAddRowContext("child", {"label": "新增", "table": "销售商品/服务信息"})
    page = _FakeEditableAddRowPage(None, [child])
    runtime._page = page

    result = runtime.add_editable_table_row(label="新增", table="销售商品/服务信息")

    assert result == {"label": "新增", "table": "销售商品/服务信息"}
    assert [call["payload"] for call in child.calls if call["script"] == _EDITABLE_TABLE_ADD_ROW_SCRIPT] == [
        {"label": "新增", "table": "销售商品/服务信息", "tableFieldid": "", "tableColumns": []}
    ]
    assert [call["script"] for call in page.calls if call["script"] == _EDITABLE_TABLE_ADD_ROW_SCRIPT] == []
    assert page.waits == [150, 800]


def test_playwright_runtime_add_editable_table_row_passes_table_identity_to_script() -> None:
    runtime = _build_runtime()
    child = _FakeEditableAddRowContext(
        "child",
        {"label": "新增", "table": "缴库明细表格", "table_fieldid": "treasuryDetailTable"},
    )
    page = _FakeEditableAddRowPage(None, [child])
    runtime._page = page

    result = runtime.add_editable_table_row(
        label="新增",
        table="缴库明细表格",
        table_fieldid="treasuryDetailTable",
        table_columns=["缴款金额", "政府非税收入项目"],
    )

    assert result["table_fieldid"] == "treasuryDetailTable"
    assert [call["payload"] for call in child.calls if call["script"] == _EDITABLE_TABLE_ADD_ROW_SCRIPT] == [
        {
            "label": "新增",
            "table": "缴库明细表格",
            "tableFieldid": "treasuryDetailTable",
            "tableColumns": ["缴款金额", "政府非税收入项目"],
        }
    ]


def test_playwright_runtime_add_editable_table_row_passes_resolved_scope_token_to_script() -> None:
    runtime = _build_runtime()
    child = _FakeEditableAddRowContext(
        "child",
        {"label": "新增", "table": "需求调查成员", "table_fieldid": "lcdTable_upDemandSurveyMember"},
    )
    page = _FakeEditableAddRowPage(None, [child])
    runtime._page = page
    scope = ResolvedTableScope(
        label="需求调查成员",
        region_fieldid="lcdTable_upDemandSurveyMember",
        runtime_fieldid="lcdTable_upDemandSurveyMember",
        foreground=True,
        columns=("序号", "姓名"),
        required_columns=(),
        token="member-scope-0",
        evidence=(),
    )

    runtime.add_editable_table_row(label="新增", table_scope=scope)

    payload = next(call["payload"] for call in child.calls if call["script"] == _EDITABLE_TABLE_ADD_ROW_SCRIPT)
    assert payload["tableScopeToken"] == "member-scope-0"


def test_playwright_runtime_add_editable_table_row_retries_after_unchanged_existing_rows(monkeypatch) -> None:
    runtime = _build_runtime()
    calls: list[str] = []
    first = {
        "label": "新增",
        "table": "需求清单",
        "table_fieldid": "cgbd_table",
        "row_state_before": {"dataRowCount": 1, "rowTexts": ["1 已有行"]},
        "row_state": {"dataRowCount": 1, "rowTexts": ["1 已有行"]},
        "row_state_changed": False,
        "row_state_reliable": True,
    }
    second = {
        "label": "新增",
        "table": "需求清单",
        "table_fieldid": "cgbd_table",
        "row_state_before": {"dataRowCount": 1, "rowTexts": ["1 已有行"]},
        "row_state": {"dataRowCount": 2, "rowTexts": ["1 已有行", "2"]},
        "row_state_changed": True,
        "row_state_reliable": True,
    }
    page = _FakeEditableAddRowPage([first, second], [])
    runtime._page = page
    monkeypatch.setattr(
        runtime,
        "_settle_editable_table_add_row_interactions",
        lambda: calls.append("settle"),
        raising=False,
    )

    result = runtime.add_editable_table_row(label="新增", table="需求清单", table_fieldid="cgbd_table")

    assert result["row_state_changed"] is True
    assert result["retry_count"] == 1
    assert result["first_attempt"]["row_state_changed"] is False
    assert calls == ["settle", "settle"]
    assert [call["payload"] for call in page.calls if call["script"] == _EDITABLE_TABLE_ADD_ROW_SCRIPT] == [
        {"label": "新增", "table": "需求清单", "tableFieldid": "cgbd_table", "tableColumns": []},
        {"label": "新增", "table": "需求清单", "tableFieldid": "cgbd_table", "tableColumns": []},
    ]


def test_playwright_runtime_add_editable_table_row_reports_retry_when_rows_still_unchanged(monkeypatch) -> None:
    runtime = _build_runtime()
    calls: list[str] = []
    unchanged = {
        "label": "新增",
        "table": "需求清单",
        "table_fieldid": "cgbd_table",
        "row_state_before": {"dataRowCount": 1, "rowTexts": ["1 已有行"]},
        "row_state": {"dataRowCount": 1, "rowTexts": ["1 已有行"]},
        "row_state_changed": False,
        "row_state_reliable": True,
    }
    page = _FakeEditableAddRowPage([dict(unchanged), dict(unchanged)], [])
    runtime._page = page
    monkeypatch.setattr(
        runtime,
        "_settle_editable_table_add_row_interactions",
        lambda: calls.append("settle"),
        raising=False,
    )

    result = runtime.add_editable_table_row(label="新增", table="需求清单", table_fieldid="cgbd_table")

    assert result["row_state_changed"] is False
    assert result["retry_count"] == 1
    assert result["first_attempt"]["row_state_changed"] is False
    assert result["row_state"]["dataRowCount"] == 1
    assert calls == ["settle", "settle"]


def test_playwright_runtime_add_editable_table_row_does_not_retry_unreliable_rows(monkeypatch) -> None:
    runtime = _build_runtime()
    calls: list[str] = []
    unreliable = {
        "label": "新增",
        "table": "调入方",
        "table_fieldid": "table2",
        "row_state_before": {"dataRowCount": 2, "rowTexts": ["1 其他表格行"]},
        "row_state": {"dataRowCount": 2, "rowTexts": ["1 其他表格行"]},
        "row_state_changed": False,
        "row_state_reliable": False,
        "validation_root_source": "placeholder-unresolved",
        "chosen_candidate": {"className": "ydf-table-placeholder-add-button"},
    }
    page = _FakeEditableAddRowPage([unreliable, {"label": "新增", "row_state_changed": True}], [])
    runtime._page = page
    monkeypatch.setattr(
        runtime,
        "_settle_editable_table_add_row_interactions",
        lambda: calls.append("settle"),
        raising=False,
    )

    result = runtime.add_editable_table_row(label="新增", table="调入方", table_fieldid="table2")

    assert result["row_state_reliable"] is False
    assert "retry_count" not in result
    assert calls == ["settle"]
    assert [call["payload"] for call in page.calls if call["script"] == _EDITABLE_TABLE_ADD_ROW_SCRIPT] == [
        {"label": "新增", "table": "调入方", "tableFieldid": "table2", "tableColumns": []}
    ]


def test_playwright_runtime_add_editable_table_row_accepts_empty_placeholder_growth(monkeypatch) -> None:
    runtime = _build_runtime()
    calls: list[str] = []
    added = {
        "label": "新增",
        "table": "调入方",
        "table_fieldid": "table2",
        "row_state_before": {"dataRowCount": 0, "rowTexts": [], "empty": True},
        "row_state": {"dataRowCount": 1, "rowTexts": ["1 新增行"]},
        "row_state_changed": True,
        "row_state_reliable": True,
        "validation_root_source": "target-identity",
        "chosen_candidate": {"className": "ydf-table-placeholder-add-button"},
    }
    page = _FakeEditableAddRowPage([added, {"label": "新增", "row_state_changed": True}], [])
    runtime._page = page
    monkeypatch.setattr(
        runtime,
        "_settle_editable_table_add_row_interactions",
        lambda: calls.append("settle"),
        raising=False,
    )

    result = runtime.add_editable_table_row(label="新增", table="调入方", table_fieldid="table2")

    assert result["row_state_changed"] is True
    assert result["row_state_reliable"] is True
    assert "retry_count" not in result
    assert calls == ["settle"]


def test_playwright_runtime_activates_editable_table_cell_inside_child_frame(monkeypatch) -> None:
    runtime = _build_runtime()
    child_frame = _FakeEditableSelectorContext("child", '[data-ydf-browser-cell-target="frame-cell"]')
    page = _FakeEditableSelectorPage("", [child_frame])
    runtime._page = page
    cell = _FakeEditableCell()
    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: cell)
    monkeypatch.setattr(runtime, "_editable_table_cell_has_active_editor", lambda _cell: True, raising=False)

    selector = runtime._activate_editable_table_cell("追减金额(元)", row_number=1, table="指标信息")

    assert selector == '[data-ydf-browser-cell-target="frame-cell"]'
    assert [call["payload"] for call in child_frame.calls if call["script"] == _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT] == [
        {"column": "追减金额(元)", "rowNumber": 1, "table": "指标信息"}
    ]
    assert cell.scrolled is True
    assert cell.clicked is True


def test_playwright_runtime_prefers_child_frame_editable_table_cell_over_background_page(monkeypatch) -> None:
    runtime = _build_runtime()
    child_frame = _FakeEditableSelectorContext("child", '[data-ydf-browser-cell-target="foreground-cell"]')
    page = _FakeEditableSelectorPage('[data-ydf-browser-cell-target="background-cell"]', [child_frame])
    runtime._page = page
    cell = _FakeEditableCell()
    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: cell)
    monkeypatch.setattr(runtime, "_editable_table_cell_has_active_editor", lambda _cell: True, raising=False)

    selector = runtime._activate_editable_table_cell("追减金额(元)", row_number=1, table="指标信息")

    assert selector == '[data-ydf-browser-cell-target="foreground-cell"]'


def test_playwright_runtime_fill_editable_table_row_uses_resolved_scope_token(monkeypatch) -> None:
    runtime = _build_runtime()
    page = _FakeEditableSelectorPage('[data-ydf-browser-cell-target="resolved-cell"]', [])
    runtime._page = page
    cell = _FakeEditableCell()
    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: cell)
    monkeypatch.setattr(runtime, "_editable_table_cell_has_active_editor", lambda _cell: True, raising=False)
    monkeypatch.setattr(runtime, "_fill_active_editable_table_cell", lambda *_args, **_kwargs: None)
    scope = ResolvedTableScope(
        label="增加",
        region_fieldid="bg_table",
        runtime_fieldid="bg_table_table",
        foreground=True,
        columns=("收入分成比例%", "说明"),
        required_columns=("收入分成比例%",),
        token="resolved-scope-token",
        evidence=(),
    )

    runtime.fill_editable_table_row({"收入分成比例%": "50.00"}, row_number=1, table_scope=scope)

    payloads = [call["payload"] for call in page.calls if call["script"] == _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT]
    assert payloads[0]["tableScopeToken"] == "resolved-scope-token"
    assert "data-ydf-table-scope-token" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "resolved-table-scope" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT


def test_editable_table_cell_selector_does_not_fallback_when_scope_token_is_missing() -> None:
    assert "if (tableScopeToken && !targetRoots.length)" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "missing-scope-token" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT


def test_editable_table_cell_selector_scopes_last_row_to_target_table_root() -> None:
    assert "const targetTableRootCandidates = () =>" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "const rowCandidatesForRoot = (root)" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "rootSortScore" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "target-table-fieldid" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "rowText" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT


def test_editable_table_cell_selector_does_not_identity_match_from_document_body_scope() -> None:
    assert "document-body-identity-scope-disabled" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT


def test_editable_table_column_identity_payload_includes_displayvalue_fields() -> None:
    candidate = SimpleNamespace(
        fieldid="nameField",
        key="nameField",
        data_field="internalDepName",
        region_fieldid="tableField",
        element_type="formItem",
        component_name="YDFInput",
        raw={"props": {"displayvalue": "internalDepCode+internalDepName"}},
    )

    payload = runtime_module._editable_table_column_identity_payload(candidate)

    assert payload["displayFields"] == ["internalDepCode", "internalDepName"]


def test_editable_table_column_identity_payload_includes_column_groups() -> None:
    candidate = SimpleNamespace(
        fieldid="final_current",
        key="final_current",
        data_field="finalCurrentAppropriation",
        region_fieldid="detail_table",
        element_type="column",
        component_name="YDFInputNumber",
        column_groups=["全年执行决算金额"],
        raw={},
    )

    payload = runtime_module._editable_table_column_identity_payload(candidate)

    assert payload["columnGroups"] == ["全年执行决算金额"]


def test_playwright_runtime_editable_table_identity_conflict_fails(monkeypatch) -> None:
    runtime = _build_runtime()

    class _ConflictContext:
        def evaluate(self, script: str, payload=None):
            if script == _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT:
                return {
                    "selector": "",
                    "locator_source": "text-geometry",
                    "targetIdentity": {"dataField": "estVal", "columnFieldid": "quantityField"},
                    "actualIdentity": {"data_field": "activityDesc", "fieldid": "remarkField"},
                    "identityConflict": {
                        "targetIdentity": {"dataField": "estVal", "columnFieldid": "quantityField"},
                        "actualIdentity": {"data_field": "activityDesc", "fieldid": "remarkField"},
                    },
                }
            return None

    monkeypatch.setattr(runtime, "_editable_table_search_contexts", lambda: [_ConflictContext()])

    with pytest.raises(RuntimeError) as exc_info:
        runtime._find_editable_table_cell_selector(
            {
                "column": "计量数",
                "columnFieldid": "quantityField",
                "dataField": "estVal",
                "tableFieldid": "pmEstImateList",
            }
        )

    message = str(exc_info.value)
    assert "可编辑表格列身份冲突" in message
    assert "column=计量数" in message
    assert "estVal" in message
    assert "activityDesc" in message


def test_playwright_runtime_activates_editable_table_cell_until_editor_appears(monkeypatch) -> None:
    runtime = _build_runtime()
    page = _FakeEditableSelectorPage('[data-ydf-browser-cell-target="cell"]', [])
    runtime._page = page
    cell = _FakeEditableCell()
    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: cell)
    monkeypatch.setattr(
        runtime,
        "_editable_table_cell_has_active_editor",
        lambda active_cell: active_cell.dblclicked,
        raising=False,
    )

    runtime._activate_editable_table_cell("追减金额(元)", row_number=1, table="指标信息")

    assert cell.clicked is True
    assert cell.dblclicked is True


def test_playwright_runtime_editable_table_fill_requires_real_input(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    cell = _FakeEditableCell()
    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: cell)
    monkeypatch.setattr(runtime, "_first_visible_child_locator", lambda root, selectors: None)
    monkeypatch.setattr(runtime, "_active_editable_locator", lambda: None)
    monkeypatch.setattr(runtime._popup_reference_module(), "editable_cell_looks_like_reference", lambda *args: False)
    monkeypatch.setattr(runtime, "_describe_editable_table_cell", lambda _cell: "plain text cell")
    monkeypatch.setattr(runtime, "_save_diagnostic_screenshot", lambda name: "")
    monkeypatch.setattr(runtime, "_wait_for_editable_table_cell_value", lambda cell, value: str(value))

    with pytest.raises(RuntimeError, match="未出现可输入控件"):
        runtime._fill_active_editable_table_cell("cell-selector", "1")


def test_playwright_runtime_editable_table_editor_missing_reports_scope(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    cell = _FakeEditableCell()
    runtime._last_editable_table_cell_resolution = {
        "locator_source": "identity-cell",
        "tableScope": {
            "table": "物资信息",
            "tableFieldid": "202308231611442671562585718836",
            "rootSource": "target-table-fieldid",
            "rowIndex": 0,
            "rowText": "1 复印纸 A4复印纸17220923 晨光 A4 箱 0.0",
        },
    }
    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: cell)
    monkeypatch.setattr(runtime, "_first_visible_child_locator", lambda root, selectors: None)
    monkeypatch.setattr(runtime, "_active_editable_locator", lambda: None)
    monkeypatch.setattr(runtime._popup_reference_module(), "editable_cell_looks_like_reference", lambda *args: False)
    monkeypatch.setattr(runtime, "_describe_editable_table_cell", lambda _cell: '{"cell": "", "row": "", "inputs": []}')
    monkeypatch.setattr(runtime, "_save_diagnostic_screenshot", lambda name: "")
    monkeypatch.setattr(runtime, "_wait_for_editable_table_cell_value", lambda cell, value: str(value))

    with pytest.raises(RuntimeError) as exc_info:
        runtime._fill_active_editable_table_cell("cell-selector", "1")

    message = str(exc_info.value)
    assert "table=物资信息" in message
    assert "table_fieldid=202308231611442671562585718836" in message
    assert "root_source=target-table-fieldid" in message
    assert "row_index=0" in message
    assert "复印纸" in message


def test_playwright_runtime_editable_cell_ignores_focused_input_outside_cell(monkeypatch) -> None:
    runtime = _build_runtime()

    class _Cell:
        def locator(self, _selector: str) -> _FakeLocatorGroup:
            return _FakeLocatorGroup([])

        def evaluate(self, _script: str, **_kwargs) -> bool:
            return False

    monkeypatch.setattr(runtime, "_first_visible_child_locator", lambda root, selectors: None)
    monkeypatch.setattr(runtime, "_active_editable_locator", lambda: object())
    monkeypatch.setattr(runtime, "_locator_is_directly_editable", lambda locator: False)

    assert runtime._editable_table_cell_has_active_editor(_Cell()) is False


def test_playwright_runtime_fill_editable_table_cell_does_not_use_focused_form_field(
    monkeypatch,
) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    cell = _FakeEditableCell()

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: cell)
    monkeypatch.setattr(runtime, "_first_visible_child_locator", lambda root, selectors: None)
    monkeypatch.setattr(runtime, "_active_editable_locator", lambda: object())
    monkeypatch.setattr(runtime._popup_reference_module(), "editable_cell_looks_like_reference", lambda *args: False)
    monkeypatch.setattr(runtime, "_describe_editable_table_cell", lambda _cell: "plain text cell")
    monkeypatch.setattr(runtime, "_save_diagnostic_screenshot", lambda name: "")

    with pytest.raises(RuntimeError, match="未出现可输入控件"):
        runtime._fill_active_editable_table_cell("cell-selector", "货物")


def test_playwright_runtime_fill_editable_table_row_allows_full_width_parentheses(monkeypatch) -> None:
    runtime = _build_runtime()
    activated_columns: list[str] = []
    filled: list[tuple[str, str]] = []
    monkeypatch.setattr(
        runtime,
        "_activate_editable_table_cell",
        lambda column, **_kwargs: activated_columns.append(column) or "cell-selector",
    )
    monkeypatch.setattr(
        runtime,
        "_fill_active_editable_table_cell",
        lambda selector, value, **_kwargs: filled.append((selector, value)),
    )

    result = runtime.fill_editable_table_row({"价格/标准（元）": "1000.00"}, table="项目测算信息")

    assert activated_columns == ["价格/标准（元）"]
    assert filled == [("cell-selector", "1000.00")]
    assert result["fields"] == [{"column": "价格/标准（元）", "value": "1000.00"}]


def test_playwright_runtime_fill_editable_table_row_uses_column_identity_for_est_val(monkeypatch) -> None:
    runtime = _build_runtime()
    quantity = SimpleNamespace(
        fieldid="2022110818063614636522705307434",
        data_field="estVal",
        region_fieldid="pmEstImateList",
        element_type="column",
        component_name="YDFInputNumber",
    )
    remark = SimpleNamespace(
        fieldid="2023080616145836030408170989523",
        data_field="activityDesc",
        region_fieldid="pmEstImateList",
        element_type="formItem",
        component_name="YDFInput",
    )
    activated: list[dict[str, object]] = []
    filled: list[tuple[str, str]] = []

    def _activate(column, row_number=-1, table=None, column_candidate=None):
        activated.append(
            {
                "column": column,
                "row_number": row_number,
                "table": table,
                "candidate": column_candidate,
            }
        )
        runtime._last_editable_table_cell_resolution = {
            "locator_source": "identity-cell",
            "actual_data_field": getattr(column_candidate, "data_field", ""),
        }
        return f"[cell-{getattr(column_candidate, 'data_field', 'missing')}]"

    monkeypatch.setattr(runtime, "_activate_editable_table_cell", _activate)
    monkeypatch.setattr(
        runtime,
        "_fill_active_editable_table_cell",
        lambda selector, value, **_kwargs: filled.append((selector, value)),
    )

    result = runtime.fill_editable_table_row(
        {"计量数": "500"},
        table="项目测算信息",
        column_candidates={"计量数": quantity, "备注": remark},
    )

    assert activated == [
        {"column": "计量数", "row_number": -1, "table": "项目测算信息", "candidate": quantity}
    ]
    assert filled == [("[cell-estVal]", "500")]
    assert result["fields"] == [
        {
            "column": "计量数",
            "value": "500",
            "fieldid": "2022110818063614636522705307434",
            "data_field": "estVal",
            "table_fieldid": "pmEstImateList",
            "locator_source": "identity-cell",
            "actual_data_field": "estVal",
        }
    ]


def test_playwright_runtime_fill_editable_table_row_reports_column_groups(monkeypatch) -> None:
    runtime = _build_runtime()
    candidate = SimpleNamespace(
        fieldid="final_current",
        data_field="finalCurrentAppropriation",
        region_fieldid="detail_table",
        element_type="column",
        component_name="YDFInputNumber",
        column_groups=["全年执行决算金额"],
    )

    def _activate(column, row_number=-1, table=None, column_candidate=None):
        runtime._last_editable_table_cell_resolution = {
            "locator_source": "identity-cell",
            "actual_data_field": "finalCurrentAppropriation",
            "columnGroups": ["全年执行决算金额"],
        }
        return "[cell-finalCurrentAppropriation]"

    monkeypatch.setattr(runtime, "_activate_editable_table_cell", _activate)
    monkeypatch.setattr(runtime, "_fill_active_editable_table_cell", lambda *_args, **_kwargs: None)

    result = runtime.fill_editable_table_row(
        {"当年财政拨款(万元)": 3},
        table="三级项目同步",
        column_candidates={"当年财政拨款(万元)": candidate},
    )

    assert result["fields"][0]["column_groups"] == ["全年执行决算金额"]
    assert result["fields"][0]["locator_source"] == "identity-cell"


def test_playwright_runtime_fill_editable_table_row_reports_table_scope_context(monkeypatch) -> None:
    runtime = _build_runtime()
    quantity = SimpleNamespace(
        fieldid="2023082316181074251211093500313",
        data_field="applyNum",
        region_fieldid="202308231611442671562585718836",
        element_type="formItem",
        component_name="YDFInputNumber",
    )

    def _activate(column, row_number=-1, table=None, column_candidate=None):
        runtime._last_editable_table_cell_resolution = {
            "locator_source": "identity-cell",
            "actual_data_field": "applyNum",
            "tableScope": {
                "table": table,
                "tableFieldid": getattr(column_candidate, "region_fieldid", ""),
                "rootSource": "target-table-fieldid",
                "rowIndex": 0,
                "rowText": "1 复印纸 A4复印纸17220923 晨光 A4 箱 0.0",
            },
        }
        return "[cell-applyNum]"

    monkeypatch.setattr(runtime, "_activate_editable_table_cell", _activate)
    monkeypatch.setattr(runtime, "_fill_active_editable_table_cell", lambda *_args, **_kwargs: None)

    result = runtime.fill_editable_table_row(
        {"申请数量": "2"},
        table="物资信息",
        column_candidates={"申请数量": quantity},
    )

    assert result["fields"][0]["table_scope"] == {
        "table": "物资信息",
        "table_fieldid": "202308231611442671562585718836",
        "root_source": "target-table-fieldid",
        "row_index": 0,
        "row_text": "1 复印纸 A4复印纸17220923 晨光 A4 箱 0.0",
    }


def test_playwright_runtime_refinds_editable_table_cell_with_each_column_identity(monkeypatch) -> None:
    runtime = _build_runtime()
    candidates = {
        "单价": SimpleNamespace(
            fieldid="priceField",
            data_field="price",
            region_fieldid="pmEstImateList",
            element_type="column",
            component_name="YDFInputNumber",
        ),
        "计量数": SimpleNamespace(
            fieldid="quantityField",
            data_field="estVal",
            region_fieldid="pmEstImateList",
            element_type="column",
            component_name="YDFInputNumber",
        ),
    }
    activated: list[tuple[str, str]] = []

    def _activate(column, row_number=-1, table=None, column_candidate=None):
        data_field = getattr(column_candidate, "data_field", "")
        activated.append((column, data_field))
        runtime._last_editable_table_cell_resolution = {
            "locator_source": "identity-header-geometry",
            "actual_data_field": data_field,
        }
        return f"[cell-{data_field}]"

    monkeypatch.setattr(runtime, "_activate_editable_table_cell", _activate)
    monkeypatch.setattr(runtime, "_fill_active_editable_table_cell", lambda *_args, **_kwargs: None)

    result = runtime.fill_editable_table_row(
        {"单价": "300", "计量数": "500"},
        table="项目测算信息",
        column_candidates=candidates,
    )

    assert activated == [("单价", "price"), ("计量数", "estVal")]
    assert [field["data_field"] for field in result["fields"]] == ["price", "estVal"]
    assert [field["locator_source"] for field in result["fields"]] == [
        "identity-header-geometry",
        "identity-header-geometry",
    ]


def test_playwright_runtime_fill_editable_table_row_reports_text_geometry_fallback(monkeypatch) -> None:
    runtime = _build_runtime()

    def _activate(column, row_number=-1, table=None, column_candidate=None):
        runtime._last_editable_table_cell_resolution = {"locator_source": "text-geometry"}
        return "[cell]"

    monkeypatch.setattr(runtime, "_activate_editable_table_cell", _activate)
    monkeypatch.setattr(runtime, "_fill_active_editable_table_cell", lambda *_args, **_kwargs: None)

    result = runtime.fill_editable_table_row({"备注信息": "测试"}, table="支出明细")

    assert result["fields"] == [
        {"column": "备注信息", "value": "测试", "locator_source": "text-geometry"}
    ]


def test_playwright_runtime_fill_editable_table_row_reports_column_context(monkeypatch) -> None:
    runtime = _build_runtime()
    monkeypatch.setattr(runtime, "_activate_editable_table_cell", lambda *args, **kwargs: "cell-selector")

    def _raise(*_args, **_kwargs) -> None:
        raise RuntimeError("未打开弹出参照选择框")

    monkeypatch.setattr(runtime, "_fill_active_editable_table_cell", _raise)

    with pytest.raises(RuntimeError) as exc_info:
        runtime.fill_editable_table_row({"采购品目": "台式计算机"}, table="需求清单")

    message = str(exc_info.value)
    assert "可编辑表格列录入失败" in message
    assert "table=需求清单" in message
    assert "column=采购品目" in message
    assert "value=台式计算机" in message
    assert "未打开弹出参照选择框" in message


class _FakeTableTreeCandidate:
    def __init__(self, code: str, on_hover=None) -> None:
        self.code = code
        self._on_hover = on_hover

    def is_visible(self, timeout: int = 0) -> bool:
        return True

    def inner_text(self, timeout: int = 0) -> str:
        return f"{self.code} 目录"

    def hover(self, timeout: int = 0) -> None:
        if self._on_hover is not None:
            self._on_hover(self.code)

    def evaluate(self, script: str):
        if "collapsedMarker" in script:
            return True
        if "innerText" in script or "textContent" in script:
            return f"{self.code} 目录"
        return {"x": 16, "y": 17}


class _FakeTableTreeLocatorGroup:
    def __init__(self, matches: list[_FakeTableTreeCandidate]) -> None:
        self.matches = matches

    @property
    def first(self) -> _FakeTableTreeCandidate:
        return self.matches[0]

    def count(self) -> int:
        return len(self.matches)

    def nth(self, index: int) -> _FakeTableTreeCandidate:
        return self.matches[index]


class _FakeTableTreePage:
    def __init__(self, expander_codes: list[str]) -> None:
        self.expander_codes = expander_codes
        self.row_visible = False
        self.false_positive_target_locator = False
        self.hovered: list[str] = []
        self.scrolls = 0
        self.waits: list[int] = []

    def locator(self, selector: str) -> _FakeTableTreeLocatorGroup:
        if "988988988" in selector:
            if self.row_visible or self.false_positive_target_locator:
                code = "988988988" if self.row_visible else "false-positive"
                return _FakeTableTreeLocatorGroup([_FakeTableTreeCandidate(code, self.hovered.append)])
            return _FakeTableTreeLocatorGroup([])
        if "expand" in selector or "triangle" in selector or "switcher" in selector:
            return _FakeTableTreeLocatorGroup([_FakeTableTreeCandidate(code) for code in self.expander_codes])
        if self.row_visible:
            return _FakeTableTreeLocatorGroup([_FakeTableTreeCandidate("988988988", self.hovered.append)])
        return _FakeTableTreeLocatorGroup([_FakeTableTreeCandidate(code, self.hovered.append) for code in self.expander_codes])

    def evaluate(self, _script: str) -> bool:
        self.scrolls += 1
        self.row_visible = True
        return True

    def wait_for_timeout(self, timeout: int) -> None:
        self.waits.append(timeout)


class _FakeContext:
    def __init__(self, *, close_on_zero_pages: bool = False) -> None:
        self.pages: list[_FakePage] = []
        self.close_on_zero_pages = close_on_zero_pages
        self.closed = False
        self.min_page_count = 1
        self.page = self.new_page()
        self.added_cookies: list[dict] = []
        self.cleared_cookies: list[dict] = []
        self.cookies_payload: list[dict] = []
        self.routes: list[tuple[object, object]] = []
        self.request = SimpleNamespace(fetch=self._fetch)
        self.fetch_calls: list[dict[str, object]] = []
        self.fetch_response = SimpleNamespace(
            status=200,
            headers={
                "content-type": "application/json",
                "content-encoding": "gzip",
                "set-cookie": "LOCAL=1",
            },
            body=lambda: b'{"ok":true}',
        )

    def new_page(self) -> _FakePage:
        if self.closed:
            raise RuntimeError("Target page, context or browser has been closed")
        page = _FakePage(self._close_page)
        self.pages.append(page)
        self.page = page
        return page

    def _close_page(self, page: _FakePage) -> None:
        self.pages.remove(page)
        self.min_page_count = min(self.min_page_count, len(self.pages))
        if self.close_on_zero_pages and not self.pages:
            self.closed = True

    def close(self) -> None:
        self.closed = True
        for page in list(self.pages):
            page.close()

    def add_cookies(self, cookies: list[dict]) -> None:
        self.added_cookies.extend(cookies)

    def cookies(self) -> list[dict]:
        return list(self.cookies_payload)

    def clear_cookies(self, **kwargs) -> None:
        self.cleared_cookies.append(kwargs)

    def route(self, pattern, handler) -> None:
        self.routes.append((pattern, handler))

    def _fetch(self, url: str, **kwargs):
        self.fetch_calls.append({"url": url, **kwargs})
        return self.fetch_response


class _FakeBrowser:
    def __init__(self) -> None:
        self.context = _FakeContext()
        self.context_kwargs: dict[str, object] = {}

    def new_context(self, **kwargs) -> _FakeContext:
        self.context_kwargs = kwargs
        return self.context

    def close(self) -> None:
        return


class _FakePlaywright:
    def __init__(self) -> None:
        self.browser = _FakeBrowser()
        self.persistent_context = _FakeContext(close_on_zero_pages=True)
        self.launch_kwargs: list[dict[str, object]] = []
        self.persistent_kwargs: list[dict[str, object]] = []
        self.chromium = SimpleNamespace(launch=self._launch)
        self.chromium.launch_persistent_context = self._launch_persistent_context

    def _launch(self, **kwargs) -> _FakeBrowser:
        self.launch_kwargs.append(kwargs)
        return self.browser

    def _launch_persistent_context(self, user_data_dir, **kwargs) -> _FakeContext:
        self.persistent_kwargs.append({"user_data_dir": user_data_dir, **kwargs})
        return self.persistent_context

    def stop(self) -> None:
        return


class _FakePlaywrightManager:
    def __init__(self) -> None:
        self.instance = _FakePlaywright()

    def start(self) -> _FakePlaywright:
        return self.instance



def _patch_popup_reference_select(monkeypatch, runtime, callback) -> None:
    """Install a public-interface fake while keeping Runtime adapter tests focused."""
    popup_reference = runtime._popup_reference_module()

    def select(request):
        identity = getattr(request.source, "identity", None)
        selector = str(getattr(identity, "selector", "") or "")
        owner = runtime._resolve_visible_locator(selector) if selector else None
        try:
            fill_locator = runtime._resolve_fill_locator(selector) if selector else None
        except (AttributeError, RuntimeError):
            fill_locator = None
        raw_target = request.target
        if isinstance(raw_target, dict):
            target = dict(raw_target)
        elif isinstance(raw_target, (list, tuple)):
            target = {"selections": list(raw_target)}
        else:
            target = {"value": raw_target}
        value = target["value"] if set(target) == {"value"} else target
        callback(owner, fill_locator, value)
        return PopupReferenceResult(
            selected=(target,),
            confirmed=True,
            root_backfilled=True,
            completion="owner_backfilled",
        )

    monkeypatch.setattr(popup_reference, "select", select)


def _build_runtime(
    session: requests.Session | None = None,
    request_forward_rules=None,
    observation_session=None,
    window_size: tuple[int, int] | None = None,
) -> PlaywrightRuntime:
    return PlaywrightRuntime(
        config=EnvironmentConfig(
            env_name="ydf",
            base_url="https://example.yonyougov.top",
            sysid="yonbip",
            username="demo",
            password="demo",
        ),
        session=session or requests.Session(),
        headless=True,
        request_forward_rules=request_forward_rules,
        window_size=window_size,
        observation_session=observation_session,
    )


@pytest.mark.parametrize(
    ("page", "expected"),
    [
        (None, False),
        (SimpleNamespace(is_closed=lambda: False), True),
        (SimpleNamespace(is_closed=lambda: True), False),
    ],
)
def test_playwright_runtime_reports_whether_current_page_is_open(page, expected: bool) -> None:
    runtime = _build_runtime()
    runtime._page = page

    assert runtime.has_open_page() is expected


def test_playwright_runtime_treats_page_state_error_as_closed() -> None:
    runtime = _build_runtime()
    runtime._page = SimpleNamespace(is_closed=lambda: (_ for _ in ()).throw(RuntimeError("browser closed")))

    assert runtime.has_open_page() is False


def test_playwright_runtime_probes_page_to_detect_disconnected_browser() -> None:
    runtime = _build_runtime()
    runtime._page = SimpleNamespace(
        is_closed=lambda: False,
        evaluate=lambda _script: (_ for _ in ()).throw(
            RuntimeError("Target page, context or browser has been closed")
        ),
    )

    assert runtime.has_open_page() is False


def test_playwright_runtime_keeps_page_open_on_unrelated_probe_error() -> None:
    runtime = _build_runtime()
    runtime._page = SimpleNamespace(
        is_closed=lambda: False,
        evaluate=lambda _script: (_ for _ in ()).throw(RuntimeError("page is navigating")),
    )

    assert runtime.has_open_page() is True


@pytest.mark.parametrize("profile", [False, True])
def test_playwright_runtime_keeps_headed_viewport_attached_to_window(monkeypatch, profile: bool) -> None:
    manager = _FakePlaywrightManager()
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=lambda: manager))
    runtime = _build_runtime()
    runtime.headless = False
    runtime.profile_dir = Path("/tmp/ydf-browser-test-profile") if profile else None

    runtime.start()

    launch_kwargs = manager.instance.persistent_kwargs[-1] if profile else manager.instance.launch_kwargs[-1]
    context_kwargs = manager.instance.persistent_kwargs[-1] if profile else manager.instance.browser.context_kwargs
    assert "args" not in launch_kwargs
    assert "viewport" not in context_kwargs
    assert context_kwargs["no_viewport"] is True


@pytest.mark.parametrize("profile", [False, True])
@pytest.mark.parametrize("headless", [False, True])
@pytest.mark.parametrize("window_size", [(1600, 1000), (1280, 720)])
def test_playwright_runtime_applies_explicit_window_size(
    monkeypatch,
    profile: bool,
    headless: bool,
    window_size: tuple[int, int],
) -> None:
    manager = _FakePlaywrightManager()
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=lambda: manager))
    runtime = _build_runtime(window_size=window_size)
    runtime.headless = headless
    runtime.profile_dir = Path("/tmp/ydf-browser-test-profile") if profile else None

    runtime.start()

    width, height = window_size
    launch_kwargs = manager.instance.persistent_kwargs[-1] if profile else manager.instance.launch_kwargs[-1]
    if headless:
        assert "args" not in launch_kwargs
    else:
        assert launch_kwargs["args"] == [f"--window-size={width},{height}"]
    context_kwargs = manager.instance.persistent_kwargs[-1] if profile else manager.instance.browser.context_kwargs
    if headless:
        assert context_kwargs["viewport"] == {"width": width, "height": height}
        assert "no_viewport" not in context_kwargs
    else:
        assert "viewport" not in context_kwargs
        assert context_kwargs["no_viewport"] is True


def test_capture_page_memory_returns_top_page_js_heap() -> None:
    runtime = _build_runtime()
    runtime._page = SimpleNamespace(
        is_closed=lambda: False,
        evaluate=lambda _script: 10485760,
    )

    assert runtime.capture_page_memory() == {
        "available": True,
        "used_js_heap_size": 10485760,
        "unavailable_reason": "",
    }


@pytest.mark.parametrize(
    ("page", "reason"),
    [
        (None, "page_not_available"),
        (SimpleNamespace(is_closed=lambda: True), "page_closed"),
        (
            SimpleNamespace(is_closed=lambda: False, evaluate=lambda _script: None),
            "performance_memory_not_supported",
        ),
    ],
)
def test_capture_page_memory_returns_unavailable_without_raising(page, reason: str) -> None:
    runtime = _build_runtime()
    runtime._page = page

    assert runtime.capture_page_memory() == {
        "available": False,
        "used_js_heap_size": 0,
        "unavailable_reason": reason,
    }


def test_capture_page_memory_handles_evaluate_failure() -> None:
    runtime = _build_runtime()

    def fail(_script: str) -> None:
        raise RuntimeError("page disappeared")

    runtime._page = SimpleNamespace(is_closed=lambda: False, evaluate=fail)

    assert runtime.capture_page_memory() == {
        "available": False,
        "used_js_heap_size": 0,
        "unavailable_reason": "capture_failed",
    }


def test_cookie_visible_to_url_matches_host_parent_domain_and_path() -> None:
    target_url = "https://dv5-ydf.yonyougov.top/yonbip/index.html"

    assert cookie_visible_to_url({"domain": "dv5-ydf.yonyougov.top", "path": "/"}, target_url) is True
    assert cookie_visible_to_url({"domain": ".yonyougov.top", "path": "/"}, target_url) is True
    assert cookie_visible_to_url({"domain": "tv5-ydf.yonyougov.top", "path": "/"}, target_url) is False
    assert cookie_visible_to_url({"domain": ".yonyougov.top", "path": "/other"}, target_url) is False


def test_playwright_runtime_starts_persistent_context_without_extra_page(monkeypatch, tmp_path) -> None:
    manager = _FakePlaywrightManager()
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=lambda: manager))
    runtime = _build_runtime()
    runtime.profile_dir = tmp_path / "profile"
    initial_page = manager.instance.persistent_context.pages[0]

    runtime.start()

    assert manager.instance.persistent_kwargs[-1]["user_data_dir"] == str(tmp_path / "profile")
    assert manager.instance.launch_kwargs == []
    assert runtime._context is manager.instance.persistent_context
    assert runtime._page is initial_page
    assert runtime._context.pages == [initial_page]


def test_playwright_runtime_records_manual_browser_app_for_visible_temporary_context(monkeypatch) -> None:
    manager = _FakePlaywrightManager()
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=lambda: manager))
    monkeypatch.setattr(runtime_module, "_browser_app_name", lambda context: "Google Chrome for Testing")
    runtime = _build_runtime()
    runtime.headless = False

    runtime.start()

    assert runtime._context is manager.instance.browser.context
    assert runtime._manual_browser_app_name == "Google Chrome for Testing"


def test_playwright_runtime_open_home_injects_session_cookies(monkeypatch) -> None:
    manager = _FakePlaywrightManager()
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=lambda: manager))
    session = requests.Session()
    session.cookies.set("SESSION", "abc", domain="example.yonyougov.top", path="/")
    runtime = _build_runtime(session=session)

    runtime.start()
    runtime.open_home()

    assert manager.instance.browser.context.added_cookies == [
        {
            "name": "SESSION",
            "value": "abc",
            "domain": "example.yonyougov.top",
            "path": "/",
            "secure": False,
        }
    ]
    assert runtime._page.goto_calls == ["https://example.yonyougov.top/"]


def test_playwright_runtime_waits_for_all_manual_session_pages(monkeypatch) -> None:
    runtime = _build_runtime()
    pulls = []
    runtime.session._ydf_cookie_bridge = SimpleNamespace(pull=lambda: pulls.append(True))

    class _ManualContext:
        def __init__(self) -> None:
            first = _FakePage()
            second = _FakePage()
            self.snapshots = [
                [first],
                [first, second],
                [],
            ]

        @property
        def pages(self):
            return self.snapshots.pop(0)

    context = _ManualContext()
    runtime._context = context
    monkeypatch.setattr(runtime_module.time, "sleep", lambda _seconds: None)

    assert runtime.wait_for_manual_session() == "browser_closed"
    assert context.snapshots == []
    assert len(pulls) == 2


def test_playwright_runtime_ignores_browser_replacement_tab_after_all_pages_close(monkeypatch) -> None:
    runtime = _build_runtime()

    class _StatePage:
        def __init__(self) -> None:
            self.closed = False

        def is_closed(self):
            return self.closed

    first = _StatePage()
    second = _StatePage()
    replacement = _StatePage()

    class _Context:
        def __init__(self) -> None:
            self.calls = 0

        def is_closed(self):
            return False

        @property
        def pages(self):
            self.calls += 1
            if self.calls == 1:
                return [first, second]
            if self.calls == 2:
                first.closed = True
                return [second]
            second.closed = True
            return [replacement]

    context = _Context()
    runtime._context = context
    sleep_calls = 0

    def _sleep(_seconds):
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls > 2:
            raise AssertionError("replacement tab must not keep session alive")

    monkeypatch.setattr(runtime_module.time, "sleep", _sleep)

    assert runtime.wait_for_manual_session() == "browser_closed"
    assert context.calls == 3


def test_playwright_runtime_detects_last_page_reused_as_chromium_new_tab(monkeypatch) -> None:
    runtime = _build_runtime()
    page = SimpleNamespace(url="https://example.yonyougov.top/", is_closed=lambda: False)

    class _Context:
        def __init__(self) -> None:
            self.calls = 0

        def is_closed(self):
            return False

        @property
        def pages(self):
            self.calls += 1
            if self.calls == 2:
                page.url = "chrome://newtab/"
            return [page]

    context = _Context()
    runtime._context = context
    sleep_calls = 0

    def _sleep(_seconds):
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls > 1:
            raise AssertionError("Chromium replacement new tab must not keep session alive")

    monkeypatch.setattr(runtime_module.time, "sleep", _sleep)

    assert runtime.wait_for_manual_session() == "browser_closed"
    assert context.calls == 2


def test_playwright_runtime_exits_when_last_manual_page_target_closes(monkeypatch) -> None:
    runtime = _build_runtime()

    class _Page:
        url = "https://example.yonyougov.top/"

        def __init__(self) -> None:
            self.evaluate_calls = 0

        def is_closed(self):
            return False

        def evaluate(self, _script):
            self.evaluate_calls += 1
            if self.evaluate_calls > 1:
                raise RuntimeError("Target page, context or browser has been closed")
            return True

    page = _Page()

    class _Context:
        def is_closed(self):
            return False

        @property
        def pages(self):
            return [page]

    runtime._context = _Context()
    monkeypatch.setattr(runtime_module.time, "sleep", lambda _seconds: None)

    assert runtime.wait_for_manual_session() == "browser_closed"
    assert page.evaluate_calls == 2


def test_playwright_runtime_exits_when_manual_browser_has_no_windows(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._manual_browser_app_name = "Google Chrome for Testing"
    runtime._context = SimpleNamespace(
        is_closed=lambda: False,
        pages=[
            SimpleNamespace(is_closed=lambda: False, url="https://example.yonyougov.top/", evaluate=lambda _script: True),
            SimpleNamespace(is_closed=lambda: False, url="https://www.baidu.com/", evaluate=lambda _script: True),
        ],
    )
    monkeypatch.setattr(runtime_module, "_manual_browser_window_count", lambda app_name: 0 if app_name == "Google Chrome for Testing" else None)
    monkeypatch.setattr(runtime_module.time, "sleep", lambda _seconds: (_ for _ in ()).throw(AssertionError("must not poll closed window")))
    runtime._manual_browser_seen_windows = True

    assert runtime.wait_for_manual_session() == "browser_closed"


def test_playwright_runtime_does_not_exit_before_manual_browser_window_appears(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._manual_browser_app_name = "Google Chrome for Testing"
    runtime._context = SimpleNamespace(
        is_closed=lambda: False,
        pages=[SimpleNamespace(is_closed=lambda: False, url="https://example.yonyougov.top/", evaluate=lambda _script: True)],
    )
    counts = iter([0, 1, 0])
    monkeypatch.setattr(runtime_module, "_manual_browser_window_count", lambda _app_name: next(counts))
    monkeypatch.setattr(runtime_module.time, "sleep", lambda _seconds: None)

    assert runtime.wait_for_manual_session() == "browser_closed"


def test_playwright_runtime_manual_wait_uses_playwright_timeout_when_available(monkeypatch) -> None:
    runtime = _build_runtime()
    waits: list[int] = []
    page = SimpleNamespace(
        is_closed=lambda: False,
        url="https://example.yonyougov.top/",
        evaluate=lambda _script: True,
        wait_for_timeout=lambda timeout_ms: waits.append(timeout_ms),
    )

    class _Context:
        def __init__(self) -> None:
            self.calls = 0

        def is_closed(self):
            return False

        @property
        def pages(self):
            self.calls += 1
            return [page] if self.calls == 1 else []

    runtime._context = _Context()
    monkeypatch.setattr(runtime_module.time, "sleep", lambda _seconds: (_ for _ in ()).throw(AssertionError("manual wait must pump Playwright events")))

    assert runtime.wait_for_manual_session() == "browser_closed"
    assert waits == [200]


def test_playwright_runtime_treats_closed_manual_context_as_normal_exit() -> None:
    runtime = _build_runtime()

    class _ClosedContext:
        @property
        def pages(self):
            raise RuntimeError("Target page, context or browser has been closed")

    runtime._context = _ClosedContext()

    assert runtime.wait_for_manual_session() == "browser_closed"


def test_playwright_runtime_exits_when_context_reports_closed() -> None:
    runtime = _build_runtime()

    class _ClosedContext:
        def is_closed(self):
            return True

        @property
        def pages(self):
            raise AssertionError("closed context pages must not be polled")

    runtime._context = _ClosedContext()

    assert runtime.wait_for_manual_session() == "browser_closed"


def test_playwright_runtime_exits_when_all_context_pages_are_closed(monkeypatch) -> None:
    runtime = _build_runtime()

    class _ClosedPage:
        def is_closed(self):
            return True

    class _Context:
        def is_closed(self):
            return False

        @property
        def pages(self):
            return [_ClosedPage()]

    runtime._context = _Context()
    monkeypatch.setattr(runtime_module.time, "sleep", lambda _seconds: (_ for _ in ()).throw(AssertionError("must not poll closed pages")))

    assert runtime.wait_for_manual_session() == "browser_closed"


def test_playwright_runtime_propagates_unrelated_manual_context_errors() -> None:
    runtime = _build_runtime()

    class _BrokenContext:
        @property
        def pages(self):
            raise RuntimeError("connection lost")

    runtime._context = _BrokenContext()

    with pytest.raises(RuntimeError, match="connection lost"):
        runtime.wait_for_manual_session()


def test_playwright_runtime_clears_visible_profile_cookies_before_login(monkeypatch) -> None:
    manager = _FakePlaywrightManager()
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=lambda: manager))
    runtime = _build_runtime()
    runtime.profile_dir = Path("/tmp/ydf-profile")
    runtime.start()
    runtime._context.cookies_payload = [
        {"name": "LOCAL", "domain": "example.yonyougov.top", "path": "/"},
        {"name": "PARENT", "domain": ".yonyougov.top", "path": "/"},
        {"name": "OTHER", "domain": "other.example.com", "path": "/"},
    ]

    runtime.clear_visible_cookies("https://example.yonyougov.top")

    assert runtime._context.cleared_cookies == [
        {"name": "LOCAL", "domain": "example.yonyougov.top", "path": "/"},
        {"name": "PARENT", "domain": ".yonyougov.top", "path": "/"},
    ]


def test_playwright_runtime_open_menu_replaces_page_without_zero_page_gap(monkeypatch) -> None:
    manager = _FakePlaywrightManager()
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=lambda: manager))
    session = requests.Session()
    session.cookies.set("SESSION", "abc", domain="example.yonyougov.top", path="/")
    runtime = _build_runtime(session=session)
    runtime.profile_dir = Path("/tmp/ydf-profile")
    monkeypatch.setattr(runtime, "_wait_ready", lambda: None)
    runtime.start()
    context = manager.instance.persistent_context

    runtime.open_menu(MenuTarget(menu_code="A", menu_name="菜单A", path=["菜单A"], service_code="service-a"))
    first_page = runtime._page
    runtime.open_menu(MenuTarget(menu_code="B", menu_name="菜单B", path=["菜单B"], service_code="service-b"))

    assert first_page.closed is True
    assert runtime._page is not first_page
    assert runtime._page.goto_calls == ["https://example.yonyougov.top/#/service/service-b"]
    assert context.closed is False
    assert context.min_page_count == 1


def test_playwright_runtime_close_case_pages_keeps_holder_and_context(monkeypatch) -> None:
    manager = _FakePlaywrightManager()
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=lambda: manager))
    runtime = _build_runtime()
    runtime.profile_dir = Path("/tmp/ydf-profile")
    monkeypatch.setattr(runtime, "_wait_ready", lambda: None)
    runtime.start()
    page = runtime._page

    runtime.close_case_pages()

    assert page.closed is True
    assert runtime._page is not None
    assert runtime._page.closed is False
    assert runtime._context is manager.instance.persistent_context
    assert runtime._context.closed is False
    assert runtime._context.min_page_count == 1

    runtime.open_menu(MenuTarget(menu_code="A", menu_name="菜单A", path=["菜单A"], service_code="service-a"))

    assert runtime._page.goto_calls == ["https://example.yonyougov.top/#/service/service-a"]


def test_playwright_runtime_close_case_pages_tolerates_already_closed_browser(monkeypatch) -> None:
    manager = _FakePlaywrightManager()
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=lambda: manager))
    runtime = _build_runtime()
    runtime.profile_dir = Path("/tmp/ydf-profile")
    runtime.start()
    runtime._context.close()

    runtime.close_case_pages()

    assert runtime._page is None


def test_playwright_runtime_stop_tolerates_already_closed_resources() -> None:
    runtime = _build_runtime()
    runtime.profile_dir = Path("/tmp/ydf-profile")
    calls: list[str] = []

    def _closed(name: str) -> None:
        calls.append(name)
        raise RuntimeError("Target page, context or browser has been closed")

    runtime._context = SimpleNamespace(close=lambda: _closed("context"))
    runtime._browser = SimpleNamespace(close=lambda: _closed("browser"))
    runtime._playwright = SimpleNamespace(stop=lambda: calls.append("playwright"))

    runtime.stop()

    assert calls == ["context", "browser", "playwright"]


def test_playwright_runtime_close_case_pages_does_not_hide_unexpected_holder_error(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime.profile_dir = Path("/tmp/ydf-profile")
    runtime._context = SimpleNamespace(pages=[])
    monkeypatch.setattr(runtime, "_new_page", lambda: (_ for _ in ()).throw(RuntimeError("new page failed")))

    with pytest.raises(RuntimeError, match="new page failed"):
        runtime.close_case_pages()


def test_playwright_runtime_stop_does_not_hide_unexpected_cleanup_error() -> None:
    runtime = _build_runtime()
    runtime.profile_dir = Path("/tmp/ydf-profile")
    runtime._context = SimpleNamespace(close=lambda: (_ for _ in ()).throw(RuntimeError("cleanup failed")))

    with pytest.raises(RuntimeError, match="cleanup failed"):
        runtime.stop()


def _checkbox_bound_element(fieldid: str = "hideZero") -> BoundElement:
    candidate = ElementCandidate(
        key=fieldid,
        fieldid=fieldid,
        label="隐藏0金额行",
        title="",
        region_key="budget_form",
        region_fieldid="budget_form",
        element_type="formItem",
        component_name="YDFCheckbox",
        data_field="hideZero",
    )
    runtime = RuntimeElement(
        fieldid=fieldid,
        id=None,
        name=None,
        placeholder=None,
        text="隐藏0金额行",
        role=None,
        tag_name="label",
        visible=True,
        selector=f'[fieldid="{fieldid}"]',
        editable=True,
    )
    return BoundElement(candidate=candidate, runtime=runtime, confidence=0.95, reasons=["fieldid"])


def _toolbar_bound_element(
    label: str = "导入",
    *,
    component_name: str = "YDFButton",
    raw: dict | None = None,
) -> BoundElement:
    candidate = ElementCandidate(
        key="import_btn",
        fieldid="import_btn",
        label=label,
        title="",
        region_key="toolbar",
        region_fieldid="toolbar",
        element_type="leafItem",
        component_name=component_name,
        raw=raw or {},
    )
    runtime = RuntimeElement(
        fieldid="import_btn",
        id=None,
        name=None,
        placeholder=None,
        text=label,
        role="button",
        tag_name="button",
        visible=True,
        selector='[fieldid="import_btn"]',
    )
    return BoundElement(candidate=candidate, runtime=runtime, confidence=0.95, reasons=["fieldid"])


def _import_request(
    url: str,
    *,
    method: str,
    content_type: str = "application/json",
) -> SimpleNamespace:
    return SimpleNamespace(
        url=url,
        method=method,
        resource_type="xhr",
        headers={"content-type": content_type},
        post_data_buffer=None,
        failure=None,
    )


def _import_response(
    request: SimpleNamespace,
    *,
    status: int,
    payload: object,
) -> SimpleNamespace:
    return SimpleNamespace(
        url=request.url,
        request=request,
        status=status,
        headers={"content-type": "application/json"},
        json=lambda: payload,
    )


def test_playwright_runtime_reads_checked_form_checkbox_as_on(monkeypatch) -> None:
    runtime = _build_runtime()
    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda _selector: _FakeFormCheckboxRoot(checked=True))
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda _selector: _FakeInputValueLocator(""))

    assert runtime.read_field_value(_checkbox_bound_element()) == "on"


def test_playwright_runtime_reads_unchecked_form_checkbox_as_off_instead_of_default_value(monkeypatch) -> None:
    runtime = _build_runtime()
    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda _selector: _FakeFormCheckboxRoot(checked=False))
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda _selector: _FakeInputValueLocator("on"))

    assert runtime.read_field_value(_checkbox_bound_element()) == "off"


def test_playwright_runtime_fails_when_form_checkbox_state_is_unreadable(monkeypatch) -> None:
    runtime = _build_runtime()
    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda _selector: _FakeFormCheckboxRoot(checked=None))
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda _selector: _FakeInputValueLocator("序号"))

    with pytest.raises(RuntimeError, match="checkbox 状态不可读"):
        runtime.read_field_value(_checkbox_bound_element())


def test_playwright_runtime_read_field_value_keeps_non_empty_control_value(monkeypatch) -> None:
    runtime = _build_runtime()
    root = object()
    bound = SimpleNamespace(
        candidate=SimpleNamespace(label="开户银行", aliases=lambda: {"开户银行"}),
        runtime=SimpleNamespace(selector='[fieldid="sqxx_form_bankOutletsCode_input"]'),
    )

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda _selector: root)
    monkeypatch.setattr(runtime, "_looks_like_switch_field", lambda *_args: False)
    monkeypatch.setattr(runtime, "_looks_like_radio_field", lambda *_args: False)
    monkeypatch.setattr(runtime, "_looks_like_checkbox_field", lambda *_args: False)
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda _selector: _FakeInputValueLocator("中信银行"))
    monkeypatch.setattr(runtime, "_read_field_value_from_page_text", lambda _label: "账户性质")

    assert runtime.read_field_value(bound) == "中信银行"


def test_playwright_runtime_start_only_boots_browser(monkeypatch) -> None:
    manager = _FakePlaywrightManager()
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=lambda: manager))
    runtime = _build_runtime()
    calls: list[str] = []
    monkeypatch.setattr(runtime, "_wait_ready", lambda: calls.append("wait_ready"))
    monkeypatch.setattr(runtime, "_ensure_authenticated", lambda: calls.append("ensure_authenticated"))

    runtime.start()

    assert runtime._page is runtime._context.page
    assert "response" in runtime._page.event_handlers
    assert runtime._page.goto_calls == []
    assert calls == []


def test_playwright_runtime_starts_headed_browser_without_fixed_window_size(monkeypatch) -> None:
    manager = _FakePlaywrightManager()
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=lambda: manager))
    runtime = _build_runtime()
    runtime.headless = False

    runtime.start()

    assert manager.instance.launch_kwargs[-1]["headless"] is False
    assert "args" not in manager.instance.launch_kwargs[-1]
    assert "viewport" not in manager.instance.browser.context_kwargs
    assert manager.instance.browser.context_kwargs["no_viewport"] is True


@pytest.mark.parametrize("profile", [False, True])
def test_playwright_runtime_uses_1440x900_default_viewport_when_headless(monkeypatch, profile: bool) -> None:
    manager = _FakePlaywrightManager()
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=lambda: manager))
    runtime = _build_runtime()
    runtime.profile_dir = Path("/tmp/ydf-browser-test-profile") if profile else None

    runtime.start()

    launch_kwargs = manager.instance.persistent_kwargs[-1] if profile else manager.instance.launch_kwargs[-1]
    context_kwargs = manager.instance.persistent_kwargs[-1] if profile else manager.instance.browser.context_kwargs
    assert "args" not in launch_kwargs
    assert context_kwargs["viewport"] == {"width": 1440, "height": 900}
    assert "no_viewport" not in context_kwargs


def test_request_forward_rule_rewrites_urls_with_and_without_strip_prefix() -> None:
    keep_rule = parse_request_forward_rule(
        "/yondif-bm-fe/**=https://localhost:3000/app",
        strip_prefix=False,
    )
    strip_rule = parse_request_forward_rule(
        "/yondif-bm-be/**=http://localhost:62871/api",
        strip_prefix=True,
    )

    assert (
        keep_rule.rewrite_url("https://example.yonyougov.top/yondif-bm-fe/static/app.js?v=1")
        == "https://localhost:3000/app/yondif-bm-fe/static/app.js?v=1"
    )
    assert (
        strip_rule.rewrite_url("https://example.yonyougov.top/yondif-bm-be/bill/detail?id=42")
        == "http://localhost:62871/api/bill/detail?id=42"
    )
    assert strip_rule.rewrite_url("https://example.yonyougov.top/yondif-ams-be/api") is None


def test_request_forward_rules_use_first_matching_rule() -> None:
    first = parse_request_forward_rule("/yondif-bm-be/**=http://localhost:62871", strip_prefix=False)
    second = parse_request_forward_rule("/yondif-bm-be/**=http://localhost:7000", strip_prefix=False)

    assert (
        rewrite_forwarded_url(
            "https://example.yonyougov.top/yondif-bm-be/api?q=1",
            [first, second],
        )
        == "http://localhost:62871/yondif-bm-be/api?q=1"
    )


def test_playwright_runtime_registers_forward_route_only_when_rules_exist(monkeypatch) -> None:
    manager = _FakePlaywrightManager()
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=lambda: manager))
    runtime = _build_runtime()

    runtime.start()

    assert manager.instance.browser.context.routes == []
    assert "service_workers" not in manager.instance.browser.context_kwargs

    manager = _FakePlaywrightManager()
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=lambda: manager))
    runtime = _build_runtime(
        request_forward_rules=[
            parse_request_forward_rule("/yondif-bm-be/**=http://localhost:62871", strip_prefix=False)
        ]
    )

    runtime.start()

    assert manager.instance.browser.context.routes[0][0] == "**/*"
    assert manager.instance.browser.context_kwargs["service_workers"] == "block"


def test_playwright_runtime_forwards_matching_request_by_fetching_and_fulfilling(monkeypatch) -> None:
    manager = _FakePlaywrightManager()
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=lambda: manager))
    runtime = _build_runtime(
        request_forward_rules=[
            parse_request_forward_rule("/yondif-bm-be/**=http://localhost:62871", strip_prefix=False)
        ]
    )
    runtime.start()
    handler = manager.instance.browser.context.routes[0][1]
    request = SimpleNamespace(
        url="https://example.yonyougov.top/yondif-bm-be/bill/detail?id=42",
        method="POST",
        headers={"host": "example.yonyougov.top", "cookie": "SESSION=abc", "content-length": "99"},
        post_data_buffer=b'{"id":42}',
    )
    route = SimpleNamespace(
        fulfilled=None,
        aborted=False,
        fallback_called=False,
        fulfill=lambda **kwargs: setattr(route, "fulfilled", kwargs),
        abort=lambda: setattr(route, "aborted", True),
        fallback=lambda: setattr(route, "fallback_called", True),
    )

    handler(route, request)

    assert manager.instance.browser.context.fetch_calls == [
        {
            "url": "http://localhost:62871/yondif-bm-be/bill/detail?id=42",
            "method": "POST",
            "headers": {"cookie": "SESSION=abc"},
            "data": b'{"id":42}',
            "ignore_https_errors": True,
        }
    ]
    assert route.fulfilled["status"] == 200
    assert route.fulfilled["headers"] == {"content-type": "application/json"}
    assert route.fulfilled["body"] == b'{"ok":true}'
    assert route.fallback_called is False
    assert route.aborted is False


def test_playwright_runtime_records_forward_provenance_on_same_request_lifecycle(monkeypatch, tmp_path) -> None:
    manager = _FakePlaywrightManager()
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=lambda: manager))
    observation = ObservationSession(
        tmp_path / "events.jsonl",
        tool_version="test",
        run_id="run-1",
        configuration={},
    )
    rule = parse_request_forward_rule("/yondif-bm-be/**=http://localhost:62871", strip_prefix=True)
    runtime = _build_runtime(request_forward_rules=[rule], observation_session=observation)
    runtime.start()
    handler = manager.instance.browser.context.routes[0][1]
    request = SimpleNamespace(
        url="https://example.yonyougov.top/yondif-bm-be/bill/save?token=secret&id=42",
        method="POST",
        resource_type="xhr",
        headers={"content-type": "application/json"},
        post_data_buffer=b'{"id":42}',
        failure=None,
    )
    route = SimpleNamespace(
        fulfill=lambda **_kwargs: None,
        abort=lambda: None,
        fallback=lambda: None,
    )

    handler(route, request)
    runtime._page.event_handlers["request"](request)
    request.response = lambda: SimpleNamespace(
        url=request.url,
        request=request,
        status=200,
        headers={"content-type": "application/json"},
    )
    runtime._page.event_handlers["requestfinished"](request)

    records = [
        json.loads(line)
        for line in (tmp_path / "artifacts" / "network" / "index.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    completed = records[-1]
    assert completed["request_id"] == records[0]["request_id"]
    assert completed["actual_url"] == "http://localhost:62871/bill/save?token=%5BREDACTED%5D&id=42"
    assert completed["forwarding"] == {
        "matched": True,
        "rule": rule.to_dict(),
        "success": True,
        "status": 200,
    }


def test_playwright_runtime_aborts_forwarded_request_when_local_fetch_fails(monkeypatch) -> None:
    manager = _FakePlaywrightManager()
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=lambda: manager))
    runtime = _build_runtime(
        request_forward_rules=[
            parse_request_forward_rule("/yondif-bm-be/**=http://localhost:62871", strip_prefix=False)
        ]
    )
    runtime.start()
    manager.instance.browser.context.request.fetch = lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("connection refused"))
    handler = manager.instance.browser.context.routes[0][1]
    request = SimpleNamespace(
        url="https://example.yonyougov.top/yondif-bm-be/bill/detail",
        method="GET",
        headers={},
        post_data_buffer=None,
    )
    route = SimpleNamespace(
        aborted=False,
        fallback_called=False,
        abort=lambda: setattr(route, "aborted", True),
        fallback=lambda: setattr(route, "fallback_called", True),
    )

    handler(route, request)

    assert route.aborted is True
    assert route.fallback_called is False
    assert runtime.capture_page_state()["request_forwarding"]["recent_events"][0]["error"] == "connection refused"


def test_playwright_runtime_collects_network_performance_summary(monkeypatch) -> None:
    manager = _FakePlaywrightManager()
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=lambda: manager))
    runtime = _build_runtime()
    runtime.enable_performance_collection()
    runtime.start()

    request = SimpleNamespace(method="GET", url="https://example.yonyougov.top/static/app.js", resource_type="script")
    response = SimpleNamespace(
        url=request.url,
        status=200,
        headers={"content-length": "1200"},
        request=request,
    )
    runtime._page.event_handlers["response"](response)
    runtime._page.event_handlers["requestfailed"](
        SimpleNamespace(method="POST", url="https://example.yonyougov.top/yondif-ams-be/api", resource_type="xhr")
    )

    summary = runtime.collect_network_summary(reset=True)

    assert summary["request_count"] == 2
    assert summary["failed_count"] == 1
    assert summary["static_resource_count"] == 1
    assert summary["api_request_count"] == 1
    assert summary["status_counts"] == {"200": 1}
    assert summary["encoded_body_size"] == 1200
    assert summary["top_slow_requests"][0]["url"] == "https://example.yonyougov.top/static/app.js"
    assert summary["top_slow_static_resources"][0]["url"] == "https://example.yonyougov.top/static/app.js"
    assert summary["top_slow_api_requests"][0]["url"] == "https://example.yonyougov.top/yondif-ams-be/api"
    assert runtime.collect_network_summary()["request_count"] == 0


def test_response_body_size_falls_back_when_request_sizes_is_cancelled() -> None:
    def cancelled_sizes():
        raise asyncio.CancelledError

    request = SimpleNamespace(sizes=cancelled_sizes)
    response = SimpleNamespace(headers={"content-length": "321"})

    assert _response_body_size(request, response) == 321


def test_network_event_falls_back_to_request_body_when_request_sizes_is_cancelled() -> None:
    def cancelled_sizes():
        raise asyncio.CancelledError

    runtime = _build_runtime()
    request = SimpleNamespace(
        sizes=cancelled_sizes,
        post_data_buffer=b"abc",
        method="POST",
        resource_type="xhr",
        url="https://example.yonyougov.top/api/save",
    )
    response = SimpleNamespace(url=request.url, status=200, headers={"content-length": "12"})

    runtime._record_or_update_network_event(request, response=response, failed=False)

    assert runtime._network_events[0]["request_body_size"] == 3
    assert runtime._network_events[0]["request_body_size_available"] is True
    assert runtime._network_events[0]["request_body_size_unavailable_reason"] == ""


def test_playwright_runtime_sends_requests_to_existing_observation_hook() -> None:
    class Observation:
        def __init__(self) -> None:
            self.started = []

        def network_request_started(self, **payload) -> None:
            self.started.append(payload)

    observation = Observation()
    runtime = _build_runtime(observation_session=observation)
    request = SimpleNamespace(
        method="POST",
        url="https://example.yonyougov.top/ydf/bill/save",
        resource_type="xhr",
        headers={"content-type": "application/json"},
        post_data_buffer=b'{"name":"test"}',
    )

    runtime._capture_network_request(request)

    assert observation.started[0]["request_key"] == id(request)
    assert observation.started[0]["original_url"] == request.url
    assert observation.started[0]["resource_type"] == "xhr"


def test_playwright_runtime_writes_case_console_and_page_error_index(tmp_path) -> None:
    observation = ObservationSession(
        tmp_path / "events.jsonl",
        tool_version="test",
        run_id="run-1",
        configuration={},
    )
    observation.set_scope(case_id="case-a", step_id="3", phase="execute")
    runtime = _build_runtime(observation_session=observation)

    runtime._capture_console_event(
        SimpleNamespace(
            type="log",
            text="ignored",
            location={"url": "https://example.yonyougov.top/app.js", "lineNumber": 1},
        )
    )
    runtime._capture_console_event(
        SimpleNamespace(
            type="error",
            text="request failed token=console-secret",
            location={"url": "https://example.yonyougov.top/app.js?session=s", "lineNumber": 2},
        )
    )
    runtime._capture_page_error(SimpleNamespace(message="page failed password=page-secret", stack="at save"))

    records = [
        json.loads(line)
        for line in (tmp_path / "artifacts" / "errors" / "index.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [item["event"] for item in records] == ["console_error", "page_error"]
    assert all(item["step_id"] == "3" and item["phase"] == "execute" for item in records)
    assert "console-secret" not in json.dumps(records)
    assert "page-secret" not in json.dumps(records)
    assert records[0]["location"]["url"].endswith("session=%5BREDACTED%5D")


def test_playwright_runtime_captures_one_masked_viewport_failure_screenshot(monkeypatch, tmp_path) -> None:
    observation = ObservationSession(
        tmp_path / "events.jsonl",
        tool_version="test",
        run_id="run-1",
        configuration={},
    )
    observation.set_scope(case_id="case-a", step_id="2", phase="execute")
    runtime = _build_runtime(observation_session=observation)
    masks = [object(), object()]
    calls = []

    def screenshot(**kwargs):
        calls.append(kwargs)
        Path(kwargs["path"]).write_bytes(b"safe-png")

    runtime._page = SimpleNamespace(screenshot=screenshot)
    monkeypatch.setattr(runtime, "_collect_sensitive_screenshot_masks", lambda: masks)

    first = runtime.capture_safe_failure_screenshot()
    second = runtime.capture_safe_failure_screenshot()

    assert first["path"] == "artifacts/cases/case-a/failure-screenshot.png"
    assert first["masked_count"] == 2
    assert Path(first["absolute_path"]).read_bytes() == b"safe-png"
    assert calls[0]["full_page"] is False
    assert calls[0]["mask"] == masks
    assert second["capture_unavailable_reason"] == "already_attempted"
    assert len(calls) == 1


def test_playwright_runtime_captures_structural_foreground_summary_without_text() -> None:
    runtime = _build_runtime()
    frame = SimpleNamespace(
        url="https://example.test/page?token=secret",
        evaluate=lambda _script: {"dialogs": 1, "modals": 1, "drawers": 0},
    )
    runtime._page = SimpleNamespace(frames=[frame])

    summary = runtime.capture_foreground_summary()

    assert summary == {
        "visible": True,
        "frames": [
            {
                "url": "https://example.test/page?token=%5BREDACTED%5D",
                "dialogs": 1,
                "modals": 1,
                "drawers": 0,
            }
        ],
    }


def test_playwright_runtime_collects_only_current_table_assertion_rows(monkeypatch) -> None:
    runtime = _build_runtime()
    calls = []
    context = SimpleNamespace(
        evaluate=lambda script, payload: calls.append((script, payload))
        or {
            "rows": [{"编码": "001", "名称": "对象一"}],
            "identity_columns": ["编码"],
            "pagination": {"current_page": "1"},
            "empty_state": False,
        }
    )
    monkeypatch.setattr(runtime, "_table_selection_context", lambda *args, **kwargs: context)

    result = runtime.collect_table_assertion_rows(
        table="单位资金往来对象",
        table_fieldid="counterpart-table",
        table_columns=["编码", "名称"],
    )

    assert result["rows"] == [{"编码": "001", "名称": "对象一"}]
    assert result["pagination"] == {"current_page": "1"}
    assert calls[0][1] == {
        "table": "单位资金往来对象",
        "tableFieldid": "counterpart-table",
        "columns": ["编码", "名称"],
    }


def test_playwright_runtime_skips_failure_screenshot_when_any_visible_frame_mask_scan_fails(
    monkeypatch,
    tmp_path,
) -> None:
    observation = ObservationSession(
        tmp_path / "events.jsonl",
        tool_version="test",
        run_id="run-1",
        configuration={},
    )
    observation.set_scope(case_id="case-a")
    runtime = _build_runtime(observation_session=observation)
    calls = []
    runtime._page = SimpleNamespace(screenshot=lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(
        runtime,
        "_collect_sensitive_screenshot_masks",
        lambda: (_ for _ in ()).throw(RuntimeError("frame inaccessible")),
    )

    result = runtime.capture_safe_failure_screenshot()

    assert result["capture_unavailable_reason"] == "redaction_unsupported"
    assert "frame inaccessible" in result["detail"]
    assert calls == []


def test_playwright_runtime_scans_visible_child_frame_element_handle_without_locator_timeout() -> None:
    runtime = _build_runtime()
    empty_controls = SimpleNamespace(count=lambda: 0)
    main_frame = SimpleNamespace(locator=lambda _selector: empty_controls)

    class FrameElementHandle:
        def is_visible(self):
            return True

    child_frame = SimpleNamespace(
        frame_element=lambda: FrameElementHandle(),
        locator=lambda _selector: empty_controls,
    )
    runtime._page = SimpleNamespace(frames=[main_frame, child_frame])

    assert runtime._collect_sensitive_screenshot_masks() == []


@pytest.mark.parametrize(
    ("sample_request", "expected"),
    [
        (SimpleNamespace(sizes=lambda: {"requestBodySize": 12}, method="POST"), (12, True, "")),
        (
            SimpleNamespace(
                sizes=lambda: (_ for _ in ()).throw(RuntimeError()),
                post_data_buffer=b"abc",
                method="POST",
            ),
            (3, True, ""),
        ),
        (
            SimpleNamespace(sizes=lambda: {"requestBodySize": -1}, post_data_buffer=b"abc", method="POST"),
            (3, True, ""),
        ),
        (
            SimpleNamespace(sizes=lambda: {}, post_data_buffer=None, headers={"content-length": "7"}, method="POST"),
            (7, True, ""),
        ),
        (SimpleNamespace(sizes=lambda: {}, post_data_buffer=None, headers={}, method="GET"), (0, True, "")),
        (SimpleNamespace(sizes=lambda: {}, post_data_buffer=None, headers={}, method="HEAD"), (0, True, "")),
        (
            SimpleNamespace(sizes=lambda: {}, post_data_buffer=None, headers={}, method="POST"),
            (0, False, "request_body_size_unavailable"),
        ),
    ],
)
def test_request_body_size_uses_supported_fallbacks(sample_request, expected) -> None:
    assert runtime_module._request_body_size(sample_request) == expected


def test_network_summary_marks_upload_unavailable_when_any_request_is_unknown() -> None:
    summary = runtime_module._summarize_network_events(
        [
            {"request_body_size": 10, "request_body_size_available": True},
            {
                "request_body_size": 0,
                "request_body_size_available": False,
                "request_body_size_unavailable_reason": "request_body_size_unavailable",
            },
        ]
    )

    assert summary["request_body_size"] == 10
    assert summary["request_body_size_available"] is False
    assert summary["request_body_size_unavailable_reason"] == "request_body_size_unavailable"


def test_playwright_runtime_updates_zero_request_body_size_without_exposing_body(monkeypatch) -> None:
    manager = _FakePlaywrightManager()
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=lambda: manager))
    runtime = _build_runtime()
    runtime.enable_performance_collection()
    runtime.start()

    class _Request:
        method = "POST"
        url = "https://example.yonyougov.top/yondif-ams-be/api/save"
        resource_type = "xhr"
        post_data_buffer = "secret-request-body"

        def __init__(self) -> None:
            self.finished = False

        def sizes(self):
            if not self.finished:
                raise RuntimeError("request not finished")
            return {"requestBodySize": 0}

    request = _Request()
    runtime._page.event_handlers["request"](request)
    request.finished = True
    runtime._page.event_handlers["requestfinished"](request)

    summary = runtime.collect_network_summary()
    events = runtime.collect_network_events()
    assert summary["request_body_size"] == 0
    assert summary["request_body_size_available"] is True
    assert events[0]["request_body_size"] == 0
    assert events[0]["request_body_size_available"] is True
    assert "secret-request-body" not in json.dumps(
        {"raw_events": runtime._network_events, "summary": summary, "events": events}
    )


def test_playwright_runtime_uses_request_sizes_for_responses_without_content_length(monkeypatch) -> None:
    manager = _FakePlaywrightManager()
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=lambda: manager))
    runtime = _build_runtime()
    runtime.enable_performance_collection()
    runtime.start()

    class _Request:
        method = "POST"
        url = "https://example.yonyougov.top/yondif-ams-be/api/list"
        resource_type = "xhr"

        def response(self):
            return SimpleNamespace(url=self.url, status=200, headers={}, request=self)

        def sizes(self):
            return {
                "requestBodySize": 128,
                "requestHeadersSize": 64,
                "responseBodySize": 4096,
                "responseHeadersSize": 96,
            }

    runtime._page.event_handlers["requestfinished"](_Request())

    summary = runtime.collect_network_summary()
    assert summary["encoded_body_size"] == 4096
    assert summary["requests"][0]["encoded_body_size"] == 4096


def test_playwright_runtime_ignores_cancelled_request_sizes_during_browser_close(monkeypatch) -> None:
    manager = _FakePlaywrightManager()
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=lambda: manager))
    runtime = _build_runtime()
    runtime.enable_performance_collection()
    runtime.start()

    class _Request:
        method = "GET"
        url = "https://example.yonyougov.top/yondif-ams-be/api/list"
        resource_type = "xhr"

        def response(self):
            return SimpleNamespace(url=self.url, status=200, headers={"content-length": "512"}, request=self)

        def sizes(self):
            raise asyncio.CancelledError

    runtime._page.event_handlers["requestfinished"](_Request())

    summary = runtime.collect_network_summary()
    assert summary["requests"][0]["encoded_body_size"] == 512


def test_playwright_runtime_uses_playwright_relative_timing_for_request_duration(monkeypatch) -> None:
    manager = _FakePlaywrightManager()
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=lambda: manager))
    runtime = _build_runtime()
    runtime.enable_performance_collection()
    runtime.start()
    request = SimpleNamespace(
        method="GET",
        url="https://example.yonyougov.top/yondif-ams-be/api",
        resource_type="xhr",
        timing=lambda: {
            "startTime": 1760000000000,
            "connectEnd": 20,
            "requestEnd": 80,
            "responseEnd": 345,
        },
    )
    response = SimpleNamespace(url=request.url, status=200, headers={}, request=request)

    runtime._page.event_handlers["response"](response)

    summary = runtime.collect_network_summary()
    assert summary["top_slow_api_requests"][0]["duration_ms"] == 345


def test_playwright_runtime_updates_network_duration_when_request_finishes(monkeypatch) -> None:
    manager = _FakePlaywrightManager()
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=lambda: manager))
    runtime = _build_runtime()
    runtime.enable_performance_collection()
    runtime.start()

    class _Request:
        method = "GET"
        url = "https://example.yonyougov.top/static/app.js"
        resource_type = "script"

        def __init__(self) -> None:
            self._timing = {"startTime": 1760000000000, "responseEnd": -1, "requestEnd": -1, "connectEnd": 12}
            self._response = SimpleNamespace(url=self.url, status=200, headers={"content-length": "10"}, request=self)

        def timing(self):
            return self._timing

        def response(self):
            return self._response

    request = _Request()
    runtime._page.event_handlers["response"](request.response())
    request._timing = {"startTime": 1760000000000, "responseEnd": 640, "requestEnd": 120, "connectEnd": 12}
    runtime._page.event_handlers["requestfinished"](request)

    summary = runtime.collect_network_summary()
    assert summary["top_slow_static_resources"][0]["duration_ms"] == 640


def test_playwright_runtime_attributes_cross_step_request_to_starting_step(monkeypatch) -> None:
    manager = _FakePlaywrightManager()
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=lambda: manager))
    runtime = _build_runtime()
    runtime.enable_performance_collection()
    runtime.start()

    class _Request:
        method = "GET"
        url = "https://example.yonyougov.top/yondif-ams-be/api/list"
        resource_type = "xhr"

        def __init__(self) -> None:
            self._timing = {"startTime": 1760000000000, "responseEnd": -1, "requestEnd": -1}
            self._response = SimpleNamespace(url=self.url, status=200, headers={"content-length": "42"}, request=self)

        def timing(self):
            return self._timing

        def response(self):
            return self._response

    request = _Request()
    runtime.begin_performance_step({"suite_code": "smoke", "case_code": "case-a", "step_index": 1, "action": "open_menu"})
    runtime._page.event_handlers["request"](request)
    first_summary = runtime.collect_network_summary(reset=True)
    runtime.end_performance_step()

    runtime.begin_performance_step({"suite_code": "smoke", "case_code": "case-a", "step_index": 2, "action": "query.search"})
    request._timing = {"startTime": 1760000000000, "requestEnd": 60, "responseEnd": 320}
    runtime._page.event_handlers["requestfinished"](request)
    second_summary = runtime.collect_network_summary(reset=True)
    runtime.end_performance_step()

    events = runtime.collect_network_events()
    assert first_summary["request_count"] == 1
    assert first_summary["requests"][0]["step_index"] == 1
    assert second_summary["request_count"] == 0
    assert events[0]["step_index"] == 1
    assert events[0]["action"] == "open_menu"
    assert events[0]["completed_step_index"] == 2
    assert events[0]["completed_action"] == "query.search"
    assert events[0]["completed_step_context"] == "step"
    assert events[0]["duration_ms"] == 320


def test_playwright_runtime_marks_unattributed_requests_as_unknown(monkeypatch) -> None:
    manager = _FakePlaywrightManager()
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=lambda: manager))
    runtime = _build_runtime()
    runtime.enable_performance_collection()
    runtime.start()

    request = SimpleNamespace(method="GET", url="https://example.yonyougov.top/yondif-ams-be/api/background", resource_type="xhr")
    runtime._page.event_handlers["request"](request)

    summary = runtime.collect_network_summary(reset=True)

    assert summary["request_count"] == 1
    assert summary["requests"][0]["step_context"] == "unknown"


def test_request_duration_accepts_playwright_relative_timing() -> None:
    request = SimpleNamespace(
        timing=lambda: {
            "startTime": 1760000000000,
            "domainLookupStart": 1,
            "requestEnd": 40,
            "responseEnd": 123,
        }
    )

    assert _request_duration_ms(request) == 123


def test_playwright_runtime_captures_dynamic_matching_template_response(monkeypatch) -> None:
    manager = _FakePlaywrightManager()
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=lambda: manager))
    runtime = _build_runtime()
    runtime.start()
    payload = {"data": {"uidata": [{"divCode": "editRoot"}]}}
    request = SimpleNamespace(method="POST")
    response = SimpleNamespace(
        url="https://example.yonyougov.top/yondif-ams-be/ytemplate/assign/matchingTemplate?serviceCode=global00_-1_PM_INIT",
        request=request,
        json=lambda: payload,
    )

    runtime._page.event_handlers["response"](response)

    assert runtime.peek_dynamic_template_payload() == payload
    assert runtime.pop_dynamic_template_payload_if_current({"data": {}}) is None
    assert runtime.peek_dynamic_template_payload() == payload
    assert runtime.pop_dynamic_template_payload() == payload
    assert runtime.pop_dynamic_template_payload() is None


def test_playwright_runtime_exposes_page_response_events_since_cursor() -> None:
    runtime = _build_runtime()
    cursor = runtime.begin_page_response_capture()
    response = SimpleNamespace(
        url="https://example.yonyougov.top/service/detail",
        status=200,
        request=SimpleNamespace(method="GET"),
        json=lambda: {"data": {"serviceCode": "global00_-1_PM_INIT"}},
    )

    runtime._handle_response(response)
    next_cursor, events = runtime.page_responses_since(cursor)

    assert next_cursor == 1
    assert events == [{"method": "GET", "url": response.url, "status": 200, "response": response}]
    assert runtime.page_responses_since(next_cursor) == (1, [])


def test_playwright_runtime_begin_page_response_capture_discards_old_events() -> None:
    runtime = _build_runtime()
    runtime._page_response_events = [{"method": "GET", "url": "https://example.test/old"}]

    cursor = runtime.begin_page_response_capture()

    assert cursor == 0
    assert runtime.page_responses_since(cursor) == (0, [])


def test_playwright_runtime_evaluates_script_across_available_frames() -> None:
    class Frame:
        def __init__(self, name: str, value: Any = None, error: Exception | None = None) -> None:
            self.name = name
            self.url = f"https://example.test/{name}"
            self.value = value
            self.error = error

        def evaluate(self, script: str, payload: Any) -> Any:
            assert script == "scan"
            assert payload == {"fieldid": "root"}
            if self.error is not None:
                raise self.error
            return self.value

    runtime = _build_runtime()
    runtime._page = SimpleNamespace(
        frames=[Frame("main", [{"fieldid": "root"}]), Frame("broken", error=RuntimeError("detached"))]
    )

    assert runtime.evaluate_all_frames("scan", {"fieldid": "root"}) == [
        {
            "frame_name": "main",
            "frame_url": "https://example.test/main",
            "value": [{"fieldid": "root"}],
        }
    ]


def test_playwright_runtime_open_menu_applies_api_cookies_before_navigation(monkeypatch) -> None:
    manager = _FakePlaywrightManager()
    monkeypatch.setitem(sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=lambda: manager))
    session = requests.Session()
    session.cookies.set("SESSION", "abc", domain="example.yonyougov.top", path="/")
    runtime = _build_runtime(session=session)
    monkeypatch.setattr(runtime, "_wait_ready", lambda: None)

    runtime.start()
    runtime.open_menu(
        MenuTarget(
            menu_code="PM_INIT",
            menu_name="执行项目立项",
            path=["项目库", "执行项目管理", "执行项目立项"],
            service_code="global00_-1_GX_PM3_INIT",
        )
    )

    assert runtime._context.added_cookies
    assert runtime._page.goto_calls == ["https://example.yonyougov.top/#/service/global00_-1_GX_PM3_INIT"]


def test_playwright_runtime_exposes_foundational_page_adapter_operations() -> None:
    class VisibleLocator:
        @property
        def first(self):
            return self

        def wait_for(self, state: str, timeout: int) -> None:
            assert state == "visible"
            assert timeout == 8000

    main_frame = SimpleNamespace(name="", url="https://example.test/#/service/demo", parent_frame=None)
    child_frame = SimpleNamespace(name="demo", url="https://example.test/apps/demo", parent_frame=main_frame)
    page = SimpleNamespace(
        url=main_frame.url,
        main_frame=main_frame,
        frames=[main_frame, child_frame],
        locator=lambda _selector: VisibleLocator(),
        reload=lambda **kwargs: setattr(page, "reload_options", kwargs),
    )
    runtime = _build_runtime()
    runtime._page = page

    assert runtime.current_page_url() == main_frame.url
    assert runtime.wait_for_first_visible(['text="演示"'], timeout_ms=8000) is True
    assert runtime.page_frame_states() == [
        {"name": "", "url": main_frame.url, "is_main": True, "parent_is_main": False},
        {"name": "demo", "url": child_frame.url, "is_main": False, "parent_is_main": True},
    ]
    runtime.reload_page()
    assert page.reload_options == {"wait_until": "domcontentloaded"}


def test_build_tree_node_selectors_prioritize_exact_match() -> None:
    selectors = build_tree_node_selectors("101 综合司01")

    assert selectors[0] == 'text="101 综合司01"'
    assert any("a:has-text" in item for item in selectors)


def test_build_row_hover_selectors_cover_common_grid_rows() -> None:
    selectors = build_row_hover_selectors("360000241010010000039")

    assert selectors[0] == 'tr:has-text("360000241010010000039")'
    assert any('[role="row"]' in item for item in selectors)
    assert any(".ant-table-row" in item for item in selectors)


def test_build_row_action_selectors_prioritize_row_specific_fieldids() -> None:
    assert build_row_action_selectors("删除")[0] == '[fieldid="sc_btn"]'
    assert build_row_action_selectors("启用")[0] == '[fieldid="rowBtnEnable"]'
    assert build_row_action_selectors("停用")[0] == '[fieldid="rowBtnDisable"]'


def test_build_row_selection_checkbox_selectors_prioritize_first_column() -> None:
    selectors = build_row_selection_checkbox_selectors()

    assert selectors[0] == 'td:first-child input[type="checkbox"]'
    assert any("selection" in item for item in selectors)
    assert selectors[-1] == '[role="checkbox"]'


def test_build_table_data_row_selectors_cover_common_tables() -> None:
    selectors = build_table_data_row_selectors()

    assert selectors[0] == "tbody tr"
    assert any("ant-table" in item for item in selectors)
    assert any('[role="row"]' in item for item in selectors)


def test_build_tree_closed_switcher_selectors_cover_wui_tree_collapsed_nodes() -> None:
    selectors = build_tree_closed_switcher_selectors()

    assert any("wui-tree-center_close" in item for item in selectors)
    assert any("wui-tree-treenode-close" in item for item in selectors)


def test_build_toolbar_action_selectors_cover_overflow_toolbar_buttons() -> None:
    selectors = build_toolbar_action_selectors("导出")

    assert selectors[0] == '[fieldid="dc_btn"]'
    assert any('button:has-text("导出")' in item for item in selectors)


def test_build_toolbar_action_selectors_prefer_exact_text_before_contains() -> None:
    selectors = build_toolbar_action_selectors("保存")

    assert 'button:text-is("保存")' in selectors
    assert selectors.index('button:text-is("保存")') < selectors.index('button:has-text("保存")')


def test_playwright_runtime_toolbar_action_ignores_conflicting_fieldid_tab() -> None:
    runtime = _build_runtime()
    conflicting = _FakeActionLocator("待审核")
    runtime._page = _FakeActionPage(
        {
            '[fieldid="btn-audit"]': [conflicting],
            "button": [_FakeActionLocator("通过")],
        }
    )

    bound = runtime._resolve_visible_toolbar_action("通过", fieldid="btn-audit", aliases=["通过"])

    assert bound.runtime.selector == "button"
    assert conflicting.scroll_calls == 0


def test_build_toolbar_more_selectors_cover_common_more_buttons() -> None:
    selectors = build_toolbar_more_selectors()

    assert any("更多" in item for item in selectors)
    assert any("more" in item for item in selectors)


def test_build_toolbar_dropdown_item_selectors_scope_to_visible_popup_menus() -> None:
    selectors = build_toolbar_dropdown_item_selectors()

    assert ".ant-dropdown:visible .ant-dropdown-menu-item" in selectors
    assert ".wui-dropdown:visible [role=\"menuitem\"]" in selectors
    assert '[class*="popover"]:visible [class*="item"]' in selectors


def test_build_tab_action_selectors_prefer_fieldid_and_tab_scoped_text() -> None:
    selectors = build_tab_action_selectors("待提交", fieldid="stepWaitSubmit")

    assert selectors[0] == '[fieldid="stepWaitSubmit"]'
    assert '[role="tab"]:text-is("待提交")' in selectors
    assert 'text="待提交"' not in selectors


def test_build_tab_exact_text_selectors_scope_to_tab_like_elements() -> None:
    selectors = build_tab_exact_text_selectors()

    assert '[role="tab"]' in selectors
    assert any("tabs" in item.lower() for item in selectors)
    assert any("capsule" in item.lower() for item in selectors)
    assert "div" not in selectors


def test_build_editable_table_add_row_selectors_scope_to_table_footer() -> None:
    selectors = build_editable_table_add_row_selectors("新增")

    assert selectors[0] == '.ant-table-footer a:text-is("新增")'
    assert any(".wui-table-footer" in item for item in selectors)
    assert all("text-is" in item for item in selectors)


def test_editable_table_add_row_script_scores_external_table_label() -> None:
    assert "const tableLabelScore = (root) =>" in _EDITABLE_TABLE_ADD_ROW_SCRIPT
    assert "if (normalizeText(node.innerText || node.textContent).includes(table))" in _EDITABLE_TABLE_ADD_ROW_SCRIPT
    assert "const labels = Array.from(document.querySelectorAll('span, div, label, h1, h2, h3, h4'))" in _EDITABLE_TABLE_ADD_ROW_SCRIPT
    assert "rect.bottom <= rootRect.top + 8" in _EDITABLE_TABLE_ADD_ROW_SCRIPT
    assert "if (table && root && !rootText.includes(table)) continue;" not in _EDITABLE_TABLE_ADD_ROW_SCRIPT


def test_editable_table_add_row_script_accepts_leading_icon_text() -> None:
    assert "const actionTextMatches = (value) =>" in _EDITABLE_TABLE_ADD_ROW_SCRIPT
    assert "replace(/^[\\s+＋]+/" in _EDITABLE_TABLE_ADD_ROW_SCRIPT
    assert ".filter((el) => actionTextMatches(el.innerText || el.textContent))" in _EDITABLE_TABLE_ADD_ROW_SCRIPT


def test_editable_table_add_row_script_treats_ydf_placeholder_as_table_root() -> None:
    assert ".ydf-table-placeholder" in _EDITABLE_TABLE_ADD_ROW_SCRIPT
    assert "[class*=\"table-placeholder\"]" in _EDITABLE_TABLE_ADD_ROW_SCRIPT


def test_editable_table_add_row_script_uses_target_validation_root_when_scoped() -> None:
    assert "const targetValidationRootFor = (root) => {" in _EDITABLE_TABLE_ADD_ROW_SCRIPT
    assert "const broadValidationRootFor = (root) => {" in _EDITABLE_TABLE_ADD_ROW_SCRIPT
    assert (
        "return hasTargetTableScope ? targetValidationRootFor(root) : broadValidationRootFor(root);"
        in _EDITABLE_TABLE_ADD_ROW_SCRIPT
    )


def test_editable_table_add_row_script_reports_before_after_row_state() -> None:
    assert "const stateBefore = rowState(validationRootBefore.root);" in _EDITABLE_TABLE_ADD_ROW_SCRIPT
    assert "const state = await waitForRowStateChange(validationRootBefore, stateBefore, chosen.root);" in (
        _EDITABLE_TABLE_ADD_ROW_SCRIPT
    )
    assert "const rowStateChanged = rowStateReliable && (state.dataRowCount > stateBefore.dataRowCount" in (
        _EDITABLE_TABLE_ADD_ROW_SCRIPT
    )
    assert "row_state_before: stateBefore" in _EDITABLE_TABLE_ADD_ROW_SCRIPT
    assert "row_state_changed: rowStateChanged" in _EDITABLE_TABLE_ADD_ROW_SCRIPT
    assert "row_state_reliable:" in _EDITABLE_TABLE_ADD_ROW_SCRIPT
    assert "validation_root_source:" in _EDITABLE_TABLE_ADD_ROW_SCRIPT


def test_editable_table_add_row_script_reports_chosen_candidate_diagnostic() -> None:
    assert "chosen_candidate:" in _EDITABLE_TABLE_ADD_ROW_SCRIPT
    assert "top_candidates:" in _EDITABLE_TABLE_ADD_ROW_SCRIPT


def test_editable_table_add_row_script_ignores_empty_and_summary_rows() -> None:
    assert "暂无数据|暂时没有数据|点击上方查询条件搜索数据" in _EDITABLE_TABLE_ADD_ROW_SCRIPT
    assert "^小计(?:\\s|$)|^合计(?:\\s|$)" in _EDITABLE_TABLE_ADD_ROW_SCRIPT


def test_editable_table_add_row_script_polls_after_click_for_async_rows() -> None:
    assert "const waitForRowStateChange = async (previousResolution, previousState, anchor) => {" in (
        _EDITABLE_TABLE_ADD_ROW_SCRIPT
    )
    assert "for (let attempt = 0; attempt < 8; attempt += 1)" in _EDITABLE_TABLE_ADD_ROW_SCRIPT
    assert "await new Promise((resolve) => setTimeout(resolve, 250));" in _EDITABLE_TABLE_ADD_ROW_SCRIPT


def test_editable_table_add_row_script_skips_row_scoped_actions() -> None:
    assert "row-scoped-action" in _EDITABLE_TABLE_ADD_ROW_SCRIPT
    assert "const rowScopedAction = rowScope && !tableLevelAction;" in _EDITABLE_TABLE_ADD_ROW_SCRIPT
    assert "const rootState = rowState(root);" in _EDITABLE_TABLE_ADD_ROW_SCRIPT
    assert "rootState.dataRowCount > 0" in _EDITABLE_TABLE_ADD_ROW_SCRIPT
    assert "const stickyTableBodyAction =" in _EDITABLE_TABLE_ADD_ROW_SCRIPT


def test_editable_table_add_row_target_validation_does_not_score_ancestor_rows() -> None:
    start = _EDITABLE_TABLE_ADD_ROW_SCRIPT.index("const targetValidationRootFor = (root) => {")
    end = _EDITABLE_TABLE_ADD_ROW_SCRIPT.index("  const broadValidationRootFor = (root) => {", start)
    target_validation = _EDITABLE_TABLE_ADD_ROW_SCRIPT[start:end]

    assert "rootMatchesIdentity(node)" in target_validation
    assert "columnIdentityScore(node)" in target_validation
    assert "rowCount + columnIdentityScore" not in target_validation
    assert "bestScore" not in target_validation


def test_editable_table_add_row_identity_match_does_not_treat_containing_ancestor_as_target() -> None:
    start = _EDITABLE_TABLE_ADD_ROW_SCRIPT.index("const rootMatchesIdentity = (root) => {")
    end = _EDITABLE_TABLE_ADD_ROW_SCRIPT.index("  const actionTextMatches = (value) => {", start)
    identity_match = _EDITABLE_TABLE_ADD_ROW_SCRIPT[start:end]

    assert "const rootHasOwnIdentity = (root) =>" in _EDITABLE_TABLE_ADD_ROW_SCRIPT
    assert "const closestIdentityTableRoot = (root, anchor = null) =>" in _EDITABLE_TABLE_ADD_ROW_SCRIPT
    assert "return Boolean(root.querySelector(identitySelectorForValue(targetTableFieldid)));" not in identity_match


def test_editable_table_add_row_target_validation_builds_split_table_cluster() -> None:
    assert "const splitTableClusterRoot = (root) => {" in _EDITABLE_TABLE_ADD_ROW_SCRIPT
    assert "wui-table-header" in _EDITABLE_TABLE_ADD_ROW_SCRIPT
    assert "wui-table-body" in _EDITABLE_TABLE_ADD_ROW_SCRIPT
    assert "return anchorIdentityRoot(identityRoot, anchor);" in _EDITABLE_TABLE_ADD_ROW_SCRIPT


def test_editable_table_add_row_script_matches_table_runtime_identity_suffix() -> None:
    start = _EDITABLE_TABLE_ADD_ROW_SCRIPT.index("const tableIdentityAttributeNames = [")
    end = _EDITABLE_TABLE_ADD_ROW_SCRIPT.index("  const identityAttributeNames = [", start)
    table_identity = _EDITABLE_TABLE_ADD_ROW_SCRIPT[start:end]

    assert "data-index" not in table_identity
    assert "data-key" not in table_identity
    assert "const tableIdentityMatchesValue = (value) =>" in _EDITABLE_TABLE_ADD_ROW_SCRIPT
    assert "value === `${targetTableFieldid}_table`" in _EDITABLE_TABLE_ADD_ROW_SCRIPT


def test_editable_table_add_row_script_anchors_descendant_identity_to_action_root() -> None:
    assert "const globalTargetIdentityRoot = (anchor = null) =>" in _EDITABLE_TABLE_ADD_ROW_SCRIPT
    assert "source: 'target-global-identity'" in _EDITABLE_TABLE_ADD_ROW_SCRIPT
    assert "const anchorIdentityRoot = (identityRoot, anchor) =>" in _EDITABLE_TABLE_ADD_ROW_SCRIPT
    assert "const identityElementRoot = (identityEl) =>" in _EDITABLE_TABLE_ADD_ROW_SCRIPT
    assert "const anchoredRoots = [];" in _EDITABLE_TABLE_ADD_ROW_SCRIPT
    assert "const identityRoot = closestIdentityTableRoot(node, root);" in _EDITABLE_TABLE_ADD_ROW_SCRIPT


def test_playwright_runtime_add_editable_table_row_reports_table_name_mismatch(monkeypatch) -> None:
    runtime = _build_runtime()
    page = _FakeEditableAddRowPage(None, [])
    runtime._page = page
    debug = {
        "candidates": [
            {
                "text": "新增",
                "skipped": "table-label-mismatch",
                "hasRoot": True,
                "nearbyLabels": ["需求调查成员", "需求调查对象"],
            }
        ]
    }

    monkeypatch.setattr(runtime, "_editable_table_search_contexts", lambda: [page])
    monkeypatch.setattr(runtime, "_read_editable_table_add_row_debug", lambda context: debug)
    monkeypatch.setattr(runtime, "_find_first_visible_selector", lambda selectors: None)
    monkeypatch.setattr(runtime, "_collect_page_diagnostic_text", lambda: "diag")
    monkeypatch.setattr(runtime, "_save_diagnostic_screenshot", lambda name: None)

    with pytest.raises(RuntimeError, match="可编辑表格名称未匹配.*需求调查员.*需求调查成员"):
        runtime.add_editable_table_row(label="新增", table="需求调查员")


def test_playwright_runtime_editable_table_add_row_fails_when_click_leaves_empty_row(monkeypatch) -> None:
    runtime = _build_runtime()
    page = _FakeEditableAddRowPage(None, [])
    runtime._page = page
    debug = {
        "failure": "add-row-no-data-row",
        "tableFieldid": "treasuryDetailTable",
        "rowState": {"rowCount": 1, "rowTexts": ["暂无数据"], "empty": True},
        "validationRoot": {"text": "缴库明细表格 暂无数据"},
        "candidates": [{"text": "新增", "skipped": "empty-after-click"}],
    }

    monkeypatch.setattr(runtime, "_editable_table_search_contexts", lambda: [page])
    monkeypatch.setattr(runtime, "_read_editable_table_add_row_debug", lambda context: debug)
    monkeypatch.setattr(runtime, "_find_first_visible_selector", lambda selectors: None)
    monkeypatch.setattr(runtime, "_collect_page_diagnostic_text", lambda: "diag")
    monkeypatch.setattr(runtime, "_save_diagnostic_screenshot", lambda name: None)

    with pytest.raises(RuntimeError, match="可编辑表格新增行未生效.*treasuryDetailTable.*缴库明细表格.*暂无数据"):
        runtime.add_editable_table_row(label="新增", table="缴库明细表格")


def test_playwright_runtime_editable_table_add_row_does_not_fallback_click_after_script_failure(
    monkeypatch,
) -> None:
    runtime = _build_runtime()
    page = _FakeEditableAddRowPage(None, [])
    runtime._page = page
    debug = {
        "failure": "add-row-no-data-row",
        "tableFieldid": "table2",
        "rowState": {"rowCount": 1, "rowTexts": ["暂无数据"], "dataRowCount": 0, "empty": True},
        "validationRoot": {"text": "调入方 暂无数据 小计 0.00"},
    }
    fallback_clicks: list[str] = []

    class _Fallback:
        def click(self, timeout: int = 0) -> None:
            fallback_clicks.append(str(timeout))

    monkeypatch.setattr(runtime, "_editable_table_search_contexts", lambda: [page])
    monkeypatch.setattr(runtime, "_read_editable_table_add_row_debug", lambda context: debug)
    monkeypatch.setattr(runtime, "_find_first_visible_selector", lambda selectors: "button.fallback")
    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: _Fallback())
    monkeypatch.setattr(runtime, "_save_diagnostic_screenshot", lambda name: None)

    with pytest.raises(RuntimeError, match="可编辑表格新增行未生效.*table2.*调入方.*暂无数据"):
        runtime.add_editable_table_row(label="新增", table="调入方")

    assert fallback_clicks == []


def test_playwright_runtime_fill_editable_table_cell_uses_switch_control(monkeypatch) -> None:
    runtime = _build_runtime()
    cell = object()
    calls: list[tuple[object, object]] = []

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: cell)
    monkeypatch.setattr(runtime, "_first_visible_child_locator", lambda current_root, selectors: None)
    monkeypatch.setattr(runtime, "_active_editable_locator", lambda: None)
    monkeypatch.setattr(runtime, "_locator_is_directly_editable", lambda locator: False)
    monkeypatch.setattr(runtime, "_editable_table_cell_plain_editor_overrides_reference_metadata", lambda *_args: False)
    monkeypatch.setattr(runtime._popup_reference_module(), "editable_cell_looks_like_reference", lambda *_args: False)
    monkeypatch.setattr(runtime, "_read_switch_field_state", lambda current_root: False)
    monkeypatch.setattr(runtime, "_set_switch_field_value", lambda current_root, value: calls.append((current_root, value)))
    monkeypatch.setattr(runtime, "_describe_editable_table_cell", lambda current_root: "diag")
    monkeypatch.setattr(runtime, "_save_diagnostic_screenshot", lambda name: None)

    runtime._fill_active_editable_table_cell("[data-cell]", True)

    assert calls == [(cell, True)]


def test_editable_table_cell_selector_ignores_required_header_marker() -> None:
    assert "normalizeHeader" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "replace(/^[\\s*＊✱✳※]+/" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "normalizeHeader(header.innerText" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT


def test_editable_table_cell_selector_scopes_rows_to_matched_header_table() -> None:
    assert "const candidates = []" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "const root = tableRoot(header)" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "headerRoot.parentElement" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "|| header.parentElement" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "rowRoot.querySelectorAll(rowSelector)" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "directCells(headerRow, headerSelector)" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert ".wui-table-header" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert ".wui-table-row" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "rowRoots.length < 6" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "headerRect.bottom - 4" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "rect.bottom <= rootRect.top + 8" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "candidate.score < 0" not in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT


def test_editable_table_cell_selector_can_filter_by_column_group_path() -> None:
    assert "columnGroupsMatch" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "headerGroupPath" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "column-group-geometry" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT


def test_editable_table_cell_selector_prefers_exact_header_over_prefix_match() -> None:
    assert "const headerMatchScore = (text) =>" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "if (text === wanted) return 100" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "matchScore" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "b.matchScore - a.matchScore" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT


def test_editable_table_cell_selector_matches_parentheses_shape_from_real_header() -> None:
    assert "const asciiUnitSuffixMatch = (text, wanted) =>" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "if (asciiUnitSuffixMatch(text, wanted)) return 40" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "const toAsciiParens = (value) =>" not in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "rejectFullWidthParenRequest" not in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "if (wanted.includes(text)) return 40" not in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT


def test_editable_table_cell_selector_ignores_summary_rows_for_last_row() -> None:
    assert "const isSummaryRow = (row) =>" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "小计" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "合计" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "rows.filter((row) => !isSummaryRow(row))" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT


def test_editable_table_cell_selector_maps_multi_header_child_by_position() -> None:
    assert "const cellForHeader = (cells, header, fallbackIndex) =>" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "headerCenterX" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "const cell = cells[candidate.columnIndex]" not in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT


def test_editable_table_cell_selector_prefers_column_identity_and_reports_fallback() -> None:
    assert "columnFieldid" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "dataField" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "tableFieldid" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "identity-cell" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "identity-header-geometry" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "text-geometry" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "identityConflict" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT


def test_runtime_scan_keeps_uikey_wrapper_as_unverified_and_targets_inner_control() -> None:
    assert "const directControl = canEditControl(el)" in runtime_module._DOM_SCAN_SCRIPT
    assert "preferUiKey && !directControl ? uiKey : null" in runtime_module._DOM_SCAN_SCRIPT


def test_runtime_scan_preserves_each_dom_control_before_binding() -> None:
    assert "const results = [];" in runtime_module._DOM_SCAN_SCRIPT
    assert "results.push({" in runtime_module._DOM_SCAN_SCRIPT
    assert "const unique = new Map();" not in runtime_module._DOM_SCAN_SCRIPT


@pytest.mark.parametrize("in_frame", [False, True])
@pytest.mark.parametrize("search_readonly", [False, True])
def test_query_select_binds_identity_root_with_readonly_search_input(
    _popup_reference_page, in_frame, search_readonly,
) -> None:
    from ydf_browser.binder import bind_manifest

    page = _popup_reference_page
    page.set_content('<iframe style="width:1000px;height:700px"></iframe>' if in_frame else '')
    context = page.frames[1] if in_frame else page.main_frame
    context.set_content(f'''
        <div uikey="202308181621065311411754912743" class="wui-form-item">
          <div class="wui-form-item-label"><label for="accStaCode" title="账户状态">账户状态</label></div>
          <div class="wui-form-item-control">
            <div class="wui-select wui-select-multiple" fieldid="query_accStaCode">
              <div class="wui-select-selector">
                <span class="wui-select-selection-item" title="启用">启用</span>
                <input role="combobox" fieldid="query_accStaCode_search_input" {'readonly' if search_readonly else ''}>
              </div>
            </div>
          </div>
        </div>
    ''')
    runtime = _build_runtime()
    runtime._page = page
    candidate = ElementCandidate(
        key="account_state", fieldid="query_accStaCode", label="账户状态", title="",
        region_key="query", region_fieldid="query", element_type="formItem",
        component_name="YDFSelect", data_field="accStaCode",
        runtime_fieldids=["202308181621065311411754912743", "query_accStaCode", "query_accStaCode_search_input"],
        verified_runtime_fieldids=["202308181621065311411754912743"],
    )
    manifest = PageManifest(PageMeta("root", "basAccount", None, None), query_fields=[candidate])

    binding = bind_manifest(manifest, runtime.capture_runtime_elements(manifest))

    bound = binding.fields_by_alias["账户状态"]
    root = runtime._resolve_visible_locator(bound.runtime.selector)
    assert bound.runtime.tag_name != "label"
    if search_readonly:
        assert bound.runtime.is_identity_root is True
        assert root.locator('input[role="combobox"]').count() == 1
    else:
        assert bound.runtime.tag_name == "input"
    assert runtime._looks_like_choice_field(root, bound) is True


def test_runtime_scan_keeps_offscreen_pointer_receivability_unknown(_popup_reference_page) -> None:
    page = _popup_reference_page
    page.set_content(
        """
        <div style="height: 1200px"></div>
        <div uikey="2025051418225652189824966080132">
          <textarea fieldid="lcdPanel_dcjg_surveySituation1"></textarea>
        </div>
        <textarea fieldid="blocked" style="position: fixed; top: 20px; pointer-events: none"></textarea>
        """
    )
    runtime = _build_runtime()
    runtime._page = page

    scanned = runtime._scan_frame(page.main_frame)
    textarea = next(item for item in scanned if item.get("tag_name") == "textarea")
    blocked = next(item for item in scanned if item.get("fieldid") == "blocked")

    assert textarea["visible"] is True
    assert textarea["pointer_receivable"] is None
    assert blocked["pointer_receivable"] is False


@pytest.mark.parametrize("in_frame", [False, True])
@pytest.mark.parametrize("axis", ["x", "y"])
def test_form_fill_scrolls_field_clipped_by_scroll_container(_popup_reference_page, in_frame, axis) -> None:
    from ydf_browser.binder import bind_manifest

    page = _popup_reference_page
    context = page
    if in_frame:
        page.set_content('<iframe style="width:1000px;height:700px"></iframe>')
        context = page.frames[1]
    margin = "margin-left:300px" if axis == "x" else "margin-top:300px"
    panel = "left:280px;top:0" if axis == "x" else "left:0;top:220px"
    context.set_content(f'''
        <div id="form" style="position:absolute;left:100px;top:100px;width:180px;height:120px;overflow:auto">
          <textarea fieldid="reviewComment" style="display:block;width:80px;height:40px;{margin}"></textarea>
        </div>
        <div style="position:fixed;{panel};right:0;bottom:0;background:white"></div>
    ''')
    runtime = _build_runtime()
    runtime._page = page
    field = ElementCandidate(
        key="reviewComment", fieldid="reviewComment", label="评审内容及意见", title="",
        region_key="baseForm", region_fieldid="baseForm", element_type="formItem",
        component_name="YDFTextArea", verified_runtime_fieldids=["reviewComment"],
    )
    manifest = PageManifest(PageMeta("root", "bgtMainBill", None, None), fields=[field])
    binding = bind_manifest(manifest, runtime.capture_runtime_elements(manifest))

    assert "评审内容及意见" not in binding.incompatible_fields
    bound = binding.fields_by_alias["评审内容及意见"]
    assert bound.runtime.pointer_receivable is None
    assert bound.contract_path["applicability"] == "unverified"
    result = runtime.fill_form_field(bound, "回归评审意见")

    assert result["confirmed"] is True
    assert context.locator("textarea").input_value() == "回归评审意见"
    scroll = "scrollLeft" if axis == "x" else "scrollTop"
    assert context.locator("#form").evaluate(f"el => el.{scroll}") > 0


@pytest.mark.parametrize(
    ("margin", "overflow", "blocked", "expected"),
    [(116, "auto", False, True), (116, "auto", True, False), (300, "hidden", False, False)],
)
def test_runtime_scan_checks_visible_scroll_container_intersection(
    _popup_reference_page, margin, overflow, blocked, expected,
) -> None:
    page = _popup_reference_page
    page.set_content(f'''
        <div style="position:absolute;top:100px;height:120px;width:400px;overflow:{overflow}">
          <textarea fieldid="reviewComment" style="display:block;margin-top:{margin}px;height:160px"></textarea>
        </div>
        <div style="position:fixed;top:220px;bottom:0;width:500px;background:white"></div>
    ''')
    if blocked:
        page.locator("body").evaluate('''el => el.insertAdjacentHTML('beforeend',
            '<div style="position:fixed;inset:0;z-index:99;background:white"></div>')''')
    runtime = _build_runtime()
    runtime._page = page

    scanned = runtime.capture_runtime_elements(None)

    assert next(item for item in scanned if item.get("fieldid") == "reviewComment")["pointer_receivable"] is expected


@pytest.fixture
def _scroll_review_manifest():
    field = ElementCandidate(
        key="review", fieldid="review", label="评审内容及意见", title="",
        region_key=None, region_fieldid=None, element_type="formItem",
        component_name="YDFTextArea", verified_runtime_fieldids=["review"],
    )
    return PageManifest(PageMeta("root", "bgtMainBill", None, None), fields=[field])


@pytest.mark.parametrize("in_frame", [False, True])
@pytest.mark.parametrize("kind", ["nested_clip", "zero_scrollport", "fixed", "fixed_parent", "absolute"])
def test_runtime_scan_rejects_unrecoverable_or_covered_field(
    _popup_reference_page, _scroll_review_manifest, in_frame, kind,
) -> None:
    from ydf_browser.binder import bind_manifest

    page = _popup_reference_page
    context = page
    if in_frame:
        page.set_content('<iframe style="width:1000px;height:700px"></iframe>')
        context = page.frames[1]
    if kind == "nested_clip":
        html = '''<div style="height:100px;width:500px;overflow:auto">
            <div style="height:100px;overflow:clip"><textarea fieldid="review" style="margin-top:300px"></textarea></div>
            <div style="height:800px"></div></div>'''
    elif kind == "zero_scrollport":
        html = '<div style="height:0;width:500px;overflow:auto"><textarea fieldid="review"></textarea></div>'
    elif kind == "fixed_parent":
        html = '''<div style="height:100px;width:500px;overflow:auto">
            <div style="height:800px"></div><div style="position:fixed;top:300px">
              <textarea fieldid="review"></textarea></div></div>'''
    else:
        html = f'''<div style="position:relative"><div style="height:100px;width:500px;overflow:auto">
            <div style="height:800px"></div><textarea fieldid="review" style="position:{kind};top:300px"></textarea>
            </div></div>'''
    context.set_content(html + '<div style="position:fixed;top:100px;bottom:0;width:500px;background:white;z-index:9"></div>')
    runtime = _build_runtime()
    runtime._page = page

    scanned = runtime.capture_runtime_elements(_scroll_review_manifest)
    target = next(item for item in scanned if item.get("fieldid") == "review")

    assert target["pointer_receivable"] is False
    assert not bind_manifest(_scroll_review_manifest, scanned).bound_fields
    assert context.locator("textarea").input_value() == ""


@pytest.mark.parametrize(
    ("position", "parent_style", "expected"),
    [("fixed", "", True), ("fixed", "transform:translateZ(0)", None),
     ("absolute", "", True), ("absolute", "position:relative", None)],
)
def test_runtime_scan_uses_positioned_field_containing_block(
    _popup_reference_page, position, parent_style, expected,
) -> None:
    page = _popup_reference_page
    page.set_content(f'''<div style="position:relative;top:100px">
        <div style="height:100px;width:500px;overflow:auto;{parent_style}">
          <textarea fieldid="review" style="position:{position};top:300px"></textarea>
          <div style="height:800px"></div></div></div>''')
    runtime = _build_runtime()
    runtime._page = page

    scanned = runtime.capture_runtime_elements(None)

    assert next(item for item in scanned if item.get("fieldid") == "review")["pointer_receivable"] is expected


@pytest.mark.parametrize("overflow", ["hidden", "clip"])
def test_runtime_scan_preserves_recovery_inside_non_scrolling_ancestor(_popup_reference_page, overflow) -> None:
    page = _popup_reference_page
    page.set_content(f'''<div style="height:100px;width:500px;overflow:{overflow}">
        <div style="height:100px;overflow:auto"><textarea fieldid="review" style="margin-top:300px"></textarea>
          <div style="height:800px"></div></div></div>''')
    runtime = _build_runtime()
    runtime._page = page

    scanned = runtime.capture_runtime_elements(None)

    assert next(item for item in scanned if item.get("fieldid") == "review")["pointer_receivable"] is None


@pytest.mark.parametrize("display", ["inline", "contents"])
def test_runtime_scan_does_not_clip_through_non_container_box(_popup_reference_page, display) -> None:
    page = _popup_reference_page
    page.set_content(f'<div style="display:{display};overflow:hidden"><textarea fieldid="review"></textarea></div>')
    runtime = _build_runtime()
    runtime._page = page

    scanned = runtime.capture_runtime_elements(None)

    assert next(item for item in scanned if item.get("fieldid") == "review")["pointer_receivable"] is True


@pytest.mark.parametrize("axis", ["x", "y"])
@pytest.mark.parametrize("scale", [0.5, 2])
def test_form_fill_scrolls_scaled_container(
    _popup_reference_page, _scroll_review_manifest, axis, scale,
) -> None:
    from ydf_browser.binder import bind_manifest

    page = _popup_reference_page
    margin = "margin-left:180px" if axis == "x" else "margin-top:180px"
    page.set_content(f'''<div id="form" style="position:absolute;top:100px;left:100px;width:120px;height:120px;
        overflow:auto;border:4px solid black;transform:scale({scale});transform-origin:top left">
        <textarea fieldid="review" style="display:block;width:80px;height:40px;{margin}"></textarea></div>''')
    rect = page.locator("#form").bounding_box()
    panel = f'left:{rect["x"] + rect["width"]}px;top:0' if axis == "x" else f'top:{rect["y"] + rect["height"]}px;left:0'
    page.locator("body").evaluate("(el, panel) => el.insertAdjacentHTML('beforeend', panel)",
        f'<div style="position:fixed;{panel};right:0;bottom:0;background:white"></div>')
    runtime = _build_runtime()
    runtime._page = page
    binding = bind_manifest(_scroll_review_manifest, runtime.capture_runtime_elements(_scroll_review_manifest))

    assert binding.fields_by_alias["评审内容及意见"].runtime.pointer_receivable is None
    result = runtime.fill_form_field(binding.fields_by_alias["评审内容及意见"], "缩放回归")

    assert result["confirmed"] is True
    assert page.locator("textarea").input_value() == "缩放回归"
    scroll = "scrollLeft" if axis == "x" else "scrollTop"
    assert page.locator("#form").evaluate(f"el => el.{scroll}") > 0


@pytest.mark.parametrize("scale_style", ["transform:scale(2);transform-origin:top left", "zoom:2"])
def test_runtime_scan_rejects_covered_visible_scaled_field(_popup_reference_page, scale_style) -> None:
    page = _popup_reference_page
    page.set_content(f'''<div style="position:absolute;top:100px;left:100px;height:120px;width:400px;
        overflow:auto;border:4px solid black;{scale_style}">
        <textarea fieldid="review" style="display:block;margin-top:80px;height:40px"></textarea></div>
        <div style="position:fixed;inset:0;z-index:9;background:white"></div>''')
    runtime = _build_runtime()
    runtime._page = page

    scanned = runtime.capture_runtime_elements(None)

    assert next(item for item in scanned if item.get("fieldid") == "review")["pointer_receivable"] is False


@pytest.mark.parametrize("height", [850, 874, 875, 918, 919, 930])
def test_form_fill_wrapped_scroll_field_at_height_boundaries(_popup_reference_page, request, height) -> None:
    from ydf_browser.binder import bind_manifest

    page = _popup_reference_page
    viewport = page.viewport_size
    request.addfinalizer(lambda: page.set_viewport_size(viewport))
    page.set_viewport_size({"width": 1686, "height": height - 87})
    key = "2023042314414892207813816827400"
    fieldid = "20221130164140156649558989275_reviewComment"
    page.set_content(f'''<div id="form" style="position:absolute;top:162px;left:50px;width:1250px;
        height:{height - 143 - 162}px;overflow:auto"><div style="height:605px"></div>
        <div uikey="{key}" style="position:relative;height:100px">
          <textarea id="{key}" fieldid="{fieldid}" style="position:absolute;top:4px;left:142px;
            width:1050px;height:90px;padding:0;border:0"></textarea></div></div>
        <div style="position:fixed;top:{height - 143}px;left:50px;width:1250px;height:48px;background:white"></div>''')
    runtime = _build_runtime()
    runtime._page = page
    field = ElementCandidate(
        key=key, fieldid=fieldid, label="评审内容及意见", title="",
        region_key=None, region_fieldid=None, element_type="formItem", component_name="YDFTextArea",
        runtime_fieldids=[key, fieldid], verified_runtime_fieldids=[key],
    )
    manifest = PageManifest(PageMeta("root", "bgtMainBill", None, None), fields=[field])
    binding = bind_manifest(manifest, runtime.capture_runtime_elements(manifest))

    assert not binding.incompatible_fields
    assert len(binding.bound_fields) == 1
    assert binding.bound_fields[0].runtime.tag_name == "textarea"
    result = runtime.fill_form_field(binding.bound_fields[0], "边界回归")

    assert result["confirmed"] is True
    assert page.locator("textarea").input_value() == "边界回归"
    assert page.locator("#form").evaluate("el => el.scrollTop") > 0


@pytest.mark.parametrize("in_frame", [False, True])
def test_form_fill_does_not_force_value_when_scroll_reveals_covered_field(
    _popup_reference_page, _scroll_review_manifest, in_frame,
) -> None:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from ydf_browser.binder import bind_manifest

    page = _popup_reference_page
    context = page
    if in_frame:
        page.set_content('<iframe style="width:1000px;height:700px"></iframe>')
        context = page.frames[1]
    context.set_content('''<script>window.inputCount=0</script><div style="height:1200px"></div>
        <textarea fieldid="review" oninput="window.inputCount++"></textarea>''')
    page.locator("body").evaluate('''el => el.insertAdjacentHTML('beforeend',
        '<div style="position:fixed;inset:0;z-index:9;background:white"></div>')''')
    runtime = _build_runtime()
    runtime._page = page
    binding = bind_manifest(_scroll_review_manifest, runtime.capture_runtime_elements(_scroll_review_manifest))
    bound = binding.fields_by_alias["评审内容及意见"]
    assert bound.runtime.pointer_receivable is None

    with pytest.raises(PlaywrightTimeoutError):
        runtime.fill_form_field(bound, "不应录入")

    assert context.locator("textarea").input_value() == ""
    assert context.evaluate("window.inputCount") == 0


def test_editable_table_add_row_validates_against_resolved_scope_token(_popup_reference_page) -> None:
    page = _popup_reference_page
    page.set_content(
        """
        <style>
          #app { margin-top: 100px; }
          table { width: 600px; }
          td { height: 24px; }
          .ydf-table-placeholder-add-button { width: 80px; height: 24px; }
        </style>
        <div id="app" fieldid="lcdTable_upDemandSurveyMember">
          <table id="background"><tbody><tr><td>背景1</td></tr><tr><td>背景2</td></tr></tbody></table>
          <section data-ydf-table-scope-token="member-scope-0">
            <h3>需求调查成员</h3>
            <table><tbody id="member-body"><tr><td>1</td></tr></tbody></table>
            <div
              class="ydf-table-placeholder-add-button"
              fieldid="lcdTable_upDemandSurveyMember_add_button"
              onclick="document.querySelector('#member-body').insertAdjacentHTML('beforeend', '<tr><td>2</td></tr>')"
            >新增</div>
          </section>
        </div>
        """
    )

    result = page.evaluate(
        _EDITABLE_TABLE_ADD_ROW_SCRIPT,
        {
            "label": "新增",
            "table": "需求调查成员",
            "tableFieldid": "lcdTable_upDemandSurveyMember",
            "tableColumns": ["序号", "姓名"],
            "tableScopeToken": "member-scope-0",
        },
    )

    assert result["validation_root_source"] == "resolved-table-scope"
    assert result["row_state_before"]["dataRowCount"] == 1
    assert result["row_state"]["dataRowCount"] == 2


@pytest.mark.parametrize("initial_rows", [0, 1])
def test_editable_table_add_row_returns_empty_state_once_when_form_opens(_popup_reference_page, monkeypatch, initial_rows) -> None:
    page = _popup_reference_page
    page.set_content(
        """
        <style>
          #app { margin-top: 100px; }
          table { width: 600px; }
          td { height: 24px; }
          .ydf-table-placeholder-add-button { width: 80px; height: 24px; }
          [role="dialog"] { position: fixed; top: 160px; width: 500px; height: 300px; }
        </style>
        <section
          id="app"
          fieldid="upProjectPurTable"
          data-ydf-table-scope-token="plan-detail-scope"
        >
          <h3>计划明细</h3>
          <table><tbody><tr><td>暂无数据</td></tr></tbody></table>
          <button
            class="ydf-table-placeholder-add-button"
            fieldid="upProjectPurTable_add_button"
            onclick="window.addRowClicks += 1; document.querySelector('#detail-form').hidden = false"
          >新增</button>
        </section>
        <div id="detail-form" role="dialog" hidden>计划明细表单<input aria-label="采购品目"></div>
        <script>window.addRowClicks = 0</script>
        """
    )
    runtime = _build_runtime()
    runtime._page = page
    scope = ResolvedTableScope(
        label="计划明细",
        region_fieldid="upProjectPurTable",
        runtime_fieldid="upProjectPurTable",
        foreground=True,
        columns=(),
        required_columns=(),
        token="plan-detail-scope",
        evidence=(),
    )

    if initial_rows:
        page.locator("tbody").evaluate("node => node.innerHTML = '<tr><td>已有明细</td></tr>'")
    waits = []
    monkeypatch.setattr(page, "wait_for_timeout", waits.append)
    page.evaluate("""() => {
        window.rowPolls = 0;
        window.originalRowTimeout = window.setTimeout;
        window.setTimeout = (fn, ms) => {
            if (ms === 250) window.rowPolls++;
            return window.originalRowTimeout(fn, ms);
        };
    }""")
    try:
        result = runtime.add_editable_table_row(label="新增", table_scope=scope)
    finally:
        page.evaluate("() => window.setTimeout = window.originalRowTimeout")

    assert page.locator("#detail-form").is_visible() is True
    assert page.evaluate("() => window.addRowClicks") == 1
    assert page.evaluate("() => window.rowPolls") < 8
    assert 800 not in waits
    assert result["row_state_before"]["dataRowCount"] == initial_rows
    assert result["row_state"]["dataRowCount"] == initial_rows
    assert result["row_state_changed"] is False
    assert result["row_state_reliable"] is True
    assert result["validation_root_source"] == "resolved-table-scope"
    assert result["chosen_candidate"]["source"] == "table-fieldid-add-button"


def test_editable_table_add_row_does_not_click_when_resolved_scope_token_is_stale(_popup_reference_page) -> None:
    page = _popup_reference_page
    page.set_content(
        """
        <style>
          #app { margin-top: 100px; }
          .ydf-table-placeholder-add-button { width: 80px; height: 24px; }
        </style>
        <div id="app">
          <h3>其他明细</h3>
          <table>
            <tbody><tr><td>背景1</td><td><button
              fieldid="lcdTable_other_add_button"
              onclick="this.dataset.clicked = '1'"
            >新增</button></td></tr></tbody>
          </table>
        </div>
        """
    )
    runtime = _build_runtime()
    runtime._page = page
    scope = ResolvedTableScope(
        label="需求调查成员",
        region_fieldid="lcdTable_upDemandSurveyMember",
        runtime_fieldid="lcdTable_upDemandSurveyMember",
        foreground=True,
        columns=("序号", "姓名"),
        required_columns=(),
        token="stale-member-scope",
        evidence=(),
    )

    with pytest.raises(RuntimeError, match="表格作用域令牌失效"):
        runtime.add_editable_table_row(label="新增", table_scope=scope)

    assert page.locator('[fieldid="lcdTable_other_add_button"]').get_attribute("data-clicked") is None


def test_runtime_scan_selector_uses_marker_without_document_wide_uniqueness_queries() -> None:
    assert "document.querySelectorAll(candidate)" not in runtime_module._DOM_SCAN_SCRIPT
    assert "scan-${frameIndex}-${Date.now()}-${runtimeScanId}" in runtime_module._DOM_SCAN_SCRIPT
    assert "`${semanticSelector}${directIdentity ? '' : ' '}${markerSelector}`" in runtime_module._DOM_SCAN_SCRIPT


def test_editable_table_cell_selector_accepts_platform_editcell_identity() -> None:
    assert "platformCellFieldid" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "platformCellFieldidPrefix" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT
    assert "value.startsWith(platformCellFieldidPrefix)" in _EDITABLE_TABLE_CELL_SELECTOR_SCRIPT


def test_build_query_action_selectors_strictly_bind_search_icon_button() -> None:
    selectors = build_query_action_selectors("查询")

    assert selectors[0] == "button.lcd-query-string-config-query"
    assert "button.wui-button-icon-only:has(.icon-sousuo)" in selectors
    assert "button:has(.icon-sousuo)" in selectors


def test_build_query_action_selectors_include_rule_based_fieldids() -> None:
    selectors = build_query_action_selectors("查询", fieldids=["dataQueryArea_query_icon"])

    assert selectors[:4] == [
        '[fieldid="dataQueryArea_query_icon"]',
        '[data-fieldid="dataQueryArea_query_icon"]',
        'button[fieldid="dataQueryArea_query_icon"]',
        'button[data-fieldid="dataQueryArea_query_icon"]',
    ]


def test_playwright_runtime_query_reset_uses_unique_foreground_region(monkeypatch) -> None:
    runtime = PlaywrightRuntime.__new__(PlaywrightRuntime)
    monkeypatch.setattr(
        runtime,
        "_query_reset_regions",
        lambda fieldids: [
            {
                "query_region_fieldid": "backgroundQuery",
                "root_selector": '[data-ydf-query-reset-region="background"]',
                "in_foreground": False,
            },
            {
                "query_region_fieldid": "foregroundQuery",
                "root_selector": '[data-ydf-query-reset-region="foreground"]',
                "in_foreground": True,
            },
        ],
        raising=False,
    )
    monkeypatch.setattr(runtime, "_has_visible_foreground_layer", lambda: True, raising=False)
    candidate_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        runtime,
        "_query_reset_candidates",
        lambda region, source: candidate_calls.append((region["query_region_fieldid"], source))
        or (
            [
                {
                    "selector": '[data-ydf-query-reset-candidate="foreground"]',
                    "locator_source": "reset_btn",
                }
            ]
            if source == "reset_btn"
            else []
        ),
        raising=False,
    )
    clicked: list[BoundElement] = []
    monkeypatch.setattr(runtime, "click", clicked.append)
    monkeypatch.setattr(runtime, "_wait_ready", lambda: None)

    result = runtime.click_query_reset(["backgroundQuery", "foregroundQuery"])

    assert result == {
        "query_region_fieldid": "foregroundQuery",
        "button": "重置",
        "locator_source": "reset_btn",
    }
    assert clicked[0].runtime.selector == '[data-ydf-query-reset-candidate="foreground"]'
    assert candidate_calls == [("foregroundQuery", "reset_btn")]


def test_playwright_runtime_query_reset_rejects_ambiguous_foreground_regions(monkeypatch) -> None:
    runtime = PlaywrightRuntime.__new__(PlaywrightRuntime)
    monkeypatch.setattr(
        runtime,
        "_query_reset_regions",
        lambda fieldids: [
            {
                "query_region_fieldid": fieldid,
                "root_selector": f'[data-ydf-query-reset-region="{fieldid}"]',
                "in_foreground": True,
            }
            for fieldid in fieldids
        ],
        raising=False,
    )
    monkeypatch.setattr(runtime, "_has_visible_foreground_layer", lambda: True, raising=False)
    monkeypatch.setattr(
        runtime,
        "_query_reset_candidates",
        lambda *args: pytest.fail("查询区歧义必须在按钮扫描前失败"),
        raising=False,
    )

    with pytest.raises(RuntimeError, match="查询区匹配不唯一"):
        runtime.click_query_reset(["queryA", "queryB"])


def test_playwright_runtime_query_reset_does_not_open_more_when_button_is_missing(monkeypatch) -> None:
    runtime = PlaywrightRuntime.__new__(PlaywrightRuntime)
    region = {
        "query_region_fieldid": "dataQueryArea",
        "root_selector": '[data-ydf-query-reset-region="query"]',
        "in_foreground": False,
    }
    monkeypatch.setattr(runtime, "_query_reset_regions", lambda fieldids: [region], raising=False)
    monkeypatch.setattr(runtime, "_has_visible_foreground_layer", lambda: False, raising=False)
    monkeypatch.setattr(runtime, "_query_reset_candidates", lambda region, source: [], raising=False)
    monkeypatch.setattr(runtime, "_collect_page_diagnostic_text", lambda: "页面含有更多按钮")
    monkeypatch.setattr(runtime, "_save_diagnostic_screenshot", lambda name: None)
    monkeypatch.setattr(
        runtime,
        "_reveal_toolbar_overflow",
        lambda *args, **kwargs: pytest.fail("query.reset 不应展开更多菜单"),
    )

    with pytest.raises(RuntimeError, match="未找到可点击查询重置动作"):
        runtime.click_query_reset(["dataQueryArea"])


def test_playwright_runtime_query_reset_does_not_fall_back_to_background_region(monkeypatch) -> None:
    runtime = PlaywrightRuntime.__new__(PlaywrightRuntime)
    monkeypatch.setattr(
        runtime,
        "_query_reset_regions",
        lambda fieldids: [
            {
                "query_region_fieldid": "backgroundQuery",
                "root_selector": '[data-ydf-query-reset-region="background"]',
                "in_foreground": False,
            }
        ],
        raising=False,
    )
    monkeypatch.setattr(runtime, "_has_visible_foreground_layer", lambda: True, raising=False)
    monkeypatch.setattr(
        runtime,
        "_query_reset_candidates",
        lambda *args: pytest.fail("存在前景层时不得扫描背景查询区按钮"),
        raising=False,
    )
    monkeypatch.setattr(runtime, "_collect_page_diagnostic_text", lambda: "存在前景弹窗")
    monkeypatch.setattr(runtime, "_save_diagnostic_screenshot", lambda name: None)

    with pytest.raises(RuntimeError, match="未找到前景可见查询区"):
        runtime.click_query_reset(["backgroundQuery"])


def test_playwright_runtime_query_reset_prefers_reset_identity_before_text(monkeypatch) -> None:
    runtime = PlaywrightRuntime.__new__(PlaywrightRuntime)
    region = {
        "query_region_fieldid": "dataQueryArea",
        "root_selector": '[data-ydf-query-reset-region="query"]',
        "in_foreground": False,
    }
    monkeypatch.setattr(runtime, "_query_reset_regions", lambda fieldids: [region], raising=False)
    monkeypatch.setattr(runtime, "_has_visible_foreground_layer", lambda: False, raising=False)
    calls: list[str] = []
    monkeypatch.setattr(
        runtime,
        "_query_reset_candidates",
        lambda selected, source: calls.append(source)
        or (
            [{"selector": '[data-reset="identity"]', "locator_source": "reset_btn"}]
            if source == "reset_btn"
            else [{"selector": '[data-reset="text"]', "locator_source": "exact_text"}]
        ),
        raising=False,
    )
    clicked: list[BoundElement] = []
    monkeypatch.setattr(runtime, "click", clicked.append)
    monkeypatch.setattr(runtime, "_wait_ready", lambda: None)

    result = runtime.click_query_reset(["dataQueryArea"])

    assert calls == ["reset_btn"]
    assert result["locator_source"] == "reset_btn"
    assert clicked[0].runtime.selector == '[data-reset="identity"]'


def test_playwright_runtime_query_reset_regions_find_drag_root_across_frames() -> None:
    class Root:
        def __init__(self, foreground: bool, canonical_token: str) -> None:
            self.foreground = foreground
            self.canonical_token = canonical_token

        def is_visible(self, timeout: int) -> bool:
            return True

        def evaluate(self, script: str, marker: str | None = None):
            if marker is not None:
                return {"token": self.canonical_token, "inForeground": self.foreground}
            return self.foreground

    class Locator:
        def __init__(self, items: list[Root]) -> None:
            self.items = items

        def count(self) -> int:
            return len(self.items)

        def nth(self, index: int) -> Root:
            return self.items[index]

    class Frame:
        def __init__(self, roots: dict[str, list[Root]]) -> None:
            self.roots = roots

        def locator(self, selector: str) -> Locator:
            return Locator(self.roots.get(selector, []))

    fieldid = "dataQueryArea"
    main = Frame({})
    child = Frame(
        {
            f'[fieldid="{fieldid}"]': [Root(foreground=True, canonical_token="logical-one")],
            f'[fieldid="{fieldid}_drag"]': [Root(foreground=True, canonical_token="logical-one")],
        }
    )
    runtime = PlaywrightRuntime.__new__(PlaywrightRuntime)
    runtime._page = SimpleNamespace(frames=[main, child])

    regions = runtime._query_reset_regions([fieldid])

    assert len(regions) == 1
    assert regions[0]["query_region_fieldid"] == fieldid
    assert regions[0]["frame_index"] == 1
    assert regions[0]["in_foreground"] is True
    assert regions[0]["root_source"] == f'[fieldid="{fieldid}_drag"]'
    assert regions[0]["root_selector"].startswith('[data-ydf-query-reset-region="')

    reused = Frame(
        {
            f'[fieldid="{fieldid}_drag"]': [
                Root(foreground=False, canonical_token="background"),
                Root(foreground=True, canonical_token="foreground"),
            ]
        }
    )
    runtime._page = SimpleNamespace(frames=[reused])
    reused_regions = runtime._query_reset_regions([fieldid])
    assert len(reused_regions) == 2
    assert {region["in_foreground"] for region in reused_regions} == {False, True}

    ambiguous = Frame(
        {
            f'[fieldid="{fieldid}_drag"]': [
                Root(foreground=True, canonical_token="foreground-a"),
                Root(foreground=True, canonical_token="foreground-b"),
            ]
        }
    )
    runtime._page = SimpleNamespace(frames=[ambiguous])
    ambiguous_regions = runtime._query_reset_regions([fieldid])
    assert len(ambiguous_regions) == 2
    assert all(region["in_foreground"] for region in ambiguous_regions)


def test_playwright_runtime_query_reset_candidates_scan_only_selected_root_and_deduplicate(monkeypatch) -> None:
    class Button:
        def __init__(self, text: str) -> None:
            self.text = text
            self.marker: str | None = None

        def is_visible(self, timeout: int) -> bool:
            return True

        def inner_text(self, timeout: int) -> str:
            return self.text

        def evaluate(self, script: str, marker: str) -> str:
            self.marker = self.marker or marker
            return self.marker

    class Locator:
        def __init__(self, items: list[Button]) -> None:
            self.items = items

        def count(self) -> int:
            return len(self.items)

        def nth(self, index: int) -> Button:
            return self.items[index]

    exact = Button("重置")
    batch = Button("批量重置")

    class Root:
        def locator(self, selector: str) -> Locator:
            if selector in {'button:text-is("重置")', 'button:has-text("重置")'}:
                return Locator([exact, batch])
            return Locator([])

    class Frame:
        def locator(self, selector: str) -> Root:
            assert selector == '[data-ydf-query-reset-region="selected"]'
            return Root()

    runtime = PlaywrightRuntime.__new__(PlaywrightRuntime)
    monkeypatch.setattr(runtime, "_is_clickable_action_target", lambda locator: True)
    region = {
        "context": Frame(),
        "root_selector": '[data-ydf-query-reset-region="selected"]',
        "query_region_fieldid": "dataQueryArea",
    }

    candidates = runtime._query_reset_candidates(region, "exact_text")

    assert len(candidates) == 1
    assert candidates[0]["locator_source"] == "exact_text"
    assert candidates[0]["selector"].startswith('[data-ydf-query-reset-candidate="')


def test_playwright_runtime_query_reset_requires_exact_visible_text_for_text_fallback() -> None:
    runtime = PlaywrightRuntime.__new__(PlaywrightRuntime)

    class Locator:
        def __init__(self, text: str) -> None:
            self.text = text

        def inner_text(self, timeout: int) -> str:
            return self.text

    assert runtime._is_exact_query_reset_target(Locator("批量重置"), "exact_text") is False
    assert runtime._is_exact_query_reset_target(Locator("  重置\n"), "exact_text") is True
    assert runtime._is_exact_query_reset_target(Locator(""), "reset_btn") is True


def test_playwright_runtime_candidate_selectors_include_rule_based_fieldids() -> None:
    runtime = PlaywrightRuntime.__new__(PlaywrightRuntime)
    candidate = ElementCandidate(
        key="depart",
        fieldid="depart",
        label="部门",
        title="",
        region_key="baseForm",
        region_fieldid="baseForm",
        element_type="formItem",
        component_name="YDFTreeModalSelect",
        data_field="depart",
        runtime_fieldids=["baseForm_depart_input", "baseForm_depart_btn"],
    )

    selectors = runtime._candidate_selectors(candidate.fieldid, candidate.label, candidate.runtime_fieldids)

    assert selectors[:6] == [
        '[fieldid="baseForm_depart_input"]',
        '[data-fieldid="baseForm_depart_input"]',
        '#baseForm_depart_input',
        '[fieldid="baseForm_depart_btn"]',
        '[data-fieldid="baseForm_depart_btn"]',
        '#baseForm_depart_btn',
    ]



def test_build_dialog_button_selectors_scope_to_visible_dialog() -> None:
    selectors = build_dialog_button_selectors("确定")

    assert selectors[0] == '.ant-modal:visible button:text-is("确定")'
    assert any(".wui-modal" in item for item in selectors)
    assert any(".u-modal" in item for item in selectors)


def test_build_transfer_dialog_selectors_cover_visible_modal_transfer_controls() -> None:
    assert build_transfer_dialog_dialog_selectors()[0] == ".ant-modal:visible"
    assert ".wui-modal:visible" in build_transfer_dialog_dialog_selectors()
    assert ".yy-modal:visible" in build_transfer_dialog_dialog_selectors()
    assert any("right" in item.lower() for item in build_transfer_dialog_move_to_target_selectors())
    assert 'button:text-is("确定")' in build_transfer_dialog_confirm_selectors("确定")


def test_playwright_runtime_select_transfer_dialog_uses_structured_targets() -> None:
    runtime = _build_runtime()

    class _TransferPage:
        def __init__(self) -> None:
            self.args = None
            self.waits: list[int] = []

        def evaluate(self, script: str, args: dict) -> dict:
            assert "transfer" in script.lower()
            self.args = args
            return {"selected": args["items"], "moved": len(args["items"])}

        def wait_for_timeout(self, timeout: int) -> None:
            self.waits.append(timeout)

    page = _TransferPage()
    runtime._page = page

    result = runtime.select_transfer_dialog(
        title="设置支付任务类型",
        items=[{"match": {"column": "支付任务类型名称", "equals": "工资统发"}}],
        move="to_right",
        confirm=True,
    )

    assert result == {
        "selected": [{"match": {"column": "支付任务类型名称", "equals": "工资统发"}}],
        "moved": 1,
    }
    assert page.args == {
        "title": "设置支付任务类型",
        "items": [{"match": {"column": "支付任务类型名称", "equals": "工资统发"}}],
        "move": "to_right",
        "confirm": True,
        "selectors": {
            "dialogs": build_transfer_dialog_dialog_selectors(),
            "move_to_target": build_transfer_dialog_move_to_target_selectors(),
            "confirm": build_transfer_dialog_confirm_selectors("确定"),
        },
    }
    assert page.waits == [500]


def test_playwright_runtime_upload_attachments_waits_for_component_accepted_state(tmp_path) -> None:
    upload_file = tmp_path / "workpaper.pdf"
    upload_file.write_text("fake pdf", encoding="utf-8")
    runtime = _build_runtime()
    page = _FakeAttachmentPage(
        filename=upload_file.name,
        states=[
            {
                "completed": False,
                "signal": "",
                "text": upload_file.name,
                "root_selector": '[fieldid="fjxx"]',
            },
            {
                "completed": True,
                "signal": "file-row",
                "text": upload_file.name,
                "root_selector": '[fieldid="fjxx"]',
            },
        ],
    )
    runtime._page = page

    result = runtime.upload_attachments([{"type": "底稿附件", "file": str(upload_file)}])

    assert page.input.files == [str(upload_file)]
    assert page.waits == [500]
    attachment_result = result["attachments"][0]
    assert attachment_result["type"] == "底稿附件"
    assert attachment_result["file"] == str(upload_file)
    assert attachment_result["status"] == "success"
    assert attachment_result["target_label"] == "底稿附件"
    assert attachment_result["target_fieldid"] == "fjxx"
    assert attachment_result["completion_signal"] == "file-row"
    assert "wait_duration_ms" in attachment_result


def test_playwright_runtime_upload_attachments_switches_table_view_once_and_restores(tmp_path, monkeypatch) -> None:
    upload_files = [tmp_path / "first.pdf", tmp_path / "second.pdf"]
    for upload_file in upload_files:
        upload_file.write_text("fake pdf", encoding="utf-8")
    runtime = _build_runtime()
    page = _FakeAttachmentPage(filename=upload_files[-1].name)
    runtime._page = page
    current_view = "table"
    switches: list[str] = []

    monkeypatch.setattr(runtime, "_read_attachment_view", lambda _candidates: current_view, raising=False)

    def switch_view(target_view: str, _candidates) -> None:
        nonlocal current_view
        switches.append(target_view)
        current_view = target_view

    monkeypatch.setattr(runtime, "_switch_attachment_view", switch_view, raising=False)

    result = runtime.upload_attachments(
        [{"type": "底稿附件", "file": str(upload_file)} for upload_file in upload_files]
    )

    assert page.input.files == [str(upload_file) for upload_file in upload_files]
    assert switches == ["card", "table"]
    assert result["initial_view"] == "table"
    assert result["upload_view"] == "card"
    assert result["view_restored"] is True


def test_playwright_runtime_upload_attachments_keeps_card_view(tmp_path, monkeypatch) -> None:
    upload_file = tmp_path / "workpaper.pdf"
    upload_file.write_text("fake pdf", encoding="utf-8")
    runtime = _build_runtime()
    page = _FakeAttachmentPage(filename=upload_file.name)
    runtime._page = page
    switches: list[str] = []

    monkeypatch.setattr(runtime, "_read_attachment_view", lambda _candidates: "card", raising=False)
    monkeypatch.setattr(runtime, "_switch_attachment_view", lambda view, _candidates: switches.append(view), raising=False)

    result = runtime.upload_attachments([{"type": "底稿附件", "file": str(upload_file)}])

    assert switches == []
    assert result["initial_view"] == "card"
    assert result["upload_view"] == "card"
    assert result["view_restored"] is True


def test_playwright_runtime_upload_attachments_preserves_upload_error_when_restore_fails(tmp_path, monkeypatch) -> None:
    upload_file = tmp_path / "workpaper.pdf"
    upload_file.write_text("fake pdf", encoding="utf-8")
    runtime = _build_runtime()
    runtime._page = _FakeAttachmentPage(filename=upload_file.name)
    current_view = "table"

    monkeypatch.setattr(runtime, "_read_attachment_view", lambda _candidates: current_view, raising=False)

    def switch_view(target_view: str, _candidates) -> None:
        nonlocal current_view
        if target_view == "table":
            raise RuntimeError("恢复按钮不可用")
        current_view = target_view

    monkeypatch.setattr(runtime, "_switch_attachment_view", switch_view, raising=False)
    monkeypatch.setattr(
        runtime,
        "_wait_for_attachment_upload",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("上传业务失败")),
    )

    with pytest.raises(RuntimeError, match="上传业务失败.*恢复附件表格视图失败.*恢复按钮不可用"):
        runtime.upload_attachments([{"type": "底稿附件", "file": str(upload_file)}])


def test_playwright_runtime_upload_attachments_reports_successful_upload_when_restore_fails(tmp_path, monkeypatch) -> None:
    upload_file = tmp_path / "workpaper.pdf"
    upload_file.write_text("fake pdf", encoding="utf-8")
    runtime = _build_runtime()
    runtime._page = _FakeAttachmentPage(filename=upload_file.name)

    monkeypatch.setattr(runtime, "_read_attachment_view", lambda _candidates: "table", raising=False)

    def switch_view(target_view: str, _candidates) -> None:
        if target_view == "table":
            raise RuntimeError("恢复按钮不可用")

    monkeypatch.setattr(runtime, "_switch_attachment_view", switch_view, raising=False)

    with pytest.raises(RuntimeError, match="附件已上传.*workpaper.pdf.*恢复附件表格视图失败"):
        runtime.upload_attachments([{"type": "底稿附件", "file": str(upload_file)}])


def test_playwright_runtime_upload_attachments_rejects_disallowed_file_type(tmp_path) -> None:
    upload_file = tmp_path / "workpaper.xlsx"
    upload_file.write_text("not allowed", encoding="utf-8")
    runtime = _build_runtime()
    page = _FakeAttachmentPage(filename=upload_file.name)
    runtime._page = page

    with pytest.raises(RuntimeError, match="文件类型不匹配"):
        runtime.upload_attachments(
            [{"type": "底稿附件", "file": str(upload_file)}],
            attachment_candidates=[
                {
                    "label": "底稿附件",
                    "fieldid": "fjxx",
                    "raw": {"props": {"enableFileType": "pdf,doc,docx"}},
                }
            ],
        )

    assert page.input.files == []


def test_build_query_expand_selectors_cover_wui_query_collapse_button() -> None:
    selectors = build_query_expand_selectors()

    assert selectors[0] == "button.query-collapse-icon:has(.icon-xiangxia)"
    assert "button.wui-button.query-collapse-icon.wui-button-icon-only" in selectors


def test_playwright_runtime_click_prefers_visible_match() -> None:
    runtime = _build_runtime()
    hidden = _FakeMatch(visible=False)
    visible = _FakeMatch(visible=True)

    class _Page:
        def locator(self, selector: str) -> _FakeLocatorGroup:
            assert selector == '[fieldid="xq_btn"]'
            return _FakeLocatorGroup([hidden, visible])

        def wait_for_timeout(self, *_args, **_kwargs) -> None:
            return

    runtime._page = _Page()

    class _Bound:
        class _Runtime:
            selector = '[fieldid="xq_btn"]'

        runtime = _Runtime()

    runtime.click(_Bound())

    assert hidden.clicked is False
    assert visible.clicked is True


@pytest.mark.parametrize("typing_fails", [False, True])
def test_playwright_runtime_sets_plain_form_field_value_exactly(typing_fails) -> None:
    runtime = _build_runtime()
    calls: list[tuple[str, object]] = []

    class _FillLocator:
        def click(self, timeout: int = 0) -> None:
            calls.append(("click", timeout))

        def press(self, key: str, timeout: int = 0) -> None:
            calls.append(("press", key))

        def type(self, value: str, delay: int = 0) -> None:
            calls.append(("type", value))
            if typing_fails:
                raise RuntimeError("keyboard entry failed")

        def fill(self, value: str) -> None:
            calls.append(("fill", value))

        def evaluate(self, script: str, value: str) -> None:
            calls.append(("evaluate", value))

    runtime._set_text_field_value(_FillLocator(), "new value")

    expected_calls = [
        ("click", 1000),
        ("press", "Meta+A"),
        ("press", "Control+A"),
        ("press", "Backspace"),
        ("type", "new value"),
        ("evaluate", "new value"),
        ("press", "Tab"),
    ]
    if typing_fails:
        expected_calls.insert(5, ("fill", "new value"))
    assert calls == expected_calls


def test_playwright_runtime_prepare_binding_does_not_expand_query_conditions(monkeypatch) -> None:
    runtime = _build_runtime()
    calls: list[list[str]] = []
    runtime._page = _FakePage()

    monkeypatch.setattr(runtime, "_try_click_first", lambda selectors: calls.append(selectors) or True)

    runtime.prepare_binding(SimpleNamespace(query_fields=[object()]))

    assert calls == []


def test_playwright_runtime_expand_query_conditions_clicks_collapse_button(monkeypatch) -> None:
    runtime = _build_runtime()
    calls: list[list[str]] = []
    runtime._page = _FakePage()

    monkeypatch.setattr(runtime, "_try_click_first", lambda selectors: calls.append(selectors) or True)

    assert runtime.expand_query_conditions() is True
    assert calls == [build_query_expand_selectors()]


def test_runtime_query_expand_selectors_are_loaded_from_render_adapter_registry(monkeypatch) -> None:
    class Registry:
        def selectors(self, name: str, *args, **kwargs) -> list[str]:
            assert name == "query.expand"
            return ["button.custom-query-expand"]

    monkeypatch.setattr(runtime_module, "RENDER_ADAPTERS", Registry(), raising=False)

    assert build_query_expand_selectors() == ["button.custom-query-expand"]


def test_playwright_runtime_fill_query_field_expands_tree_choice_when_value_is_hidden(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _ChoiceRoot:
        def click(self, timeout: int = 0) -> None:
            calls.append("open")

    class _ChoiceInput:
        def fill(self, value: str, timeout: int = 0) -> None:
            calls.append(f"fill:{value}")

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: _ChoiceRoot())
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: _ChoiceInput())
    monkeypatch.setattr(runtime, "_looks_like_choice_field", lambda root, bound: True)

    attempts = {"count": 0}

    def _try_click_choice(value: str) -> bool:
        attempts["count"] += 1
        calls.append(f"choose:{value}:{attempts['count']}")
        return attempts["count"] == 2

    monkeypatch.setattr(runtime, "_try_click_query_choice", _try_click_choice)
    monkeypatch.setattr(runtime, "_expand_query_choice_tree_until_visible", lambda value: calls.append(f"expand:{value}"))
    monkeypatch.setattr(runtime, "_wait_for_query_choice_dropdown_to_settle", lambda: calls.append("settle"))

    bound = SimpleNamespace(runtime=SimpleNamespace(selector='[fieldid="query_apply_dept"]'))

    runtime.fill_query_field(bound, "001 办公室")

    assert calls == [
        "open",
        "fill:001 办公室",
        "choose:001 办公室:1",
        "choose:001 办公室:2",
        "settle",
    ]


def test_playwright_runtime_fill_query_field_uses_popup_reference_for_modal_select(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    root = object()
    fill_locator = object()

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: root)
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: fill_locator)
    monkeypatch.setattr(runtime, "_looks_like_choice_field", lambda current_root, bound: True)
    _patch_popup_reference_select(monkeypatch, runtime, lambda current_root, locator, value: calls.append(
            f"popup:{value}:{current_root is root}:{locator is fill_locator}"
        ))
    monkeypatch.setattr(
        runtime,
        "_select_query_choice",
        lambda current_root, locator, value: (_ for _ in ()).throw(
            AssertionError("modal query field should not use dropdown choice")
        ),
    )

    bound = SimpleNamespace(
        candidate=SimpleNamespace(component_name="YDFTreeModalSelect", raw={"dataType": "refer"}),
        runtime=SimpleNamespace(
            selector='[fieldid="query_proCatalogCode"]',
            role="textbox",
            tag_name="input",
            name="YDFTreeModalSelect",
        ),
    )

    runtime.fill_query_field(bound, "101 财政一级")

    assert calls == ["popup:101 财政一级:True:True"]


def test_playwright_runtime_fill_query_field_keeps_plain_tree_select_as_choice(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    root = object()
    fill_locator = object()

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: root)
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: fill_locator)
    monkeypatch.setattr(runtime, "_looks_like_choice_field", lambda current_root, bound: True)
    _patch_popup_reference_select(monkeypatch, runtime, lambda current_root, locator, value: (_ for _ in ()).throw(
            AssertionError("plain tree select query field should not use popup reference")
        ))

    monkeypatch.setattr(
        runtime,
        "_select_query_choice",
        lambda current_root, locator, value: calls.append(
            f"choice:{value}:{current_root is root}:{locator is fill_locator}"
        ),
    )

    bound = SimpleNamespace(
        candidate=SimpleNamespace(component_name="YDFTreeSelect", raw={}),
        runtime=SimpleNamespace(
            selector='[fieldid="query_internalDepCode"]',
            role="combobox",
            tag_name="input",
            name="YDFTreeSelect",
        ),
    )

    runtime.fill_query_field(bound, "001 办公室")

    assert calls == ["choice:001 办公室:True:True"]


def test_playwright_runtime_fill_query_field_keeps_lcd_enum_as_choice(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    root = object()
    fill_locator = object()

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: root)
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: fill_locator)
    monkeypatch.setattr(runtime._popup_reference_module(), "root_has_trigger", lambda current_root: True)
    _patch_popup_reference_select(monkeypatch, runtime, lambda current_root, locator, value: (_ for _ in ()).throw(
            AssertionError("LCDEnum query field should not use popup reference")
        ))

    def _select_query_choice(current_root, locator, value, **kwargs):
        calls.append(
            f"choice:{value}:{current_root is root}:{locator is fill_locator}:"
            f"active={kwargs.get('root_already_active')}:require={kwargs.get('require_value_match')}"
        )

    monkeypatch.setattr(runtime, "_select_query_choice", _select_query_choice)

    bound = SimpleNamespace(
        candidate=SimpleNamespace(component_name="LCDEnum", raw={"enumType": "ammStockOutBillTypeEnums"}),
        runtime=SimpleNamespace(
            selector='[fieldid="query_outStoreTypeCode"]',
            role=None,
            tag_name="div",
            name="LCDEnum",
        ),
    )

    runtime.fill_query_field(bound, "调拨")

    assert calls == ["choice:调拨:True:True:active=True:require=True"]


def test_playwright_runtime_rejects_scalar_for_table_modal_query_field(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: object())
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: object())
    _patch_popup_reference_select(monkeypatch, runtime, lambda root, fill, value: calls.append(f"popup:{value}"))

    bound = SimpleNamespace(
        candidate=SimpleNamespace(component_name="YDFTableModalSelect", raw={"dataType": "refer"}, label="项目代码"),
        runtime=SimpleNamespace(
            selector='[fieldid="query_projectCode"]',
            role="textbox",
            tag_name="input",
            name="YDFTableModalSelect",
        ),
    )

    with pytest.raises(RuntimeError, match="表格参照.*match"):
        runtime.fill_query_field(bound, "360000241010010000013")

    assert calls == []


def test_playwright_runtime_allows_row_number_for_table_modal_query_field(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []
    target = {"row_number": 1}

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: object())
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: object())
    _patch_popup_reference_select(monkeypatch, runtime, lambda root, fill, value: calls.append(f"popup:{value}"))

    bound = SimpleNamespace(
        candidate=SimpleNamespace(component_name="YDFTableModalSelect", raw={"dataType": "refer"}, label="项目代码"),
        runtime=SimpleNamespace(
            selector='[fieldid="query_projectCode"]',
            role="textbox",
            tag_name="input",
            name="YDFTableModalSelect",
        ),
    )

    runtime.fill_query_field(bound, target)

    assert calls == [f"popup:{target}"]


def test_playwright_runtime_fill_form_field_uses_choice_popup_for_refer(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _ChoiceRoot:
        def click(self, timeout: int = 0) -> None:
            calls.append("open")

    class _ChoiceInput:
        def fill(self, value: str, timeout: int = 0) -> None:
            calls.append(f"fill:{value}")

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: _ChoiceRoot())
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: _ChoiceInput())
    monkeypatch.setattr(runtime, "_looks_like_choice_field", lambda root, bound: True)
    monkeypatch.setattr(runtime, "_try_click_query_choice", lambda value: calls.append(f"choose:{value}") or True)
    monkeypatch.setattr(runtime, "_wait_for_query_choice_dropdown_to_settle", lambda: calls.append("settle"))
    monkeypatch.setattr(
        runtime,
        "_query_choice_selection_settled",
        lambda root, value, **kwargs: calls.append(f"confirmed:{kwargs.get('require_value_match')}") or True,
    )

    bound = SimpleNamespace(runtime=SimpleNamespace(selector='[fieldid="proManager"]'))

    runtime.fill_form_field(bound, "吕晓雷")

    assert calls == ["open", "fill:吕晓雷", "choose:吕晓雷", "confirmed:True"]


def test_playwright_runtime_fill_form_field_uses_popup_reference_for_ref_component(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _ReferenceRoot:
        def evaluate(self, _script: str) -> str:
            return ""

        def locator(self, _selector: str):
            raise AssertionError("component-name detection should not need DOM probing")

    class _ReferenceInput:
        pass

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: _ReferenceRoot())
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: _ReferenceInput())
    _patch_popup_reference_select(monkeypatch, runtime, lambda root, fill, value: calls.append(f"popup:{value}"))
    monkeypatch.setattr(runtime, "_select_query_choice", lambda root, fill, value, **kwargs: calls.append(f"choice:{value}"))
    monkeypatch.setattr(runtime, "_set_text_field_value", lambda locator, value: calls.append(f"text:{value}"))

    bound = SimpleNamespace(
        candidate=SimpleNamespace(component_name="YDFRefTree", raw={}),
        runtime=SimpleNamespace(
            selector='[fieldid="govPurchaseItem"]',
            role="textbox",
            tag_name="input",
            name="YDFRefTree",
        ),
    )

    runtime.fill_form_field(bound, "C99000000 其他服务")

    assert calls == ["popup:C99000000 其他服务"]


def test_playwright_runtime_fill_form_field_uses_popup_reference_for_modal_select_component(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _ReferenceRoot:
        def evaluate(self, _script: str, *_args) -> str:
            return ""

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: _ReferenceRoot())
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: object())
    _patch_popup_reference_select(monkeypatch, runtime, lambda root, fill, value: calls.append(f"popup:{value}"))
    monkeypatch.setattr(runtime, "_select_query_choice", lambda root, fill, value, **_kwargs: calls.append(f"choice:{value}"))

    bound = SimpleNamespace(
        candidate=SimpleNamespace(component_name="YDFTableModalSelect", raw={}),
        runtime=SimpleNamespace(
            selector='[fieldid="assetCode"]',
            role="textbox",
            tag_name="input",
            name="YDFTableModalSelect",
        ),
    )

    runtime.fill_form_field(bound, {"match": {"column": "代码集名称", "equals": "房屋"}})

    assert calls == ["popup:{'match': {'column': '代码集名称', 'equals': '房屋'}}"]


def test_playwright_runtime_fill_form_field_uses_popup_reference_for_refuri_ydf_select(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    root = object()
    fill_locator = object()

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: root)
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: fill_locator)
    monkeypatch.setattr(runtime, "_resolve_foreground_form_field_root", lambda bound: None)
    monkeypatch.setattr(runtime, "_resolve_form_field_root_by_label_position", lambda bound: None)
    monkeypatch.setattr(runtime, "_narrow_form_field_root", lambda current_root, bound: current_root)
    monkeypatch.setattr(runtime, "_looks_like_switch_field", lambda current_root, bound: False)
    monkeypatch.setattr(runtime, "_looks_like_radio_field", lambda current_root, bound: False)
    _patch_popup_reference_select(monkeypatch, runtime, lambda current_root, locator, value: calls.append(f"popup:{value}:{current_root is root}:{locator is fill_locator}"))
    monkeypatch.setattr(runtime, "_select_query_choice", lambda current_root, locator, value, **_kwargs: calls.append(f"choice:{value}"))

    bound = SimpleNamespace(
        candidate=SimpleNamespace(
            component_name="YDFSelect",
            raw={
                "dataType": "refer",
                "refuri": "fbdi.RefTable_9978ddcc55",
                "enty": {"info": {"refCode": "fbdi.RefTable_9978ddcc55"}},
            },
        ),
        runtime=SimpleNamespace(
            selector='[fieldid="setModeCode"]',
            role=None,
            tag_name="div",
            name="YDFSelect",
        ),
    )

    runtime.fill_form_field(bound, "1 电子转账支付")

    assert calls == ["popup:1 电子转账支付:True:True"]


def test_playwright_runtime_fill_form_field_skips_choice_when_current_value_matches(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    root = object()
    fill_locator = object()

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: root)
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: fill_locator)
    monkeypatch.setattr(runtime, "_resolve_foreground_form_field_root", lambda bound: None)
    monkeypatch.setattr(runtime, "_resolve_form_field_root_by_label_position", lambda bound: None)
    monkeypatch.setattr(runtime, "_narrow_form_field_root", lambda current_root, bound: current_root)
    monkeypatch.setattr(runtime, "_looks_like_switch_field", lambda current_root, bound: False)
    monkeypatch.setattr(runtime, "_looks_like_radio_field", lambda current_root, bound: False)
    monkeypatch.setattr(runtime, "_read_field_value_from_container", lambda bound: "1 电子转账支付")
    _patch_popup_reference_select(monkeypatch, runtime, lambda current_root, locator, value: calls.append(f"popup:{value}"))
    monkeypatch.setattr(runtime, "_select_query_choice", lambda current_root, locator, value, **_kwargs: calls.append(f"choice:{value}"))

    bound = SimpleNamespace(
        candidate=SimpleNamespace(
            component_name="YDFSelect",
            raw={"dataType": "refer", "refuri": "fbdi.RefTable_9978ddcc55"},
        ),
        runtime=SimpleNamespace(
            selector='[fieldid="setModeCode"]',
            role=None,
            tag_name="div",
            name="YDFSelect",
        ),
    )

    result = runtime.fill_form_field(bound, "1 电子转账支付")

    assert calls == []
    assert result == {"actual": "1 电子转账支付", "confirmed": True, "skipped": True}


def test_playwright_runtime_fill_form_field_reads_current_value_by_candidate_identity(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _WrongRoot:
        def evaluate(self, _script: str, *_args) -> str:
            return "001 管理学院"

    class _TargetRoot:
        def is_visible(self, timeout: int = 0) -> bool:
            return True

        def evaluate(self, _script: str, *_args) -> str:
            return "1 电子转账支付"

    class _Locator:
        first = _TargetRoot()

        def count(self) -> int:
            return 1

        def nth(self, _index: int) -> _TargetRoot:
            return _TargetRoot()

    class _Context:
        def locator(self, selector: str) -> _Locator:
            assert "setModeCode" in selector
            return _Locator()

    fill_locator = object()

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: _WrongRoot())
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: fill_locator)
    monkeypatch.setattr(runtime, "_resolve_foreground_form_field_root", lambda bound: None)
    monkeypatch.setattr(runtime, "_resolve_form_field_root_by_label_position", lambda bound: None)
    monkeypatch.setattr(runtime, "_narrow_form_field_root", lambda current_root, bound: current_root)
    monkeypatch.setattr(runtime, "_looks_like_switch_field", lambda current_root, bound: False)
    monkeypatch.setattr(runtime, "_looks_like_radio_field", lambda current_root, bound: False)
    monkeypatch.setattr(runtime, "_all_search_contexts", lambda: [_Context()])
    _patch_popup_reference_select(monkeypatch, runtime, lambda current_root, locator, value: calls.append(f"popup:{value}"))
    monkeypatch.setattr(runtime, "_select_query_choice", lambda current_root, locator, value, **_kwargs: calls.append(f"choice:{value}"))

    bound = SimpleNamespace(
        candidate=SimpleNamespace(
            fieldid="setModeCode",
            label="结算方式",
            component_name="YDFSelect",
            raw={"dataType": "refer", "refuri": "fbdi.RefTable_9978ddcc55"},
        ),
        runtime=SimpleNamespace(
            selector='[fieldid="internalDepCode_drag"]',
            fieldid="internalDepCode_drag",
            role=None,
            tag_name="div",
            name="单位内设机构",
        ),
    )

    result = runtime.fill_form_field(bound, "1 电子转账支付")

    assert calls == []
    assert result == {"actual": "1 电子转账支付", "confirmed": True, "skipped": True}


def test_playwright_runtime_fill_form_field_keeps_ydf_input_with_reference_enty_as_text(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    root = object()
    fill_locator = object()

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: root)
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: fill_locator)
    monkeypatch.setattr(runtime, "_resolve_foreground_form_field_root", lambda bound: None)
    monkeypatch.setattr(runtime, "_resolve_form_field_root_by_label_position", lambda bound: None)
    monkeypatch.setattr(runtime, "_narrow_form_field_root", lambda current_root, bound: current_root)
    monkeypatch.setattr(runtime, "_looks_like_switch_field", lambda current_root, bound: False)
    monkeypatch.setattr(runtime, "_looks_like_radio_field", lambda current_root, bound: False)
    monkeypatch.setattr(runtime, "_read_field_value_from_candidate_identity", lambda bound, label: "")
    _patch_popup_reference_select(monkeypatch, runtime, lambda current_root, locator, value: calls.append(f"popup:{value}"))
    monkeypatch.setattr(runtime, "_set_text_field_value", lambda locator, value: calls.append(f"text:{value}:{locator is fill_locator}"))
    monkeypatch.setattr(runtime, "_confirm_plain_field_value", lambda locator, value, bound: {"actual": str(value)})

    bound = SimpleNamespace(
        candidate=SimpleNamespace(
            fieldid="payeeAcctNo",
            label="收款人账号",
            component_name="YDFInput",
            raw={
                "dataType": "",
                "enty": {"info": {"refCode": "fbdi.RefTable_9978ddcc55", "refName": "公共代码集-无权限参照-业务使用"}},
            },
        ),
        runtime=SimpleNamespace(
            selector='[fieldid="payeeAcctNo"]',
            role=None,
            tag_name="div",
            name="YDFInput",
        ),
    )

    runtime.fill_form_field(bound, "121212121212")

    assert calls == ["text:121212121212:True"]


def test_playwright_runtime_fill_form_field_uses_popup_for_caninput_modal_reference_scalar(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    root = object()
    fill_locator = object()

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: root)
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: fill_locator)
    monkeypatch.setattr(runtime, "_resolve_foreground_form_field_root", lambda bound: None)
    monkeypatch.setattr(runtime, "_resolve_form_field_root_by_label_position", lambda bound: None)
    monkeypatch.setattr(runtime, "_narrow_form_field_root", lambda current_root, bound: current_root)
    monkeypatch.setattr(runtime, "_looks_like_switch_field", lambda current_root, bound: False)
    monkeypatch.setattr(runtime, "_looks_like_radio_field", lambda current_root, bound: False)
    _patch_popup_reference_select(monkeypatch, runtime, lambda current_root, locator, value: calls.append(
            f"popup:{value}:{current_root is root}:{locator is fill_locator}"
        ))
    monkeypatch.setattr(runtime, "_select_query_choice", lambda current_root, locator, value: calls.append(f"choice:{value}"))
    monkeypatch.setattr(runtime, "_set_text_field_value", lambda locator, value: calls.append(f"text:{value}:{locator is fill_locator}"))

    bound = SimpleNamespace(
        candidate=SimpleNamespace(
            component_name="YDFTreeModalSelect",
            raw={"dataType": "refer", "props": {"caninput": 1}},
        ),
        runtime=SimpleNamespace(
            selector='[fieldid="sqxx_form_bankOutletsCode"]',
            role="textbox",
            tag_name="input",
            name="YDFTreeModalSelect",
        ),
    )

    runtime.fill_form_field(bound, "621700000001")

    assert calls == ["popup:621700000001:True:True"]


@pytest.mark.parametrize(
    "refer_type,caninput,target,reject_on_blur,direct",
    [
        ("uidata", 1, "新支付摘要", False, True),
        ("link", True, "新支付摘要", False, True),
        ("uidata", "1", "新支付摘要", False, True),
        ("uidata", 1, "新支付摘要", True, True),
        ("uidata", 0, "新支付摘要", False, False),
        ("uidata", "0", "新支付摘要", False, False),
        ("tree", 1, "新支付摘要", False, False),
        ("uidata", 1, {"first_available": True}, False, False),
    ],
)
def test_inputable_page_reference_form_fill(
    _popup_reference_page, monkeypatch, refer_type, caninput, target, reject_on_blur, direct
) -> None:
    page = _popup_reference_page
    page.set_content('''
        <div fieldid="payInformationPanel_useDes" class="ydf-select">
          <input fieldid="payInformationPanel_useDes_input_search_input" role="combobox"
            oninput="window.committedValue=this.value"
            onblur="if(window.rejectOnBlur) { this.value=''; window.committedValue=''; }">
          <button fieldid="payInformationPanel_useDes_btn">参照</button>
        </div>
    ''')
    page.evaluate("reject => { window.rejectOnBlur=reject; window.committedValue=''; }", reject_on_blur)
    runtime = _build_runtime()
    runtime._page = page
    root = page.locator('[fieldid="payInformationPanel_useDes"]')
    monkeypatch.setattr(runtime, "_resolve_foreground_form_field_root", lambda bound: root)
    popup_calls = []
    _patch_popup_reference_select(monkeypatch, runtime, lambda *args: popup_calls.append(args))
    bound = SimpleNamespace(
        candidate=SimpleNamespace(
            fieldid="payInformationPanel_useDes", label="支付摘要", component_name="YDFReferSelect",
            raw={"props": {"referType": refer_type, "caninput": caninput}},
        ),
        runtime=SimpleNamespace(
            selector='[fieldid="payInformationPanel_useDes"]', role="combobox",
            tag_name="input", name="YDFReferSelect", in_dialog=False,
        ),
    )
    if direct and reject_on_blur:
        with pytest.raises(RuntimeError, match="字段录入后未回填"):
            runtime.fill_form_field(bound, target)
    else:
        result = runtime.fill_form_field(bound, target)
        if direct:
            assert result["confirmed"] is True
            assert result["actual"] == target
            assert page.evaluate("window.committedValue") == target
            assert root.locator("input").input_value() == target
    assert bool(popup_calls) is not direct


def test_playwright_runtime_fill_form_field_uses_popup_for_caninput_refer_select_structured(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    root = object()
    fill_locator = object()
    target = {"filter": "自动化测试", "row_number": 1}

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: root)
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: fill_locator)
    monkeypatch.setattr(runtime, "_resolve_foreground_form_field_root", lambda bound: None)
    monkeypatch.setattr(runtime, "_resolve_form_field_root_by_label_position", lambda bound: None)
    monkeypatch.setattr(runtime, "_narrow_form_field_root", lambda current_root, bound: current_root)
    monkeypatch.setattr(runtime, "_looks_like_switch_field", lambda current_root, bound: False)
    monkeypatch.setattr(runtime, "_looks_like_radio_field", lambda current_root, bound: False)
    _patch_popup_reference_select(monkeypatch, runtime, lambda current_root, locator, value: calls.append(f"popup:{value}:{current_root is root}:{locator is fill_locator}"))
    monkeypatch.setattr(runtime, "_set_text_field_value", lambda locator, value: calls.append(f"text:{value}"))

    bound = SimpleNamespace(
        candidate=SimpleNamespace(component_name="YDFReferSelect", raw={"props": {"caninput": 1}}),
        runtime=SimpleNamespace(
            selector='[fieldid="useDesSelect"]',
            role="textbox",
            tag_name="input",
            name="YDFReferSelect",
        ),
    )

    runtime.fill_form_field(bound, target)

    assert calls == [f"popup:{target}:True:True"]


def test_playwright_runtime_fill_editable_table_cell_uses_popup_reference_for_modal_column(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _ReferenceCell:
        pass

    class _ReferenceInput:
        pass

    column = SimpleNamespace(component_name="YDFTreeModalSelect", raw={"dataType": "refer"}, label="一级指标", title="")

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: _ReferenceCell())
    monkeypatch.setattr(runtime, "_first_visible_child_locator", lambda root, selectors: _ReferenceInput())
    monkeypatch.setattr(runtime, "_active_editable_locator", lambda: None)
    _patch_popup_reference_select(monkeypatch, runtime, lambda root, fill, value, **_kwargs: calls.append(f"popup:{value}"))
    monkeypatch.setattr(runtime, "_set_text_field_value", lambda locator, value: calls.append(f"text:{value}"))
    monkeypatch.setattr(runtime, "_has_visible_choice_dropdown", lambda: False)

    runtime._fill_active_editable_table_cell(
        '[data-ydf-browser-cell-target="cell"]',
        "101 成本指标",
        column_candidate=column,
    )

    assert calls == ["popup:101 成本指标"]


def test_playwright_runtime_fill_editable_table_cell_marks_structured_popup_origin(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    requests = []

    class _ReferenceCell:
        pass

    class _ReferenceInput:
        pass

    column = SimpleNamespace(
        component_name="YDFReferSelect",
        raw={"dataType": "refer"},
        label="收款方户名",
        title="",
    )
    target = {"filter": "严巴天", "first_available": True}

    def select(request):
        requests.append(request)
        return PopupReferenceResult(
            selected=(target,),
            confirmed=True,
            root_backfilled=True,
            completion="owner_backfilled",
        )

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: _ReferenceCell())
    monkeypatch.setattr(runtime, "_first_visible_child_locator", lambda root, selectors: _ReferenceInput())
    monkeypatch.setattr(runtime, "_active_editable_locator", lambda: None)
    monkeypatch.setattr(runtime._popup_reference_module(), "select", select)
    monkeypatch.setattr(runtime, "_set_text_field_value", lambda locator, value: None)
    monkeypatch.setattr(runtime, "_has_visible_choice_dropdown", lambda: False)

    runtime._fill_active_editable_table_cell(
        '[data-ydf-browser-cell-target="cell"]',
        target,
        column_candidate=column,
    )

    assert len(requests) == 1
    assert requests[0].source.kind == "editable_table"
    assert requests[0].target == target


def test_playwright_runtime_rejects_scalar_for_table_modal_column(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _ReferenceCell:
        pass

    class _ReferenceInput:
        pass

    column = SimpleNamespace(component_name="YDFTableModalSelect", raw={"dataType": "refer"}, label="二级项目代码", title="")

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: _ReferenceCell())
    monkeypatch.setattr(runtime, "_first_visible_child_locator", lambda root, selectors: _ReferenceInput())
    monkeypatch.setattr(runtime, "_active_editable_locator", lambda: None)
    _patch_popup_reference_select(monkeypatch, runtime, lambda root, fill, value, **_kwargs: calls.append(f"popup:{value}"))
    monkeypatch.setattr(runtime, "_has_visible_choice_dropdown", lambda: False)

    with pytest.raises(RuntimeError, match="表格参照.*match"):
        runtime._fill_active_editable_table_cell(
            '[data-ydf-browser-cell-target="cell"]',
            "360000241010010000013",
            column_candidate=column,
        )

    assert calls == []


def test_playwright_runtime_allows_match_for_table_modal_column(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _ReferenceCell:
        pass

    class _ReferenceInput:
        pass

    column = SimpleNamespace(component_name="YDFTableModalSelect", raw={"dataType": "refer"}, label="二级项目代码", title="")
    target = {"match": {"column": "项目代码", "equals": "360000241010010000013"}}

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: _ReferenceCell())
    monkeypatch.setattr(runtime, "_first_visible_child_locator", lambda root, selectors: _ReferenceInput())
    monkeypatch.setattr(runtime, "_active_editable_locator", lambda: None)
    _patch_popup_reference_select(monkeypatch, runtime, lambda root, fill, value, **_kwargs: calls.append(f"popup:{value}"))
    monkeypatch.setattr(runtime, "_set_text_field_value", lambda locator, value: calls.append(f"text:{value}"))
    monkeypatch.setattr(runtime, "_has_visible_choice_dropdown", lambda: False)

    runtime._fill_active_editable_table_cell(
        '[data-ydf-browser-cell-target="cell"]',
        target,
        column_candidate=column,
    )

    assert calls == [f"popup:{target}"]


def test_playwright_runtime_rejects_scalar_for_table_modal_form_field(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    root = object()
    fill_locator = object()
    bound = SimpleNamespace(
        candidate=SimpleNamespace(component_name="YDFTableModalSelect", raw={"dataType": "refer"}, label="资产分类"),
        runtime=SimpleNamespace(
            selector='[fieldid="assetClass"]',
            role="textbox",
            tag_name="input",
            name="YDFTableModalSelect",
        ),
    )

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: root)
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: fill_locator)
    monkeypatch.setattr(runtime, "_resolve_foreground_form_field_root", lambda bound_element: None)
    monkeypatch.setattr(runtime, "_resolve_form_field_root_by_label_position", lambda bound_element: None)
    monkeypatch.setattr(runtime, "_narrow_form_field_root", lambda current_root, bound_element: current_root)
    monkeypatch.setattr(runtime, "_looks_like_switch_field", lambda current_root, bound_element: False)
    monkeypatch.setattr(runtime, "_looks_like_radio_field", lambda current_root, bound_element: False)
    _patch_popup_reference_select(monkeypatch, runtime, lambda current_root, locator, value: calls.append(f"popup:{value}"))

    with pytest.raises(RuntimeError, match="表格参照.*match"):
        runtime.fill_form_field(bound, "房屋")

    assert calls == []


def test_playwright_runtime_visible_choice_dropdown_ignores_generic_ref_popup_class() -> None:
    runtime = _build_runtime()

    class _Page:
        frames: list[object] = []

        def locator(self, selector: str) -> _FakeLocatorGroup:
            if selector in {'[class*="popup"]', '[class*="refer"]', '[class*="ref"]'}:
                return _FakeLocatorGroup([_FakeMatch(True)])
            return _FakeLocatorGroup([])

    runtime._page = _Page()

    assert runtime._has_visible_choice_dropdown() is False


def test_playwright_runtime_fill_editable_table_cell_uses_plain_editor_when_modal_metadata_has_no_trigger(
    monkeypatch,
) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _PlainCell:
        def evaluate(self, _script: str) -> bool:
            return True

    class _PlainInput:
        pass

    column = SimpleNamespace(component_name="YDFTreeModalSelect", raw={"dataType": "refer"}, label="目标指标值", title="")

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: _PlainCell())
    monkeypatch.setattr(runtime, "_first_visible_child_locator", lambda root, selectors: _PlainInput())
    monkeypatch.setattr(runtime, "_active_editable_locator", lambda: None)
    monkeypatch.setattr(runtime._popup_reference_module(), "root_has_trigger", lambda root: False)
    monkeypatch.setattr(runtime, "_read_editable_table_cell_text", lambda cell: "")
    monkeypatch.setattr(runtime, "_wait_for_editable_table_cell_backfill", lambda cell, before_text: "90")
    monkeypatch.setattr(runtime, "_wait_for_editable_table_cell_value", lambda cell, value: "90")
    _patch_popup_reference_select(monkeypatch, runtime, lambda root, fill, value, **_kwargs: calls.append(f"popup:{value}"))
    monkeypatch.setattr(runtime, "_select_query_choice", lambda root, fill, value, **_kwargs: calls.append(f"choice:{value}"))
    monkeypatch.setattr(runtime, "_set_text_field_value", lambda locator, value: calls.append(f"text:{value}"))
    monkeypatch.setattr(runtime, "_has_visible_choice_dropdown", lambda: False)

    runtime._fill_active_editable_table_cell(
        "cell-selector",
        90,
        column_candidate=column,
    )

    assert calls == ["text:90"]


def test_playwright_runtime_fill_form_field_keeps_plain_select_as_choice(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _SelectRoot:
        def evaluate(self, _script: str, *_args) -> bool:
            return True

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: _SelectRoot())
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: object())
    _patch_popup_reference_select(monkeypatch, runtime, lambda root, fill, value: calls.append(f"popup:{value}"))
    monkeypatch.setattr(runtime, "_select_query_choice", lambda root, fill, value, **_kwargs: calls.append(f"choice:{value}"))

    bound = SimpleNamespace(
        candidate=SimpleNamespace(component_name="YDFSelect", raw={}),
        runtime=SimpleNamespace(
            selector='[fieldid="sexCode"]',
            role="combobox",
            tag_name="input",
            name="YDFSelect",
        ),
    )

    runtime.fill_form_field(bound, "男")

    assert calls == ["choice:男"]


def test_playwright_runtime_fill_form_field_keeps_tree_select_as_tree_choice(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _SelectRoot:
        def evaluate(self, _script: str, *_args) -> bool:
            return True

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: _SelectRoot())
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: object())
    _patch_popup_reference_select(monkeypatch, runtime, lambda root, fill, value: (_ for _ in ()).throw(
            AssertionError("plain tree select should not use popup reference")
        ))
    monkeypatch.setattr(
        runtime,
        "_select_query_choice",
        lambda root, fill, value, **_kwargs: calls.append(f"tree-choice:{value}"),
    )

    bound = SimpleNamespace(
        candidate=SimpleNamespace(component_name="YDFTreeSelect", raw={}),
        runtime=SimpleNamespace(
            selector='[fieldid="proCatalogCode_search_input"]',
            role="combobox",
            tag_name="input",
            name="YDFTreeSelect",
        ),
    )

    runtime.fill_form_field(bound, "财政二级项目")

    assert calls == ["tree-choice:财政二级项目"]


def test_playwright_runtime_plain_select_with_reference_metadata_stays_choice(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _SelectRoot:
        def evaluate(self, _script: str, *_args) -> bool:
            return True

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: _SelectRoot())
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: object())
    _patch_popup_reference_select(monkeypatch, runtime, lambda root, fill, value: calls.append(f"popup:{value}"))
    monkeypatch.setattr(runtime, "_select_query_choice", lambda root, fill, value, **_kwargs: calls.append(f"choice:{value}"))

    bound = SimpleNamespace(
        candidate=SimpleNamespace(
            component_name="YDFSelect",
            raw={"dataType": "refer", "enty": {"refCode": "fbdi.RefTable_9978ddcc55", "refName": "公共代码集"}},
        ),
        runtime=SimpleNamespace(
            selector='[fieldid="sexCode"]',
            role=None,
            tag_name="div",
            name="YDFSelect",
        ),
    )

    runtime.fill_form_field(bound, "男")

    assert calls == ["choice:男"]


def test_playwright_runtime_lcd_enum_field_stays_choice_with_arrow_trigger(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _EnumRoot:
        def evaluate(self, _script: str, *_args) -> bool:
            return False

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: _EnumRoot())
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: object())
    monkeypatch.setattr(runtime._popup_reference_module(), "root_has_trigger", lambda root: True)
    _patch_popup_reference_select(monkeypatch, runtime, lambda root, fill, value: (_ for _ in ()).throw(AssertionError("LCDEnum should not use popup reference")))
    monkeypatch.setattr(runtime, "_select_query_choice", lambda root, fill, value, **_kwargs: calls.append(f"choice:{value}"))

    bound = SimpleNamespace(
        candidate=SimpleNamespace(component_name="LCDEnum", raw={"enumType": "ammSourceMode"}),
        runtime=SimpleNamespace(
            selector='[fieldid="sourceModeCode"]',
            role=None,
            tag_name="div",
            name="LCDEnum",
        ),
    )

    runtime.fill_form_field(bound, "采购")

    assert calls == ["choice:采购"]


def test_playwright_runtime_enum_type_metadata_stays_choice(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _EnumRoot:
        def evaluate(self, _script: str, *_args) -> bool:
            return False

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: _EnumRoot())
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: object())
    monkeypatch.setattr(runtime._popup_reference_module(), "root_has_trigger", lambda root: True)
    _patch_popup_reference_select(monkeypatch, runtime, lambda root, fill, value: (_ for _ in ()).throw(AssertionError("enumType field should not use popup reference")))
    monkeypatch.setattr(runtime, "_select_query_choice", lambda root, fill, value, **_kwargs: calls.append(f"choice:{value}"))

    bound = SimpleNamespace(
        candidate=SimpleNamespace(component_name="RuntimeInput", raw={"enumType": "ammSourceMode"}),
        runtime=SimpleNamespace(
            selector='[fieldid="sourceModeCode"]',
            role=None,
            tag_name="div",
            name="RuntimeInput",
        ),
    )

    runtime.fill_form_field(bound, "采购")

    assert calls == ["choice:采购"]


def test_playwright_runtime_tree_modal_select_still_uses_popup_reference(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _ReferenceRoot:
        def evaluate(self, _script: str, *_args) -> bool:
            return False

    root = _ReferenceRoot()
    fill_locator = object()

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: root)
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: fill_locator)
    monkeypatch.setattr(runtime._popup_reference_module(), "root_has_trigger", lambda current_root: True)
    monkeypatch.setattr(runtime, "_select_query_choice", lambda root, fill, value, **_kwargs: calls.append(f"choice:{value}"))
    _patch_popup_reference_select(monkeypatch, runtime, lambda root, fill, value: calls.append(f"popup:{value}"))

    bound = SimpleNamespace(
        candidate=SimpleNamespace(component_name="YDFTreeModalSelect", raw={"enumType": "shouldNotMatter"}),
        runtime=SimpleNamespace(
            selector='[fieldid="agencyCode"]',
            role=None,
            tag_name="div",
            name="YDFTreeModalSelect",
        ),
    )

    runtime.fill_form_field(bound, "001 办公室")

    assert calls == ["popup:001 办公室"]


def test_playwright_runtime_table_modal_select_scalar_still_requires_structured_target(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()

    class _ReferenceRoot:
        def evaluate(self, _script: str, *_args) -> bool:
            return False

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: _ReferenceRoot())
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: object())
    monkeypatch.setattr(runtime._popup_reference_module(), "root_has_trigger", lambda root: True)
    _patch_popup_reference_select(monkeypatch, runtime, lambda root, fill, value: (_ for _ in ()).throw(AssertionError("scalar table modal select should fail before popup")))

    bound = SimpleNamespace(
        candidate=SimpleNamespace(component_name="YDFTableModalSelect", raw={}, label="甲方名称", title=""),
        runtime=SimpleNamespace(
            selector='[fieldid="partyAName"]',
            role=None,
            tag_name="div",
            name="YDFTableModalSelect",
        ),
    )

    with pytest.raises(RuntimeError, match="表格参照字段\\[甲方名称\\]必须使用 match"):
        runtime.fill_form_field(bound, "测试")


def test_playwright_runtime_plain_input_with_reference_metadata_stays_text(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _Root:
        pass

    class _NarrowedRoot:
        pass

    root = _Root()
    narrowed = _NarrowedRoot()
    fill_locator = object()

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: root)
    monkeypatch.setattr(runtime, "_resolve_foreground_form_field_root", lambda bound: None)
    monkeypatch.setattr(runtime, "_resolve_form_field_root_by_label_position", lambda bound: None)
    monkeypatch.setattr(runtime, "_narrow_form_field_root", lambda current_root, bound: narrowed)
    monkeypatch.setattr(runtime, "_resolve_fill_locator_from_root", lambda locator: fill_locator)
    monkeypatch.setattr(runtime._popup_reference_module(), "root_has_trigger", lambda locator: False)
    monkeypatch.setattr(runtime, "_looks_like_switch_field", lambda locator, bound: False)
    monkeypatch.setattr(runtime, "_looks_like_choice_field", lambda locator, bound: False)
    _patch_popup_reference_select(monkeypatch, runtime, lambda root, fill, value: calls.append(f"popup:{value}"))
    monkeypatch.setattr(runtime, "_set_text_field_value", lambda locator, value: calls.append(f"text:{value}:{locator is fill_locator}"))
    monkeypatch.setattr(runtime, "_confirm_plain_field_value", lambda locator, value, bound: {"actual": str(value)})

    bound = SimpleNamespace(
        candidate=SimpleNamespace(
            component_name="YDFInput",
            raw={
                "dataType": "",
                "enty": {
                    "refCode": "yondif-bm.RefTable_4c1c5e7c77",
                    "refName": "第三方机构参照（参照树）",
                },
            },
        ),
        runtime=SimpleNamespace(
            selector='[fieldid="estimateAgencyName"]',
            role=None,
            tag_name="div",
            name="YDFInput",
        ),
    )

    runtime.fill_form_field(bound, "用友网络")

    assert calls == ["text:用友网络:True"]


def test_playwright_runtime_plain_textarea_ignores_reference_trigger(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _Root:
        pass

    class _NarrowedRoot:
        pass

    root = _Root()
    narrowed = _NarrowedRoot()
    fill_locator = object()

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda _selector: root)
    monkeypatch.setattr(runtime, "_resolve_foreground_form_field_root", lambda _bound: None)
    monkeypatch.setattr(runtime, "_resolve_pointer_receiving_form_field_root", lambda _bound: None)
    monkeypatch.setattr(runtime, "_resolve_form_field_root_by_label_position", lambda _bound: None)
    monkeypatch.setattr(runtime, "_narrow_form_field_root", lambda _root, _bound: narrowed)
    monkeypatch.setattr(runtime, "_resolve_fill_locator_from_root", lambda _root: fill_locator)
    monkeypatch.setattr(runtime._popup_reference_module(), "root_has_trigger", lambda _root: True)
    monkeypatch.setattr(runtime, "_looks_like_switch_field", lambda _root, _bound: False)
    monkeypatch.setattr(runtime, "_looks_like_radio_field", lambda _root, _bound: False)
    monkeypatch.setattr(runtime, "_looks_like_choice_field", lambda _root, _bound: False)
    _patch_popup_reference_select(monkeypatch, runtime, lambda _root, _fill, value: calls.append(f"popup:{value}"))
    monkeypatch.setattr(runtime, "_set_text_field_value", lambda locator, value: calls.append(f"text:{value}:{locator is fill_locator}"))
    monkeypatch.setattr(runtime, "_confirm_plain_field_value", lambda _locator, value, _bound: {"actual": str(value)})

    bound = SimpleNamespace(
        candidate=SimpleNamespace(component_name="YDFTextArea", raw={}),
        runtime=SimpleNamespace(selector='[fieldid="remark"]', role=None, tag_name="textarea", name="YDFTextArea"),
    )

    runtime.fill_form_field(bound, "入库备注")

    assert calls == ["text:入库备注:True"]



def test_playwright_runtime_only_text_input_ignores_dropdown_wrapper_class(monkeypatch) -> None:
    runtime = _build_runtime()

    class _Root:
        def evaluate(self, script: str, *_args):
            if "querySelector" in script:
                return {"tag": "input", "role": "textbox", "className": "wui-input"}
            return "wui-dropdown-field"

    bound = SimpleNamespace(
        candidate=SimpleNamespace(component_name="RuntimeInput", raw={"runtime_only": True}),
        runtime=SimpleNamespace(
            selector='[uikey="counterpartName"]',
            role=None,
            tag_name="label",
            name=None,
        ),
    )

    assert runtime._looks_like_choice_field(_Root(), bound) is False




def test_playwright_runtime_only_popup_reference_precedes_choice_branch(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    root = object()
    fill_locator = object()
    calls: list[str] = []
    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda _selector: root)
    monkeypatch.setattr(runtime, "_resolve_runtime_only_form_field_root", lambda _bound: root)
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda _selector: fill_locator)
    monkeypatch.setattr(runtime, "_looks_like_switch_field", lambda *_args: False)
    monkeypatch.setattr(runtime, "_looks_like_radio_field", lambda *_args: False)
    monkeypatch.setattr(runtime, "_looks_like_date_range_field", lambda *_args: False)
    monkeypatch.setattr(runtime, "_looks_like_date_field", lambda *_args: False)
    monkeypatch.setattr(runtime._popup_reference_module(), "looks_like_field", lambda *_args: True)
    monkeypatch.setattr(runtime, "_looks_like_choice_field", lambda *_args: True)
    _patch_popup_reference_select(monkeypatch, runtime, lambda *_args: calls.append("popup"))
    monkeypatch.setattr(
        runtime,
        "_select_choice_for_field",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("popup field used choice branch")),
    )

    bound = SimpleNamespace(
        candidate=SimpleNamespace(component_name="RuntimeSelect", raw={"runtime_only": True}),
        runtime=SimpleNamespace(
            fieldid="ryjbxx_form_idenTypeCode_input_search_input",
            selector='[fieldid="ryjbxx_form_idenTypeCode_input_search_input"]',
            in_dialog=True,
        ),
    )

    runtime.fill_form_field(bound, "身份证")

    assert calls == ["popup"]


def test_playwright_runtime_only_structured_popup_reference_precedes_choice_branch(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    root = object()
    fill_locator = object()
    calls: list[str] = []
    target = {
        "filter": {"conditions": [{"field": "银行网点名称", "equals": "中国工商银行绍兴胜利路支行"}]},
        "match": {"column": "银行网点名称", "equals": "中国工商银行绍兴胜利路支行"},
    }
    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda _selector: root)
    monkeypatch.setattr(runtime, "_resolve_runtime_only_form_field_root", lambda _bound: root)
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda _selector: fill_locator)
    monkeypatch.setattr(runtime, "_looks_like_switch_field", lambda *_args: False)
    monkeypatch.setattr(runtime, "_looks_like_radio_field", lambda *_args: False)
    monkeypatch.setattr(runtime, "_looks_like_date_range_field", lambda *_args: False)
    monkeypatch.setattr(runtime, "_looks_like_date_field", lambda *_args: False)
    monkeypatch.setattr(runtime._popup_reference_module(), "looks_like_field", lambda *_args: True)
    monkeypatch.setattr(runtime, "_looks_like_choice_field", lambda *_args: True)
    _patch_popup_reference_select(monkeypatch, runtime, lambda *_args: calls.append("popup"))
    monkeypatch.setattr(
        runtime,
        "_select_choice_for_field",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("structured popup field used choice branch")),
    )

    bound = SimpleNamespace(
        candidate=SimpleNamespace(component_name="RuntimeInput", raw={"runtime_only": True}),
        runtime=SimpleNamespace(
            fieldid="202312011437208069681134818301",
            selector='[uikey="202312011437208069681134818301"]',
            in_dialog=True,
        ),
    )

    runtime.fill_form_field(bound, target)

    assert calls == ["popup"]


def test_playwright_runtime_only_input_does_not_use_popup_reference_heuristic(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []
    root = object()
    fill_locator = object()

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda _selector: root)
    monkeypatch.setattr(runtime, "_resolve_runtime_only_form_field_root", lambda _bound: root)
    monkeypatch.setattr(
        runtime,
        "_resolve_foreground_form_field_root",
        lambda _bound: (_ for _ in ()).throw(AssertionError("plain runtime-only input waited for popup foreground")),
    )
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda _selector: fill_locator)
    monkeypatch.setattr(runtime, "_looks_like_switch_field", lambda *_args: False)
    monkeypatch.setattr(runtime, "_looks_like_radio_field", lambda *_args: False)
    monkeypatch.setattr(runtime, "_looks_like_date_range_field", lambda *_args: False)
    monkeypatch.setattr(runtime, "_looks_like_date_field", lambda *_args: False)
    monkeypatch.setattr(runtime, "_looks_like_choice_field", lambda *_args: False)
    monkeypatch.setattr(runtime._popup_reference_module(), "looks_like_field", lambda *_args: True)
    _patch_popup_reference_select(monkeypatch, runtime, lambda *_args: (_ for _ in ()).throw(AssertionError("runtime-only text input should not open a reference")))
    monkeypatch.setattr(runtime, "_set_text_field_value", lambda _locator, value: calls.append(f"text:{value}"))
    monkeypatch.setattr(runtime, "_confirm_plain_field_value", lambda *_args: {"confirmed": True})

    bound = SimpleNamespace(
        candidate=SimpleNamespace(component_name="RuntimeInput", raw={"runtime_only": True}),
        runtime=SimpleNamespace(selector='[uikey="counterpartName"]', in_dialog=True),
    )

    runtime.fill_form_field(bound, "单位资金往来对象")

    assert calls == ["text:单位资金往来对象"]


def test_playwright_runtime_only_form_field_prefers_bound_runtime_selector(monkeypatch) -> None:
    runtime = _build_runtime()
    exact_root = object()
    positional_root = object()

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda _selector: exact_root)
    monkeypatch.setattr(runtime, "_resolve_form_field_root_by_label_position", lambda _bound: positional_root)
    monkeypatch.setattr(runtime, "_resolve_foreground_form_field_root", lambda _bound: None)

    bound = SimpleNamespace(
        candidate=SimpleNamespace(raw={"runtime_only": True}),
        runtime=SimpleNamespace(selector='[uikey="counterpartName"]'),
    )

    assert runtime._resolve_runtime_only_form_field_root(bound) is exact_root


def test_playwright_runtime_only_form_field_rejects_non_pointer_candidate(monkeypatch) -> None:
    runtime = _build_runtime()
    background_root = object()
    foreground_root = object()

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda _selector: background_root)
    monkeypatch.setattr(runtime, "_resolve_form_field_root_by_label_position", lambda _bound: foreground_root)
    monkeypatch.setattr(runtime, "_resolve_foreground_form_field_root", lambda _bound: None)

    bound = SimpleNamespace(
        candidate=SimpleNamespace(raw={"runtime_only": True}),
        runtime=SimpleNamespace(
            selector='[fieldid="background"]',
            pointer_receivable=False,
        ),
    )

    assert runtime._resolve_runtime_only_form_field_root(bound) is foreground_root






@pytest.fixture(scope="module")
def _popup_reference_page():
    from playwright.sync_api import sync_playwright

    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.launch(headless=True)
    except Exception:
        playwright.stop()
        raise
    page = browser.new_page(viewport={"width": 1200, "height": 800})
    try:
        yield page
    finally:
        browser.close()
        playwright.stop()


@pytest.mark.parametrize("value", [{"first_available": True}, "主流程/申请"])
def test_runtime_only_return_dialog_select_uses_control_not_label(_popup_reference_page, value) -> None:
    from ydf_browser.binder import bind_runtime_form_field

    page = _popup_reference_page
    page.set_content('''
      <style>
        .wui-modal { width: 700px; padding: 20px; }
        .wui-form-item { display: flex; height: 40px; }
        .wui-form-item-label { width: 180px; }
        .wui-select { width: 300px; height: 32px; border: 1px solid; }
        [role="option"] { height: 30px; }
      </style>
      <div fieldid="_modal" class="wui-modal" role="dialog">
        <div class="wui-form-item">
          <div class="wui-form-item-label"><label title="请选择退回环节">请选择退回环节</label></div>
          <div class="wui-select bip-workflow-select" onclick="document.getElementById('options').hidden=false">
            <span class="wui-select-selection-placeholder">请选择退回环节</span>
          </div>
        </div>
        <div class="workflow-approve-ex">
          <div class="workflow-approve-ex-name">退回说明</div><input name="reason">
        </div>
        <button onclick="this.closest('[role=dialog]').remove()">取消</button>
      </div>
      <div id="options" class="wui-select-dropdown" hidden>
        <div role="option" aria-disabled="true">不可选环节</div>
        <div role="option" onclick="
          const selected=document.querySelector('.wui-select span');
          selected.className='wui-select-selection-item'; selected.textContent=this.textContent;
          this.parentElement.hidden=true;">主流程/申请</div>
      </div>
    ''')
    runtime = _build_runtime()
    runtime._page = page
    bound = bind_runtime_form_field("请选择退回环节", runtime.capture_runtime_elements(None))

    assert bound is not None
    assert bound.candidate.component_name == "RuntimeSelect"
    assert bound.runtime.tag_name != "label"
    assert bound.runtime.role is None
    result = runtime.fill_form_field(bound, value)

    assert page.locator('.wui-select-selection-item').inner_text() == "主流程/申请"
    assert runtime.read_field_value(bound) == "主流程/申请"
    if isinstance(value, dict):
        assert result["actual"] == "主流程/申请"
        assert result["confirmed"] is True
    rebound = bind_runtime_form_field("请选择退回环节", runtime.capture_runtime_elements(None))
    assert rebound is not None
    assert rebound.candidate.component_name == "RuntimeSelect"
    reason = bind_runtime_form_field("退回说明", runtime.capture_runtime_elements(None))
    assert reason is not None
    result = runtime.fill_form_field(reason, "资料不完整")
    assert result["confirmed"] is True
    assert page.locator('input[name="reason"]').input_value() == "资料不完整"


@pytest.mark.parametrize("initial", ["请选择退回环节", "原有环节"])
def test_runtime_only_first_choice_requires_committed_value(_popup_reference_page, initial) -> None:
    from ydf_browser.binder import bind_runtime_form_field

    page = _popup_reference_page
    page.set_content(f'''
      <div class="wui-modal" role="dialog">
        <div class="wui-form-item">
          <label>请选择退回环节</label>
          <div class="wui-select" style="height:32px;width:300px"
            onclick="document.getElementById('options').hidden=false">
            <span class="wui-select-selection-item">{initial}</span>
          </div>
        </div>
      </div>
      <div id="options" class="wui-select-dropdown" hidden>
        <div role="option" onclick="this.parentElement.hidden=true">主流程/申请</div>
      </div>
    ''')
    runtime = _build_runtime()
    runtime._page = page
    bound = bind_runtime_form_field("请选择退回环节", runtime.capture_runtime_elements(None))

    with pytest.raises(RuntimeError, match="下拉选择后未回填"):
        runtime.fill_form_field(bound, {"first_available": True})


@pytest.mark.parametrize("in_frame", [False, True])
@pytest.mark.parametrize("other_label", ["<label>退回说明</label>", ""])
def test_runtime_only_dialog_label_does_not_inherit_other_fields_editability(_popup_reference_page, in_frame, other_label) -> None:
    from ydf_browser.binder import bind_runtime_form_field

    page = _popup_reference_page
    page.set_content('<iframe style="width:800px;height:300px"></iframe>' if in_frame else '')
    frame = page.frames[-1]
    frame.set_content(f'''
      <div fieldid="_modal" class="wui-modal" role="dialog">
        <div class="wui-form-item"><label title="请选择退回环节">请选择退回环节</label></div>
        <div class="wui-form-item">{other_label}<input aria-label="退回说明"></div>
      </div>
    ''')
    runtime = _build_runtime()
    runtime._page = page

    elements = runtime.capture_runtime_elements(None)

    assert bind_runtime_form_field("请选择退回环节", elements) is None
    assert bind_runtime_form_field("退回说明", elements) is not None
    assert all(not item["editable"] for item in elements if item["tag_name"] == "label")


def test_workflow_panel_clicks_checked_radio_action_and_waits_for_close(_popup_reference_page) -> None:
    page = _popup_reference_page
    page.set_content('''
        <button onclick="window.backgroundClicked=true">撤回审批</button>
        <div id="workflow-approve-component">
          <div class="approve-component-title">审批</div>
          <div class="approve-btns-container"><div class="approve_btns_btn_group">
            <label class="wui-radio-button is-checked"
              onclick="document.getElementById('workflow-approve-component').remove()">
              <input type="radio" checked value="withdrawTask"><span>撤回审批</span>
            </label>
          </div></div>
          <div class="history"><button>撤回审批</button></div>
        </div>
    ''')
    runtime = _build_runtime()
    runtime._page = page
    snapshot = {}

    def click():
        snapshot.update(runtime.click_workflow_panel_action("撤回审批"))

    result = ActionCompletion(runtime).execute(
        ActionCompletionRequest("workflow_panel.click", {"action": "撤回审批", "workflow_panel": True}), click,
    )
    assert result.completion_signal == "foreground_closed"
    assert result.fallback_used is False
    assert snapshot["action"]["label"] == "撤回审批"
    assert snapshot["action"]["kind"] == "radio"
    assert page.evaluate("Boolean(window.backgroundClicked)") is False


@pytest.mark.parametrize("variant", ["disabled", "aria_disabled", "hidden", "covered", "duplicate_actions", "duplicate_panels", "child_duplicate", "wrong_label", "history_only"])
def test_workflow_panel_rejects_unsafe_or_missing_action(_popup_reference_page, variant) -> None:
    page = _popup_reference_page
    action = '<button onclick="window.executed=true">撤回审批</button>'
    if variant == "disabled":
        action = '<label><input type="radio" disabled>撤回审批</label>'
    if variant == "aria_disabled":
        action = '<label><input type="radio" aria-disabled="true">撤回审批</label>'
    if variant == "hidden":
        action = '<button style="display:none">撤回审批</button>'
    if variant == "duplicate_actions":
        action *= 2
    if variant == "wrong_label":
        action = '<button>撤回审批（全部）</button>'
    if variant == "history_only":
        action = ''
    panel = f'<div id="workflow-approve-component"><div class="approve-btns-container">{action}</div><div class="history"><button>撤回审批</button></div></div>'
    if variant == "duplicate_panels":
        panel *= 2
    page.set_content(panel)
    if variant == "child_duplicate":
        page.evaluate("() => document.body.append(document.createElement('iframe'))")
        page.frames[1].set_content(panel)
    if variant == "covered":
        page.evaluate('''() => {const overlay=document.createElement('div');
            overlay.style.cssText='position:fixed;inset:0;z-index:9999;background:white';document.body.append(overlay)}''')
    runtime = _build_runtime()
    runtime._page = page
    with pytest.raises(RuntimeError, match="工作流操作面板动作不可用") as exc:
        runtime.click_workflow_panel_action("撤回审批")
    assert exc.value.data["workflow_panel"]["status"] != "ready"
    assert page.evaluate("Boolean(window.executed)") is False


def test_workflow_panel_in_child_frame_opens_explicit_confirmation(_popup_reference_page) -> None:
    page = _popup_reference_page
    page.set_content('<button>背景动作</button><iframe style="width:600px;height:300px"></iframe>')
    frame = page.frames[1]
    frame.set_content('''<div id="workflow-approve-component"><div class="approve-btns-container">
      <button onclick="document.getElementById('confirmation').style.display='block'">撤回审批</button>
      </div></div>
      <div id="confirmation" class="wui-modal" role="dialog" style="display:none">
        <h4>撤回审批</h4><textarea fieldid="approve_comment_textarea"></textarea>
        <button fieldid="approve_component_confirm_ok" onclick="window.confirmed=true">确定</button>
      </div>''')
    runtime = _build_runtime()
    runtime._page = page
    result = ActionCompletion(runtime).execute(
        ActionCompletionRequest("workflow_panel.click", {"workflow_panel": True, "action": "撤回审批"}),
        lambda: (runtime.click_workflow_panel_action("撤回审批"), None)[1],
    )
    assert result.completion_signal == "confirmation_required"
    assert frame.evaluate("Boolean(window.confirmed)") is False


def test_workflow_panel_radio_state_alone_does_not_complete_action(_popup_reference_page) -> None:
    page = _popup_reference_page
    page.set_content('''<div id="workflow-approve-component"><div class="approve-btns-container">
        <label><input type="radio">撤回审批</label></div></div>''')
    runtime = _build_runtime()
    runtime._page = page
    with pytest.raises(TimeoutError):
        ActionCompletion(runtime).execute(
            ActionCompletionRequest("workflow_panel.click", {"workflow_panel": True},
                                    deadline=time.monotonic() + 1),
            lambda: (runtime.click_workflow_panel_action("撤回审批"), None)[1],
        )
    assert page.locator('input[type="radio"]').is_checked()


def test_playwright_runtime_committed_choice_distinguishes_open_filter_from_closed_value(_popup_reference_page) -> None:
    runtime = _build_runtime()
    page = _popup_reference_page
    page.set_content(
        """
        <style>
          #choice-root, .wui-select-selector, .wui-select-selection-search, input, .wui-select-selection-item {
            display: block; width: 320px; height: 32px;
          }
        </style>
        <div id="choice-root" class="wui-select wui-select-open wui-select-show-search">
          <div class="wui-select-selector">
            <span class="wui-select-selection-search">
              <input fieldid="draftTemplateCode_input_search_input"
                value="预制项目支出编报模板" role="combobox" aria-expanded="true">
            </span>
          </div>
        </div>
        """
    )
    root = page.locator("#choice-root")
    root.locator("input").focus()

    assert runtime._choice_root_committed_value_matches(root, "预制项目支出编报模板") is False

    root.evaluate(
        """node => {
          node.classList.remove('wui-select-open');
          const input = node.querySelector('input');
          input.setAttribute('aria-expanded', 'false');
          input.blur();
        }"""
    )

    assert runtime._choice_root_committed_value_matches(root, "预制项目支出编报模板") is True


def test_playwright_runtime_committed_choice_reads_input_root_value(_popup_reference_page) -> None:
    runtime = _build_runtime()
    page = _popup_reference_page
    page.set_content(
        """
        <input id="source-mode" class="wui-select-selection-search-input"
          value="采购" title="采购" role="combobox" aria-expanded="false"
          style="display: block; width: 320px; height: 32px">
        """
    )

    assert runtime._choice_root_committed_value_matches(page.locator("#source-mode"), "采购") is True
















































































































































def test_playwright_runtime_editable_popup_reference_requires_backfill(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _Cell:
        def evaluate(self, _script: str, **_kwargs) -> str:
            return ""

    cell = _Cell()
    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: cell)
    monkeypatch.setattr(runtime, "_first_visible_child_locator", lambda root, selectors: None)
    monkeypatch.setattr(runtime, "_active_editable_locator", lambda: None)
    monkeypatch.setattr(runtime._popup_reference_module(), "editable_cell_looks_like_reference", lambda *args: True)
    _patch_popup_reference_select(monkeypatch, runtime, lambda root, fill_locator, value, **_kwargs: calls.append(f"select:{value}"))

    with pytest.raises(RuntimeError, match="弹出参照选择未回填到字段"):
        runtime._fill_active_editable_table_cell("cell-selector", {"filter": "666666666"})

    assert calls == ["select:{'filter': '666666666'}"]








def test_playwright_runtime_fill_editable_table_row_reports_popup_reference_diagnostics(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    reference_target = {
        "tab": "本单位人员账户",
        "filter": "苏康涯",
        "match": {"column": "户名", "equals": "苏康涯"},
    }

    monkeypatch.setattr(runtime, "_activate_editable_table_cell", lambda *args, **kwargs: "cell-selector")

    def _fill_cell(_selector, value, column_candidate=None) -> dict[str, object]:
        assert value == reference_target
        return {
            "popup_tab_context": [{"label": "本单位人员账户"}],
            "selected": [reference_target],
            "confirmed": True,
            "confirm_label": "确定",
        }

    monkeypatch.setattr(runtime, "_fill_active_editable_table_cell", _fill_cell)

    result = runtime.fill_editable_table_row({"收款方户名": reference_target}, table="汇款转账")

    field_result = result["fields"][0]
    assert field_result["popup_tab_context"] == [{"label": "本单位人员账户"}]
    assert field_result["selected"] == [reference_target]
    assert field_result["confirmed"] is True
    assert field_result["confirm_label"] == "确定"


def test_playwright_runtime_fill_editable_table_cell_uses_popup_for_structured_target_on_input_column(
    monkeypatch,
) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _Cell:
        pass

    class _Input:
        pass

    target = {"tree": {"label": "A05040101 复印纸"}, "first_available": True}
    column = SimpleNamespace(component_name="YDFInput", raw={}, label="物资分类", title="")

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: _Cell())
    monkeypatch.setattr(runtime, "_first_visible_child_locator", lambda root, selectors: _Input())
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda _selector: _Input())
    monkeypatch.setattr(runtime, "_active_editable_locator", lambda: None)
    monkeypatch.setattr(runtime, "_editable_table_cell_looks_like_choice", lambda *_args: False)
    monkeypatch.setattr(runtime, "_editable_table_cell_plain_editor_overrides_reference_metadata", lambda *_args: False)
    monkeypatch.setattr(runtime._popup_reference_module(), "root_has_trigger", lambda root: False)
    monkeypatch.setattr(runtime, "_read_editable_table_cell_text", lambda cell: "")
    monkeypatch.setattr(runtime, "_wait_for_editable_table_cell_backfill", lambda cell, before_text: "A05040101 复印纸")
    _patch_popup_reference_select(monkeypatch, runtime, lambda root, fill, value, **_kwargs: calls.append(f"popup:{value}:{type(root).__name__}:{type(fill).__name__}"))
    monkeypatch.setattr(runtime, "_set_text_field_value", lambda locator, value: calls.append(f"text:{value}"))
    monkeypatch.setattr(runtime, "_has_visible_choice_dropdown", lambda: False)

    runtime._fill_active_editable_table_cell(
        "cell-selector",
        target,
        column_candidate=column,
    )

    assert calls == [f"popup:{target}:_Cell:_Input"]


def test_playwright_runtime_structured_editable_popup_failure_does_not_fall_back_to_text(
    monkeypatch,
) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()

    class _Cell:
        pass

    class _Input:
        pass

    target = {"tree": {"label": "A05040101 复印纸"}, "first_available": True}
    column = SimpleNamespace(component_name="YDFInput", raw={}, label="物资分类", title="")

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: _Cell())
    monkeypatch.setattr(runtime, "_first_visible_child_locator", lambda root, selectors: _Input())
    monkeypatch.setattr(runtime, "_active_editable_locator", lambda: None)
    monkeypatch.setattr(runtime, "_editable_table_cell_looks_like_choice", lambda *_args: False)
    monkeypatch.setattr(runtime, "_editable_table_cell_plain_editor_overrides_reference_metadata", lambda *_args: False)
    monkeypatch.setattr(runtime._popup_reference_module(), "root_has_trigger", lambda root: False)
    _patch_popup_reference_select(monkeypatch, runtime, lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("无法打开弹出参照选择框")))
    monkeypatch.setattr(
        runtime,
        "_set_text_field_value",
        lambda *_args: (_ for _ in ()).throw(AssertionError("structured reference target must not become text")),
    )

    with pytest.raises(RuntimeError) as exc_info:
        runtime._fill_active_editable_table_cell(
            "cell-selector",
            target,
            column_candidate=column,
        )

    message = str(exc_info.value)
    assert "无法打开弹出参照选择框" in message
    assert "A05040101 复印纸" in message


def test_playwright_runtime_fill_editable_table_row_reports_tree_popup_reference_diagnostics(
    monkeypatch,
) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    reference_target = {"tree": {"label": "A05040101 复印纸"}, "first_available": True}

    monkeypatch.setattr(runtime, "_activate_editable_table_cell", lambda *args, **kwargs: "cell-selector")

    def _fill_cell(_selector, value, column_candidate=None) -> dict[str, object]:
        assert value == reference_target
        return {
            "popup_tree_context": [{"label": "A05040101 复印纸"}],
            "selected": [reference_target],
            "confirmed": True,
            "confirm_label": "确定",
        }

    monkeypatch.setattr(runtime, "_fill_active_editable_table_cell", _fill_cell)

    result = runtime.fill_editable_table_row({"物资分类": reference_target}, table="物资入库")

    field_result = result["fields"][0]
    assert field_result["popup_tree_context"] == [{"label": "A05040101 复印纸"}]
    assert field_result["selected"] == [reference_target]
    assert field_result["confirmed"] is True
    assert field_result["confirm_label"] == "确定"


def test_playwright_runtime_fill_editable_table_row_reports_first_available_candidate_diagnostics(
    monkeypatch,
) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    reference_target = {"tree": {"label": "A05040101 复印纸"}, "first_available": True}

    monkeypatch.setattr(runtime, "_activate_editable_table_cell", lambda *args, **kwargs: "cell-selector")

    def _fill_cell(_selector, value, column_candidate=None) -> dict[str, object]:
        assert value == reference_target
        return {
            "popup_tree_context": [{"label": "A05040101 复印纸"}],
            "selected": [reference_target],
            "confirmed": True,
            "confirm_label": "确定",
            "candidate_kind": "table-row",
            "candidate_source": "right-table",
            "candidate_text": "A050401010000000001 A3复印纸",
            "candidate_requires_selection": True,
            "candidate_selected": True,
        }

    monkeypatch.setattr(runtime, "_fill_active_editable_table_cell", _fill_cell)

    result = runtime.fill_editable_table_row({"物资分类": reference_target}, table="物资入库")

    field_result = result["fields"][0]
    assert field_result["candidate_kind"] == "table-row"
    assert field_result["candidate_source"] == "right-table"
    assert field_result["candidate_text"] == "A050401010000000001 A3复印纸"
    assert field_result["candidate_requires_selection"] is True
    assert field_result["candidate_selected"] is True


def test_playwright_runtime_fill_editable_table_cell_uses_choice_for_tree_select_column(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _Cell:
        pass

    class _Input:
        pass

    column = SimpleNamespace(component_name="YDFTreeSelect", raw={}, label="政府预算支出经济分类", title="")

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: _Cell())
    monkeypatch.setattr(runtime, "_first_visible_child_locator", lambda root, selectors: _Input())
    monkeypatch.setattr(runtime, "_active_editable_locator", lambda: None)
    monkeypatch.setattr(runtime._popup_reference_module(), "editable_cell_looks_like_reference", lambda *args: False)
    monkeypatch.setattr(runtime, "_read_editable_table_cell_text", lambda cell, **_kwargs: "50101 工资奖金津补贴")
    monkeypatch.setattr(runtime, "_select_query_choice", lambda root, fill, value, **_kwargs: calls.append(f"choice:{value}"))
    monkeypatch.setattr(runtime, "_set_text_field_value", lambda locator, value: calls.append(f"text:{value}"))
    monkeypatch.setattr(runtime, "_has_visible_choice_dropdown", lambda: False)

    runtime._fill_active_editable_table_cell(
        "cell-selector",
        "50101 工资奖金津补贴",
        column_candidate=column,
    )

    assert calls == ["choice:50101 工资奖金津补贴"]


def test_playwright_runtime_fill_editable_table_cell_recovers_choice_dropdown_after_popup_trigger(
    monkeypatch,
) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _Cell:
        pass

    class _Input:
        pass

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: _Cell())
    monkeypatch.setattr(runtime, "_first_visible_child_locator", lambda root, selectors: _Input())
    monkeypatch.setattr(runtime, "_active_editable_locator", lambda: None)
    monkeypatch.setattr(runtime._popup_reference_module(), "editable_cell_looks_like_reference", lambda *args: True)
    monkeypatch.setattr(runtime, "_editable_table_cell_looks_like_choice", lambda *args: False)
    monkeypatch.setattr(runtime, "_has_visible_choice_dropdown", lambda: True)

    def _raise_popup_missing(*_args, **_kwargs) -> None:
        calls.append("popup")
        raise RuntimeError("未打开弹出参照选择框")

    _patch_popup_reference_select(monkeypatch, runtime, _raise_popup_missing)
    monkeypatch.setattr(
        runtime,
        "_try_click_query_choice_with_wait",
        lambda value, timeout_ms=1200: calls.append(f"option:{value}") or True,
    )
    monkeypatch.setattr(
        runtime,
        "_query_choice_selection_settled",
        lambda root, value, **_kwargs: calls.append(f"settled:{value}") or True,
    )
    monkeypatch.setattr(runtime, "_try_click_query_choice_text_fallback", lambda value: False)
    monkeypatch.setattr(runtime, "_wait_for_editable_table_cell_value", lambda cell, value: str(value))

    runtime._fill_active_editable_table_cell(
        "cell-selector",
        "办公费",
        column_candidate=None,
    )

    assert calls == ["popup", "option:办公费", "settled:办公费"]


def test_playwright_runtime_activate_editable_cell_does_not_scroll_when_cell_is_visible(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _Cell:
        def scroll_into_view_if_needed(self, timeout: int = 0) -> None:
            calls.append("scroll")

        def evaluate(self, script: str, *_args) -> None:
            assert "isActionTarget" in script
            assert "增行|删行|新增|插入|复制|删除|更多" in script
            calls.append("dom-click")

        def click(self, timeout: int = 0) -> None:
            calls.append("playwright-click")

        def dblclick(self, timeout: int = 0) -> None:
            calls.append("playwright-dblclick")

    monkeypatch.setattr(runtime, "_find_editable_table_cell_selector", lambda payload: "[cell]")
    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: _Cell())
    monkeypatch.setattr(runtime, "_locator_intersects_viewport", lambda locator: True, raising=False)
    monkeypatch.setattr(runtime, "_wait_for_editable_table_cell_editor", lambda cell, timeout_ms=600: calls.append("editor") or True)

    selector = runtime._activate_editable_table_cell("费用名称", row_number=-1)

    assert selector == "[cell]"
    assert calls == ["dom-click", "editor"]


def test_playwright_runtime_relocates_editable_cell_after_horizontal_reveal(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []
    selectors = iter(["[cell-before]", "[cell-after]"])

    class _Cell:
        def click(self, timeout: int = 0) -> None:
            calls.append("click")

        def dblclick(self, timeout: int = 0) -> None:
            calls.append("dblclick")

        def evaluate(self, _script: str, *_args) -> None:
            calls.append("dom-click")

    monkeypatch.setattr(
        runtime,
        "_find_editable_table_cell_selector",
        lambda payload: calls.append(f"find:{payload['column']}") or next(selectors),
    )
    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: calls.append(f"resolve:{selector}") or _Cell())
    monkeypatch.setattr(runtime, "_locator_intersects_viewport", lambda locator: True, raising=False)
    monkeypatch.setattr(runtime, "_reveal_editable_table_cell_for_activation", lambda cell: calls.append("reveal") or True, raising=False)
    monkeypatch.setattr(runtime, "_wait_for_editable_table_cell_editor", lambda cell, timeout_ms=600: calls.append("editor") or True)

    selector = runtime._activate_editable_table_cell("政府预算支出经济分类", row_number=1, table="指标信息")

    assert selector == "[cell-after]"
    assert calls == [
        "find:政府预算支出经济分类",
        "resolve:[cell-before]",
        "reveal",
        "find:政府预算支出经济分类",
        "resolve:[cell-after]",
        "dom-click",
        "editor",
    ]


def test_playwright_runtime_retries_editable_cell_activation_after_moving_mouse_off_row_actions(monkeypatch) -> None:
    runtime = _build_runtime()
    calls: list[str] = []

    class _Mouse:
        def move(self, x: int, y: int) -> None:
            calls.append(f"mouse:{x},{y}")

    class _Page(_FakePage):
        mouse = _Mouse()

    class _Cell:
        def click(self, timeout: int = 0) -> None:
            calls.append("playwright-click")

        def dblclick(self, timeout: int = 0) -> None:
            calls.append("playwright-dblclick")

        def evaluate(self, _script: str, *_args) -> None:
            calls.append("dom-click")

    runtime._page = _Page()
    monkeypatch.setattr(runtime, "_find_editable_table_cell_selector", lambda payload: calls.append("find") or "[cell]")
    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: calls.append("resolve") or _Cell())
    monkeypatch.setattr(runtime, "_locator_intersects_viewport", lambda locator: True, raising=False)
    monkeypatch.setattr(runtime, "_reveal_editable_table_cell_for_activation", lambda cell: False, raising=False)

    attempts = {"count": 0}

    def _wait_for_editor(_cell, timeout_ms: int = 600) -> bool:
        attempts["count"] += 1
        calls.append(f"editor:{attempts['count']}")
        return attempts["count"] == 5

    monkeypatch.setattr(runtime, "_wait_for_editable_table_cell_editor", _wait_for_editor)

    selector = runtime._activate_editable_table_cell("测算依据及说明", row_number=-1, table="测算信息")

    assert selector == "[cell]"
    assert "mouse:1,1" in calls
    assert calls[-2:] == ["dom-click", "editor:5"]


def test_playwright_runtime_collapses_row_actions_before_retrying_editable_cell_activation(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []
    selectors = iter(["[cell-blocked]", "[cell-after-mouse]", "[cell-after-collapse]"])

    class _Cell:
        def __init__(self, selector: str) -> None:
            self.selector = selector

        def click(self, timeout: int = 0, **kwargs) -> None:
            force = kwargs.get("force", False)
            calls.append(f"playwright-click:{self.selector}:force={force}")

        def dblclick(self, timeout: int = 0, **kwargs) -> None:
            force = kwargs.get("force", False)
            calls.append(f"playwright-dblclick:{self.selector}:force={force}")

        def evaluate(self, _script: str, *_args) -> None:
            calls.append(f"dispatch:{self.selector}")

    monkeypatch.setattr(
        runtime,
        "_find_editable_table_cell_selector",
        lambda payload: calls.append("find") or next(selectors),
    )
    monkeypatch.setattr(
        runtime,
        "_resolve_visible_locator",
        lambda selector: calls.append(f"resolve:{selector}") or _Cell(selector),
    )
    monkeypatch.setattr(runtime, "_locator_intersects_viewport", lambda locator: True, raising=False)
    monkeypatch.setattr(runtime, "_reveal_editable_table_cell_for_activation", lambda cell: False, raising=False)
    monkeypatch.setattr(
        runtime,
        "_collapse_editable_table_row_action_overlay",
        lambda cell: calls.append(f"collapse:{cell.selector}") or {"collapsed": True},
        raising=False,
    )

    attempts = {"count": 0}

    def _wait_for_editor(_cell, timeout_ms: int = 600) -> bool:
        attempts["count"] += 1
        calls.append(f"editor:{attempts['count']}")
        return attempts["count"] == 8

    monkeypatch.setattr(runtime, "_wait_for_editable_table_cell_editor", _wait_for_editor)

    selector = runtime._activate_editable_table_cell("备注", row_number=-1, table="需求清单")

    assert selector == "[cell-after-collapse]"
    assert "collapse:[cell-after-mouse]" in calls
    assert calls[-2:] == ["playwright-click:[cell-after-collapse]:force=True", "editor:8"]


def test_playwright_runtime_editable_cell_activation_falls_back_to_cell_when_row_actions_cover_points() -> None:
    source_consts = "\n".join(str(item) for item in runtime_module.PlaywrightRuntime._dispatch_editable_table_cell_activation.__code__.co_consts)
    assert "let target = node" in source_consts
    assert "foundUsableTarget" in source_consts
    assert "if (!foundUsableTarget) target = node" in source_consts
    assert "rect.width / 2" in source_consts
    assert source_consts.index("rect.width / 2") < source_consts.index("rect.left + 8")
    for label in ("插入", "复制", "更多"):
        assert label in source_consts


def test_playwright_runtime_restores_collapsed_row_actions_after_editable_field_backfill(monkeypatch) -> None:
    runtime = _build_runtime()
    calls: list[str] = []

    def _activate(*_args, **_kwargs) -> str:
        runtime._last_editable_table_row_action_overlay = {"collapse": {"collapsed": True}}
        return "cell-selector"

    monkeypatch.setattr(runtime, "_activate_editable_table_cell", _activate)
    monkeypatch.setattr(runtime, "_fill_active_editable_table_cell", lambda *_args, **_kwargs: calls.append("fill"))
    monkeypatch.setattr(
        runtime,
        "_restore_last_editable_table_row_action_overlay",
        lambda: calls.append("restore") or {"collapse": {"collapsed": True}, "restore": {"restored": True}},
        raising=False,
    )

    result = runtime.fill_editable_table_row({"备注": "UI"}, table="需求清单")

    assert calls == ["fill", "restore"]
    assert result["fields"][0]["row_action_overlay"]["restore"]["restored"] is True


def test_playwright_runtime_row_action_restore_failure_keeps_confirmed_field_result(monkeypatch) -> None:
    runtime = _build_runtime()

    def _activate(*_args, **_kwargs) -> str:
        runtime._last_editable_table_row_action_overlay = {"collapse": {"collapsed": True}}
        return "cell-selector"

    monkeypatch.setattr(runtime, "_activate_editable_table_cell", _activate)
    monkeypatch.setattr(runtime, "_fill_active_editable_table_cell", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        runtime,
        "_restore_last_editable_table_row_action_overlay",
        lambda: (_ for _ in ()).throw(RuntimeError("restore failed")),
        raising=False,
    )

    result = runtime.fill_editable_table_row({"备注": "UI"}, table="需求清单")

    assert result["fields"][0]["value"] == "UI"
    assert result["fields"][0]["row_action_overlay"]["restore"]["restored"] is False
    assert "restore failed" in result["fields"][0]["row_action_overlay"]["restore"]["error"]


def test_playwright_runtime_row_action_overlay_helpers_are_scoped_to_current_cell_row() -> None:
    runtime = _build_runtime()
    calls: list[str] = []

    class _Cell:
        def evaluate(self, script: str, *_args):
            calls.append(script)
            assert "node.closest('tr" in script
            assert "tableRoot" in script
            assert "tableRoot.querySelectorAll" in script
            assert "searchRoot.querySelectorAll" in script
            assert "[class*=\"action\"]" in script
            assert "document.querySelectorAll" not in script
            return {"collapsed": True}

    assert runtime._collapse_editable_table_row_action_overlay(_Cell()) == {"collapsed": True}
    assert calls
    assert "iconOnlyToggle" in calls[0]


def test_playwright_runtime_row_action_collapse_uses_playwright_click(monkeypatch) -> None:
    runtime = _build_runtime()
    calls: list[str] = []

    class _Cell:
        def evaluate(self, _script: str, *_args):
            return {"collapsed": True, "selector": '[data-ydf-browser-row-action-toggle="collapse"]'}

    class _Toggle:
        def click(self, timeout: int = 0, **kwargs) -> None:
            calls.append(f"click:{kwargs.get('force', False)}")

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: _Toggle())

    result = runtime._collapse_editable_table_row_action_overlay(_Cell())

    assert calls == ["click:True"]
    assert result["collapsed"] is True


def test_playwright_runtime_row_action_restore_does_not_treat_text_left_header_as_toggle() -> None:
    runtime = _build_runtime()
    calls: list[str] = []

    class _Cell:
        def evaluate(self, script: str, *_args):
            calls.append(script)
            assert "|left|" not in script
            assert "hasIcon && item.rect.width <= 40" not in script
            return {"restored": False, "reason": "missing-row-action-toggle"}

    assert runtime._restore_editable_table_row_action_overlay(_Cell()) == {
        "restored": False,
        "reason": "missing-row-action-toggle",
    }


def test_playwright_runtime_waits_for_external_choice_dropdown_after_editable_cell_activation(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    monkeypatch.setattr(runtime, "_editable_table_cell_has_active_editor", lambda cell: False)
    monkeypatch.setattr(runtime, "_has_visible_choice_dropdown", lambda: True)

    assert runtime._wait_for_editable_table_cell_editor(object(), timeout_ms=0, dropdown_before=False) is True
    assert runtime._wait_for_editable_table_cell_editor(object(), timeout_ms=0, dropdown_before=True) is False



def test_playwright_runtime_fill_editable_table_cell_uses_active_external_choice_dropdown(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    cell = _FakeEditableCell()
    calls: list[str] = []
    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: cell)
    monkeypatch.setattr(runtime, "_first_visible_child_locator", lambda root, selectors: None)
    monkeypatch.setattr(runtime, "_active_editable_locator_within", lambda root: None)
    monkeypatch.setattr(runtime, "_locator_is_directly_editable", lambda locator: False)
    monkeypatch.setattr(runtime, "_has_visible_choice_dropdown", lambda: True)
    monkeypatch.setattr(runtime, "_try_click_query_choice_with_wait", lambda value, timeout_ms=5000: calls.append(value) or True)
    monkeypatch.setattr(runtime, "_wait_for_query_choice_dropdown_to_settle", lambda: calls.append("settle"))
    monkeypatch.setattr(runtime, "_query_choice_selection_settled", lambda cell, value: True)
    monkeypatch.setattr(runtime, "_wait_for_editable_table_cell_value", lambda cell, value: str(value))

    runtime._fill_active_editable_table_cell("cell-selector", "A001")

    assert calls == ["A001"]


def test_playwright_runtime_first_available_prefers_new_dropdown_over_popup_metadata(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    runtime._editable_table_choice_dropdown_before_activation = False
    cell = _FakeEditableCell()
    calls: list[str] = []
    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: cell)
    monkeypatch.setattr(runtime, "_first_visible_child_locator", lambda root, selectors: object())
    monkeypatch.setattr(runtime, "_safe_has_visible_choice_dropdown", lambda: True)
    monkeypatch.setattr(runtime, "_read_editable_table_cell_text", lambda root: "")
    monkeypatch.setattr(runtime, "_try_select_current_editable_table_choice", lambda root, value: calls.append("choice") or True)
    monkeypatch.setattr(runtime, "_wait_for_editable_table_cell_backfill", lambda root, before: "234567 测试指标")
    _patch_popup_reference_select(monkeypatch, runtime, lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not route to popup")))

    runtime._fill_active_editable_table_cell(
        "cell-selector",
        {"first_available": True},
        column_candidate=SimpleNamespace(component_name="YDFInput", raw={}),
    )

    assert calls == ["choice"]


def test_playwright_runtime_first_query_choice_falls_back_to_plain_text_children() -> None:
    source = "\n".join(str(item) for item in PlaywrightRuntime._click_first_query_choice.__code__.co_consts)

    assert "root.querySelectorAll('*')" in source


def test_playwright_runtime_first_available_waits_for_async_choice_options(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    attempts = iter([False, True])
    waits: list[int] = []
    monkeypatch.setattr(runtime, "_has_visible_choice_dropdown", lambda: True)
    monkeypatch.setattr(runtime, "_click_first_query_choice", lambda: next(attempts))
    monkeypatch.setattr(runtime, "_wait_for_query_choice_dropdown_to_settle", lambda: None)
    monkeypatch.setattr(runtime._page, "wait_for_timeout", lambda timeout: waits.append(timeout))

    assert runtime._try_select_current_editable_table_choice(object(), {"first_available": True}) is True
    assert waits == [250]


def test_playwright_runtime_editable_table_editor_missing_reports_activation_state(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    cell = _FakeEditableCell()
    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: cell)
    monkeypatch.setattr(runtime, "_first_visible_child_locator", lambda root, selectors: None)
    monkeypatch.setattr(runtime, "_active_editable_locator_within", lambda root: None)
    monkeypatch.setattr(runtime._popup_reference_module(), "editable_cell_looks_like_reference", lambda *args: False)
    monkeypatch.setattr(runtime, "_describe_editable_table_cell", lambda cell: "cell diag")
    monkeypatch.setattr(runtime, "_describe_editable_table_activation_state", lambda cell: "activation diag")
    monkeypatch.setattr(runtime, "_save_diagnostic_screenshot", lambda name: "")

    with pytest.raises(RuntimeError) as exc_info:
        runtime._fill_active_editable_table_cell("cell-selector", "1")

    assert "activation_state=activation diag" in str(exc_info.value)


def test_playwright_runtime_editable_table_activation_state_summarizes_attempts_focus_and_candidates(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._last_editable_table_activation_attempts = [{"action": "dispatch-click", "ready": False}]
    runtime._last_editable_table_cell_resolution = {
        "locator_source": "text-geometry",
        "targetIdentity": {"dataField": "internalDepName"},
        "actualIdentity": {"data_field": "internalDepCode"},
    }

    class _Focused:
        def evaluate(self, _script: str):
            return {"tag": "input", "className": "wui-input", "value": ""}

    monkeypatch.setattr(runtime, "_safe_has_visible_choice_dropdown", lambda: True)
    monkeypatch.setattr(runtime, "_editable_table_cell_has_active_editor", lambda cell: False)
    monkeypatch.setattr(runtime, "_active_editable_locator_within", lambda cell: None)
    monkeypatch.setattr(runtime, "_active_editable_locator", lambda: _Focused())
    monkeypatch.setattr(runtime, "_collect_choice_diagnostic_text", lambda: ".wui-select-dropdown[0]=秘书处01")

    state = runtime._describe_editable_table_activation_state(object())

    assert '"activation_attempts": [{"action": "dispatch-click", "ready": false}]' in state
    assert '"focused_editor": {"tag": "input"' in state
    assert '"choice_surface": ".wui-select-dropdown[0]=秘书处01"' in state
    assert '"locator_source": "text-geometry"' in state
    assert '"dataField": "internalDepName"' in state


def test_playwright_runtime_select_choice_can_skip_initial_root_click_for_active_editable_cell(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _ChoiceRoot:
        def click(self, timeout: int = 0) -> None:
            calls.append("unexpected-root-click")

    class _ChoiceInput:
        pass

    monkeypatch.setattr(
        runtime,
        "_fill_query_choice_filter",
        lambda fill, value, **kwargs: calls.append(f"filter:{kwargs.get('prevent_scroll')}"),
    )
    monkeypatch.setattr(runtime, "_open_choice_field_without_scroll", lambda root, fill: calls.append("open-no-scroll"), raising=False)
    monkeypatch.setattr(runtime, "_wait_for_query_choice_surface_ready", lambda timeout_ms=2500: calls.append(f"ready:{timeout_ms}") or True, raising=False)
    monkeypatch.setattr(runtime, "_try_click_query_choice_with_wait", lambda value, timeout_ms=1200: calls.append(f"option:{value}") or True)
    monkeypatch.setattr(runtime, "_query_choice_dropdown_visible", lambda: True)
    monkeypatch.setattr(
        runtime,
        "_query_choice_selection_settled",
        lambda root, value, **kwargs: calls.append(f"settled:{kwargs.get('require_value_match')}") or True,
    )

    runtime._select_query_choice(
        _ChoiceRoot(),
        _ChoiceInput(),
        "办公费",
        require_value_match=True,
        root_already_active=True,
    )

    assert calls == ["open-no-scroll", "ready:2500", "option:办公费", "settled:True"]


def test_playwright_runtime_select_choice_uses_visible_option_before_filtering(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _Root:
        def click(self, timeout: int = 0) -> None:
            calls.append("root-click")

    class _Input:
        def fill(self, value: str, timeout: int = 0) -> None:
            calls.append(f"fill:{value}")

    monkeypatch.setattr(runtime, "_try_click_query_choice_with_wait", lambda value, timeout_ms=1200: calls.append(f"click:{value}:{timeout_ms}") or True)
    monkeypatch.setattr(runtime, "_query_choice_selection_settled", lambda root, value, **kwargs: calls.append("settled") or True)
    monkeypatch.setattr(runtime, "_query_choice_dropdown_visible", lambda: True)

    runtime._select_query_choice(_Root(), _Input(), "采购")

    assert calls == ["root-click", "click:采购:800", "settled"]


def test_playwright_runtime_choice_stops_after_value_backfills_even_if_dropdown_lingers(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _Root:
        def click(self, timeout: int = 0) -> None:
            calls.append("root-click")

    class _Input:
        def fill(self, value: str, timeout: int = 0) -> None:
            calls.append(f"fill:{value}")

    monkeypatch.setattr(runtime, "_try_click_query_choice_with_wait", lambda value, timeout_ms=1200: calls.append(f"click:{value}") or True)
    monkeypatch.setattr(runtime, "_choice_root_value_matches", lambda root, value: True)
    monkeypatch.setattr(runtime, "_query_choice_dropdown_visible", lambda: True)
    monkeypatch.setattr(runtime, "_blur_query_choice_root", lambda root: calls.append("blur"))
    monkeypatch.setattr(runtime, "_force_dismiss_query_choice_dropdown", lambda root: calls.append("dismiss"))
    monkeypatch.setattr(runtime, "_try_click_query_choice_text_fallback", lambda value: calls.append(f"fallback:{value}") or False)
    monkeypatch.setattr(runtime, "_open_existing_select_for_filter", lambda root, fill, value: calls.append("reopen"))
    monkeypatch.setattr(runtime, "_expand_query_choice_tree_until_visible", lambda value: calls.append("expand"))
    monkeypatch.setattr(runtime, "_try_commit_query_choice_with_keyboard", lambda root, fill, value, **kwargs: calls.append("keyboard") or False)
    monkeypatch.setattr(runtime, "_collect_choice_diagnostic_text", lambda: "")
    monkeypatch.setattr(runtime, "_save_diagnostic_screenshot", lambda name: "")

    runtime._select_query_choice(_Root(), _Input(), "50101 工资奖金津补贴")

    assert calls == [
        "root-click",
        "click:50101 工资奖金津补贴",
        "blur",
        "dismiss",
    ]


def test_playwright_runtime_choice_stops_after_visible_text_backfills_when_selection_value_unreadable(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _Root:
        def click(self, timeout: int = 0) -> None:
            calls.append("root-click")

    class _Input:
        def fill(self, value: str, timeout: int = 0) -> None:
            calls.append(f"fill:{value}")

    monkeypatch.setattr(runtime, "_try_click_query_choice_with_wait", lambda value, timeout_ms=1200: calls.append(f"click:{value}") or True)
    monkeypatch.setattr(runtime, "_choice_root_value_matches", lambda root, value: calls.append("value-match:false") or False)
    monkeypatch.setattr(runtime, "_choice_root_visible_value_matches", lambda root, value: calls.append("visible-match:true") or True, raising=False)
    monkeypatch.setattr(runtime, "_query_choice_dropdown_visible", lambda: False)
    monkeypatch.setattr(runtime, "_blur_query_choice_root", lambda root: calls.append("blur"))
    monkeypatch.setattr(runtime, "_force_dismiss_query_choice_dropdown", lambda root: calls.append("dismiss"))
    monkeypatch.setattr(runtime, "_try_click_query_choice_text_fallback", lambda value: calls.append(f"fallback:{value}") or False)
    monkeypatch.setattr(runtime, "_open_existing_select_for_filter", lambda root, fill, value: calls.append("reopen"))
    monkeypatch.setattr(runtime, "_expand_query_choice_tree_until_visible", lambda value: calls.append("expand"))
    monkeypatch.setattr(runtime, "_try_commit_query_choice_with_keyboard", lambda root, fill, value, **kwargs: calls.append("keyboard") or False)
    monkeypatch.setattr(runtime, "_collect_choice_diagnostic_text", lambda: "")
    monkeypatch.setattr(runtime, "_save_diagnostic_screenshot", lambda name: "")

    runtime._select_query_choice(_Root(), _Input(), "50101 工资奖金津补贴")

    assert calls == [
        "root-click",
        "fill:50101 工资奖金津补贴",
        "click:50101 工资奖金津补贴",
        "value-match:false",
        "visible-match:true",
        "blur",
    ]


def test_playwright_runtime_editable_choice_cell_requires_backfill(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _Cell:
        pass

    class _Input:
        pass

    column = SimpleNamespace(component_name="YDFTreeSelect", raw={}, label="政府预算支出经济分类", title="")

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: _Cell())
    monkeypatch.setattr(runtime, "_first_visible_child_locator", lambda root, selectors: _Input())
    monkeypatch.setattr(runtime, "_active_editable_locator", lambda: None)
    monkeypatch.setattr(runtime._popup_reference_module(), "editable_cell_looks_like_reference", lambda *args: False)
    monkeypatch.setattr(runtime, "_read_editable_table_cell_text", lambda cell, **_kwargs: "")
    monkeypatch.setattr(runtime, "_select_query_choice", lambda root, fill, value, **_kwargs: calls.append(f"choice:{value}"))
    monkeypatch.setattr(runtime, "_set_text_field_value", lambda locator, value: calls.append(f"text:{value}"))
    monkeypatch.setattr(runtime, "_has_visible_choice_dropdown", lambda: False)
    monkeypatch.setattr(runtime, "_describe_editable_table_cell", lambda cell: "empty cell")
    monkeypatch.setattr(runtime, "_save_diagnostic_screenshot", lambda name: "")

    with pytest.raises(RuntimeError, match="可编辑表格单元格录入后未回填"):
        runtime._fill_active_editable_table_cell(
            "cell-selector",
            "50101 工资奖金津补贴",
            column_candidate=column,
        )

    assert calls == ["choice:50101 工资奖金津补贴"]


def test_playwright_runtime_editable_table_cell_value_matches_formatted_number() -> None:
    runtime = _build_runtime()

    assert runtime._editable_table_cell_value_matches("1,000", 1000)
    assert runtime._editable_table_cell_value_matches("1,000.00", "1000")
    assert runtime._editable_table_cell_value_matches("1000", "1000.0")
    assert not runtime._editable_table_cell_value_matches("A1000", "1000.0")












def test_playwright_runtime_popup_reference_prefers_narrowed_field_root(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _Root:
        pass

    class _NarrowedRoot:
        def evaluate(self, _script: str, *args: object) -> object:
            if args:
                return {"index": 0, "count": 1}
            return {"id": "narrowed-root", "fieldid": "", "dataFieldid": "", "uikey": ""}

    class _Input:
        pass

    root = _Root()
    narrowed = _NarrowedRoot()
    field_input = _Input()

    monkeypatch.setattr(
        runtime,
        "_resolve_visible_locator",
        lambda selector: narrowed if "narrowed-root" in selector else root,
    )
    monkeypatch.setattr(runtime._popup_reference_module(), "looks_like_field", lambda locator, bound: True)
    monkeypatch.setattr(runtime, "_resolve_foreground_form_field_root", lambda bound: None)
    monkeypatch.setattr(runtime, "_narrow_form_field_root", lambda current_root, bound: narrowed)
    monkeypatch.setattr(
        runtime,
        "_resolve_form_field_root_by_label_position",
        lambda bound: (_ for _ in ()).throw(AssertionError("label-position fallback should not run first")),
    )
    monkeypatch.setattr(runtime, "_resolve_fill_locator_from_root", lambda locator: calls.append(f"fill:{type(locator).__name__}") or field_input)
    _patch_popup_reference_select(monkeypatch, runtime, lambda locator, fill, value: calls.append(f"popup:{type(locator).__name__}:{value}"))

    bound = SimpleNamespace(
        candidate=SimpleNamespace(component_name="YDFTreeModalSelect", raw={}),
        runtime=SimpleNamespace(selector='[uikey="queryArea"]'),
    )

    runtime.fill_form_field(bound, "C99000000 其他服务")

    assert calls == ["fill:_NarrowedRoot", "popup:_NarrowedRoot:C99000000 其他服务"]


def test_playwright_runtime_plain_choice_field_precedes_popup_reference(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _Root:
        pass

    class _Input:
        pass

    root = _Root()
    fill_locator = _Input()

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: root)
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: fill_locator)
    monkeypatch.setattr(runtime, "_looks_like_switch_field", lambda locator, bound: False)
    monkeypatch.setattr(runtime, "_looks_like_radio_field", lambda locator, bound: False)
    monkeypatch.setattr(runtime, "_looks_like_choice_field", lambda locator, bound: True)
    monkeypatch.setattr(runtime._popup_reference_module(), "root_has_trigger", lambda locator: True)
    _patch_popup_reference_select(monkeypatch, runtime, lambda locator, fill, value: (_ for _ in ()).throw(AssertionError("plain choice should not use popup reference")))
    monkeypatch.setattr(
        runtime,
        "_select_query_choice",
        lambda locator, fill, value, **kwargs: calls.append(f"choice:{value}:{kwargs.get('require_value_match')}"),
    )

    bound = SimpleNamespace(
        candidate=SimpleNamespace(component_name="RuntimeInput", raw={"runtime_only": True}),
        runtime=SimpleNamespace(selector='[uikey="accNature"]'),
    )

    runtime.fill_form_field(bound, "003 一般存款账户")

    assert calls == ["choice:003 一般存款账户:True"]


def test_playwright_runtime_plain_choice_does_not_skip_filter_text(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    root = object()
    calls: list[str] = []

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda _selector: root)
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda _selector: object())
    monkeypatch.setattr(runtime, "_looks_like_switch_field", lambda *_args: False)
    monkeypatch.setattr(runtime, "_looks_like_radio_field", lambda *_args: False)
    monkeypatch.setattr(runtime, "_looks_like_choice_field", lambda *_args: True)
    monkeypatch.setattr(runtime._popup_reference_module(), "root_has_trigger", lambda _root: False)
    monkeypatch.setattr(runtime, "_choice_field_is_multi_select", lambda *_args: False)
    monkeypatch.setattr(runtime, "_read_field_value_from_container", lambda _bound: "预制项目支出编报模板")
    monkeypatch.setattr(runtime, "_choice_root_committed_value_matches", lambda *_args: False)
    monkeypatch.setattr(
        runtime,
        "_select_query_choice",
        lambda _root, _fill, value, **_kwargs: calls.append(value),
    )

    bound = SimpleNamespace(
        candidate=SimpleNamespace(component_name="YDFTreeSelect", raw={}),
        runtime=SimpleNamespace(selector='[fieldid="draftTemplateCode"]'),
    )

    runtime.fill_form_field(bound, "预制项目支出编报模板")

    assert calls == ["预制项目支出编报模板"]



def test_playwright_runtime_fill_form_field_fills_plain_input_and_commits(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _Input:
        def __init__(self) -> None:
            self.value = ""

        def click(self, timeout: int = 0) -> None:
            calls.append("click")

        def type(self, value: str, delay: int = 0) -> None:
            self.value = value
            calls.append(f"type:{value}")

        def fill(self, value: str) -> None:
            self.value = value
            calls.append(f"fill:{value}")

        def press(self, key: str, timeout: int = 0) -> None:
            calls.append(f"press:{key}")

        def input_value(self, timeout: int = 0) -> str:
            return self.value

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: object())
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: _Input())
    monkeypatch.setattr(runtime, "_looks_like_choice_field", lambda root, bound: False)

    bound = SimpleNamespace(runtime=SimpleNamespace(selector='[fieldid="projectName"]'))

    runtime.fill_form_field(bound, "puqh测试项目1")

    assert calls == [
        "click", "press:Meta+A", "press:Control+A", "press:Backspace", "type:puqh测试项目1", "press:Tab",
    ]


def test_playwright_runtime_fill_form_field_fails_when_plain_input_does_not_backfill(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()

    class _Input:
        def click(self, timeout: int = 0) -> None:
            pass

        def press(self, key: str, timeout: int = 0) -> None:
            pass

        def type(self, value: str, delay: int = 0) -> None:
            pass

        def evaluate(self, script: str, value: str) -> None:
            pass

        def input_value(self, timeout: int = 0) -> str:
            return ""

        def text_content(self, timeout: int = 0) -> str:
            return ""

        def get_attribute(self, name: str, timeout: int = 0) -> str:
            return ""

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: object())
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: _Input())
    monkeypatch.setattr(runtime, "_looks_like_choice_field", lambda root, bound: False)

    bound = SimpleNamespace(
        candidate=SimpleNamespace(label="项目名称", component_name="YDFInput"),
        runtime=SimpleNamespace(selector='[fieldid="projectName"]', in_dialog=True),
    )

    try:
        runtime.fill_form_field(bound, "Codex项目")
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected fill_form_field to fail when value does not backfill")

    assert "项目名称" in message
    assert "Codex项目" in message
    assert '[fieldid="projectName"]' in message


def test_playwright_runtime_resolves_pointer_receiving_form_field_root(monkeypatch) -> None:
    runtime = _build_runtime()
    stale_root = SimpleNamespace(is_visible=lambda timeout=0: True)
    active_root = SimpleNamespace(is_visible=lambda timeout=0: True)
    stale_input = object()
    active_input = object()

    class _Candidates:
        def count(self) -> int:
            return 2

        def nth(self, index: int):
            return [stale_root, active_root][index]

    class _Page(_FakePage):
        def locator(self, selector: str):
            return _Candidates()

    runtime._page = _Page()
    monkeypatch.setattr(
        runtime,
        "_resolve_fill_locator_from_root",
        lambda root: active_input if root is active_root else stale_input,
    )
    monkeypatch.setattr(runtime, "_receives_pointer_events", lambda locator: locator is active_input)

    bound = SimpleNamespace(
        candidate=SimpleNamespace(key="", fieldid="proName", data_field="proName"),
        runtime=SimpleNamespace(selector='[fieldid="proName"]'),
    )

    assert runtime._resolve_pointer_receiving_form_field_root(bound) is active_root


def test_playwright_runtime_fill_form_field_refreshes_pointer_root_even_when_binding_is_in_dialog(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    stale_root = object()
    active_root = object()
    stale_input = object()
    active_input = object()
    calls: list[object] = []

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: stale_root)
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: stale_input)
    monkeypatch.setattr(
        runtime,
        "_resolve_fill_locator_from_root",
        lambda root: active_input if root is active_root else stale_input,
    )
    monkeypatch.setattr(runtime, "_resolve_pointer_receiving_form_field_root", lambda bound: active_root, raising=False)
    monkeypatch.setattr(runtime, "_looks_like_switch_field", lambda root, bound: False)
    monkeypatch.setattr(runtime, "_looks_like_radio_field", lambda root, bound: False)
    monkeypatch.setattr(runtime, "_looks_like_choice_field", lambda root, bound: False)
    monkeypatch.setattr(runtime._popup_reference_module(), "looks_like_field", lambda root, bound: False)
    monkeypatch.setattr(runtime, "_set_text_field_value", lambda locator, value: calls.append(locator))
    monkeypatch.setattr(runtime, "_confirm_plain_field_value", lambda locator, value, bound: {"actual": str(value)})

    bound = SimpleNamespace(
        candidate=SimpleNamespace(
            key="field-key",
            fieldid="proName",
            data_field="proName",
            label="项目名称",
            component_name="YDFInput",
            raw={},
        ),
        runtime=SimpleNamespace(selector='[fieldid="proName"]', in_dialog=True),
    )

    runtime.fill_form_field(bound, "预制财政二级11")

    assert calls == [active_input]


def test_playwright_runtime_fill_form_popup_reference_prefers_field_owner_over_trigger(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    trigger_root = object()

    class _OwnerRoot:
        def evaluate(self, _script: str, *args: object) -> object:
            if args:
                return {"index": 0, "count": 1}
            return {"id": "foreground-owner", "fieldid": "", "dataFieldid": "", "uikey": ""}

    owner_root = _OwnerRoot()
    trigger_input = object()
    owner_input = object()
    selected: list[tuple[object, object]] = []

    monkeypatch.setattr(
        runtime,
        "_resolve_visible_locator",
        lambda selector: owner_root if "foreground-owner" in selector else trigger_root,
    )
    monkeypatch.setattr(
        runtime,
        "_resolve_fill_locator",
        lambda selector: owner_input if "foreground-owner" in selector else trigger_input,
    )
    monkeypatch.setattr(runtime, "_resolve_pointer_receiving_form_field_root", lambda _bound: trigger_root)
    monkeypatch.setattr(runtime, "_resolve_foreground_form_field_root", lambda _bound: owner_root)
    monkeypatch.setattr(
        runtime,
        "_resolve_fill_locator_from_root",
        lambda root: owner_input if root is owner_root else trigger_input,
    )
    monkeypatch.setattr(runtime._popup_reference_module(), "looks_like_field", lambda _root, _bound: True)
    monkeypatch.setattr(runtime, "_looks_like_switch_field", lambda _root, _bound: False)
    monkeypatch.setattr(runtime, "_looks_like_radio_field", lambda _root, _bound: False)
    _patch_popup_reference_select(monkeypatch, runtime, lambda root, fill, _value: selected.append((root, fill)))

    bound = SimpleNamespace(
        candidate=SimpleNamespace(
            key="purItemDirect",
            fieldid="purItemDirect",
            data_field="purItemCode",
            label="采购品目",
            component_name="YDFTableModalSelect",
            raw={},
        ),
        runtime=SimpleNamespace(
            selector='[data-ydf-browser-runtime-id="modal-button"]',
            fieldid="purItemDirect",
            in_dialog=True,
        ),
        contract_path={"applicability": "verified"},
    )

    runtime.fill_form_field(bound, {"match": {"column": "品目编码", "equals": "A02010105"}})

    assert selected == [(owner_root, owner_input)]


def test_playwright_runtime_fill_form_field_treats_date_picker_as_plain_input(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _Input:
        def __init__(self) -> None:
            self.value = ""

        def fill(self, value: str) -> None:
            self.value = value
            calls.append(f"fill:{value}")

        def press(self, key: str, timeout: int = 0) -> None:
            calls.append(f"press:{key}")

        def input_value(self, timeout: int = 0) -> str:
            return self.value

    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: _Input())
    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: object())
    monkeypatch.setattr(
        runtime,
        "_set_date_field_value",
        lambda locator, value: (setattr(locator, "value", value), calls.append(f"date:{value}")),
    )

    bound = SimpleNamespace(
        candidate=SimpleNamespace(component_name="YDFDatePicker"),
        runtime=SimpleNamespace(selector='[fieldid="proEndTime"]', role="textbox", tag_name="input", name="YDFDatePicker"),
    )

    runtime.fill_form_field(bound, "2026-12-31")

    assert calls == ["date:2026-12-31"]


def test_playwright_runtime_fill_form_field_confirms_year_date_picker_backfill(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _Input:
        def input_value(self, timeout: int = 0) -> str:
            return "2026"

        def text_content(self, timeout: int = 0) -> str:
            return ""

        def get_attribute(self, name: str, timeout: int = 0) -> str:
            return ""

        def press(self, key: str, timeout: int = 0) -> None:
            calls.append(f"press:{key}")

    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: _Input())
    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: object())
    monkeypatch.setattr(runtime, "_set_date_field_value", lambda locator, value: calls.append(f"date:{value}"))

    bound = SimpleNamespace(
        candidate=SimpleNamespace(label="设立年度", component_name="YDFDatePicker"),
        runtime=SimpleNamespace(selector='[fieldid="setupYear"]', role="textbox", tag_name="input", name="YDFDatePicker"),
    )

    result = runtime.fill_form_field(bound, "2026")

    assert result["actual"] == "2026"
    assert calls == ["date:2026"]


def test_playwright_runtime_fill_form_field_routes_date_range_before_plain_date(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []
    root = object()
    fill_locator = object()

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: root)
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: fill_locator)
    monkeypatch.setattr(runtime, "_resolve_foreground_form_field_root", lambda bound: None)
    monkeypatch.setattr(runtime, "_resolve_form_field_root_by_label_position", lambda bound: None)
    monkeypatch.setattr(runtime, "_narrow_form_field_root", lambda current_root, bound: current_root)
    monkeypatch.setattr(runtime, "_looks_like_switch_field", lambda current_root, bound: False)
    monkeypatch.setattr(runtime, "_looks_like_radio_field", lambda current_root, bound: False)
    monkeypatch.setattr(
        runtime,
        "_set_date_field_value",
        lambda locator, value: (_ for _ in ()).throw(AssertionError("date range must not use plain date setter")),
    )
    monkeypatch.setattr(
        runtime,
        "_set_date_range_field_value",
        lambda current_root, locator, value, bound: calls.append(
            f"range:{value}:{current_root is root}:{locator is fill_locator}"
        )
        or {"actual": value, "confirmed": True},
        raising=False,
    )

    bound = SimpleNamespace(
        candidate=SimpleNamespace(label="对账起止日期", component_name="YDFDateRange"),
        runtime=SimpleNamespace(selector='[uikey="rangeDate"]', role=None, tag_name="div", name="YDFDateRange"),
    )

    result = runtime.fill_form_field(bound, "2026-01-01~2026-01-12")

    assert calls == ["range:2026-01-01~2026-01-12:True:True"]
    assert result == {"actual": "2026-01-01~2026-01-12", "confirmed": True}


def test_parse_date_range_value_accepts_spaces_and_normalizes() -> None:
    assert runtime_module._parse_date_range_value("2026-01-01 ~ 2026-01-12") == (
        "2026-01-01",
        "2026-01-12",
        "2026-01-01~2026-01-12",
    )


def test_playwright_runtime_fill_form_field_uses_switch_control_for_ydf_switch(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _SwitchRoot:
        pass

    root = _SwitchRoot()

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: root)
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: object())
    monkeypatch.setattr(runtime, "_narrow_form_field_root", lambda current_root, bound: current_root)
    monkeypatch.setattr(runtime._popup_reference_module(), "looks_like_field", lambda current_root, bound: False)
    monkeypatch.setattr(runtime, "_looks_like_choice_field", lambda current_root, bound: False)
    monkeypatch.setattr(runtime, "_set_switch_field_value", lambda current_root, value: calls.append(f"switch:{value}"), raising=False)
    monkeypatch.setattr(runtime, "_set_text_field_value", lambda locator, value: calls.append(f"text:{value}"))

    bound = SimpleNamespace(
        candidate=SimpleNamespace(component_name="YDFSwitch", raw={}),
        runtime=SimpleNamespace(
            selector='[fieldid="isEnabled"]',
            role=None,
            tag_name="div",
            name="YDFSwitch",
        ),
    )

    runtime.fill_form_field(bound, "是")

    assert calls == ["switch:是"]


def test_playwright_runtime_fill_form_field_uses_radio_for_flat_refer_radio_options(
    monkeypatch,
) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []
    root = object()
    fill_locator = object()

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: root)
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: fill_locator)
    monkeypatch.setattr(runtime, "_resolve_foreground_form_field_root", lambda bound: None)
    monkeypatch.setattr(runtime, "_resolve_form_field_root_by_label_position", lambda bound: None)
    monkeypatch.setattr(runtime, "_narrow_form_field_root", lambda current_root, bound: current_root)
    monkeypatch.setattr(runtime._popup_reference_module(), "root_has_trigger", lambda current_root: False)
    monkeypatch.setattr(runtime, "_set_radio_field_value", lambda current_root, value: calls.append(f"radio:{value}"), raising=False)
    _patch_popup_reference_select(monkeypatch, runtime, lambda current_root, locator, value: calls.append(f"popup:{value}"))
    monkeypatch.setattr(runtime, "_select_query_choice", lambda current_root, locator, value: calls.append(f"choice:{value}"))
    monkeypatch.setattr(runtime, "_set_text_field_value", lambda locator, value: calls.append(f"text:{value}"))

    bound = SimpleNamespace(
        candidate=SimpleNamespace(component_name="YDFRadio", raw={"dataType": "refer"}),
        runtime=SimpleNamespace(
            selector='[fieldid="anonFlag"]',
            role=None,
            tag_name="div",
            name="YDFRadio",
        ),
    )

    runtime.fill_form_field(bound, "转办类")

    assert calls == ["radio:转办类"]


def test_playwright_runtime_set_radio_field_value_selects_non_boolean_refer_option_once(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()

    class _RadioOption:
        def __init__(self, root) -> None:
            self.root = root

        def click(self, timeout: int = 0) -> None:
            self.root.clicked = True
            self.root.click_count += 1

    class _RadioRoot:
        def __init__(self, states: list[dict[str, bool]]) -> None:
            self.states = iter(states)
            self.clicked = False
            self.click_count = 0

        def evaluate(self, _script: str, *_args):
            return next(self.states)

        def locator(self, _selector: str) -> _RadioOption:
            return _RadioOption(self)

    root = _RadioRoot(
        [
            {"found": True, "selected": False, "selector": '[data-ydf-browser-radio-target="x"]'},
            {"found": True, "selected": True},
            {"found": True, "selected": True},
            {"found": True, "selected": True},
        ]
    )

    runtime._set_radio_field_value(root, "转办类")
    runtime._set_radio_field_value(root, "转办类")

    assert root.clicked is True
    assert root.click_count == 1


def test_playwright_runtime_fill_form_field_keeps_plain_input_with_switch_descendant_as_text(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _InputRoot:
        def evaluate(self, _script: str, *_args) -> bool:
            return True

    root = _InputRoot()
    fill_locator = object()

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: root)
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: fill_locator)
    monkeypatch.setattr(runtime, "_resolve_foreground_form_field_root", lambda bound: None)
    monkeypatch.setattr(runtime, "_resolve_form_field_root_by_label_position", lambda bound: None)
    monkeypatch.setattr(runtime, "_narrow_form_field_root", lambda current_root, bound: current_root)
    monkeypatch.setattr(runtime._popup_reference_module(), "looks_like_field", lambda *_args: False)
    monkeypatch.setattr(runtime, "_looks_like_choice_field", lambda current_root, bound: False)
    monkeypatch.setattr(runtime, "_set_switch_field_value", lambda current_root, value: calls.append(f"switch:{value}"), raising=False)
    monkeypatch.setattr(runtime, "_set_text_field_value", lambda locator, value: calls.append(f"text:{value}:{locator is fill_locator}"))
    monkeypatch.setattr(runtime, "_confirm_plain_field_value", lambda locator, value, bound: {"actual": str(value)})

    bound = SimpleNamespace(
        candidate=SimpleNamespace(component_name="YDFInput", raw={}),
        runtime=SimpleNamespace(
            selector='[uikey="20240226184518671966082768024288"]',
            role=None,
            tag_name="div",
            name=None,
        ),
    )

    runtime.fill_form_field(bound, "12323232")

    assert calls == ["text:12323232:True"]


def test_playwright_runtime_fill_form_field_keeps_precise_bound_root(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    root = object()
    broadened_root = object()
    amount_input = object()
    summary_input = object()

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: root)
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: amount_input)
    monkeypatch.setattr(runtime, "_resolve_foreground_form_field_root", lambda bound: None)
    monkeypatch.setattr(runtime, "_resolve_form_field_root_by_label_position", lambda bound: None)
    monkeypatch.setattr(runtime, "_narrow_form_field_root", lambda current_root, bound: broadened_root)
    monkeypatch.setattr(
        runtime,
        "_resolve_fill_locator_from_root",
        lambda current_root: summary_input if current_root is broadened_root else amount_input,
    )
    monkeypatch.setattr(runtime._popup_reference_module(), "root_has_trigger", lambda current_root: False)
    monkeypatch.setattr(runtime, "_looks_like_choice_field", lambda current_root, bound: False)
    monkeypatch.setattr(runtime, "_set_text_field_value", lambda locator, value: calls.append(f"{value}:{locator is amount_input}"))
    monkeypatch.setattr(runtime, "_confirm_plain_field_value", lambda locator, value, bound: {"actual": str(value)})

    bound = SimpleNamespace(
        candidate=SimpleNamespace(component_name="YDFInputNumber", raw={}),
        runtime=SimpleNamespace(
            selector='[uikey="202304231403300007966741815109"]',
            role=None,
            tag_name="div",
            name=None,
        ),
        reasons=["template_key"],
    )

    runtime.fill_form_field(bound, "0.22")

    assert calls == ["0.22:True"]


def test_playwright_runtime_set_switch_field_value_clicks_only_when_state_differs(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    root = object()
    states = iter([False, True, True])
    clicks: list[str] = []

    monkeypatch.setattr(runtime, "_read_switch_field_state", lambda current_root: next(states), raising=False)
    monkeypatch.setattr(runtime, "_click_switch_field", lambda current_root: clicks.append("click"), raising=False)

    runtime._set_switch_field_value(root, "是")
    runtime._set_switch_field_value(root, "是")

    assert clicks == ["click"]


def test_playwright_runtime_click_switch_field_uses_playwright_click_for_marked_target() -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _SwitchTarget:
        def click(self, timeout: int = 0) -> None:
            calls.append(f"target-click:{timeout}")

    class _SwitchRoot:
        def evaluate(self, _script: str, *_args) -> str:
            calls.append("evaluate")
            return '[data-ydf-browser-switch-target="switch-1"]'

        def locator(self, selector: str) -> _SwitchTarget:
            calls.append(f"locator:{selector}")
            return _SwitchTarget()

        def click(self, timeout: int = 0) -> None:
            calls.append(f"root-click:{timeout}")

    runtime._click_switch_field(_SwitchRoot())

    assert calls == [
        "evaluate",
        'locator:[data-ydf-browser-switch-target="switch-1"]',
        "target-click:1000",
    ]


def test_playwright_runtime_click_switch_field_prefers_descendant_switch_over_form_root() -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _SwitchTarget:
        def click(self, timeout: int = 0) -> None:
            calls.append(f"target-click:{timeout}")

    class _SwitchRoot:
        def evaluate(self, script: str, *_args) -> str:
            calls.append("evaluate")
            if "rootIsSwitchLike" not in script or "isSwitchContainer" not in script:
                return '[data-ydf-browser-switch-target="form-root"]'
            return '[data-ydf-browser-switch-target="switch-descendant"]'

        def locator(self, selector: str) -> _SwitchTarget:
            calls.append(f"locator:{selector}")
            return _SwitchTarget()

        def click(self, timeout: int = 0) -> None:
            calls.append(f"root-click:{timeout}")

    runtime._click_switch_field(_SwitchRoot())

    assert 'locator:[data-ydf-browser-switch-target="switch-descendant"]' in calls
    assert 'locator:[data-ydf-browser-switch-target="form-root"]' not in calls


def test_playwright_runtime_fill_query_field_does_not_press_escape(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()

    class _Keyboard:
        def press(self, key: str) -> None:
            raise AssertionError(f"unexpected keyboard press: {key}")

    runtime._page.keyboard = _Keyboard()

    class _ChoiceRoot:
        def click(self, timeout: int = 0) -> None:
            return

    class _ChoiceInput:
        def fill(self, value: str, timeout: int = 0) -> None:
            return

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: _ChoiceRoot())
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: _ChoiceInput())
    monkeypatch.setattr(runtime, "_looks_like_choice_field", lambda root, bound: True)
    monkeypatch.setattr(runtime, "_try_click_query_choice", lambda value: True)
    monkeypatch.setattr(runtime, "_wait_for_query_choice_dropdown_to_settle", lambda: None)

    bound = SimpleNamespace(runtime=SimpleNamespace(selector='[fieldid="query_apply_dept"]'))

    runtime.fill_query_field(bound, "001 办公室")


def test_playwright_runtime_choice_selection_confirms_dropdown_closed_after_blur(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    monkeypatch.setattr(runtime, "_wait_for_query_choice_dropdown_to_settle", lambda: calls.append("settle"))
    monkeypatch.setattr(runtime, "_choice_root_value_matches", lambda root, value: calls.append(f"match:{value}") or True)
    monkeypatch.setattr(runtime, "_blur_query_choice_root", lambda root: calls.append("blur"))
    monkeypatch.setattr(runtime, "_query_choice_dropdown_visible", lambda: calls.append("visible") or False)

    assert runtime._query_choice_selection_settled(object(), "男") is True
    assert calls == ["settle", "match:男", "blur", "settle", "visible"]


def test_playwright_runtime_strict_choice_settlement_rechecks_committed_value_after_blur(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    monkeypatch.setattr(runtime, "_wait_for_query_choice_dropdown_to_settle", lambda: calls.append("settle"))
    monkeypatch.setattr(runtime, "_choice_root_value_matches", lambda root, value: calls.append("filter-input-match") or True)
    monkeypatch.setattr(runtime, "_choice_root_visible_value_matches", lambda root, value: calls.append("visible-match") or True)
    monkeypatch.setattr(runtime, "_blur_query_choice_root", lambda root: calls.append("blur"))
    monkeypatch.setattr(runtime, "_query_choice_dropdown_visible", lambda: calls.append("closed") or False)
    monkeypatch.setattr(
        runtime,
        "_choice_root_committed_value_matches",
        lambda root, value: calls.append("committed-miss") or False,
        raising=False,
    )

    assert runtime._query_choice_selection_settled(object(), "办公费", require_value_match=True) is False
    assert calls == ["settle", "filter-input-match", "blur", "settle", "closed", "committed-miss"]


def test_playwright_runtime_blur_choice_root_dispatches_dom_blur_after_tab() -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _Root:
        def press(self, key: str, timeout: int = 0) -> None:
            calls.append(f"press:{key}")

        def evaluate(self, _script: str) -> None:
            calls.append("dom-blur")

    runtime._blur_query_choice_root(_Root())

    assert calls == ["press:Tab", "dom-blur"]


def test_playwright_runtime_detects_choice_dropdown_with_dom_visibility_fallback() -> None:
    runtime = _build_runtime()

    class _HiddenMatch:
        def is_visible(self, timeout: int = 0) -> bool:
            return False

    class _LocatorGroup:
        def count(self) -> int:
            return 1

        def nth(self, _index: int) -> _HiddenMatch:
            return _HiddenMatch()

    class _Page:
        frames: list[object] = []

        def locator(self, _selector: str) -> _LocatorGroup:
            return _LocatorGroup()

        def evaluate(self, _script: str, *_args) -> bool:
            return True

    runtime._page = _Page()

    assert runtime._query_choice_dropdown_visible() is True


def test_playwright_runtime_fill_query_field_filters_then_clicks_choice(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _ChoiceRoot:
        def click(self, timeout: int = 0) -> None:
            calls.append("open")

    class _ChoiceInput:
        def fill(self, value: str, timeout: int = 0) -> None:
            calls.append(f"fill:{value}")

    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: _ChoiceRoot())
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda selector: _ChoiceInput())
    monkeypatch.setattr(runtime, "_looks_like_choice_field", lambda root, bound: True)
    monkeypatch.setattr(runtime, "_try_click_query_choice", lambda value: calls.append(f"choose:{value}") or True)
    monkeypatch.setattr(runtime, "_wait_for_query_choice_dropdown_to_settle", lambda: calls.append("settle"))

    bound = SimpleNamespace(runtime=SimpleNamespace(selector='[fieldid="query_apply_dept"]'))

    runtime.fill_query_field(bound, "001 办公室")

    assert calls == ["open", "fill:001 办公室", "choose:001 办公室", "settle"]


def test_playwright_runtime_select_choice_prefers_structured_option_before_text_fallback(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _ChoiceRoot:
        def click(self, timeout: int = 0) -> None:
            calls.append("open")

    class _ChoiceInput:
        def fill(self, value: str, timeout: int = 0) -> None:
            calls.append(f"fill:{value}")

    monkeypatch.setattr(
        runtime,
        "_try_click_query_choice_text_fallback",
        lambda value: (_ for _ in ()).throw(AssertionError("text fallback should run after structured options")),
    )
    monkeypatch.setattr(runtime, "_try_click_query_choice_with_wait", lambda value, timeout_ms=1200: calls.append(f"option:{value}") or True)
    monkeypatch.setattr(runtime, "_query_choice_selection_settled", lambda root, value, **kwargs: calls.append(f"settled:{value}") or True)

    runtime._select_query_choice(_ChoiceRoot(), _ChoiceInput(), "男")

    assert calls == ["open", "fill:男", "option:男", "settled:男"]


def test_playwright_runtime_select_choice_can_pick_first_available(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    class _ChoiceRoot:
        def click(self, timeout: int = 0) -> None:
            calls.append("open")

    class _ChoiceInput:
        def fill(self, value: str, timeout: int = 0) -> None:
            calls.append(f"fill:{value}")

    monkeypatch.setattr(runtime, "_click_first_query_choice", lambda: calls.append("first") or True)
    monkeypatch.setattr(runtime, "_wait_for_query_choice_dropdown_to_settle", lambda: calls.append("settle"))

    runtime._select_query_choice(_ChoiceRoot(), _ChoiceInput(), {"first_available": True})

    assert calls == ["open", "first", "settle"]




















def test_build_query_choice_selectors_are_scoped_to_popups() -> None:
    selectors = build_query_choice_selectors("001 办公室")

    assert 'text="001 办公室"' not in selectors
    assert '.w-select-dropdown :text-is("001 办公室")' in selectors
    assert '.wui-select-dropdown :text-is("001 办公室")' in selectors
    assert selectors.index('.w-select-dropdown [class*="item"]:has-text("001 办公室")') < selectors.index(
        '.w-select-dropdown :text-is("001 办公室")'
    )
    assert all(
        "dropdown" in selector
        or "popup" in selector
        or "listbox" in selector
        or "select-item-option" in selector
        or "refer" in selector
        or "ref" in selector
        for selector in selectors
    )

def test_playwright_runtime_try_click_query_choice_skips_broad_click_after_tree_expand(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []
    context = object()

    def _expand_only(value: str, context=None) -> bool:
        calls.append(f"precise:{value}")
        runtime._last_query_choice_precise_action = "expanded"
        return False

    monkeypatch.setattr(runtime, "_all_search_contexts", lambda: [context])
    monkeypatch.setattr(runtime, "_try_click_precise_query_choice_tree_node", _expand_only, raising=False)
    monkeypatch.setattr(runtime, "_try_click_first", lambda selectors, context=None: calls.append("broad") or True)

    assert runtime._try_click_query_choice("办公费") is False
    assert calls == ["precise:办公费"]


def test_playwright_runtime_click_query_choice_target_uses_real_mouse_before_dom_fallback() -> None:
    runtime = _build_runtime()
    calls: list[str] = []

    class _Mouse:
        def move(self, x: float, y: float) -> None:
            calls.append(f"move:{x}:{y}")

        def down(self) -> None:
            calls.append("down")

        def up(self) -> None:
            calls.append("up")

    class _Page(_FakePage):
        def __init__(self) -> None:
            super().__init__()
            self.mouse = _Mouse()

    class _Target:
        def bounding_box(self, timeout: int = 0) -> dict[str, float]:
            calls.append(f"box:{timeout}")
            return {"x": 10, "y": 20, "width": 100, "height": 30}

        def evaluate(self, _script: str) -> None:
            calls.append("dom-click")

        def scroll_into_view_if_needed(self, timeout: int = 0) -> None:
            calls.append("scroll")

        def click(self, timeout: int = 0, force: bool = False) -> None:
            calls.append(f"playwright-click:{force}")

    runtime._page = _Page()
    assert runtime._click_query_choice_target_without_scroll(_Target()) is True
    assert calls == ["box:2000", "move:60.0:35.0", "down", "up"]


def test_playwright_runtime_precise_choice_detects_expanded_state_as_parent(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[object] = []

    class _Context:
        def evaluate(self, script: str, payload):
            calls.append(("script", "aria-expanded" in script, "querySelectorAll(selector)" in script))
            return {"action": "blocked", "selector": ""}

    monkeypatch.setattr(
        runtime,
        "_click_query_choice_target_without_scroll",
        lambda target: (_ for _ in ()).throw(AssertionError("parent node should not be clicked")),
    )

    assert runtime._try_click_precise_query_choice_tree_node("办公费", context=_Context()) is False
    assert calls == [("script", True, True)]
    assert runtime._last_query_choice_precise_action == "blocked"


def test_playwright_runtime_choice_text_fallback_skips_broad_click_after_precise_block(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []
    context = object()

    def _blocked(value: str, context=None) -> bool:
        calls.append(f"precise:{value}")
        runtime._last_query_choice_precise_action = "blocked"
        return False

    monkeypatch.setattr(runtime, "_all_search_contexts", lambda: [context])
    monkeypatch.setattr(runtime, "_try_click_precise_query_choice_tree_node", _blocked, raising=False)

    assert runtime._try_click_query_choice_text_fallback("办公费") is False
    assert calls == ["precise:办公费"]



def test_playwright_runtime_clicks_popup_text_choice_with_script_fallback(monkeypatch) -> None:
    runtime = _build_runtime()
    calls: list[tuple[str, str]] = []

    class _EvaluatePage:
        def evaluate(self, script: str, value: str) -> bool:
            calls.append((script, value))
            return True

    runtime._page = _EvaluatePage()
    monkeypatch.setattr(runtime, "_try_click_precise_query_choice_tree_node", lambda value, context=None: False)

    assert runtime._try_click_query_choice_text_fallback("099 老干部处") is True
    assert calls
    assert "document.querySelectorAll" in calls[0][0]
    assert "[class*=\"dropdown\"]" in calls[0][0]
    assert calls[0][1] == "099 老干部处"


def test_playwright_runtime_click_tree_node_retries_after_expanding(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    attempts = {"count": 0}
    expansions: list[str] = []

    def _try_click_first(_selectors: list[str]) -> bool:
        attempts["count"] += 1
        return attempts["count"] >= 2

    monkeypatch.setattr(runtime, "_try_click_first", _try_click_first)
    monkeypatch.setattr(runtime, "_expand_tree_until_visible", lambda label: expansions.append(label))

    runtime.click_tree_node("001 办公室")

    assert attempts["count"] == 2
    assert expansions == ["001 办公室"]


def test_playwright_runtime_click_tree_node_searches_before_expanding(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    searched = {"done": False}
    expansions: list[str] = []

    def _try_click_first(_selectors: list[str], context=None) -> bool:
        return searched["done"]

    def _try_search_tree_node(label: str, context=None) -> bool:
        searched["done"] = True
        return True

    monkeypatch.setattr(runtime, "_try_check_tree_node", lambda label, context=None: False, raising=False)
    monkeypatch.setattr(runtime, "_try_click_first", _try_click_first)
    monkeypatch.setattr(runtime, "_try_search_tree_node", _try_search_tree_node, raising=False)
    monkeypatch.setattr(runtime, "_expand_tree_until_visible", lambda label, context=None: expansions.append(label))

    runtime.click_tree_node("流程管理")

    assert searched["done"] is True
    assert expansions == []


def test_playwright_runtime_click_tree_node_falls_back_when_search_misses(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    attempts = {"count": 0}
    searches: list[str] = []
    expansions: list[str] = []

    def _try_click_first(_selectors: list[str], context=None) -> bool:
        attempts["count"] += 1
        return attempts["count"] >= 3

    monkeypatch.setattr(runtime, "_try_check_tree_node", lambda label, context=None: False, raising=False)
    monkeypatch.setattr(runtime, "_try_click_first", _try_click_first)
    monkeypatch.setattr(runtime, "_try_search_tree_node", lambda label, context=None: searches.append(label) or False, raising=False)
    monkeypatch.setattr(runtime, "_expand_tree_until_visible", lambda label, context=None: expansions.append(label))

    runtime.click_tree_node("流程管理")

    assert searches == ["流程管理"]
    assert expansions == ["流程管理"]


def test_playwright_runtime_click_tree_node_keeps_node_interactions_in_strict_tree_scope(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    strict_tree = object()
    search_scope = object()
    expanded = False
    outside_clicks: list[str] = []
    searches: list[object] = []
    expansions: list[tuple[str, object]] = []

    def _tree_search_context(_fieldid: str, *, include_search_scope: bool = False):
        return search_scope if include_search_scope else strict_tree

    def _try_click_first(_selectors: list[str], context=None) -> bool:
        if context is search_scope:
            outside_clicks.append("41 基本存款账户")
            return True
        assert context is strict_tree
        return expanded

    def _try_search_tree_node(_label: str, context=None) -> bool:
        searches.append(context)
        return False

    def _expand_tree_until_visible(label: str, context=None) -> None:
        nonlocal expanded
        expanded = True
        expansions.append((label, context))

    monkeypatch.setattr(runtime, "_tree_search_context", _tree_search_context)
    monkeypatch.setattr(runtime, "_try_check_tree_node", lambda label, context=None: False)
    monkeypatch.setattr(runtime, "_try_click_first", _try_click_first)
    monkeypatch.setattr(runtime, "_try_search_tree_node", _try_search_tree_node)
    monkeypatch.setattr(runtime, "_expand_tree_until_visible", _expand_tree_until_visible)

    runtime.click_tree_node("41 基本存款账户", tree_fieldid="account_tree")

    assert outside_clicks == []
    assert searches == [search_scope]
    assert expansions == [("41 基本存款账户", strict_tree)]


def test_playwright_runtime_click_tree_node_falls_back_to_strict_tree_when_search_scope_fails(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    strict_tree = object()
    expanded = False
    searches: list[object] = []

    def _tree_search_context(_fieldid: str, *, include_search_scope: bool = False):
        if include_search_scope:
            raise RuntimeError("search scope unavailable")
        return strict_tree

    def _try_click_first(_selectors: list[str], context=None) -> bool:
        assert context is strict_tree
        return expanded

    def _expand_tree_until_visible(_label: str, context=None) -> None:
        nonlocal expanded
        assert context is strict_tree
        expanded = True

    monkeypatch.setattr(runtime, "_tree_search_context", _tree_search_context)
    monkeypatch.setattr(runtime, "_try_check_tree_node", lambda label, context=None: False)
    monkeypatch.setattr(runtime, "_try_click_first", _try_click_first)
    monkeypatch.setattr(runtime, "_try_search_tree_node", lambda label, context=None: searches.append(context) or False)
    monkeypatch.setattr(runtime, "_expand_tree_until_visible", _expand_tree_until_visible)

    runtime.click_tree_node("41 基本存款账户", tree_fieldid="account_tree")

    assert searches == [strict_tree]


def test_playwright_runtime_click_tree_node_uses_checkbox_after_search(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    searched = {"done": False}
    checked: list[str] = []

    def _try_check_tree_node(label: str, context=None) -> bool:
        if searched["done"]:
            checked.append(label)
            return True
        return False

    def _try_search_tree_node(label: str, context=None) -> bool:
        searched["done"] = True
        return True

    monkeypatch.setattr(runtime, "_try_check_tree_node", _try_check_tree_node, raising=False)
    monkeypatch.setattr(
        runtime,
        "_try_click_first",
        lambda _selectors, context=None: (
            pytest.fail("tree.select should use the node checkbox after search") if searched["done"] else False
        ),
    )
    monkeypatch.setattr(runtime, "_try_search_tree_node", _try_search_tree_node, raising=False)
    monkeypatch.setattr(
        runtime,
        "_expand_tree_until_visible",
        lambda label, context=None: pytest.fail("search hit should not expand tree nodes"),
    )

    runtime.click_tree_node("流程管理")

    assert checked == ["流程管理"]


def test_playwright_runtime_tree_search_context_falls_back_to_unique_visible_tree_root() -> None:
    class _MissingFieldidLocator(_FakeMatch):
        def wait_for(self, state: str = "visible", timeout: int = 0) -> None:
            raise RuntimeError("missing fieldid")

    class _MissingFieldidContext:
        def __init__(self) -> None:
            self.marked = False
            self.root = _FakeMatch(True)

        def locator(self, selector: str) -> _FakeLocatorGroup:
            if selector == '[fieldid="domain_tree"], [data-fieldid="domain_tree"]':
                return _FakeLocatorGroup([_MissingFieldidLocator(False)])
            if selector.startswith('[data-ydf-browser-tree-search-root="tree-root-'):
                return _FakeLocatorGroup([self.root])
            return _FakeLocatorGroup([])

        def evaluate(self, _script: str, marker: str) -> str:
            self.marked = True
            return f'[data-ydf-browser-tree-search-root="{marker}"]'

    context = _MissingFieldidContext()
    runtime = _build_runtime()
    runtime._page = SimpleNamespace(frames=[], locator=context.locator)
    runtime._all_search_contexts = lambda: [context]  # type: ignore[method-assign]

    root = runtime._tree_search_context("domain_tree", include_search_scope=True)

    assert context.marked is True
    assert root is context.root


def test_playwright_runtime_tree_search_context_expands_exact_tree_to_search_scope() -> None:
    class _TreeLocator(_FakeMatch):
        def wait_for(self, state: str = "visible", timeout: int = 0) -> None:
            return

        def evaluate(self, _script: str, marker: str) -> str:
            return f'[data-ydf-browser-tree-search-root="{marker}"]'

    class _TreeContext:
        def __init__(self) -> None:
            self.tree = _TreeLocator(True)
            self.scope = _FakeMatch(True)

        def locator(self, selector: str) -> _FakeLocatorGroup:
            if selector == '[fieldid="domain_tree"], [data-fieldid="domain_tree"]':
                return _FakeLocatorGroup([self.tree])
            if selector.startswith('[data-ydf-browser-tree-search-root="tree-scope-'):
                return _FakeLocatorGroup([self.scope])
            return _FakeLocatorGroup([])

    context = _TreeContext()
    runtime = _build_runtime()
    runtime._page = SimpleNamespace(frames=[], locator=context.locator)
    runtime._all_search_contexts = lambda: [context]  # type: ignore[method-assign]

    root = runtime._tree_search_context("domain_tree", include_search_scope=True)

    assert root is context.scope


def test_playwright_runtime_tree_search_context_does_not_escape_lcd_tree_component() -> None:
    class _TreeLocator(_FakeMatch):
        def wait_for(self, state: str = "visible", timeout: int = 0) -> None:
            return

        def evaluate(self, script: str, marker: str) -> str:
            if "LCDTree" in script and "lcd-tree" in script:
                return ""
            return f'[data-ydf-browser-tree-search-root="{marker}"]'

    class _TreeContext:
        def __init__(self) -> None:
            self.tree = _TreeLocator(True)
            self.outside_scope = _FakeMatch(True)

        def locator(self, selector: str) -> _FakeLocatorGroup:
            if selector == '[fieldid="domain_tree"], [data-fieldid="domain_tree"]':
                return _FakeLocatorGroup([self.tree])
            if selector.startswith('[data-ydf-browser-tree-search-root="tree-scope-'):
                return _FakeLocatorGroup([self.outside_scope])
            return _FakeLocatorGroup([])

    context = _TreeContext()
    runtime = _build_runtime()
    runtime._page = SimpleNamespace(frames=[], locator=context.locator)
    runtime._all_search_contexts = lambda: [context]  # type: ignore[method-assign]

    root = runtime._tree_search_context("domain_tree", include_search_scope=True)

    assert root is context.tree


def test_playwright_runtime_select_tree_context_uses_tree_click_flow(monkeypatch) -> None:
    runtime = _build_runtime()
    calls: list[str] = []

    monkeypatch.setattr(runtime, "click_tree_node", lambda label: calls.append(f"tree:{label}"))

    runtime.select_tree_node("101001 秘书处")

    assert calls == ["tree:101001 秘书处"]


def test_playwright_runtime_click_tree_node_prefers_checkbox_when_present(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    checked: list[tuple[str, object]] = []

    monkeypatch.setattr(
        runtime,
        "_try_check_tree_node",
        lambda label, context=None: checked.append((label, context)) or True,
        raising=False,
    )
    monkeypatch.setattr(
        runtime,
        "_try_click_first",
        lambda _selectors, context=None: pytest.fail("tree.select should click the node checkbox before label text"),
    )

    runtime.click_tree_node("360000001 南昌市")

    assert checked == [("360000001 南昌市", None)]


class _FakeTreeShortcutTarget:
    def __init__(self) -> None:
        self.clicks: list[dict[str, object]] = []

    def click(self, timeout: int = 0, force: bool = False) -> None:
        self.clicks.append({"timeout": timeout, "force": force})


class _FakeTreeShortcutRoot:
    def __init__(self, results: list[dict[str, str]]) -> None:
        self.results = list(results)
        self.evaluated_payloads: list[dict[str, object]] = []
        self.waited = False
        self.targets: dict[str, _FakeTreeShortcutTarget] = {}

    def wait_for(self, state: str = "visible", timeout: int = 0) -> None:
        self.waited = True

    def evaluate(self, _script: str, payload: dict[str, object]) -> dict[str, str]:
        self.evaluated_payloads.append(payload)
        if self.results:
            return self.results.pop(0)
        return {"action": "none", "label": "", "selector": ""}

    def locator(self, selector: str) -> _FakeLocatorGroup:
        target = self.targets.setdefault(selector, _FakeTreeShortcutTarget())
        return _FakeLocatorGroup([target])


class _FakeTreeShortcutPage:
    def __init__(self, tree_root: _FakeTreeShortcutRoot, fieldid: str = "topTree") -> None:
        self.tree_root = tree_root
        self.fieldid = fieldid
        self.frames: list[object] = []
        self.waits: list[int] = []

    def locator(self, selector: str) -> _FakeLocatorGroup:
        if selector == f'[fieldid="{self.fieldid}"], [data-fieldid="{self.fieldid}"]':
            return _FakeLocatorGroup([self.tree_root])
        return _FakeLocatorGroup([])

    def wait_for_timeout(self, timeout: int) -> None:
        self.waits.append(timeout)


def test_playwright_runtime_select_tree_root_returns_selected_label_and_clicks_target() -> None:
    root = _FakeTreeShortcutRoot(
        [{"action": "select", "label": "001 办公室", "selector": '[data-ydf-browser-tree-shortcut-target="root"]'}]
    )
    page = _FakeTreeShortcutPage(root)
    runtime = _build_runtime()
    runtime._page = page

    selected_label = runtime.select_tree_root(tree_fieldid="topTree")

    assert selected_label == "001 办公室"
    assert root.waited is True
    assert root.evaluated_payloads == [{"node": "root", "marker": root.evaluated_payloads[0]["marker"]}]
    assert root.targets['[data-ydf-browser-tree-shortcut-target="root"]'].clicks == [{"timeout": 3000, "force": False}]
    assert page.waits == [1200]


def test_playwright_runtime_select_tree_root_keeps_checked_control_selected() -> None:
    root = _FakeTreeShortcutRoot(
        [{"action": "already_selected", "label": "360000001 南昌市", "selector": ""}]
    )
    page = _FakeTreeShortcutPage(root)
    runtime = _build_runtime()
    runtime._page = page

    selected_label = runtime.select_tree_root(tree_fieldid="topTree")

    assert selected_label == "360000001 南昌市"
    assert root.targets == {}
    assert page.waits == [1200]


def test_playwright_runtime_select_first_tree_leaf_expands_and_requeries_dom() -> None:
    root = _FakeTreeShortcutRoot(
        [
            {"action": "expand", "label": "101 综合司01", "selector": '[data-ydf-browser-tree-shortcut-target="expand"]'},
            {"action": "select", "label": "101001 秘书处", "selector": '[data-ydf-browser-tree-shortcut-target="leaf"]'},
        ]
    )
    page = _FakeTreeShortcutPage(root)
    runtime = _build_runtime()
    runtime._page = page

    selected_label = runtime.select_first_tree_leaf(tree_fieldid="topTree")

    assert selected_label == "101001 秘书处"
    assert [payload["node"] for payload in root.evaluated_payloads] == ["first_leaf", "first_leaf"]
    assert root.targets['[data-ydf-browser-tree-shortcut-target="expand"]'].clicks == [{"timeout": 3000, "force": False}]
    assert root.targets['[data-ydf-browser-tree-shortcut-target="leaf"]'].clicks == [{"timeout": 3000, "force": False}]
    assert page.waits == [400, 1200]


def test_tree_shortcut_script_ignores_noop_leaf_switchers() -> None:
    assert "noop" in _TREE_SHORTCUT_TARGET_SCRIPT
    assert "treenode-leaf" in _TREE_SHORTCUT_TARGET_SCRIPT


def test_playwright_runtime_focus_row_by_text_uses_hover_flow(monkeypatch) -> None:
    runtime = _build_runtime()
    calls: list[str] = []

    monkeypatch.setattr(runtime, "hover_row_by_text", lambda text, column=None: calls.append(f"hover:{text}"))

    runtime.focus_table_row({"column": "项目代码", "equals": "360000241010010000039"})

    assert calls == ["hover:360000241010010000039"]


def test_playwright_runtime_select_table_row_clicks_matching_row_checkbox(monkeypatch) -> None:
    runtime = _build_runtime()
    calls: list[str] = []

    monkeypatch.setattr(runtime, "_click_row_checkbox_by_text", lambda text: calls.append(text))
    runtime._page = _FakePage()

    runtime.select_table_row({"equals": "360000241010010000039"})

    assert calls == ["360000241010010000039"]


def test_playwright_runtime_single_column_match_uses_column_row_lookup(monkeypatch) -> None:
    runtime = _build_runtime()
    row = object()
    clicked: list[object] = []

    monkeypatch.setattr(
        runtime,
        "_click_row_checkbox_by_text",
        lambda text, **_kwargs: pytest.fail("column match must not use whole-row text lookup"),
    )
    monkeypatch.setattr(
        runtime,
        "_find_visible_table_data_row_by_values",
        lambda values, **_kwargs: row if values == ["是"] else None,
    )
    monkeypatch.setattr(runtime, "_try_click_row_checkbox", lambda candidate: clicked.append(candidate) or True)

    runtime._click_row_checkbox_by_match_values(["是"], column="政府采购标识")

    assert clicked == [row]


def test_table_row_values_script_matches_wui_header_fieldid_to_cell_data_index() -> None:
    assert "identityEquivalent" in _TABLE_ROW_VALUES_SCRIPT
    assert "left.endsWith(`_${right}`)" in _TABLE_ROW_VALUES_SCRIPT
    assert "right.endsWith(`_${left}`)" in _TABLE_ROW_VALUES_SCRIPT


def test_table_row_values_script_reads_editable_cell_control_value() -> None:
    assert "input, textarea, select" in _TABLE_ROW_VALUES_SCRIPT
    assert "control.value" in _TABLE_ROW_VALUES_SCRIPT


@pytest.mark.parametrize("value", ["专家姓名0929092515660", "专家姓名"])
@pytest.mark.parametrize("operation", ["row", "column", "match"])
def test_table_values_preserve_business_text_matching_header(_popup_reference_page, value, operation) -> None:
    page = _popup_reference_page
    page.set_content(f'''
      <table fieldid="experts"><thead><tr><th fieldid="experts_expertName">专家姓名</th></tr></thead>
      <tbody><tr><td fieldid="experts_expertName">{value}</td></tr></tbody></table>
    ''')
    runtime = _build_runtime()
    runtime._page = page
    match = {"column": "专家姓名", "equals": value}
    if operation == "row":
        assert runtime.collect_table_row_values(match, ["专家姓名"], table_fieldid="experts") == {"专家姓名": value}
    elif operation == "column":
        assert runtime.collect_table_column_values("专家姓名", table_fieldid="experts") == [value]
    else:
        row = runtime._find_visible_table_data_row_by_values([value], column="专家姓名", table_fieldid="experts")
        assert row is not None
        assert row.inner_text() == value


def test_playwright_runtime_reports_column_match_row_without_selection_control(monkeypatch) -> None:
    runtime = _build_runtime()
    row = object()

    monkeypatch.setattr(runtime, "_find_visible_table_data_row_by_values", lambda values, **_kwargs: row)
    monkeypatch.setattr(runtime, "_try_click_row_checkbox", lambda _row: False)
    monkeypatch.setattr(
        runtime,
        "_expand_table_tree_until_values_visible",
        lambda values, column=None, **_kwargs: None,
    )
    monkeypatch.setattr(runtime, "_format_table_selection_failure", lambda message, **kwargs: f"{message}; {kwargs}")

    with pytest.raises(RuntimeError) as exc:
        runtime._click_row_checkbox_by_match_values(
            ["是"],
            column="政府采购标识",
            table="可用指标",
            table_fieldid="kyzb_table",
        )

    message = str(exc.value)
    assert "未确认表格行选中" in message
    assert "政府采购标识" in message
    assert "是" in message
    assert "kyzb_table" in message


def test_playwright_runtime_column_match_clicks_row_when_no_checkbox(monkeypatch) -> None:
    runtime = _build_runtime()
    row = object()
    clicked_rows: list[object] = []

    monkeypatch.setattr(runtime, "_find_visible_table_data_row_by_values", lambda values, **_kwargs: row)
    monkeypatch.setattr(runtime, "_try_click_row_checkbox", lambda _row: False)
    monkeypatch.setattr(
        runtime,
        "_try_click_table_row_for_selection",
        lambda candidate: clicked_rows.append(candidate) or True,
    )

    runtime._click_row_checkbox_by_match_values(
        ["财会监督1"],
        column="人员名称",
        table="内部检查小组",
        table_fieldid="2_2_tab",
    )

    assert clicked_rows == [row]


def test_playwright_runtime_column_match_fails_when_row_click_does_not_select(monkeypatch) -> None:
    runtime = _build_runtime()
    row = _FakeSelectableTableRow(visible=True, selectable=False, selected_after_click=False)

    monkeypatch.setattr(runtime, "_find_visible_table_data_row_by_values", lambda values, **_kwargs: row)
    monkeypatch.setattr(runtime, "_try_click_row_checkbox", lambda _row: False)
    monkeypatch.setattr(
        runtime,
        "_expand_table_tree_until_values_visible",
        lambda values, column=None, **_kwargs: None,
    )

    with pytest.raises(RuntimeError) as exc:
        runtime._click_row_checkbox_by_match_values(
            ["财会监督1"],
            column="人员名称",
            table="内部检查小组",
            table_fieldid="2_2_tab",
        )

    assert row.clicked is True
    assert "未确认表格行选中" in str(exc.value)


def test_playwright_runtime_select_table_row_clicks_composite_match_row_checkbox(monkeypatch) -> None:
    runtime = _build_runtime()
    calls: list[tuple[list[str], str | None]] = []

    monkeypatch.setattr(
        runtime,
        "_click_row_checkbox_by_match_values",
        lambda values, column=None, **_kwargs: calls.append((list(values), column)),
    )
    runtime._page = _FakePage()

    runtime.select_table_row(
        {
            "conditions": [
                {"column": "三级项目名称", "equals": "tztj513004"},
                {"column": "部门预算支出经济分类", "equals": "30101 基本工资"},
            ]
        }
    )

    assert calls == [(["tztj513004", "30101 基本工资"], "三级项目名称")]


def test_playwright_runtime_select_table_row_uses_all_match_conditions(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    first_row = _FakeSelectableTableRow(visible=True, text="财政一级项目ys06231632 111.00")
    target_row = _FakeSelectableTableRow(visible=True, text="财政一级项目ys06231632 888.00")
    context = _FakeCompositeMatchTableContext(first_row, target_row)

    monkeypatch.setattr(runtime, "_table_selection_context", lambda *args, **kwargs: context)

    runtime.select_table_row(
        {
            "conditions": [
                {"column": "一级项目名称", "equals": "财政一级项目ys06231632"},
                {"column": "指标金额", "equals": "888.00"},
            ]
        },
        table="table1",
        table_fieldid="table1",
    )

    assert first_row.checkbox is not None
    assert target_row.checkbox is not None
    assert first_row.checkbox.clicked is False
    assert target_row.checkbox.clicked is True
    assert runtime.last_table_selection_debug["row_text"] == "财政一级项目ys06231632 888.00"
    assert context.payloads[-1]["match"] == {
        "conditions": [
            {"column": "一级项目名称", "equals": "财政一级项目ys06231632"},
            {"column": "指标金额", "equals": "888.00"},
        ]
    }


def test_playwright_runtime_select_table_row_uses_all_match_conditions_after_reordering(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    first_row = _FakeSelectableTableRow(visible=True, text="财政一级项目ys06231632 111.00")
    target_row = _FakeSelectableTableRow(visible=True, text="财政一级项目ys06231632 888.00")
    context = _FakeCompositeMatchTableContext(first_row, target_row)

    monkeypatch.setattr(runtime, "_table_selection_context", lambda *args, **kwargs: context)

    runtime.select_table_row(
        {
            "conditions": [
                {"column": "指标金额", "equals": "888.00"},
                {"column": "一级项目名称", "equals": "财政一级项目ys06231632"},
            ]
        },
        table="table1",
        table_fieldid="table1",
    )

    assert first_row.checkbox is not None
    assert target_row.checkbox is not None
    assert first_row.checkbox.clicked is False
    assert target_row.checkbox.clicked is True
    assert runtime.last_table_selection_debug["row_text"] == "财政一级项目ys06231632 888.00"
    assert context.payloads[-1]["match"] == {
        "conditions": [
            {"column": "指标金额", "equals": "888.00"},
            {"column": "一级项目名称", "equals": "财政一级项目ys06231632"},
        ]
    }


def test_playwright_runtime_composite_row_selection_expands_until_all_values_visible(monkeypatch) -> None:
    runtime = _build_runtime()
    row = object()
    lookups = [None, row]
    expanded_values: list[tuple[list[str], str | None]] = []
    expanded_single: list[tuple[str, str | None]] = []
    clicked: list[object] = []

    monkeypatch.setattr(runtime, "_find_visible_table_data_row_by_values", lambda _values, **_kwargs: lookups.pop(0))
    monkeypatch.setattr(
        runtime,
        "_expand_table_tree_until_values_visible",
        lambda values, column=None, **_kwargs: expanded_values.append((list(values), column)),
        raising=False,
    )
    monkeypatch.setattr(
        runtime,
        "_expand_table_tree_until_row_visible",
        lambda text, column=None: expanded_single.append((text, column)),
    )
    monkeypatch.setattr(runtime, "_try_click_row_checkbox", lambda candidate: clicked.append(candidate) or True)

    runtime._click_row_checkbox_by_match_values(["tztj513004", "30101 基本工资"], column="三级项目名称")

    assert expanded_values == [(["tztj513004", "30101 基本工资"], "三级项目名称")]
    assert expanded_single == []
    assert clicked == [row]


@pytest.mark.parametrize(
    "values",
    [
        ["30101 基本工资", "UI自动化财务三级项目wdy"],
        ["UI自动化财务三级项目wdy", "30101 基本工资"],
    ],
)
def test_playwright_runtime_composite_tree_selection_does_not_use_first_value_as_ancestor_code(
    monkeypatch,
    values,
) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    candidate = _FakeTableTreeCandidate("988")
    clicked: list[str] = []
    found = False

    monkeypatch.setattr(
        runtime,
        "_find_visible_table_data_row_by_values",
        lambda _values, **_kwargs: object() if found else None,
    )
    monkeypatch.setattr(runtime, "_visible_table_tree_expanders", lambda _selector, context=None: [candidate])
    monkeypatch.setattr(runtime, "_visible_table_row_signature", lambda context=None: ("found",) if found else ("hidden",))
    monkeypatch.setattr(runtime, "_scroll_table_left", lambda context=None: False)
    monkeypatch.setattr(runtime, "_scroll_table_down", lambda context=None: False)

    def click(_candidate) -> bool:
        nonlocal found
        clicked.append(_candidate.code)
        found = True
        return True

    monkeypatch.setattr(runtime, "_click_table_tree_expander", click)

    runtime._expand_table_tree_until_values_visible(values, max_rounds=1)

    assert clicked == ["988"]
    assert runtime.last_table_tree_search["found"] is True


def test_playwright_runtime_composite_row_selection_passes_target_table_to_tree_expansion(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    row = object()
    lookups = [None, row]
    expanded: list[dict[str, object]] = []

    monkeypatch.setattr(runtime, "_find_visible_table_data_row_by_values", lambda _values, **_kwargs: lookups.pop(0))
    monkeypatch.setattr(
        runtime,
        "_expand_table_tree_until_values_visible",
        lambda values, **kwargs: expanded.append({"values": list(values), **kwargs}),
    )
    monkeypatch.setattr(runtime, "_try_click_row_checkbox", lambda candidate: candidate is row)

    runtime._click_row_checkbox_by_match_values(
        ["UI自动化财务三级项目wdy", "30101 基本工资"],
        column="三级项目名称",
        table="指标额度",
        table_fieldid="quota_table",
        table_columns=["三级项目名称", "部门预算支出经济分类"],
    )

    assert expanded == [
        {
            "values": ["UI自动化财务三级项目wdy", "30101 基本工资"],
            "column": "三级项目名称",
            "table": "指标额度",
            "table_fieldid": "quota_table",
            "table_columns": ["三级项目名称", "部门预算支出经济分类"],
            "match": None,
        }
    ]


def test_playwright_runtime_tree_expansion_scopes_helpers_to_target_table(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    context = object()
    helper_contexts: list[object] = []

    monkeypatch.setattr(runtime, "_table_selection_context", lambda *args, **kwargs: context)
    monkeypatch.setattr(runtime, "_find_visible_table_data_row_by_values", lambda _values, **_kwargs: None)
    monkeypatch.setattr(
        runtime,
        "_visible_table_tree_expanders",
        lambda _selector, context=None: helper_contexts.append(context) or [],
    )
    monkeypatch.setattr(runtime, "_scroll_table_left", lambda context=None: helper_contexts.append(context) or False)
    monkeypatch.setattr(runtime, "_scroll_table_down", lambda context=None: helper_contexts.append(context) or False)

    runtime._expand_table_tree_until_values_visible(
        ["UI自动化财务三级项目wdy", "30101 基本工资"],
        max_rounds=1,
        column="三级项目名称",
        table="指标额度",
        table_fieldid="quota_table",
        table_columns=["三级项目名称", "部门预算支出经济分类"],
    )

    assert helper_contexts
    assert all(item is context for item in helper_contexts)


def test_playwright_runtime_tree_expansion_refreshes_table_context_after_target_lookup(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    candidate = _FakeTableTreeCandidate("988")
    contexts: list[SimpleNamespace] = []
    clicked: list[str] = []
    found = False

    def resolve_context(*_args, **_kwargs):
        if contexts:
            contexts[-1].active = False
        context = SimpleNamespace(active=True)
        contexts.append(context)
        return context

    def find_target(_values, **_kwargs):
        resolve_context()
        return object() if found else None

    monkeypatch.setattr(runtime, "_table_selection_context", resolve_context)
    monkeypatch.setattr(runtime, "_find_visible_table_data_row_by_values", find_target)
    monkeypatch.setattr(
        runtime,
        "_visible_table_tree_expanders",
        lambda _selector, context=None: [candidate] if context and context.active else [],
    )
    monkeypatch.setattr(
        runtime,
        "_visible_table_row_signature",
        lambda context=None: ("found",) if found else ("hidden",),
    )
    monkeypatch.setattr(runtime, "_scroll_table_left", lambda context=None: False)
    monkeypatch.setattr(runtime, "_scroll_table_down", lambda context=None: False)

    def click(_candidate) -> bool:
        nonlocal found
        clicked.append(_candidate.code)
        found = True
        return True

    monkeypatch.setattr(runtime, "_click_table_tree_expander", click)

    runtime._expand_table_tree_until_values_visible(
        ["UI自动化财务三级项目wdy", "30101 基本工资"],
        max_rounds=1,
        table="指标额度",
        table_fieldid="quota_table",
    )

    assert clicked == ["988"]
    assert runtime.last_table_tree_search["found"] is True


def test_playwright_runtime_select_table_row_by_index_clicks_one_based_row(monkeypatch) -> None:
    runtime = _build_runtime()
    calls: list[int] = []

    monkeypatch.setattr(runtime, "_click_row_checkbox_by_index", lambda row_number: calls.append(row_number))
    runtime._page = _FakePage()

    runtime.select_table_row_by_index(1)

    assert calls == [1]


def test_playwright_runtime_select_table_rows_by_indices_clicks_each_row(monkeypatch) -> None:
    runtime = _build_runtime()
    calls: list[int] = []

    monkeypatch.setattr(runtime, "select_table_row_by_index", lambda row_number: calls.append(row_number))

    runtime.select_table_rows_by_indices([1, 3, 5])

    assert calls == [1, 3, 5]


def test_playwright_runtime_select_table_rows_by_indices_passes_table(monkeypatch) -> None:
    runtime = _build_runtime()
    calls: list[tuple[int, str | None, str | None]] = []

    monkeypatch.setattr(
        runtime,
        "select_table_row_by_index",
        lambda row_number, table=None, table_fieldid=None, table_columns=None: calls.append(
            (row_number, table, table_fieldid)
        ),
    )

    runtime.select_table_rows_by_indices([1, 2], table="可用指标")

    assert calls == [(1, "可用指标", None), (2, "可用指标", None)]


def test_playwright_runtime_select_table_rows_by_indices_passes_table_fieldid(monkeypatch) -> None:
    runtime = _build_runtime()
    calls: list[tuple[int, str | None, str | None]] = []

    monkeypatch.setattr(
        runtime,
        "select_table_row_by_index",
        lambda row_number, table=None, table_fieldid=None, table_columns=None: calls.append(
            (row_number, table, table_fieldid)
        ),
    )

    runtime.select_table_rows_by_indices([1, 2], table="可用指标", table_fieldid="budgetTable")

    assert calls == [(1, "可用指标", "budgetTable"), (2, "可用指标", "budgetTable")]


def test_playwright_runtime_select_table_rows_by_indices_passes_table_columns(monkeypatch) -> None:
    runtime = _build_runtime()
    calls: list[tuple[int, list[str] | None]] = []

    monkeypatch.setattr(
        runtime,
        "select_table_row_by_index",
        lambda row_number, table=None, table_fieldid=None, table_columns=None: calls.append(
            (row_number, table_columns)
        ),
    )

    runtime.select_table_rows_by_indices([1], table="可用指标", table_columns=["项目", "可用金额"])

    assert calls == [(1, ["项目", "可用金额"])]


def test_playwright_runtime_table_fieldid_root_selector_searches_child_frames() -> None:
    runtime = _build_runtime()

    class _Context:
        def __init__(self, result: dict[str, object]) -> None:
            self.result = result
            self.frames: list[object] = []

        def evaluate(self, script: str, payload: dict[str, object]) -> dict[str, object]:
            assert script == _TABLE_FIELDID_ROOT_SELECTOR_SCRIPT
            return self.result

    frame = _Context({"selector": '[data-ydf-browser-table-selection-root="frame"]', "fieldid": "kyzb_table"})
    page = _Context({"selector": "", "fieldids": ["kyzb_table"]})
    page.frames = [frame]
    runtime._page = page

    selector = runtime._resolve_table_selection_fieldid_root_selector(["kyzb_table"])

    assert selector == '[data-ydf-browser-table-selection-root="frame"]'
    assert runtime.last_table_selection_root == {"selector": selector, "fieldid": "kyzb_table"}


def test_playwright_runtime_select_all_table_rows_clicks_header_checkbox_not_rows() -> None:
    runtime = _build_runtime()
    header = _FakeHeaderCheckbox("unchecked")
    data_row = _FakeSelectableTableRow(visible=True)
    page = _FakeSelectableTablePage(
        {
            'thead input[type="checkbox"]': [header],
            "tbody tr": [data_row],
        }
    )
    runtime._page = page

    runtime.select_all_table_rows()

    assert header.clicks == [{"timeout": 3000, "force": False}]
    assert data_row.checkbox is not None
    assert data_row.checkbox.clicked is False
    assert page.waits == [300]


def test_playwright_runtime_select_all_table_rows_keeps_checked_header_selected() -> None:
    runtime = _build_runtime()
    header = _FakeHeaderCheckbox("checked")
    page = _FakeSelectableTablePage({'thead input[type="checkbox"]': [header]})
    runtime._page = page

    runtime.select_all_table_rows()

    assert header.clicks == []
    assert page.waits == [300]


def test_playwright_runtime_select_all_table_rows_clicks_mixed_header_checkbox() -> None:
    runtime = _build_runtime()
    header = _FakeHeaderCheckbox("mixed")
    page = _FakeSelectableTablePage({'thead input[type="checkbox"]': [header]})
    runtime._page = page

    runtime.select_all_table_rows()

    assert header.clicks == [{"timeout": 3000, "force": False}]
    assert page.waits == [300]


def test_playwright_runtime_select_all_table_rows_fails_without_header_checkbox() -> None:
    runtime = _build_runtime()
    runtime._page = _FakeSelectableTablePage({"tbody tr": [_FakeSelectableTableRow(visible=True)]})

    with pytest.raises(RuntimeError) as exc:
        runtime.select_all_table_rows()

    assert "未找到表头全选 checkbox" in str(exc.value)


def test_playwright_runtime_select_all_table_rows_scopes_to_named_table() -> None:
    runtime = _build_runtime()
    global_header = _FakeHeaderCheckbox("unchecked")
    scoped_header = _FakeHeaderCheckbox("unchecked")
    page = _FakeScopedSelectableTablePage(
        {'thead input[type="checkbox"]': [global_header]},
        {'thead input[type="checkbox"]': [scoped_header]},
        fieldid="detail_table",
    )
    runtime._page = page

    runtime.select_all_table_rows(table="可用指标", table_fieldid="detail_table", table_columns=["预算编制科目"])

    assert scoped_header.clicks == [{"timeout": 3000, "force": False}]
    assert global_header.clicks == []
    assert page.evaluated_payloads[0]["fieldids"] == ["detail_table_drag", "detail_table"]


def test_playwright_runtime_collect_table_headers_scopes_to_table_fieldid() -> None:
    runtime = _build_runtime()
    scoped_context = _FakeHeaderCollectionContext([["预算编制科目", "金额"]])
    page = _FakeHeaderCollectionPage([["全局列"]], scoped_context=scoped_context)
    runtime._page = page

    headers = runtime.collect_table_headers(
        table="可用指标",
        table_fieldid="detail_table",
        table_columns=["预算编制科目"],
    )

    assert headers == ["预算编制科目", "金额"]
    assert page.evaluated_payloads[0]["fieldids"] == ["detail_table_drag", "detail_table"]
    assert page.evaluated_payloads[0]["requireSelectableRows"] is False
    assert scoped_context.calls[0]["payload"] == {
        "table": "可用指标",
        "tableFieldid": "detail_table",
        "columns": ["预算编制科目"],
        "includeIdentity": True,
        "rewindToLeft": True,
        "rememberScrollLeft": True,
    }


def test_playwright_runtime_collect_table_headers_scrolls_to_collect_all() -> None:
    runtime = _build_runtime()
    page = _FakeHeaderCollectionPage(
        [["序号", "* 一级绩效指标"], ["序号", "* 一级绩效指标", "* 二级绩效指标", "* 三级绩效指标分值"]],
        scroll_results=[True, False],
    )
    runtime._page = page

    headers = runtime.collect_table_headers()

    assert headers == ["序号", "* 一级绩效指标", "* 二级绩效指标", "* 三级绩效指标分值"]
    assert [call["script"] for call in page.calls] == [
        _SCROLL_TABLE_HEADERS_RIGHT_SCRIPT,
        _TABLE_HEADERS_SCRIPT,
        _SCROLL_TABLE_HEADERS_RIGHT_SCRIPT,
        _TABLE_HEADERS_SCRIPT,
        _SCROLL_TABLE_HEADERS_RIGHT_SCRIPT,
        _SCROLL_TABLE_HEADERS_RIGHT_SCRIPT,
    ]
    assert page.waits == [250]


def test_playwright_runtime_collect_table_header_records_preserves_virtualized_same_name_identities() -> None:
    runtime = _build_runtime()
    runtime._page = _FakeHeaderCollectionPage(
        [
            [{"text": "数量", "identity": "data-index:requestedNum"}],
            [{"text": "数量", "identity": "data-index:approvedNum"}],
        ],
        scroll_results=[True, False],
    )

    records = runtime._collect_table_header_records()

    assert records == [
        ("数量", "data-index:requestedNum"),
        ("数量", "data-index:approvedNum"),
    ]


def test_playwright_runtime_collect_table_header_records_deduplicates_virtualized_same_identity() -> None:
    runtime = _build_runtime()
    runtime._page = _FakeHeaderCollectionPage(
        [
            [{"text": "数量", "identity": "data-index:num"}],
            [{"text": "*数量", "identity": "data-index:num"}],
        ],
        scroll_results=[True, False],
    )

    records = runtime._collect_table_header_records()

    assert records == [("数量", "data-index:num")]


def test_playwright_runtime_collect_table_headers_does_not_scroll_when_columns_are_complete() -> None:
    runtime = _build_runtime()
    page = _FakeHeaderCollectionPage([["序号", "* 一级绩效指标", "* 二级绩效指标"]], scroll_results=[True])
    runtime._page = page

    headers = runtime.collect_table_headers(
        table_columns=["序号", "一级绩效指标", "二级绩效指标"],
    )

    assert headers == ["序号", "* 一级绩效指标", "* 二级绩效指标"]
    assert [call["script"] for call in page.calls] == [
        _SCROLL_TABLE_HEADERS_RIGHT_SCRIPT,
        _TABLE_HEADERS_SCRIPT,
    ]
    assert page.waits == []


def test_playwright_runtime_collect_table_headers_restores_horizontal_scroll_position() -> None:
    runtime = _build_runtime()
    page = _FakeHeaderScrollRestorePage(
        [["序号", "* 一级绩效指标"], ["序号", "* 一级绩效指标", "* 二级绩效指标"]],
        scroll_results=[True, False],
        scroll_left=37,
    )
    runtime._page = page

    runtime.collect_table_headers()

    assert page.scroll_left == 37
    assert page.calls[0]["payload"]["rewindToLeft"] is True


def test_playwright_runtime_collect_table_headers_returns_empty_when_no_headers() -> None:
    runtime = _build_runtime()
    page = _FakeHeaderCollectionPage([[]], scroll_results=[False])
    runtime._page = page

    assert runtime.collect_table_headers() == []


def test_playwright_runtime_collect_table_column_values_scopes_to_table_fieldid() -> None:
    runtime = _build_runtime()
    scoped_context = _FakeTableValueCollectionContext(["400.00"])
    page = _FakeTableValueCollectionPage(scoped_context)
    runtime._page = page

    values = runtime.collect_table_column_values(
        "可授权金额",
        table="授权明细",
        table_fieldid="bg_table",
        table_columns=["被授权人名称", "可授权金额", "起始时间"],
    )

    assert values == ["400.00"]
    assert page.evaluated_payloads[0]["fieldids"] == ["bg_table_drag", "bg_table"]
    assert page.evaluated_payloads[0]["requireSelectableRows"] is False
    assert scoped_context.calls[0]["payload"] == {
        "column": "可授权金额",
        "table": "授权明细",
        "tableFieldid": "bg_table",
        "columns": ["被授权人名称", "可授权金额", "起始时间"],
    }


def test_playwright_runtime_collect_table_row_values_passes_table_identity_payload() -> None:
    runtime = _build_runtime()
    scoped_context = _FakeTableValueCollectionContext({"可授权金额": "400.00"})
    page = _FakeTableValueCollectionPage(scoped_context)
    runtime._page = page

    values = runtime.collect_table_row_values(
        {"column": "被授权人名称", "equals": "人员二十二"},
        ["可授权金额"],
        table="授权明细",
        table_fieldid="bg_table",
        table_columns=["被授权人名称", "可授权金额", "起始时间"],
    )

    assert values == {"可授权金额": "400.00"}
    assert scoped_context.calls[0]["payload"] == {
        "match": {"column": "被授权人名称", "equals": "人员二十二"},
        "matchValues": ["人员二十二"],
        "columns": ["可授权金额"],
        "table": "授权明细",
        "tableFieldid": "bg_table",
        "tableColumns": ["被授权人名称", "可授权金额", "起始时间"],
    }


def test_playwright_runtime_click_table_cell_link_passes_table_identity_payload() -> None:
    runtime = _build_runtime()
    scoped_context = _FakeTableCellLinkClickContext({"clicked": True, "clicked_text": "202600000000060"})
    page = _FakeTableCellLinkClickPage(scoped_context)
    runtime._page = page

    result = runtime.click_table_cell_link(
        column="任务编码",
        match={"column": "序号", "equals": 1},
        link_text="202600000000060",
        table="盘点任务",
        table_fieldid="inventory_table",
        table_columns=["序号", "任务编码", "任务名称"],
    )

    assert result == {"clicked": True, "clicked_text": "202600000000060"}
    assert page.evaluated_payloads[0]["fieldids"] == ["inventory_table_drag", "inventory_table"]
    assert scoped_context.calls[0]["payload"] == {
        "column": "任务编码",
        "linkText": "202600000000060",
        "match": {"column": "序号", "equals": 1},
        "matchValues": ["1"],
        "rowNumber": None,
        "table": "盘点任务",
        "tableFieldid": "inventory_table",
        "tableColumns": ["序号", "任务编码", "任务名称"],
    }


def test_playwright_runtime_click_table_cell_link_fails_without_link() -> None:
    runtime = _build_runtime()
    scoped_context = _FakeTableCellLinkClickContext(
        {"clicked": False, "reason": "cell-not-clickable", "column": "任务编码"}
    )
    runtime._page = _FakeTableCellLinkClickPage(scoped_context)

    with pytest.raises(RuntimeError) as exc:
        runtime.click_table_cell_link(
            column="任务编码",
            match={"column": "序号", "equals": 1},
            table_fieldid="inventory_table",
            table_columns=["序号", "任务编码"],
        )

    assert "任务编码" in str(exc.value)
    assert "cell-not-clickable" in str(exc.value)


def test_table_headers_script_scopes_split_headers_and_normalizes_precisely() -> None:
    assert "const rootArg = rootOrPayload instanceof HTMLElement ? rootOrPayload : null" in _TABLE_HEADERS_SCRIPT
    assert "const normalizeHeader = (value) => normalize(String(value || '').replace(/^[\\s*＊✱✳※]+/, ''))" in _TABLE_HEADERS_SCRIPT
    assert "const headerRoot = el.closest('.ant-table-header, .wui-table-header, .u-table-header" in _TABLE_HEADERS_SCRIPT
    assert "rootArg.contains(el)" in _TABLE_HEADERS_SCRIPT
    assert "const key = normalizeHeader(text)" in _TABLE_HEADERS_SCRIPT
    assert "header.includes(expected)" not in _TABLE_HEADERS_SCRIPT


def test_table_header_collection_uses_header_only_table_selection_mode() -> None:
    assert "const requireSelectableRows = payload && payload.requireSelectableRows !== false" in _TABLE_FIELDID_ROOT_SELECTOR_SCRIPT
    assert (
        "if (requireSelectableRows && selectableRows <= 0 && receivableRows <= 0 && columnsMatched <= 0) continue"
        in _TABLE_FIELDID_ROOT_SELECTOR_SCRIPT
    )
    assert "const requireSelectableRows = payload && payload.requireSelectableRows !== false" in _TABLE_SELECTION_ROOT_SELECTOR_SCRIPT
    assert "(!requireSelectableRows || item.selectableRows > 0)" in _TABLE_SELECTION_ROOT_SELECTOR_SCRIPT


def test_playwright_runtime_select_table_rows_by_indices_counts_visible_selectable_rows() -> None:
    runtime = _build_runtime()
    hidden_row = _FakeSelectableTableRow(visible=False)
    first_visible_row = _FakeSelectableTableRow(visible=True)
    second_visible_row = _FakeSelectableTableRow(visible=True)
    runtime._page = _FakeSelectableTablePage(
        {
            "tbody tr": [
                hidden_row,
                first_visible_row,
                second_visible_row,
            ]
        }
    )

    runtime.select_table_rows_by_indices([1, 2])

    assert hidden_row.checkbox is not None
    assert hidden_row.checkbox.clicked is False
    assert first_visible_row.checkbox is not None
    assert first_visible_row.checkbox.clicked is True
    assert second_visible_row.checkbox is not None
    assert second_visible_row.checkbox.clicked is True


def test_playwright_runtime_focus_table_row_by_index_skips_no_data_and_summary_rows() -> None:
    runtime = _build_runtime()

    class _HoverRow:
        def __init__(self, text: str) -> None:
            self.text = text
            self.hovered = False

        def is_visible(self, timeout: int = 0) -> bool:
            return True

        def inner_text(self, timeout: int = 0) -> str:
            return self.text

        def hover(self, timeout: int = 0) -> None:
            self.hovered = True

    class _HoverPage:
        def __init__(self, rows: list[_HoverRow]) -> None:
            self.rows = rows
            self.waits: list[int] = []

        def locator(self, selector: str) -> _FakeLocatorGroup:
            if selector == "tbody tr":
                return _FakeLocatorGroup(self.rows)
            return _FakeLocatorGroup([])

        def wait_for_timeout(self, timeout: int) -> None:
            self.waits.append(timeout)

    no_data = _HoverRow("暂无数据 点击上方查询条件搜索数据")
    data = _HoverRow("1 101 成本指标 90.0 101001 经济成本指标")
    summary = _HoverRow("小计 90.0")
    runtime._page = _HoverPage([no_data, data, summary])

    runtime.focus_table_row_by_index(1)

    assert no_data.hovered is False
    assert data.hovered is True
    assert summary.hovered is False


def test_playwright_runtime_focus_table_row_by_index_scopes_to_table_fieldid() -> None:
    runtime = _build_runtime()

    class _HoverRow:
        def __init__(self, text: str) -> None:
            self.text = text
            self.hovered = False

        def is_visible(self, timeout: int = 0) -> bool:
            return True

        def inner_text(self, timeout: int = 0) -> str:
            return self.text

        def evaluate(self, _script: str) -> bool:
            return True

        def hover(self, timeout: int = 0) -> None:
            self.hovered = True

    global_row = _HoverRow("1 背景列表行")
    scoped_row = _HoverRow("1 复印纸 A4 箱")
    page = _FakeScopedSelectableTablePage(
        {"tbody tr": [global_row]},
        {"tbody tr": [scoped_row]},
        fieldid="wzxx_table",
    )
    runtime._page = page

    runtime.focus_table_row_by_index(1, table="物资信息", table_fieldid="wzxx_table")

    assert global_row.hovered is False
    assert scoped_row.hovered is True
    assert page.evaluated_payloads[0]["fieldids"] == ["wzxx_table_drag", "wzxx_table"]


def test_playwright_runtime_focus_table_row_match_scopes_to_table_fieldid() -> None:
    runtime = _build_runtime()

    class _HoverRow:
        def __init__(self, text: str) -> None:
            self.text = text
            self.hovered = False

        def is_visible(self, timeout: int = 0) -> bool:
            return True

        def inner_text(self, timeout: int = 0) -> str:
            return self.text

        def hover(self, timeout: int = 0) -> None:
            self.hovered = True

    global_row = _HoverRow("1 复印纸 背景列表")
    scoped_row = _HoverRow("1 复印纸 A4 箱")
    page = _FakeScopedSelectableTablePage(
        {"tbody tr": [global_row]},
        {"tbody tr": [scoped_row]},
        fieldid="wzxx_table",
    )
    runtime._page = page

    runtime.focus_table_row({"equals": "复印纸"}, table="物资信息", table_fieldid="wzxx_table")

    assert global_row.hovered is False
    assert scoped_row.hovered is True
    assert page.evaluated_payloads[0]["fieldids"] == ["wzxx_table_drag", "wzxx_table"]


def test_playwright_runtime_select_table_row_by_index_scopes_to_named_table() -> None:
    runtime = _build_runtime()
    global_row = _FakeSelectableTableRow(visible=True)
    scoped_row = _FakeSelectableTableRow(visible=True)
    runtime._page = _FakeScopedSelectableTablePage(
        {"tbody tr": [global_row]},
        {"tbody tr": [scoped_row]},
    )

    runtime.select_table_row_by_index(1, table="可用指标")

    assert global_row.checkbox is not None
    assert scoped_row.checkbox is not None
    assert global_row.checkbox.clicked is False
    assert scoped_row.checkbox.clicked is True


def test_playwright_runtime_select_table_row_by_index_scoped_tbody_uses_plain_rows() -> None:
    runtime = _build_runtime()
    scoped_row = _FakeSelectableTableRow(visible=True)
    runtime._page = _FakeScopedSelectableTablePage(
        {"tbody tr": []},
        {"tr": [scoped_row]},
    )

    runtime.select_table_row_by_index(1, table="消费明细")

    assert scoped_row.checkbox is not None
    assert scoped_row.checkbox.clicked is True


def test_playwright_runtime_select_table_row_by_index_scoped_wrapper_prefers_tbody_rows() -> None:
    runtime = _build_runtime()
    header_row = _FakeSelectableTableRow(visible=True)
    data_row = _FakeSelectableTableRow(visible=True)
    runtime._page = _FakeScopedSelectableTablePage(
        {"tbody tr": []},
        {
            "tr": [header_row, data_row],
            "tbody tr": [data_row],
        },
        fieldid="budgetTable",
    )

    runtime.select_table_row_by_index(1, table="可用指标", table_fieldid="budgetTable")

    assert header_row.checkbox is not None
    assert data_row.checkbox is not None
    assert header_row.checkbox.clicked is False
    assert data_row.checkbox.clicked is True


def test_playwright_runtime_select_table_row_by_index_scopes_to_table_fieldid() -> None:
    runtime = _build_runtime()
    global_row = _FakeSelectableTableRow(visible=True)
    scoped_row = _FakeSelectableTableRow(visible=True)
    page = _FakeScopedSelectableTablePage(
        {"tbody tr": [global_row]},
        {"tr": [scoped_row]},
        fieldid="budgetTable",
    )
    runtime._page = page

    runtime.select_table_row_by_index(1, table="可用指标", table_fieldid="budgetTable")

    assert global_row.checkbox is not None
    assert scoped_row.checkbox is not None
    assert global_row.checkbox.clicked is False
    assert scoped_row.checkbox.clicked is True
    assert page.evaluated_payloads[0]["fieldids"] == ["budgetTable_drag", "budgetTable"]


def test_playwright_runtime_select_table_row_by_index_waits_for_delayed_business_row() -> None:
    runtime = _build_runtime()
    row = _FakeSelectableTableRow(visible=True)
    page = _FakeScopedSelectableTablePage({}, {}, fieldid="budgetTable")
    runtime._page = page

    def reveal_row(timeout: int) -> None:
        page.waits.append(timeout)
        page.scoped_context.rows_by_selector["tbody tr"] = [row]

    page.wait_for_timeout = reveal_row

    runtime.select_table_row_by_index(1, table="可用指标", table_fieldid="budgetTable")

    assert row.checkbox is not None
    assert row.checkbox.clicked is True
    assert page.waits[0] == 250


def test_playwright_runtime_select_table_row_by_index_does_not_fallback_from_fieldid_to_table_name() -> None:
    runtime = _build_runtime()
    named_row = _FakeSelectableTableRow(visible=True)
    runtime._page = _FakeFieldidFallbackTablePage(
        {"tbody tr": []},
        {"tbody tr": [named_row]},
    )

    with pytest.raises(RuntimeError) as exc:
        runtime.select_table_row_by_index(1, table="调出方", table_fieldid="detail_table")

    assert named_row.checkbox is not None
    assert named_row.checkbox.clicked is False
    assert "detail_table" in str(exc.value)


def test_playwright_runtime_select_table_row_by_index_records_actual_table_root_debug() -> None:
    runtime = _build_runtime()
    scoped_row = _FakeSelectableTableRow(visible=True)
    runtime._page = _FakeScopedSelectableTablePage(
        {"tbody tr": []},
        {"tbody tr": [scoped_row]},
        fieldid="budgetTable",
        root_info={"fieldid": "budgetTable", "source": "fieldid", "selectableRows": 1},
    )

    runtime.select_table_row_by_index(1, table="可用指标", table_fieldid="budgetTable")

    assert runtime.last_table_selection_debug is not None
    assert runtime.last_table_selection_debug["root_fieldid"] == "budgetTable"
    assert runtime.last_table_selection_debug["root_source"] == "fieldid"
    assert runtime.last_table_selection_debug["root_selectable_rows"] == 1


def test_playwright_runtime_select_table_row_by_index_prefers_foreground_fieldid_root() -> None:
    runtime = _build_runtime()
    background_row = _FakeSelectableTableRow(
        visible=True,
        selectable=True,
        text="1 背景旧表",
        receives_pointer=False,
    )
    foreground_row = _FakeSelectableTableRow(
        visible=True,
        selectable=False,
        text="1 调出方 33.00",
    )
    runtime._page = _FakeForegroundFieldidTablePage(
        {"tbody tr": [background_row]},
        {"tbody tr": [foreground_row]},
    )

    runtime.select_table_row_by_index(1, table="调出方", table_fieldid="table1")

    assert background_row.checkbox is not None
    assert background_row.checkbox.clicked is False
    assert foreground_row.clicked is True
    assert runtime.last_table_selection_debug is not None
    assert runtime.last_table_selection_debug["root_fieldid"] == "table1_drag"
    assert runtime.last_table_selection_debug["root_selectable_rows"] == 0


def test_playwright_runtime_select_table_row_by_index_clicks_scoped_data_row_without_checkbox() -> None:
    runtime = _build_runtime()
    global_row = _FakeSelectableTableRow(visible=True, selectable=True)
    scoped_row = _FakeSelectableTableRow(visible=True, selectable=False, text="1 单位收入 3,000.00")
    page = _FakeScopedSelectableTablePage(
        {"tbody tr": [global_row]},
        {"tbody tr": [scoped_row]},
        fieldid="dzkxxx_table",
    )
    runtime._page = page

    runtime.select_table_row_by_index(1, table="到账款项信息", table_fieldid="dzkxxx_table")

    assert global_row.checkbox is not None
    assert global_row.checkbox.clicked is False
    assert scoped_row.clicked is True
    assert page.evaluated_payloads[0]["fieldids"] == ["dzkxxx_table_drag", "dzkxxx_table"]


def test_playwright_runtime_select_table_row_by_index_fails_when_row_click_does_not_select() -> None:
    runtime = _build_runtime()
    scoped_row = _FakeSelectableTableRow(
        visible=True,
        selectable=False,
        text="1 单位收入 3,000.00",
        selected_after_click=False,
    )
    runtime._page = _FakeScopedSelectableTablePage(
        {"tbody tr": []},
        {"tbody tr": [scoped_row]},
        fieldid="dzkxxx_table",
    )

    with pytest.raises(RuntimeError) as exc:
        runtime.select_table_row_by_index(1, table="到账款项信息", table_fieldid="dzkxxx_table")

    assert scoped_row.clicked is True
    assert "未确认表格行选中" in str(exc.value)


def test_playwright_runtime_select_table_row_by_index_keeps_checkbox_priority() -> None:
    runtime = _build_runtime()
    scoped_row = _FakeSelectableTableRow(visible=True, selectable=True, text="1 单位收入 3,000.00")
    runtime._page = _FakeScopedSelectableTablePage(
        {"tbody tr": []},
        {"tbody tr": [scoped_row]},
        fieldid="dzkxxx_table",
    )

    runtime.select_table_row_by_index(1, table="到账款项信息", table_fieldid="dzkxxx_table")

    assert scoped_row.checkbox is not None
    assert scoped_row.checkbox.clicked is True
    assert scoped_row.clicked is False


def test_playwright_runtime_select_table_row_by_index_fallback_skips_empty_and_summary_rows() -> None:
    runtime = _build_runtime()
    no_data = _FakeSelectableTableRow(visible=True, selectable=False, text="暂无数据 点击上方查询条件搜索数据")
    summary = _FakeSelectableTableRow(visible=True, selectable=False, text="小计 3,000.00")
    data = _FakeSelectableTableRow(visible=True, selectable=False, text="1 单位收入 3,000.00")
    runtime._page = _FakeScopedSelectableTablePage(
        {"tbody tr": []},
        {"tbody tr": [no_data, summary, data]},
        fieldid="dzkxxx_table",
    )

    runtime.select_table_row_by_index(1, table="到账款项信息", table_fieldid="dzkxxx_table")

    assert no_data.clicked is False
    assert summary.clicked is False
    assert data.clicked is True


def test_playwright_runtime_rejects_search_no_results_placeholder_as_table_data_row(
    _popup_reference_page,
) -> None:
    runtime = _build_runtime()
    runtime._page = _popup_reference_page
    _popup_reference_page.set_content(
        '<table><tbody><tr><td class="wui-table-placeholder-cell">搜索无结果</td></tr></tbody></table>'
    )

    assert runtime._row_looks_like_table_data_row(_popup_reference_page.locator("tbody tr")) is False


def test_playwright_runtime_select_table_row_by_index_tr_fallback_skips_header_checkbox() -> None:
    runtime = _build_runtime()
    header = _FakeSelectableTableRow(visible=True, selectable=True, text="")
    data = _FakeSelectableTableRow(visible=True, selectable=False, text="1 单位收入 3,000.00")
    runtime._page = _FakeScopedSelectableTablePage(
        {"tbody tr": []},
        {"tbody tr": [], "tr": [header, data]},
        fieldid="dzkxxx_table",
    )

    runtime.select_table_row_by_index(1, table="到账款项信息", table_fieldid="dzkxxx_table")

    assert header.checkbox is not None
    assert header.checkbox.clicked is False
    assert data.clicked is True


def test_playwright_runtime_try_click_row_checkbox_uses_aligned_selection_column_when_row_has_no_checkbox() -> None:
    runtime = _build_runtime()
    checkbox = _FakeRowCheckbox()
    runtime._page = _FakeAlignedCheckboxPage(checkbox)
    row = _FakeAlignedCheckboxRow(marker="row")

    assert runtime._try_click_row_checkbox(row) is True

    assert checkbox.clicked is True
    assert runtime._page.selectors
    assert runtime._page.selectors[-1].startswith('[data-ydf-browser-row-checkbox-target="')


@pytest.mark.parametrize("scoped", [False, True])
def test_playwright_runtime_aligned_checkbox_respects_resolved_root(_popup_reference_page, scoped) -> None:
    page = _popup_reference_page
    token = 'data-ydf-table-scope-token="target"' if scoped else ''
    page.set_content(f"""
      <div class="ant-table" style="display:flex;align-items:center">
        <table {token}><tbody><tr><td style="height:30px">目标业务行</td></tr></tbody></table>
        <input type="checkbox">
      </div>
    """)
    runtime = _build_runtime()
    runtime._page = page
    assert runtime._try_click_aligned_row_checkbox(page.locator('tr')) is (not scoped)
    assert page.locator('input').is_checked() is (not scoped)


def test_playwright_runtime_try_click_row_checkbox_does_not_toggle_unconfirmed_candidates() -> None:
    runtime = _build_runtime()
    row = _FakeRepeatedCheckboxRow()

    assert runtime._try_click_row_checkbox(row) is False

    assert row.checkbox.click_count == 1
    assert runtime.last_table_selection_debug == {"strategy": "checkbox", "selected_after": False}


def test_playwright_runtime_try_click_table_row_for_selection_clicks_row_when_checkbox_is_absent() -> None:
    runtime = _build_runtime()
    row = _FakeAlignedCheckboxRow(marker=None)

    assert runtime._try_click_table_row_for_selection(row) is True

    assert row.clicked is True
    assert row.click_kwargs["position"] == {"x": 12, "y": 12}


def test_playwright_runtime_try_click_table_row_for_selection_requires_selected_state() -> None:
    runtime = _build_runtime()
    row = _FakeAlignedCheckboxRow(marker=None, selected_after_click=False)

    assert runtime._try_click_table_row_for_selection(row) is False

    assert row.clicked is True


def test_table_selection_root_script_penalizes_wrapping_multiple_table_roots() -> None:
    assert "const nestedTableRootCount = (root) =>" in _TABLE_SELECTION_ROOT_SELECTOR_SCRIPT
    assert "const selectableRowCount = (root) =>" in _TABLE_SELECTION_ROOT_SELECTOR_SCRIPT
    assert "score -= Math.min(420, nestedTableRootCount(root) * 120)" in _TABLE_SELECTION_ROOT_SELECTOR_SCRIPT
    assert "const requireSelectableRows = payload && payload.requireSelectableRows !== false" in _TABLE_SELECTION_ROOT_SELECTOR_SCRIPT
    assert "(!requireSelectableRows || item.selectableRows > 0)" in _TABLE_SELECTION_ROOT_SELECTOR_SCRIPT


def test_table_selection_root_script_scores_nearby_manifest_columns() -> None:
    assert "const columnNames = Array.isArray(payload && payload.columns)" in _TABLE_SELECTION_ROOT_SELECTOR_SCRIPT
    assert "const headerTextsNearRoot = (root) =>" in _TABLE_SELECTION_ROOT_SELECTOR_SCRIPT
    assert "if (columnScore > 0) score += 100 + columnScore" in _TABLE_SELECTION_ROOT_SELECTOR_SCRIPT
    assert "label.parentElement.contains(root)" not in _TABLE_SELECTION_ROOT_SELECTOR_SCRIPT


def test_table_selection_root_script_builds_split_table_cluster() -> None:
    assert "const splitTableClusterRoot = (root) =>" in _TABLE_SELECTION_ROOT_SELECTOR_SCRIPT
    assert "selected.clusterRoot.setAttribute('data-ydf-browser-table-selection-root', marker)" in (
        _TABLE_SELECTION_ROOT_SELECTOR_SCRIPT
    )


def test_table_fieldid_root_script_prefers_drag_fieldid() -> None:
    assert "payload && payload.fieldids" in _TABLE_FIELDID_ROOT_SELECTOR_SCRIPT
    assert "a.fieldidIndex - b.fieldidIndex" in _TABLE_FIELDID_ROOT_SELECTOR_SCRIPT
    assert "fieldid.endsWith('_drag')" in _TABLE_FIELDID_ROOT_SELECTOR_SCRIPT


def test_table_fieldid_root_script_builds_split_wui_table_cluster() -> None:
    assert "const splitTableClusterRoot = (root) =>" in _TABLE_FIELDID_ROOT_SELECTOR_SCRIPT
    assert "wui-table-header" in _TABLE_FIELDID_ROOT_SELECTOR_SCRIPT
    assert "wui-table-body" in _TABLE_FIELDID_ROOT_SELECTOR_SCRIPT
    assert "selected.clusterRoot.setAttribute('data-ydf-browser-table-selection-root', marker)" in _TABLE_FIELDID_ROOT_SELECTOR_SCRIPT


def test_table_fieldid_root_script_scores_expected_columns_before_checkbox_count() -> None:
    assert "const expectedColumns = Array.isArray(payload && payload.columns)" in _TABLE_FIELDID_ROOT_SELECTOR_SCRIPT
    assert "const matchedColumnCount = (root) =>" in _TABLE_FIELDID_ROOT_SELECTOR_SCRIPT
    assert "const columnsMatched = matchedColumnCount(clusterRoot)" in _TABLE_FIELDID_ROOT_SELECTOR_SCRIPT
    assert "b.columnsMatched - a.columnsMatched" in _TABLE_FIELDID_ROOT_SELECTOR_SCRIPT


def test_table_fieldid_root_script_scores_receivable_rows_before_checkbox_count() -> None:
    assert "const receivableRowCount = (root) =>" in _TABLE_FIELDID_ROOT_SELECTOR_SCRIPT
    assert "const receivableRows = receivableRowCount(clusterRoot)" in _TABLE_FIELDID_ROOT_SELECTOR_SCRIPT
    assert "b.receivableRows - a.receivableRows" in _TABLE_FIELDID_ROOT_SELECTOR_SCRIPT
    assert _TABLE_FIELDID_ROOT_SELECTOR_SCRIPT.index("b.receivableRows - a.receivableRows") < (
        _TABLE_FIELDID_ROOT_SELECTOR_SCRIPT.index("b.selectableRows - a.selectableRows")
    )


def test_table_column_values_script_reads_from_related_split_body_root() -> None:
    assert "const relatedTableBodies = (table, scope) =>" in _TABLE_COLUMN_VALUES_SCRIPT
    assert "for (const bodyRoot of relatedTableBodies(table, scope))" in _TABLE_COLUMN_VALUES_SCRIPT
    assert "const rows = dataRowsForTable(table, scope)" in _TABLE_COLUMN_VALUES_SCRIPT
    assert "const allCells = dataRowsForTable(table, scope).flatMap" in _TABLE_COLUMN_VALUES_SCRIPT


def test_table_column_values_script_filters_summary_rows() -> None:
    assert "const isSummaryRow = (row) =>" in _TABLE_COLUMN_VALUES_SCRIPT
    assert "/(summary|footer|total|subtotal|tfoot)/i.test(className)" in _TABLE_COLUMN_VALUES_SCRIPT
    assert "小计|合计|汇总|总计" in _TABLE_COLUMN_VALUES_SCRIPT
    assert "if (isSummaryRow(row)) continue;" in _TABLE_COLUMN_VALUES_SCRIPT
    assert "const allCells = dataRowsForTable(table, scope).flatMap" in _TABLE_COLUMN_VALUES_SCRIPT


def test_table_row_values_script_reuses_related_split_body_root() -> None:
    assert "const relatedTableBodies = (table, scope) =>" in _TABLE_ROW_VALUES_SCRIPT
    assert "const candidateRows = dataRowsForHeaders(headers, scope)" in _TABLE_ROW_VALUES_SCRIPT
    assert "for (const bodyRoot of relatedTableBodies(table, scope))" in _TABLE_ROW_VALUES_SCRIPT


def test_playwright_runtime_select_table_row_by_index_reports_visible_selectable_count() -> None:
    runtime = _build_runtime()
    first_visible_row = _FakeSelectableTableRow(visible=True)
    runtime._page = _FakeSelectableTablePage({"tbody tr": [first_visible_row]})

    with pytest.raises(RuntimeError) as exc:
        runtime.select_table_rows_by_indices([1, 2])

    assert "目标行号=2" in str(exc.value)
    assert "当前可见可勾选行数=1" in str(exc.value)


def test_playwright_runtime_hover_row_expands_table_tree_when_match_is_hidden(monkeypatch) -> None:
    runtime = _build_runtime()
    calls: list[str] = []

    def hover_visible(_text, column=None):
        calls.append("hover")
        if calls.count("hover") == 1:
            raise RuntimeError("hidden")

    monkeypatch.setattr(runtime, "_hover_visible_table_data_row", hover_visible)
    monkeypatch.setattr(runtime, "_expand_table_tree_until_row_visible", lambda text, column=None: calls.append(f"expand:{text}"))
    runtime._page = _FakePage()

    runtime.hover_row_by_text("101001001")

    assert calls == ["hover", "expand:101001001", "hover"]


def test_playwright_runtime_focus_table_row_passes_match_column_to_hover(monkeypatch) -> None:
    runtime = _build_runtime()
    calls: list[tuple[str, str | None]] = []

    monkeypatch.setattr(runtime, "hover_row_by_text", lambda text, column=None: calls.append((text, column)))

    runtime.focus_table_row({"column": "支出范围说明", "equals": "验证没有编码规则的属性查找test"})

    assert calls == [("验证没有编码规则的属性查找test", "支出范围说明")]


def test_playwright_runtime_hover_row_ignores_false_positive_text_locator() -> None:
    runtime = _build_runtime()
    page = _FakeTableTreePage(expander_codes=[])
    page.false_positive_target_locator = True
    runtime._page = page

    runtime.hover_row_by_text("988988988")

    assert page.scrolls > 0
    assert page.hovered == ["988988988"]


def test_build_table_tree_expand_selectors_cover_wui_table_tree_icons() -> None:
    selectors = build_table_tree_expand_selectors()

    assert any("wui-table-row-expand-icon-collapsed" in item for item in selectors)
    assert any("expand-icon-con" in item for item in selectors)
    assert any("uf-triangle-right" in item for item in selectors)
    assert any("tree-switcher" in item for item in selectors)


def test_playwright_runtime_table_tree_expander_uses_force_click_fallback() -> None:
    runtime = _build_runtime()
    calls: list[str] = []

    class ForceOnlyCandidate:
        def click(self, **kwargs):
            calls.append(f"click:{bool(kwargs.get('force'))}:{bool(kwargs.get('position'))}")
            if not kwargs.get("force"):
                raise RuntimeError("covered")

    assert runtime._click_table_tree_expander(ForceOnlyCandidate()) is True
    assert calls == ["click:False:True", "click:False:False", "click:True:False"]


def test_playwright_runtime_table_tree_expander_clicks_computed_icon_position() -> None:
    runtime = _build_runtime()
    calls: list[dict] = []

    class PositionedCandidate:
        def evaluate(self, _script):
            return {"x": 36, "y": 17}

        def click(self, **kwargs):
            calls.append(kwargs)

    assert runtime._click_table_tree_expander(PositionedCandidate()) is True
    assert calls == [{"position": {"x": 36, "y": 17}, "force": True, "timeout": 2000}]


def test_playwright_runtime_table_tree_expansion_prefers_matching_code_prefix(monkeypatch) -> None:
    runtime = _build_runtime()
    page = _FakeTableTreePage(expander_codes=["724", "988"])
    runtime._page = page
    clicked: list[str] = []

    def click(candidate):
        clicked.append(candidate.code)
        if candidate.code == "988":
            page.row_visible = True
        return True

    monkeypatch.setattr(runtime, "_click_table_tree_expander", click)

    runtime._expand_table_tree_until_row_visible("988988988", max_rounds=2)

    assert clicked == ["988"]


def test_playwright_runtime_table_tree_expansion_scrolls_when_visible_expanders_are_unrelated(monkeypatch) -> None:
    runtime = _build_runtime()
    page = _FakeTableTreePage(expander_codes=["101", "724"])
    runtime._page = page
    clicked: list[str] = []

    monkeypatch.setattr(runtime, "_click_table_tree_expander", lambda candidate: clicked.append(candidate.code) or True)

    runtime._expand_table_tree_until_row_visible("988988988", max_rounds=2)

    assert clicked == []
    assert page.scrolls > 0


def test_playwright_runtime_table_tree_expansion_ignores_false_positive_text_locator(monkeypatch) -> None:
    runtime = _build_runtime()
    page = _FakeTableTreePage(expander_codes=[])
    page.false_positive_target_locator = True
    runtime._page = page

    runtime._expand_table_tree_until_row_visible("988988988", max_rounds=2)

    assert page.scrolls == 1


def test_playwright_runtime_table_tree_expansion_scrolls_for_non_code_target() -> None:
    runtime = _build_runtime()
    page = _FakeTableTreePage(expander_codes=[])
    runtime._page = page

    runtime._expand_table_tree_until_row_visible("验证没有编码规则的属性查找test", max_rounds=2)

    assert page.scrolls > 0


def test_table_tree_leading_code_ignores_embedded_digits() -> None:
    assert _leading_code("101 综合司01") == "101"
    assert _leading_code("tztj513004") == ""


def test_playwright_runtime_table_tree_expansion_retries_unexpanded_visible_node(monkeypatch) -> None:
    runtime = _build_runtime()
    page = _FakeTableTreePage(expander_codes=["383"])
    runtime._page = page
    clicked: list[str] = []

    monkeypatch.setattr(runtime, "_click_table_tree_expander", lambda candidate: clicked.append(candidate.code) or True)
    monkeypatch.setattr(runtime, "_scroll_table_down", lambda context=None: False)

    runtime._expand_table_tree_until_row_visible("验证没有编码规则的属性查找test", max_rounds=2)

    assert clicked == ["383", "383"]


def test_playwright_runtime_select_table_row_stops_retrying_stalled_expander(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    candidate = _FakeTableTreeCandidate("普通表格行")
    clicked: list[str] = []
    dispatched: list[str] = []

    monkeypatch.setattr(runtime, "_table_selection_context", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(runtime, "_find_visible_table_data_row_by_values", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runtime, "_find_visible_table_data_row", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runtime, "_visible_table_tree_expanders", lambda _selector, context=None: [candidate])
    monkeypatch.setattr(runtime, "_visible_table_row_signature", lambda context=None: ("unchanged",))
    monkeypatch.setattr(runtime, "_scroll_table_left", lambda context=None: False)
    monkeypatch.setattr(runtime, "_scroll_table_down", lambda context=None: False)
    monkeypatch.setattr(
        runtime,
        "_click_table_tree_expander",
        lambda item: clicked.append(item.code) or True,
    )
    monkeypatch.setattr(
        runtime,
        "_dispatch_table_tree_expander_click",
        lambda item: dispatched.append(item.code) or True,
    )
    monkeypatch.setattr(runtime, "_table_tree_expander_still_collapsed", lambda *_args: True)
    monkeypatch.setattr(runtime, "_format_table_selection_failure", lambda message, **_kwargs: message)

    with pytest.raises(RuntimeError, match="未找到匹配表格行"):
        runtime.select_table_row(
            {"column": "资金往来对象名称", "equals": "不存在的资金往来对象"},
            table="表格",
            table_fieldid="BAS_FUND_COUNTERPART_TABLE",
        )

    assert clicked == ["普通表格行", "普通表格行"]
    assert dispatched == ["普通表格行", "普通表格行"]
    assert runtime.last_table_tree_search["expanded"] == 0
    assert runtime.last_table_tree_search["found"] is False


def test_playwright_runtime_table_tree_expansion_continues_after_stalled_candidate_limit(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    stalled = _FakeTableTreeCandidate("无进展候选")
    stalled_duplicate = _FakeTableTreeCandidate("无进展候选")
    next_candidate = _FakeTableTreeCandidate("有效候选")
    clicked: list[str] = []
    found = False

    monkeypatch.setattr(
        runtime,
        "_find_visible_table_data_row",
        lambda *_args, **_kwargs: object() if found else None,
    )
    monkeypatch.setattr(
        runtime,
        "_visible_table_tree_expanders",
        lambda _selector, context=None: [stalled, stalled_duplicate, next_candidate],
    )
    monkeypatch.setattr(
        runtime,
        "_visible_table_row_signature",
        lambda context=None: ("found",) if found else ("unchanged",),
    )
    monkeypatch.setattr(runtime, "_scroll_table_down", lambda context=None: False)

    def click(candidate) -> bool:
        nonlocal found
        clicked.append(candidate.code)
        if candidate is next_candidate:
            found = True
        return True

    monkeypatch.setattr(runtime, "_click_table_tree_expander", click)
    monkeypatch.setattr(runtime, "_dispatch_table_tree_expander_click", lambda _candidate: True)
    monkeypatch.setattr(
        runtime,
        "_table_tree_expander_still_collapsed",
        lambda candidate, _key: candidate in (stalled, stalled_duplicate),
    )

    runtime._expand_table_tree_until_values_visible(["目标行"], max_rounds=2)

    assert clicked == ["无进展候选", "无进展候选", "有效候选"]
    assert runtime.last_table_tree_search["found"] is True


def test_playwright_runtime_table_tree_expansion_does_not_dispatch_when_click_reveals_target(monkeypatch) -> None:
    runtime = _build_runtime()
    page = _FakeTableTreePage(expander_codes=["988"])
    runtime._page = page
    dispatches: list[str] = []

    def click(candidate):
        page.row_visible = True
        return True

    def dispatch(candidate):
        dispatches.append(candidate.code)
        page.row_visible = False
        return True

    monkeypatch.setattr(runtime, "_click_table_tree_expander", click)
    monkeypatch.setattr(runtime, "_table_tree_expander_still_collapsed", lambda _candidate, _key: True)
    monkeypatch.setattr(runtime, "_dispatch_table_tree_expander_click", dispatch)

    runtime._expand_table_tree_until_row_visible("988988988", max_rounds=1)

    assert page.row_visible is True
    assert dispatches == []
    assert runtime.last_table_tree_search["found"] is True


def test_table_row_values_script_supports_split_header_and_body_tables() -> None:
    assert "replace(/^[\\s*＊✱✳※]+/" in _TABLE_ROW_VALUES_SCRIPT
    assert "rootOrPayload instanceof HTMLElement" in _TABLE_ROW_VALUES_SCRIPT
    assert "tableFieldid" in _TABLE_ROW_VALUES_SCRIPT
    assert "dataField" in _TABLE_ROW_VALUES_SCRIPT
    assert "identityMatches" in _TABLE_ROW_VALUES_SCRIPT
    assert "const candidateRows = dataRowsForHeaders(headers, scope)" in _TABLE_ROW_VALUES_SCRIPT
    assert "if (!candidateRows.length) candidateRows.push(...scopedRows)" in _TABLE_ROW_VALUES_SCRIPT


def test_table_column_values_script_uses_identity_and_scoped_payload() -> None:
    assert "payload.column" in _TABLE_COLUMN_VALUES_SCRIPT
    assert "rootOrPayload instanceof HTMLElement" in _TABLE_COLUMN_VALUES_SCRIPT
    assert "tableFieldid" in _TABLE_COLUMN_VALUES_SCRIPT
    assert "dataField" in _TABLE_COLUMN_VALUES_SCRIPT
    assert "identityMatches" in _TABLE_COLUMN_VALUES_SCRIPT
    assert "document.querySelectorAll('td, [role=\"cell\"], .ant-table-cell" not in _TABLE_COLUMN_VALUES_SCRIPT


def test_playwright_runtime_click_toolbar_action_uses_visible_toolbar_button(monkeypatch) -> None:
    runtime = _build_runtime()
    calls: list[str] = []

    monkeypatch.setattr(runtime, "_resolve_visible_toolbar_action", lambda label: calls.append(label) or label)
    monkeypatch.setattr(runtime, "click", lambda bound: calls.append(bound))

    runtime.click_toolbar_action("保存")

    assert calls == ["保存", "保存"]


def test_playwright_runtime_toolbar_lookup_does_not_scroll_unrelated_buttons() -> None:
    unrelated = _FakeActionLocator("修改", in_table=True)
    toolbar = _FakeActionLocator("新增")
    runtime = _build_runtime()
    runtime._page = _FakeActionPage({"button": [unrelated, toolbar]})

    runtime.click_toolbar_action("新增")

    assert toolbar.clicked is True
    assert unrelated.scroll_calls == 0


def test_playwright_runtime_toolbar_lookup_ignores_same_label_table_buttons() -> None:
    row_action = _FakeActionLocator("新增", in_table=True)
    toolbar = _FakeActionLocator("新增")
    runtime = _build_runtime()
    runtime._page = _FakeActionPage({"button": [row_action, toolbar]})

    runtime.click_toolbar_action("新增")

    assert toolbar.clicked is True
    assert row_action.clicked is False
    assert row_action.scroll_calls == 0


def test_playwright_runtime_toolbar_fieldid_ignores_same_label_table_buttons() -> None:
    row_action = _FakeActionLocator("新增", in_table=True)
    toolbar = _FakeActionLocator("新增")
    runtime = _build_runtime()
    runtime._page = _FakeActionPage({'[fieldid="btn-add"]': [row_action, toolbar]})

    runtime.click_toolbar_action("新增", fieldid="btn-add")

    assert toolbar.clicked is True
    assert row_action.clicked is False
    assert row_action.scroll_calls == 0


def test_playwright_runtime_resolves_toolbar_action_by_exact_text_before_contains(monkeypatch) -> None:
    runtime = _build_runtime()
    calls: list[str] = []

    def exact(_selectors, label: str, **_kwargs) -> str:
        calls.append(f"exact:{label}")
        return "button >> nth=2"

    def contains(_selectors, **_kwargs):
        calls.append("contains")
        return 'button:has-text("保存")'

    monkeypatch.setattr(runtime, "_find_first_visible_exact_text_selector", exact)
    monkeypatch.setattr(runtime, "_find_first_visible_selector", contains)

    bound = runtime._resolve_visible_toolbar_action("保存")

    assert bound.runtime.selector == "button >> nth=2"
    assert calls == ["exact:保存"]


def test_playwright_runtime_click_toolbar_action_reveals_more_when_button_is_overflowed(monkeypatch) -> None:
    runtime = _build_runtime()
    calls: list[str] = []

    def _resolve(label: str):
        calls.append(f"resolve:{label}")
        if calls.count(f"resolve:{label}") == 1:
            raise RuntimeError("未找到可点击工具栏动作")
        return label

    monkeypatch.setattr(runtime, "_resolve_visible_toolbar_action", _resolve)
    monkeypatch.setattr(runtime, "_reveal_toolbar_overflow", lambda label=None: calls.append(f"more:{label}"))
    monkeypatch.setattr(runtime, "click", lambda bound: calls.append(f"click:{bound}"))
    monkeypatch.setattr(runtime, "_click_and_save_download", lambda bound: calls.append(f"download:{bound}"))

    runtime.click_toolbar_action("导出")

    assert calls == ["resolve:导出", "more:导出", "resolve:导出", "download:导出"]


def test_playwright_runtime_click_toolbar_action_waits_for_billrender_button(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    calls: list[str] = []

    def _resolve(label: str, **_kwargs):
        calls.append(f"resolve:{label}")
        if calls.count(f"resolve:{label}") == 1:
            raise RuntimeError("未找到可点击工具栏动作")
        return label

    monkeypatch.setattr(runtime, "_resolve_visible_toolbar_action", _resolve)
    monkeypatch.setattr(runtime, "click", lambda bound: calls.append(f"click:{bound}"))
    monkeypatch.setattr(
        runtime,
        "_reveal_toolbar_overflow",
        lambda *_args, **_kwargs: pytest.fail("按钮就绪后不应展开更多菜单"),
    )

    runtime.click_toolbar_action("新增")

    assert calls == ["resolve:新增", "resolve:新增", "click:新增"]


def test_playwright_runtime_normalizes_billrender_template_body_response() -> None:
    runtime = _build_runtime()
    payload = {"uidata": [{"divCode": "editRoot", "nodeType": "root"}], "pageId": "editRoot"}
    response = SimpleNamespace(
        url="https://example.yonyougov.top/yondif-ams-be/ytemplate/template/getTemplateBody",
        request=SimpleNamespace(method="POST"),
        json=lambda: payload,
    )

    runtime._capture_dynamic_template_response(response)

    assert runtime._dynamic_template_payload["data"]["uidata"][0]["divCode"] == "editRoot"
    assert runtime._dynamic_template_payload["_ydf_dynamic_template_source"] == "template_body"
    runtime._action_completion_context = {"target_page_id": "editRoot"}
    assert runtime._dynamic_template_payload_matches_action() is True


def test_playwright_runtime_click_toolbar_action_treats_export_excel_as_download(monkeypatch) -> None:
    runtime = _build_runtime()
    calls: list[str] = []

    monkeypatch.setattr(runtime, "_resolve_visible_toolbar_action", lambda label: calls.append(f"resolve:{label}") or label)
    monkeypatch.setattr(runtime, "click", lambda bound: calls.append(f"click:{bound}"))
    monkeypatch.setattr(runtime, "_click_and_save_download", lambda bound: calls.append(f"download:{bound}"))

    runtime.click_toolbar_action("导出excel")

    assert calls == ["resolve:导出excel", "download:导出excel"]


def test_playwright_runtime_click_toolbar_action_searches_child_frames_by_fieldid() -> None:
    runtime = _build_runtime()
    toolbar_button = _FakeMatch(visible=True)

    class _Context:
        def __init__(self, matches_by_selector: dict[str, list[_FakeMatch]], frames: list[object] | None = None) -> None:
            self.matches_by_selector = matches_by_selector
            self.frames = frames or []

        def locator(self, selector: str) -> _FakeLocatorGroup:
            return _FakeLocatorGroup(self.matches_by_selector.get(selector, []))

        def wait_for_timeout(self, *_args, **_kwargs) -> None:
            return

    frame = _Context({'[fieldid="kl_btn"]': [toolbar_button]})
    runtime._page = _Context({}, frames=[frame])

    runtime.click_toolbar_action("开立", fieldid="kl_btn")

    assert toolbar_button.clicked is True


def test_playwright_runtime_fieldid_action_skips_visible_button_blocked_by_footer() -> None:
    runtime = _build_runtime()

    class _ActionMatch:
        def __init__(self, *, receives_pointer: bool) -> None:
            self.receives_pointer = receives_pointer

        def is_visible(self, timeout: int = 0) -> bool:
            return True

        def bounding_box(self, timeout: int = 0) -> dict[str, int]:
            return {"x": 20, "y": 180, "width": 120, "height": 36}

        def evaluate(self, _script: str) -> bool:
            return self.receives_pointer

    class _Context:
        frames: list[object] = []

        def __init__(self, matches_by_selector: dict[str, list[_ActionMatch]]) -> None:
            self.matches_by_selector = matches_by_selector

        def locator(self, selector: str) -> _FakeLocatorGroup:
            return _FakeLocatorGroup(self.matches_by_selector.get(selector, []))

    runtime._page = _Context(
        {
            '[fieldid="bcbtdj_btn"]': [
                _ActionMatch(receives_pointer=False),
                _ActionMatch(receives_pointer=True),
            ]
        }
    )

    selector = runtime._find_first_visible_fieldid_action_selector("bcbtdj_btn")

    assert selector == '[fieldid="bcbtdj_btn"] >> nth=1'


class _PointerAwareActionMatch:
    def __init__(
        self,
        clickability: dict[str, object],
        *,
        text: str = "保存",
        click_error: Exception | None = None,
    ) -> None:
        self.clickability = clickability
        self.text = text
        self.click_error = click_error
        self.click_calls: list[dict[str, object]] = []
        self.scrolled = False

    def is_visible(self, timeout: int = 0) -> bool:
        return True

    def bounding_box(self, timeout: int = 0) -> dict[str, int]:
        return {"x": 20, "y": 180, "width": 120, "height": 36}

    def scroll_into_view_if_needed(self, timeout: int = 0) -> None:
        self.scrolled = True

    def evaluate(self, _script: str):
        return self.clickability

    def inner_text(self, timeout: int = 0) -> str:
        return self.text

    def get_attribute(self, _attr: str, timeout: int = 0) -> str:
        return ""

    def click(self, **kwargs) -> None:
        self.click_calls.append(dict(kwargs))
        if self.click_error is not None:
            raise self.click_error


class _PointerAwarePage:
    frames: list[object] = []

    def __init__(self, matches_by_selector: dict[str, list[_PointerAwareActionMatch]]) -> None:
        self.matches_by_selector = matches_by_selector
        self.waits: list[int] = []
        self.viewport_size = {"width": 1440, "height": 900}
        self.viewport_updates: list[dict[str, int]] = []

    def locator(self, selector: str) -> _FakeLocatorGroup:
        return _FakeLocatorGroup(self.matches_by_selector.get(selector, []))

    def wait_for_timeout(self, timeout: int) -> None:
        self.waits.append(timeout)

    def set_viewport_size(self, size: dict[str, int]) -> None:
        self.viewport_size = dict(size)
        self.viewport_updates.append(dict(size))


def test_playwright_runtime_finds_edge_click_point_when_center_is_intercepted() -> None:
    runtime = _build_runtime()
    locator = _PointerAwareActionMatch(
        {
            "clickable": True,
            "position": {"x": 8, "y": 18},
            "point": "left-middle",
        }
    )

    position = runtime._action_click_position(locator)

    assert position == {"x": 8, "y": 18}
    assert locator.scrolled is True


def test_playwright_runtime_samples_narrow_visible_left_edge() -> None:
    runtime = _build_runtime()

    class _LeftEdgeOnlyActionMatch(_PointerAwareActionMatch):
        def evaluate(self, script: str):
            if "left-edge" in script:
                return {
                    "clickable": True,
                    "position": {"x": 2, "y": 18},
                    "point": "left-edge",
                }
            return {
                "clickable": False,
                "blocked": True,
                "diagnostic": "left edge was not sampled",
            }

    locator = _LeftEdgeOnlyActionMatch({"clickable": False})

    position = runtime._action_click_position(locator)

    assert position == {"x": 2, "y": 18}


def test_playwright_runtime_centers_partially_visible_action_before_sampling() -> None:
    runtime = _build_runtime()

    class _ScrollSensitiveActionMatch(_PointerAwareActionMatch):
        def __init__(self) -> None:
            super().__init__({"clickable": False})
            self.centered = False

        def evaluate(self, script: str):
            if "scrollIntoView" in script and "inline" in script:
                self.centered = True
                return None
            if self.centered:
                return {
                    "clickable": True,
                    "position": {"x": 36, "y": 18},
                    "point": "center",
                }
            return {
                "clickable": False,
                "blocked": True,
                "diagnostic": "action was not horizontally centered",
            }

    locator = _ScrollSensitiveActionMatch()

    position = runtime._action_click_position(locator)

    assert position == {"x": 36, "y": 18}


def test_playwright_runtime_click_uses_reachable_position() -> None:
    runtime = _build_runtime()
    locator = _PointerAwareActionMatch(
        {
            "clickable": True,
            "position": {"x": 8, "y": 18},
            "point": "left-middle",
        }
    )
    runtime._page = _PointerAwarePage({'[fieldid="bc_btn"]': [locator]})
    bound = SimpleNamespace(runtime=SimpleNamespace(selector='[fieldid="bc_btn"]'))

    runtime.click(bound)

    assert locator.click_calls == [{"position": {"x": 8, "y": 18}}]
    assert runtime._page.waits == [600]


def test_playwright_runtime_click_expands_viewport_for_right_edge_action() -> None:
    runtime = _build_runtime()

    class _ViewportSensitiveActionMatch(_PointerAwareActionMatch):
        def __init__(self, page: _PointerAwarePage) -> None:
            super().__init__({"clickable": False})
            self.page = page

        def evaluate(self, script: str):
            if "scrollIntoView" in script:
                return None
            if self.page.viewport_size["width"] > 1440:
                return {
                    "clickable": True,
                    "position": {"x": 36, "y": 18},
                    "point": "center",
                }
            return {
                "clickable": False,
                "blocked": True,
                "diagnostic": "center: outside viewport | left-edge: div.workbenchRightSidebar-fixedBox",
            }

    page = _PointerAwarePage({})
    locator = _ViewportSensitiveActionMatch(page)
    page.matches_by_selector = {'[fieldid="bc_btn"]': [locator]}
    runtime._page = page
    bound = SimpleNamespace(runtime=SimpleNamespace(selector='[fieldid="bc_btn"]'))

    runtime.click(bound)

    assert page.viewport_updates[-1]["width"] > 1440
    assert locator.click_calls == [{"position": {"x": 36, "y": 18}}]


def test_playwright_runtime_fieldid_action_skips_fully_blocked_candidate() -> None:
    runtime = _build_runtime()
    runtime._page = _PointerAwarePage(
        {
            '[fieldid="bc_btn"]': [
                _PointerAwareActionMatch(
                    {
                        "clickable": False,
                        "blocked": True,
                        "diagnostic": "center: .workbenchRightSidebar-fixedBox",
                    }
                ),
                _PointerAwareActionMatch(
                    {
                        "clickable": True,
                        "position": {"x": 8, "y": 18},
                        "point": "left-middle",
                    }
                ),
            ]
        }
    )

    selector = runtime._find_first_visible_fieldid_action_selector("bc_btn", labels=["保存"], strict_label=True)

    assert selector == '[fieldid="bc_btn"] >> nth=1'


def test_playwright_runtime_fieldid_action_returns_blocked_label_match_for_diagnostic() -> None:
    runtime = _build_runtime()
    runtime._page = _PointerAwarePage(
        {
            '[fieldid="bc_btn"]': [
                _PointerAwareActionMatch(
                    {
                        "clickable": False,
                        "blocked": True,
                        "diagnostic": "center: .workbenchRightSidebar-fixedBox",
                    },
                    text="保存",
                ),
            ]
        }
    )

    selector = runtime._find_first_visible_fieldid_action_selector("bc_btn", labels=["保存"], strict_label=True)

    assert selector == '[fieldid="bc_btn"]'


@pytest.mark.parametrize(
    ("in_frame", "parent_blocked", "detail_available", "explicit_identity"),
    [
        (False, True, True, False),
        (True, True, True, False),
        (False, False, True, False),
        (False, True, False, False),
        (False, True, True, True),
    ],
)
def test_playwright_runtime_toolbar_click_uses_foreground_button_over_blocked_parent_fieldid(
    _popup_reference_page, in_frame, parent_blocked, detail_available, explicit_identity,
) -> None:
    runtime = _build_runtime()
    page = _popup_reference_page
    context = page
    if in_frame:
        page.set_content('<iframe style="width:100%;height:750px;border:0"></iframe>')
        context = page.frames[-1]
    context.set_content(
        """
        <button fieldid="parent-confirm" style="position:absolute;top:150px;left:30px"
          onclick="window.clicked='parent'">确定</button>
        <div class="wui-table-body" style="position:absolute;inset:100px 0 0;background:white"></div>
        <div class="lcd-btntoolbar" style="position:absolute;bottom:10px;right:10px">
          <button fieldid="detail-confirm" onclick="window.clicked='detail'">确定</button>
        </div>
        """
    )
    context.evaluate("window.clicked = null")
    if not parent_blocked:
        context.locator(".wui-table-body").evaluate("node => node.remove()")
    if not detail_available:
        context.locator('[fieldid="detail-confirm"]').evaluate("node => node.remove()")
    runtime._page = page

    if explicit_identity or not detail_available:
        with pytest.raises(RuntimeError, match="目标元素没有可接收 pointer event 的点击点:.*wui-table-body"):
            if explicit_identity:
                runtime.click_action_by_fieldid("parent-confirm")
            else:
                runtime.click_toolbar_action("确定", fieldid="parent-confirm")
        assert context.evaluate("window.clicked") is None
    else:
        runtime.click_toolbar_action("确定", fieldid="parent-confirm")
        assert context.evaluate("window.clicked") == ("detail" if parent_blocked else "parent")


def test_playwright_runtime_fieldid_action_prefers_later_blocked_duplicate_for_diagnostic() -> None:
    runtime = _build_runtime()
    runtime._page = _PointerAwarePage(
        {
            '[fieldid="bc_btn"]': [
                _PointerAwareActionMatch(
                    {
                        "clickable": False,
                        "blocked": True,
                        "diagnostic": "center: .wui-table-body",
                    },
                    text="保存",
                ),
                _PointerAwareActionMatch(
                    {
                        "clickable": False,
                        "blocked": True,
                        "diagnostic": "center: .workbenchRightSidebar-fixedBox",
                    },
                    text="保存",
                ),
            ]
        }
    )

    selector = runtime._find_first_visible_fieldid_action_selector("bc_btn", labels=["保存"], strict_label=True)

    assert selector == '[fieldid="bc_btn"] >> nth=1'


def test_playwright_runtime_click_fails_fully_blocked_action_without_force() -> None:
    runtime = _build_runtime()
    locator = _PointerAwareActionMatch(
        {
            "clickable": False,
            "blocked": True,
            "diagnostic": "center: .workbenchRightSidebar-fixedBox",
        },
        click_error=RuntimeError("center intercepted"),
    )
    runtime._page = _PointerAwarePage({'[fieldid="bc_btn"]': [locator]})
    bound = SimpleNamespace(runtime=SimpleNamespace(selector='[fieldid="bc_btn"]'))

    with pytest.raises(RuntimeError, match="workbenchRightSidebar-fixedBox"):
        runtime.click(bound)

    assert all(not call.get("force") for call in locator.click_calls)


def test_playwright_runtime_click_toolbar_action_uses_dynamic_dropdown_child(monkeypatch) -> None:
    runtime = _build_runtime()
    calls: list[str] = []

    monkeypatch.setattr(
        runtime,
        "_click_toolbar_dropdown_sub_action",
        lambda label, sub_label: calls.append(f"dropdown:{label}>{sub_label}"),
    )

    runtime.click_toolbar_action("新增", sub_label="租赁合同")

    assert calls == ["dropdown:新增>租赁合同"]


def test_playwright_runtime_click_row_action_prefers_visible_row_button(monkeypatch) -> None:
    runtime = _build_runtime()
    calls: list[str] = []

    class _BoundAction:
        class _Candidate:
            label = "详情"

        class _RuntimeNode:
            selector = '[fieldid="xq_btn"]'

        candidate = _Candidate()
        runtime = _RuntimeNode()

    monkeypatch.setattr(
        runtime,
        "_resolve_visible_row_action",
        lambda action_label: calls.append(action_label) or _BoundAction(),
    )
    monkeypatch.setattr(runtime, "click", lambda bound: calls.append(bound.candidate.label))

    runtime.click_row_action("详情")

    assert calls == ["详情", "详情"]


def test_playwright_runtime_resolves_row_action_with_row_scoped_selector(monkeypatch) -> None:
    runtime = _build_runtime()
    calls: list[list[str]] = []

    def row_scoped(selectors: list[str]) -> str:
        calls.append(selectors)
        return 'button:has-text("停用") >> nth=1'

    monkeypatch.setattr(runtime, "_find_first_visible_row_action_selector", row_scoped)

    bound = runtime._resolve_visible_row_action("停用")

    assert bound.runtime.selector == 'button:has-text("停用") >> nth=1'
    assert calls == [build_row_action_selectors("停用")]


def test_playwright_runtime_click_dialog_button_can_wait_for_download(monkeypatch) -> None:
    runtime = _build_runtime()
    calls: list[str] = []

    monkeypatch.setattr(runtime, "_find_first_visible_selector", lambda selectors: calls.append(selectors[0]) or "button.ok")
    monkeypatch.setattr(runtime, "_click_selector_and_save_download", lambda selector: calls.append(f"download:{selector}"))

    runtime.click_dialog_button("确定", expect_download=True)

    assert calls == ['.ant-modal:visible button:text-is("确定")', "download:button.ok"]


def test_playwright_runtime_import_upload_runs_standard_flow(monkeypatch, tmp_path) -> None:
    runtime = _build_runtime()
    file_path = tmp_path / "bad.xlsx"
    file_path.write_bytes(b"xlsx")
    calls: list[object] = []

    monkeypatch.setattr(runtime, "_open_import_sub_action", lambda label, sub_action: calls.append((label, sub_action)))
    monkeypatch.setattr(runtime, "_select_import_workbench_file", lambda files: calls.append(("select", files)))
    monkeypatch.setattr(runtime, "_submit_import_workbench", lambda: calls.append("submit"))
    monkeypatch.setattr(
        runtime,
        "_wait_for_import_results",
        lambda files, **_kwargs: calls.append(("wait", files))
        or [{"file": "bad.xlsx", "status": "failure", "message": "账号不能为空"}],
    )
    monkeypatch.setattr(runtime, "_close_import_progress_dialog", lambda: calls.append("close-progress"))

    result = runtime.import_upload("导入", [str(file_path)])

    assert calls == [
        ("导入", "导入"),
        ("select", [str(file_path)]),
        "submit",
        ("wait", [str(file_path)]),
        "close-progress",
    ]
    assert result["import_results"] == [{"file": "bad.xlsx", "status": "failure", "message": "账号不能为空"}]


def test_playwright_runtime_import_upload_uses_direct_file_button(monkeypatch, tmp_path) -> None:
    runtime = _build_runtime()
    file_path = tmp_path / "direct.xlsx"
    file_path.write_bytes(b"xlsx")
    calls: list[object] = []

    class _Chooser:
        def set_files(self, files) -> None:
            calls.append(("set_files", files))

    class _ChooserInfo:
        value = _Chooser()

        def __enter__(self):
            calls.append("expect_file_chooser")
            return self

        def __exit__(self, *_args) -> None:
            return None

    class _Page:
        def expect_file_chooser(self, timeout: int = 0):
            calls.append(("chooser_timeout", timeout))
            return _ChooserInfo()

    class _Locator:
        def click(self, timeout: int = 0) -> None:
            calls.append(("click", timeout))

    bound = _toolbar_bound_element(
        component_name="YDFileImportButton",
        raw={"props": {"justFile": "single"}},
    )
    monkeypatch.setattr(
        runtime,
        "_resolve_visible_toolbar_action",
        lambda label, fieldid=None, aliases=None: calls.append(("resolve", label, fieldid, aliases)) or bound,
    )
    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: calls.append(("locator", selector)) or _Locator())
    monkeypatch.setattr(runtime, "_require_page", lambda: _Page())
    monkeypatch.setattr(runtime, "_open_import_sub_action", lambda label, sub_action: calls.append(("unexpected-open", label, sub_action)))
    monkeypatch.setattr(runtime, "_select_import_workbench_file", lambda files: calls.append(("unexpected-select", files)))
    monkeypatch.setattr(runtime, "_submit_import_workbench", lambda: calls.append("unexpected-submit"))
    monkeypatch.setattr(
        runtime,
        "_wait_for_direct_import_network_result",
        lambda files, **_kwargs: calls.append(("wait-network", files))
        or {
            "import_results": [
                {"file": "direct.xlsx", "status": "submitted", "message": "后端已接收导入文件"}
            ],
            "network_requests": [{"url": "/ydf/custom/CustomImport", "method": "POST", "status": 200}],
        },
    )
    monkeypatch.setattr(
        runtime,
        "_wait_for_import_results",
        lambda files, **_kwargs: calls.append(("wait", files))
        or [{"file": "direct.xlsx", "status": "success", "message": "导入完成"}],
    )
    monkeypatch.setattr(runtime, "_close_import_progress_dialog", lambda: calls.append("close-progress"))

    result = runtime.import_upload(
        "导入",
        [str(file_path)],
        action_candidates=[
            {
                "fieldid": "import_btn",
                "label": "导入",
                "component_name": "YDFileImportButton",
                "raw": {"props": {"justFile": "single"}},
            }
        ],
    )

    assert calls == [
        ("resolve", "导入", "import_btn", ["导入", "import_btn"]),
        ("locator", '[fieldid="import_btn"]'),
        ("chooser_timeout", 10000),
        "expect_file_chooser",
        ("click", 3000),
        ("set_files", [str(file_path)]),
        ("wait-network", [str(file_path)]),
        ("wait", [str(file_path)]),
        "close-progress",
    ]
    assert result["import_results"] == [{"file": "direct.xlsx", "status": "success", "message": "导入完成"}]


def test_playwright_runtime_direct_import_upload_uses_notification_failure(monkeypatch, tmp_path) -> None:
    runtime = _build_runtime()
    file_path = tmp_path / "direct.xlsx"
    file_path.write_bytes(b"xlsx")
    calls: list[object] = []

    monkeypatch.setattr(
        runtime,
        "_resolve_visible_toolbar_action",
        lambda label, fieldid=None, aliases=None: _toolbar_bound_element(component_name="YDFileImportButton"),
    )
    monkeypatch.setattr(runtime, "_select_direct_import_file", lambda bound, files: calls.append(("select-direct", files)))
    monkeypatch.setattr(runtime, "collect_notifications", lambda timeout_ms=1500: [{"type": "error", "message": "项目代码不能为空！"}])
    monkeypatch.setattr(runtime, "_close_import_progress_dialog", lambda: calls.append("close-progress"))

    result = runtime.import_upload(
        "导入",
        [str(file_path)],
        action_candidates=[
            {
                "fieldid": "import_btn",
                "label": "导入",
                "component_name": "YDFileImportButton",
            }
        ],
    )

    assert calls == [("select-direct", [str(file_path)]), "close-progress"]
    assert result["import_results"] == [
        {"file": "direct.xlsx", "status": "failure", "message": "项目代码不能为空！"}
    ]


def test_playwright_runtime_import_upload_detects_generic_button_file_chooser(monkeypatch, tmp_path) -> None:
    runtime = _build_runtime()
    file_path = tmp_path / "direct.xlsx"
    file_path.write_bytes(b"xlsx")
    calls: list[object] = []

    class _Chooser:
        def set_files(self, files) -> None:
            calls.append(("set_files", files))

    class _ChooserInfo:
        value = _Chooser()

        def __enter__(self):
            calls.append("expect_file_chooser")
            return self

        def __exit__(self, *_args) -> None:
            return None

    class _Page:
        def expect_file_chooser(self, timeout: int = 0):
            calls.append(("chooser_timeout", timeout))
            return _ChooserInfo()

    class _Locator:
        def click(self, timeout: int = 0) -> None:
            calls.append(("click", timeout))

    bound = _toolbar_bound_element(label="导入并测算", component_name="YDFButton")
    monkeypatch.setattr(
        runtime,
        "_resolve_visible_toolbar_action",
        lambda label, fieldid=None, aliases=None: calls.append(("resolve", label, fieldid)) or bound,
    )
    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda selector: calls.append(("locator", selector)) or _Locator())
    monkeypatch.setattr(runtime, "_require_page", lambda: _Page())
    monkeypatch.setattr(
        runtime,
        "_wait_for_direct_import_network_result",
        lambda files, **_kwargs: {
            "import_results": [
                {"file": "direct.xlsx", "status": "submitted", "message": "后端已接收导入文件"}
            ],
            "network_requests": [{"url": "/ydf/custom/CustomImport", "method": "POST", "status": 200}],
        },
    )
    monkeypatch.setattr(runtime, "_close_import_progress_dialog", lambda: calls.append("close-progress"))

    result = runtime.import_upload(
        "导入并测算",
        [str(file_path)],
        fieldid="custom_import",
        expected_status="submitted",
        action_candidates=[
            {
                "fieldid": "custom_import",
                "label": "导入并测算",
                "component_name": "YDFButton",
            }
        ],
    )

    assert ("resolve", "导入并测算", "custom_import") in calls
    assert ("set_files", [str(file_path)]) in calls
    assert result["entry"] == "direct_file"
    assert result["import_results"][0]["status"] == "submitted"
    assert result["network_requests"] == [
        {"url": "/ydf/custom/CustomImport", "method": "POST", "status": 200}
    ]


def test_playwright_runtime_stops_direct_import_tracking_when_file_selection_fails(monkeypatch, tmp_path) -> None:
    runtime = _build_runtime()
    file_path = tmp_path / "direct.xlsx"
    file_path.write_bytes(b"xlsx")
    monkeypatch.setattr(runtime, "_resolve_direct_import_action", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(
        runtime,
        "_select_direct_import_file",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("chooser failed")),
    )

    with pytest.raises(RuntimeError, match="chooser failed"):
        runtime.import_upload("导入", [str(file_path)])

    assert runtime._direct_import_network_events is None


def test_playwright_runtime_tracks_direct_import_request_chain_and_excludes_polling() -> None:
    runtime = _build_runtime()
    runtime._start_direct_import_network_tracking(["/tmp/资金调度导入模板.xlsx"])

    poll = _import_request(
        "https://example.yonyougov.top/messagecenter/poll",
        method="GET",
    )
    seed = _import_request(
        "https://example.yonyougov.top/excel/invalid?fileName=资金调度导入模板.xlsx",
        method="GET",
    )
    parse = _import_request(
        "https://example.yonyougov.top/ydf/custom/EstimatePayTraRemain",
        method="POST",
    )
    runtime._capture_network_request(poll)
    runtime._capture_network_response(_import_response(poll, status=200, payload={"success": True}))
    runtime._capture_network_request(seed)
    runtime._capture_network_response(_import_response(seed, status=200, payload={"data": 0}))
    runtime._capture_network_request(parse)
    runtime._capture_network_response(_import_response(parse, status=200, payload={"data": {"rows": 1}}))

    result = runtime._wait_for_direct_import_network_result(
        ["/tmp/资金调度导入模板.xlsx"],
        timeout_ms=1,
        quiet_ms=0,
    )

    assert result["import_results"] == [
        {"file": "资金调度导入模板.xlsx", "status": "submitted", "message": "后端已接收导入文件"}
    ]
    assert [item["url"] for item in result["network_requests"]] == [seed.url, parse.url]


@pytest.mark.parametrize(
    ("response_status", "payload", "expected_status", "message"),
    [
        (200, {"success": True, "message": "导入成功"}, "success", "导入成功"),
        (200, {"success": False, "message": "文件格式错误"}, "failure", "文件格式错误"),
        (302, {"message": "跳转"}, "failure", "HTTP 302"),
        (500, {"message": "服务异常"}, "failure", "HTTP 500"),
    ],
)
def test_playwright_runtime_classifies_direct_import_backend_result(
    response_status,
    payload,
    expected_status,
    message,
) -> None:
    runtime = _build_runtime()
    runtime._start_direct_import_network_tracking(["/tmp/direct.xlsx"])
    request = _import_request(
        "https://example.yonyougov.top/ydf/custom/CustomImport",
        method="POST",
        content_type="multipart/form-data; boundary=test",
    )
    runtime._capture_network_request(request)
    runtime._capture_network_response(_import_response(request, status=response_status, payload=payload))

    result = runtime._wait_for_direct_import_network_result(
        ["/tmp/direct.xlsx"],
        timeout_ms=1,
        quiet_ms=0,
    )

    assert result["import_results"][0]["status"] == expected_status
    assert message in result["import_results"][0]["message"]


def test_playwright_runtime_direct_import_requires_related_backend_request() -> None:
    runtime = _build_runtime()
    runtime._page = SimpleNamespace(wait_for_timeout=lambda _ms: None)
    runtime._start_direct_import_network_tracking(["/tmp/direct.xlsx"])

    with pytest.raises(RuntimeError, match="未观察到相关后端上传或解析请求"):
        runtime._wait_for_direct_import_network_result(
            ["/tmp/direct.xlsx"],
            timeout_ms=1,
            quiet_ms=0,
        )


def test_import_file_resolver_supports_paths_relative_to_current_working_directory(monkeypatch, tmp_path) -> None:
    file_path = tmp_path / "fixtures" / "bad.xlsx"
    file_path.parent.mkdir()
    file_path.write_bytes(b"xlsx")
    monkeypatch.chdir(tmp_path)

    resolved = _resolve_import_file("fixtures/bad.xlsx")

    assert resolved == file_path.resolve()


def test_playwright_runtime_import_download_template_runs_standard_flow(monkeypatch) -> None:
    runtime = _build_runtime()
    calls: list[object] = []

    monkeypatch.setattr(runtime, "_open_import_sub_action", lambda label, sub_action: calls.append((label, sub_action)))
    monkeypatch.setattr(
        runtime,
        "_download_template_from_dialog",
        lambda template: calls.append(("download", template))
        or {"template": template, "downloaded_files": ["/Users/ken/Downloads/template.xlsx"]},
    )
    monkeypatch.setattr(runtime, "_close_template_download_dialog", lambda: calls.append("close-template"))

    result = runtime.import_download_template("导入", "收款人账户管理导入模板")

    assert calls == [
        ("导入", "下载模版"),
        ("download", "收款人账户管理导入模板"),
        "close-template",
    ]
    assert result["downloaded_files"] == ["/Users/ken/Downloads/template.xlsx"]


def test_playwright_runtime_set_amount_unit_uses_dialog_scope(monkeypatch) -> None:
    runtime = _build_runtime()
    dialog = object()
    action_candidates = [{"component_name": "LCDSetAmtunit", "fieldid": "amount_unit_btn"}]
    calls: list[tuple] = []

    monkeypatch.setattr(
        runtime,
        "_click_amount_unit_entry",
        lambda candidates=None: calls.append(("entry", candidates)),
        raising=False,
    )
    monkeypatch.setattr(
        runtime,
        "_resolve_amount_unit_dialog",
        lambda: calls.append(("dialog",)) or dialog,
        raising=False,
    )
    monkeypatch.setattr(
        runtime,
        "_set_radio_field_value",
        lambda root, value: calls.append(("radio", root, value)),
    )
    monkeypatch.setattr(
        runtime,
        "_read_radio_field_value",
        lambda root: calls.append(("read", root)) or "万元",
    )
    monkeypatch.setattr(
        runtime,
        "_click_amount_unit_confirm",
        lambda root: calls.append(("confirm", root)),
        raising=False,
    )

    result = runtime.set_amount_unit("万元", action_candidates=action_candidates)

    assert result == {"value": "万元", "actual_value": "万元"}
    assert calls == [
        ("entry", action_candidates),
        ("dialog",),
        ("radio", dialog, "万元"),
        ("read", dialog),
        ("confirm", dialog),
    ]


def test_playwright_runtime_amount_unit_confirm_failure_reports_diagnostics(monkeypatch) -> None:
    runtime = _build_runtime()

    class EmptyDialog:
        def locator(self, _selector: str) -> _FakeLocatorGroup:
            return _FakeLocatorGroup([])

    monkeypatch.setattr(runtime, "_collect_top_dialog_text", lambda: "设置金额单位 元 万元")
    monkeypatch.setattr(runtime, "_save_diagnostic_screenshot", lambda _name: "/tmp/amount-unit.png")

    with pytest.raises(RuntimeError) as exc:
        runtime._click_amount_unit_confirm(EmptyDialog())

    message = str(exc.value)
    assert "未找到金额单位弹窗确认按钮" in message
    assert "设置金额单位 元 万元" in message
    assert "screenshot=/tmp/amount-unit.png" in message


def test_template_download_selectors_match_template_title_aliases() -> None:
    selectors = build_template_download_link_selectors(None)

    assert any("模版下载" in selector for selector in selectors)
    assert any("模板下载" in selector for selector in selectors)
    assert any('span:text-is("下载")' in selector for selector in selectors)


def test_import_filename_normalization_matches_wrapped_progress_text() -> None:
    filename = "收款人账户管理导入模板_1806195728602103815-3.xlsx"
    progress_text = "收款人账户管理导入模板\n-1806195728602103815-3.xlsx"

    assert _normalize_import_filename(filename) == _normalize_import_filename(progress_text)


def test_import_status_infers_single_failure_from_progress_dialog_without_original_filename(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakeTextPage(
        "\n".join(
            [
                "正在操作 (1 / 1)",
                "导入（1 / 1）",
                "收款人账户管理导入模板",
                "-1806195728602103815-3.xlsx",
                "导入失败",
            ]
        )
    )
    monkeypatch.setattr(runtime_module, "_is_visible_text", lambda _page, _text: False)

    status = runtime._read_import_file_status("empty-template.xlsx", allow_single_result=True)

    assert status == "failure"


def test_import_failure_reason_ignores_progress_dialog_generic_failure(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakeTextPage(
        "\n".join(
            [
                "正在操作 (1 / 1)",
                "导入（1 / 1）",
                "收款人账户管理导入模板",
                "-1806195728602103815-3.xlsx",
                "导入失败",
            ]
        )
    )
    monkeypatch.setattr(runtime_module, "_is_visible_text", lambda _page, _text: False)
    monkeypatch.setattr(runtime, "_open_import_failure_detail", lambda _filename: None)
    monkeypatch.setattr(runtime, "_close_import_failure_detail_dialog", lambda: None)
    monkeypatch.setattr(runtime, "_collect_top_dialog_text", lambda: "导入（1 / 1） 收款人账户管理导入模板 导入失败")

    message = runtime._read_import_failure_reason("empty-template.xlsx")

    assert message == ""


def test_import_wait_fails_when_failure_detail_cannot_be_extracted(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakeTextPage(
        "\n".join(
            [
                "正在操作 (1 / 1)",
                "导入（1 / 1）",
                "收款人账户管理导入模板",
                "-1806195728602103815-3.xlsx",
                "导入失败",
            ]
        )
    )
    monkeypatch.setattr(runtime_module, "_is_visible_text", lambda _page, _text: False)
    monkeypatch.setattr(runtime, "_open_import_failure_detail", lambda _filename: None)
    monkeypatch.setattr(runtime, "_close_import_failure_detail_dialog", lambda: None)

    try:
        runtime._wait_for_import_results(["/tmp/empty-template.xlsx"], timeout_ms=1)
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected import failure detail extraction to fail")

    assert "未能提取导入失败详情" in message


def test_import_failure_message_rejects_progress_summary_as_real_reason() -> None:
    message = _extract_import_failure_message(
        "1 puqh02 2 puqh01 3 Z03 已选 0 行 共 64 条 "
        "正在操作(1/1) 导入 ( 1/1 ) 收款人账户管理导入模板_1806195728602103815-3.xlsx 导入失败 移除 查看"
    )

    assert message == ""


def test_import_failure_message_extracts_detail_dialog_reason() -> None:
    message = _extract_import_failure_message("提示 收款人信息不能为空 关闭")

    assert message == "收款人信息不能为空"


def test_import_status_reads_single_failure_from_child_frame_progress(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakeTextPage(
        "",
        frames=[
            _FakeTextPage(
                "\n".join(
                    [
                        "正在操作 (1 / 1)",
                        "导入（1 / 1）",
                        "收款人账户管理导入模板",
                        "-1806195728602103815-3.xlsx",
                        "导入失败",
                    ]
                )
            )
        ],
    )
    monkeypatch.setattr(runtime_module, "_is_visible_text", lambda _page, _text: False)

    status = runtime._read_import_file_status("empty-template.xlsx", allow_single_result=True)

    assert status == "failure"


class _FakeBprContext:
    def __init__(self) -> None:
        self.cookies: list[dict[str, object]] = []

    def add_cookies(self, cookies: list[dict[str, object]]) -> None:
        self.cookies.extend(cookies)


class _FakeBprPage:
    def __init__(self) -> None:
        self.url = "https://example.yonyougov.top/#/service/demo"
        self.context = _FakeBprContext()
        self.evaluate_calls: list[tuple[str, object]] = []
        self.events = [{"en": "HBClick", "evt": 1200, "attrs": {"bprId": "fake"}, "ntxt": "保存"}]

    def evaluate(self, script: str, arg=None):
        self.evaluate_calls.append((script, arg))
        if "localStorage" in script and "sessionStorage" in script:
            return {"userId": "u-1", "userName": "张三", "tenantId": "t-1"}
        url = str(arg.get("url") if isinstance(arg, dict) else "")
        if "monitor/record" in script or "monitor/record" in url:
            return {"status": 200, "text": "ok"}
        if "__ydfBrowserBprCollectorInstalled" in script:
            return None
        if "__ydfBrowserBprEvents" in script:
            return self.events
        if "bprcall" in script or "bprcall" in url:
            return {
                "status": 200,
                "text": '{"code":"200","message":"https://example.yonyougov.top/iuap-ymc-server/proxy/server/bpr/open?pk=fake"}',
            }
        return None


def test_playwright_runtime_start_bpr_writes_encoded_cookies_and_calls_monitor() -> None:
    runtime = _build_runtime()
    page = _FakeBprPage()
    runtime._page = page

    session = runtime.start_bpr(index=1, name="保存录制", control_step=2)

    cookies = {item["name"]: item for item in page.context.cookies}
    assert cookies["mdd_monitor_uid"]["value"] == session["bpr_id"]
    assert cookies["ymc_flag"]["value"] == f"bprId%3D{session['bpr_id']}%3BbprStartTs%3D{session['start_ts']}"
    assert cookies["mdd_monitor_record"]["value"] == "true"
    assert cookies["ymc_recording"]["value"] == "true"
    assert session["user_id"] == "u-1"
    assert session["user_name"] == "张三"
    assert session["tenant_id"] == "t-1"
    assert any("monitor/record" in str(arg) for _script, arg in page.evaluate_calls)


def test_playwright_runtime_stop_bpr_posts_bprcall_and_extracts_report_url() -> None:
    runtime = _build_runtime()
    page = _FakeBprPage()
    runtime._page = page

    result = runtime.stop_bpr(
        {
            "bpr_id": "fake-bpr",
            "start_ts": 1000,
            "host": "https://example.yonyougov.top",
            "user_id": "u-1",
            "user_name": "张三",
            "tenant_id": "t-1",
        }
    )

    assert result["report_url"] == "https://example.yonyougov.top/iuap-ymc-server/proxy/server/bpr/open?pk=fake"
    assert result["uba_event_count"] == 3
    stop_call = next(arg for script, arg in page.evaluate_calls if "bprcall" in script or "bprcall" in str(arg))
    assert "bprId=fake-bpr" in stop_call["url"]
    assert stop_call["body"]["ubaData"][0]["header"]["userid"] == "u-1"
    assert stop_call["body"]["ubaData"][0]["header"]["ytid"] == "t-1"
    assert stop_call["body"]["ubaData"][0]["content"][0]["ntxt"] == "ydf-browser-bpr-start"


class _FakeBprDownload:
    def __init__(
        self,
        content: bytes = b"<html>raw bpr</html>",
        *,
        saved_paths: list[Path] | None = None,
        saved_parent_modes: list[int] | None = None,
        fail_after_write: bool = False,
    ) -> None:
        self.content = content
        self.saved_paths = saved_paths
        self.saved_parent_modes = saved_parent_modes
        self.fail_after_write = fail_after_write

    def save_as(self, target: str) -> None:
        path = Path(target)
        if self.saved_paths is not None:
            self.saved_paths.append(path)
        if self.saved_parent_modes is not None:
            self.saved_parent_modes.append(path.parent.stat().st_mode & 0o777)
        path.write_bytes(self.content)
        if self.fail_after_write:
            raise OSError("partial download")


class _FakeBprDownloadInfo:
    def __init__(self, download: _FakeBprDownload | None = None) -> None:
        self._active = False
        self._prepared_download = download
        self._download: _FakeBprDownload | None = None

    def __enter__(self):
        self._active = True
        return self

    def __exit__(self, *_args) -> None:
        self._active = False
        return None

    def record_click(self) -> None:
        if not self._active:
            raise AssertionError("下载按钮必须在 expect_download 上下文内点击")
        self._download = self._prepared_download or _FakeBprDownload()

    @property
    def value(self) -> _FakeBprDownload:
        if self._download is None:
            raise AssertionError("expect_download 上下文内未发生按钮点击")
        return self._download


class _FakeBprDownloadButton:
    def __init__(self, calls: list[tuple[str, object]]) -> None:
        self.calls = calls
        self.download_info: _FakeBprDownloadInfo | None = None

    def wait_for(self, **kwargs) -> None:
        self.calls.append(("button.wait_for", kwargs))

    def click(self, **kwargs) -> None:
        self.calls.append(("button.click", kwargs))
        if self.download_info is None:
            raise AssertionError("点击前必须进入 expect_download 上下文")
        self.download_info.record_click()


class _FakeBprDownloadPage:
    def __init__(self, page_bpr_id: str = "bpr-123", download: _FakeBprDownload | None = None) -> None:
        self.calls: list[tuple[str, object]] = []
        self.page_bpr_id = page_bpr_id
        self.download = download
        self.button = _FakeBprDownloadButton(self.calls)

    def goto(self, url: str, **kwargs) -> None:
        self.calls.append(("goto", {"url": url, **kwargs}))

    def wait_for_function(self, _script: str, *, arg: str, timeout: int) -> None:
        self.calls.append(("wait_for_function", {"arg": arg, "timeout": timeout}))
        if self.page_bpr_id != arg:
            raise TimeoutError("BPR ID 未就绪")

    def get_by_role(self, role: str, *, name: str, exact: bool):
        self.calls.append(("get_by_role", {"role": role, "name": name, "exact": exact}))
        return self.button

    def expect_download(self, *, timeout: int):
        self.calls.append(("expect_download", {"timeout": timeout}))
        download_info = _FakeBprDownloadInfo(self.download)
        self.button.download_info = download_info
        return download_info


def test_playwright_runtime_download_bpr_report_accepts_distinct_url_record_key_and_uses_one_deadline(
    tmp_path: Path,
    monkeypatch,
) -> None:
    runtime = _build_runtime()
    saved_paths: list[Path] = []
    saved_parent_modes: list[int] = []
    page = _FakeBprDownloadPage(
        download=_FakeBprDownload(saved_paths=saved_paths, saved_parent_modes=saved_parent_modes)
    )
    runtime._page = page
    monotonic_values = iter([10.0, 10.5, 11.0, 11.5, 12.0, 12.5])
    monkeypatch.setattr(runtime_module.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(runtime, "_apply_api_session_cookies", lambda: page.calls.append(("cookies", {})))
    target = tmp_path / "nested" / "bpr.html"

    saved = runtime.download_bpr_report(
        "https://example.yonyougov.top/iuap-ymc-server/proxy/server/bpr/open?pk=report-record-456",
        "bpr-123",
        target,
    )

    assert saved == target
    assert target.read_bytes() == b"<html>raw bpr</html>"
    assert target.stat().st_mode & 0o777 == 0o600
    assert saved_parent_modes == [0o700]
    assert saved_paths[0] != target
    assert not list(target.parent.glob(".ydf-browser-bpr-*"))
    assert [name for name, _payload in page.calls] == [
        "cookies",
        "goto",
        "wait_for_function",
        "get_by_role",
        "button.wait_for",
        "expect_download",
        "button.click",
    ]
    timeouts = [
        payload["timeout"]
        for name, payload in page.calls
        if name in {"goto", "wait_for_function", "button.wait_for", "expect_download", "button.click"}
    ]
    assert timeouts == [59500, 59000, 58500, 58000, 57500]


def test_playwright_runtime_download_bpr_report_cleans_partial_private_download(tmp_path: Path, monkeypatch) -> None:
    runtime = _build_runtime()
    saved_paths: list[Path] = []
    saved_parent_modes: list[int] = []
    page = _FakeBprDownloadPage(
        download=_FakeBprDownload(
            saved_paths=saved_paths,
            saved_parent_modes=saved_parent_modes,
            fail_after_write=True,
        )
    )
    runtime._page = page
    monkeypatch.setattr(runtime, "_apply_api_session_cookies", lambda: None)
    target = tmp_path / "nested" / "bpr.html"

    with pytest.raises(OSError, match="partial download"):
        runtime.download_bpr_report(
            "https://example.yonyougov.top/iuap-ymc-server/proxy/server/bpr/open?pk=report-record-456",
            "bpr-123",
            target,
        )

    assert saved_parent_modes == [0o700]
    assert not target.exists()
    assert not list(target.parent.glob(".ydf-browser-bpr-*"))

def test_playwright_runtime_download_bpr_report_rejects_loaded_page_id(tmp_path: Path, monkeypatch) -> None:
    runtime = _build_runtime()
    page = _FakeBprDownloadPage(page_bpr_id="other")
    runtime._page = page
    monkeypatch.setattr(runtime, "_apply_api_session_cookies", lambda: None)

    with pytest.raises(TimeoutError, match="BPR ID"):
        runtime.download_bpr_report(
            "https://example.yonyougov.top/iuap-ymc-server/proxy/server/bpr/open?pk=report-record-456",
            "bpr-123",
            tmp_path / "bpr.html",
        )

    assert not (tmp_path / "bpr.html").exists()


def test_normalize_multi_select_target_values_preserves_scalar_list_and_empty() -> None:
    assert runtime_module._normalize_multi_select_target_values("草稿") == ["草稿"]
    assert runtime_module._normalize_multi_select_target_values(["启用", "草稿"]) == ["启用", "草稿"]
    assert runtime_module._normalize_multi_select_target_values([]) == []

    with pytest.raises(ValueError, match="重复值"):
        runtime_module._normalize_multi_select_target_values(["草稿", " 草稿 "])


def test_multi_select_value_diagnostics_matches_code_name_display_variants() -> None:
    assert runtime_module._multi_select_value_diagnostics(["001 办公室"], ["办公室"]) == {
        "expected_values": ["001 办公室"],
        "actual_values": ["办公室"],
        "missing_values": [],
        "unexpected_values": [],
    }
    assert runtime_module._multi_select_value_diagnostics(["草稿"], ["草稿", "启用"]) == {
        "expected_values": ["草稿"],
        "actual_values": ["草稿", "启用"],
        "missing_values": [],
        "unexpected_values": ["启用"],
    }
    assert runtime_module._multi_select_value_diagnostics(["001 办公室"], ["002 办公室"]) == {
        "expected_values": ["001 办公室"],
        "actual_values": ["002 办公室"],
        "missing_values": ["001 办公室"],
        "unexpected_values": ["002 办公室"],
    }


def test_candidate_claims_multi_select_from_checkable_prop() -> None:
    candidate = SimpleNamespace(raw={"props": {"checkable": 1}}, component_name="YDFSelect")

    assert runtime_module._candidate_claims_multi_select(candidate) is True


def test_runtime_single_select_evidence_overrides_checkable_template_metadata() -> None:
    class Root:
        def evaluate(self, _script):
            return False

    candidate = SimpleNamespace(raw={"props": {"checkable": 1}}, component_name="YDFSelect")

    assert _build_runtime()._choice_field_is_multi_select(Root(), candidate) is False


@pytest.mark.parametrize(
    "selector_token",
    ["wui-select-selection-item", "ant-select-selection-item", "u-select-selection-item"],
)
def test_read_multi_select_choice_values_covers_wui_ant_and_uui_tags(selector_token) -> None:
    class Root:
        def evaluate(self, script):
            assert selector_token in script
            return ["001 办公室", "草稿"]

    runtime = _build_runtime()

    assert runtime._read_multi_select_choice_values(Root()) == ["001 办公室", "草稿"]


def test_read_multi_select_choice_values_falls_back_to_checked_dropdown_options(monkeypatch) -> None:
    class Root:
        def evaluate(self, _script):
            return []

    monkeypatch.setattr(PlaywrightRuntime, "_read_checked_multi_select_choice_values", lambda self, root: ["草稿"])

    assert _build_runtime()._read_multi_select_choice_values(Root()) == ["草稿"]


def test_checked_multi_select_values_are_scoped_to_current_root(monkeypatch) -> None:
    class Root:
        def evaluate(self, script, payload):
            assert "aria-controls" in script
            assert payload["action"] == "read"
            return ["草稿"]

    runtime = _build_runtime()
    monkeypatch.setattr(
        runtime,
        "_all_search_contexts",
        lambda: (_ for _ in ()).throw(AssertionError("must not scan unrelated frames or dropdowns")),
    )

    assert runtime._read_checked_multi_select_choice_values(Root()) == ["草稿"]


def test_multi_select_surface_association_fails_when_new_overlay_is_not_unique(monkeypatch) -> None:
    class Root:
        def click(self, **_kwargs):
            return None

        def evaluate(self, _script, payload):
            if payload["action"] == "visible":
                return False
            if payload["action"] == "attach":
                return {"ok": False, "count": 2}
            raise AssertionError(payload)

    runtime = _build_runtime()
    runtime._active_multi_select_surface_token = "token"
    monkeypatch.setattr(runtime, "_wait_for_query_choice_surface_ready", lambda **_kwargs: True)

    with pytest.raises(RuntimeError, match="候选面不唯一"):
        runtime._ensure_multi_select_choice_surface_open(Root(), object())


def test_unique_multi_select_candidate_uses_current_owned_surface(monkeypatch) -> None:
    class Root:
        def evaluate(self, script, payload):
            assert "data-ydf-multi-select-owner" in script
            assert payload["action"] == "candidates"
            return ["001 办公室"]

    runtime = _build_runtime()
    monkeypatch.setattr(
        runtime,
        "_all_search_contexts",
        lambda: (_ for _ in ()).throw(AssertionError("must not scan unrelated frames")),
    )

    assert runtime._wait_for_unique_multi_select_candidate(Root(), "办公室") == "001 办公室"


def test_multi_select_clear_script_clicks_only_select_all_when_present() -> None:
    assert "selectAll.length ? [selectAll[0]] : options" in runtime_module._MULTI_SELECT_SURFACE_SCRIPT


def test_existing_multi_select_surface_requires_active_trigger_before_owner_claim() -> None:
    script = runtime_module._MULTI_SELECT_SURFACE_SCRIPT

    assert "node.contains(node.ownerDocument.activeElement)" in script
    assert "payload.allowExistingSingle && active && allSurfaces.length === 1" in script


def test_multi_select_candidate_ambiguity_rejects_multiple_equivalent_options() -> None:
    assert runtime_module._ambiguous_multi_select_candidate_values(
        "办公室", ["001 办公室", "002 办公室"]
    ) == ["001 办公室", "002 办公室"]
    assert runtime_module._ambiguous_multi_select_candidate_values(
        "001 办公室", ["001 办公室", "办公室"]
    ) == ["001 办公室", "办公室"]
    assert runtime_module._ambiguous_multi_select_candidate_values(
        "001 办公室", ["001 办公室", "001 办公室"]
    ) == []


def test_assign_multi_select_choice_replaces_existing_values(monkeypatch) -> None:
    runtime = _build_runtime()
    selected = ["启用"]
    monkeypatch.setattr(runtime, "_read_multi_select_choice_values", lambda _root: list(selected))

    def clear(_root, _fill_locator):
        selected.clear()

    def select(_root, _fill_locator, value, **_kwargs):
        selected.append(value)

    monkeypatch.setattr(runtime, "_clear_multi_select_choice", clear)
    monkeypatch.setattr(runtime, "_select_single_query_choice", select)
    monkeypatch.setattr(runtime, "_prepare_multi_select_choice_surface", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runtime, "_ensure_multi_select_choice_surface_open", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runtime, "_dismiss_multi_select_choice_surface", lambda _root: None)

    result = runtime._assign_multi_select_choice(object(), object(), "草稿")

    assert selected == ["草稿"]
    assert result == {"expected_values": ["草稿"], "actual_values": ["草稿"]}


def test_assign_multi_select_choice_opens_checkbox_surface_before_reading_defaults(monkeypatch) -> None:
    runtime = _build_runtime()
    selected = ["启用"]
    surface_open = False

    def read(_root):
        return list(selected) if surface_open else []

    def open_surface(_root, _fill_locator, **_kwargs):
        nonlocal surface_open
        surface_open = True

    monkeypatch.setattr(runtime, "_read_multi_select_choice_values", read)
    monkeypatch.setattr(runtime, "_prepare_multi_select_choice_surface", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runtime, "_ensure_multi_select_choice_surface_open", open_surface)
    monkeypatch.setattr(runtime, "_clear_multi_select_choice", lambda _root, _fill_locator: selected.clear())
    monkeypatch.setattr(runtime, "_select_single_query_choice", lambda _root, _fill, value, **_kwargs: selected.append(value))
    monkeypatch.setattr(runtime, "_dismiss_multi_select_choice_surface", lambda _root: None)

    result = runtime._assign_multi_select_choice(object(), object(), "草稿")

    assert result == {"expected_values": ["草稿"], "actual_values": ["草稿"]}


def test_assign_multi_select_choice_empty_list_clears_all_values(monkeypatch) -> None:
    runtime = _build_runtime()
    selected = ["启用"]
    monkeypatch.setattr(runtime, "_read_multi_select_choice_values", lambda _root: list(selected))
    monkeypatch.setattr(runtime, "_clear_multi_select_choice", lambda _root, _fill_locator: selected.clear())
    monkeypatch.setattr(runtime, "_prepare_multi_select_choice_surface", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runtime, "_ensure_multi_select_choice_surface_open", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runtime, "_dismiss_multi_select_choice_surface", lambda _root: None)

    result = runtime._assign_multi_select_choice(object(), object(), [])

    assert result == {"expected_values": [], "actual_values": []}


def test_assign_multi_select_choice_failure_exposes_full_set_diagnostics(monkeypatch) -> None:
    runtime = _build_runtime()
    monkeypatch.setattr(runtime, "_read_multi_select_choice_values", lambda _root: ["启用"])
    monkeypatch.setattr(runtime, "_clear_multi_select_choice", lambda _root, _fill_locator: None)
    monkeypatch.setattr(runtime, "_prepare_multi_select_choice_surface", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runtime, "_ensure_multi_select_choice_surface_open", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runtime, "_dismiss_multi_select_choice_surface", lambda _root: None)

    with pytest.raises(runtime_module.MultiSelectAssignmentError) as exc:
        runtime._assign_multi_select_choice(object(), object(), "草稿")

    assert exc.value.data == {
        "expected_values": ["草稿"],
        "actual_values": ["启用"],
        "missing_values": ["草稿"],
        "unexpected_values": ["启用"],
    }


def test_assign_multi_select_choice_selection_error_exposes_full_target_diagnostics(monkeypatch) -> None:
    runtime = _build_runtime()
    monkeypatch.setattr(runtime, "_read_multi_select_choice_values", lambda _root: [])
    monkeypatch.setattr(runtime, "_prepare_multi_select_choice_surface", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(runtime, "_ensure_multi_select_choice_surface_open", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        runtime,
        "_select_single_query_choice",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("候选歧义")),
    )
    monkeypatch.setattr(runtime, "_dismiss_multi_select_choice_surface", lambda _root: None)

    with pytest.raises(runtime_module.MultiSelectAssignmentError) as exc:
        runtime._assign_multi_select_choice(object(), object(), ["草稿", "启用"])

    assert exc.value.data == {
        "expected_values": ["草稿", "启用"],
        "actual_values": [],
        "missing_values": ["草稿", "启用"],
        "unexpected_values": [],
    }


def test_form_multi_select_does_not_skip_when_scalar_is_only_one_existing_value(monkeypatch) -> None:
    runtime = _build_runtime()
    runtime._page = _FakePage()
    root = object()
    fill_locator = object()
    bound = SimpleNamespace(
        candidate=SimpleNamespace(component_name="YDFSelect", raw={"props": {"checkable": 1}}),
        runtime=SimpleNamespace(selector='[fieldid="accStaCode"]', in_dialog=False),
    )
    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda _selector: root)
    monkeypatch.setattr(runtime, "_resolve_runtime_only_form_field_root", lambda _bound: root)
    monkeypatch.setattr(runtime._popup_reference_module(), "looks_like_field", lambda *_args: False)
    monkeypatch.setattr(runtime, "_looks_like_switch_field", lambda *_args: False)
    monkeypatch.setattr(runtime, "_looks_like_radio_field", lambda *_args: False)
    monkeypatch.setattr(runtime, "_looks_like_date_range_field", lambda *_args: False)
    monkeypatch.setattr(runtime, "_looks_like_date_field", lambda *_args: False)
    monkeypatch.setattr(runtime, "_looks_like_choice_field", lambda *_args: True)
    monkeypatch.setattr(runtime, "_resolve_fill_locator", lambda _selector: fill_locator)
    monkeypatch.setattr(runtime, "_read_field_value_from_container", lambda _bound: "启用 草稿")
    calls = []
    monkeypatch.setattr(runtime, "_select_choice_for_field", lambda *args, **kwargs: calls.append((args, kwargs)) or {})

    runtime.fill_form_field(bound, "草稿")

    assert calls


def test_editable_table_multi_select_bypasses_single_choice_shortcut(monkeypatch) -> None:
    runtime = _build_runtime()
    cell = object()
    candidate = SimpleNamespace(component_name="YDFSelect", raw={"props": {"checkable": 1}})
    monkeypatch.setattr(runtime, "_resolve_visible_locator", lambda _selector: cell)
    monkeypatch.setattr(runtime, "_first_visible_child_locator", lambda *_args: None)
    monkeypatch.setattr(runtime, "_active_editable_locator_within", lambda _cell: None)
    monkeypatch.setattr(runtime, "_locator_is_directly_editable", lambda _cell: False)
    monkeypatch.setattr(runtime, "_choice_field_is_multi_select", lambda *_args: True)
    monkeypatch.setattr(runtime, "_safe_has_visible_choice_dropdown", lambda: True)
    monkeypatch.setattr(
        runtime,
        "_try_select_current_editable_table_choice",
        lambda *_args: (_ for _ in ()).throw(AssertionError("must not use single-choice shortcut")),
    )
    monkeypatch.setattr(
        runtime,
        "_select_query_choice",
        lambda *_args, **kwargs: {"expected_values": ["草稿"], "actual_values": ["草稿"]},
    )

    result = runtime._fill_active_editable_table_cell("cell", "草稿", column_candidate=candidate)

    assert result == {"expected_values": ["草稿"], "actual_values": ["草稿"]}


def test_playwright_runtime_tab_action_already_rendered(monkeypatch) -> None:
    runtime = object.__new__(PlaywrightRuntime)
    bound = BoundElement(
        candidate=ElementCandidate(
            key="tab", fieldid="tab-001", label="待提交", title="待提交",
            region_key=None, region_fieldid=None, element_type="action", component_name="Button",
        ),
        runtime=RuntimeElement(
            fieldid="tab-001", id=None, name=None, placeholder=None, text="待提交",
            role=None, tag_name="div", visible=True, selector="[fieldid='tab-001']",
        ),
        confidence=1.0,
        reasons=["test"],
    )
    selector_calls: list[str | None] = []
    exact_calls: list[str] = []

    def fake_find_selector(selectors, **_kwargs):
        selector_calls.append(selectors)
        return "[fieldid='tab-001']"

    def fake_find_exact(selectors, text, **_kwargs):
        exact_calls.append(text)
        return None

    monkeypatch.setattr(runtime, "_find_first_visible_selector", fake_find_selector)
    monkeypatch.setattr(runtime, "_find_first_visible_exact_text_selector", fake_find_exact)
    monkeypatch.setattr(
        runtime,
        "_build_visible_action_bound_element",
        lambda label, selector, reason: bound,
    )

    result = runtime._resolve_visible_tab_action("待提交", fieldid="tab-001")

    assert result is bound
    assert len(selector_calls) == 1
    assert exact_calls == []


def test_playwright_runtime_tab_action_retry_hit(monkeypatch) -> None:
    runtime = object.__new__(PlaywrightRuntime)
    bound = BoundElement(
        candidate=ElementCandidate(
            key="tab", fieldid="tab-002", label="待审核", title="待审核",
            region_key=None, region_fieldid=None, element_type="action", component_name="Button",
        ),
        runtime=RuntimeElement(
            fieldid="tab-002", id=None, name=None, placeholder=None, text="待审核",
            role=None, tag_name="div", visible=True, selector="[fieldid='tab-002']",
        ),
        confidence=1.0,
        reasons=["test"],
    )
    attempts: list[int] = []
    sleep_calls: list[float] = []

    def fake_find_selector(selectors, **_kwargs):
        attempts.append(len(attempts))
        if len(attempts) < 3:
            return None
        return "[fieldid='tab-002']"

    def fake_find_exact(selectors, text, **_kwargs):
        return None

    monkeypatch.setattr(runtime, "_find_first_visible_selector", fake_find_selector)
    monkeypatch.setattr(runtime, "_find_first_visible_exact_text_selector", fake_find_exact)
    monkeypatch.setattr(runtime, "_tab_retry_sleep", lambda seconds: sleep_calls.append(seconds))
    monkeypatch.setattr(runtime, "_tab_retry_now", lambda: 0.0)
    monkeypatch.setattr(
        runtime,
        "_build_visible_action_bound_element",
        lambda label, selector, reason: bound,
    )

    result = runtime._resolve_visible_tab_action("待审核")

    assert result is bound
    assert len(attempts) == 3
    assert len(sleep_calls) == 2


def test_playwright_runtime_tab_action_retry_exhausted(monkeypatch) -> None:
    runtime = object.__new__(PlaywrightRuntime)
    diagnostic_text = "fieldid候选 count=1 visible=False | stepBar容器 count=1 子元素=0"
    now_calls: list[int] = []

    def fake_now() -> float:
        now_calls.append(len(now_calls))
        return 0.0 if len(now_calls) <= 1 else 10.0

    monkeypatch.setattr(runtime, "_find_first_visible_selector", lambda *_a, **_kw: None)
    monkeypatch.setattr(runtime, "_find_first_visible_exact_text_selector", lambda *_a, **_kw: None)
    monkeypatch.setattr(runtime, "_tab_retry_sleep", lambda _seconds: None)
    monkeypatch.setattr(runtime, "_tab_retry_now", fake_now)
    monkeypatch.setattr(runtime, "_collect_tab_diagnostic", lambda fieldid, label: diagnostic_text)
    monkeypatch.setattr(runtime, "_collect_page_diagnostic_text", lambda: "")
    monkeypatch.setattr(runtime, "_save_diagnostic_screenshot", lambda _name: None)

    with pytest.raises(RuntimeError, match="未找到可点击页签") as exc_info:
        runtime.click_tab_action("待提交", fieldid="tab-003")

    assert "fieldid候选" in str(exc_info.value)
    assert "stepBar容器" in str(exc_info.value)


def test_table_scope_probe_does_not_scroll_unrelated_tables(_popup_reference_page) -> None:
    from ydf_browser.models import PageManifest, PageMeta
    from ydf_browser.table_scope import RuntimeTableScopeAdapter, TableScopeRequest, TableScopeResolver

    page = _popup_reference_page
    page.set_content('''
      <div fieldid="DETAIL" class="ant-table"><table><thead><tr><th>费用名称</th></tr></thead>
        <tbody><tr><td>办公费</td></tr></tbody></table></div>
      <div fieldid="INDICATOR" class="ant-table-body" style="width:300px;height:100px;overflow:auto">
        <table style="width:900px"><thead><tr><th>指标信息</th></tr></thead><tbody><tr><td>指标一</td></tr></tbody></table>
      </div>
    ''')
    page.evaluate('''() => {
      window.unrelatedScroll = [];
      const node = document.querySelector('[fieldid="INDICATOR"]');
      const descriptor = Object.getOwnPropertyDescriptor(Element.prototype, 'scrollLeft');
      Object.defineProperty(node, 'scrollLeft', {...descriptor, set(value) {
        const before = descriptor.get.call(this);
        descriptor.set.call(this, value);
        if (descriptor.get.call(this) !== before) window.unrelatedScroll.push(value);
      }});
    }''')
    runtime = _build_runtime()
    runtime._page = page
    regions = [Region(fid, fid, label, "main_table", "table", "Table", None, True, 0)
               for fid, label in [("MISSING", "隐藏表格"), ("DETAIL", "费用明细"), ("INDICATOR", "指标信息")]]
    manifest = PageManifest(PageMeta("page", None, None, None), regions=regions)
    for required in [(), ("费用名称",)]:
        scope = TableScopeResolver(RuntimeTableScopeAdapter(runtime)).resolve(
            manifest, TableScopeRequest(target="费用明细", required_columns=required),
        )
        assert scope.region_fieldid == "DETAIL"
    assert page.evaluate('window.unrelatedScroll') == []


def test_header_collection_missing_identity_never_scrolls_page(_popup_reference_page) -> None:
    page = _popup_reference_page
    page.set_content('<div class="ant-table-body" style="width:300px;height:100px;overflow:auto"><div style="width:900px">无关表格</div></div>')
    runtime = _build_runtime()
    runtime._page = page
    with pytest.raises(RuntimeError, match="表格作用域未匹配"):
        runtime.collect_table_headers(table_fieldid="MISSING")
    assert page.locator('.ant-table-body').evaluate('(node) => node.scrollLeft') == 0


@pytest.mark.parametrize("state", ["ready", "iframe", "loading", "frame_loading", "hidden_frame", "placeholder", "disabled", "old", "unrelated", "multiple"])
def test_action_completion_new_popup_ready(_popup_reference_page, monkeypatch, state) -> None:
    page = _popup_reference_page
    page.set_content('<style>body {padding-top:100px}</style><button fieldid="choose" onclick="showPopup()">选择指标</button>')
    page.evaluate('''state => {
      const row = state === 'placeholder' ? '<tr><td>暂无数据</td></tr>'
        : `<tr><td><input type="checkbox" ${state === 'disabled' ? 'disabled' : ''}>指标一</td></tr>`;
      const content = `<div ${state === 'frame_loading' ? 'aria-busy="true"' : ''}><table><tbody>${row}</tbody></table></div>`;
      const inFrame = ['iframe', 'frame_loading', 'hidden_frame'].includes(state);
      window.showPopup = () => {
        if (state === 'old' && document.querySelector('[role=dialog]')) return;
        const dialog = document.createElement('div');
        dialog.setAttribute('role', 'dialog');
        dialog.style = 'position:fixed;top:200px;left:100px;background:white;width:500px;height:400px';
        if (state === 'loading') dialog.setAttribute('aria-busy', 'true');
        dialog.innerHTML = `<h2 class="${inFrame ? 'yy-ydf-modal-header' : 'wui-modal-title'}">${state === 'unrelated' ? '其它参照' : '选择指标'}</h2>
          ${inFrame ? '<iframe></iframe>' : content}<button>确定</button><button>取消</button>`;
        document.body.append(dialog);
        if (inFrame) {
          dialog.querySelector('iframe').srcdoc = content;
          if (state === 'hidden_frame') dialog.querySelector('iframe').style.display = 'none';
        }
        if (state === 'multiple') {
          const second = dialog.cloneNode(true);second.style.left = '650px';document.body.append(second);
        }
      };
      if (state === 'old') window.showPopup();
    }''', state)
    runtime = _build_runtime()
    runtime._page = page
    now = [0.0]
    monkeypatch.setattr(runtime, "_action_completion_now", lambda: now[0])
    def poll(ms):
        now[0] += ms / 1000
        page.wait_for_timeout(10)
    monkeypatch.setattr(runtime, "_wait_action_completion_poll", poll)
    def click():
        runtime.click_toolbar_action("选择指标", fieldid="choose")
        if state in {"iframe", "frame_loading", "hidden_frame"}:
            page.frame_locator('iframe').locator('table').wait_for(state='attached')
    request = ActionCompletionRequest("toolbar.click", {"action": "选择指标"}, deadline=0.6)
    if state in {"ready", "iframe"}:
        result = ActionCompletion(runtime).execute(request, click)
        assert result.completion_signal == "popup_reference_ready"
        assert result.fallback_used is False
    else:
        with pytest.raises(TimeoutError):
            ActionCompletion(runtime).execute(request, click)


def test_table_scope_hydrates_only_required_virtual_columns(_popup_reference_page) -> None:
    from ydf_browser.table_scope import RuntimeTableScopeAdapter, TableScopeRequest, TableScopeResolver

    page = _popup_reference_page
    page.set_content('''
      <div fieldid="DETAIL" class="ant-table">
        <div class="ant-table-body" style="width:300px;height:100px;overflow:auto">
          <table style="width:900px"><thead><tr><th data-field="name">费用名称</th></tr></thead>
            <tbody><tr><td>办公费</td></tr></tbody></table>
        </div>
      </div>
      <div fieldid="OTHER" class="ant-table-body" style="width:500px;height:150px;overflow:auto">
        <table style="width:1200px"><thead><tr><th>指标信息</th></tr></thead><tbody><tr><td>指标一</td></tr></tbody></table>
      </div>
    ''')
    page.evaluate('''() => {
      window.otherMoves = [];
      const descriptor = Object.getOwnPropertyDescriptor(Element.prototype, 'scrollLeft');
      const target = document.querySelector('[fieldid=DETAIL] .ant-table-body');
      Object.defineProperty(target, 'scrollLeft', {...descriptor, set(value) {
        descriptor.set.call(this, value);
        this.querySelector('thead tr').innerHTML = descriptor.get.call(this) > 0
          ? '<th data-field="remark">备注</th>' : '<th data-field="name">费用名称</th>';
      }});
      const other = document.querySelector('[fieldid=OTHER]');
      Object.defineProperty(other, 'scrollLeft', {...descriptor, set(value) {
        window.otherMoves.push(value); descriptor.set.call(this, value);
      }});
    }''')
    runtime = _build_runtime()
    runtime._page = page
    manifest = PageManifest(PageMeta("page", None, None, None), regions=[
        Region(fid, fid, label, "main_table", "table", "Table", None, True, 0)
        for fid, label in [("DETAIL", "费用明细"), ("OTHER", "指标信息")]
    ])
    scope = TableScopeResolver(RuntimeTableScopeAdapter(runtime)).resolve(
        manifest, TableScopeRequest(target="费用明细", required_columns=("费用名称", "备注")),
    )
    assert scope.columns == ("费用名称", "备注")
    assert page.locator('[fieldid=DETAIL] .ant-table-body').evaluate('(node) => node.scrollLeft') == 0
    assert page.evaluate('window.otherMoves') == []


def _resolved_alias_table(page, *, in_frame=False):
    from ydf_browser.table_scope import RuntimeTableScopeAdapter, TableScopeRequest, TableScopeResolver

    page.set_content('''
      <div fieldid="ACTUAL" class="ant-table"><table>
        <thead><tr><th><input type="checkbox" onclick="document.querySelectorAll('tbody input').forEach(x => x.checked = this.checked)"></th><th>编码</th><th>金额</th></tr></thead>
        <tbody><tr><td><input type="checkbox"></td><td><a href="#" onclick="window.linkClicked = true;return false">A</a></td><td>10</td></tr>
        <tr><td><input type="checkbox"></td><td>B</td><td>20</td></tr></tbody>
      </table></div>
    ''')
    if in_frame:
        content = page.content()
        page.set_content('<iframe style="width:700px;height:400px"></iframe>')
        page.frames[1].set_content(content)
    runtime = _build_runtime()
    runtime._page = page
    region = Region("TEMPLATE", "TEMPLATE", "明细表", "main_table", "table", "Table", None, True, 0,
                    runtime_fieldids=["ACTUAL"])
    manifest = PageManifest(PageMeta("page", None, None, None), regions=[region])
    scope = TableScopeResolver(RuntimeTableScopeAdapter(runtime)).resolve_for_execution(
        manifest, TableScopeRequest(target="明细表", required_columns=("编码", "金额")),
    )
    return runtime, scope


@pytest.mark.parametrize("operation", ["headers", "column", "row", "snapshot", "match", "index", "indices", "all", "hover", "hover_index", "link"])
@pytest.mark.parametrize("in_frame", [False, True])
def test_table_scope_consumers_keep_resolved_runtime_identity(_popup_reference_page, operation, in_frame) -> None:
    page = _popup_reference_page
    runtime, scope = _resolved_alias_table(page, in_frame=in_frame)
    document = page.frames[1] if in_frame else page
    kw = {"table_scope": scope}
    match = {"column": "编码", "equals": "A"}
    if operation == "headers":
        assert runtime.collect_table_headers(**kw) == ["编码", "金额"]
    elif operation == "column":
        assert runtime.collect_table_column_values("金额", **kw) == ["10", "20"]
    elif operation == "row":
        assert runtime.collect_table_row_values(match, ["金额"], **kw) == {"金额": "10"}
    elif operation == "snapshot":
        assert len(runtime.collect_table_assertion_rows(**kw)["rows"]) == 2
    elif operation == "match":
        runtime.select_table_row(match, **kw)
    elif operation == "index":
        runtime.select_table_row_by_index(1, **kw)
    elif operation == "indices":
        runtime.select_table_rows_by_indices([1, 2], **kw)
    elif operation == "all":
        runtime.select_all_table_rows(**kw)
    elif operation == "hover":
        runtime.focus_table_row(match, **kw)
    elif operation == "hover_index":
        runtime.focus_table_row_by_index(1, **kw)
    elif operation == "link":
        runtime.click_table_cell_link(column="编码", match=match, **kw)
        assert document.evaluate("window.linkClicked") is True
    if operation in {"match", "index", "indices", "all"}:
        assert document.locator("tbody input").first.is_checked()
    assert scope.to_dict()["runtime_fieldid"] == "ACTUAL"


def test_table_scope_refreshes_between_resolution_and_first_consumer(_popup_reference_page) -> None:
    page = _popup_reference_page
    runtime, scope = _resolved_alias_table(page)
    page.locator('[fieldid="ACTUAL"]').evaluate('''node => {
      const replacement = node.cloneNode(true);
      replacement.removeAttribute('data-ydf-table-scope-token');
      node.replaceWith(replacement);
    }''')
    assert runtime.collect_table_column_values("金额", table_scope=scope) == ["10", "20"]


def test_table_scope_does_not_replay_selection_after_dom_replacement(_popup_reference_page) -> None:
    page = _popup_reference_page
    runtime, scope = _resolved_alias_table(page)
    page.evaluate('''() => {
      window.selectionCount = 0;
      document.querySelector('tbody input').onchange = () => {
        window.selectionCount++;
        const root = document.querySelector('[fieldid="ACTUAL"]');
        const replacement = root.cloneNode(true);
        replacement.removeAttribute('data-ydf-table-scope-token');
        root.replaceWith(replacement);
      };
    }''')
    with pytest.raises(RuntimeError, match="作用域.*失效"):
        runtime.select_table_rows_by_indices([1, 2], table_scope=scope)
    assert page.evaluate("window.selectionCount") == 1
    assert not page.locator('tbody input').nth(1).is_checked()


@pytest.mark.parametrize("change", ["duplicate_token", "background", "disabled"])
def test_table_scope_token_rejects_changed_interaction_context(_popup_reference_page, change) -> None:
    page = _popup_reference_page
    runtime, scope = _resolved_alias_table(page)
    assert runtime.collect_table_column_values("金额", table_scope=scope) == ["10", "20"]
    if change == "duplicate_token":
        page.locator('[fieldid="ACTUAL"]').evaluate('(node) => document.body.append(node.cloneNode(true))')
    elif change == "background":
        page.evaluate('''() => { const modal = document.createElement('div'); modal.setAttribute('role', 'dialog');
            modal.textContent = '前景'; document.body.append(modal); }''')
    else:
        page.locator('[fieldid="ACTUAL"]').evaluate('(node) => node.setAttribute("aria-disabled", "true")')
    assert runtime.is_table_scope_token_valid(scope.token) is False
    with pytest.raises(RuntimeError):
        runtime.select_table_row_by_index(1, table_scope=scope)
    assert not page.locator('tbody input').first.is_checked()


def test_table_scope_plain_table_never_absorbs_split_sibling(_popup_reference_page) -> None:
    from ydf_browser.table_scope import RuntimeTableScopeAdapter, TableScopeRequest, TableScopeResolver

    page = _popup_reference_page
    page.set_content('''
      <div fieldid="DETAIL" class="ant-table"><table><thead><tr><th>金额</th></tr></thead>
        <tbody><tr><td>10</td></tr></tbody></table></div>
      <div fieldid="OTHER" class="ant-table-body"><table><thead><tr><th>金额</th></tr></thead>
        <tbody><tr><td>999</td></tr></tbody></table></div>
    ''')
    runtime = _build_runtime()
    runtime._page = page
    region = Region("DETAIL", "DETAIL", "费用明细", "main_table", "table", "Table", None, True, 0)
    scope = TableScopeResolver(RuntimeTableScopeAdapter(runtime)).resolve_for_execution(
        PageManifest(PageMeta("page", None, None, None), regions=[region]),
        TableScopeRequest(target="DETAIL", required_columns=("金额",)),
    )
    assert runtime.collect_table_column_values("金额", table_scope=scope) == ["10"]


def test_scoped_add_row_never_clicks_sibling_button(_popup_reference_page, monkeypatch) -> None:
    page = _popup_reference_page
    runtime, scope = _resolved_alias_table(page)
    page.evaluate('''() => {
      document.body.style.paddingTop = '100px';
      window.siblingClicks = 0;
      document.body.insertAdjacentHTML('beforeend', `<section><h3>明细表</h3>
        <div class="ant-table" fieldid="SIBLING"><table><thead><tr><th>编码</th><th>金额</th></tr></thead>
        <tbody><tr><td>C</td><td>999</td></tr></tbody></table>
        <div class="ant-table-footer"><button onclick="window.siblingClicks++">新增</button></div></div></section>`);
    }''')
    monkeypatch.setattr(page, 'wait_for_timeout', lambda _ms: None)
    try:
        runtime.add_editable_table_row(table_scope=scope)
    except RuntimeError:
        pass
    assert page.evaluate('window.siblingClicks') == 0


@pytest.mark.parametrize("button_identity", ["TEMPLATE", "ACTUAL"])
def test_scoped_add_row_accepts_unique_owned_external_button(_popup_reference_page, button_identity) -> None:
    page = _popup_reference_page
    runtime, scope = _resolved_alias_table(page)
    page.evaluate('''identity => {
      document.body.style.paddingTop = '100px';
      document.body.insertAdjacentHTML('beforeend', `<button fieldid="${identity}_add_button"
        onclick="document.querySelector('tbody').insertAdjacentHTML('beforeend', '<tr><td></td><td>C</td><td>30</td></tr>')">新增</button>`);
    }''', button_identity)
    runtime.add_editable_table_row(table_scope=scope)
    assert runtime.collect_table_column_values("金额", table_scope=scope) == ["10", "20", "30"]


def test_table_scope_missing_body_never_absorbs_identified_sibling(_popup_reference_page) -> None:
    from ydf_browser.table_scope import RuntimeTableScopeAdapter, TableScopeRequest, TableScopeResolver

    page = _popup_reference_page
    page.set_content('''<section id="container">
      <div class="ant-table" fieldid="DETAIL"><div class="ant-table-header">
        <table><thead><tr><th>金额</th></tr></thead></table></div></div>
      <div class="ant-table" fieldid="OTHER"><div class="ant-table-body">
        <table><thead><tr><th>金额</th></tr></thead><tbody><tr><td>999</td></tr></tbody></table>
      </div></div></section>''')
    runtime = _build_runtime()
    runtime._page = page
    region = Region("DETAIL", "DETAIL", "费用明细", "main_table", "table", "Table", None, True, 0)
    scope = TableScopeResolver(RuntimeTableScopeAdapter(runtime)).resolve_for_execution(
        PageManifest(PageMeta("page", None, None, None), regions=[region]),
        TableScopeRequest(target="DETAIL", required_columns=("金额",)),
    )
    assert not page.locator('#container').get_attribute('data-ydf-table-scope-token')
    assert runtime.collect_table_column_values("金额", table_scope=scope) == []


@pytest.mark.parametrize("in_frame", [False, True])
def test_dialog_button_waits_for_delayed_confirmation(_popup_reference_page, monkeypatch, in_frame) -> None:
    page = _popup_reference_page
    page.set_content('<iframe style="width:800px;height:500px"></iframe>' if in_frame else '')
    context = page.frames[-1] if in_frame else page
    context.set_content('''
        <div class="wui-modal wui-modal-open ac-confirm" role="dialog"
             style="display:none;position:absolute;top:120px">
          <button class="wui-button wui-modal-ok-button" onclick="this.closest('[role=dialog]').remove()">
            <span class="wui-button-text-wrap">确定</span>
          </button>
        </div>
    ''')
    runtime = _build_runtime()
    runtime._page = page
    monkeypatch.setattr(runtime, "_collect_page_diagnostic_text", lambda: "delayed confirmation")
    monkeypatch.setattr(runtime, "_save_diagnostic_screenshot", lambda *_: None)
    context.evaluate("setTimeout(() => document.querySelector('[role=dialog]').style.display = 'block', 600)")

    runtime.click_dialog_button("确定")

    assert context.locator('[role="dialog"]').count() == 0


def test_dialog_button_missing_exhausts_bounded_wait(monkeypatch) -> None:
    runtime = _build_runtime()
    now = [0.0]
    waits = []

    def poll(milliseconds):
        waits.append(milliseconds)
        now[0] += milliseconds / 1000

    runtime._page = SimpleNamespace(wait_for_timeout=poll)
    monkeypatch.setattr(runtime_module, "time", SimpleNamespace(monotonic=lambda: now[0]))
    monkeypatch.setattr(runtime, "_find_first_visible_selector", lambda *_: None)
    monkeypatch.setattr(runtime, "_collect_page_diagnostic_text", lambda: "missing")
    monkeypatch.setattr(runtime, "_save_diagnostic_screenshot", lambda *_: None)

    with pytest.raises(RuntimeError, match="未找到可点击弹窗按钮: 确定"):
        runtime.click_dialog_button("确定")

    assert 10 <= now[0] < 10.1
    assert all(0 < value <= 100 for value in waits)


def test_manual_cookie_sync_does_not_hide_non_closure_errors():
    runtime = _build_runtime()
    def fail():
        raise RuntimeError("cookie read failed")
    runtime.session._ydf_cookie_bridge = SimpleNamespace(pull=fail)
    with pytest.raises(RuntimeError, match="cookie read failed"):
        runtime.sync_manual_session_cookies()


@pytest.mark.parametrize("layout", ["unique", "duplicate", "controls"])
@pytest.mark.parametrize("component", ["YDFInput", "YDFSelect"])
def test_readonly_form_identity_uses_unique_dom_root(_popup_reference_page, layout, component):
    from ydf_browser.binder import bind_manifest, bind_runtime_readable_form_field

    page = _popup_reference_page
    content = '''<div role="dialog"><div uikey="expert_name">
      <div class="ant-form-item-label"><label title="姓名">姓名</label></div><div class="ant-form-item-control"><div class="dis-editable">专家姓名回读</div></div>
    </div></div>'''
    if component == "YDFSelect":
        content = content.replace('class="dis-editable"', 'class="ant-select dis-editable"')
    page.set_content(content * (2 if layout == "duplicate" else 1))
    if layout == "controls":
        page.locator('[uikey="expert_name"]').evaluate('''node => {
          node.insertAdjacentHTML('beforeend', '<input fieldid="first" readonly value="A"><input fieldid="second" readonly value="B">');
        }''')
    runtime = _build_runtime()
    runtime._page = page
    candidate = ElementCandidate(
        key="name", fieldid="expertName", label="姓名", title="姓名", region_key=None,
        region_fieldid=None, element_type="formItem", component_name=component,
        runtime_fieldids=["expertName", "expert_name"], verified_runtime_fieldids=["expert_name"],
    )
    manifest = PageManifest(PageMeta("detail", None, None, None), fields=[candidate])
    elements = runtime.capture_runtime_elements(manifest)
    assert not bind_manifest(manifest, elements).bound_fields
    bound = bind_runtime_readable_form_field([candidate], elements)
    if layout != "unique":
        assert bound is None
    else:
        assert bound is not None
        assert runtime.read_field_value(bound) == "专家姓名回读"
