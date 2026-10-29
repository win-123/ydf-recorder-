import json
import time
from dataclasses import dataclass, field
from typing import Any
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import pytest

import ydf_browser.executor as executor_module
from ydf_browser.action_completion import (
    ActionCompletionObservation,
    ActionCompletionRequest,
    ActionNotification,
)
from ydf_browser.dsl import load_dsl, load_dsl_document_from_file
from ydf_browser.binder import bind_manifest
from ydf_browser.executor import WorkflowExecutor, _values_match
from ydf_browser.gateway import MenuTarget
from ydf_browser.menu_opening import MenuOpening
from ydf_browser.models import ActionStep
from ydf_browser.observation import ObservationSession
from ydf_browser.runtime import PlaywrightRuntime
from ydf_browser.template_parser import build_page_manifest
from ydf_browser.variables import RuntimeVariableContext


@dataclass
class FakeGateway:
    template_payload: dict
    menu_target: MenuTarget = field(
        default_factory=lambda: MenuTarget(
            menu_code="PM_INIT",
            menu_name="项目立项",
            path=["项目管理", "项目立项"],
            service_code="global00_-1_PM_INIT",
            page_code="PM_INIT",
            biz_obj_code="pmProjectInfo",
        )
    )

    def resolve_menu(self, menu_path: str, timeout_seconds: float | None = None) -> MenuTarget:
        assert menu_path == "项目管理>>项目立项"
        return self.menu_target

    def fetch_template(self, menu_target: MenuTarget, timeout_seconds: float | None = None) -> dict:
        assert menu_target.menu_code == "PM_INIT"
        return self.template_payload


def _add_main_table_columns(template_payload: dict, *labels: str) -> None:
    table = next(
        child
        for child in template_payload["data"]["uidata"][0]["children"]
        if str(child.get("nodeType") or "").lower() == "table"
    )
    existing = {str(child.get("label") or "") for child in table.get("children") or []}
    for index, label in enumerate(labels):
        if label in existing:
            continue
        table.setdefault("children", []).append(
            {
                "key": f"scope_test_column_{index}",
                "divCode": f"scope_test_column_{index}",
                "nodeType": "column",
                "label": label,
                "name": "TableColumn",
                "dataField": f"scopeTestColumn{index}",
            }
        )


def _without_timing(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if key != "timing"}


def _record_json_response(
    observation: ObservationSession,
    *,
    request_key: int,
    original_url: str,
    actual_url: str,
    body: dict[str, Any],
    status: int = 200,
    forwarding: dict[str, Any] | None = None,
) -> str | None:
    request_id = observation.network_request_started(
        request_key=request_key,
        original_url=original_url,
        actual_url=actual_url,
        base_url="https://dv5-ydf.yonyougov.top",
        resource_type="xhr",
        method="POST",
        headers={"content-type": "application/json"},
        body=b"{}",
        forwarding=forwarding,
    )
    observation.network_request_completed(
        request_key=request_key,
        actual_url=actual_url,
        status=status,
        headers={"content-type": "application/json"},
        body=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        forwarding=forwarding,
    )
    return request_id


@dataclass
class FakeRuntime:
    menu_opening_work_surfaces = False

    runtime_elements: list[dict]
    runtime_elements_by_page: dict[str, list[dict]] = field(default_factory=dict)
    next_dynamic_template_payload: dict | None = None
    dynamic_template_payloads_by_toolbar_click: dict[str, dict] = field(default_factory=dict)
    dynamic_template_payloads_by_dialog_click: dict[str, dict] = field(default_factory=dict)
    dynamic_template_payloads_by_row_action: dict[str, dict] = field(default_factory=dict)
    dynamic_template_payloads_by_editable_table_add: dict[str, dict] = field(default_factory=dict)
    field_values: dict[str, str] = field(default_factory=dict)
    raw_filled_fields: list[dict[str, Any]] = field(default_factory=list)
    opened_menu: MenuTarget | None = None
    clicked_targets: list[str] = field(default_factory=list)
    clicked_fieldids: list[str] = field(default_factory=list)
    row_action_clicks: list[str] = field(default_factory=list)
    table_cell_link_clicks: list[dict[str, Any]] = field(default_factory=list)
    filled_fields: list[dict[str, str]] = field(default_factory=list)
    query_filled_fields: list[dict[str, str]] = field(default_factory=list)
    table_column_values: dict[str, list[str]] = field(default_factory=dict)
    table_snapshot_rows: list[dict[str, Any]] = field(default_factory=list)
    table_column_collections: list[dict[str, Any]] = field(default_factory=list)
    table_row_collections: list[dict[str, Any]] = field(default_factory=list)
    table_headers: list[str] = field(default_factory=list)
    table_header_collections: list[dict[str, Any]] = field(default_factory=list)
    validated_menu_names: list[str] = field(default_factory=list)
    prepared_manifest_keys: list[str] = field(default_factory=list)
    selected_tree_nodes: list[dict[str, Any]] = field(default_factory=list)
    selected_tree_shortcuts: list[dict[str, Any]] = field(default_factory=list)
    focused_rows: list[dict] = field(default_factory=list)
    selected_rows: list[dict] = field(default_factory=list)
    selected_row_numbers: list[int | dict[str, Any]] = field(default_factory=list)
    selected_all_tables: list[dict[str, Any]] = field(default_factory=list)
    dialog_clicks: list[dict[str, Any]] = field(default_factory=list)
    tab_clicks: list[dict[str, str | None]] = field(default_factory=list)
    notifications: list[dict[str, str]] = field(default_factory=list)
    notification_capture_count: int = 0
    notification_close_calls: list[dict[str, str]] = field(default_factory=list)
    notification_close_result: dict[str, Any] = field(default_factory=dict)
    import_uploads: list[dict[str, Any]] = field(default_factory=list)
    import_template_downloads: list[dict[str, Any]] = field(default_factory=list)
    amount_unit_sets: list[dict[str, Any]] = field(default_factory=list)
    editable_table_adds: list[dict[str, Any]] = field(default_factory=list)
    editable_table_fills: list[dict[str, Any]] = field(default_factory=list)
    attachment_uploads: list[list[dict[str, str]]] = field(default_factory=list)
    attachment_upload_candidates: list[list[dict[str, Any]]] = field(default_factory=list)
    transfer_dialog_selections: list[dict[str, Any]] = field(default_factory=list)
    popup_reference_selections: list[dict[str, Any]] = field(default_factory=list)
    toolbar_click_details: list[dict[str, Any]] = field(default_factory=list)
    query_click_details: list[dict[str, Any]] = field(default_factory=list)
    query_reset_calls: list[list[str]] = field(default_factory=list)
    bpr_starts: list[dict[str, Any]] = field(default_factory=list)
    bpr_stops: list[dict[str, Any]] = field(default_factory=list)
    next_import_upload_result: dict[str, Any] = field(default_factory=dict)
    next_import_template_download_result: dict[str, Any] = field(default_factory=dict)
    expanded_query_count: int = 0
    should_validate: bool = True
    should_find_tree: bool = True
    should_find_row: bool = True
    should_select_row: bool = True
    should_find_row_number: bool = True
    visible_region_fieldids: set[str] | None = None
    network_summaries: list[dict[str, Any]] = field(default_factory=list)
    page_memory: dict[str, Any] = field(
        default_factory=lambda: {
            "available": True,
            "used_js_heap_size": 10485760,
            "unavailable_reason": "",
        }
    )
    menu_hosting: dict[str, Any] = field(default_factory=lambda: {"mode": "direct"})
    action_completion_observations: list[ActionCompletionObservation] = field(default_factory=list)
    action_completion_events: list[dict[str, Any]] = field(default_factory=list)
    action_completion_clock: float = 0.0
    action_completion_active: bool = False
    action_completion_current: ActionCompletionObservation | None = None
    action_completion_default: ActionCompletionObservation = field(
        default_factory=lambda: ActionCompletionObservation(dom_signal="fixture_state")
    )

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

    def inspect_menu_hosting(self, menu_target: MenuTarget) -> dict[str, Any]:
        assert menu_target is self.opened_menu
        return dict(self.menu_hosting)

    def wait_for_first_visible(self, selectors: list[str], timeout_ms: int) -> bool:
        return self.should_validate

    def current_page_url(self) -> str:
        return "fixture://page"

    def reload_page(self) -> None:
        return

    def page_frame_states(self) -> list[dict[str, Any]]:
        if self.menu_hosting.get("mode") != "iframe":
            return [{"name": "", "url": "fixture://page", "is_main": True, "parent_is_main": False}]
        return [
            {"name": "", "url": "fixture://page", "is_main": True, "parent_is_main": False},
            {
                "name": self.menu_hosting.get("frame_name", ""),
                "url": self.menu_hosting.get("frame_url", ""),
                "is_main": False,
                "parent_is_main": True,
            },
        ]

    def collect_network_summary(self, reset: bool = False) -> dict[str, Any]:
        summary = self.network_summaries.pop(0) if self.network_summaries else {"request_count": 0, "failed_count": 0}
        summary["reset"] = reset
        return summary

    def capture_page_memory(self) -> dict[str, Any]:
        return dict(self.page_memory)

    def start_bpr(
        self,
        *,
        index: int | None = None,
        name: str = "",
        description: str = "",
        control_step: int | None = None,
    ) -> dict[str, Any]:
        payload = {
            "index": index,
            "name": name,
            "description": description,
            "start_control_step": control_step,
            "bpr_id": f"fake-bpr-{index}",
            "start_ts": 1000 * int(index or 1),
        }
        self.bpr_starts.append(payload)
        return payload

    def stop_bpr(self, session: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "bpr_id": session.get("bpr_id"),
            "end_ts": int(session.get("start_ts") or 0) + 250,
            "report_url": f"https://example.yonyougov.top/iuap-ymc-server/proxy/server/bpr/open?pk={session.get('bpr_id')}",
        }
        self.bpr_stops.append(dict(session))
        return payload

    def ensure_menu_tab(self, menu_target: MenuTarget) -> None:
        self.validated_menu_names.append(menu_target.menu_name)
        if not self.should_validate:
            raise RuntimeError(f"菜单页签校验失败: {menu_target.menu_name}")

    def prepare_binding(self, manifest) -> None:
        self.prepared_manifest_keys.append(manifest.page.fieldid)

    def expand_query_conditions(self) -> bool:
        self.expanded_query_count += 1
        return True

    def capture_runtime_elements(self, manifest) -> list[dict]:
        assert manifest.page.biz_obj_code == "pmProjectInfo"
        runtime_elements = list(self.runtime_elements_by_page.get(manifest.page.fieldid, self.runtime_elements))
        if self.focused_rows:
            runtime_elements.append(
                {
                    "fieldid": "xq_btn",
                    "id": None,
                    "name": None,
                    "placeholder": None,
                    "text": "详情",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="xq_btn"]',
                }
            )
        return runtime_elements

    def pop_dynamic_template_payload(self) -> dict | None:
        payload = self.next_dynamic_template_payload
        self.next_dynamic_template_payload = None
        return payload

    def pop_dynamic_template_payload_if_current(self, expected: dict) -> dict | None:
        if self.next_dynamic_template_payload is not expected:
            return None
        return self.pop_dynamic_template_payload()

    def peek_dynamic_template_payload(self) -> dict | None:
        return self.next_dynamic_template_payload

    def click_toolbar_action(
        self,
        label: str,
        sub_label: str | None = None,
        fieldid: str | None = None,
        aliases: list[str] | None = None,
    ) -> None:
        target = f"{label}>{sub_label}" if sub_label else label
        self.clicked_targets.append(target)
        self.toolbar_click_details.append(
            {
                "label": label,
                "sub_label": sub_label,
                "fieldid": fieldid,
                "aliases": aliases or [],
            }
        )
        dynamic_key = target if target in self.dynamic_template_payloads_by_toolbar_click else label
        if dynamic_key in self.dynamic_template_payloads_by_toolbar_click:
            self.next_dynamic_template_payload = self.dynamic_template_payloads_by_toolbar_click[dynamic_key]

    def click_tab_action(self, label: str, fieldid: str | None = None) -> None:
        self.tab_clicks.append({"label": label, "fieldid": fieldid})
        self.clicked_targets.append(label)

    def click_action_by_fieldid(self, fieldid: str) -> None:
        self.clicked_fieldids.append(fieldid)
        if fieldid in self.dynamic_template_payloads_by_toolbar_click:
            self.next_dynamic_template_payload = self.dynamic_template_payloads_by_toolbar_click[fieldid]

    def fill_field(self, bound_element, value: str) -> None:
        self.raw_filled_fields.append({"fieldid": bound_element.candidate.fieldid, "value": value})
        self.filled_fields.append({"fieldid": bound_element.candidate.fieldid, "value": str(value)})
        self.field_values[bound_element.candidate.fieldid] = str(value)

    def fill_form_field(self, bound_element, value: str) -> None:
        self.fill_field(bound_element, value)

    def fill_query_field(self, bound_element, value: str) -> None:
        self.query_filled_fields.append({"fieldid": bound_element.candidate.fieldid, "value": str(value)})

    def click_query_action(self, label: str = "查询", fieldids: list[str] | None = None) -> None:
        self.clicked_targets.append(label)
        self.query_click_details.append({"label": label, "fieldids": fieldids or []})

    def click_query_reset(self, query_region_fieldids: list[str]) -> dict[str, str]:
        self.query_reset_calls.append(list(query_region_fieldids))
        return {
            "query_region_fieldid": query_region_fieldids[0],
            "button": "重置",
            "locator_source": "exact_text",
        }

    def collect_table_column_values(
        self,
        column: str,
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        table_scope=None,
    ) -> list[str]:
        if table_scope is not None:
            table = table_scope.current.label
            table_fieldid = table_scope.current.region_fieldid
            table_columns = list(table_scope.current.columns)
        self.table_column_collections.append(
            {
                "column": column,
                "table": table,
                "table_fieldid": table_fieldid,
                "table_columns": table_columns,
            }
        )
        return self.table_column_values.get(column, [])

    def collect_table_assertion_rows(self, **_kwargs: Any) -> dict[str, Any]:
        return {
            "rows": list(self.table_snapshot_rows),
            "identity_columns": ["项目编码"],
            "pagination": {"current_page": 1},
            "empty_state": not self.table_snapshot_rows,
        }

    def collect_table_row_values(
        self,
        match: dict[str, Any],
        columns: list[str],
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        table_scope=None,
    ) -> dict[str, str]:
        if table_scope is not None:
            table = table_scope.current.label
            table_fieldid = table_scope.current.region_fieldid
            table_columns = list(table_scope.current.columns)
        self.focused_rows.append(match)
        self.table_row_collections.append(
            {
                "match": match,
                "columns": columns,
                "table": table,
                "table_fieldid": table_fieldid,
                "table_columns": table_columns,
            }
        )
        return {column: self.table_column_values.get(column, [""])[0] for column in columns}

    def collect_table_headers(
        self,
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        table_scope=None,
    ) -> list[str]:
        if table_scope is not None:
            table = table_scope.current.label
            table_fieldid = table_scope.current.region_fieldid
            table_columns = list(table_scope.current.columns)
        self.table_header_collections.append(
            {
                "table": table,
                "table_fieldid": table_fieldid,
                "table_columns": table_columns,
            }
        )
        return list(self.table_headers)

    def collect_notifications(self) -> list[dict[str, str]]:
        return self.notifications

    def begin_notification_capture(self) -> None:
        self.notification_capture_count += 1

    def _acquire_action_completion(self) -> None:
        if self.action_completion_active:
            raise RuntimeError("已有动作正在等待完成")
        self.action_completion_active = True

    def _release_action_completion(self) -> None:
        self.action_completion_active = False

    def _prepare_action_completion(self, request: ActionCompletionRequest) -> None:
        self.action_completion_current = None
        self.action_completion_events.append(
            {"event": "prepare", "action": request.action, "context": dict(request.context)}
        )
        self.begin_notification_capture()

    def _observe_action_completion(
        self,
        request: ActionCompletionRequest,
        stage: str = "",
    ) -> ActionCompletionObservation:
        self.action_completion_events.append(
            {"event": "observe", "action": request.action, "stage": stage or "all"}
        )
        if self.action_completion_current is None:
            if self.action_completion_observations:
                self.action_completion_current = self.action_completion_observations.pop(0)
            else:
                notifications = tuple(
                    ActionNotification(
                        type=str(item.get("type") or "info"),
                        message=str(item.get("message") or ""),
                    )
                    for item in self.collect_notifications()
                )
                self.action_completion_current = ActionCompletionObservation(
                    notifications=notifications,
                    dynamic_template=self.action_completion_default.dynamic_template,
                    dynamic_template_fallback=self.action_completion_default.dynamic_template_fallback,
                    dom_signal=self.action_completion_default.dom_signal,
                )
        observation = self.action_completion_current
        if stage == "notifications":
            return ActionCompletionObservation(notifications=observation.notifications)
        if stage == "dynamic_template":
            return ActionCompletionObservation(
                dynamic_template=observation.dynamic_template,
                dynamic_template_fallback=observation.dynamic_template_fallback,
            )
        if stage == "dom":
            self.action_completion_current = None
            return ActionCompletionObservation(dom_signal=observation.dom_signal)
        self.action_completion_current = None
        return observation

    def _action_completion_now(self) -> float:
        return self.action_completion_clock

    def _wait_action_completion_poll(self, timeout_ms: int) -> None:
        self.action_completion_events.append({"event": "wait", "timeout_ms": timeout_ms})
        self.action_completion_clock += timeout_ms / 1000

    def close_notification(
        self,
        *,
        expected_type: str = "",
        contains: str = "",
        equals: str = "",
        message: str = "",
        label: str = "",
    ) -> dict[str, Any]:
        payload = {
            "expected_type": expected_type,
            "contains": contains,
            "equals": equals,
            "message": message,
            "label": label,
        }
        self.notification_close_calls.append(payload)
        result = self.notification_close_result or {
            "closed_notification": {"type": expected_type or "error", "message": contains or message or equals},
            "remaining_notifications": [],
            "close_action": "close-icon",
        }
        self.notifications = list(result.get("remaining_notifications") or [])
        return result

    def select_tree_node(self, label: str, tree_fieldid: str | None = None) -> None:
        self.selected_tree_nodes.append({"label": label, "tree_fieldid": tree_fieldid})
        if not self.should_find_tree:
            raise RuntimeError(f"未找到树节点: {label}")

    def select_tree_root(self, tree_fieldid: str | None = None) -> str:
        self.selected_tree_shortcuts.append({"node": "root", "tree_fieldid": tree_fieldid})
        if not self.should_find_tree:
            raise RuntimeError("未找到树节点: root")
        return "001 办公室"

    def select_first_tree_leaf(self, tree_fieldid: str | None = None) -> str:
        self.selected_tree_shortcuts.append({"node": "first_leaf", "tree_fieldid": tree_fieldid})
        if not self.should_find_tree:
            raise RuntimeError("未找到树节点: first_leaf")
        return "001001 秘书处"

    def is_region_visible(self, fieldid: str) -> bool:
        if self.visible_region_fieldids is None:
            return True
        return fieldid in self.visible_region_fieldids

    def focus_table_row(
        self,
        match: dict[str, str],
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        table_scope=None,
    ) -> None:
        if table_scope is not None:
            table = table_scope.current.label
            table_fieldid = table_scope.current.region_fieldid
            table_columns = list(table_scope.current.columns)
        payload = dict(match)
        if table:
            payload["table"] = table
        if table_fieldid:
            payload["table_fieldid"] = table_fieldid
        if table_columns:
            payload["table_columns"] = table_columns
        self.focused_rows.append(payload)
        if not self.should_find_row:
            raise RuntimeError(f"未找到表格行: {match}")

    def focus_table_row_by_index(
        self,
        row_number: int,
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        table_scope=None,
    ) -> None:
        if table_scope is not None:
            table = table_scope.current.label
            table_fieldid = table_scope.current.region_fieldid
            table_columns = list(table_scope.current.columns)
        payload: dict[str, Any] = {"row_number": row_number}
        if table:
            payload["table"] = table
        if table_fieldid:
            payload["table_fieldid"] = table_fieldid
        if table_columns:
            payload["table_columns"] = table_columns
        self.focused_rows.append(payload)
        if not self.should_find_row_number:
            raise RuntimeError(f"未找到表格行: {row_number}")

    def select_table_row(
        self,
        match: dict[str, str],
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        table_scope=None,
    ) -> None:
        if table_scope is not None:
            table = table_scope.current.label
            table_fieldid = table_scope.current.region_fieldid
            table_columns = list(table_scope.current.columns)
        payload = dict(match)
        if table:
            payload["table"] = table
        if table_fieldid:
            payload["table_fieldid"] = table_fieldid
        if table_columns:
            payload["table_columns"] = table_columns
        self.selected_rows.append(payload)
        if not self.should_select_row:
            raise RuntimeError(f"未找到表格行选择框: {match}")

    def select_table_row_by_index(
        self,
        row_number: int,
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        table_scope=None,
    ) -> None:
        if table_scope is not None:
            table = table_scope.current.label
            table_fieldid = table_scope.current.region_fieldid
            table_columns = list(table_scope.current.columns)
        if table or table_fieldid:
            self.selected_row_numbers.append(
                {
                    "row_number": row_number,
                    "table": table,
                    "table_fieldid": table_fieldid,
                    "table_columns": table_columns,
                }
            )
        else:
            self.selected_row_numbers.append(row_number)
        if not self.should_select_row:
            raise RuntimeError(f"未找到表格行选择框: {row_number}")

    def select_table_rows_by_indices(
        self,
        row_numbers: list[int],
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        table_scope=None,
    ) -> None:
        if table_scope is not None:
            table = table_scope.current.label
            table_fieldid = table_scope.current.region_fieldid
            table_columns = list(table_scope.current.columns)
        for row_number in row_numbers:
            self.select_table_row_by_index(
                row_number,
                table=table,
                table_fieldid=table_fieldid,
                table_columns=table_columns,
            )

    def select_all_table_rows(
        self,
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        table_scope=None,
    ) -> None:
        if table_scope is not None:
            table = table_scope.current.label
            table_fieldid = table_scope.current.region_fieldid
            table_columns = list(table_scope.current.columns)
        self.selected_all_tables.append(
            {
                "table": table,
                "table_fieldid": table_fieldid,
                "table_columns": table_columns,
            }
        )
        if not self.should_select_row:
            raise RuntimeError("未找到表头全选 checkbox")

    def click_row_action(self, action_label: str) -> None:
        self.row_action_clicks.append(action_label)
        self.clicked_targets.append(action_label)
        if action_label in self.dynamic_template_payloads_by_row_action:
            self.next_dynamic_template_payload = self.dynamic_template_payloads_by_row_action[action_label]

    def click_table_cell_link(
        self,
        *,
        column: str,
        match: dict[str, Any] | None = None,
        row_number: int | None = None,
        link_text: str | None = None,
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        table_scope=None,
    ) -> dict[str, Any]:
        if table_scope is not None:
            table = table_scope.current.label
            table_fieldid = table_scope.current.region_fieldid
            table_columns = list(table_scope.current.columns)
        payload = {
            "column": column,
            "match": match,
            "row_number": row_number,
            "link_text": link_text,
            "table": table,
            "table_fieldid": table_fieldid,
            "table_columns": table_columns,
        }
        self.table_cell_link_clicks.append(payload)
        self.clicked_targets.append(f"cell-link:{column}")
        self.next_dynamic_template_payload = self.dynamic_template_payloads_by_toolbar_click.get("cell-link") or None
        return {"column": column, "link_text": link_text, "clicked_text": link_text or "202600000000060"}

    def click_dialog_button(self, label: str, expect_download: bool = False) -> None:
        self.dialog_clicks.append({"label": label, "expect_download": expect_download})
        if label in self.dynamic_template_payloads_by_dialog_click:
            self.next_dynamic_template_payload = self.dynamic_template_payloads_by_dialog_click[label]

    def import_upload(self, label: str, files: list[str]) -> dict[str, Any]:
        self.import_uploads.append({"label": label, "files": files})
        if self.next_import_upload_result:
            return self.next_import_upload_result
        return {
            "files": files,
            "import_results": [{"file": file, "status": "success", "message": "导入完成"} for file in files],
        }

    def import_download_template(self, label: str, template: str | None = None) -> dict[str, Any]:
        self.import_template_downloads.append({"label": label, "template": template})
        if self.next_import_template_download_result:
            return self.next_import_template_download_result
        return {"template": template, "downloaded_files": ["/Users/ken/Downloads/template.xlsx"]}

    def set_amount_unit(
        self,
        value: str,
        action_candidates: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self.amount_unit_sets.append({"value": value, "action_candidates": action_candidates or []})
        return {"actual_value": value}

    def add_editable_table_row(
        self,
        label: str = "新增",
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        table_scope=None,
    ) -> dict[str, Any]:
        if table_scope is not None:
            table = table_scope.current.label
            table_fieldid = table_scope.current.region_fieldid
            table_columns = list(table_scope.current.columns)
        payload = {"label": label, "table": table, "row_number": -1}
        if table_fieldid:
            payload["table_fieldid"] = table_fieldid
        if table_columns:
            payload["table_columns"] = table_columns
        self.editable_table_adds.append(payload)
        table_key = f"{table}>{label}" if table else label
        dynamic_key = table_key if table_key in self.dynamic_template_payloads_by_editable_table_add else label
        if dynamic_key in self.dynamic_template_payloads_by_editable_table_add:
            self.next_dynamic_template_payload = self.dynamic_template_payloads_by_editable_table_add[dynamic_key]
        return payload

    def fill_editable_table_row(
        self,
        values: Any,
        row_number: int = -1,
        table: str | None = None,
        column_candidates: dict[str, Any] | None = None,
        table_scope=None,
    ) -> dict[str, Any]:
        if table_scope is not None:
            table = table_scope.current.label
        payload = {"values": values, "row_number": row_number, "table": table}
        if column_candidates is not None:
            payload["column_candidates"] = column_candidates
        self.editable_table_fills.append(payload)
        fields: list[dict[str, Any]] = []
        for key, column, value in _iter_fake_editable_table_values(values):
            field = {"column": str(column), "value": str(value)}
            candidate = (column_candidates or {}).get(str(key)) or (column_candidates or {}).get(str(column))
            if candidate is not None:
                field.update(
                    {
                        "fieldid": getattr(candidate, "fieldid", ""),
                        "data_field": getattr(candidate, "data_field", ""),
                        "table_fieldid": getattr(candidate, "region_fieldid", ""),
                        "locator_source": "identity-cell",
                    }
                )
            fields.append(field)
        return {**payload, "fields": fields}

    def upload_attachments(
        self,
        attachments: list[dict[str, str]],
        attachment_candidates: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self.attachment_uploads.append(attachments)
        self.attachment_upload_candidates.append(list(attachment_candidates or []))
        return {"attachments": [{"type": item["type"], "file": item["file"], "status": "success"} for item in attachments]}

    def select_transfer_dialog(
        self,
        *,
        title: str | None = None,
        items: list[dict[str, Any]] | None = None,
        move: str = "to_right",
        confirm: bool = True,
    ) -> dict[str, Any]:
        payload = {
            "title": title,
            "items": items or [],
            "move": move,
            "confirm": confirm,
        }
        self.transfer_dialog_selections.append(payload)
        return {"selected": payload["items"], "moved": len(payload["items"])}

    def select_popup_reference(
        self,
        *,
        title: str | None = None,
        target: dict[str, Any] | None = None,
        confirm: bool = True,
    ) -> dict[str, Any]:
        payload = {
            "title": title,
            "target": target or {},
            "confirm": confirm,
        }
        self.popup_reference_selections.append(payload)
        return {"selected": [target or {}], "confirmed": confirm}

    def read_field_value(self, bound_element) -> str:
        return self.field_values.get(bound_element.candidate.fieldid, "")


@dataclass
class FakeClock:
    now: float = 0.0

    def monotonic(self) -> float:
        return self.now

    def advance_ms(self, timeout_ms: int) -> None:
        self.now += timeout_ms / 1000


@dataclass
class OpenMenuReadinessRuntime(FakeRuntime):
    menu_opening_work_surfaces = True

    surface_snapshots: list[list[dict[str, Any]]] = field(default_factory=list)
    clock: FakeClock | None = None
    surface_capture_count: int = 0

    def _next_surface_snapshot(self) -> list[dict[str, Any]]:
        self.surface_capture_count += 1
        index = min(self.surface_capture_count - 1, len(self.surface_snapshots) - 1)
        return deepcopy(self.surface_snapshots[index]) if self.surface_snapshots else []

    def capture_open_menu_work_surfaces(self, manifest) -> list[dict[str, Any]]:
        return self._next_surface_snapshot()

    def evaluate_all_frames(self, script: str, payload: Any) -> list[dict[str, Any]]:
        return [{"frame_name": "bill", "frame_url": "fixture://bill", "value": self._next_surface_snapshot()}]

    def wait_for_timeout(self, timeout_ms: int) -> None:
        if self.clock is not None:
            self.clock.advance_ms(timeout_ms)


@dataclass
class PageResponseOpenMenuRuntime(OpenMenuReadinessRuntime):
    service_detail_payload: dict[str, Any] | None = None
    initial_template_payload: dict[str, Any] | None = None
    template_error_payload: dict[str, Any] | None = None
    retry_template_payload: dict[str, Any] | None = None
    response_events: list[dict[str, Any]] = field(default_factory=list)
    config: Any = field(
        default_factory=lambda: SimpleNamespace(
            base_url="https://example.test",
            endpoints=SimpleNamespace(
                service_detail="/service/detail",
                templates="/matchingTemplate",
                template_body="/getTemplateBody",
            )
        )
    )

    def begin_page_response_capture(self) -> int:
        self.response_events = []
        self.next_dynamic_template_payload = None
        return 0

    def page_error_cursor(self) -> int:
        return 0

    def page_errors_since(self, cursor: int) -> tuple[int, list[dict[str, Any]]]:
        errors = list(self.collect_open_menu_page_errors())
        return len(errors), errors[cursor:]

    def open_menu(self, menu_target: MenuTarget) -> None:
        super().open_menu(menu_target)
        if self.service_detail_payload is not None:
            self.response_events.append(
                {
                    "method": "GET",
                    "url": "https://example.test/service/detail",
                    "status": 200,
                    "payload": self.service_detail_payload,
                }
            )
        if self.template_error_payload is not None:
            self.response_events.append(
                {
                    "method": "POST",
                    "url": "https://example.test/matchingTemplate",
                    "status": 200,
                    "payload": self.template_error_payload,
                }
            )
        if self.initial_template_payload is not None:
            self._append_template_response(self.initial_template_payload)

    def page_responses_since(self, cursor: int) -> tuple[int, list[dict[str, Any]]]:
        return len(self.response_events), self.response_events[cursor:]

    def wait_for_timeout(self, timeout_ms: int) -> None:
        if self.retry_template_payload is not None:
            self._append_template_response(self.retry_template_payload)
            self.retry_template_payload = None
        super().wait_for_timeout(timeout_ms)

    def _append_template_response(self, payload: dict[str, Any]) -> None:
        self.response_events.append(
            {
                "method": "POST",
                "url": "https://example.test/matchingTemplate",
                "status": 200,
                "payload": payload,
            }
        )


def _browser_executor(gateway: FakeGateway, runtime: PageResponseOpenMenuRuntime, **kwargs: Any) -> WorkflowExecutor:
    now = runtime.clock.monotonic if runtime.clock is not None else time.monotonic
    return WorkflowExecutor(
        gateway=gateway,
        runtime=runtime,
        menu_opening=MenuOpening.for_browser(gateway, runtime, now=now),
        **kwargs,
    )


def _surface(
    key: str,
    region_type: str,
    *,
    busy: int = 0,
    terminal: bool = False,
    signature: str = "",
    empty_content: bool | None = None,
    transition_busy: int | None = None,
    transition_signature: str | None = None,
) -> dict[str, Any]:
    result = {
        "key": key,
        "region_type": region_type,
        "busy": busy,
        "terminal": terminal,
        "signature": signature,
        "error": "",
    }
    if empty_content is not None:
        result["empty_content"] = empty_content
    if transition_busy is not None:
        result["transition_busy"] = transition_busy
    if transition_signature is not None:
        result["transition_signature"] = transition_signature
    return result


def _iter_fake_editable_table_values(values: Any):
    if isinstance(values, dict):
        for column, value in values.items():
            column_label = str(column)
            yield column_label, column_label, value
        return
    for item in values:
        column = str(item.get("column") or item.get("field") or "")
        yield str(item.get("key") or column), column, item.get("value", item.get("equals"))


def test_workflow_executor_executes_toolbar_component_step(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
    sample_dsl_path,
) -> None:
    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=FakeRuntime(sample_runtime_elements),
    )

    document = load_dsl_document_from_file(sample_dsl_path)
    report = executor.run(document.cases[0].steps)

    assert report.success is True
    assert executor.runtime.validated_menu_names == ["项目立项"]
    assert executor.runtime.prepared_manifest_keys == ["root"]
    assert executor.runtime.clicked_targets == ["保存"]
    assert "contract_path" not in report.steps[0].data


def test_workflow_executor_serializes_verified_contract_path_for_form_fill(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime_elements = [
        {**item, "pointer_receivable": True}
        if item.get("fieldid") in {"project_name", "project_code"}
        else item
        for item in sample_runtime_elements
    ]
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=FakeRuntime(runtime_elements))

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "form", "operation": "fill", "target": {"fields": {"项目名称": "契约测试"}}},
        ]
    )

    path = report.steps[1].data["contract_path"]
    assert path["applicability"] == "verified"
    assert path["rule_ids"] == ["PRS-FORM-001"]
    assert "selector" not in path
    assert report.steps[1].data["fallback_used"] is False


def test_workflow_executor_serializes_unverified_unique_form_fallback(
    sample_template_payload: dict,
) -> None:
    runtime = FakeRuntime(
        [
            {
                "fieldid": None,
                "label_text": "项目名称",
                "role": "textbox",
                "tag_name": "input",
                "visible": True,
                "editable": True,
                "selector": "[data-field='project-name']",
            }
        ]
    )
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "form", "operation": "fill", "target": {"fields": {"项目名称": "兼容测试"}}},
        ]
    )

    assert report.success is True
    path = report.steps[1].data["contract_path"]
    assert path["applicability"] == "unverified"
    assert path["fallback_reason"] == "exact_identity_unavailable"
    assert report.steps[1].data["fallback_used"] is True


def test_workflow_executor_serializes_unverified_table_failure(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=FakeRuntime(sample_runtime_elements))

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table_row_selection",
                "operation": "select",
                "target": {
                    "table": "MISSING_TABLE",
                    "match": {"column": "项目代码", "equals": "不存在"},
                },
            },
        ]
    )

    assert report.success is False
    path = report.steps[1].data["contract_path"]
    assert path["applicability"] == "unverified"
    assert path["fallback_reason"] == "exact_identity_unavailable"


def test_workflow_executor_serializes_incompatible_exact_form_failure(
    sample_template_payload: dict,
) -> None:
    runtime = FakeRuntime(
        [
            {
                "fieldid": "project_name",
                "label_text": "项目名称",
                "role": "textbox",
                "tag_name": "input",
                "visible": True,
                "disabled": True,
                "selector": "[fieldid='project_name']",
            },
            {
                "fieldid": "similar_project_name",
                "label_text": "项目名称",
                "role": "textbox",
                "tag_name": "input",
                "visible": True,
                "editable": True,
                "selector": "[fieldid='similar_project_name']",
            },
        ]
    )
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "form", "operation": "fill", "target": {"fields": {"项目名称": "冲突测试"}}},
        ]
    )

    assert report.success is False
    path = report.steps[1].data["contract_path"]
    assert path["applicability"] == "incompatible"
    assert path["rule_ids"] == ["PRS-FORM-001"]
    assert report.steps[1].data["fallback_used"] is False


def test_workflow_executor_keeps_incompatible_background_identity_failure(
    sample_template_payload: dict,
) -> None:
    runtime = FakeRuntime(
        [
            {
                "fieldid": "project_name",
                "label_text": "项目名称",
                "role": "textbox",
                "tag_name": "input",
                "visible": True,
                "editable": True,
                "selector": "[fieldid='project_name']",
            },
            {
                "fieldid": "dialog_project_name",
                "label_text": "项目名称",
                "role": "textbox",
                "tag_name": "input",
                "visible": True,
                "editable": True,
                "in_dialog": True,
                "selector": "[fieldid='dialog_project_name']",
            },
        ]
    )
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "form", "operation": "fill", "target": {"fields": {"项目名称": "前景冲突"}}},
        ]
    )

    assert report.success is False
    assert report.steps[1].data["contract_path"]["applicability"] == "incompatible"


def test_workflow_executor_emits_failed_step_phase_events(
    tmp_path,
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    observation = ObservationSession(
        tmp_path / "events.jsonl",
        tool_version="0.1.19",
        run_id="run-1",
        configuration={"ai_observe": True},
    )
    observation.set_scope(suite_id="suite-a", case_id="case-a")
    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=FakeRuntime(sample_runtime_elements),
        observation_session=observation,
    )

    report = executor.run([ActionStep(kind="page", action="unsupported")])

    assert report.success is False
    events = [json.loads(line)["event"] for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert events == [
        "step_started",
        "phase_started",
        "diagnostic_file_created",
        "phase_failed",
        "step_failed",
    ]


def test_workflow_executor_records_step_performance_memory_when_enabled(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(
        sample_runtime_elements,
        network_summaries=[
            {
                "request_count": 4,
                "api_request_count": 1,
                "static_resource_count": 3,
                "failed_count": 0,
                "top_slow_requests": [{"url": "https://example.yonyougov.top/api/demo", "duration_ms": 120}],
            }
        ],
    )
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime, performance_enabled=True)

    report = executor.run([{"action": "open_menu", "menu_path": "项目管理>>项目立项"}])

    assert report.success is True
    assert report.performance["cache_mode"] == "cold_ephemeral"
    step_perf = report.step_results[0].data["performance"]
    assert step_perf["duration_ms"] >= 0
    assert step_perf["network"]["request_count"] == 4
    assert step_perf["memory"] == {
        "available": True,
        "used_js_heap_size": 10485760,
        "unavailable_reason": "",
    }
    assert step_perf["phases"]["resolve_menu_ms"] >= 0
    assert step_perf["phases"]["fetch_template_ms"] >= 0
    assert step_perf["phases"]["browser_open_ms"] >= 0
    assert step_perf["phases"]["binding_ms"] >= 0


def test_workflow_executor_refreshes_starting_step_upload_from_final_network_event(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    class _CrossStepRuntime(FakeRuntime):
        def collect_network_events(self) -> list[dict[str, Any]]:
            return [
                {
                    "url": "https://example.yonyougov.top/static/upload.js",
                    "method": "POST",
                    "resource_type": "script",
                    "status": 200,
                    "duration_ms": 80,
                    "encoded_body_size": 12,
                    "request_body_size": 25,
                    "request_body_size_available": True,
                    "request_body_size_unavailable_reason": "",
                    "failed": False,
                    "step_context": "step",
                    "step_index": 1,
                    "action": "open_menu",
                }
            ]

    runtime = _CrossStepRuntime(
        sample_runtime_elements,
        network_summaries=[
            {
                "network_available": True,
                "request_count": 1,
                "api_request_count": 0,
                "static_resource_count": 1,
                "request_body_size": 0,
                "request_body_size_available": False,
                "request_body_size_unavailable_reason": "request_body_size_unavailable",
            },
            {"network_available": True, "request_count": 0},
        ],
    )
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime, performance_enabled=True)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
        ]
    )

    starting_step = report.step_results[0].data["performance"]["network"]
    later_step = report.step_results[1].data["performance"]["network"]
    case_event = report.performance["network_events"][0]
    serialized = report.to_dict()
    assert starting_step["request_body_size"] == case_event["request_body_size"] == 25
    assert starting_step["request_body_size_available"] is True
    assert starting_step["api_request_count"] == 0
    assert starting_step["static_resource_count"] == 1
    assert later_step["request_body_size"] == 0
    assert later_step["request_count"] == 0
    assert serialized["performance"]["steps"][0]["network"] == starting_step


def test_workflow_executor_records_failed_step_performance_memory_when_enabled(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements, should_validate=False)
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime, performance_enabled=True)

    report = executor.run([{"action": "open_menu", "menu_path": "项目管理>>项目立项"}])

    assert report.success is False
    failed_step = report.step_results[0]
    assert failed_step.data["performance"]["duration_ms"] >= 0
    assert failed_step.data["performance"]["network"]["request_count"] == 0
    assert failed_step.data["performance"]["memory"]["used_js_heap_size"] == 10485760


def test_workflow_executor_freezes_performance_duration_before_page_memory_capture(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
    monkeypatch,
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    captured = False

    def capture_page_memory() -> dict[str, Any]:
        nonlocal captured
        captured = True
        return dict(runtime.page_memory)

    def elapsed_ms(_started: float) -> int:
        assert captured is False
        return 17

    runtime.capture_page_memory = capture_page_memory
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime, performance_enabled=True)
    monkeypatch.setattr(executor_module, "_elapsed_ms", elapsed_ms)

    performance = executor._step_performance(0.0)

    assert performance["duration_ms"] == 17
    assert performance["memory"]["used_js_heap_size"] == 10485760
    assert captured is True


def test_workflow_executor_marks_performance_page_memory_unsupported_for_older_runtime(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
    monkeypatch,
) -> None:
    monkeypatch.delattr(FakeRuntime, "capture_page_memory")
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime, performance_enabled=True)

    report = executor.run([{"action": "open_menu", "menu_path": "项目管理>>项目立项"}])

    assert report.step_results[0].data["performance"]["memory"] == {
        "available": False,
        "used_js_heap_size": 0,
        "unavailable_reason": "runtime_not_supported",
    }


def test_workflow_executor_records_bpr_session_range_and_performance_memory_excluding_control_steps(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime, performance_enabled=True)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "bpr", "operation": "start", "target": {"name": "保存动作"}},
            {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
            {"component": "bpr", "operation": "stop", "target": {}},
        ]
    )

    assert report.success is True
    assert len(report.bpr_sessions) == 1
    session = report.bpr_sessions[0]
    assert session["start_control_step"] == 2
    assert session["end_control_step"] == 4
    assert session["start_step"] == 3
    assert session["end_step"] == 3
    assert session["range"] == "step 3"
    assert [item["action"] for item in session["actions"]] == ["toolbar.click"]
    assert session["report_url"].startswith("https://example.yonyougov.top/")
    assert report.to_dict()["bpr_sessions"][0]["bpr_id"] == "fake-bpr-1"
    assert report.step_results[1].data["performance"]["memory"]["used_js_heap_size"] == 10485760
    assert report.step_results[3].data["performance"]["memory"]["used_js_heap_size"] == 10485760


def test_workflow_executor_allows_multiple_bpr_sessions(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime, performance_enabled=True)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "bpr", "operation": "start", "target": {"name": "第一次"}},
            {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
            {"component": "bpr", "operation": "stop", "target": {}},
            {"component": "bpr", "operation": "start", "target": {"name": "第二次"}},
            {"component": "toolbar", "operation": "click", "target": {"label": "提交"}},
            {"component": "bpr", "operation": "stop", "target": {}},
        ]
    )

    assert report.success is True
    assert [session["name"] for session in report.bpr_sessions] == ["第一次", "第二次"]
    assert [session["index"] for session in report.bpr_sessions] == [1, 2]
    assert [session["range"] for session in report.bpr_sessions] == ["step 3", "step 6"]
    assert len(runtime.bpr_starts) == 2
    assert len(runtime.bpr_stops) == 2


def test_workflow_executor_rejects_nested_bpr(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=FakeRuntime(sample_runtime_elements),
        performance_enabled=True,
    )

    report = executor.run(
        [
            {"component": "bpr", "operation": "start", "target": {}},
            {"component": "bpr", "operation": "start", "target": {}},
        ]
    )

    assert report.success is False
    assert "不支持嵌套 BPR 录制" in report.errors[0]


def test_workflow_executor_rejects_bpr_stop_without_active_session(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=FakeRuntime(sample_runtime_elements),
        performance_enabled=True,
    )

    report = executor.run([{"component": "bpr", "operation": "stop", "target": {}}])

    assert report.success is False
    assert "没有正在录制的 BPR session" in report.errors[0]


def test_workflow_executor_rejects_missing_bpr_stop(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=FakeRuntime(sample_runtime_elements),
        performance_enabled=True,
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "bpr", "operation": "start", "target": {"name": "漏 stop"}},
            {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
        ]
    )

    assert report.success is False
    assert "BPR 录制缺少 bpr.stop" in report.errors
    assert report.bpr_sessions[0]["status"] == "failed"
    assert report.bpr_sessions[0]["range"] == "step 3"
    assert report.step_results[-1].action == "bpr.stop"


def test_open_menu_uses_browser_template_response_without_gateway_prefetch(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    events: list[str] = []

    class OrderedGateway(FakeGateway):
        def resolve_menu(self, menu_path: str, timeout_seconds: float | None = None) -> MenuTarget:
            events.append("resolve")
            return super().resolve_menu(menu_path, timeout_seconds=timeout_seconds)

        def fetch_template(self, menu_target: MenuTarget, timeout_seconds: float | None = None) -> dict:
            events.append("fetch")
            raise AssertionError("真实 open_menu 不应预取模板")

    class OrderedRuntime(PageResponseOpenMenuRuntime):
        def open_menu(self, menu_target: MenuTarget) -> None:
            events.append("open")
            super().open_menu(menu_target)

    runtime = OrderedRuntime(
        sample_runtime_elements,
        surface_snapshots=[
            [_surface("main", "main_table", busy=1, signature="loading")],
            [_surface("main", "main_table", terminal=True, signature="row:1")],
        ],
        initial_template_payload=sample_template_payload,
    )
    report = _browser_executor(OrderedGateway(sample_template_payload), runtime).run(
        [{"action": "open_menu", "menu_path": "项目管理>>项目立项"}]
    )

    assert report.success is True
    assert events == ["resolve", "open"]


def test_open_menu_preserves_browser_template_business_error(
    sample_runtime_elements: list[dict],
) -> None:
    error_payload = {
        "code": 999,
        "message": "当前产品未授权‘支付管理’子系统",
        "displayCode": "AUTH-001",
        "traceId": "trace-001",
    }
    runtime = PageResponseOpenMenuRuntime(
        sample_runtime_elements,
        template_error_payload=error_payload,
    )

    report = _browser_executor(FakeGateway({}), runtime).run(
        [{"action": "open_menu", "menu_path": "项目管理>>项目立项"}]
    )

    assert report.success is False
    assert runtime.opened_menu is not None
    assert report.steps[0].data["error"]["type"] == "OpenMenuCompletionError"
    assert report.steps[0].data["template_error"] == {
        "type": "RuntimeError",
        "message": error_payload["message"],
        "code": 999,
        "display_code": "AUTH-001",
        "trace_id": "trace-001",
    }


def test_open_menu_recovers_when_browser_later_returns_valid_template(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = PageResponseOpenMenuRuntime(
        sample_runtime_elements,
        surface_snapshots=[
            [_surface("main", "main_table", busy=1, signature="loading")],
            [_surface("main", "main_table", terminal=True, signature="row:1")],
        ],
        service_detail_payload={
            "data": {
                "serviceCode": "global00_-1_PM_INIT",
                "nativeUrl": "tns:///bill/ydf/#/BillRender?code=PM_INIT",
            }
        },
        retry_template_payload=sample_template_payload,
    )

    report = _browser_executor(FakeGateway({}), runtime).run(
        [{"action": "open_menu", "menu_path": "项目管理>>项目立项"}]
    )

    assert report.success is True
    assert report.manifest is not None


def test_open_menu_allows_open_only_from_browser_service_detail(
    sample_runtime_elements: list[dict],
) -> None:
    runtime = PageResponseOpenMenuRuntime(
        sample_runtime_elements,
        service_detail_payload={
            "data": {
                "serviceCode": "global00_-1_PM_INIT",
                "serviceName": "分析报表",
                "nativeUrl": "tns:///native/report",
            }
        },
    )

    report = _browser_executor(FakeGateway({}), runtime).run(
        [{"action": "open_menu", "menu_path": "项目管理>>项目立项"}]
    )

    assert report.success is True
    assert report.steps[0].data["template_supported"] is False
    assert report.steps[0].data["completion_signal"] == "open_menu_open_only"
    assert report.menu_target.native_url == "tns:///native/report"


def test_open_menu_fails_closed_when_bill_page_has_no_browser_template(
    monkeypatch,
    tmp_path,
    sample_runtime_elements: list[dict],
) -> None:
    clock = FakeClock()
    monkeypatch.setattr("ydf_browser.executor.time.monotonic", clock.monotonic)
    runtime = PageResponseOpenMenuRuntime(
        sample_runtime_elements,
        clock=clock,
        service_detail_payload={
            "data": {
                "serviceCode": "global00_-1_PM_INIT",
                "nativeUrl": "tns:///bill/ydf/#/BillRender?code=PM_INIT",
            }
        },
    )
    observation = ObservationSession(
        tmp_path / "events.jsonl",
        tool_version="test",
        run_id="run-open-menu-missing-template",
        configuration={"step_timeout_seconds": 1},
    )

    report = _browser_executor(
        FakeGateway({}),
        runtime,
        observation_session=observation,
    ).run([{"action": "open_menu", "menu_path": "项目管理>>项目立项"}])

    assert report.success is False
    assert runtime.opened_menu is not None
    assert "页面初始模板响应不可用" in report.errors[0]
    assert report.steps[0].data["completion_signal"] == "open_menu_timeout"


def test_open_menu_uses_configured_shared_step_timeout(
    monkeypatch,
    tmp_path,
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    clock = FakeClock()
    monkeypatch.setattr("ydf_browser.executor.time.monotonic", clock.monotonic)
    runtime = OpenMenuReadinessRuntime(
        sample_runtime_elements,
        surface_snapshots=[[_surface("main", "main_table", busy=1, signature="loading")]],
        clock=clock,
    )
    observation = ObservationSession(
        tmp_path / "events.jsonl",
        tool_version="0.1.21",
        run_id="run-open-menu-timeout",
        configuration={"ai_observe": True, "step_timeout_seconds": 1},
    )

    report = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=runtime,
        observation_session=observation,
    ).run([{"action": "open_menu", "menu_path": "项目管理>>项目立项"}])

    assert report.success is False
    assert report.steps[0].data["completion_signal"] == "open_menu_timeout"
    assert report.steps[0].data["open_menu_readiness"]["work_surfaces"][0]["busy"] == 1
    assert 900 <= report.steps[0].data["wait_duration_ms"] <= 1000


def test_open_menu_shared_step_timeout_includes_template_preparation(
    monkeypatch,
    tmp_path,
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    clock = FakeClock()
    monkeypatch.setattr("ydf_browser.executor.time.monotonic", clock.monotonic)

    class SlowTemplateGateway(FakeGateway):
        def fetch_template(self, menu_target: MenuTarget) -> dict:
            clock.advance_ms(1000)
            return super().fetch_template(menu_target)

    observation = ObservationSession(
        tmp_path / "events.jsonl",
        tool_version="0.1.21",
        run_id="run-open-menu-template-timeout",
        configuration={"ai_observe": True, "step_timeout_seconds": 1},
    )
    runtime = FakeRuntime(sample_runtime_elements)

    report = WorkflowExecutor(
        gateway=SlowTemplateGateway(sample_template_payload),
        runtime=runtime,
        observation_session=observation,
    ).run([{"action": "open_menu", "menu_path": "项目管理>>项目立项"}])

    assert report.success is False
    assert runtime.opened_menu is None
    assert report.steps[0].data["completion_signal"] == "open_menu_timeout"
    assert report.steps[0].data["open_menu_readiness"]["phase"] == "模板获取"


def test_workflow_executor_rejects_template_technical_error_before_opening_menu(
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = {"code": 999, "message": "通用错误: 页面编码不能为空"}
    runtime_elements = [
        item for item in sample_runtime_elements if item["fieldid"] not in {"btn_save", "btn_submit"}
    ]
    runtime = FakeRuntime(runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run([{"action": "open_menu", "menu_path": "项目管理>>项目立项"}])

    assert report.success is False
    assert runtime.opened_menu is None
    assert report.manifest is None
    assert report.binding is None
    step = report.step_results[0]
    assert step.success is False
    assert step.data["template_error"]["message"] == "通用错误: 页面编码不能为空"


def test_workflow_executor_allows_explicit_non_bill_open_only_menu(
    sample_runtime_elements: list[dict],
) -> None:
    menu_target = MenuTarget(
        menu_code="REPORT",
        menu_name="分析报表",
        path=["分析", "分析报表"],
        service_code="global00_-1_REPORT",
        service_url="#/native/report",
        native_url="tns:///native/report",
    )
    gateway = FakeGateway(
        {"code": 999, "message": "通用错误: 页面编码不能为空"},
        menu_target=menu_target,
    )
    runtime = FakeRuntime(sample_runtime_elements)

    report = WorkflowExecutor(gateway=gateway, runtime=runtime).run(
        [{"action": "open_menu", "menu_path": "项目管理>>项目立项"}]
    )

    assert report.success is True
    assert report.steps[0].data["template_supported"] is False
    assert report.steps[0].data["completion_signal"] == "open_menu_open_only"


def test_workflow_executor_reports_iframe_menu_hosting_without_failing_open_menu(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(
        sample_runtime_elements,
        menu_hosting={
            "mode": "iframe",
            "frame_name": "global00_-1_PM_INIT",
            "frame_url": "https://example.test/apps/project/index.html",
        },
    )
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run([{"action": "open_menu", "menu_path": "项目管理>>项目立项"}])

    step = report.step_results[0]
    assert report.success is True
    assert step.success is True
    assert step.data["menu_hosting"] == runtime.menu_hosting
    assert "承载方式: iframe" in step.message


def test_workflow_executor_reports_direct_menu_hosting_without_failing_open_menu(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements, menu_hosting={"mode": "direct"})
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run([{"action": "open_menu", "menu_path": "项目管理>>项目立项"}])

    step = report.step_results[0]
    assert report.success is True
    assert step.success is True
    assert step.data["menu_hosting"] == {"mode": "direct"}
    assert "承载方式: direct" in step.message


def test_workflow_executor_reports_unknown_menu_hosting_without_failing_open_menu(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(
        sample_runtime_elements,
        menu_hosting={"mode": "unknown", "reason": "找到多个业务 frame"},
    )
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run([{"action": "open_menu", "menu_path": "项目管理>>项目立项"}])

    step = report.step_results[0]
    assert report.success is True
    assert step.success is True
    assert step.data["menu_hosting"] == runtime.menu_hosting
    assert "承载方式: unknown" in step.message


def test_workflow_executor_rejects_component_actions_after_unsupported_menu_open(
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = {"code": 999, "message": "通用错误: 页面编码不能为空"}
    runtime_elements = [
        item for item in sample_runtime_elements if item["fieldid"] not in {"btn_save", "btn_submit"}
    ]
    runtime = FakeRuntime(runtime_elements)
    executor = WorkflowExecutor(
        gateway=FakeGateway(
            template_payload,
            menu_target=MenuTarget(
                menu_code="PM_INIT",
                menu_name="分析报表",
                path=["分析", "分析报表"],
                service_code="global00_-1_REPORT",
                service_url="#/native/report",
                native_url="tns:///native/report",
            ),
        ),
        runtime=runtime,
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "query",
                "operation": "search",
                "target": {"conditions": [{"field": "项目负责人", "equals": "孙丽娜"}]},
            },
        ]
    )

    assert report.success is False
    assert report.step_results[0].success is True
    failed_step = report.step_results[1]
    assert failed_step.action == "query.search"
    assert "当前页面不是单据模板页面，不支持查询操作" in failed_step.message
    assert "通用错误: 页面编码不能为空" in failed_step.message


def test_workflow_executor_clicks_plain_toolbar_leaf_by_fieldid(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
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
    runtime = FakeRuntime(
        [
            *sample_runtime_elements,
            {
                "fieldid": "plan_detail_add",
                "id": None,
                "text": "新增",
                "role": "button",
                "tag_name": "button",
                "visible": True,
                "selector": '[fieldid="plan_detail_add"]',
            },
        ]
    )
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "新增"}},
        ]
    )

    assert report.success is True
    assert runtime.toolbar_click_details[-1]["fieldid"] == "plan_detail_add"


def test_workflow_executor_clicks_dynamic_lcd_bottom_toolbar_save_by_fieldid(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    list_template_payload = deepcopy(sample_template_payload)
    list_template_payload["data"]["actionEL"]["create"] = {
        "key": "create_btn",
        "divCode": "xz_btn",
        "nodeType": "leafItem",
        "label": "新增",
        "name": "Button",
        "rightflag": "create",
        "parentKeys": ["root", "toolbar_root"],
    }
    edit_template_payload = deepcopy(sample_template_payload)
    edit_root = edit_template_payload["data"]["uidata"][0]
    edit_root["divCode"] = "editRoot"
    edit_root["nodeType"] = "root"
    edit_root["children"] = [
        {
            "key": "lcdBtnToolbarOfPage",
            "divCode": "lcdBtnToolbarOfPage",
            "nodeType": "toolbar",
            "label": "底部工具栏",
            "name": "LCDBtnToolbar",
            "parentKey": "editRoot",
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
        }
    ]
    edit_template_payload["data"]["actionEL"] = {}
    runtime = FakeRuntime(
        [
            *sample_runtime_elements,
            {
                "fieldid": "xz_btn",
                "id": None,
                "text": "新增",
                "role": "button",
                "tag_name": "button",
                "visible": True,
                "selector": '[fieldid="xz_btn"]',
            },
        ],
        runtime_elements_by_page={
            "editRoot": [
                {
                    "fieldid": "btnSave",
                    "id": None,
                    "text": "保存",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="btnSave"]',
                    "in_dialog": True,
                }
            ]
        },
        dynamic_template_payloads_by_toolbar_click={"新增": edit_template_payload},
    )
    executor = WorkflowExecutor(gateway=FakeGateway(list_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "新增"}},
            {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
        ]
    )

    assert report.success is True
    assert runtime.clicked_targets == ["新增", "保存"]
    assert runtime.toolbar_click_details[-1]["fieldid"] == "btnSave"


def test_workflow_executor_rejects_unbound_runtime_toolbar_action(
    sample_template_payload: dict[str, Any],
    sample_runtime_elements: list[dict[str, Any]],
    ) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    runtime._page = object()
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "未声明动作"}},
        ]
    )

    assert report.success is False
    assert runtime.clicked_targets == []
    assert report.steps[-1].data["error"]["message"] == "未绑定工具栏动作: 未声明动作"


def test_workflow_executor_allows_unbound_toolbar_action_with_runtime_identity(
    sample_template_payload: dict[str, Any],
    sample_runtime_elements: list[dict[str, Any]],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    runtime._page = object()
    runtime.has_visible_toolbar_action = lambda _label: True  # type: ignore[method-assign]
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "未声明动作"}},
        ]
    )

    assert report.success is True
    assert runtime.clicked_targets == ["未声明动作"]


def test_workflow_executor_applies_pending_dynamic_template_before_form_fill(
    sample_template_payload: dict[str, Any],
    sample_runtime_elements: list[dict[str, Any]],
) -> None:
    payload = deepcopy(sample_template_payload)
    payload["data"]["uidata"][0]["divCode"] = "editRoot"
    class DynamicAfterOpenRuntime(FakeRuntime):
        def open_menu(self, menu_target: MenuTarget) -> None:
            super().open_menu(menu_target)
            self.next_dynamic_template_payload = payload

    runtime = DynamicAfterOpenRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "form", "operation": "fill", "target": {"fields": {"项目名称": "新项目"}}},
        ]
    )

    assert report.success is True
    assert runtime.prepared_manifest_keys == ["root", "editRoot"]


def test_workflow_executor_consumes_targetless_toolbar_template_before_form_binding(
    sample_template_payload: dict[str, Any],
    sample_runtime_elements: list[dict[str, Any]],
) -> None:
    payload = deepcopy(sample_template_payload)
    payload["data"]["uidata"][0]["divCode"] = "editRoot"
    card = next(
        child
        for child in payload["data"]["uidata"][0]["children"]
        if child.get("divCode") == "card_base"
    )
    card["children"] = [
        {
            "key": "dynamic_name",
            "divCode": "dynamic_name",
            "nodeType": "formItem",
            "label": "动态字段",
            "name": "TextInput",
            "dataField": "dynamicName",
        }
    ]
    dynamic_runtime_elements = [
        {
            "fieldid": "dynamic_name",
            "id": "dynamic_name_input",
            "text": "动态字段",
            "role": "textbox",
            "tag_name": "input",
            "visible": True,
            "selector": '[fieldid="dynamic_name"] input',
        }
    ]
    runtime = FakeRuntime(
        sample_runtime_elements,
        runtime_elements_by_page={"editRoot": dynamic_runtime_elements},
        dynamic_template_payloads_by_toolbar_click={"新增": payload},
    )
    runtime.has_visible_toolbar_action = lambda _label: True  # type: ignore[method-assign]
    runtime._dynamic_template_payload_matches_action = lambda _payload: False  # type: ignore[attr-defined]
    runtime.dynamic_template_payload_can_apply_as_fallback = lambda _payload: True  # type: ignore[attr-defined]
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "新增"}},
            {
                "component": "form",
                "operation": "fill",
                "target": {"fields": {"动态字段": "动态值"}},
            },
        ]
    )

    assert report.success is True
    assert runtime.prepared_manifest_keys == ["root", "editRoot"]
    assert runtime.filled_fields == [{"fieldid": "dynamic_name", "value": "动态值"}]


def test_workflow_executor_reports_missing_dynamic_form_field_without_runtime_fallback(
    sample_template_payload: dict[str, Any],
    sample_runtime_elements: list[dict[str, Any]],
) -> None:
    payload = deepcopy(sample_template_payload)
    payload["data"]["uidata"][0]["divCode"] = "editRoot"
    card = next(
        child
        for child in payload["data"]["uidata"][0]["children"]
        if child.get("divCode") == "card_base"
    )
    card["children"] = [
        {
            "key": "dynamic_name",
            "divCode": "dynamic_name",
            "nodeType": "formItem",
            "label": "动态字段",
            "name": "TextInput",
            "dataField": "dynamicName",
        }
    ]
    runtime = FakeRuntime(
        sample_runtime_elements,
        runtime_elements_by_page={
            "editRoot": [
                {
                    "fieldid": "dynamic_name",
                    "label_text": "动态字段",
                    "role": "textbox",
                    "tag_name": "input",
                    "visible": True,
                    "editable": True,
                    "selector": '[fieldid="dynamic_name"] input',
                },
                {
                    "fieldid": "legacy_expert_name",
                    "label_text": "专家姓名",
                    "role": "textbox",
                    "tag_name": "input",
                    "visible": True,
                    "editable": True,
                    "selector": '[fieldid="legacy_expert_name"] input',
                },
            ]
        },
        dynamic_template_payloads_by_toolbar_click={"新增": payload},
    )
    runtime.has_visible_toolbar_action = lambda _label: True  # type: ignore[method-assign]
    runtime._dynamic_template_payload_matches_action = lambda _payload: False  # type: ignore[attr-defined]
    runtime.dynamic_template_payload_can_apply_as_fallback = lambda _payload: True  # type: ignore[attr-defined]
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "新增"}},
            {
                "component": "form",
                "operation": "fill",
                "target": {"fields": {"专家姓名": "错误字段"}},
            },
        ]
    )

    assert report.success is False
    message = report.errors[0]
    assert message.startswith("未找到表单字段: 专家姓名")
    assert "动态字段" in message
    assert "Call log" not in message
    assert runtime.filled_fields == []


def test_workflow_executor_restores_list_template_after_ymbtl_backup_action(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    list_template_payload = deepcopy(sample_template_payload)
    list_template_payload["data"]["actionEL"]["create"] = {
        "key": "create_btn",
        "divCode": "xz_btn",
        "nodeType": "leafItem",
        "label": "新增",
        "name": "Button",
        "rightflag": "create",
        "parentKeys": ["root", "toolbar_root"],
    }
    edit_template_payload = deepcopy(sample_template_payload)
    edit_root = edit_template_payload["data"]["uidata"][0]
    edit_root["divCode"] = "editRoot"
    edit_root["children"] = [
        {
            "key": "editToolbar",
            "divCode": "editToolbar",
            "nodeType": "toolbar",
            "label": "按钮工具栏",
            "parentKey": "editRoot",
            "children": [
                {
                    "key": "temporarySave",
                    "divCode": "temporarySave",
                    "nodeType": "leafItem",
                    "label": "暂存",
                    "name": "YDFButton",
                    "rightflag": "temporarySave",
                }
            ],
        }
    ]
    edit_template_payload["data"]["actionEL"] = {}
    runtime = FakeRuntime(
        [
            *sample_runtime_elements,
            {
                "fieldid": "xz_btn",
                "id": None,
                "text": "新增",
                "role": "button",
                "tag_name": "button",
                "visible": True,
                "selector": '[fieldid="xz_btn"]',
            },
        ],
        runtime_elements_by_page={
            "editRoot": [
                {
                    "fieldid": "temporarySave",
                    "id": None,
                    "text": "暂存",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="temporarySave"]',
                }
            ]
        },
        dynamic_template_payloads_by_toolbar_click={"新增": edit_template_payload},
    )
    executor = WorkflowExecutor(gateway=FakeGateway(list_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "新增"}},
            {"component": "action", "operation": "click", "target": {"fieldid": "ymbtl_backup"}},
            {"component": "toolbar", "operation": "click", "target": {"label": "新增"}},
        ]
    )

    assert report.success is True
    assert report.steps[2].data["restored_template"] == {"page": "root", "bound_action_count": 3}
    assert runtime.clicked_fieldids == ["ymbtl_backup"]
    assert runtime.clicked_targets == ["新增", "新增"]


def test_workflow_executor_restores_previous_template_after_generic_action_when_list_dom_visible(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    list_template_payload = deepcopy(sample_template_payload)
    list_template_payload["data"]["actionEL"]["create"] = {
        "key": "create_btn",
        "divCode": "xz_btn",
        "nodeType": "leafItem",
        "label": "新增",
        "name": "Button",
        "rightflag": "create",
        "parentKeys": ["root", "toolbar_root"],
    }
    edit_template_payload = deepcopy(sample_template_payload)
    edit_root = edit_template_payload["data"]["uidata"][0]
    edit_root["divCode"] = "editRoot"
    edit_root["children"] = [
        {
            "key": "editToolbar",
            "divCode": "editToolbar",
            "nodeType": "toolbar",
            "label": "按钮工具栏",
            "parentKey": "editRoot",
            "children": [
                {
                    "key": "temporarySave",
                    "divCode": "temporarySave",
                    "nodeType": "leafItem",
                    "label": "暂存",
                    "name": "YDFButton",
                    "rightflag": "temporarySave",
                }
            ],
        }
    ]
    edit_template_payload["data"]["actionEL"] = {}
    runtime = FakeRuntime(
        [
            *sample_runtime_elements,
            {
                "fieldid": "xz_btn",
                "id": None,
                "text": "新增",
                "role": "button",
                "tag_name": "button",
                "visible": True,
                "selector": '[fieldid="xz_btn"]',
            },
        ],
        runtime_elements_by_page={
            "editRoot": [
                {
                    "fieldid": "temporarySave",
                    "id": None,
                    "text": "暂存",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="temporarySave"]',
                }
            ]
        },
        dynamic_template_payloads_by_toolbar_click={"新增": edit_template_payload},
    )
    executor = WorkflowExecutor(gateway=FakeGateway(list_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "新增"}},
            {"component": "action", "operation": "click", "target": {"fieldid": "custom_back_btn"}},
            {"component": "toolbar", "operation": "click", "target": {"label": "新增"}},
        ]
    )

    assert report.success is True
    assert report.steps[2].data["restored_template"] == {"page": "root", "bound_action_count": 3}
    assert runtime.clicked_fieldids == ["custom_back_btn"]
    assert runtime.clicked_targets == ["新增", "新增"]


def test_workflow_executor_does_not_restore_after_action_when_edit_actions_remain_visible(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    list_template_payload = deepcopy(sample_template_payload)
    list_template_payload["data"]["actionEL"]["create"] = {
        "key": "create_btn",
        "divCode": "xz_btn",
        "nodeType": "leafItem",
        "label": "新增",
        "name": "Button",
        "rightflag": "create",
        "parentKeys": ["root", "toolbar_root"],
    }
    edit_template_payload = deepcopy(sample_template_payload)
    edit_root = edit_template_payload["data"]["uidata"][0]
    edit_root["divCode"] = "editRoot"
    edit_root["children"] = [
        {
            "key": "editToolbar",
            "divCode": "editToolbar",
            "nodeType": "toolbar",
            "label": "按钮工具栏",
            "parentKey": "editRoot",
            "children": [
                {
                    "key": "btnSave",
                    "divCode": "btnSave",
                    "nodeType": "leafItem",
                    "label": "保存",
                    "name": "YDFButton",
                    "rightflag": "save",
                },
                {
                    "key": "btnCancel",
                    "divCode": "btnCancel",
                    "nodeType": "leafItem",
                    "label": "取消",
                    "name": "YDFButton",
                    "rightflag": "cancel",
                },
            ],
        }
    ]
    edit_template_payload["data"]["actionEL"] = {}
    edit_runtime_elements = [
        {
            "fieldid": "btnSave",
            "id": None,
            "text": "保存",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="btnSave"]',
        },
        {
            "fieldid": "btnCancel",
            "id": None,
            "text": "取消",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="btnCancel"]',
        },
    ]
    runtime = FakeRuntime(
        [
            *sample_runtime_elements,
            {
                "fieldid": "xz_btn",
                "id": None,
                "text": "新增",
                "role": "button",
                "tag_name": "button",
                "visible": True,
                "selector": '[fieldid="xz_btn"]',
            },
        ],
        runtime_elements_by_page={
            "root": edit_runtime_elements,
            "editRoot": edit_runtime_elements,
        },
        dynamic_template_payloads_by_toolbar_click={"新增": edit_template_payload},
    )
    executor = WorkflowExecutor(gateway=FakeGateway(list_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "新增"}},
            {"component": "action", "operation": "click", "target": {"fieldid": "ymbtl_backup"}},
        ]
    )

    assert report.success is True
    assert "restored_template" not in report.steps[2].data
    assert executor.current_manifest.page.fieldid == "editRoot"
    assert runtime.clicked_fieldids == ["ymbtl_backup"]


def test_workflow_executor_restores_when_previous_dom_dominates_stale_edit_actions(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    list_template_payload = deepcopy(sample_template_payload)
    list_template_payload["data"]["actionEL"]["create"] = {
        "key": "create_btn",
        "divCode": "xz_btn",
        "nodeType": "leafItem",
        "label": "新增",
        "name": "Button",
        "rightflag": "create",
        "parentKeys": ["root", "toolbar_root"],
    }
    edit_template_payload = deepcopy(sample_template_payload)
    edit_root = edit_template_payload["data"]["uidata"][0]
    edit_root["divCode"] = "editRoot"
    edit_root["children"] = [
        {
            "key": "editToolbar",
            "divCode": "editToolbar",
            "nodeType": "toolbar",
            "label": "按钮工具栏",
            "parentKey": "editRoot",
            "children": [
                {
                    "key": "btnSave",
                    "divCode": "btnSave",
                    "nodeType": "leafItem",
                    "label": "保存",
                    "name": "YDFButton",
                    "rightflag": "save",
                },
                {
                    "key": "btnCancel",
                    "divCode": "btnCancel",
                    "nodeType": "leafItem",
                    "label": "取消",
                    "name": "YDFButton",
                    "rightflag": "cancel",
                },
            ],
        }
    ]
    edit_template_payload["data"]["actionEL"] = {}
    stale_edit_actions = [
        {
            "fieldid": "btnSave",
            "id": None,
            "text": "保存",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="btnSave"]',
        },
        {
            "fieldid": "btnCancel",
            "id": None,
            "text": "取消",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="btnCancel"]',
        },
    ]
    list_runtime_elements = [
        *sample_runtime_elements,
        {
            "fieldid": "xz_btn",
            "id": None,
            "text": "新增",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="xz_btn"]',
        },
    ]
    runtime = FakeRuntime(
        list_runtime_elements,
        runtime_elements_by_page={
            "root": [*list_runtime_elements, *stale_edit_actions],
            "editRoot": stale_edit_actions,
        },
        dynamic_template_payloads_by_toolbar_click={"新增": edit_template_payload},
    )
    executor = WorkflowExecutor(gateway=FakeGateway(list_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "新增"}},
            {"component": "action", "operation": "click", "target": {"fieldid": "custom_back_btn"}},
            {"component": "toolbar", "operation": "click", "target": {"label": "新增"}},
        ]
    )

    assert report.success is True
    assert report.steps[2].data["restored_template"] == {"page": "root", "bound_action_count": 3}
    assert report.steps[2].data["dom_transition"]["reason"] == "restore"
    assert runtime.clicked_targets == ["新增", "新增"]


def test_workflow_executor_prefers_exact_save_label_over_save_and_add_alias(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    list_template_payload = deepcopy(sample_template_payload)
    list_template_payload["data"]["actionEL"]["create"] = {
        "key": "create_btn",
        "divCode": "xz_btn",
        "nodeType": "leafItem",
        "label": "新增",
        "name": "Button",
        "rightflag": "create",
        "parentKeys": ["root", "toolbar_root"],
    }
    edit_template_payload = deepcopy(sample_template_payload)
    edit_template_payload["data"]["uidata"][0]["key"] = "editRoot"
    edit_template_payload["data"]["uidata"][0]["divCode"] = "editRoot"
    edit_template_payload["data"]["uidata"][0]["children"] = []
    edit_template_payload["data"]["actionEL"] = {
        "saveAndAdd": {
            "key": "saveAndAdd",
            "divCode": "btnSaveAndAdd",
            "nodeType": "leafItem",
            "label": "保存并新增",
            "name": "Button",
            "actions": {"onClick": [{"key": "save", "label": "保存"}]},
            "parentKeys": ["editRoot"],
        },
        "save": {
            "key": "save",
            "divCode": "btnSave",
            "nodeType": "leafItem",
            "label": "保存",
            "name": "Button",
            "rightflag": "save",
            "parentKeys": ["editRoot"],
        },
    }
    runtime = FakeRuntime(
        [
            *sample_runtime_elements,
            {
                "fieldid": "xz_btn",
                "id": None,
                "text": "新增",
                "role": "button",
                "tag_name": "button",
                "visible": True,
                "selector": '[fieldid="xz_btn"]',
            },
        ],
        runtime_elements_by_page={
            "editRoot": [
                {
                    "fieldid": "btnSaveAndAdd",
                    "id": None,
                    "text": "保存并新增",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="btnSaveAndAdd"]',
                    "in_dialog": True,
                },
                {
                    "fieldid": "btnSave",
                    "id": None,
                    "text": "保存",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="btnSave"]',
                    "in_dialog": True,
                },
            ]
        },
        dynamic_template_payloads_by_toolbar_click={"新增": edit_template_payload},
    )
    executor = WorkflowExecutor(gateway=FakeGateway(list_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "新增"}},
            {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
        ]
    )

    assert report.success is True
    assert runtime.clicked_targets == ["新增", "保存"]
    assert runtime.toolbar_click_details[-1]["fieldid"] == "btnSave"


def test_workflow_executor_restores_form_template_after_popup_reference_select_from_toolbar_template(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    list_template_payload = deepcopy(sample_template_payload)
    list_template_payload["data"]["actionEL"]["create"] = {
        "key": "create_btn",
        "divCode": "xz_btn",
        "nodeType": "leafItem",
        "label": "新增",
        "name": "Button",
        "rightflag": "create",
        "parentKeys": ["root", "toolbar_root"],
    }
    edit_template_payload = deepcopy(sample_template_payload)
    edit_root = edit_template_payload["data"]["uidata"][0]
    edit_root["divCode"] = "editRoot"
    edit_root["children"] = [
        {
            "key": "editToolbar",
            "divCode": "editToolbar",
            "nodeType": "toolbar",
            "label": "按钮工具栏",
            "parentKey": "editRoot",
            "children": [
                {
                    "key": "chooseIndicator",
                    "divCode": "chooseIndicator",
                    "nodeType": "leafItem",
                    "label": "选择指标",
                    "name": "YDFButton",
                    "rightflag": "choose",
                },
                {
                    "key": "btnSave",
                    "divCode": "btnSave",
                    "nodeType": "leafItem",
                    "label": "保存",
                    "name": "YDFButton",
                    "rightflag": "save",
                },
            ],
        }
    ]
    edit_template_payload["data"]["actionEL"] = {}
    reference_template_payload = deepcopy(sample_template_payload)
    reference_root = reference_template_payload["data"]["uidata"][0]
    reference_root["divCode"] = "referenceRoot"
    reference_root["children"] = [
        {
            "key": "referenceToolbar",
            "divCode": "referenceToolbar",
            "nodeType": "toolbar",
            "label": "按钮工具栏",
            "parentKey": "referenceRoot",
            "children": [
                {
                    "key": "append",
                    "divCode": "append",
                    "nodeType": "leafItem",
                    "label": "追加",
                    "name": "YDFButton",
                    "rightflag": "append",
                }
            ],
        }
    ]
    reference_template_payload["data"]["actionEL"] = {}
    runtime = FakeRuntime(
        [
            *sample_runtime_elements,
            {
                "fieldid": "xz_btn",
                "id": None,
                "text": "新增",
                "role": "button",
                "tag_name": "button",
                "visible": True,
                "selector": '[fieldid="xz_btn"]',
            },
        ],
        runtime_elements_by_page={
            "editRoot": [
                {
                    "fieldid": "chooseIndicator",
                    "id": None,
                    "text": "选择指标",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="chooseIndicator"]',
                },
                {
                    "fieldid": "btnSave",
                    "id": None,
                    "text": "保存",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="btnSave"]',
                },
            ],
            "referenceRoot": [
                {
                    "fieldid": "append",
                    "id": None,
                    "text": "追加",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="append"]',
                }
            ],
        },
        dynamic_template_payloads_by_toolbar_click={
            "新增": edit_template_payload,
            "选择指标": reference_template_payload,
        },
    )
    executor = WorkflowExecutor(gateway=FakeGateway(list_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "新增"}},
            {"component": "toolbar", "operation": "click", "target": {"label": "选择指标"}},
            {
                "component": "popup_reference",
                "operation": "select",
                "target": {"title": "选择指标", "match": {"column": "部门经济分类科目", "equals": "30101 基本工资"}},
            },
            {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
        ]
    )

    assert report.success is True
    assert report.steps[3].data["auto_restored_template"] is True
    assert runtime.clicked_targets == ["新增", "选择指标", "保存"]
    assert runtime.toolbar_click_details[-1]["fieldid"] == "btnSave"


def _run_selection_template_restore_case(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
    *,
    open_selection_step: dict[str, Any],
) -> Any:
    list_template = deepcopy(sample_template_payload)
    list_template["data"]["actionEL"]["create"] = {
        "key": "create_btn",
        "divCode": "xz_btn",
        "nodeType": "leafItem",
        "label": "新增",
        "name": "Button",
        "rightflag": "create",
        "parentKeys": ["root", "toolbar_root"],
    }

    edit_template = deepcopy(sample_template_payload)
    edit_root = edit_template["data"]["uidata"][0]
    edit_root["key"] = "editRoot"
    edit_root["divCode"] = "editRoot"
    edit_root["children"][0]["children"] = [
        {
            "key": "selectInfoBtn",
            "divCode": "selectInfoBtn",
            "nodeType": "leafItem",
            "label": "选择",
            "name": "YDFButton",
            "rightflag": "selectInfo",
        },
        {
            "key": "btnSave",
            "divCode": "btnSave",
            "nodeType": "leafItem",
            "label": "保存",
            "name": "YDFButton",
            "rightflag": "save",
        },
    ]
    edit_template["data"]["actionEL"] = {}

    selection_template = deepcopy(sample_template_payload)
    selection_root = selection_template["data"]["uidata"][0]
    selection_root["key"] = "selectionRoot"
    selection_root["divCode"] = "selectionRoot"
    selection_root["children"][0]["children"] = [
        {
            "key": "cancelBtn",
            "divCode": "cancelBtn",
            "nodeType": "leafItem",
            "label": "取消",
            "name": "YDFButton",
            "rightflag": "cancel",
        },
        {
            "key": "selectBtn",
            "divCode": "selectBtn",
            "nodeType": "leafItem",
            "label": "确认",
            "name": "YDFButton",
            "rightflag": "confirm",
        },
    ]
    selection_template["data"]["actionEL"] = {}

    runtime = FakeRuntime(
        [
            *sample_runtime_elements,
            {
                "fieldid": "xz_btn",
                "id": None,
                "text": "新增",
                "role": "button",
                "tag_name": "button",
                "visible": True,
                "selector": '[fieldid="xz_btn"]',
            },
        ],
        runtime_elements_by_page={
            "editRoot": [
                {
                    "fieldid": "selectInfoBtn",
                    "id": None,
                    "text": "选择",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="selectInfoBtn"]',
                },
                {
                    "fieldid": "btnSave",
                    "id": None,
                    "text": "保存",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="btnSave"]',
                },
            ],
            "selectionRoot": [
                {
                    "fieldid": "cancelBtn",
                    "id": None,
                    "text": "取消",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="cancelBtn"]',
                },
                {
                    "fieldid": "selectBtn",
                    "id": None,
                    "text": "确认",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="selectBtn"]',
                },
            ],
        },
        dynamic_template_payloads_by_toolbar_click={
            "新增": edit_template,
            "选择": selection_template,
            "selectInfoBtn": selection_template,
        },
    )
    executor = WorkflowExecutor(gateway=FakeGateway(list_template), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "新增"}},
            open_selection_step,
            {"component": "table_row_selection", "operation": "select", "target": {"row_number": 1}},
            {"component": "dialog", "operation": "confirm", "target": {"label": "确认"}},
            {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
        ]
    )
    return report, runtime


def test_workflow_executor_restores_form_after_toolbar_selection_template_confirm(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    report, runtime = _run_selection_template_restore_case(
        sample_template_payload,
        sample_runtime_elements,
        open_selection_step={"component": "toolbar", "operation": "click", "target": {"label": "选择"}},
    )

    assert report.success is True
    assert report.steps[4].data["auto_restored_template"] is True
    assert runtime.clicked_targets == ["新增", "选择", "保存"]
    assert runtime.toolbar_click_details[-1]["fieldid"] == "btnSave"


def test_workflow_executor_restores_form_after_action_selection_template_confirm(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    report, runtime = _run_selection_template_restore_case(
        sample_template_payload,
        sample_runtime_elements,
        open_selection_step={"component": "action", "operation": "click", "target": {"fieldid": "selectInfoBtn"}},
    )

    assert report.success is True
    assert report.steps[4].data["auto_restored_template"] is True
    assert runtime.clicked_fieldids == ["selectInfoBtn"]
    assert runtime.clicked_targets == ["新增", "保存"]
    assert runtime.toolbar_click_details[-1]["fieldid"] == "btnSave"


def test_workflow_executor_restores_parent_template_after_row_action_popup_reference_select(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    allocation_template = deepcopy(sample_template_payload)
    allocation_root = allocation_template["data"]["uidata"][0]
    material_table = next(child for child in allocation_root["children"] if child.get("nodeType") == "table")
    material_table["label"] = "物资信息"
    outbound_table = deepcopy(material_table)
    outbound_table["key"] = outbound_table["divCode"] = "outboundTable"
    outbound_table["label"] = "物资申请出库信息"
    outbound_table["children"] = [
        {
            "key": "allocationQuantity",
            "divCode": "allocationQuantity",
            "nodeType": "formItem",
            "label": "分配数量",
            "name": "YDFInputNumber",
            "dataField": "allocationQuantity",
        }
    ]
    allocation_root["children"].append(outbound_table)

    reference_template = deepcopy(sample_template_payload)
    reference_root = reference_template["data"]["uidata"][0]
    reference_root["key"] = reference_root["divCode"] = "referenceRoot"
    reference_table = next(child for child in reference_root["children"] if child.get("nodeType") == "table")
    reference_table["label"] = "表格"
    allocation_elements = [
        *sample_runtime_elements,
        {
            "fieldid": "allocationQuantity",
            "text": "分配数量",
            "tag_name": "th",
            "visible": True,
            "selector": '[fieldid="allocationQuantity"]',
        },
    ]

    class RowActionReferenceRuntime(FakeRuntime):
        phase = "allocation"

        def capture_runtime_elements(self, manifest) -> list[dict]:
            return allocation_elements if self.phase == "allocation" else sample_runtime_elements

        def click_row_action(self, action_label: str) -> None:
            super().click_row_action(action_label)
            self.phase = "reference"

        def select_popup_reference(self, **kwargs) -> dict[str, Any]:
            result = super().select_popup_reference(**kwargs)
            self.phase = "allocation"
            return result

    runtime = RowActionReferenceRuntime(
        allocation_elements,
        dynamic_template_payloads_by_row_action={"选择库存": reference_template},
    )
    executor = WorkflowExecutor(gateway=FakeGateway(allocation_template), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table_row_action",
                "operation": "click",
                "target": {"table": "物资信息", "action": "选择库存", "row_number": 1},
            },
            {
                "component": "popup_reference",
                "operation": "select",
                "target": {"title": "选择库存", "row_number": 1},
            },
            {
                "component": "editable_table",
                "operation": "fill_row",
                "target": {"table": "物资申请出库信息", "fields": {"分配数量": "1"}},
            },
        ]
    )

    assert report.success is True
    assert report.steps[2].data["auto_restored_template"] is True
    assert runtime.editable_table_fills[-1]["table"] == "物资申请出库信息"


def test_workflow_executor_restores_form_template_after_confirmed_popup_reference_dialog_closes(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    list_template_payload = deepcopy(sample_template_payload)
    list_template_payload["data"]["actionEL"]["create"] = {
        "key": "create_btn",
        "divCode": "xz_btn",
        "nodeType": "leafItem",
        "label": "新增",
        "name": "Button",
        "rightflag": "create",
        "parentKeys": ["root", "toolbar_root"],
    }
    edit_template_payload = deepcopy(sample_template_payload)
    edit_template_payload["data"]["uidata"][0]["children"] = [
        {
            "key": "editToolbar",
            "divCode": "editToolbar",
            "nodeType": "toolbar",
            "label": "按钮工具栏",
            "parentKey": "root",
            "children": [
                {
                    "key": "addSubject",
                    "divCode": "addSubject",
                    "nodeType": "leafItem",
                    "label": "新增标的信息",
                    "name": "YDFButton",
                    "rightflag": "add-subject",
                },
                {
                    "key": "btnSave",
                    "divCode": "btnSave",
                    "nodeType": "leafItem",
                    "label": "保存",
                    "name": "YDFButton",
                    "rightflag": "save",
                },
            ],
        },
        {
            "key": "contractCard",
            "divCode": "contractCard",
            "nodeType": "card",
            "label": "合同信息",
            "children": [
                {
                    "key": "contractNo",
                    "divCode": "contractNo",
                    "nodeType": "formItem",
                    "label": "合同编号",
                    "name": "YDFInput",
                    "dataField": "contractNo",
                }
            ],
        },
    ]
    edit_template_payload["data"]["actionEL"] = {}
    reference_template_payload = deepcopy(sample_template_payload)
    reference_template_payload["data"]["uidata"][0]["children"] = [
        {
            "key": "referenceToolbar",
            "divCode": "referenceToolbar",
            "nodeType": "toolbar",
            "label": "按钮工具栏",
            "parentKey": "root",
            "children": [
                {
                    "key": "cancel",
                    "divCode": "cancel",
                    "nodeType": "leafItem",
                    "label": "取消",
                    "name": "YDFButton",
                    "rightflag": "cancel",
                },
                {
                    "key": "confirm",
                    "divCode": "confirm",
                    "nodeType": "leafItem",
                    "label": "确定",
                    "name": "YDFButton",
                    "rightflag": "confirm",
                },
            ],
        },
        {
            "key": "transientFields",
            "divCode": "transientFields",
            "nodeType": "card",
            "label": "参照缓存字段",
            "children": [
                {
                    "key": fieldid,
                    "divCode": fieldid,
                    "nodeType": "formItem",
                    "label": label,
                    "name": "YDFInput",
                    "dataField": fieldid,
                }
                for fieldid, label in (
                    ("contractNo", "合同编号"),
                    ("contractName", "合同名称"),
                    ("supplier", "采购供应商"),
                    ("signLocation", "签订地点"),
                )
            ],
        },
    ]
    reference_template_payload["data"]["actionEL"] = {}

    edit_elements = [
        {
            "fieldid": "addSubject",
            "id": None,
            "text": "新增标的信息",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="addSubject"]',
        },
        {
            "fieldid": "btnSave",
            "id": None,
            "text": "保存",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="btnSave"]',
        },
        {
            "fieldid": "editCancel",
            "id": None,
            "text": "取消",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="editCancel"]',
        },
        {
            "fieldid": "contractNo",
            "id": "contractNo",
            "text": "合同编号",
            "role": "textbox",
            "tag_name": "input",
            "visible": True,
            "selector": '[fieldid="contractNo"] input',
        },
        {
            "fieldid": "contractName",
            "id": "contractName",
            "text": "合同名称",
            "role": "textbox",
            "tag_name": "input",
            "visible": True,
            "selector": '[fieldid="contractName"] input',
        },
        {
            "fieldid": "supplier",
            "id": "supplier",
            "text": "采购供应商",
            "role": "textbox",
            "tag_name": "input",
            "visible": True,
            "selector": '[fieldid="supplier"] input',
        },
        {
            "fieldid": "signLocation",
            "id": "signLocation",
            "text": "签订地点",
            "role": "textbox",
            "tag_name": "input",
            "visible": True,
            "selector": '[fieldid="signLocation"] input',
        },
    ]
    reference_elements = [
        {
            "fieldid": "cancel",
            "id": None,
            "text": "取消",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="cancel"]',
        },
        {
            "fieldid": "confirm",
            "id": None,
            "text": "确定",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="confirm"]',
        },
    ]

    class SameRootReferenceRuntime(FakeRuntime):
        phase = "list"

        def capture_runtime_elements(self, manifest) -> list[dict]:
            if self.phase == "edit":
                return list(edit_elements)
            if self.phase == "reference":
                return list(reference_elements)
            return super().capture_runtime_elements(manifest)

        def click_toolbar_action(
            self,
            label: str,
            sub_label: str | None = None,
            fieldid: str | None = None,
            aliases: list[str] | None = None,
        ) -> None:
            super().click_toolbar_action(label, sub_label=sub_label, fieldid=fieldid, aliases=aliases)
            if label == "新增":
                self.phase = "edit"
            elif label == "新增标的信息":
                self.phase = "reference"

        def select_popup_reference(
            self,
            *,
            title: str | None = None,
            target: dict[str, Any] | None = None,
            confirm: bool = True,
        ) -> dict[str, Any]:
            result = super().select_popup_reference(title=title, target=target, confirm=confirm)
            self.phase = "edit"
            return result

    runtime = SameRootReferenceRuntime(
        [
            *sample_runtime_elements,
            {
                "fieldid": "xz_btn",
                "id": None,
                "text": "新增",
                "role": "button",
                "tag_name": "button",
                "visible": True,
                "selector": '[fieldid="xz_btn"]',
            },
        ],
        dynamic_template_payloads_by_toolbar_click={
            "新增": edit_template_payload,
            "新增标的信息": reference_template_payload,
        },
    )
    executor = WorkflowExecutor(gateway=FakeGateway(list_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "新增"}},
            {"component": "toolbar", "operation": "click", "target": {"label": "新增标的信息"}},
            {
                "component": "popup_reference",
                "operation": "select",
                "target": {"title": "标的信息", "match": {"column": "", "equals": 1}},
            },
            {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
        ]
    )

    assert report.success is True
    assert report.steps[3].data["auto_restored_template"] is True
    assert runtime.clicked_targets == ["新增", "新增标的信息", "保存"]
    assert runtime.toolbar_click_details[-1]["fieldid"] == "btnSave"


def test_workflow_executor_records_failed_component_step_context(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements, should_find_tree=False)
    runtime.notifications = [{"type": "error", "message": "系统提示: 未找到机构"}]
    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=runtime,
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "tree", "operation": "select", "target": {"label": "不存在的机构"}},
        ]
    )

    failed = report.steps[-1]
    assert report.success is False
    assert failed.action == "tree.select"
    assert failed.success is False
    assert failed.data["step_index"] == 2
    assert failed.data["step"] == {"component": "tree", "operation": "select", "target": {"label": "不存在的机构"}}
    assert failed.data["error"]["type"] == "RuntimeError"
    assert "未找到树节点" in failed.data["error"]["message"]
    assert failed.data["notifications"] == [{"type": "error", "message": "系统提示: 未找到机构"}]


@pytest.mark.parametrize("capture_diagnostics", [True, False])
def test_workflow_executor_scopes_failure_artifacts_to_current_step(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
    tmp_path: Path,
    capture_diagnostics: bool,
) -> None:
    import re

    from ydf_browser.report_html import render_html_report
    from ydf_browser.runner import archive_diagnostic_files

    class FailingRuntime(FakeRuntime):
        def open_menu(self, menu_target: MenuTarget) -> None:
            super().open_menu(menu_target)
            self.diagnostic_files.append(str(tmp_path / "earlier-step.png"))

        def click_dialog_button(self, label: str, expect_download: bool = False) -> None:
            if capture_diagnostics:
                for suffix in (".png", ".json"):
                    artifact = tmp_path / f"failure-{len(case_reports)}{suffix}"
                    artifact.write_bytes(b"diagnostic")
                    self.diagnostic_files.append(str(artifact))
            raise RuntimeError(f"未找到可点击弹窗按钮: {label}")

    runtime = FailingRuntime(sample_runtime_elements)
    runtime.diagnostic_files = [str(tmp_path / "earlier-case.png")]
    case_reports = []
    for index in range(3):
        report = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime).run([
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "dialog", "operation": "confirm", "target": {}},
        ])
        assert report.success is False
        assert report.steps[-1].action == "dialog.confirm"
        expected = [str(tmp_path / f"failure-{index}{suffix}") for suffix in (".png", ".json")]
        assert report.steps[-1].data.get("diagnostic_files", []) == (expected if capture_diagnostics else [])
        case_reports.append({"status": "failed", "case": {"code": f"case-{index}"}, "report": report.to_dict()})

    assert len(runtime.diagnostic_files) == 4 + (6 if capture_diagnostics else 0)
    result = {"suite_reports": [{"suite": {"code": "diagnostics"}, "case_reports": case_reports}]}
    archive_diagnostic_files(result, tmp_path / "report")
    output = render_html_report(result, tmp_path / "report" / "report.html")
    rows = re.findall(r'<tr\b[^>]*data-case-row[^>]*>.*?</tr>', output.read_text(), re.S)
    assert len(rows) == 3
    for index, row in enumerate(rows):
        assert row.count("<img ") == (1 if capture_diagnostics else 0)
        if capture_diagnostics:
            assert f"failure-{index}.png" in row
            assert f"failure-{index}.json" in row


def test_workflow_executor_allows_toolbar_action_present_in_template_but_not_initial_binding(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["actionEL"]["export"] = {
        "key": "export_btn",
        "divCode": "dc_btn",
        "nodeType": "leafItem",
        "label": "导出",
        "name": "Button",
        "rightflag": "export",
        "parentKeys": ["root", "toolbar_root"],
    }
    executor = WorkflowExecutor(
        gateway=FakeGateway(template_payload),
        runtime=FakeRuntime(sample_runtime_elements),
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "导出"}},
        ]
    )

    assert report.success is True
    assert executor.runtime.clicked_targets == ["导出"]


def test_workflow_executor_executes_runtime_dynamic_toolbar_dropdown_child(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["actionEL"]["add"] = {
        "key": "add_btn",
        "divCode": "xz_btn",
        "nodeType": "leafItem",
        "label": "新增",
        "name": "YDFDropdownButton",
        "rightflag": "add",
        "parentKeys": ["root", "toolbar_root"],
    }
    runtime_elements = [
        *sample_runtime_elements,
        {
            "fieldid": "xz_btn",
            "id": "add_button",
            "text": "新增",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="xz_btn"]',
        },
    ]
    executor = WorkflowExecutor(
        gateway=FakeGateway(template_payload),
        runtime=FakeRuntime(runtime_elements),
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "toolbar",
                "operation": "click",
                "target": {"label": "新增", "sub_label": "租赁合同"},
            },
        ]
    )

    assert report.success is True
    assert executor.runtime.clicked_targets == ["新增>租赁合同"]


def test_workflow_executor_clicks_code_triggered_toolbar_action_by_semantic_alias(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"][0]["children"].append(
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
    runtime = FakeRuntime(
        [
            *sample_runtime_elements,
            {
                "fieldid": "btnSetting",
                "id": None,
                "text": "设置支付任务类型",
                "role": "button",
                "tag_name": "button",
                "visible": True,
                "selector": '[fieldid="btnSetting"]',
            },
        ]
    )
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "设置支付任务类型"}},
        ]
    )

    assert report.success is True
    assert runtime.toolbar_click_details[-1]["label"] == "设置支付任务类型"
    assert runtime.toolbar_click_details[-1]["fieldid"] == "btnSetting"
    assert "配置" in runtime.toolbar_click_details[-1]["aliases"]
    assert "setTypeData" in runtime.toolbar_click_details[-1]["aliases"]


def test_workflow_executor_executes_transfer_dialog_select(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements, visible_region_fieldids={"table_rule", "table_rule_table"})
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "transfer_dialog",
                "operation": "select",
                "target": {
                    "title": "设置支付任务类型",
                    "left": {
                        "matches": [
                            {"column": "支付任务类型名称", "equals": "工资统发"},
                            {"equals": "补贴发放"},
                        ]
                    },
                    "move": "to_right",
                    "confirm": True,
                },
            },
        ]
    )

    assert report.success is True
    assert runtime.transfer_dialog_selections == [
        {
            "title": "设置支付任务类型",
            "items": [
                {"match": {"column": "支付任务类型名称", "equals": "工资统发"}},
                {"match": {"equals": "补贴发放"}},
            ],
            "move": "to_right",
            "confirm": True,
        }
    ]
    assert report.steps[-1].action == "transfer_dialog.select"


def test_workflow_executor_executes_popup_reference_select(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    target = {
        "title": "选择指标",
        "filter": {
            "conditions": [
                {"field": "部门经济分类科目", "equals": "30101 基本工资"},
            ]
        },
        "match": {"column": "部门经济分类科目", "equals": "30101 基本工资"},
    }
    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "popup_reference",
                "operation": "select",
                "target": target,
            },
        ]
    )

    assert report.success is True
    assert runtime.popup_reference_selections == [
        {"title": "选择指标", "target": target, "confirm": True}
    ]
    assert report.steps[-1].action == "popup_reference.select"
    assert report.steps[-1].data["confirmed"] is True


def test_workflow_executor_executes_popup_reference_select_by_row_number(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "popup_reference",
                "operation": "select",
                "target": {"title": "选择指标", "row_number": 1},
            },
        ]
    )

    assert report.success is True
    assert runtime.popup_reference_selections[-1] == {
        "title": "选择指标",
        "target": {"title": "选择指标", "row_number": 1},
        "confirm": True,
    }


def test_workflow_executor_executes_popup_reference_select_by_value(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    target = {
        "title": "单位遴选",
        "value": "101001 江西省局本级（主管单位/单位经办）",
    }
    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "popup_reference",
                "operation": "select",
                "target": target,
            },
        ]
    )

    assert report.success is True
    assert runtime.popup_reference_selections[-1] == {
        "title": "单位遴选",
        "target": target,
        "confirm": True,
    }


def test_workflow_executor_selects_first_available_table_row(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table_row_selection",
                "operation": "select",
                "target": {"first_available": True},
            },
        ]
    )

    assert report.success is True
    assert [item["row_number"] for item in runtime.selected_row_numbers] == [1]
    assert report.steps[-1].data["table_scope"]["table_fieldid"] == "main_table"


def test_workflow_executor_clicks_first_available_table_row_action(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table_row_action",
                "operation": "click",
                "target": {"action": "编辑", "first_available": True},
            },
        ]
    )

    assert report.success is True
    assert runtime.focused_rows == [
        {
            "row_number": 1,
            "table": "明细表",
            "table_fieldid": "main_table",
            "table_columns": ["项目代码", "金额"],
        }
    ]
    assert runtime.row_action_clicks == ["编辑"]
    assert report.steps[-1].data["table_scope"]["table_fieldid"] == "main_table"


def test_workflow_executor_rejects_ambiguous_table_row_action_before_focus(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"].append(
        {
            "key": "material_table",
            "divCode": "wzxx_table",
            "nodeType": "table",
            "label": "物资信息",
            "children": [],
        }
    )
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table_row_action",
                "operation": "click",
                "target": {"action": "编辑", "row_number": 1},
            },
        ]
    )

    assert report.success is False
    assert runtime.focused_rows == []
    assert "请补充 target.table" in report.errors[0]


def test_workflow_executor_scopes_table_row_action_by_table_name(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"].append(
        {
            "key": "material_table",
            "divCode": "wzxx_table",
            "nodeType": "table",
            "label": "物资信息",
            "children": [
                {
                    "key": "material_name_col",
                    "divCode": "wzxx_table_materialItemName",
                    "nodeType": "column",
                    "label": "物资名称",
                    "name": "TableColumn",
                    "dataField": "materialItemName",
                }
            ],
        }
    )
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table_row_action",
                "operation": "click",
                "target": {"action": "选择库存", "table": "物资信息", "row_number": 1},
            },
        ]
    )

    assert report.success is True
    assert runtime.focused_rows == [
        {
            "row_number": 1,
            "table": "物资信息",
            "table_fieldid": "wzxx_table",
            "table_columns": ["物资名称"],
        }
    ]
    assert runtime.row_action_clicks == ["选择库存"]
    assert report.steps[-1].data["table_scope"]["table_fieldid"] == "wzxx_table"
    assert report.steps[-1].data["table_scope"]["required_columns"] == []


def test_workflow_executor_scopes_table_row_action_match_by_table_name(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"].append(
        {
            "key": "material_table",
            "divCode": "wzxx_table",
            "nodeType": "table",
            "label": "物资信息",
            "children": [
                {
                    "key": "material_name_col",
                    "divCode": "wzxx_table_materialItemName",
                    "nodeType": "column",
                    "label": "物资名称",
                    "name": "TableColumn",
                    "dataField": "materialItemName",
                }
            ],
        }
    )
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table_row_action",
                "operation": "click",
                "target": {
                    "action": "选择库存",
                    "table_name": "物资信息",
                    "match": {"column": "物资名称", "equals": "复印纸"},
                },
            },
        ]
    )

    assert report.success is True
    assert runtime.focused_rows == [
        {
            "column": "物资名称",
            "equals": "复印纸",
            "table": "物资信息",
            "table_fieldid": "wzxx_table",
            "table_columns": ["物资名称"],
        }
    ]
    assert runtime.row_action_clicks == ["选择库存"]
    assert report.steps[-1].data["table_scope"]["table_fieldid"] == "wzxx_table"
    assert report.steps[-1].data["table_scope"]["required_columns"] == ["物资名称"]


def test_workflow_executor_does_not_reuse_previous_editable_table_scope_for_row_action(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"].append(
        {
            "key": "material_table",
            "divCode": "wzxx_table",
            "nodeType": "table",
            "label": "物资信息",
            "children": [
                {
                    "key": "material_name_col",
                    "divCode": "wzxx_table_materialItemName",
                    "nodeType": "column",
                    "label": "物资名称",
                    "name": "TableColumn",
                    "dataField": "materialItemName",
                }
            ],
        }
    )
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "editable_table",
                "operation": "fill_row",
                "target": {"table": "物资信息", "row_number": -1, "fields": {"物资名称": "复印纸"}},
            },
            {
                "component": "table_row_action",
                "operation": "click",
                "target": {"action": "选择库存", "row_number": 1},
            },
        ]
    )

    assert report.success is False
    assert runtime.focused_rows == []
    assert "请补充 target.table" in report.errors[0]


def test_workflow_executor_table_row_action_captures_short_success_notification(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(
        sample_runtime_elements,
        notifications=[{"type": "success", "message": "操作成功"}],
    )

    def collect_notifications() -> list[dict[str, str]]:
        return runtime.notifications if runtime.notification_capture_count else []

    runtime.collect_notifications = collect_notifications  # type: ignore[method-assign]
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table_row_action",
                "operation": "click",
                "target": {"action": "编辑", "row_number": 1},
            },
            {
                "component": "notification",
                "operation": "assert",
                "target": {"message": "操作成功"},
            },
        ]
    )

    assert report.success is True
    assert runtime.notification_capture_count == 1
    assert report.steps[1].data["notifications"] == [{"type": "success", "message": "操作成功"}]
    assert report.steps[2].data["notification"] == {"type": "success", "message": "操作成功"}


def test_workflow_executor_fails_table_row_action_on_unhandled_error_notification(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(
        sample_runtime_elements,
        notifications=[{"type": "error", "message": "生成支付单失败: 付款账户不能为空"}],
    )

    def collect_notifications() -> list[dict[str, str]]:
        return runtime.notifications if runtime.notification_capture_count else []

    runtime.collect_notifications = collect_notifications  # type: ignore[method-assign]
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table_row_action",
                "operation": "click",
                "target": {"action": "编辑", "row_number": 1},
            },
            {"component": "tree", "operation": "select", "target": {"label": "001 办公室"}},
        ]
    )

    assert report.success is False
    assert report.steps[-1].action == "table_row_action.click"
    assert report.steps[-1].success is False
    assert "table_row_action.click 后出现错误提示" in report.errors[0]
    assert "付款账户不能为空" in report.errors[0]
    assert "notification.assert" in report.errors[0]


def test_workflow_executor_allows_table_row_action_error_when_next_step_asserts_it(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(
        sample_runtime_elements,
        notifications=[{"type": "error", "message": "生成支付单失败: 付款账户不能为空"}],
    )

    def collect_notifications() -> list[dict[str, str]]:
        return runtime.notifications if runtime.notification_capture_count else []

    runtime.collect_notifications = collect_notifications  # type: ignore[method-assign]
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table_row_action",
                "operation": "click",
                "target": {"action": "编辑", "row_number": 1},
            },
            {
                "component": "notification",
                "operation": "assert",
                "target": {"type": "error", "contains": "付款账户不能为空"},
            },
        ]
    )

    assert report.success is True
    assert report.steps[1].success is True
    assert report.steps[2].data["notification"] == {
        "type": "error",
        "message": "生成支付单失败: 付款账户不能为空",
    }


def test_workflow_executor_form_fill_prefers_editable_form_item_when_label_duplicates(
    sample_template_payload: dict,
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"] = [
        {
            "key": "summary_card",
            "divCode": "summary_card",
            "nodeType": "card",
            "label": "概要",
            "children": [
                {
                    "key": "summary_contract_name",
                    "divCode": "summary_contract_name",
                    "nodeType": "leafItem",
                    "label": "合同名称",
                    "name": "LCDKeyItem",
                    "dataField": "contractName",
                }
            ],
        },
        {
            "key": "edit_card",
            "divCode": "edit_card",
            "nodeType": "card",
            "label": "基本信息",
            "children": [
                {
                    "key": "form_contract_name",
                    "divCode": "form_contract_name",
                    "nodeType": "formItem",
                    "label": "合同名称",
                    "name": "YDFInput",
                    "dataField": "contractName",
                }
            ],
        },
    ]
    runtime_elements = [
        {
            "fieldid": "summary_contract_name",
            "id": None,
            "text": "合同名称",
            "role": None,
            "tag_name": "div",
            "visible": True,
            "selector": '[fieldid="summary_contract_name"]',
        },
        {
            "fieldid": "form_contract_name",
            "id": "form_contract_name_input",
            "text": "合同名称",
            "role": "textbox",
            "tag_name": "input",
            "visible": True,
            "selector": '[fieldid="form_contract_name"]',
        },
    ]
    executor = WorkflowExecutor(
        gateway=FakeGateway(template_payload),
        runtime=FakeRuntime(runtime_elements),
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "form", "operation": "fill", "target": {"fields": {"合同名称": "Codex合同"}}},
        ]
    )

    assert report.success is True
    assert executor.runtime.filled_fields == [{"fieldid": "form_contract_name", "value": "Codex合同"}]


def test_workflow_executor_form_fill_prefers_editable_runtime_field_when_label_duplicates(
    sample_template_payload: dict,
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"] = [
        {
            "key": "readonly_card",
            "divCode": "readonly_card",
            "nodeType": "card",
            "label": "预算信息",
            "children": [
                {
                    "key": "readonly_price",
                    "divCode": "readonly_price",
                    "nodeType": "formItem",
                    "label": "单价",
                    "name": "YDFInput",
                    "dataField": "readonlyPrice",
                }
            ],
        },
        {
            "key": "editable_card",
            "divCode": "editable_card",
            "nodeType": "card",
            "label": "采购信息",
            "children": [
                {
                    "key": "editable_price",
                    "divCode": "editable_price",
                    "nodeType": "formItem",
                    "label": "单价",
                    "name": "YDFInput",
                    "dataField": "editablePrice",
                }
            ],
        },
    ]
    runtime_elements = [
        {
            "fieldid": "readonly_price",
            "id": "readonly_price_input",
            "text": "单价",
            "role": "textbox",
            "tag_name": "input",
            "visible": True,
            "selector": '[fieldid="readonly_price"]',
            "readonly": True,
            "disabled": False,
            "editable": False,
        },
        {
            "fieldid": "editable_price",
            "id": "editable_price_input",
            "text": "单价",
            "role": "textbox",
            "tag_name": "input",
            "visible": True,
            "selector": '[fieldid="editable_price"]',
            "readonly": False,
            "disabled": False,
            "editable": True,
        },
    ]
    executor = WorkflowExecutor(
        gateway=FakeGateway(template_payload),
        runtime=FakeRuntime(runtime_elements),
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "form", "operation": "fill", "target": {"fields": {"单价": "100000"}}},
        ]
    )

    assert report.success is True
    assert executor.runtime.filled_fields == [{"fieldid": "editable_price", "value": "100000"}]


def test_workflow_executor_form_fill_prefers_editable_refer_field_over_disabled_display_duplicate(
    sample_template_payload: dict,
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"] = [
        {
            "key": "budget_info",
            "divCode": "budget_info",
            "nodeType": "card",
            "label": "采购预算信息",
            "children": [
                {
                    "key": "bgt_pur_item_name",
                    "divCode": "bgt_pur_item_name",
                    "nodeType": "formItem",
                    "label": "采购品目",
                    "name": "YDFInput",
                    "dataField": "bgtPurItemName",
                    "props": {"disabled": 1},
                }
            ],
        },
        {
            "key": "purchase_amount",
            "divCode": "purchase_amount",
            "nodeType": "card",
            "label": "采购内容及金额",
            "children": [
                {
                    "key": "pur_item_code",
                    "divCode": "pur_item_code",
                    "nodeType": "formItem",
                    "label": "采购品目",
                    "name": "YDFTableModalSelect",
                    "dataField": "purItemCode",
                    "dataType": "refer",
                    "props": {"disabled": 0},
                }
            ],
        },
    ]
    runtime_elements = [
        {
            "fieldid": "bgt_pur_item_name_drag",
            "id": "wx-bgt_pur_item_name",
            "name": "采购品目",
            "text": "采购品目",
            "role": None,
            "tag_name": "div",
            "visible": True,
            "selector": '[fieldid="bgt_pur_item_name_drag"]',
            "in_dialog": True,
            "editable": True,
        },
        {
            "fieldid": "pur_item_code",
            "id": None,
            "name": None,
            "text": "采购品目",
            "role": None,
            "tag_name": "div",
            "visible": True,
            "selector": '[uikey="pur_item_code"]',
            "in_dialog": True,
            "editable": True,
        },
    ]
    executor = WorkflowExecutor(
        gateway=FakeGateway(template_payload),
        runtime=FakeRuntime(runtime_elements),
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "form",
                "operation": "fill",
                "target": {
                    "fields": {
                        "采购品目": {
                            "filter": "A02010105",
                            "match": {"column": "政府采购品目代码", "equals": "A02010105"},
                        }
                    }
                },
            },
        ]
    )

    assert report.success is True
    assert executor.runtime.filled_fields == [
        {
            "fieldid": "pur_item_code",
            "value": "{'filter': 'A02010105', 'match': {'column': '政府采购品目代码', 'equals': 'A02010105'}}",
        }
    ]


def test_workflow_executor_rebinds_form_field_that_appears_after_previous_fill(
    sample_template_payload: dict,
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"] = [
        {
            "key": "metric_card",
            "divCode": "metric_card",
            "nodeType": "card",
            "label": "指标信息",
            "children": [
                {
                    "key": "metric_attr",
                    "divCode": "metric_attr",
                    "nodeType": "formItem",
                    "label": "指标属性",
                    "name": "YDFSelect",
                    "dataField": "metricAttr",
                },
                {
                    "key": "score_rule",
                    "divCode": "score_rule",
                    "nodeType": "formItem",
                    "label": "评分规则",
                    "name": "YDFSelect",
                    "dataField": "scoreRule",
                },
            ],
        }
    ]
    metric_attr_element = {
        "fieldid": "metric_attr",
        "id": "metric_attr_input",
        "text": "指标属性",
        "role": "combobox",
        "tag_name": "input",
        "visible": True,
        "selector": '[fieldid="metric_attr"] input',
    }
    score_rule_element = {
        "fieldid": "score_rule",
        "id": "score_rule_input",
        "text": "评分规则",
        "role": "combobox",
        "tag_name": "input",
        "visible": True,
        "selector": '[fieldid="score_rule"] input',
    }
    runtime = FakeRuntime([metric_attr_element])

    def capture_runtime_elements(manifest):
        elements = [metric_attr_element]
        if runtime.field_values.get("metric_attr") == "1 定量":
            elements.append(score_rule_element)
        return elements

    runtime.capture_runtime_elements = capture_runtime_elements
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "form",
                "operation": "fill",
                "target": {"fields": {"指标属性": "1 定量", "评分规则": "04 按完成比例赋分"}},
            },
        ]
    )

    assert report.success is True
    assert runtime.filled_fields == [
        {"fieldid": "metric_attr", "value": "1 定量"},
        {"fieldid": "score_rule", "value": "04 按完成比例赋分"},
    ]


def test_workflow_executor_fills_runtime_only_dialog_field_after_toolbar_action(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["actionEL"]["audit"] = {
        "key": "audit_btn",
        "divCode": "audit_btn",
        "nodeType": "leafItem",
        "label": "审核",
        "name": "Button",
        "rightflag": "audit",
        "parentKeys": ["root", "toolbar_root"],
    }
    audit_button = {
        "fieldid": "audit_btn",
        "id": "audit_button",
        "text": "审核",
        "role": "button",
        "tag_name": "button",
        "visible": True,
        "selector": '[fieldid="audit_btn"]',
    }
    approval_dialog_field = {
        "fieldid": None,
        "id": None,
        "name": "isPreEstimate",
        "placeholder": "",
        "text": "",
        "label_text": "是否事前评估",
        "role": "combobox",
        "tag_name": "input",
        "visible": True,
        "selector": '.wui-modal input[name="isPreEstimate"]',
        "in_dialog": True,
        "editable": True,
    }
    runtime = FakeRuntime([*sample_runtime_elements, audit_button])

    def capture_runtime_elements(manifest):
        elements = [*sample_runtime_elements, audit_button]
        if "审核" in runtime.clicked_targets:
            elements.append(approval_dialog_field)
        return elements

    runtime.capture_runtime_elements = capture_runtime_elements
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "审核"}},
            {"component": "form", "operation": "fill", "target": {"fields": {"是否事前评估": "是"}}},
        ]
    )

    assert report.success is True
    assert runtime.filled_fields[-1] == {"fieldid": "runtime:是否事前评估", "value": "是"}


def test_workflow_executor_does_not_wait_for_missing_manifest_field(
    monkeypatch,
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(
        [
            *sample_runtime_elements,
            {
                "fieldid": "runtime_only_field",
                "label_text": "运行时字段",
                "role": "textbox",
                "tag_name": "input",
                "visible": True,
                "editable": True,
                "selector": '[fieldid="runtime_only_field"]',
            },
        ]
    )
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)
    monkeypatch.setattr(
        executor,
        "_refresh_binding_until_form_field",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("missing manifest field waited for refresh")),
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "form", "operation": "fill", "target": {"fields": {"运行时字段": "测试值"}}},
        ]
    )

    assert report.success is True
    assert runtime.filled_fields[-1] == {"fieldid": "runtime:运行时字段", "value": "测试值"}


def test_workflow_executor_executes_tab_click_component_step(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"].insert(
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
                    "key": "tab_wait_submit",
                    "divCode": "stepWaitSubmit",
                    "nodeType": "leafItem",
                    "label": "待提交",
                    "name": "YDFStepNext",
                }
            ],
        },
    )
    runtime_elements = [
        *sample_runtime_elements,
        {
            "fieldid": "stepWaitSubmit",
            "id": None,
            "name": None,
            "placeholder": None,
            "text": "待提交",
            "role": "tab",
            "tag_name": "div",
            "visible": True,
            "selector": '[fieldid="stepWaitSubmit"]',
        },
    ]
    runtime = FakeRuntime(runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "tab", "operation": "click", "target": {"label": "待提交"}},
        ]
    )

    assert report.success is True
    assert runtime.tab_clicks == [{"label": "待提交", "fieldid": "stepWaitSubmit"}]
    assert report.steps[-1].action == "tab.click"


def test_workflow_executor_executes_capsule_step_tab_click(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"].insert(
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
                },
                {
                    "key": "tab_wait_submit",
                    "divCode": "tabDTJ",
                    "nodeType": "leafItem",
                    "label": "待提交",
                    "name": "YDFStepNext",
                },
            ],
        },
    )
    runtime_elements = [
        *sample_runtime_elements,
        {
            "fieldid": "tabDTJ",
            "id": None,
            "name": None,
            "placeholder": None,
            "text": "待提交",
            "role": None,
            "tag_name": "div",
            "visible": True,
            "selector": '[fieldid="tabDTJ"]',
        },
    ]
    runtime = FakeRuntime(runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "tab", "operation": "click", "target": {"label": "待提交"}},
        ]
    )

    assert report.success is True
    assert runtime.tab_clicks == [{"label": "待提交", "fieldid": "tabDTJ"}]


def test_workflow_executor_can_click_runtime_only_form_tab(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "tab", "operation": "click", "target": {"label": "支出明细"}},
        ]
    )

    assert report.success is True
    assert runtime.tab_clicks == [{"label": "支出明细", "fieldid": None}]


def test_workflow_executor_assert_values_prefers_checkbox_in_current_tab() -> None:
    template_payload = {
        "appCode": "PM",
        "domainKey": "yondif-bm-be",
        "data": {
            "bizObjCode": "pmProjectInfo",
            "uidata": [
                {
                    "key": "root",
                    "divCode": "root",
                    "nodeType": "root",
                    "children": [
                        {
                            "key": "budget_tabs",
                            "divCode": "budgetTabs",
                            "nodeType": "tabs",
                            "label": "预算批复页签",
                            "name": "LCDTabs",
                            "children": [
                                {
                                    "key": "estimate_card",
                                    "divCode": "tabEstimateInfo",
                                    "nodeType": "card",
                                    "label": "测算信息",
                                    "name": "LCDCard",
                                    "children": [
                                        {
                                            "key": "estimate_form",
                                            "divCode": "estimateForm",
                                            "nodeType": "form",
                                            "label": "测算信息",
                                            "name": "LCDPanel",
                                            "children": [
                                                {
                                                    "key": "hide_zero_estimate",
                                                    "divCode": "hideZero",
                                                    "nodeType": "formItem",
                                                    "label": "隐藏0金额行",
                                                    "name": "YDFCheckbox",
                                                    "dataField": "hideZero",
                                                }
                                            ],
                                        }
                                    ],
                                },
                                {
                                    "key": "budget_card",
                                    "divCode": "tabBudgetInfo",
                                    "nodeType": "card",
                                    "label": "项目预算信息",
                                    "name": "LCDCard",
                                    "children": [
                                        {
                                            "key": "budget_form",
                                            "divCode": "budgetForm",
                                            "nodeType": "form",
                                            "label": "项目预算信息",
                                            "name": "LCDPanel",
                                            "children": [
                                                {
                                                    "key": "hide_zero_budget",
                                                    "divCode": "hideZeroBgt",
                                                    "nodeType": "formItem",
                                                    "label": "隐藏0金额行",
                                                    "name": "YDFCheckbox",
                                                    "dataField": "hideZero",
                                                }
                                            ],
                                        }
                                    ],
                                },
                            ],
                        }
                    ],
                }
            ],
        },
    }
    runtime_elements = [
        {
            "fieldid": "tabBudgetInfo_tab",
            "id": None,
            "name": None,
            "placeholder": None,
            "text": "项目预算信息",
            "role": "tab",
            "tag_name": "div",
            "visible": True,
            "selector": '[fieldid="tabBudgetInfo_tab"]',
        },
        {
            "fieldid": "estimateForm_hideZero",
            "id": None,
            "name": "hideZero",
            "placeholder": None,
            "text": "隐藏0金额行",
            "role": "checkbox",
            "tag_name": "label",
            "visible": True,
            "selector": '[fieldid="estimateForm_hideZero"]',
            "editable": True,
        },
        {
            "fieldid": "budgetForm_hideZero",
            "id": None,
            "name": "hideZero",
            "placeholder": None,
            "text": "隐藏0金额行",
            "role": "checkbox",
            "tag_name": "label",
            "visible": True,
            "selector": '[fieldid="budgetForm_hideZero"]',
            "editable": True,
        },
    ]
    runtime = FakeRuntime(runtime_elements, field_values={"estimateForm_hideZero": "off", "budgetForm_hideZero": "on"})
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "tab", "operation": "click", "target": {"label": "项目预算信息"}},
            {
                "component": "form",
                "operation": "assert_values",
                "target": {"fields": {"隐藏0金额行": "on"}},
            },
        ]
    )

    assert report.success is True
    assert report.steps[-1].data["fields"][0]["fieldid"] == "budgetForm_hideZero"


def test_values_match_accepts_checkbox_state_aliases() -> None:
    assert _values_match("on", "已勾选", checkbox=True)
    assert _values_match("on", "选中", checkbox=True)
    assert _values_match("off", "未勾选", checkbox=True)
    assert _values_match("off", "未选中", checkbox=True)
    assert not _values_match("on", "未勾选", checkbox=True)
    assert not _values_match("on", "已勾选")


def test_workflow_executor_executes_editable_table_add_and_fill(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "editable_table",
                "operation": "add_row",
                "target": {"label": "新增", "table": "明细表"},
            },
            {
                "component": "editable_table",
                "operation": "fill_row",
                "target": {
                    "table": "明细表",
                    "row_number": -1,
                    "fields": {
                        "项目代码": "测试明细",
                        "金额": "100",
                    },
                },
            },
        ]
    )

    assert report.success is True
    assert runtime.editable_table_adds == [
        {
            "label": "新增",
            "table": "明细表",
            "row_number": -1,
            "table_fieldid": "main_table",
            "table_columns": ["项目代码", "金额"],
        }
    ]
    assert runtime.editable_table_fills[0]["table"] == "明细表"
    assert runtime.editable_table_fills[0]["row_number"] == -1
    assert runtime.editable_table_fills[0]["values"] == {"项目代码": "测试明细", "金额": "100"}


def test_workflow_executor_rejects_ambiguous_editable_table_add_before_click(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"].append(
        {
            "key": "material_table",
            "divCode": "wzxx_table",
            "nodeType": "table",
            "label": "物资信息",
            "children": [],
        }
    )
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "editable_table", "operation": "add_row", "target": {"label": "新增"}},
        ]
    )

    assert report.success is False
    assert runtime.editable_table_adds == []
    assert "请补充 target.table" in report.errors[0]


def test_workflow_executor_prevalidates_all_editable_table_columns_before_fill(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "editable_table",
                "operation": "fill_row",
                "target": {
                    "table": "明细表",
                    "fields": {"金额": "100", "不存在列": "禁止部分录入"},
                },
            },
        ]
    )

    assert report.success is False
    assert runtime.editable_table_fills == []
    assert "缺少必需列" in report.errors[0]


def test_workflow_executor_resolves_editable_table_add_row_group_title_to_single_table(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    table = template_payload["data"]["uidata"][0]["children"][3]
    table["label"] = "缴库明细表格"
    table["divCode"] = "treasuryDetailTable"
    table["children"][0]["label"] = "缴款金额"
    table["children"][0]["dataField"] = "payAmt"
    table["children"][1]["label"] = "政府非税收入项目"
    table["children"][1]["dataField"] = "incomeItem"
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "editable_table",
                "operation": "add_row",
                "target": {"label": "新增", "table": "缴款明细信息"},
            },
        ]
    )

    assert report.success is True
    assert runtime.editable_table_adds == [
        {
            "label": "新增",
            "table": "缴库明细表格",
            "row_number": -1,
            "table_fieldid": "treasuryDetailTable",
            "table_columns": ["缴款金额", "政府非税收入项目"],
        }
    ]


def test_workflow_executor_fails_add_row_when_existing_table_row_count_does_not_change(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    runtime.add_editable_table_row = lambda **kwargs: {
        **kwargs,
        "row_state_before": {"dataRowCount": 1, "rowTexts": ["1 已有行"]},
        "row_state": {"dataRowCount": 1, "rowTexts": ["1 已有行"]},
        "row_state_changed": False,
        "retry_count": 1,
        "chosen_candidate": {
            "text": "新增",
            "x": 692,
            "y": 727,
            "className": "row-action",
            "rootClassName": "table-body",
            "rowScopedAction": False,
            "tableBodyAction": True,
            "rootText": "1 已有行",
        },
        "first_attempt": {
            "row_state_changed": False,
            "chosen_candidate": {"text": "新增", "x": 692, "y": 727, "className": "row-action", "rootText": "1 已有行"},
        },
    }
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "editable_table",
                "operation": "add_row",
                "target": {"label": "新增", "table": "明细表"},
            },
        ]
    )

    assert report.success is False
    assert "可编辑表格新增行未生效" in report.errors[0]
    assert "before_rows=1; after_rows=1" in report.errors[0]
    assert "retry_count=1" in report.errors[0]
    assert "chosen=新增@692,727" in report.errors[0]
    assert "first_chosen=新增@692,727" in report.errors[0]
    assert "class=row-action" in report.errors[0]
    assert "root_class=table-body" in report.errors[0]
    assert "table_body=True" in report.errors[0]


def test_workflow_executor_resolves_editable_table_fill_row_group_title_to_single_table(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    class MultiSelectEditableRuntime(FakeRuntime):
        def fill_editable_table_row(self, *args, **kwargs) -> dict[str, Any]:
            result = super().fill_editable_table_row(*args, **kwargs)
            result["fields"][0].update(
                {"expected_values": ["1.00"], "actual_values": ["1.00"]}
            )
            return result

    template_payload = deepcopy(sample_template_payload)
    table = template_payload["data"]["uidata"][0]["children"][3]
    table["label"] = "缴库明细表格"
    table["divCode"] = "treasuryDetailTable"
    table["children"][0]["label"] = "缴款金额"
    table["children"][0]["dataField"] = "payAmt"
    table["children"][1]["label"] = "政府非税收入项目"
    table["children"][1]["dataField"] = "incomeItem"
    runtime = MultiSelectEditableRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "editable_table",
                "operation": "fill_row",
                "target": {
                    "table": "缴款明细信息",
                    "row_number": 1,
                    "fields": {"缴款金额": "1.00"},
                },
            },
        ]
    )

    assert report.success is True
    assert runtime.editable_table_fills == [
        {
            "values": {"缴款金额": "1.00"},
            "row_number": 1,
            "table": "缴库明细表格",
            "column_candidates": {
                "缴款金额": build_page_manifest(template_payload).table_columns[0],
            },
        }
    ]
    assert report.steps[-1].data["fields"][0]["expected_values"] == ["1.00"]
    assert report.steps[-1].data["fields"][0]["actual_values"] == ["1.00"]


def test_workflow_executor_selects_editable_table_duplicate_column_by_group(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    table = template_payload["data"]["uidata"][0]["children"][3]
    table["label"] = "三级项目同步"
    table["children"] = [
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
        {
            "key": "remark",
            "divCode": "remark",
            "nodeType": "column",
            "label": "备注",
            "name": "YDFInput",
            "dataField": "remark",
        },
    ]
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "editable_table",
                "operation": "fill_row",
                "target": {
                    "table": "三级项目同步",
                    "row_number": 1,
                    "fields": {
                        "备注": "测试",
                        "当年财政拨款(万元)": {
                            "column_group": "全年执行决算金额",
                            "value": 3,
                        },
                    },
                },
            },
        ]
    )

    assert report.success is True
    fill = runtime.editable_table_fills[-1]
    assert fill["values"] == {"备注": "测试", "当年财政拨款(万元)": 3}
    assert fill["column_candidates"]["当年财政拨款(万元)"].data_field == "finalCurrentAppropriation"
    assert fill["column_candidates"]["当年财政拨款(万元)"].column_groups == ["全年执行决算金额"]


def test_workflow_executor_selects_flat_display_name_column_by_group(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    table = template_payload["data"]["uidata"][0]["children"][3]
    table["label"] = "三级项目"
    table["children"] = [
        {
            "key": "self_current",
            "divCode": "self_current",
            "nodeType": "formItem",
            "label": "全年执行自评金额-当年财政拨款",
            "title": "全年执行自评金额-当年财政拨款",
            "displayName": "全年执行自评金额（万元）.当年财政拨款",
            "name": "YDFInputNumber",
            "dataField": "currentAppropriation",
        },
        {
            "key": "final_current",
            "divCode": "final_current",
            "nodeType": "formItem",
            "label": "全年执行决算金额-当年财政拨款",
            "title": "全年执行决算金额-当年财政拨款",
            "displayName": "全年执行决算金额（万元）.当年财政拨款",
            "name": "YDFInputNumber",
            "dataField": "currentAppropriationPostSync",
        },
    ]
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "editable_table",
                "operation": "fill_row",
                "target": {
                    "table": "三级项目同步",
                    "row_number": 1,
                    "fields": {
                        "当年财政拨款(万元)": {
                            "column_group": "全年执行决算金额",
                            "value": 3,
                        },
                    },
                },
            },
        ]
    )

    assert report.success is True
    fill = runtime.editable_table_fills[-1]
    assert fill["column_candidates"]["当年财政拨款(万元)"].data_field == "currentAppropriationPostSync"
    assert fill["column_candidates"]["当年财政拨款(万元)"].column_groups == ["全年执行决算金额"]


def test_workflow_executor_fills_duplicate_leaf_columns_in_one_list_step(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    table = template_payload["data"]["uidata"][0]["children"][3]
    table["label"] = "三级项目同步"
    table["children"] = [
        {
            "key": "self_group",
            "divCode": "self_group",
            "nodeType": "column",
            "label": "全年执行自评金额",
            "children": [
                {
                    "key": "self_current",
                    "divCode": "self_current",
                    "nodeType": "column",
                    "label": "当年财政拨款(万元)",
                    "dataField": "currentAppropriation",
                }
            ],
        },
        {
            "key": "final_group",
            "divCode": "final_group",
            "nodeType": "column",
            "label": "全年执行决算金额",
            "children": [
                {
                    "key": "final_current",
                    "divCode": "final_current",
                    "nodeType": "column",
                    "label": "当年财政拨款(万元)",
                    "dataField": "currentAppropriationPostSync",
                }
            ],
        },
    ]
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "editable_table",
                "operation": "fill_row",
                "target": {
                    "table": "三级项目同步",
                    "row_number": 1,
                    "fields": [
                        {
                            "field": "当年财政拨款(万元)",
                            "column_group": "全年执行自评金额",
                            "equals": 1,
                        },
                        {
                            "field": "当年财政拨款(万元)",
                            "column_group": "全年执行决算金额",
                            "equals": 2,
                        },
                    ],
                },
            },
        ]
    )

    assert report.success is True
    fill = runtime.editable_table_fills[-1]
    assert fill["values"] == [
        {"key": "当年财政拨款(万元)#1", "column": "当年财政拨款(万元)", "value": 1},
        {"key": "当年财政拨款(万元)#2", "column": "当年财政拨款(万元)", "value": 2},
    ]
    assert fill["column_candidates"]["当年财政拨款(万元)#1"].data_field == "currentAppropriation"
    assert fill["column_candidates"]["当年财政拨款(万元)#2"].data_field == "currentAppropriationPostSync"


def test_workflow_executor_rejects_ambiguous_editable_table_duplicate_column(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    table = template_payload["data"]["uidata"][0]["children"][3]
    table["label"] = "三级项目同步"
    table["children"] = [
        {
            "key": "self_eval_group",
            "divCode": "self_eval_group",
            "nodeType": "column",
            "label": "全年执行自评金额",
            "children": [
                {
                    "key": "self_current",
                    "divCode": "self_current",
                    "nodeType": "column",
                    "label": "当年财政拨款(万元)",
                    "dataField": "currentAppropriation",
                }
            ],
        },
        {
            "key": "final_group",
            "divCode": "final_group",
            "nodeType": "column",
            "label": "全年执行决算金额",
            "children": [
                {
                    "key": "final_current",
                    "divCode": "final_current",
                    "nodeType": "column",
                    "label": "当年财政拨款(万元)",
                    "dataField": "finalCurrentAppropriation",
                }
            ],
        },
    ]
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "editable_table",
                "operation": "fill_row",
                "target": {
                    "table": "三级项目同步",
                    "fields": {"当年财政拨款(万元)": 3},
                },
            },
        ]
    )

    assert report.success is False
    assert "可编辑表格列名不唯一" in report.errors[0]
    assert "全年执行自评金额 > 当年财政拨款(万元)" in report.errors[0]
    assert "全年执行决算金额 > 当年财政拨款(万元)" in report.errors[0]
    assert runtime.editable_table_fills == []


def test_workflow_executor_rejects_mismatched_editable_table_name(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "editable_table",
                "operation": "add_row",
                "target": {"label": "新增", "table": "支出"},
            },
        ]
    )

    assert report.success is False
    assert "表格名称未匹配" in report.errors[0]
    assert "target.table=支出" in report.errors[0]
    assert "明细表" in report.errors[0]
    assert runtime.editable_table_adds == []


def test_workflow_executor_resolves_editable_table_by_parent_card_title(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    table = template_payload["data"]["uidata"][0]["children"][3]
    card = {
        "key": "rule_card",
        "divCode": "rule_card",
        "nodeType": "card",
        "label": "指标挂接规则",
        "children": [table],
    }
    table["key"] = "rule_table_key"
    table["divCode"] = "table_rule"
    table["label"] = "表格"
    table["children"][0]["label"] = "部门支出经济分类"
    table["children"][0]["dataField"] = "depBgtEcoCode"
    table["children"][0]["props"] = {"disabled": 0}
    view_table = deepcopy(table)
    view_table["key"] = "rule_view_table_key"
    view_table["divCode"] = "table_rule_view"
    view_table["children"][0]["dataField"] = "depBgtEcoName"
    view_table["children"][0]["props"] = {"disabled": 1}
    card["children"].append(view_table)
    template_payload["data"]["uidata"][0]["children"][3] = card
    runtime = FakeRuntime(sample_runtime_elements, visible_region_fieldids={"table_rule", "table_rule_table"})
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "editable_table",
                "operation": "fill_row",
                "target": {
                    "table": "指标挂接规则",
                    "row_number": 1,
                    "fields": {"部门支出经济分类": "30101 基本工资"},
                },
            },
        ]
    )

    assert report.success is True
    fill = runtime.editable_table_fills[-1]
    assert fill["table"] == "表格"
    assert fill["column_candidates"]["部门支出经济分类"].region_fieldid == "table_rule"
    assert report.steps[-1].data["requested_table"] == "指标挂接规则"


def test_workflow_executor_rejects_parent_card_title_when_multiple_tables_visible(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    table = template_payload["data"]["uidata"][0]["children"][3]
    card = {
        "key": "rule_card",
        "divCode": "rule_card",
        "nodeType": "card",
        "label": "指标挂接规则",
        "children": [table],
    }
    table["key"] = "rule_table_key"
    table["divCode"] = "table_rule"
    table["label"] = "表格"
    table["children"][0]["label"] = "部门支出经济分类"
    table["children"][0]["dataField"] = "depBgtEcoCode"
    view_table = deepcopy(table)
    view_table["key"] = "rule_view_table_key"
    view_table["divCode"] = "table_rule_view"
    view_table["children"][0]["dataField"] = "depBgtEcoName"
    card["children"].append(view_table)
    template_payload["data"]["uidata"][0]["children"][3] = card
    runtime = FakeRuntime(
        sample_runtime_elements,
        visible_region_fieldids={
            "table_rule",
            "table_rule_table",
            "table_rule_view",
            "table_rule_view_table",
        },
    )
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "editable_table",
                "operation": "fill_row",
                "target": {
                    "table": "指标挂接规则",
                    "row_number": 1,
                    "fields": {"部门支出经济分类": "30101 基本工资"},
                },
            },
        ]
    )

    assert report.success is False
    assert "无法唯一确定表格作用域" in report.errors[0]
    assert "请补充 target.table" in report.errors[0]
    assert "'region_fieldid': 'table_rule'" in report.errors[0]
    assert "'region_fieldid': 'table_rule_view'" in report.errors[0]
    assert runtime.editable_table_fills == []


def test_workflow_executor_resolves_editable_table_by_runtime_fieldid(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    table = template_payload["data"]["uidata"][0]["children"][3]
    table["divCode"] = "table_rule"
    table["label"] = "表格"
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "editable_table",
                "operation": "fill_row",
                "target": {
                    "table": "table_rule_table",
                    "row_number": 1,
                    "fields": {"金额": "100"},
                },
            },
        ]
    )

    assert report.success is True
    fill = runtime.editable_table_fills[-1]
    assert fill["table"] == "表格"
    assert fill["column_candidates"]["金额"].region_fieldid == "table_rule"
    assert report.steps[-1].data["requested_table"] == "table_rule_table"


def test_workflow_executor_editable_table_name_error_lists_fieldids(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    first = template_payload["data"]["uidata"][0]["children"][3]
    first["divCode"] = "table_rule"
    first["label"] = "表格"
    second = deepcopy(first)
    second["key"] = "rule_view_key"
    second["divCode"] = "table_rule_view"
    template_payload["data"]["uidata"][0]["children"].append(second)
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "editable_table",
                "operation": "fill_row",
                "target": {"table": "指标挂接规则", "fields": {"金额": "100"}},
            },
        ]
    )

    assert report.success is False
    error = report.errors[0]
    assert "表格名称未匹配" in error
    assert "'region_fieldid': 'table_rule'" in error
    assert "'runtime_fieldid': 'table_rule_table'" in error
    assert "'region_fieldid': 'table_rule_view'" in error
    assert "'runtime_fieldid': 'table_rule_view_table'" in error


def test_workflow_executor_applies_dynamic_template_after_editable_table_add_row(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    line_form_template = deepcopy(sample_template_payload)
    line_form_template["data"]["uidata"][0]["key"] = "lineForm"
    line_form_template["data"]["uidata"][0]["divCode"] = "lineForm"
    line_form_template["data"]["uidata"][0]["children"] = [
        {
            "key": "line_card",
            "divCode": "line_card",
            "nodeType": "card",
            "label": "计划明细",
            "children": [
                {
                    "key": "purchase_target",
                    "divCode": "purchase_target",
                    "nodeType": "formItem",
                    "label": "采购标的",
                    "name": "TextInput",
                    "dataField": "purchaseTarget",
                }
            ],
        }
    ]
    line_form_template["data"]["actionEL"] = {}
    runtime = FakeRuntime(
        sample_runtime_elements,
        runtime_elements_by_page={
            "lineForm": [
                {
                    "fieldid": "purchase_target",
                    "id": "purchase_target_input",
                    "text": "采购标的",
                    "role": "textbox",
                    "tag_name": "input",
                    "visible": True,
                    "selector": '[fieldid="purchase_target"] input',
                    "in_dialog": True,
                }
            ]
        },
        dynamic_template_payloads_by_editable_table_add={"明细表>新增": line_form_template},
    )
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "editable_table",
                "operation": "add_row",
                "target": {"label": "新增", "table": "明细表", "editor": "form"},
            },
            {
                "component": "form",
                "operation": "fill",
                "target": {"fields": {"采购标的": "测试采购标的"}},
            },
        ]
    )

    assert report.success is True
    assert report.steps[1].data["dynamic_template"]["page"] == "lineForm"
    assert runtime.filled_fields[-1] == {"fieldid": "purchase_target", "value": "测试采购标的"}


def test_editable_table_add_row_skips_template_wait_after_reliable_inline_growth(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    waits: list[int] = []
    runtime.wait_for_dynamic_template_payload = lambda timeout_ms=5000: waits.append(timeout_ms)  # type: ignore[attr-defined]
    runtime.add_editable_table_row = lambda **_kwargs: {  # type: ignore[method-assign]
        "row_state_before": {"dataRowCount": 0},
        "row_state": {"dataRowCount": 1},
        "row_state_reliable": True,
        "row_state_changed": True,
    }
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "editable_table",
                "operation": "add_row",
                "target": {"label": "新增", "table": "明细表", "editor": "inline"},
            },
        ]
    )

    assert report.success is True
    assert waits == []


def test_editable_table_form_add_row_keeps_template_wait_after_empty_state_click(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(
        sample_runtime_elements,
        dynamic_template_payloads_by_editable_table_add={"明细表>新增": sample_template_payload},
    )
    waits: list[int] = []
    runtime.wait_for_dynamic_template_payload = lambda timeout_ms=5000: waits.append(timeout_ms)  # type: ignore[attr-defined]

    def add_empty_table_row(*, label: str = "新增", table_scope=None) -> dict[str, Any]:
        runtime.next_dynamic_template_payload = sample_template_payload
        return {
            "label": label,
            "table": table_scope.label,
            "row_state_before": {"dataRowCount": 0, "empty": True},
            "row_state": {"dataRowCount": 0, "empty": True},
            "row_state_reliable": True,
            "row_state_changed": False,
        }

    runtime.add_editable_table_row = add_empty_table_row  # type: ignore[method-assign]
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "editable_table",
                "operation": "add_row",
                "target": {"label": "新增", "table": "明细表", "editor": "form"},
            },
        ]
    )

    assert report.success is True
    assert report.steps[1].data["dynamic_template"]["page"] == "root"
    assert waits == [5000]


def test_editable_table_empty_add_row_without_growth_or_form_fails(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    runtime.wait_for_dynamic_template_payload = lambda timeout_ms=5000: None  # type: ignore[attr-defined]
    runtime.add_editable_table_row = lambda *, label="新增", table_scope=None: {  # type: ignore[method-assign]
        "label": label,
        "table": table_scope.label,
        "row_state_before": {"dataRowCount": 0, "empty": True},
        "row_state": {"dataRowCount": 0, "rowTexts": ["暂无数据"], "empty": True},
        "row_state_reliable": True,
        "row_state_changed": False,
    }
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "editable_table",
                "operation": "add_row",
                "target": {"label": "新增", "table": "明细表", "editor": "auto"},
            },
        ]
    )

    assert report.success is False
    assert "可编辑表格新增行未生效" in report.errors[0]
    assert "before_rows=0; after_rows=0" in report.errors[0]


def test_workflow_executor_restores_parent_table_after_editable_table_dialog_confirm(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    line_form_template = deepcopy(sample_template_payload)
    line_form_template["data"]["uidata"][0]["key"] = "lineForm"
    line_form_template["data"]["uidata"][0]["divCode"] = "lineForm"
    line_form_template["data"]["uidata"][0]["children"] = [
        {
            "key": "line_card",
            "divCode": "line_card",
            "nodeType": "card",
            "label": "计划明细",
            "children": [
                {
                    "key": "purchase_target",
                    "divCode": "purchase_target",
                    "nodeType": "formItem",
                    "label": "采购标的",
                    "name": "TextInput",
                    "dataField": "purchaseTarget",
                }
            ],
        }
    ]
    line_form_template["data"]["actionEL"] = {}
    runtime = FakeRuntime(
        sample_runtime_elements,
        runtime_elements_by_page={
            "root": sample_runtime_elements,
            "lineForm": [
                {
                    "fieldid": "purchase_target",
                    "id": "purchase_target_input",
                    "text": "采购标的",
                    "role": "textbox",
                    "tag_name": "input",
                    "visible": True,
                    "selector": '[fieldid="purchase_target"] input',
                    "in_dialog": True,
                }
            ],
        },
        dynamic_template_payloads_by_editable_table_add={"明细表>新增": line_form_template},
    )
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "editable_table",
                "operation": "add_row",
                "target": {"label": "新增", "table": "明细表", "editor": "form"},
            },
            {"component": "dialog", "operation": "confirm", "target": {"label": "确定"}},
            {
                "component": "editable_table",
                "operation": "fill_row",
                "target": {"table": "明细表", "fields": {"金额": "100"}},
            },
        ]
    )

    assert report.success is True
    assert report.steps[2].data["restored_template"]["page"] == "root"


def test_workflow_executor_restores_parent_table_after_table_row_action_dialog_confirm(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    row_form_template = deepcopy(sample_template_payload)
    row_form_template["data"]["uidata"][0]["key"] = "rowForm"
    row_form_template["data"]["uidata"][0]["divCode"] = "rowForm"
    row_form_template["data"]["uidata"][0]["children"] = [
        {
            "key": "row_card",
            "divCode": "row_card",
            "nodeType": "card",
            "label": "计划明细",
            "children": [
                {
                    "key": "purchase_target",
                    "divCode": "purchase_target",
                    "nodeType": "formItem",
                    "label": "采购标的",
                    "name": "TextInput",
                    "dataField": "purchaseTarget",
                }
            ],
        }
    ]
    row_form_template["data"]["actionEL"] = {}
    runtime = FakeRuntime(
        sample_runtime_elements,
        runtime_elements_by_page={
            "root": sample_runtime_elements,
            "rowForm": [
                {
                    "fieldid": "purchase_target",
                    "id": "purchase_target_input",
                    "text": "采购标的",
                    "role": "textbox",
                    "tag_name": "input",
                    "visible": True,
                    "selector": '[fieldid="purchase_target"] input',
                    "in_dialog": True,
                }
            ],
        },
        dynamic_template_payloads_by_row_action={"编辑": row_form_template},
    )
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table_row_action",
                "operation": "click",
                "target": {"action": "编辑", "match": {"column": "项目代码", "equals": "P001"}},
            },
            {"component": "dialog", "operation": "confirm", "target": {"label": "确定"}},
            {
                "component": "editable_table",
                "operation": "fill_row",
                "target": {"table": "明细表", "fields": {"金额": "100"}},
            },
        ]
    )

    assert report.success is True
    assert report.steps[2].data["restored_template"]["page"] == "root"


def test_workflow_executor_restores_toolbar_dynamic_dialog_before_query_after_confirm(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    list_template = deepcopy(sample_template_payload)
    list_template["data"]["uidata"][0]["children"].append(
        {
            "key": "query_box",
            "divCode": "queryBox",
            "nodeType": "form",
            "label": "查询区",
            "children": [
                {
                    "key": "query_name",
                    "divCode": "query_name",
                    "nodeType": "formItem",
                    "label": "项目名称",
                    "name": "TextInput",
                    "dataField": "projectName",
                }
            ],
        }
    )
    list_template["data"]["actionEL"]["manager"] = {
        "key": "manager_btn",
        "divCode": "manager_btn",
        "nodeType": "leafItem",
        "label": "设置经费管理员",
        "name": "Button",
        "rightflag": "manager",
        "parentKeys": ["root", "toolbar_root"],
    }
    list_template["data"]["actionEL"]["query"] = {
        "key": "query_btn",
        "divCode": "query_btn",
        "nodeType": "leafItem",
        "label": "查询",
        "name": "Button",
        "rightflag": "query",
        "parentKeys": ["root", "queryBox"],
    }

    manager_template = deepcopy(sample_template_payload)
    manager_template["data"]["uidata"][0]["key"] = "managerRoot"
    manager_template["data"]["uidata"][0]["divCode"] = "managerRoot"
    manager_template["data"]["uidata"][0]["children"] = [
        {
            "key": "manager_card",
            "divCode": "managerCard",
            "nodeType": "card",
            "label": "经费管理员",
            "children": [
                {
                    "key": "budget_manager",
                    "divCode": "budget_manager",
                    "nodeType": "formItem",
                    "label": "经费管理员",
                    "name": "TextInput",
                    "dataField": "budgetManager",
                }
            ],
        }
    ]
    manager_template["data"]["actionEL"] = {
        "confirm": {
            "key": "confirm_btn",
            "divCode": "confirm_btn",
            "nodeType": "leafItem",
            "label": "确认",
            "name": "Button",
            "rightflag": "confirm",
            "parentKeys": ["managerRoot"],
        }
    }

    runtime = FakeRuntime(
        sample_runtime_elements,
        runtime_elements_by_page={
            "root": [
                *sample_runtime_elements,
                {
                    "fieldid": "manager_btn",
                    "id": None,
                    "text": "设置经费管理员",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="manager_btn"]',
                },
                {
                    "fieldid": "queryBox_projectName",
                    "id": None,
                    "name": "projectName",
                    "placeholder": "项目名称",
                    "text": "",
                    "role": "textbox",
                    "tag_name": "input",
                    "visible": True,
                    "selector": '[fieldid="queryBox_projectName"] input',
                },
                {
                    "fieldid": "query_btn",
                    "id": None,
                    "text": "查询",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="query_btn"]',
                },
            ],
            "managerRoot": [],
        },
        dynamic_template_payloads_by_toolbar_click={"设置经费管理员": manager_template},
        notifications=[{"type": "success", "message": "更新成功！"}],
    )
    executor = WorkflowExecutor(gateway=FakeGateway(list_template), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "设置经费管理员"}},
            {"component": "dialog", "operation": "confirm", "target": {"label": "确认"}},
            {
                "component": "query",
                "operation": "search",
                "target": {"conditions": [{"field": "项目名称", "equals": "ui自动化wdy0088"}]},
            },
        ]
    )

    assert report.success is True
    assert report.steps[2].data["restored_template"]["page"] == "root"
    assert report.steps[2].data["auto_restored_template"] is True
    assert runtime.query_filled_fields == [{"fieldid": "queryBox_projectName", "value": "ui自动化wdy0088"}]
    assert runtime.clicked_targets == ["设置经费管理员", "查询"]


def test_workflow_executor_preserves_toolbar_dynamic_dialog_after_confirm_when_field_stays_visible(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    list_template = deepcopy(sample_template_payload)
    list_template["data"]["actionEL"]["manager"] = {
        "key": "manager_btn",
        "divCode": "manager_btn",
        "nodeType": "leafItem",
        "label": "设置经费管理员",
        "name": "Button",
        "rightflag": "manager",
        "parentKeys": ["root", "toolbar_root"],
    }

    manager_template = deepcopy(sample_template_payload)
    manager_template["data"]["uidata"][0]["key"] = "managerRoot"
    manager_template["data"]["uidata"][0]["divCode"] = "managerRoot"
    manager_template["data"]["uidata"][0]["children"] = [
        {
            "key": "manager_card",
            "divCode": "managerCard",
            "nodeType": "card",
            "label": "经费管理员",
            "children": [
                {
                    "key": "budget_manager",
                    "divCode": "budget_manager",
                    "nodeType": "formItem",
                    "label": "经费管理员",
                    "name": "TextInput",
                    "dataField": "budgetManager",
                }
            ],
        }
    ]
    manager_template["data"]["actionEL"] = {
        "confirm": {
            "key": "confirm_btn",
            "divCode": "confirm_btn",
            "nodeType": "leafItem",
            "label": "确认",
            "name": "Button",
            "rightflag": "confirm",
            "parentKeys": ["managerRoot"],
        }
    }

    runtime = FakeRuntime(
        sample_runtime_elements,
        runtime_elements_by_page={
            "root": sample_runtime_elements,
            "managerRoot": [
                {
                    "fieldid": "budget_manager",
                    "id": "budget_manager_input",
                    "text": "经费管理员",
                    "role": "textbox",
                    "tag_name": "input",
                    "visible": True,
                    "selector": '[fieldid="budget_manager"] input',
                },
                {
                    "fieldid": "confirm_btn",
                    "id": "confirm_button",
                    "text": "确认",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="confirm_btn"]',
                }
            ],
        },
        dynamic_template_payloads_by_toolbar_click={"设置经费管理员": manager_template},
        notifications=[{"type": "success", "message": "更新成功！"}],
    )
    executor = WorkflowExecutor(gateway=FakeGateway(list_template), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "设置经费管理员"}},
            {"component": "dialog", "operation": "confirm", "target": {"label": "确认"}},
            {
                "component": "form",
                "operation": "fill",
                "target": {"fields": {"经费管理员": "人员二十一"}},
            },
        ]
    )

    assert report.success is True
    assert "auto_restored_template" not in report.steps[2].data
    assert runtime.filled_fields[-1] == {"fieldid": "budget_manager", "value": "人员二十一"}


def test_workflow_executor_preserves_toolbar_dynamic_dialog_after_confirm_error(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    class DialogErrorRuntime(FakeRuntime):
        def collect_notifications(self) -> list[dict[str, str]]:
            if self.dialog_clicks:
                return [{"type": "error", "message": "更新失败"}]
            return []

    list_template = deepcopy(sample_template_payload)
    list_template["data"]["actionEL"]["manager"] = {
        "key": "manager_btn",
        "divCode": "manager_btn",
        "nodeType": "leafItem",
        "label": "设置经费管理员",
        "name": "Button",
        "rightflag": "manager",
        "parentKeys": ["root", "toolbar_root"],
    }

    manager_template = deepcopy(sample_template_payload)
    manager_template["data"]["uidata"][0]["key"] = "managerRoot"
    manager_template["data"]["uidata"][0]["divCode"] = "managerRoot"
    manager_template["data"]["uidata"][0]["children"] = []
    manager_template["data"]["actionEL"] = {}

    runtime = DialogErrorRuntime(
        sample_runtime_elements,
        runtime_elements_by_page={"root": sample_runtime_elements, "managerRoot": []},
        dynamic_template_payloads_by_toolbar_click={"设置经费管理员": manager_template},
    )
    executor = WorkflowExecutor(gateway=FakeGateway(list_template), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "设置经费管理员"}},
            {"component": "dialog", "operation": "confirm", "target": {"label": "确认"}},
            {
                "component": "notification",
                "operation": "assert",
                "target": {"type": "error", "message_contains": "更新失败"},
            },
        ]
    )

    assert report.success is True
    assert "auto_restored_template" not in report.steps[2].data


def test_workflow_executor_preserves_row_edit_template_after_popup_reference_business_confirm(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    list_template = deepcopy(sample_template_payload)
    list_template["data"]["uidata"][0]["children"][0]["children"] = []
    list_template["data"]["actionEL"] = {
        "detail": {
            "key": "detail_btn",
            "divCode": "xq_btn",
            "nodeType": "leafItem",
            "label": "详情",
            "name": "Button",
            "rightflag": "detail",
            "parentKeys": ["root", "main_table"],
        }
    }

    edit_template = deepcopy(sample_template_payload)
    edit_template["data"]["uidata"][0]["key"] = "editRoot"
    edit_template["data"]["uidata"][0]["divCode"] = "editRoot"
    edit_template["data"]["uidata"][0]["children"] = [
        {
            "key": "edit_toolbar",
            "divCode": "edit_toolbar",
            "nodeType": "toolbar",
            "label": "底部工具栏",
            "name": "LCDBtnToolbar",
            "parentKey": "editRoot",
            "children": [
                {
                    "key": "choose_account",
                    "divCode": "choose_account",
                    "nodeType": "leafItem",
                    "label": "选择付款账户",
                    "name": "YDFButton",
                    "rightflag": "chooseAccount",
                },
                {
                    "key": "save_btn",
                    "divCode": "edit_save_btn",
                    "nodeType": "leafItem",
                    "label": "保存",
                    "name": "YDFButton",
                    "rightflag": "save",
                },
            ],
        },
        {
            "key": "edit_card",
            "divCode": "edit_card",
            "nodeType": "card",
            "label": "支付信息",
            "children": [
                {
                    "key": "account_name",
                    "divCode": "account_name",
                    "nodeType": "formItem",
                    "label": "账户名称",
                    "name": "YDFTableModalSelect",
                    "dataField": "accountName",
                }
            ],
        },
    ]
    edit_template["data"]["actionEL"] = {}

    list_runtime_elements = [
        {
            "fieldid": "project_code_col",
            "id": None,
            "text": "项目代码",
            "role": None,
            "tag_name": "th",
            "visible": True,
            "selector": '[fieldid="project_code_col"]',
        }
    ]
    edit_runtime_elements = [
        {
            "fieldid": "choose_account",
            "id": None,
            "name": None,
            "placeholder": None,
            "text": "选择付款账户",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="choose_account"]',
        },
        {
            "fieldid": "edit_save_btn",
            "id": None,
            "name": None,
            "placeholder": None,
            "text": "保存",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="edit_save_btn"]',
        },
        {
            "fieldid": "account_name",
            "id": "account_name_input",
            "text": "账户名称",
            "role": "textbox",
            "tag_name": "input",
            "visible": True,
            "selector": '[fieldid="account_name"] input',
        },
    ]
    runtime = FakeRuntime(
        list_runtime_elements,
        runtime_elements_by_page={
            "root": list_runtime_elements,
            "editRoot": edit_runtime_elements,
        },
        dynamic_template_payloads_by_row_action={"编辑": edit_template},
    )
    executor = WorkflowExecutor(gateway=FakeGateway(list_template), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table_row_action",
                "operation": "click",
                "target": {"action": "编辑", "row_number": 1},
            },
            {"component": "toolbar", "operation": "click", "target": {"label": "选择付款账户"}},
            {
                "component": "popup_reference",
                "operation": "select",
                "target": {"title": "选择付款账户", "row_number": 1},
            },
            {"component": "dialog", "operation": "confirm", "target": {"label": "确定"}},
            {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
        ]
    )

    assert report.success is True
    assert "auto_restored_template" not in report.steps[4].data
    assert runtime.clicked_targets == ["编辑", "选择付款账户", "保存"]
    assert runtime.toolbar_click_details[-1]["fieldid"] == "edit_save_btn"


def test_workflow_executor_restores_parent_after_table_row_action_toolbar_confirm(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    row_form_template = deepcopy(sample_template_payload)
    row_form_template["data"]["uidata"][0]["key"] = "rowForm"
    row_form_template["data"]["uidata"][0]["divCode"] = "rowForm"
    row_form_template["data"]["uidata"][0]["children"] = [
        {
            "key": "confirm_toolbar",
            "divCode": "confirm_toolbar",
            "nodeType": "toolbar",
            "label": "底部工具栏",
            "name": "LCDBtnToolbar",
            "parentKey": "rowForm",
            "children": [
                {
                    "key": "confirm_btn",
                    "divCode": "confirm_btn",
                    "nodeType": "leafItem",
                    "label": "确定",
                    "name": "YDFButton",
                }
            ],
        }
    ]
    row_form_template["data"]["actionEL"] = {}
    runtime = FakeRuntime(
        sample_runtime_elements,
        runtime_elements_by_page={
            "root": [
                *sample_runtime_elements,
                {
                    "fieldid": "confirm_btn",
                    "id": None,
                    "text": "确定",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="confirm_btn"]',
                    "in_dialog": True,
                },
            ],
            "rowForm": [
                {
                    "fieldid": "confirm_btn",
                    "id": None,
                    "text": "确定",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="confirm_btn"]',
                    "in_dialog": True,
                }
            ],
        },
        dynamic_template_payloads_by_row_action={"汇总规则": row_form_template},
    )
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table_row_action",
                "operation": "click",
                "target": {"action": "汇总规则", "row_number": 1},
            },
            {"component": "toolbar", "operation": "click", "target": {"label": "确定"}},
            {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
        ]
    )

    assert report.success is True
    assert report.steps[2].data["restored_template"]["page"] == "root"
    assert runtime.toolbar_click_details[-1]["label"] == "保存"


def test_workflow_executor_passes_editable_table_column_metadata_to_runtime(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    table = sample_template_payload["data"]["uidata"][0]["children"][3]
    table["label"] = "一级权重明细"
    table["children"][0].update(
        {
            "label": "一级指标",
            "name": "YDFTreeModalSelect",
            "dataField": "firstIndexCode",
            "dataType": "refer",
            "enty": {"info": {"ctpltype": "Tree"}, "label": "一级绩效指标参照（参照树）"},
        }
    )
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "editable_table",
                "operation": "fill_row",
                "target": {
                    "table": "一级权重明细",
                    "row_number": 1,
                    "fields": {"一级指标": "101 成本指标"},
                },
            },
        ]
    )

    assert report.success is True
    candidates = runtime.editable_table_fills[-1]["column_candidates"]
    assert candidates["一级指标"].component_name == "YDFTreeModalSelect"
    assert candidates["一级指标"].fieldid == "project_code_col"
    assert candidates["一级指标"].data_field == "firstIndexCode"
    assert candidates["一级指标"].region_fieldid == "main_table"
    assert candidates["一级指标"].raw["dataType"] == "refer"
    assert report.steps[1].data["fields"] == [
        {
            "column": "一级指标",
            "value": "101 成本指标",
            "fieldid": "project_code_col",
            "data_field": "firstIndexCode",
            "table_fieldid": "main_table",
            "locator_source": "identity-cell",
        }
    ]


def test_workflow_executor_prefers_visible_duplicate_editable_table_column_metadata(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    table = sample_template_payload["data"]["uidata"][0]["children"][3]
    table["children"] = [
        {
            "key": "expense_reason",
            "divCode": "expense_reason",
            "nodeType": "formItem",
            "label": "费用名称",
            "title": "支出事由",
            "name": "YDFInput",
            "dataField": "expReason",
            "hide": 1,
        },
        {
            "key": "expense_item",
            "divCode": "expense_item",
            "nodeType": "formItem",
            "label": "费用名称",
            "title": "费用项目编码",
            "name": "YDFTreeSelect",
            "dataField": "expenseItemCode",
            "dataType": "refer",
            "hide": 0,
            "enty": {"info": {"ctpltype": "Tree"}, "label": "费用"},
        },
    ]
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "editable_table",
                "operation": "fill_row",
                "target": {
                    "row_number": -1,
                    "fields": {"费用名称": "办公费"},
                },
            },
        ]
    )

    assert report.success is True
    candidates = runtime.editable_table_fills[-1]["column_candidates"]
    assert candidates["费用名称"].component_name == "YDFTreeSelect"
    assert candidates["费用名称"].visible_by_config is True


def test_workflow_executor_uploads_typed_attachments(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "attachment",
                "operation": "upload",
                "target": {
                    "attachments": [
                        {"type": "询价", "file": "/tmp/inquiry.xlsx"},
                        {"type": "造价材料", "file": "/tmp/cost.xlsx"},
                        {"type": "评审报告", "file": "/tmp/review.xlsx"},
                    ]
                },
            },
        ]
    )

    assert report.success is True
    assert runtime.attachment_uploads == [
        [
            {"type": "询价", "file": "/tmp/inquiry.xlsx"},
            {"type": "造价材料", "file": "/tmp/cost.xlsx"},
            {"type": "评审报告", "file": "/tmp/review.xlsx"},
        ]
    ]
    assert report.steps[-1].data["attachments"][0]["status"] == "success"


def test_workflow_executor_passes_upload_template_nodes_to_runtime(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    sample_template_payload["data"]["uidata"][0]["children"].append(
        {
            "key": "upload_node",
            "divCode": "fjxx",
            "nodeType": "upload",
            "label": "底稿附件",
            "name": "LCDUploadNext",
            "props": {"enableFileType": "pdf,doc,docx"},
        }
    )
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "attachment",
                "operation": "upload",
                "target": {
                    "attachments": [
                        {"type": "底稿附件", "file": "/tmp/workpaper.pdf"},
                    ]
                },
            },
        ]
    )

    assert report.success is True
    assert runtime.attachment_upload_candidates
    assert runtime.attachment_upload_candidates[-1][0]["label"] == "底稿附件"
    assert runtime.attachment_upload_candidates[-1][0]["fieldid"] == "fjxx"
    assert runtime.attachment_upload_candidates[-1][0]["raw"]["props"]["enableFileType"] == "pdf,doc,docx"


def test_workflow_executor_executes_dialog_confirm_step(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)

    def fail_generic_observation(*_args: Any, **_kwargs: Any) -> ActionCompletionObservation:
        raise AssertionError("下载弹窗应保持专用完成协议")

    runtime._observe_action_completion = fail_generic_observation  # type: ignore[method-assign]
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "dialog", "operation": "confirm", "target": {"expect_download": True}},
        ]
    )

    assert report.success is True
    assert runtime.dialog_clicks == [{"label": "确定", "expect_download": True}]


def test_workflow_executor_can_restore_previous_template_after_dialog_click(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    edit_template_payload = deepcopy(sample_template_payload)
    edit_template_payload["data"]["uidata"][0]["divCode"] = "editRoot"
    edit_template_payload["data"]["actionEL"] = {
        "save": {
            "key": "save_btn",
            "divCode": "save_btn",
            "nodeType": "leafItem",
            "label": "保存",
            "name": "Button",
            "rightflag": "save",
            "parentKeys": ["editRoot"],
        }
    }
    list_template_payload = deepcopy(sample_template_payload)
    list_template_payload["data"]["actionEL"]["create"] = {
        "key": "create_btn",
        "divCode": "xz_btn",
        "nodeType": "leafItem",
        "label": "新增",
        "name": "Button",
        "rightflag": "create",
        "parentKeys": ["root"],
    }
    runtime = FakeRuntime(
        [
            *sample_runtime_elements,
            {
                "fieldid": "xz_btn",
                "id": None,
                "name": None,
                "placeholder": None,
                "text": "新增",
                "role": "button",
                "tag_name": "button",
                "visible": True,
                "selector": '[fieldid="xz_btn"]',
            },
        ],
        runtime_elements_by_page={
            "editRoot": [
                {
                    "fieldid": "save_btn",
                    "id": None,
                    "name": None,
                    "placeholder": None,
                    "text": "保存",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="save_btn"]',
                }
            ]
        },
        dynamic_template_payloads_by_toolbar_click={"新增": edit_template_payload},
    )
    executor = WorkflowExecutor(gateway=FakeGateway(list_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "新增"}},
            {"component": "dialog", "operation": "confirm", "target": {"restore_previous": True}},
        ]
    )

    assert report.success is True
    assert report.steps[-1].data["restored_template"]["page"] == "root"


def _run_custom_dialog_restore_scenario(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
    state: str,
) -> tuple[WorkflowExecutor, Any]:
    list_template = deepcopy(sample_template_payload)
    list_template["data"]["actionEL"]["create"] = {
        "key": "create_btn",
        "divCode": "create_btn",
        "nodeType": "leafItem",
        "label": "新增",
        "name": "Button",
        "rightflag": "create",
        "parentKeys": ["root", "toolbar_root"],
    }
    edit_template = deepcopy(sample_template_payload)
    edit_root = edit_template["data"]["uidata"][0]
    edit_toolbar = deepcopy(next(child for child in edit_root["children"] if child.get("nodeType") == "toolbar"))
    edit_form = deepcopy(next(child for child in edit_root["children"] if child.get("key") == "card_base"))
    edit_table = deepcopy(next(child for child in edit_root["children"] if child.get("nodeType") == "table"))
    edit_toolbar.update(key="edit_toolbar", divCode="edit_toolbar")
    edit_toolbar["children"] = [
        {
            **edit_toolbar["children"][0],
            "key": "edit_save",
            "divCode": "edit_save",
        }
    ]
    edit_form.update(key="edit_form", divCode="edit_form", nodeType="form", label="支付信息")
    edit_form["children"] = [
        {
            **edit_form["children"][0],
            "key": "edit_summary",
            "divCode": "edit_summary",
            "label": "支付摘要",
            "dataField": "summary",
        }
    ]
    edit_table.update(key="payee_table", divCode="inc_payee_table", label="收款人信息")
    edit_table["children"] = [
        {
            **edit_table["children"][0],
            "key": "receiver_name",
            "divCode": "receiver_name",
            "label": "收款人全称",
            "dataField": "receiverName",
        }
    ]
    edit_root.update(key="editRoot", divCode="editRoot", children=[edit_toolbar, edit_form, edit_table])
    edit_template["data"]["actionEL"] = {}
    runtime_by_fieldid = {item.get("fieldid"): item for item in sample_runtime_elements}
    list_elements = [
        *sample_runtime_elements,
        {
            **runtime_by_fieldid["btn_save"],
            "fieldid": "create_btn",
            "text": "新增",
            "selector": '[fieldid="create_btn"]',
        },
    ]
    edit_elements = [
        {
            **runtime_by_fieldid["btn_save"],
            "fieldid": "edit_save",
            "selector": '[fieldid="edit_save"]',
        },
        {
            **runtime_by_fieldid["project_name"],
            "fieldid": "edit_summary",
            "text": "支付摘要",
            "selector": '[fieldid="edit_summary"]',
        },
        {
            **runtime_by_fieldid["project_code_col"],
            "fieldid": "receiver_name",
            "text": "收款人全称",
            "selector": '[fieldid="receiver_name"]',
        },
    ]
    label_only_editable_match = {
        **edit_elements[1],
        "fieldid": "list_amount",
        "label_text": "凭证金额",
        "in_dialog": True,
        "selector": '[fieldid="list_amount"]',
    }
    after_dialog = {
        "closed": [*list_elements, label_only_editable_match],
        "active": edit_elements,
        "error": list_elements,
        "insufficient": [runtime_by_fieldid["project_code_col"], edit_elements[-1]],
    }[state]
    runtime = FakeRuntime(
        list_elements,
        runtime_elements_by_page={"root": list_elements, "editRoot": edit_elements},
        dynamic_template_payloads_by_toolbar_click={"新增": edit_template},
        notifications=[{"type": "error", "message": "签章失败"}] if state == "error" else [],
    )
    original_click_dialog_button = runtime.click_dialog_button

    def click_dialog_button(label: str, expect_download: bool = False) -> None:
        original_click_dialog_button(label, expect_download=expect_download)
        runtime.runtime_elements_by_page["root"] = after_dialog
        runtime.runtime_elements_by_page["editRoot"] = after_dialog

    runtime.click_dialog_button = click_dialog_button  # type: ignore[method-assign]
    executor = WorkflowExecutor(gateway=FakeGateway(list_template), runtime=runtime)
    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "新增"}},
            {"component": "dialog", "operation": "click", "target": {"label": "去签章"}},
        ]
    )
    return executor, report


def test_workflow_executor_restores_parent_after_custom_dialog_action_closes_dynamic_form(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    executor, report = _run_custom_dialog_restore_scenario(
        sample_template_payload,
        sample_runtime_elements,
        "closed",
    )

    assert report.success is True
    assert report.steps[-1].data["restored_template"]["page"] == "root"
    assert report.steps[-1].data["auto_restored_template"] is True
    followup = executor.run(
        [
            {
                "component": "table_row_selection",
                "operation": "select",
                "target": {"table": "明细表", "row_number": 1},
            }
        ]
    )
    assert followup.success is True


def test_workflow_executor_keeps_active_dynamic_form_after_custom_dialog_action(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    executor, report = _run_custom_dialog_restore_scenario(
        sample_template_payload,
        sample_runtime_elements,
        "active",
    )

    assert report.success is True
    assert "auto_restored_template" not in report.steps[-1].data
    assert executor.current_manifest.page.fieldid == "editRoot"


def test_workflow_executor_keeps_dynamic_form_after_custom_dialog_action_error(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    executor, report = _run_custom_dialog_restore_scenario(
        sample_template_payload,
        sample_runtime_elements,
        "error",
    )

    assert report.success is False
    assert "auto_restored_template" not in report.steps[-1].data
    assert executor.current_manifest.page.fieldid == "editRoot"


def test_workflow_executor_keeps_dynamic_form_when_custom_dialog_restore_evidence_is_insufficient(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    executor, report = _run_custom_dialog_restore_scenario(
        sample_template_payload,
        sample_runtime_elements,
        "insufficient",
    )

    assert report.success is True
    assert "auto_restored_template" not in report.steps[-1].data
    assert executor.current_manifest.page.fieldid == "editRoot"


def test_workflow_executor_applies_dynamic_template_after_dialog_click(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    list_template_payload = deepcopy(sample_template_payload)
    edit_template_payload = deepcopy(sample_template_payload)
    edit_root = edit_template_payload["data"]["uidata"][0]
    edit_root["divCode"] = "editRoot"
    edit_root["children"] = [
        {
            "key": "editToolbar",
            "divCode": "editToolbar",
            "nodeType": "toolbar",
            "label": "按钮工具栏",
            "parentKey": "editRoot",
            "children": [
                {
                    "key": "chooseIndicator",
                    "divCode": "chooseIndicator",
                    "nodeType": "leafItem",
                    "label": "选择指标",
                    "name": "YDFButton",
                    "rightflag": "choose",
                }
            ],
        }
    ]
    edit_template_payload["data"]["actionEL"] = {}
    runtime = FakeRuntime(
        sample_runtime_elements,
        runtime_elements_by_page={
            "editRoot": [
                {
                    "fieldid": "chooseIndicator",
                    "id": None,
                    "text": "选择指标",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="chooseIndicator"]',
                }
            ]
        },
        dynamic_template_payloads_by_dialog_click={"生成单据": edit_template_payload},
    )
    executor = WorkflowExecutor(gateway=FakeGateway(list_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "dialog", "operation": "click", "target": {"label": "生成单据"}},
            {"component": "toolbar", "operation": "click", "target": {"label": "选择指标"}},
        ]
    )

    assert report.success is True
    assert report.steps[1].data["dynamic_template"]["page"] == "editRoot"
    assert runtime.clicked_targets == ["选择指标"]
    assert runtime.toolbar_click_details[-1]["fieldid"] == "chooseIndicator"


def test_workflow_executor_executes_dialog_cancel_step(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "dialog", "operation": "cancel", "target": {}},
        ]
    )

    assert report.success is True
    assert runtime.dialog_clicks == [{"label": "取消", "expect_download": False}]


def test_workflow_executor_asserts_table_empty(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements, table_column_values={"项目名称": []})
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "table", "operation": "assert_empty", "target": {"column": "项目名称"}},
        ]
    )

    assert report.success is True


def test_workflow_executor_classifies_comparable_assertion_mismatch(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
    tmp_path,
) -> None:
    runtime = FakeRuntime(
        sample_runtime_elements,
        table_column_values={"项目名称": ["现有项目"]},
        table_snapshot_rows=[{"项目编码": "P001", "项目名称": "现有项目"}],
    )
    observation = ObservationSession(
        tmp_path / "events.jsonl",
        tool_version="test",
        run_id="run-1",
        configuration={},
    )
    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=runtime,
        observation_session=observation,
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "table", "operation": "assert_empty", "target": {"column": "项目名称"}},
        ]
    )

    failed = report.steps[-1]
    assert report.success is False
    assert failed.data["error"]["type"] == "BusinessAssertionMismatch"
    assert failed.observation["outcome"] == "assertion_failed"
    assert failed.observation["reason_code"] == "assertion_mismatch"
    assert failed.observation["business_target"] == {"component": "table", "operation": "assert_empty"}
    assert failed.observation["assertion_receipt"]["expected"] == {"column": "项目名称", "empty": True}
    assert failed.observation["assertion_receipt"]["actual"] == {
        "column": "项目名称",
        "values": ["现有项目"],
    }
    bundle_reference = failed.data["failure_evidence_bundle"]["path"]
    bundle = json.loads((tmp_path / bundle_reference).read_text(encoding="utf-8"))
    assert bundle["failure"]["step_id"] == "2"
    assert bundle["failure"]["business_target"] == {"component": "table", "operation": "assert_empty"}
    assert bundle["manifest"]["page"] == "root"
    assert bundle["binding"]["bound_action_count"] == 2
    assert bundle["network"]["candidate_request_ids"] == []
    assert bundle["page"] == {"capture_unavailable_reason": "not_available"}
    assert bundle["foreground_layer"] == {"capture_unavailable_reason": "not_available"}
    assert bundle["errors"]["adjacent"] == []
    assert bundle["network"]["failed_requests"] == []
    assert bundle["table_assertion_snapshot"]["visible_business_row_count"] == 1
    assert bundle["table_assertion_snapshot"]["rows"] == [{"项目编码": "P001", "项目名称": "现有项目"}]
    assert bundle["table_assertion_snapshot"]["capture_scope"] == "current_rendered_page"
    assert bundle_reference in failed.observation["evidence_refs"]


def test_workflow_executor_asserts_table_row_values_by_match(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    _add_main_table_columns(template_payload, "目录编码", "支出范围说明")
    runtime = FakeRuntime(sample_runtime_elements, table_column_values={"支出范围说明": ["机关类人员经费Codex1234"]})
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table",
                "operation": "assert_row_values",
                "target": {
                    "match": {"column": "目录编码", "equals": "101001001"},
                    "fields": {"支出范围说明": "机关类人员经费Codex1234"},
                },
            },
        ]
    )

    assert report.success is True
    assert runtime.focused_rows[0]["column"] == "目录编码"
    assert report.steps[-1].data["table_scope"]["required_columns"] == ["目录编码", "支出范围说明"]


def test_workflow_executor_assert_column_values_passes_table_context(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"][3]["label"] = "授权明细"
    runtime = FakeRuntime(sample_runtime_elements, table_column_values={"金额": ["400.00"]})
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table",
                "operation": "assert_column_values",
                "target": {"table": "授权明细", "column": "金额", "equals": "400.00"},
            },
        ]
    )

    assert report.success is True
    assert runtime.table_column_collections == [
        {
            "column": "金额",
            "table": "授权明细",
            "table_fieldid": "main_table",
            "table_columns": ["项目代码", "金额"],
        }
    ]
    assert report.steps[-1].data["table"] == "授权明细"
    assert report.steps[-1].data["table_fieldid"] == "main_table"


def test_workflow_executor_assert_column_values_accepts_table_fieldid(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements, table_column_values={"金额": ["400.00"]})
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table",
                "operation": "assert_column_values",
                "target": {"table": "main_table", "column": "金额", "equals": "400.00"},
            },
        ]
    )

    assert report.success is True
    assert runtime.table_column_collections == [
        {
            "column": "金额",
            "table": '明细表',
            "table_fieldid": "main_table",
            "table_columns": ["项目代码", "金额"],
        }
    ]


def test_workflow_executor_assert_row_values_allows_runtime_table_fieldid(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"][3]["children"].extend(
        [
            {
                "key": "authorized_name_col",
                "divCode": "main_table_authorizedName",
                "nodeType": "column",
                "label": "被授权人名称",
                "name": "TableColumn",
                "dataField": "authorizedName",
            },
            {
                "key": "available_amount_col",
                "divCode": "main_table_availableAmount",
                "nodeType": "column",
                "label": "可授权金额",
                "name": "TableColumn",
                "dataField": "availableAmount",
            },
        ]
    )
    runtime = FakeRuntime(sample_runtime_elements, table_column_values={"可授权金额": ["400.00"]})
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table",
                "operation": "assert_row_values",
                "target": {
                    "table": "main_table_table",
                    "match": {"column": "被授权人名称", "equals": "人员二十二"},
                    "fields": {"可授权金额": "400.00"},
                },
            },
        ]
    )

    assert report.success is True
    assert runtime.table_row_collections == [
        {
            "match": {"column": "被授权人名称", "equals": "人员二十二"},
            "columns": ["可授权金额"],
            "table": '明细表',
            "table_fieldid": "main_table",
            "table_columns": ["项目代码", "金额", "被授权人名称", "可授权金额"],
        }
    ]


def test_workflow_executor_assert_row_values_infers_table_from_match_and_fields(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements, table_column_values={"金额": ["400.00"]})
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table",
                "operation": "assert_row_values",
                "target": {
                    "match": {"column": "项目代码", "equals": "P001"},
                    "fields": {"金额": "400.00"},
                },
            },
        ]
    )

    assert report.success is True
    assert runtime.table_row_collections == [
        {
            "match": {"column": "项目代码", "equals": "P001"},
            "columns": ["金额"],
            "table": '明细表',
            "table_fieldid": "main_table",
            "table_columns": ["项目代码", "金额"],
        }
    ]
    assert report.steps[-1].data["table_fieldid"] == "main_table"


def test_workflow_executor_rejects_ambiguous_table_value_assertion(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"].append(
        {
            "key": "detail_table",
            "divCode": "detail_table",
            "nodeType": "table",
            "label": "可用指标",
            "children": [
                {
                    "key": "detail_amount_col",
                    "divCode": "detail_amount_col",
                    "nodeType": "column",
                    "label": "金额",
                    "name": "TableColumn",
                    "dataField": "availableAmount",
                }
            ],
        }
    )
    runtime = FakeRuntime(sample_runtime_elements, table_column_values={"金额": ["400.00"]})
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table",
                "operation": "assert_column_values",
                "target": {"column": "金额", "equals": "400.00"},
            },
        ]
    )

    assert report.success is False
    assert "无法唯一确定表格作用域" in report.errors[0]
    assert "target.table" in report.errors[0]
    assert runtime.table_column_collections == []


def test_workflow_executor_rejects_duplicate_table_label_for_value_assertion(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"].append(
        {
            "key": "detail_table",
            "divCode": "detail_table",
            "nodeType": "table",
            "label": "明细表",
            "children": [
                {
                    "key": "detail_amount_col",
                    "divCode": "detail_amount_col",
                    "nodeType": "column",
                    "label": "金额",
                    "name": "TableColumn",
                    "dataField": "availableAmount",
                }
            ],
        }
    )
    runtime = FakeRuntime(sample_runtime_elements, table_column_values={"金额": ["400.00"]})
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table",
                "operation": "assert_column_values",
                "target": {"table": "明细表", "column": "金额", "equals": "400.00"},
            },
        ]
    )

    assert report.success is False
    assert "无法唯一确定表格作用域" in report.errors[0]
    assert "target=明细表" in report.errors[0]
    assert runtime.table_column_collections == []


def test_workflow_executor_asserts_table_columns_absent_by_table(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"][3]["label"] = "三级模板明细"
    runtime = FakeRuntime(
        sample_runtime_elements,
        table_headers=["序号", "* 一级绩效指标", "* 二级绩效指标", "* 三级绩效指标", "* 三级绩效指标分值"],
    )
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table",
                "operation": "assert_columns",
                "target": {
                    "table": "三级模板明细",
                    "absent": ["一级绩效指标分值", "二级绩效指标分值"],
                },
            },
        ]
    )

    assert report.success is True
    assert runtime.table_header_collections == [
        {
            "table": "三级模板明细",
            "table_fieldid": "main_table",
            "table_columns": ["项目代码", "金额"],
        }
    ]
    assert report.steps[-1].data["table"] == "三级模板明细"
    assert report.steps[-1].data["headers"] == [
        "序号",
        "* 一级绩效指标",
        "* 二级绩效指标",
        "* 三级绩效指标",
        "* 三级绩效指标分值",
    ]
    assert report.steps[-1].data["table_scope"]["required_columns"] == []


def test_workflow_executor_asserts_table_columns_present_and_absent(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(
        sample_runtime_elements,
        table_headers=["项目代码", "金额", "状态"],
    )
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table",
                "operation": "assert_columns",
                "target": {"present": ["项目代码", "金额"], "absent": ["一级绩效指标分值"]},
            },
        ]
    )

    assert report.success is True
    assert runtime.table_header_collections == [
        {"table": '明细表', "table_fieldid": "main_table", "table_columns": ["项目代码", "金额"]}
    ]
    assert report.steps[-1].data["present"] == ["项目代码", "金额"]
    assert report.steps[-1].data["absent"] == ["一级绩效指标分值"]


def test_workflow_executor_fails_table_columns_when_absent_column_exists(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements, table_headers=["一级绩效指标", "一级绩效指标分值"])
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table",
                "operation": "assert_columns",
                "target": {"absent": ["一级绩效指标分值"]},
            },
        ]
    )

    assert report.success is False
    assert "表格列不应存在" in report.errors[0]
    assert "一级绩效指标分值" in report.errors[0]
    assert "headers" in report.steps[-1].data["error"]["message"]


def test_workflow_executor_fails_table_columns_when_present_column_missing(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements, table_headers=["一级绩效指标"])
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table",
                "operation": "assert_columns",
                "target": {"present": ["二级绩效指标"]},
            },
        ]
    )

    assert report.success is False
    assert "缺少必需列" in report.errors[0]
    assert "二级绩效指标" in report.errors[0]
    assert runtime.table_header_collections == []


def test_workflow_executor_resolves_table_columns_from_unique_required_column_owner(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"].append(
        {
            "key": "detail_table",
            "divCode": "detail_table",
            "nodeType": "table",
            "label": "可用指标",
            "children": [
                {
                    "key": "subject_col",
                    "divCode": "subject_col",
                    "nodeType": "column",
                    "label": "预算编制科目",
                    "name": "TableColumn",
                    "dataField": "subjectCode",
                }
            ],
        }
    )
    runtime = FakeRuntime(sample_runtime_elements, table_headers=["项目代码"])
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "table", "operation": "assert_columns", "target": {"present": ["项目代码"]}},
        ]
    )

    assert report.success is True
    assert runtime.table_header_collections == [
        {"table": '明细表', "table_fieldid": "main_table", "table_columns": ["项目代码", "金额"]}
    ]
    assert report.steps[-1].data["table_scope"]["required_columns"] == ["项目代码"]


def test_workflow_executor_returns_warning_after_toolbar_click(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["actionEL"]["batch_replace"] = {
        "key": "batch_replace_btn",
        "divCode": "kzsz_btn",
        "nodeType": "leafItem",
        "label": "批量替换",
        "name": "Button",
        "rightflag": "batch_replace",
        "parentKeys": ["root", "toolbar_root"],
    }
    runtime = FakeRuntime(
        sample_runtime_elements,
        notifications=[
            {
                "type": "warning",
                "message": "当前选中的数据不满足操作的前提条件",
            }
        ],
    )
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "tree", "operation": "select", "target": {"label": "001 办公室"}},
            {"component": "table_row_selection", "operation": "select", "target": {"row_number": 1}},
            {"component": "toolbar", "operation": "click", "target": {"label": "批量替换"}},
        ]
    )

    assert report.success is True
    assert report.steps[-1].data["notifications"] == [
        {
            "type": "warning",
            "message": "当前选中的数据不满足操作的前提条件",
        }
    ]


def test_workflow_executor_does_not_return_with_header_button_after_save(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(
        sample_runtime_elements,
        notifications=[{"type": "success", "message": "保存成功"}],
    )

    def fail_if_called() -> bool:
        raise AssertionError("保存后不应该点击 pageHeader_return 兜底")

    runtime.close_edit_page_if_still_open = fail_if_called  # type: ignore[attr-defined]
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
        ]
    )

    assert report.success is True
    assert report.steps[-1].data["notifications"] == [{"type": "success", "message": "保存成功"}]
    assert "closed_edit_page" not in report.steps[-1].data


def test_workflow_executor_fails_toolbar_click_on_unhandled_error_notification(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(
        sample_runtime_elements,
        notifications=[
            {
                "type": "error",
                "message": "除一级项目或者人员类项目、公用经费项目外，分年度支出计划必须存在!",
            }
        ],
    )
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
            {"component": "tree", "operation": "select", "target": {"label": "001 办公室"}},
        ]
    )

    assert report.success is False
    assert len(report.steps) == 2
    assert report.steps[-1].action == "toolbar.click"
    assert report.steps[-1].success is False
    assert "toolbar.click(保存) 后出现错误提示" in report.errors[0]
    assert "分年度支出计划必须存在" in report.errors[0]
    assert "notification.assert" in report.errors[0]
    assert report.steps[-1].data["error"]["type"] == "NotificationError"


@pytest.mark.parametrize("expected_error", [False, True])
@pytest.mark.parametrize("component", ["toolbar", "action", "dialog", "tab"])
@pytest.mark.parametrize("initial_success", [False, True])
def test_workflow_executor_captures_error_during_post_click_template_binding(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
    expected_error: bool,
    component: str,
    initial_success: bool,
) -> None:
    message = "QuerySchema执行过程出错,实体URI:BGT.BGT.bgtMainBill"
    notification = {"type": "error", "message": message}
    pending: list[dict[str, str]] = []
    edit_template = deepcopy(sample_template_payload)
    edit_template["data"]["uidata"][0]["divCode"] = "editRoot"

    class LateNotificationRuntime(FakeRuntime):
        _merge_notifications = PlaywrightRuntime._merge_notifications

        def capture_runtime_elements(self, manifest) -> list[dict]:
            elements = super().capture_runtime_elements(manifest)
            if manifest.page.fieldid == "editRoot" or self.tab_clicks:
                # The real message appears and disappears while the template is rebound.
                pending.extend([notification, {"type": "info", "message": message}])
            return elements

        def _drain_buffered_notifications(self) -> list[dict[str, str]]:
            items = list(pending)
            pending.clear()
            return items

    runtime = LateNotificationRuntime(
        sample_runtime_elements,
        notifications=[{"type": "success", "message": "保存成功"}] if initial_success else [],
        dynamic_template_payloads_by_toolbar_click={"保存": edit_template, "btn_save": edit_template},
        dynamic_template_payloads_by_dialog_click={"保存": edit_template},
    )
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)
    target = {"fieldid": "btn_save"} if component == "action" else {
        "label": "项目基本信息" if component == "tab" else "保存",
    }
    next_step = (
        {"component": "notification", "operation": "assert", "target": {"type": "error", "contains": message}}
        if expected_error
        else {"component": "tab", "operation": "click", "target": {"label": "政府采购信息"}}
    )

    report = executor.run([
        {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
        {"component": component, "operation": "click", "target": target},
        next_step,
    ])

    assert report.success is expected_error
    assert report.steps[1].data["notifications"] == [*runtime.notifications, notification]
    assert runtime.tab_clicks == ([{"label": "项目基本信息", "fieldid": None}] if component == "tab" else [])
    if expected_error:
        assert report.steps[2].data["notification"] == notification
    else:
        assert len(report.steps) == 2
        assert report.steps[1].data["error"]["type"] == "NotificationError"
        assert message in report.errors[0]


def test_workflow_executor_adds_confirmed_notification_request_association(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
    tmp_path,
) -> None:
    message = (
        "权限查询异常：Illegal rpc request, src: fbdi, dest: yondif-ams, current: fbdi, "
        "service: com.yonyougov.app.auth.IDataAuthDataServerClient, "
        "method: listCurrentUserDefaultOrgRightsByCatalogs"
    )
    observation = ObservationSession(
        tmp_path / "events.jsonl",
        tool_version="test",
        run_id="run-1",
        configuration={},
    )
    runtime = FakeRuntime(sample_runtime_elements, notifications=[{"type": "error", "message": message}])
    original_click = runtime.click_toolbar_action

    def record_business_error(label: str, sub_label: str | None = None, fieldid: str | None = None, aliases: list[str] | None = None) -> None:
        original_click(label, sub_label=sub_label, fieldid=fieldid, aliases=aliases)
        _record_json_response(
            observation,
            request_key=9001,
            original_url="https://dv5-ydf.yonyougov.top/fbdi-be/rights/listCurrentUserDefaultOrgRightsByCatalogs",
            actual_url="http://127.0.0.1:62871/fbdi-be/rights/listCurrentUserDefaultOrgRightsByCatalogs",
            forwarding={
                "matched": True,
                "success": True,
                "status": 200,
                "actual_url": "http://127.0.0.1:62871/fbdi-be/rights/listCurrentUserDefaultOrgRightsByCatalogs",
                "rule": {"source": "/fbdi-be/**", "target": "http://127.0.0.1:62871"},
            },
            body={"code": 999, "message": message, "traceId": "trace-001"},
        )

    runtime.click_toolbar_action = record_business_error  # type: ignore[method-assign]
    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=runtime,
        observation_session=observation,
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
        ]
    )

    failed = report.steps[-1]
    bundle_reference = failed.data["failure_evidence_bundle"]["path"]
    bundle = json.loads((tmp_path / bundle_reference).read_text(encoding="utf-8"))
    [association] = bundle["notification_request_associations"]
    assert association["notification"] == {"type": "error", "message": message}
    assert association["status"] == "confirmed"
    assert association["evidence_basis"] == "yondif_code_999_message_exact"
    assert association["request_id"] == "request-000001"
    assert association["method"] == "POST"
    assert association["http_status"] == 200
    assert association["original_url"] == "https://dv5-ydf.yonyougov.top/fbdi-be/rights/listCurrentUserDefaultOrgRightsByCatalogs"
    assert association["actual_url"] == "http://127.0.0.1:62871/fbdi-be/rights/listCurrentUserDefaultOrgRightsByCatalogs"
    assert association["forwarding"]["matched"] is True
    assert association["forwarding"]["success"] is True
    assert association["response_body"]["path"].endswith("/response-body.json")
    assert bundle["network"]["failed_requests"] == []


def test_workflow_executor_adds_unresolved_notification_request_candidates(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
    tmp_path,
) -> None:
    message = "保存失败"
    observation = ObservationSession(
        tmp_path / "events.jsonl",
        tool_version="test",
        run_id="run-1",
        configuration={},
    )
    runtime = FakeRuntime(sample_runtime_elements, notifications=[{"type": "error", "message": message}])
    original_click = runtime.click_toolbar_action

    def record_generic_business_error(label: str, sub_label: str | None = None, fieldid: str | None = None, aliases: list[str] | None = None) -> None:
        original_click(label, sub_label=sub_label, fieldid=fieldid, aliases=aliases)
        _record_json_response(
            observation,
            request_key=9002,
            original_url="https://dv5-ydf.yonyougov.top/fbdi-be/bill/save",
            actual_url="http://127.0.0.1:62871/fbdi-be/bill/save",
            body={"success": False, "message": message},
        )

    runtime.click_toolbar_action = record_generic_business_error  # type: ignore[method-assign]
    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=runtime,
        observation_session=observation,
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
        ]
    )

    failed = report.steps[-1]
    bundle_reference = failed.data["failure_evidence_bundle"]["path"]
    bundle = json.loads((tmp_path / bundle_reference).read_text(encoding="utf-8"))
    [association] = bundle["notification_request_associations"]
    assert association["notification"] == {"type": "error", "message": message}
    assert association["status"] == "unresolved"
    assert association["reason"] == "no_confirmed_match"
    assert association["candidate_request_ids"] == ["request-000001"]
    assert "request_id" not in association
    assert "best_request_id" not in association


def test_workflow_executor_can_assert_captured_save_error_notification(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(
        sample_runtime_elements,
        notifications=[
            {
                "type": "error",
                "message": "单据检查未通过: 面板-账户名称不能为空 面板-账号不能为空",
            }
        ],
    )
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
            {
                "component": "notification",
                "operation": "assert",
                "target": {
                    "type": "error",
                    "contains": "账户名称不能为空",
                },
            },
        ]
    )

    assert report.success is True
    assert report.steps[-1].data["notification"] == {
        "type": "error",
        "message": "单据检查未通过: 面板-账户名称不能为空 面板-账号不能为空",
    }


def test_workflow_executor_closes_expected_error_notification_before_next_toolbar_click(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["actionEL"]["adjust_budget"] = {
        "key": "adjust_budget_btn",
        "divCode": "kzsz_btn",
        "nodeType": "leafItem",
        "label": "预算调整",
        "name": "Button",
        "rightflag": "adjust_budget",
        "parentKeys": ["root", "toolbar_root"],
    }
    template_payload["data"]["actionEL"]["choose_budget"] = {
        "key": "choose_budget_btn",
        "divCode": "kzsz_btn",
        "nodeType": "leafItem",
        "label": "选择项目预算",
        "name": "Button",
        "rightflag": "choose_budget",
        "parentKeys": ["root", "toolbar_root"],
    }
    runtime = FakeRuntime(
        sample_runtime_elements,
        notifications=[{"type": "error", "message": "请联系管理员"}],
    )

    def click_toolbar_action(
        label: str,
        sub_label: str | None = None,
        fieldid: str | None = None,
        aliases: list[str] | None = None,
    ) -> None:
        FakeRuntime.click_toolbar_action(runtime, label, sub_label=sub_label, fieldid=fieldid, aliases=aliases)
        if label == "选择项目预算":
            runtime.notifications = []

    runtime.click_toolbar_action = click_toolbar_action  # type: ignore[method-assign]
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "预算调整"}},
            {
                "component": "notification",
                "operation": "assert",
                "target": {"type": "error", "contains": "请联系管理员"},
            },
            {
                "component": "notification",
                "operation": "close",
                "target": {"type": "error", "contains": "请联系管理员"},
            },
            {"component": "toolbar", "operation": "click", "target": {"label": "选择项目预算"}},
        ]
    )

    assert report.success is True
    assert runtime.clicked_targets == ["预算调整", "选择项目预算"]
    assert runtime.notification_close_calls == [
        {
            "expected_type": "error",
            "contains": "请联系管理员",
            "equals": "",
            "message": "",
            "label": "",
        }
    ]
    assert report.steps[3].data["closed_notification"] == {"type": "error", "message": "请联系管理员"}
    assert report.steps[3].data["remaining_notifications"] == []


def test_workflow_executor_notification_close_keeps_remaining_notifications(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(
        sample_runtime_elements,
        notifications=[
            {"type": "error", "message": "请联系管理员"},
            {"type": "warning", "message": "请确认当前数据"},
        ],
        notification_close_result={
            "closed_notification": {"type": "error", "message": "请联系管理员"},
            "remaining_notifications": [{"type": "warning", "message": "请确认当前数据"}],
            "close_action": "confirm-button:确定",
        },
    )
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "notification",
                "operation": "close",
                "target": {"type": "error", "contains": "请联系管理员", "button": "确定"},
            },
        ]
    )

    assert report.success is True
    assert report.steps[-1].data["closed_notification"] == {"type": "error", "message": "请联系管理员"}
    assert report.steps[-1].data["remaining_notifications"] == [{"type": "warning", "message": "请确认当前数据"}]
    assert report.steps[-1].data["close_action"] == "confirm-button:确定"
    assert runtime.notification_close_calls[-1]["label"] == "确定"


def test_workflow_executor_notification_message_ignores_trailing_punctuation(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(
        sample_runtime_elements,
        notifications=[{"type": "success", "message": "保存成功"}],
    )
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
            {
                "component": "notification",
                "operation": "assert",
                "target": {"message": "保存成功！"},
            },
        ]
    )

    assert report.success is True
    assert report.steps[-1].data["notification"] == {"type": "success", "message": "保存成功"}


def test_workflow_executor_notification_assert_rechecks_when_last_notifications_do_not_match(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    collect_calls: list[int] = []

    def collect_notifications() -> list[dict[str, str]]:
        collect_calls.append(len(collect_calls) + 1)
        if len(collect_calls) <= 2:
            return [{"type": "info", "message": "正在处理，请稍候..."}]
        return [{"type": "success", "message": "提交成功"}]

    runtime.collect_notifications = collect_notifications  # type: ignore[method-assign]
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "dialog", "operation": "confirm", "target": {"label": "确定"}},
            {
                "component": "notification",
                "operation": "assert",
                "target": {"type": "success", "message_contains": "成功"},
            },
        ]
    )

    assert report.success is True
    assert report.steps[1].data["notifications"] == [{"type": "info", "message": "正在处理，请稍候..."}]
    assert report.steps[2].data["notification"] == {"type": "success", "message": "提交成功"}
    assert len(collect_calls) == 3


@pytest.mark.parametrize("ready_after_seconds", [0, 15, 59, 60, 61])
@pytest.mark.parametrize("intermediate_notification", [False, True])
def test_workflow_executor_notification_assert_waits_up_to_one_minute(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
    monkeypatch: pytest.MonkeyPatch,
    ready_after_seconds: int,
    intermediate_notification: bool,
) -> None:
    clock = FakeClock()

    def sleep(seconds: float) -> None:
        clock.now += seconds

    monkeypatch.setattr(executor_module.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(executor_module.time, "sleep", sleep)
    runtime = FakeRuntime(sample_runtime_elements)
    notification = {"type": "success", "message": "保存并签章成功"}

    def collect_notifications() -> list[dict[str, str]]:
        if clock.now >= ready_after_seconds:
            return [notification]
        if intermediate_notification:
            return [{"type": "info", "message": "正在处理，请稍候..."}]
        return []

    runtime.collect_notifications = collect_notifications  # type: ignore[method-assign]
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)
    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
            {
                "component": "notification",
                "operation": "assert",
                "target": {"type": "success", "contains": "保存并签章成功"},
            },
        ]
    )

    assert report.success is (ready_after_seconds <= 60)
    assert clock.now == min(ready_after_seconds, 60)
    if report.success:
        assert report.steps[-1].data["notification"] == notification
    else:
        assert "未找到匹配页面提示" in report.errors[0]


def test_workflow_executor_captures_transient_toolbar_notification_during_save_wait(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    runtime._notification_capture_armed = False  # type: ignore[attr-defined]
    runtime._captured_notifications = []  # type: ignore[attr-defined]

    original_click_toolbar_action = runtime.click_toolbar_action

    def begin_notification_capture() -> None:
        runtime._notification_capture_armed = True  # type: ignore[attr-defined]
        runtime._captured_notifications = []  # type: ignore[attr-defined]

    def click_toolbar_action(
        label: str,
        sub_label: str | None = None,
        fieldid: str | None = None,
        aliases: list[str] | None = None,
    ) -> None:
        original_click_toolbar_action(label, sub_label=sub_label, fieldid=fieldid, aliases=aliases)
        if label == "保存" and runtime._notification_capture_armed:  # type: ignore[attr-defined]
            runtime.notifications = [{"type": "success", "message": "保存成功！"}]
            runtime._captured_notifications = list(runtime.notifications)  # type: ignore[attr-defined]

    def wait_after_action() -> None:
        runtime.notifications = []

    def collect_notifications() -> list[dict[str, str]]:
        return list(runtime._captured_notifications or runtime.notifications)  # type: ignore[attr-defined]

    runtime.begin_notification_capture = begin_notification_capture  # type: ignore[attr-defined]
    runtime.click_toolbar_action = click_toolbar_action  # type: ignore[method-assign]
    runtime.wait_after_action = wait_after_action  # type: ignore[attr-defined]
    runtime.collect_notifications = collect_notifications  # type: ignore[method-assign]
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
            {
                "component": "notification",
                "operation": "assert",
                "target": {"contains": "保存成功"},
            },
        ]
    )

    assert report.success is True
    assert report.steps[-1].data["notification"] == {"type": "success", "message": "保存成功！"}


def test_workflow_executor_captures_notification_from_fieldid_action_click(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    runtime._notification_capture_armed = False  # type: ignore[attr-defined]
    runtime._captured_notifications = []  # type: ignore[attr-defined]

    original_click_action_by_fieldid = runtime.click_action_by_fieldid

    def begin_notification_capture() -> None:
        runtime._notification_capture_armed = True  # type: ignore[attr-defined]
        runtime._captured_notifications = []  # type: ignore[attr-defined]

    def click_action_by_fieldid(fieldid: str) -> None:
        original_click_action_by_fieldid(fieldid)
        if fieldid == "btn-save" and runtime._notification_capture_armed:  # type: ignore[attr-defined]
            runtime._captured_notifications = [{"type": "success", "message": "保存成功！"}]  # type: ignore[attr-defined]

    def collect_notifications() -> list[dict[str, str]]:
        return list(runtime._captured_notifications)  # type: ignore[attr-defined]

    runtime.begin_notification_capture = begin_notification_capture  # type: ignore[attr-defined]
    runtime.click_action_by_fieldid = click_action_by_fieldid  # type: ignore[method-assign]
    runtime.collect_notifications = collect_notifications  # type: ignore[method-assign]
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "action", "operation": "click", "target": {"fieldid": "btn-save"}},
            {
                "component": "notification",
                "operation": "assert",
                "target": {"contains": "保存成功"},
            },
        ]
    )

    assert report.success is True
    assert runtime.clicked_fieldids == ["btn-save"]
    assert report.steps[-1].data["notification"] == {"type": "success", "message": "保存成功！"}


def test_workflow_executor_does_not_restore_previous_template_after_save_error(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    list_template = deepcopy(sample_template_payload)
    list_template["data"]["actionEL"]["create"] = {
        "key": "create_btn",
        "divCode": "xz_btn",
        "nodeType": "leafItem",
        "label": "新增",
        "name": "Button",
        "rightflag": "create",
        "parentKeys": ["root", "toolbar_root"],
    }

    edit_template = deepcopy(sample_template_payload)
    edit_template["data"]["uidata"][0]["key"] = "editRoot"
    edit_template["data"]["uidata"][0]["divCode"] = "editRoot"
    edit_template["data"]["actionEL"] = {
        "save": {
            "key": "save_btn",
            "divCode": "btn_save",
            "nodeType": "leafItem",
            "label": "保存",
            "name": "Button",
            "rightflag": "save",
            "parentKeys": ["editRoot"],
        },
        "cancel": {
            "key": "cancel_btn",
            "divCode": "btn_cancel",
            "nodeType": "leafItem",
            "label": "取消",
            "name": "Button",
            "rightflag": "cancel",
            "parentKeys": ["editRoot"],
        },
    }

    runtime = FakeRuntime(
        sample_runtime_elements,
        runtime_elements_by_page={
            "root": [
                *sample_runtime_elements,
                {
                    "fieldid": "xz_btn",
                    "id": None,
                    "name": None,
                    "placeholder": None,
                    "text": "新增",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="xz_btn"]',
                },
            ],
            "editRoot": [
                {
                    "fieldid": "btn_save",
                    "id": None,
                    "name": None,
                    "placeholder": None,
                    "text": "保存",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="btn_save"]',
                },
                {
                    "fieldid": "btn_cancel",
                    "id": None,
                    "name": None,
                    "placeholder": None,
                    "text": "取消",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="btn_cancel"]',
                },
            ],
        },
        dynamic_template_payloads_by_toolbar_click={"新增": edit_template},
    )
    original_click_toolbar_action = runtime.click_toolbar_action

    def click_toolbar_action(
        label: str,
        sub_label: str | None = None,
        fieldid: str | None = None,
        aliases=None,
    ) -> None:
        original_click_toolbar_action(label, sub_label=sub_label, fieldid=fieldid, aliases=aliases)
        if label == "保存":
            runtime.notifications = [{"type": "error", "message": "单据检查未通过: 面板-账户名称不能为空"}]
        else:
            runtime.notifications = []

    runtime.click_toolbar_action = click_toolbar_action  # type: ignore[method-assign]
    executor = WorkflowExecutor(gateway=FakeGateway(list_template), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "新增"}},
            {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
            {
                "component": "notification",
                "operation": "assert",
                "target": {"type": "error", "contains": "账户名称不能为空"},
            },
            {"component": "toolbar", "operation": "click", "target": {"label": "取消"}},
        ]
    )

    assert report.success is True
    assert runtime.clicked_targets == ["新增", "保存", "取消"]
    assert "restored_template" not in report.steps[2].data


def test_workflow_executor_does_not_restore_previous_template_when_save_leaves_cancel_visible(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    list_template = deepcopy(sample_template_payload)
    list_template["data"]["actionEL"] = {
        "reduce": {
            "key": "reduce_btn",
            "divCode": "reduce_btn",
            "nodeType": "leafItem",
            "label": "追减",
            "name": "Button",
            "rightflag": "reduce",
            "parentKeys": ["root", "toolbar_root"],
        },
        **{
            f"list_action_{index}": {
                "key": f"list_action_{index}",
                "divCode": f"list_action_{index}",
                "nodeType": "leafItem",
                "label": f"列表动作{index}",
                "name": "Button",
                "rightflag": f"listAction{index}",
                "parentKeys": ["root", "toolbar_root"],
            }
            for index in range(5)
        },
    }

    edit_template = deepcopy(sample_template_payload)
    edit_template["data"]["uidata"][0]["key"] = "editRoot"
    edit_template["data"]["uidata"][0]["divCode"] = "root"
    edit_template["data"]["actionEL"] = {
        "save": {
            "key": "save_btn",
            "divCode": "save_btn",
            "nodeType": "leafItem",
            "label": "保存",
            "name": "Button",
            "rightflag": "save",
            "parentKeys": ["editRoot"],
        },
        "cancel": {
            "key": "cancel_btn",
            "divCode": "cancel_btn",
            "nodeType": "leafItem",
            "label": "取消",
            "name": "Button",
            "rightflag": "cancel",
            "parentKeys": ["editRoot"],
        },
    }

    runtime_elements = [
        *sample_runtime_elements,
        {
            "fieldid": "reduce_btn",
            "id": None,
            "name": None,
            "placeholder": None,
            "text": "追减",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="reduce_btn"]',
        },
        *[
            {
                "fieldid": f"list_action_{index}",
                "id": None,
                "name": None,
                "placeholder": None,
                "text": f"列表动作{index}",
                "role": "button",
                "tag_name": "button",
                "visible": True,
                "selector": f'[fieldid="list_action_{index}"]',
            }
            for index in range(5)
        ],
        {
            "fieldid": "save_btn",
            "id": None,
            "name": None,
            "placeholder": None,
            "text": "保存",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="save_btn"]',
        },
        {
            "fieldid": "cancel_btn",
            "id": None,
            "name": None,
            "placeholder": None,
            "text": "取消",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="cancel_btn"]',
        },
    ]
    runtime = FakeRuntime(
        runtime_elements,
        dynamic_template_payloads_by_toolbar_click={"追减": edit_template},
        notifications=[{"type": "success", "message": "保存成功"}],
    )
    executor = WorkflowExecutor(gateway=FakeGateway(list_template), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "追减"}},
            {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
            {
                "component": "notification",
                "operation": "assert",
                "target": {"type": "success", "message_contains": "保存成功"},
            },
            {"component": "toolbar", "operation": "click", "target": {"label": "取消"}},
        ]
    )

    assert report.success is True
    assert "restored_template" not in report.steps[2].data
    assert runtime.clicked_targets == ["追减", "保存", "取消"]


def test_workflow_executor_restores_after_save_when_only_stale_child_cancel_remains(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    list_template = deepcopy(sample_template_payload)
    list_template["data"]["actionEL"]["add_external"] = {
        "key": "add_external_btn",
        "divCode": "add_external_btn",
        "nodeType": "leafItem",
        "label": "添加外部成员",
        "name": "Button",
        "rightflag": "addExternal",
        "parentKeys": ["root", "toolbar_root"],
    }

    child_template = deepcopy(sample_template_payload)
    child_template["data"]["uidata"][0]["key"] = "childRoot"
    child_template["data"]["uidata"][0]["divCode"] = "childRoot"
    child_template["data"]["uidata"][0]["children"] = [
        {
            "key": "child_card",
            "divCode": "childCard",
            "nodeType": "card",
            "label": "外部成员",
            "children": [
                {
                    "key": "external_name",
                    "divCode": "external_name",
                    "nodeType": "formItem",
                    "label": "人员名称",
                    "name": "TextInput",
                    "dataField": "externalName",
                }
            ],
        }
    ]
    child_template["data"]["actionEL"] = {
        "save": {
            "key": "child_save",
            "divCode": "child_save",
            "nodeType": "leafItem",
            "label": "保存",
            "name": "Button",
            "rightflag": "save",
            "parentKeys": ["childRoot"],
        },
        "cancel": {
            "key": "child_cancel",
            "divCode": "child_cancel",
            "nodeType": "leafItem",
            "label": "取消",
            "name": "Button",
            "rightflag": "cancel",
            "parentKeys": ["childRoot"],
        },
    }

    runtime = FakeRuntime(
        sample_runtime_elements,
        runtime_elements_by_page={
            "root": [
                *sample_runtime_elements,
                {
                    "fieldid": "add_external_btn",
                    "id": None,
                    "text": "添加外部成员",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="add_external_btn"]',
                },
                {
                    "fieldid": "child_cancel",
                    "id": None,
                    "text": "取消",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="child_cancel"]',
                },
            ],
            "childRoot": [
                {
                    "fieldid": "child_save",
                    "id": None,
                    "text": "保存",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="child_save"]',
                },
                {
                    "fieldid": "child_cancel",
                    "id": None,
                    "text": "取消",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="child_cancel"]',
                },
                {
                    "fieldid": "external_name",
                    "id": "external_name_input",
                    "text": "人员名称",
                    "role": "textbox",
                    "tag_name": "input",
                    "visible": True,
                    "selector": '[fieldid="external_name"] input',
                },
            ],
        },
        dynamic_template_payloads_by_toolbar_click={"添加外部成员": child_template},
    )
    executor = WorkflowExecutor(gateway=FakeGateway(list_template), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "添加外部成员"}},
            {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
            {
                "component": "table_row_selection",
                "operation": "select",
                "target": {"match": {"column": "项目代码", "equals": "XM001"}},
            },
        ]
    )

    assert report.success is True
    assert report.steps[2].data["restored_template"]["page"] == "root"
    assert report.steps[2].data["auto_restored_template"] is True
    assert runtime.selected_rows == [
        {
            "table": "明细表",
            "column": "项目代码",
            "equals": "XM001",
            "table_fieldid": "main_table",
            "table_columns": ["项目代码", "金额"],
        }
    ]


def test_workflow_executor_restores_previous_table_template_before_table_selection(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    list_template = deepcopy(sample_template_payload)
    list_template["data"]["actionEL"]["add_external"] = {
        "key": "add_external_btn",
        "divCode": "add_external_btn",
        "nodeType": "leafItem",
        "label": "添加外部成员",
        "name": "Button",
        "rightflag": "addExternal",
        "parentKeys": ["root", "toolbar_root"],
    }

    child_template = deepcopy(sample_template_payload)
    child_template["data"]["uidata"][0]["key"] = "childRoot"
    child_template["data"]["uidata"][0]["divCode"] = "childRoot"
    child_template["data"]["uidata"][0]["children"] = [
        {
            "key": "child_card",
            "divCode": "childCard",
            "nodeType": "card",
            "label": "外部成员",
            "children": [],
        }
    ]
    child_template["data"]["actionEL"] = {
        "save": {
            "key": "child_save",
            "divCode": "child_save",
            "nodeType": "leafItem",
            "label": "保存",
            "name": "Button",
            "rightflag": "save",
            "parentKeys": ["childRoot"],
        },
        "cancel": {
            "key": "child_cancel",
            "divCode": "child_cancel",
            "nodeType": "leafItem",
            "label": "取消",
            "name": "Button",
            "rightflag": "cancel",
            "parentKeys": ["childRoot"],
        },
    }

    child_actions = [
        {
            "fieldid": "child_save",
            "id": None,
            "text": "保存",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="child_save"]',
        },
        {
            "fieldid": "child_cancel",
            "id": None,
            "text": "取消",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="child_cancel"]',
        },
    ]
    runtime = FakeRuntime(
        sample_runtime_elements,
        runtime_elements_by_page={
            "root": [
                *sample_runtime_elements,
                {
                    "fieldid": "add_external_btn",
                    "id": None,
                    "text": "添加外部成员",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="add_external_btn"]',
                },
                *child_actions,
            ],
            "childRoot": child_actions,
        },
        dynamic_template_payloads_by_toolbar_click={"添加外部成员": child_template},
    )
    executor = WorkflowExecutor(gateway=FakeGateway(list_template), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "添加外部成员"}},
            {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
            {
                "component": "table_row_selection",
                "operation": "select",
                "target": {"match": {"column": "项目代码", "equals": "XM001"}},
            },
        ]
    )

    assert report.success is True
    assert "restored_template" not in report.steps[2].data
    assert runtime.selected_rows == [
        {
            "table": "明细表",
            "column": "项目代码",
            "equals": "XM001",
            "table_fieldid": "main_table",
            "table_columns": ["项目代码", "金额"],
        }
    ]


def test_workflow_executor_restores_previous_template_after_cancel_returns_to_list(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    list_template = deepcopy(sample_template_payload)
    list_template["data"]["actionEL"] = {
        "reduce": {
            "key": "reduce_btn",
            "divCode": "reduce_btn",
            "nodeType": "leafItem",
            "label": "追减",
            "name": "Button",
            "rightflag": "reduce",
            "parentKeys": ["root", "toolbar_root"],
        },
        "submit": {
            "key": "submit_btn",
            "divCode": "submit_btn",
            "nodeType": "leafItem",
            "label": "提交",
            "name": "Button",
            "rightflag": "submit",
            "parentKeys": ["root", "toolbar_root"],
        },
    }

    edit_template = deepcopy(sample_template_payload)
    edit_template["data"]["uidata"][0]["key"] = "editRoot"
    edit_template["data"]["uidata"][0]["divCode"] = "root"
    edit_template["data"]["uidata"][0]["children"] = [
        {
            "key": "edit_toolbar",
            "divCode": "edit_toolbar",
            "nodeType": "toolbar",
            "label": "底部工具栏",
            "parentKey": "root",
            "children": [
                {
                    "key": "cancel_btn",
                    "divCode": "cancel_btn",
                    "nodeType": "leafItem",
                    "label": "取消",
                    "name": "Button",
                    "rightflag": "cancel",
                }
            ],
        }
    ]
    edit_template["data"]["actionEL"] = {
        "cancel": {
            "key": "cancel_btn",
            "divCode": "cancel_btn",
            "nodeType": "leafItem",
            "label": "取消",
            "name": "Button",
            "rightflag": "cancel",
            "parentKeys": ["editRoot"],
        },
    }

    list_runtime_elements = [
        *sample_runtime_elements,
        {
            "fieldid": "reduce_btn",
            "id": None,
            "name": None,
            "placeholder": None,
            "text": "追减",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="reduce_btn"]',
        },
        {
            "fieldid": "submit_btn",
            "id": None,
            "name": None,
            "placeholder": None,
            "text": "提交",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="submit_btn"]',
        },
    ]
    edit_runtime_elements = [
        *sample_runtime_elements,
        {
            "fieldid": "cancel_btn",
            "id": None,
            "name": None,
            "placeholder": None,
            "text": "取消",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="cancel_btn"]',
        },
    ]
    runtime = FakeRuntime(
        edit_runtime_elements,
        dynamic_template_payloads_by_toolbar_click={"追减": edit_template},
    )

    original_click_toolbar_action = runtime.click_toolbar_action

    def click_toolbar_action(
        label: str,
        sub_label: str | None = None,
        fieldid: str | None = None,
        aliases: list[str] | None = None,
    ) -> None:
        original_click_toolbar_action(label, sub_label=sub_label, fieldid=fieldid, aliases=aliases)
        if label == "取消":
            runtime.runtime_elements = list_runtime_elements

    runtime.click_toolbar_action = click_toolbar_action  # type: ignore[method-assign]
    executor = WorkflowExecutor(gateway=FakeGateway(list_template), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "追减"}},
            {"component": "toolbar", "operation": "click", "target": {"label": "取消"}},
            {"component": "toolbar", "operation": "click", "target": {"label": "提交"}},
        ]
    )

    assert report.success is True
    assert report.steps[2].data["auto_restored_template"] is True
    assert runtime.clicked_targets == ["追减", "取消", "提交"]
    assert runtime.toolbar_click_details[-1]["fieldid"] == "btn_submit"


def test_workflow_executor_restores_previous_template_after_successful_save_returns_to_list(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    list_template = deepcopy(sample_template_payload)
    list_template["data"]["uidata"][0]["children"].append(
        {
            "key": "query_box",
            "divCode": "queryBox",
            "nodeType": "form",
            "label": "查询区",
            "children": [
                {
                    "key": "query_name",
                    "divCode": "query_name",
                    "nodeType": "formItem",
                    "label": "项目名称",
                    "name": "TextInput",
                    "dataField": "projectName",
                }
            ],
        }
    )
    list_template["data"]["actionEL"]["create"] = {
        "key": "create_btn",
        "divCode": "xz_btn",
        "nodeType": "leafItem",
        "label": "新增",
        "name": "Button",
        "rightflag": "create",
        "parentKeys": ["root", "toolbar_root"],
    }
    list_template["data"]["actionEL"]["query"] = {
        "key": "query_btn",
        "divCode": "query_btn",
        "nodeType": "leafItem",
        "label": "查询",
        "name": "Button",
        "rightflag": "query",
        "parentKeys": ["root", "queryBox"],
    }

    edit_template = deepcopy(sample_template_payload)
    edit_template["data"]["uidata"][0]["key"] = "editRoot"
    edit_template["data"]["uidata"][0]["divCode"] = "editRoot"
    edit_template["data"]["uidata"][0]["children"] = [
        {
            "key": "edit_card",
            "divCode": "editCard",
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
                }
            ],
        }
    ]
    edit_template["data"]["actionEL"] = {
        "save": {
            "key": "save_btn",
            "divCode": "btn_save",
            "nodeType": "leafItem",
            "label": "保存",
            "name": "Button",
            "rightflag": "save",
            "parentKeys": ["editRoot"],
        }
    }

    runtime = FakeRuntime(
        sample_runtime_elements,
        runtime_elements_by_page={
            "root": [
                *sample_runtime_elements,
                {
                    "fieldid": "xz_btn",
                    "id": None,
                    "name": None,
                    "placeholder": None,
                    "text": "新增",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="xz_btn"]',
                },
                {
                    "fieldid": "queryBox_projectName",
                    "id": None,
                    "name": "projectName",
                    "placeholder": "项目名称",
                    "text": "",
                    "role": "textbox",
                    "tag_name": "input",
                    "visible": True,
                    "selector": '[fieldid="queryBox_projectName"] input',
                },
                {
                    "fieldid": "query_btn",
                    "id": None,
                    "name": None,
                    "placeholder": None,
                    "text": "查询",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="query_btn"]',
                },
            ],
            "editRoot": [
                {
                    "fieldid": "btn_save",
                    "id": None,
                    "name": None,
                    "placeholder": None,
                    "text": "保存",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="btn_save"]',
                },
                {
                    "fieldid": "project_name",
                    "id": "project_name_input",
                    "text": "项目名称",
                    "role": "textbox",
                    "tag_name": "input",
                    "visible": True,
                    "selector": '[fieldid="project_name"] input',
                },
            ],
        },
        dynamic_template_payloads_by_toolbar_click={"新增": edit_template},
        notifications=[{"type": "success", "message": "保存成功"}],
    )
    executor = WorkflowExecutor(gateway=FakeGateway(list_template), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "新增"}},
            {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
            {
                "component": "query",
                "operation": "search",
                "target": {"conditions": [{"field": "项目名称", "equals": "Codex"}]},
            },
        ]
    )

    assert report.success is True
    assert report.steps[2].data["restored_template"]["page"] == "root"
    assert runtime.clicked_targets == ["新增", "保存", "查询"]


def test_workflow_executor_restores_previous_template_after_save_returns_to_list_without_toast(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    list_template = deepcopy(sample_template_payload)
    list_template["data"]["actionEL"]["create"] = {
        "key": "create_btn",
        "divCode": "xz_btn",
        "nodeType": "leafItem",
        "label": "新增",
        "name": "Button",
        "rightflag": "create",
        "parentKeys": ["root", "toolbar_root"],
    }

    edit_template = deepcopy(sample_template_payload)
    edit_template["data"]["uidata"][0]["key"] = "editRoot"
    edit_template["data"]["uidata"][0]["divCode"] = "editRoot"
    edit_template["data"]["uidata"][0]["children"] = [
        {
            "key": "edit_card",
            "divCode": "editCard",
            "nodeType": "card",
            "label": "基本信息",
            "children": [
                {
                    "key": "edit_name",
                    "divCode": "edit_name",
                    "nodeType": "formItem",
                    "label": "编辑页字段",
                    "name": "TextInput",
                    "dataField": "editName",
                }
            ],
        }
    ]
    edit_template["data"]["actionEL"] = {
        "save": {
            "key": "save_btn",
            "divCode": "btn_save",
            "nodeType": "leafItem",
            "label": "保存",
            "name": "Button",
            "rightflag": "save",
            "parentKeys": ["editRoot"],
        }
    }

    runtime = FakeRuntime(
        sample_runtime_elements,
        runtime_elements_by_page={
            "root": [
                *sample_runtime_elements,
                {
                    "fieldid": "xz_btn",
                    "id": None,
                    "name": None,
                    "placeholder": None,
                    "text": "新增",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="xz_btn"]',
                },
            ],
            "editRoot": [
                {
                    "fieldid": "btn_save",
                    "id": None,
                    "name": None,
                    "placeholder": None,
                    "text": "保存",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="btn_save"]',
                },
                {
                    "fieldid": "edit_name",
                    "id": "edit_name_input",
                    "text": "编辑页字段",
                    "role": "textbox",
                    "tag_name": "input",
                    "visible": True,
                    "selector": '[fieldid="edit_name"] input',
                },
            ],
        },
        dynamic_template_payloads_by_toolbar_click={"新增": edit_template},
        notifications=[],
    )
    executor = WorkflowExecutor(gateway=FakeGateway(list_template), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "新增"}},
            {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
        ]
    )

    assert report.success is True
    assert report.steps[2].data["restored_template"]["page"] == "root"
    assert report.steps[2].data["auto_restored_template"] is True


def test_workflow_executor_restores_parent_table_after_toolbar_confirm_closes_dynamic_form(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    list_template = deepcopy(sample_template_payload)
    list_template["data"]["actionEL"]["generate"] = {
        "key": "generate_btn",
        "divCode": "generate_btn",
        "nodeType": "leafItem",
        "label": "生成对账单",
        "name": "Button",
        "rightflag": "generate",
        "parentKeys": ["root", "toolbar_root"],
    }

    form_template = deepcopy(sample_template_payload)
    form_template["data"]["uidata"][0]["key"] = "reconForm"
    form_template["data"]["uidata"][0]["divCode"] = "reconForm"
    form_template["data"]["uidata"][0]["children"] = [
        {
            "key": "recon_card",
            "divCode": "recon_card",
            "nodeType": "card",
            "label": "生成对账单",
            "children": [
                {
                    "key": "begin_date",
                    "divCode": "begin_date",
                    "nodeType": "formItem",
                    "label": "开始时间",
                    "name": "YDFDatePicker",
                    "dataField": "beginDate",
                }
            ],
        },
        {
            "key": "recon_toolbar",
            "divCode": "recon_toolbar",
            "nodeType": "toolbar",
            "label": "按钮工具栏",
            "parentKey": "root",
            "children": [
                {
                    "key": "confirm_btn",
                    "divCode": "confirm_btn",
                    "nodeType": "leafItem",
                    "label": "确定",
                    "name": "Button",
                    "rightflag": "confirm",
                },
                {
                    "key": "cancel_btn",
                    "divCode": "cancel_btn",
                    "nodeType": "leafItem",
                    "label": "取消",
                    "name": "Button",
                    "rightflag": "cancel",
                },
            ],
        },
    ]
    form_template["data"]["actionEL"] = {}

    list_runtime_elements = [
        *sample_runtime_elements,
        {
            "fieldid": "generate_btn",
            "id": None,
            "name": None,
            "placeholder": None,
            "text": "生成对账单",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="generate_btn"]',
        },
    ]
    form_runtime_elements = [
        {
            "fieldid": "begin_date",
            "id": "begin_date_input",
            "text": "开始时间",
            "role": "textbox",
            "tag_name": "input",
            "visible": True,
            "selector": '[fieldid="begin_date"] input',
        },
        {
            "fieldid": "confirm_btn",
            "id": None,
            "name": None,
            "placeholder": None,
            "text": "确定",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="confirm_btn"]',
        },
        {
            "fieldid": "cancel_btn",
            "id": None,
            "name": None,
            "placeholder": None,
            "text": "取消",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="cancel_btn"]',
        },
    ]
    runtime = FakeRuntime(
        list_runtime_elements,
        runtime_elements_by_page={
            "root": list_runtime_elements,
            "reconForm": form_runtime_elements,
        },
        dynamic_template_payloads_by_toolbar_click={"生成对账单": form_template},
        notifications=[{"type": "success", "message": "生成成功"}],
    )
    original_click_toolbar_action = runtime.click_toolbar_action

    def click_toolbar_action(
        label: str,
        sub_label: str | None = None,
        fieldid: str | None = None,
        aliases: list[str] | None = None,
    ) -> None:
        original_click_toolbar_action(label, sub_label=sub_label, fieldid=fieldid, aliases=aliases)
        if label == "确定":
            runtime.runtime_elements_by_page["reconForm"] = list_runtime_elements

    runtime.click_toolbar_action = click_toolbar_action  # type: ignore[method-assign]
    executor = WorkflowExecutor(gateway=FakeGateway(list_template), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "生成对账单"}},
            {"component": "toolbar", "operation": "click", "target": {"label": "确定"}},
            {"component": "table_row_selection", "operation": "select", "target": {"row_numbers": 1}},
        ]
    )

    assert report.success is True
    assert report.steps[2].data["restored_template"]["page"] == "root"
    assert report.steps[2].data["auto_restored_template"] is True
    assert [item["row_number"] for item in runtime.selected_row_numbers] == [1]


def test_workflow_executor_restores_parent_template_after_dialog_save_closes_dynamic_dialog(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    list_template = deepcopy(sample_template_payload)
    list_template["data"]["actionEL"] = {
        "claim": {
            "key": "claim_btn",
            "divCode": "claim_btn",
            "nodeType": "leafItem",
            "label": "项目认领",
            "name": "Button",
            "rightflag": "claim",
            "parentKeys": ["root", "toolbar_root"],
        },
        "submit": {
            "key": "submit_btn",
            "divCode": "btn_submit",
            "nodeType": "leafItem",
            "label": "提交",
            "name": "Button",
            "rightflag": "submit",
            "parentKeys": ["root", "toolbar_root"],
        },
    }

    claim_template = deepcopy(sample_template_payload)
    claim_template["data"]["uidata"][0]["key"] = "claimForm"
    claim_template["data"]["uidata"][0]["divCode"] = "claimForm"
    claim_template["data"]["uidata"][0]["children"] = [
        {
            "key": "claim_toolbar",
            "divCode": "claim_toolbar",
            "nodeType": "toolbar",
            "label": "按钮工具栏",
            "children": [
                {
                    "key": "claim_save_btn",
                    "divCode": "claim_save_btn",
                    "nodeType": "leafItem",
                    "label": "保存",
                    "name": "Button",
                    "rightflag": "save",
                },
                {
                    "key": "invoice_btn",
                    "divCode": "invoice_btn",
                    "nodeType": "leafItem",
                    "label": "开具发票",
                    "name": "Button",
                    "rightflag": "invoice",
                },
            ],
        }
    ]
    claim_template["data"]["actionEL"] = {}

    invoice_template = deepcopy(sample_template_payload)
    invoice_template["data"]["uidata"][0]["key"] = "invoiceDialog"
    invoice_template["data"]["uidata"][0]["divCode"] = "invoiceDialog"
    invoice_template["data"]["uidata"][0]["children"] = [
        {
            "key": "invoice_toolbar",
            "divCode": "invoice_toolbar",
            "nodeType": "toolbar",
            "label": "按钮工具栏",
            "children": [
                {
                    "key": "invoice_save_btn",
                    "divCode": "invoice_save_btn",
                    "nodeType": "leafItem",
                    "label": "保存",
                    "name": "Button",
                    "rightflag": "save",
                }
            ],
        }
    ]
    invoice_template["data"]["actionEL"] = {}

    list_runtime_elements = [
        *sample_runtime_elements,
        {
            "fieldid": "claim_btn",
            "id": None,
            "name": None,
            "placeholder": None,
            "text": "项目认领",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="claim_btn"]',
        },
    ]
    claim_runtime_elements = [
        {
            "fieldid": "claim_save_btn",
            "id": None,
            "name": None,
            "placeholder": None,
            "text": "保存",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="claim_save_btn"]',
        },
        {
            "fieldid": "invoice_btn",
            "id": None,
            "name": None,
            "placeholder": None,
            "text": "开具发票",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="invoice_btn"]',
        },
    ]
    invoice_runtime_elements = [
        {
            "fieldid": "invoice_save_btn",
            "id": None,
            "name": None,
            "placeholder": None,
            "text": "保存",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="invoice_save_btn"]',
        }
    ]
    runtime = FakeRuntime(
        list_runtime_elements,
        runtime_elements_by_page={
            "root": list_runtime_elements,
            "claimForm": claim_runtime_elements,
            "invoiceDialog": invoice_runtime_elements,
        },
        dynamic_template_payloads_by_toolbar_click={
            "项目认领": claim_template,
            "开具发票": invoice_template,
        },
        notifications=[{"type": "success", "message": "保存成功"}],
    )
    original_click_toolbar_action = runtime.click_toolbar_action
    original_click_dialog_button = runtime.click_dialog_button

    def click_toolbar_action(
        label: str,
        sub_label: str | None = None,
        fieldid: str | None = None,
        aliases: list[str] | None = None,
    ) -> None:
        original_click_toolbar_action(label, sub_label=sub_label, fieldid=fieldid, aliases=aliases)
        if label == "保存" and fieldid == "claim_save_btn":
            runtime.runtime_elements_by_page["claimForm"] = list_runtime_elements

    def click_dialog_button(label: str, expect_download: bool = False) -> None:
        original_click_dialog_button(label, expect_download=expect_download)
        if label == "保存":
            runtime.runtime_elements_by_page["invoiceDialog"] = claim_runtime_elements

    runtime.click_toolbar_action = click_toolbar_action  # type: ignore[method-assign]
    runtime.click_dialog_button = click_dialog_button  # type: ignore[method-assign]
    executor = WorkflowExecutor(gateway=FakeGateway(list_template), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "项目认领"}},
            {"component": "toolbar", "operation": "click", "target": {"label": "开具发票"}},
            {"component": "dialog", "operation": "click", "target": {"label": "保存"}},
            {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
            {"component": "toolbar", "operation": "click", "target": {"label": "提交"}},
        ]
    )

    assert report.success is True
    assert report.steps[3].data["restored_template"]["page"] == "claimForm"
    assert report.steps[3].data["auto_restored_template"] is True
    assert report.steps[4].data["restored_template"]["page"] == "root"
    assert runtime.toolbar_click_details[-1]["fieldid"] == "btn_submit"


def test_workflow_executor_reuses_seen_form_template_when_row_action_switches_dom_without_payload(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    list_template = deepcopy(sample_template_payload)
    list_template["data"]["actionEL"]["create"] = {
        "key": "create_btn",
        "divCode": "xz_btn",
        "nodeType": "leafItem",
        "label": "新增",
        "name": "Button",
        "rightflag": "create",
        "parentKeys": ["root", "toolbar_root"],
    }
    list_template["data"]["actionEL"]["add_child"] = {
        "key": "add_child_btn",
        "divCode": "btnAdd",
        "nodeType": "leafItem",
        "label": "新增下级",
        "name": "Button",
        "rightflag": "create",
        "parentKeys": ["root", "main_table"],
    }

    edit_template = deepcopy(sample_template_payload)
    edit_template["data"]["uidata"][0]["key"] = "editRoot"
    edit_template["data"]["uidata"][0]["divCode"] = "editRoot"
    edit_template["data"]["uidata"][0]["children"] = [
        {
            "key": "edit_card",
            "divCode": "editCard",
            "nodeType": "card",
            "label": "基本信息",
            "children": [
                {
                    "key": "category_name",
                    "divCode": "categoryName",
                    "nodeType": "formItem",
                    "label": "分类名称",
                    "name": "TextInput",
                    "dataField": "draftTemplateName",
                }
            ],
        }
    ]
    edit_template["data"]["actionEL"] = {
        "save": {
            "key": "save_btn",
            "divCode": "btn_save",
            "nodeType": "leafItem",
            "label": "保存",
            "name": "Button",
            "rightflag": "save",
            "parentKeys": ["editRoot"],
        }
    }

    runtime = FakeRuntime(
        sample_runtime_elements,
        runtime_elements_by_page={
            "root": [
                *sample_runtime_elements,
                {
                    "fieldid": "xz_btn",
                    "id": None,
                    "name": None,
                    "placeholder": None,
                    "text": "新增",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="xz_btn"]',
                },
            ],
            "editRoot": [
                {
                    "fieldid": "btn_save",
                    "id": None,
                    "name": None,
                    "placeholder": None,
                    "text": "保存",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="btn_save"]',
                },
                {
                    "fieldid": "categoryName",
                    "id": None,
                    "name": "draftTemplateName",
                    "placeholder": "分类名称",
                    "text": "",
                    "role": "textbox",
                    "tag_name": "input",
                    "visible": True,
                    "selector": '[fieldid="categoryName"] input',
                },
            ],
        },
        dynamic_template_payloads_by_toolbar_click={"新增": edit_template},
        notifications=[{"type": "success", "message": "保存成功"}],
    )
    runtime.resolve_visible_page_identity = lambda fieldids: "editRoot"  # type: ignore[method-assign]
    executor = WorkflowExecutor(gateway=FakeGateway(list_template), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "新增"}},
            {"component": "form", "operation": "fill", "target": {"fields": {"分类名称": "父分类"}}},
            {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
            {
                "component": "table_row_action",
                "operation": "click",
                "target": {"action": "新增下级", "match": {"column": "项目代码", "equals": "父分类"}},
            },
            {"component": "form", "operation": "fill", "target": {"fields": {"分类名称": "子分类"}}},
        ]
    )

    assert report.success is True
    assert report.steps[4].data["dom_switched_template"]["page"] == "editRoot"
    assert runtime.filled_fields[-1] == {"fieldid": "categoryName", "value": "子分类"}


def test_workflow_executor_uploads_import_file_with_default_success_assertion(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "import",
                "operation": "upload",
                "target": {"file": "/tmp/payee.xlsx"},
            },
        ]
    )

    assert report.success is True
    assert runtime.import_uploads == [{"label": "导入", "files": ["/tmp/payee.xlsx"]}]
    assert report.steps[-1].data["import_results"] == [
        {"file": "/tmp/payee.xlsx", "status": "success", "message": "导入完成"}
    ]


def test_workflow_executor_can_assert_import_failure_reason(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(
        sample_runtime_elements,
        next_import_upload_result={
            "import_results": [
                {"file": "/tmp/bad.xlsx", "status": "failure", "message": "账号不能为空"}
            ]
        },
    )
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "import",
                "operation": "upload",
                "target": {
                    "file": "/tmp/bad.xlsx",
                    "assert": {"status": "failure", "error_contains": "账号不能为空"},
                },
            },
        ]
    )

    assert report.success is True
    assert report.steps[-1].data["import_results"][0]["message"] == "账号不能为空"


def test_workflow_executor_preserves_direct_import_results_with_assertion(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(
        sample_runtime_elements,
        next_import_upload_result={
            "import_results": [
                {"file": "/tmp/direct.xlsx", "status": "success", "message": "直连导入完成"}
            ],
            "entry": "direct_file",
        },
    )
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "import",
                "operation": "upload",
                "target": {
                    "label": "导入",
                    "file": "/tmp/direct.xlsx",
                    "assert": {"status": "success"},
                },
            },
        ]
    )

    assert report.success is True
    assert runtime.import_uploads == [{"label": "导入", "files": ["/tmp/direct.xlsx"]}]
    assert report.steps[-1].data["import_results"] == [
        {"file": "/tmp/direct.xlsx", "status": "success", "message": "直连导入完成"}
    ]
    assert report.steps[-1].data["entry"] == "direct_file"


def test_workflow_executor_passes_direct_import_expectation_and_fieldid(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    class RuntimeWithImportExpectation(FakeRuntime):
        def import_upload(
            self,
            label: str,
            files: list[str],
            *,
            fieldid: str | None = None,
            expected_status: str = "success",
            action_candidates: list[dict[str, Any]] | None = None,
        ) -> dict[str, Any]:
            self.import_uploads.append(
                {
                    "label": label,
                    "files": files,
                    "fieldid": fieldid,
                    "expected_status": expected_status,
                    "action_candidates": action_candidates or [],
                }
            )
            return {
                "entry": "direct_file",
                "import_results": [
                    {"file": files[0], "status": "submitted", "message": "后端已接收导入文件"}
                ],
            }

    runtime = RuntimeWithImportExpectation(sample_runtime_elements)
    runtime.field_values["project_name"] = "回填完成"
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
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
            {
                "component": "form",
                "operation": "assert_values",
                "target": {"fields": {"项目名称": "回填完成"}},
            },
        ]
    )

    assert report.success is True
    assert runtime.import_uploads[-1]["fieldid"] == "custom_import"
    assert runtime.import_uploads[-1]["expected_status"] == "submitted"


def test_workflow_executor_accepts_success_for_submitted_expectation(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(
        sample_runtime_elements,
        next_import_upload_result={
            "import_results": [
                {"file": "/tmp/direct.xlsx", "status": "success", "message": "导入成功"}
            ]
        },
    )
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "import",
                "operation": "upload",
                "target": {
                    "file": "/tmp/direct.xlsx",
                    "assert": {"status": "submitted"},
                },
            },
            {
                "component": "table",
                "operation": "assert_empty",
                "target": {"column": "错误信息"},
            },
        ]
    )

    assert report.success is True


def test_workflow_executor_rejects_failure_for_submitted_expectation(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(
        sample_runtime_elements,
        next_import_upload_result={
            "import_results": [
                {"file": "/tmp/direct.xlsx", "status": "failure", "message": "文件格式错误"}
            ]
        },
    )
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "import",
                "operation": "upload",
                "target": {
                    "file": "/tmp/direct.xlsx",
                    "assert": {"status": "submitted"},
                },
            },
            {
                "component": "table",
                "operation": "assert_empty",
                "target": {"column": "错误信息"},
            },
        ]
    )

    assert report.success is False
    assert "导入结果状态不匹配" in report.errors[0]


def test_workflow_executor_passes_import_action_candidates_when_supported(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    sample_template_payload["data"]["uidata"][0]["children"][0]["children"].append(
        {
            "key": "direct_import",
            "divCode": "direct_import",
            "nodeType": "leafItem",
            "label": "导入",
            "name": "YDFileImportButton",
            "props": {"fieldid": "direct_import", "justFile": "single"},
        }
    )

    class RuntimeWithImportCandidates(FakeRuntime):
        def import_upload(
            self,
            label: str,
            files: list[str],
            action_candidates: list[dict[str, Any]] | None = None,
        ) -> dict[str, Any]:
            self.import_uploads.append(
                {"label": label, "files": files, "action_candidates": action_candidates or []}
            )
            return {
                "import_results": [
                    {"file": files[0], "status": "success", "message": "导入完成"}
                ]
            }

    runtime = RuntimeWithImportCandidates(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "import",
                "operation": "upload",
                "target": {"label": "导入", "file": "/tmp/direct.xlsx"},
            },
        ]
    )

    assert report.success is True
    candidates = runtime.import_uploads[-1]["action_candidates"]
    assert any(item["component_name"] == "YDFileImportButton" for item in candidates)


def test_workflow_executor_fails_when_import_status_does_not_match_assertion(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(
        sample_runtime_elements,
        next_import_upload_result={
            "import_results": [
                {"file": "/tmp/bad.xlsx", "status": "failure", "message": "账号不能为空"}
            ]
        },
    )
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "import", "operation": "upload", "target": {"file": "/tmp/bad.xlsx"}},
        ]
    )

    assert report.success is False
    assert "导入结果状态不匹配" in report.errors[0]


def test_workflow_executor_downloads_import_template(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "import",
                "operation": "download_template",
                "target": {"template": "收款人账户管理导入模板"},
            },
        ]
    )

    assert report.success is True
    assert runtime.import_template_downloads == [{"label": "导入", "template": "收款人账户管理导入模板"}]
    assert report.steps[-1].data["downloaded_files"] == ["/Users/ken/Downloads/template.xlsx"]


def test_workflow_executor_sets_amount_unit_with_public_component_candidate(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    toolbar_children = sample_template_payload["data"]["uidata"][0]["children"][0]["children"]
    toolbar_children.append(
        {
            "key": "amount_unit",
            "divCode": "amount_unit_btn",
            "nodeType": "leafItem",
            "label": "设置金额单位",
            "name": "LCDSetAmtunit",
        }
    )
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "amount_unit",
                "operation": "set",
                "target": {"value": "万元"},
            },
        ]
    )

    assert report.success is True
    assert runtime.amount_unit_sets[-1]["value"] == "万元"
    assert any(
        item["component_name"] == "LCDSetAmtunit"
        for item in runtime.amount_unit_sets[-1]["action_candidates"]
    )
    assert report.steps[-1].action == "amount_unit.set"
    assert report.steps[-1].data["actual_value"] == "万元"


def test_workflow_executor_rebinds_dynamic_template_after_create_and_return(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    list_template = deepcopy(sample_template_payload)
    list_template["data"]["uidata"][0]["children"].insert(
        1,
        {
            "key": "query_box",
            "divCode": "queryBox",
            "nodeType": "card",
            "label": "查询区",
            "children": [
                {
                    "key": "query_button",
                    "divCode": "query_btn",
                    "nodeType": "leafItem",
                    "label": "查询",
                    "name": "Button",
                    "rightflag": "query",
                }
            ],
        },
    )
    list_template["data"]["actionEL"]["create"] = {
        "key": "create_btn",
        "divCode": "xz_btn",
        "nodeType": "leafItem",
        "label": "新增",
        "name": "Button",
        "rightflag": "create",
        "parentKeys": ["root", "toolbar_root"],
    }
    edit_template = deepcopy(sample_template_payload)
    edit_template["data"]["uidata"][0]["divCode"] = "editRoot"
    edit_template["data"]["uidata"][0]["children"] = [
        {
            "key": "page_header",
            "divCode": "pageHeader",
            "nodeType": "toolbar",
            "label": "页面头部",
            "parentKey": "editRoot",
            "children": [
                {
                    "key": "page_header_return",
                    "divCode": "pageHeader_return",
                    "nodeType": "leafItem",
                    "label": "返回",
                    "name": "Button",
                    "rightflag": "return",
                }
            ],
        }
    ]
    edit_template["data"]["actionEL"] = {
        "return": {
            "key": "page_header_return",
            "divCode": "pageHeader_return",
            "nodeType": "leafItem",
            "label": "返回",
            "name": "Button",
            "rightflag": "return",
            "parentKeys": ["editRoot", "pageHeader"],
        }
    }
    runtime = FakeRuntime(
        sample_runtime_elements,
        runtime_elements_by_page={
            "root": [
                *sample_runtime_elements,
                {
                    "fieldid": "xz_btn",
                    "id": None,
                    "name": None,
                    "placeholder": None,
                    "text": "新增",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="xz_btn"]',
                },
                {
                    "fieldid": "query_btn",
                    "id": None,
                    "name": None,
                    "placeholder": None,
                    "text": "查询",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="query_btn"]',
                },
            ],
            "editRoot": [
                {
                    "fieldid": "pageHeader_return",
                    "id": None,
                    "name": None,
                    "placeholder": None,
                    "text": "返回",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="pageHeader_return"]',
                }
            ],
        },
        dynamic_template_payloads_by_toolbar_click={"新增": edit_template},
    )
    executor = WorkflowExecutor(gateway=FakeGateway(list_template), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "新增"}},
            {"component": "action", "operation": "click", "target": {"fieldid": "pageHeader_return"}},
            {"component": "query", "operation": "search", "target": {"conditions": []}},
            {"component": "table_row_action", "operation": "click", "target": {"action": "详情", "row_number": 1}},
        ]
    )

    assert report.success is True
    assert runtime.clicked_targets == ["新增", "查询", "详情"]
    assert runtime.clicked_fieldids == ["pageHeader_return"]
    assert runtime.focused_rows[0]["row_number"] == 1
    assert runtime.expanded_query_count == 0
    assert runtime.prepared_manifest_keys == ["root", "editRoot", "root"]
    assert report.steps[1].data["dynamic_template"] == {"page": "editRoot", "bound_action_count": 1}
    assert report.steps[2].data["restored_template"] == {"page": "root", "bound_action_count": 3}


def test_workflow_executor_fills_form_saves_queries_and_asserts_detail_values(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    list_template = deepcopy(sample_template_payload)
    _add_main_table_columns(list_template, "项目负责人", "项目名称")
    list_template["data"]["uidata"][0]["children"].insert(
        1,
        {
            "key": "query_box",
            "divCode": "queryBox",
            "nodeType": "card",
            "label": "查询区",
            "children": [
                {
                    "key": "query_manager",
                    "divCode": "query_proManager",
                    "nodeType": "formItem",
                    "label": "项目负责人",
                    "name": "TextInput",
                    "dataField": "proManager",
                },
                {
                    "key": "query_button",
                    "divCode": "query_btn",
                    "nodeType": "leafItem",
                    "label": "查询",
                    "name": "Button",
                    "rightflag": "query",
                },
            ],
        },
    )
    list_template["data"]["actionEL"]["create"] = {
        "key": "create_btn",
        "divCode": "xz_btn",
        "nodeType": "leafItem",
        "label": "新增",
        "name": "Button",
        "rightflag": "create",
        "parentKeys": ["root", "toolbar_root"],
    }
    edit_template = deepcopy(sample_template_payload)
    edit_template["data"]["uidata"][0]["divCode"] = "editRoot"
    edit_template["data"]["uidata"][0]["children"] = [
        {
            "key": "edit_toolbar",
            "divCode": "editToolbar",
            "nodeType": "toolbar",
            "label": "按钮工具栏",
            "parentKey": "editRoot",
            "children": [
                {
                    "key": "save_btn",
                    "divCode": "btn_save",
                    "nodeType": "leafItem",
                    "label": "保存",
                    "name": "Button",
                    "rightflag": "save",
                }
            ],
        },
        {
            "key": "edit_card",
            "divCode": "editCard",
            "nodeType": "card",
            "label": "基本信息",
            "children": [
                {
                    "key": "project_name",
                    "divCode": "projectName",
                    "nodeType": "formItem",
                    "label": "项目名称",
                    "name": "TextInput",
                    "dataField": "projectName",
                },
                {
                    "key": "project_manager",
                    "divCode": "proManager",
                    "nodeType": "formItem",
                    "label": "项目负责人",
                    "name": "YDFRefer",
                    "dataField": "proManager",
                },
                {
                    "key": "start_time",
                    "divCode": "proStartTime",
                    "nodeType": "formItem",
                    "label": "项目起始时间",
                    "name": "YDFDatePicker",
                    "dataField": "proStartTime",
                },
                {
                    "key": "budget_template",
                    "divCode": "bgtTemplateCode",
                    "nodeType": "formItem",
                    "label": "预算模板",
                    "name": "YDFTreeSelect",
                    "dataField": "bgtTemplateCode",
                },
                {
                    "key": "total_amount",
                    "divCode": "proAmount",
                    "nodeType": "formItem",
                    "label": "项目总额",
                    "name": "YDFInputNumber",
                    "dataField": "proAmount",
                },
            ],
        },
    ]
    edit_template["data"]["actionEL"] = {
        "save": {
            "key": "save_btn",
            "divCode": "btn_save",
            "nodeType": "leafItem",
            "label": "保存",
            "name": "Button",
            "rightflag": "save",
            "parentKeys": ["editRoot", "editToolbar"],
        }
    }
    runtime_elements_by_page = {
        "root": [
            *sample_runtime_elements,
            {
                "fieldid": "xz_btn",
                "id": None,
                "name": None,
                "placeholder": None,
                "text": "新增",
                "role": "button",
                "tag_name": "button",
                "visible": True,
                "selector": '[fieldid="xz_btn"]',
            },
            {
                "fieldid": "query_proManager",
                "id": None,
                "name": "proManager",
                "placeholder": "项目负责人",
                "text": "",
                "role": "textbox",
                "tag_name": "input",
                "visible": True,
                "selector": '[fieldid="query_proManager"] input',
            },
            {
                "fieldid": "query_btn",
                "id": None,
                "name": None,
                "placeholder": None,
                "text": "查询",
                "role": "button",
                "tag_name": "button",
                "visible": True,
                "selector": '[fieldid="query_btn"]',
            },
        ],
        "editRoot": [
            {
                "fieldid": "btn_save",
                "id": None,
                "name": None,
                "placeholder": None,
                "text": "保存",
                "role": "button",
                "tag_name": "button",
                "visible": True,
                "selector": '[fieldid="btn_save"]',
            },
            {
                "fieldid": "projectName",
                "id": None,
                "name": "projectName",
                "placeholder": "项目名称",
                "text": "",
                "role": "textbox",
                "tag_name": "input",
                "visible": True,
                "selector": '[fieldid="projectName"] input',
            },
            {
                "fieldid": "proManager",
                "id": None,
                "name": "proManager",
                "placeholder": "项目负责人",
                "text": "",
                "role": "combobox",
                "tag_name": "input",
                "visible": True,
                "selector": '[fieldid="proManager"] input',
            },
            {
                "fieldid": "proStartTime",
                "id": None,
                "name": "proStartTime",
                "placeholder": "项目起始时间",
                "text": "",
                "role": "textbox",
                "tag_name": "input",
                "visible": True,
                "selector": '[fieldid="proStartTime"] input',
            },
            {
                "fieldid": "bgtTemplateCode",
                "id": None,
                "name": "bgtTemplateCode",
                "placeholder": "预算模板",
                "text": "",
                "role": "combobox",
                "tag_name": "input",
                "visible": True,
                "selector": '[fieldid="bgtTemplateCode"] input',
            },
            {
                "fieldid": "proAmount",
                "id": None,
                "name": "proAmount",
                "placeholder": "项目总额",
                "text": "",
                "role": "spinbutton",
                "tag_name": "input",
                "visible": True,
                "selector": '[fieldid="proAmount"] input',
            },
        ],
    }
    runtime = FakeRuntime(
        sample_runtime_elements,
        runtime_elements_by_page=runtime_elements_by_page,
        dynamic_template_payloads_by_toolbar_click={"新增": edit_template},
        dynamic_template_payloads_by_row_action={"详情": edit_template},
        table_column_values={"项目负责人": ["吕晓雷"]},
    )
    executor = WorkflowExecutor(gateway=FakeGateway(list_template), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "新增"}},
            {
                "component": "form",
                "operation": "fill",
                "target": {
                    "fields": {
                        "项目名称": "puqh测试项目1",
                        "项目负责人": "吕晓雷",
                        "项目开始时间": "2026-05-01",
                        "预算模版": "0320 0320预算模板",
                        "项目总额": "300000",
                    }
                },
            },
            {
                "component": "toolbar",
                "operation": "click",
                "target": {"label": "保存", "restore_previous": True},
            },
            {
                "component": "query",
                "operation": "search",
                "target": {"conditions": [{"field": "项目负责人", "equals": "吕晓雷"}]},
            },
            {
                "component": "table",
                "operation": "assert_column_values",
                "target": {"column": "项目负责人", "equals": "吕晓雷"},
            },
            {
                "component": "table_row_action",
                "operation": "click",
                "target": {"action": "详情", "match": {"column": "项目名称", "equals": "puqh测试项目1"}},
            },
            {
                "component": "form",
                "operation": "assert_values",
                "target": {
                    "fields": {
                        "项目名称": "puqh测试项目1",
                        "项目负责人": "吕晓雷",
                        "项目总额": "300000",
                    }
                },
            },
        ]
    )

    assert report.success is True
    assert runtime.filled_fields[:3] == [
        {"fieldid": "projectName", "value": "puqh测试项目1"},
        {"fieldid": "proManager", "value": "吕晓雷"},
        {"fieldid": "proStartTime", "value": "2026-05-01"},
    ]
    assert runtime.clicked_targets == ["新增", "保存", "查询", "详情"]
    assert runtime.prepared_manifest_keys == ["root", "editRoot", "root", "editRoot"]
    assert report.steps[3].data["restored_template"] == {"page": "root", "bound_action_count": 3}


def test_workflow_executor_asserts_detail_field_by_property_uri_when_labels_differ(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    list_template = deepcopy(sample_template_payload)
    _add_main_table_columns(list_template, "项目名称")
    list_template["data"]["uidata"][0]["enty"] = {"info": {"uri": "PM.PM.pmProjectInfo"}}
    list_template["data"]["actionEL"]["create"] = {
        "key": "create_btn",
        "divCode": "xz_btn",
        "nodeType": "leafItem",
        "label": "新增",
        "name": "Button",
        "rightflag": "create",
        "parentKeys": ["root", "toolbar_root"],
    }

    edit_template = deepcopy(sample_template_payload)
    edit_template["data"]["uidata"][0] = {
        "key": "editRoot",
        "divCode": "editRoot",
        "nodeType": "root",
        "bizObjCode": "pmProjectInfo",
        "enty": {"info": {"uri": "PM.PM.pmProjectInfo"}},
        "children": [
            {
                "key": "edit_form",
                "divCode": "pmProjectInfo",
                "nodeType": "form",
                "label": "基本信息",
                "name": "LCDPanel",
                "children": [
                    {
                        "key": "edit_catalog",
                        "divCode": "proCatalogCode",
                        "nodeType": "formItem",
                        "label": "执行项目分类",
                        "name": "YDFTreeSelect",
                        "dataField": "proCatalogCode",
                    }
                ],
            }
        ],
    }
    edit_template["data"]["actionEL"] = {
        "save": {
            "key": "save_btn",
            "divCode": "btn_save",
            "nodeType": "leafItem",
            "label": "保存",
            "name": "Button",
            "rightflag": "save",
            "parentKeys": ["editRoot"],
        }
    }

    detail_template = deepcopy(edit_template)
    detail_template["data"]["uidata"][0]["divCode"] = "detailRoot"
    detail_template["data"]["uidata"][0]["key"] = "detailRoot"
    detail_template["data"]["uidata"][0]["children"][0]["children"][0].update(
        {
            "key": "detail_catalog",
            "divCode": "detailProCatalogCode",
            "label": "项目分类",
            "dataField": "proCatalogCode",
        }
    )
    detail_template["data"]["actionEL"] = {}

    runtime = FakeRuntime(
        sample_runtime_elements,
        runtime_elements_by_page={
            "root": [
                *sample_runtime_elements,
                {
                    "fieldid": "xz_btn",
                    "id": None,
                    "name": None,
                    "placeholder": None,
                    "text": "新增",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="xz_btn"]',
                },
            ],
            "editRoot": [
                {
                    "fieldid": "pmProjectInfo_proCatalogCode",
                    "id": None,
                    "name": "proCatalogCode",
                    "placeholder": "执行项目分类",
                    "text": "",
                    "role": "combobox",
                    "tag_name": "input",
                    "visible": True,
                    "selector": '[fieldid="pmProjectInfo_proCatalogCode"] input',
                },
                {
                    "fieldid": "btn_save",
                    "id": None,
                    "name": None,
                    "placeholder": None,
                    "text": "保存",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="btn_save"]',
                },
            ],
            "detailRoot": [
                {
                    "fieldid": "pmProjectInfo_proCatalogCode",
                    "id": None,
                    "name": None,
                    "placeholder": None,
                    "text": "909 11133+2026",
                    "role": None,
                    "tag_name": "div",
                    "visible": True,
                    "selector": '[fieldid="pmProjectInfo_proCatalogCode"]',
                }
            ],
        },
        dynamic_template_payloads_by_toolbar_click={"新增": edit_template},
        dynamic_template_payloads_by_row_action={"详情": detail_template},
        field_values={"pmProjectInfo_proCatalogCode": "909 11133+2026"},
    )
    executor = WorkflowExecutor(gateway=FakeGateway(list_template), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "新增"}},
            {
                "component": "form",
                "operation": "fill",
                "target": {"fields": {"执行项目分类": "909 11133+2026"}},
            },
            {
                "component": "toolbar",
                "operation": "click",
                "target": {"label": "保存", "restore_previous": True},
            },
            {
                "component": "table_row_action",
                "operation": "click",
                "target": {"action": "详情", "match": {"column": "项目名称", "equals": "puqh测试项目1"}},
            },
            {
                "component": "form",
                "operation": "assert_values",
                "target": {"fields": {"执行项目分类": "909 11133+2026"}},
            },
        ]
    )

    assert report.success is True
    assert report.steps[-1].data["fields"][0]["fieldid"] == "pmProjectInfo_proCatalogCode"
    assert report.steps[-1].data["fields"][0]["property_uri"] == "PM.PM.pmProjectInfo.proCatalogCode"


def test_workflow_executor_preserves_structured_reference_target_for_form_fill(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template = deepcopy(sample_template_payload)
    template["data"]["uidata"][0]["children"].append(
        {
            "key": "asset_field",
            "divCode": "assetCode",
            "nodeType": "formItem",
            "label": "资产分类",
            "name": "YDFRef",
            "dataField": "assetCode",
        }
    )
    runtime_elements = [
        *sample_runtime_elements,
        {
            "fieldid": "assetCode",
            "id": None,
            "name": "assetCode",
            "placeholder": "资产分类",
            "text": "",
            "role": "textbox",
            "tag_name": "input",
            "visible": True,
            "selector": '[fieldid="assetCode"] input',
        },
    ]
    runtime = FakeRuntime(runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(template), runtime=runtime)
    reference_target = {
        "filter": "房屋",
        "match": {"column": "代码集名称", "equals": "房屋"},
    }

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "form", "operation": "fill", "target": {"fields": {"资产分类": reference_target}}},
        ]
    )

    assert report.success is True
    assert runtime.raw_filled_fields[-1] == {"fieldid": "assetCode", "value": reference_target}


def test_workflow_executor_reports_popup_reference_tree_context_for_form_fill(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    class PopupResultRuntime(FakeRuntime):
        def fill_form_field(self, bound_element, value: str) -> dict[str, object]:
            super().fill_form_field(bound_element, value)
            return {
                "popup_tab_context": [{"label": "本单位人员账户"}],
                "popup_tree_context": [{"label": "101 综合司01"}],
                "selected": [
                    {
                        "tab": "本单位人员账户",
                        "tree": {"label": "101 综合司01"},
                        "match": {"column": "人员名称", "equals": "人员二十一"},
                    }
                ],
                "confirmed": True,
                "confirm_label": "保存",
            }

    template = deepcopy(sample_template_payload)
    template["data"]["uidata"][0]["children"].append(
        {
            "key": "manager_field",
            "divCode": "proManager",
            "nodeType": "formItem",
            "label": "项目负责人",
            "name": "YDFReferSelect",
            "dataField": "proManager",
        }
    )
    runtime_elements = [
        *sample_runtime_elements,
        {
            "fieldid": "proManager",
            "id": None,
            "name": "proManager",
            "placeholder": "项目负责人",
            "text": "",
            "role": "textbox",
            "tag_name": "input",
            "visible": True,
            "selector": '[fieldid="proManager"] input',
        },
    ]
    runtime = PopupResultRuntime(runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(template), runtime=runtime)
    reference_target = {
        "tree": {"label": "101 综合司01"},
        "match": {"column": "人员名称", "equals": "人员二十一"},
        "confirm_label": "保存",
    }

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "form", "operation": "fill", "target": {"fields": {"项目负责人": reference_target}}},
        ]
    )

    field_result = report.steps[-1].data["fields"][0]
    assert field_result["popup_tab_context"] == [{"label": "本单位人员账户"}]
    assert field_result["popup_tree_context"] == [{"label": "101 综合司01"}]
    assert field_result["selected"][0]["match"] == {"column": "人员名称", "equals": "人员二十一"}
    assert field_result["confirm_label"] == "保存"


def test_workflow_executor_fails_form_popup_reference_without_completion_evidence(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    class UnconfirmedPopupRuntime(FakeRuntime):
        def fill_form_field(self, bound_element, value: str) -> dict[str, object]:
            super().fill_form_field(bound_element, value)
            return {
                "selected": [value],
                "confirmed": False,
                "close_action": "target",
                "root_backfilled": False,
                "dialog_hidden": False,
            }

    template = deepcopy(sample_template_payload)
    template["data"]["uidata"][0]["children"].append(
        {
            "key": "manager_field",
            "divCode": "proManager",
            "nodeType": "formItem",
            "label": "项目负责人",
            "name": "YDFReferSelect",
            "dataField": "proManager",
        }
    )
    runtime_elements = [
        *sample_runtime_elements,
        {
            "fieldid": "proManager",
            "id": None,
            "name": "proManager",
            "placeholder": "项目负责人",
            "text": "",
            "role": "textbox",
            "tag_name": "input",
            "visible": True,
            "selector": '[fieldid="proManager"] input',
        },
    ]
    runtime = UnconfirmedPopupRuntime(runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(template), runtime=runtime)
    reference_target = {
        "filter": {"conditions": [{"field": "人员名称", "equals": "人员十一"}]},
        "match": {"column": "人员名称", "equals": "人员十一"},
    }

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "form", "operation": "fill", "target": {"fields": {"项目负责人": reference_target}}},
        ]
    )

    assert report.success is False
    assert "表单字段[项目负责人]录入失败" in report.errors[0]
    assert "弹出参照未确认完成" in report.errors[0]
    assert "close_action=target" in report.errors[0]


def test_workflow_executor_accepts_form_popup_reference_when_dialog_closes(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    class ClosedPopupRuntime(FakeRuntime):
        def fill_form_field(self, bound_element, value: str) -> dict[str, object]:
            super().fill_form_field(bound_element, value)
            return {
                "selected": [value],
                "confirmed": False,
                "close_action": "target",
                "root_backfilled": False,
                "dialog_hidden": True,
            }

    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=ClosedPopupRuntime(sample_runtime_elements),
    )

    report = executor.run([
        {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
        {"component": "form", "operation": "fill", "target": {"fields": {"项目名称": "已关闭"}}},
    ])

    assert report.success is True


def test_workflow_executor_restores_parent_after_form_fill_applies_closed_popup_template(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    list_template = deepcopy(sample_template_payload)
    list_template["data"]["actionEL"]["create"] = {
        "key": "create_btn",
        "divCode": "xz_btn",
        "nodeType": "leafItem",
        "label": "新增",
        "name": "Button",
        "rightflag": "create",
        "parentKeys": ["root", "toolbar_root"],
    }

    edit_template = deepcopy(sample_template_payload)
    edit_root = edit_template["data"]["uidata"][0]
    edit_root["key"] = edit_root["divCode"] = "editRoot"
    edit_root["children"][1]["children"][0]["label"] = "采购供应商"
    edit_root["children"][3]["label"] = "合同付款计划"
    shared_cancel = {
        "key": "cancel_btn",
        "divCode": "qx_btn",
        "nodeType": "leafItem",
        "label": "取消",
        "name": "Button",
        "rightflag": "cancel",
        "parentKeys": ["editRoot", "toolbar_root"],
    }
    edit_template["data"]["actionEL"]["cancel"] = shared_cancel

    reference_template = deepcopy(sample_template_payload)
    reference_root = reference_template["data"]["uidata"][0]
    reference_root["key"] = reference_root["divCode"] = "supplierRoot"
    reference_table = deepcopy(reference_root["children"][3])
    reference_table["label"] = "表格"
    reference_root["children"] = [reference_table]
    reference_template["data"]["actionEL"] = {"cancel": shared_cancel}

    list_elements = [
        *sample_runtime_elements,
        {
            "fieldid": "xz_btn",
            "text": "新增",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="xz_btn"]',
        },
    ]
    edit_elements = [
        {**sample_runtime_elements[0], "text": "采购供应商"},
        sample_runtime_elements[2],
        sample_runtime_elements[4],
        {
            "fieldid": "qx_btn",
            "text": "取消",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="qx_btn"]',
        },
    ]

    class ClosedSupplierPopupRuntime(FakeRuntime):
        def fill_form_field(self, bound_element, value: str) -> dict[str, object]:
            super().fill_form_field(bound_element, value)
            self.next_dynamic_template_payload = reference_template
            return {
                "selected": [value],
                "confirmed": True,
                "dialog_hidden": True,
            }

    runtime = ClosedSupplierPopupRuntime(
        list_elements,
        runtime_elements_by_page={"root": list_elements, "editRoot": edit_elements, "supplierRoot": edit_elements},
        dynamic_template_payloads_by_toolbar_click={"新增": edit_template},
    )
    executor = WorkflowExecutor(gateway=FakeGateway(list_template), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "新增"}},
            {
                "component": "form",
                "operation": "fill",
                "target": {"fields": {"采购供应商": {"first_available": True}}},
            },
            {
                "component": "editable_table",
                "operation": "add_row",
                "target": {"label": "新增", "table": "合同付款计划"},
            },
        ]
    )

    assert report.success is True
    assert report.steps[2].data["auto_restored_template"] is True
    assert report.steps[2].data["restored_template"]["page"] == "editRoot"
    assert runtime.editable_table_adds[-1]["table"] == "合同付款计划"


def test_workflow_executor_keeps_form_fill_template_without_post_fill_dynamic_payload(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    list_template = deepcopy(sample_template_payload)
    list_root = list_template["data"]["uidata"][0]
    list_root["children"] = [list_root["children"][1], list_root["children"][3]]
    list_root["children"][0]["children"][0]["label"] = "采购供应商"
    list_root["children"][1]["label"] = "付款合同列表"
    list_template["data"]["actionEL"] = {}

    edit_template = deepcopy(list_template)
    edit_root = edit_template["data"]["uidata"][0]
    edit_root["key"] = edit_root["divCode"] = "editRoot"
    edit_root["children"][1]["label"] = "合同付款计划"

    runtime_elements = [
        {**sample_runtime_elements[0], "text": "采购供应商"},
        sample_runtime_elements[4],
    ]

    class PendingEditTemplateRuntime(FakeRuntime):
        def open_menu(self, menu_target: MenuTarget) -> None:
            super().open_menu(menu_target)
            self.next_dynamic_template_payload = edit_template

        def fill_form_field(self, bound_element, value: str) -> dict[str, object]:
            super().fill_form_field(bound_element, value)
            return {
                "selected": [value],
                "confirmed": True,
                "dialog_hidden": True,
            }

    runtime = PendingEditTemplateRuntime(runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(list_template), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "form",
                "operation": "fill",
                "target": {"fields": {"采购供应商": {"first_available": True}}},
            },
            {
                "component": "editable_table",
                "operation": "add_row",
                "target": {"label": "新增", "table": "合同付款计划"},
            },
        ]
    )

    assert report.success is True
    assert report.steps[1].data["popup_reference_restore"]["reason"] == "unsupported_template_context"
    assert "auto_restored_template" not in report.steps[1].data
    assert runtime.editable_table_adds[-1]["table"] == "合同付款计划"


def test_workflow_executor_restores_list_template_after_nested_popup_reference_form_fill(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    class PopupReferenceReturnsToListRuntime(FakeRuntime):
        def fill_form_field(self, bound_element, value: str) -> dict[str, object]:
            super().fill_form_field(bound_element, value)
            self.runtime_elements_by_page["managerRoot"] = list(self.runtime_elements_by_page["root"])
            return {
                "selected": [
                    {
                        "filter": {"conditions": [{"field": "人员名称", "equals": "人员二十一"}]},
                        "match": {"column": "人员名称", "equals": "人员二十一"},
                    }
                ],
                "confirmed": True,
                "confirm_label": "保存",
            }

    list_template = deepcopy(sample_template_payload)
    list_template["data"]["uidata"][0]["children"].append(
        {
            "key": "query_box",
            "divCode": "queryBox",
            "nodeType": "form",
            "label": "查询区",
            "children": [
                {
                    "key": "query_name",
                    "divCode": "query_name",
                    "nodeType": "formItem",
                    "label": "项目名称",
                    "name": "TextInput",
                    "dataField": "projectName",
                }
            ],
        }
    )
    list_template["data"]["actionEL"]["setManager"] = {
        "key": "set_manager_btn",
        "divCode": "set_manager_btn",
        "nodeType": "leafItem",
        "label": "设置经费管理员",
        "name": "Button",
        "rightflag": "set-manager",
        "parentKeys": ["root", "toolbar_root"],
    }
    list_template["data"]["actionEL"]["query"] = {
        "key": "query_btn",
        "divCode": "query_btn",
        "nodeType": "leafItem",
        "label": "查询",
        "name": "Button",
        "rightflag": "query",
        "parentKeys": ["root", "queryBox"],
    }

    manager_template = deepcopy(sample_template_payload)
    manager_template["data"]["uidata"][0]["key"] = "managerRoot"
    manager_template["data"]["uidata"][0]["divCode"] = "managerRoot"
    manager_template["data"]["uidata"][0]["children"] = [
        {
            "key": "managerCard",
            "divCode": "managerCard",
            "nodeType": "card",
            "label": "设置经费管理员",
            "children": [
                {
                    "key": "bgtManager",
                    "divCode": "bgtManager",
                    "nodeType": "formItem",
                    "label": "经费管理员",
                    "name": "YDFReferSelect",
                    "dataField": "bgtManager",
                }
            ],
        },
        {
            "key": "managerToolbar",
            "divCode": "managerToolbar",
            "nodeType": "toolbar",
            "label": "底部工具栏",
            "name": "LCDBtnToolbar",
            "children": [],
        },
    ]
    manager_template["data"]["actionEL"] = {
        "confirm": {
            "key": "confirm",
            "divCode": "confirm",
            "nodeType": "leafItem",
            "label": "确认",
            "name": "Button",
            "rightflag": "confirm",
            "parentKeys": ["managerRoot"],
        }
    }
    root_elements = [
        *sample_runtime_elements,
        {
            "fieldid": "set_manager_btn",
            "id": None,
            "name": None,
            "placeholder": None,
            "text": "设置经费管理员",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="set_manager_btn"]',
        },
        {
            "fieldid": "query_name",
            "id": None,
            "name": "projectName",
            "placeholder": "项目名称",
            "text": "",
            "role": "textbox",
            "tag_name": "input",
            "visible": True,
            "selector": '[fieldid="query_name"] input',
        },
        {
            "fieldid": "query_btn",
            "id": None,
            "name": None,
            "placeholder": None,
            "text": "查询",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="query_btn"]',
        },
        {
            "fieldid": "global_confirm_probe",
            "id": "confirm",
            "name": "confirm",
            "placeholder": None,
            "text": "",
            "role": None,
            "tag_name": "div",
            "visible": True,
            "selector": '[id="confirm"]',
        },
    ]
    runtime = PopupReferenceReturnsToListRuntime(
        root_elements,
        runtime_elements_by_page={
            "root": root_elements,
            "managerRoot": [
                {
                    "fieldid": "bgtManager",
                    "id": None,
                    "name": "bgtManager",
                    "placeholder": "经费管理员",
                    "text": "",
                    "role": "textbox",
                    "tag_name": "input",
                    "visible": True,
                    "selector": '[fieldid="bgtManager"] input',
                },
                {
                    "fieldid": "confirm",
                    "id": None,
                    "name": None,
                    "placeholder": None,
                    "text": "确认",
                    "role": "button",
                    "tag_name": "button",
                    "visible": True,
                    "selector": '[fieldid="confirm"]',
                },
            ],
        },
        dynamic_template_payloads_by_toolbar_click={"设置经费管理员": manager_template},
    )
    executor = WorkflowExecutor(gateway=FakeGateway(list_template), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "设置经费管理员"}},
            {
                "component": "form",
                "operation": "fill",
                "target": {
                    "fields": {
                        "经费管理员": {
                            "filter": {"conditions": [{"field": "人员名称", "equals": "人员二十一"}]},
                            "match": {"column": "人员名称", "equals": "人员二十一"},
                        }
                    }
                },
            },
            {
                "component": "query",
                "operation": "search",
                "target": {"conditions": [{"field": "项目名称", "equals": "ui自动化wdy0033"}]},
            },
        ]
    )

    assert report.success is True
    assert report.steps[2].data["auto_restored_template"] is True
    assert runtime.query_filled_fields[-1] == {"fieldid": "queryBox_projectName", "value": "ui自动化wdy0033"}


def test_workflow_executor_keeps_foreground_dialog_after_nested_popup_reference_until_confirmed(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    list_template = deepcopy(sample_template_payload)
    list_template["data"]["uidata"][0]["children"].append(
        {
            "key": "query_box",
            "divCode": "queryBox",
            "nodeType": "form",
            "label": "查询区",
            "children": [
                {
                    "key": "query_name",
                    "divCode": "query_name",
                    "nodeType": "formItem",
                    "label": "项目名称",
                    "name": "TextInput",
                    "dataField": "projectName",
                }
            ],
        }
    )
    list_template["data"]["actionEL"]["setManager"] = {
        "key": "set_manager_btn",
        "divCode": "set_manager_btn",
        "nodeType": "leafItem",
        "label": "设置经费管理员",
        "name": "Button",
        "rightflag": "set-manager",
        "parentKeys": ["root", "toolbar_root"],
    }
    list_template["data"]["actionEL"]["query"] = {
        "key": "query_btn",
        "divCode": "query_btn",
        "nodeType": "leafItem",
        "label": "查询",
        "name": "Button",
        "rightflag": "query",
        "parentKeys": ["root", "queryBox"],
    }

    manager_template = deepcopy(sample_template_payload)
    manager_template["data"]["uidata"][0]["key"] = "managerRoot"
    manager_template["data"]["uidata"][0]["divCode"] = "managerRoot"
    manager_template["data"]["uidata"][0]["children"] = [
        {
            "key": "managerCard",
            "divCode": "managerCard",
            "nodeType": "card",
            "label": "设置经费管理员",
            "children": [
                {
                    "key": "bgtManager",
                    "divCode": "bgtManager",
                    "nodeType": "formItem",
                    "label": "经费管理员",
                    "name": "YDFReferSelect",
                    "dataField": "bgtManager",
                }
            ],
        },
        {
            "key": "managerToolbar",
            "divCode": "managerToolbar",
            "nodeType": "toolbar",
            "label": "底部工具栏",
            "name": "LCDBtnToolbar",
            "children": [],
        },
    ]
    manager_template["data"]["actionEL"] = {
        "cancel": {
            "key": "cancel",
            "divCode": "cancel",
            "nodeType": "leafItem",
            "label": "取消",
            "name": "Button",
            "rightflag": "cancel",
            "parentKeys": ["managerRoot", "managerToolbar"],
        },
        "confirm": {
            "key": "confirm",
            "divCode": "confirm",
            "nodeType": "leafItem",
            "label": "确认",
            "name": "Button",
            "rightflag": "confirm",
            "parentKeys": ["managerRoot", "managerToolbar"],
        },
    }
    root_elements = [
        *sample_runtime_elements,
        {
            "fieldid": "set_manager_btn",
            "id": None,
            "name": None,
            "placeholder": None,
            "text": "设置经费管理员",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="set_manager_btn"]',
        },
        {
            "fieldid": "queryBox_projectName",
            "id": None,
            "name": "projectName",
            "placeholder": "项目名称",
            "text": "",
            "role": "textbox",
            "tag_name": "input",
            "visible": True,
            "selector": '[fieldid="queryBox_projectName"] input',
        },
        {
            "fieldid": "query_btn",
            "id": None,
            "name": None,
            "placeholder": None,
            "text": "查询",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="query_btn"]',
        },
    ]
    manager_elements = [
        {
            "fieldid": "bgtManager",
            "id": None,
            "name": "bgtManager",
            "placeholder": "经费管理员",
            "text": "",
            "role": "textbox",
            "tag_name": "input",
            "visible": True,
            "selector": '[fieldid="bgtManager"] input',
        },
        {
            "fieldid": "cancel",
            "id": None,
            "name": None,
            "placeholder": None,
            "text": "取消",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="cancel"]',
        },
        {
            "fieldid": "confirm",
            "id": None,
            "name": None,
            "placeholder": None,
            "text": "确认",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="confirm"]',
        },
    ]

    class PopupReferenceLeavesDialogRuntime(FakeRuntime):
        def fill_form_field(self, bound_element, value: str) -> dict[str, object]:
            super().fill_form_field(bound_element, value)
            self.runtime_elements_by_page["root"] = manager_elements
            return {
                "selected": [{"match": {"column": "人员名称", "equals": "人员二十一"}}],
                "confirmed": True,
                "confirm_label": "保存",
            }

        def click_toolbar_action(
            self,
            label: str,
            sub_label: str | None = None,
            fieldid: str | None = None,
            aliases: list[str] | None = None,
        ) -> None:
            super().click_toolbar_action(label, sub_label=sub_label, fieldid=fieldid, aliases=aliases)
            if label == "确认":
                self.runtime_elements_by_page["root"] = root_elements
                self.runtime_elements_by_page["managerRoot"] = root_elements
                self.notifications = [{"type": "success", "message": "更新成功！"}]

    runtime = PopupReferenceLeavesDialogRuntime(
        root_elements,
        runtime_elements_by_page={"root": root_elements, "managerRoot": manager_elements},
        dynamic_template_payloads_by_toolbar_click={"设置经费管理员": manager_template},
    )
    executor = WorkflowExecutor(gateway=FakeGateway(list_template), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "设置经费管理员"}},
            {
                "component": "form",
                "operation": "fill",
                "target": {
                    "fields": {
                        "经费管理员": {
                            "match": {"column": "人员名称", "equals": "人员二十一"},
                        }
                    }
                },
            },
            {"component": "toolbar", "operation": "click", "target": {"label": "确认"}},
            {
                "component": "query",
                "operation": "search",
                "target": {"conditions": [{"field": "项目名称", "equals": "ui自动化wdy0033"}]},
            },
        ]
    )

    assert report.success is True
    assert report.steps[2].data["popup_reference_restore"]["should_restore"] is False
    assert report.steps[2].data["popup_reference_restore"]["reason"] == "current_template_stable_action_visible"
    assert "auto_restored_template" not in report.steps[2].data
    assert report.steps[3].data["auto_restored_template"] is True
    assert runtime.query_filled_fields[-1] == {"fieldid": "queryBox_projectName", "value": "ui自动化wdy0033"}


def test_workflow_executor_reports_form_field_name_when_fill_fails(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    class FailingRuntime(FakeRuntime):
        def fill_form_field(self, bound_element, value: str) -> None:
            if bound_element.candidate.label == "项目名称":
                raise RuntimeError("弹出参照选择未回填到字段: 无可见下拉/参照候选")
            super().fill_form_field(bound_element, value)

    runtime = FailingRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "form", "operation": "fill", "target": {"fields": {"项目名称": "Codex项目"}}},
        ]
    )

    assert report.success is False
    assert "表单字段[项目名称]录入失败" in report.errors[0]
    assert "弹出参照选择未回填到字段" in report.errors[0]


def test_workflow_executor_preserves_multi_select_failure_diagnostics(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    class StructuredFailure(RuntimeError):
        def __init__(self) -> None:
            super().__init__("普通多选下拉最终集合与目标集合不一致")
            self.data = {
                "expected_values": ["草稿"],
                "actual_values": ["草稿", "启用"],
                "missing_values": [],
                "unexpected_values": ["启用"],
            }

    class FailingRuntime(FakeRuntime):
        def fill_form_field(self, bound_element, value: str) -> None:
            raise StructuredFailure()

    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=FailingRuntime(sample_runtime_elements),
    )
    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "form", "operation": "fill", "target": {"fields": {"项目名称": "草稿"}}},
        ]
    )

    assert report.success is False
    assert report.steps[-1].data["expected_values"] == ["草稿"]
    assert report.steps[-1].data["actual_values"] == ["草稿", "启用"]
    assert report.steps[-1].data["missing_values"] == []
    assert report.steps[-1].data["unexpected_values"] == ["启用"]


def test_workflow_executor_reports_confirmed_form_fill_value(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    class ConfirmingRuntime(FakeRuntime):
        def fill_form_field(self, bound_element, value: str) -> dict[str, Any]:
            super().fill_form_field(bound_element, value)
            return {
                "actual": str(value),
                "selector": bound_element.runtime.selector,
                "confirmed": True,
                "expected_values": [str(value)],
                "actual_values": [str(value)],
            }

    runtime = ConfirmingRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "form", "operation": "fill", "target": {"fields": {"项目名称": "Codex项目"}}},
        ]
    )

    assert report.success is True
    assert report.steps[-1].data["fields"] == [
        {
            "field": "项目名称",
            "equals": "Codex项目",
            "fieldid": "project_name",
            "actual": "Codex项目",
            "selector": '[fieldid="project_name"] input',
            "confirmed": True,
            "expected_values": ["Codex项目"],
            "actual_values": ["Codex项目"],
        }
    ]


def test_workflow_executor_resolves_cached_random_tokens_in_form_values(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "form",
                "operation": "fill",
                "target": {
                    "fields": {
                        "项目名称": "codex测试姓名{{random.suffix}}",
                        "项目编码": "codex测试姓名{{random.suffix}}",
                    }
                },
            },
        ]
    )

    assert report.success is True
    name_value = runtime.filled_fields[0]["value"]
    code_value = runtime.filled_fields[1]["value"]
    assert name_value == code_value
    assert name_value.startswith("codex测试姓名")
    assert "{{random.suffix}}" not in name_value


def test_workflow_executor_reuses_cached_random_token_in_tree_label(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "form",
                "operation": "fill",
                "target": {"fields": {"项目名称": "{{random.suffix}}"}},
            },
            {
                "component": "tree",
                "operation": "select",
                "target": {"label": "{{random.suffix}}"},
            },
        ]
    )

    assert report.success is True
    assert runtime.selected_tree_nodes == [
        {"label": runtime.filled_fields[0]["value"], "tree_fieldid": "topTree"},
    ]
    assert "{{random.suffix}}" not in runtime.selected_tree_nodes[0]["label"]


def test_workflow_executor_resolves_runtime_variables_in_tree_labels(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=runtime,
        runtime_variables={"org.first", "org.second"},
        runtime_context=RuntimeVariableContext(
            {
                "org": {
                    "first": "001 办公室",
                    "second": "002 财务处",
                }
            }
        ),
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "tree",
                "operation": "select",
                "target": {
                    "labels": ["{{org.first}}", "{{org.second}}"],
                },
            },
        ]
    )

    assert report.success is True
    assert runtime.selected_tree_nodes == [
        {"label": "001 办公室", "tree_fieldid": "topTree"},
        {"label": "002 财务处", "tree_fieldid": "topTree"},
    ]


def _tab_table_child_template(sample_template_payload: dict) -> dict:
    template = deepcopy(sample_template_payload)
    root = template["data"]["uidata"][0]
    root["key"] = "editRoot"
    root["divCode"] = "editRoot"
    root["children"] = [
        {
            "key": "status_tabs",
            "divCode": "status_tabs",
            "nodeType": "toolbar",
            "label": "状态页签",
            "props": {"type": "tab"},
            "parentKey": "editRoot",
            "children": [
                {
                    "key": "pending_tab",
                    "divCode": "pending_tab",
                    "nodeType": "leafItem",
                    "label": "待提交",
                    "name": "Button",
                }
            ],
        },
        {
            "key": "edit_table",
            "divCode": "edit_table",
            "nodeType": "table",
            "label": "子表格",
            "children": [
                {
                    "key": "edit_code_col",
                    "divCode": "edit_code_col",
                    "nodeType": "column",
                    "label": "子表编码",
                    "name": "TableColumn",
                    "dataField": "editCode",
                }
            ],
        },
    ]
    template["data"]["actionEL"] = {
        "save": {
            "key": "edit_save",
            "divCode": "edit_save",
            "nodeType": "leafItem",
            "label": "保存",
            "name": "Button",
            "rightflag": "save",
            "parentKeys": ["editRoot"],
        }
    }
    return template


def _run_tab_table_transition(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
    *,
    return_to_parent: bool,
) -> tuple[WorkflowExecutor, Any]:
    list_template = deepcopy(sample_template_payload)
    list_template["data"]["actionEL"]["create"] = {
        "key": "create_btn",
        "divCode": "xz_btn",
        "nodeType": "leafItem",
        "label": "新增",
        "name": "Button",
        "rightflag": "create",
        "parentKeys": ["root", "toolbar_root"],
    }
    edit_template = _tab_table_child_template(sample_template_payload)
    list_elements = [
        *sample_runtime_elements,
        {
            "fieldid": "xz_btn",
            "text": "新增",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="xz_btn"]',
        },
    ]
    edit_elements = [
        {
            "fieldid": "edit_save",
            "text": "保存",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="edit_save"]',
        },
        {
            "fieldid": "edit_code_col",
            "text": "子表编码",
            "tag_name": "th",
            "visible": True,
            "selector": '[fieldid="edit_code_col"]',
        },
    ]

    class TabTransitionRuntime(FakeRuntime):
        surface = "list"

        def click_toolbar_action(self, *args: Any, **kwargs: Any) -> None:
            super().click_toolbar_action(*args, **kwargs)
            self.surface = "edit"

        def click_tab_action(self, label: str, fieldid: str | None = None) -> None:
            super().click_tab_action(label, fieldid)
            if return_to_parent:
                self.surface = "list"

        def capture_runtime_elements(self, manifest) -> list[dict]:
            return list(list_elements) if self.surface == "list" else list_elements + edit_elements

        def is_region_visible(self, fieldid: str) -> bool:
            return fieldid in ({"main_table"} if self.surface == "list" else {"main_table", "edit_table"})

    runtime = TabTransitionRuntime(
        list_elements,
        dynamic_template_payloads_by_toolbar_click={"新增": edit_template},
    )
    executor = WorkflowExecutor(gateway=FakeGateway(list_template), runtime=runtime)
    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "新增"}},
            {"component": "tab", "operation": "click", "target": {"label": "待提交"}},
            {"component": "table_row_selection", "operation": "select", "target": {"row_number": 1}},
        ]
    )
    return executor, report


def test_workflow_executor_restores_parent_table_template_after_tab_click(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    _executor, report = _run_tab_table_transition(
        sample_template_payload,
        sample_runtime_elements,
        return_to_parent=True,
    )

    assert report.success is True, report.errors
    assert report.steps[2].data["restored_template"]["page"] == "root"
    assert report.steps[2].data["auto_restored_template"] is True
    assert report.steps[3].data["table_scope"]["table_fieldid"] == "main_table"


def test_workflow_executor_keeps_active_table_template_after_tab_click(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    executor, report = _run_tab_table_transition(
        sample_template_payload,
        sample_runtime_elements,
        return_to_parent=False,
    )

    assert report.success is True, report.errors
    assert "auto_restored_template" not in report.steps[2].data
    assert executor.current_manifest.page.fieldid == "editRoot"
    assert report.steps[3].data["table_scope"]["table_fieldid"] == "edit_table"


def test_workflow_executor_rebinds_fields_after_tab_click(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template = deepcopy(sample_template_payload)
    template["data"]["uidata"][0]["children"].append(
        {
            "key": "salary_tab",
            "divCode": "salary_tab",
            "nodeType": "card",
            "label": "工资信息",
            "name": "LCDCard",
            "parentKey": "root",
            "children": [
                {
                    "key": "salary_card_no",
                    "divCode": "salaryCardNo",
                    "nodeType": "formItem",
                    "label": "工资卡1卡号",
                    "name": "YDFInput",
                    "dataField": "salaryCardNo",
                }
            ],
        }
    )
    basic_elements = list(sample_runtime_elements)
    salary_elements = [
        *sample_runtime_elements,
        {
            "fieldid": "salaryCardNo",
            "id": None,
            "name": "salaryCardNo",
            "placeholder": "工资卡1卡号",
            "text": "",
            "role": "textbox",
            "tag_name": "input",
            "visible": True,
            "selector": '[fieldid="salaryCardNo"] input',
        },
    ]

    class TabRuntime(FakeRuntime):
        def click_tab_action(self, label: str, fieldid: str | None = None) -> None:
            super().click_tab_action(label, fieldid)
            self.runtime_elements_by_page["root"] = salary_elements

    runtime = TabRuntime(basic_elements, runtime_elements_by_page={"root": basic_elements})
    executor = WorkflowExecutor(gateway=FakeGateway(template), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "tab", "operation": "click", "target": {"label": "工资信息"}},
            {
                "component": "form",
                "operation": "fill",
                "target": {"fields": {"工资卡1卡号": "6222000000000000000"}},
            },
        ]
    )

    assert report.success is True
    assert runtime.filled_fields[-1] == {"fieldid": "salaryCardNo", "value": "6222000000000000000"}


def test_workflow_executor_rebinds_delayed_query_field_after_tab_click(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template = deepcopy(sample_template_payload)
    template["data"]["uidata"][0]["children"].extend(
        [
            {
                "key": "all_tab",
                "divCode": "all_tab",
                "nodeType": "card",
                "label": "全部",
                "name": "LCDCard",
                "parentKey": "root",
                "children": [],
            },
            {
                "key": "query_box",
                "divCode": "dataQueryArea",
                "nodeType": "form",
                "name": "LCDQueryString",
                "children": [
                    {
                        "key": "query_expert_name",
                        "divCode": "expertName",
                        "nodeType": "formItem",
                        "label": "专家姓名",
                        "name": "YDFInput",
                        "dataField": "expertName",
                    }
                ],
            },
        ]
    )
    template["data"]["actionEL"]["save"] = {
        "key": "save_btn",
        "divCode": "save_btn",
        "nodeType": "leafItem",
        "label": "保存",
        "name": "Button",
        "rightflag": "save",
        "parentKeys": ["root"],
    }
    query_elements = [
        *sample_runtime_elements,
        {
            "fieldid": "expertName",
            "name": "expertName",
            "label_text": "专家姓名",
            "placeholder": "请输入专家姓名",
            "role": "textbox",
            "tag_name": "input",
            "visible": True,
            "editable": True,
            "selector": '[fieldid="expertName"] input',
        },
    ]

    class DelayedQueryRuntime(FakeRuntime):
        after_tab = False
        captures_after_tab = 0

        def click_tab_action(self, label: str, fieldid: str | None = None) -> None:
            super().click_tab_action(label, fieldid)
            self.after_tab = True

        def expand_query_conditions(self) -> bool:
            self.expanded_query_count += 1
            return False

        def capture_runtime_elements(self, manifest) -> list[dict]:
            if self.after_tab:
                self.captures_after_tab += 1
                if self.captures_after_tab >= 2:
                    return query_elements
            return super().capture_runtime_elements(manifest)

    runtime = DelayedQueryRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(template), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "tab", "operation": "click", "target": {"label": "全部"}},
            {
                "component": "query",
                "operation": "search",
                "target": {"conditions": [{"field": "专家姓名", "equals": "自动化专家"}]},
            },
        ]
    )

    assert report.success is True, report.errors
    assert runtime.query_filled_fields == [
        {"fieldid": "dataQueryArea_expertName", "value": "自动化专家"}
    ]


def test_workflow_executor_executes_tree_and_table_row_action_steps(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=FakeRuntime(sample_runtime_elements),
    )

    report = executor.run(
        load_dsl(
            {
                "steps": [
                    {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
                    {"component": "tree", "operation": "select", "target": {"label": "001 办公室"}},
                    {
                        "component": "table_row_action",
                        "operation": "click",
                        "target": {
                            "action": "详情",
                            "match": {"column": "项目代码", "equals": "360000241010010000039"},
                        },
                    },
                ]
            }
        )
    )

    assert report.success is True
    assert executor.runtime.selected_tree_nodes == [{"label": "001 办公室", "tree_fieldid": "topTree"}]
    assert _without_timing(report.steps[1].data) == {"label": "001 办公室", "tree_fieldid": "topTree"}
    assert executor.runtime.focused_rows == [
        {
            "column": "项目代码",
            "equals": "360000241010010000039",
            "table": "明细表",
            "table_fieldid": "main_table",
            "table_columns": ["项目代码", "金额"],
        }
    ]
    assert executor.runtime.row_action_clicks == ["详情"]


def test_workflow_executor_reports_tree_search_metadata(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    class TreeSearchRuntime(FakeRuntime):
        def select_tree_node(self, label: str, tree_fieldid: str | None = None) -> None:
            super().select_tree_node(label, tree_fieldid=tree_fieldid)
            self.last_tree_search = {
                "label": label,
                "used": True,
                "found": True,
                "reason": "",
            }

    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=TreeSearchRuntime(sample_runtime_elements),
    )

    report = executor.run(
        load_dsl(
            {
                "steps": [
                    {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
                    {"component": "tree", "operation": "select", "target": {"label": "001 办公室"}},
                ]
            }
        )
    )

    assert report.success is True
    assert _without_timing(report.steps[-1].data) == {
        "label": "001 办公室",
        "tree_fieldid": "topTree",
        "tree_search": {
            "label": "001 办公室",
            "used": True,
            "found": True,
            "reason": "",
        },
    }


def test_workflow_executor_reports_tree_search_metadata_on_failure(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    class FailingTreeSearchRuntime(FakeRuntime):
        def select_tree_node(self, label: str, tree_fieldid: str | None = None) -> None:
            self.last_tree_search = {
                "label": label,
                "used": True,
                "found": False,
                "reason": "search_result_empty",
            }
            raise RuntimeError(f"未找到树节点: {label}")

    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=FailingTreeSearchRuntime(sample_runtime_elements),
    )

    report = executor.run(
        load_dsl(
            {
                "steps": [
                    {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
                    {"component": "tree", "operation": "select", "target": {"label": "流程管理"}},
                ]
            }
        )
    )

    assert report.success is False
    assert report.steps[-1].data["tree_search"] == {
        "label": "流程管理",
        "used": True,
        "found": False,
        "reason": "search_result_empty",
    }


def test_workflow_executor_selects_tree_by_component_name(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    side_card_children = template_payload["data"]["uidata"][0]["children"][2]["children"]
    side_card_children.append(
        {
            "key": "project_catalog_tree",
            "divCode": "downTree",
            "nodeType": "tree",
            "label": "项目目录",
            "name": "LCDTree",
        }
    )
    executor = WorkflowExecutor(
        gateway=FakeGateway(template_payload),
        runtime=FakeRuntime(sample_runtime_elements),
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "tree",
                "operation": "select",
                "target": {"name": "项目目录", "label": "901 执行项目分类0320"},
            },
        ]
    )

    assert report.success is True
    assert executor.runtime.selected_tree_nodes == [{"label": "901 执行项目分类0320", "tree_fieldid": "downTree"}]
    assert _without_timing(report.steps[-1].data) == {
        "label": "901 执行项目分类0320",
        "name": "项目目录",
        "tree_fieldid": "downTree",
    }


def test_workflow_executor_selects_tree_root_shortcut_with_resolved_fieldid(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=runtime,
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "tree",
                "operation": "select",
                "target": {"name": "内部机构", "node": "root"},
            },
        ]
    )

    assert report.success is True
    assert runtime.selected_tree_shortcuts == [{"node": "root", "tree_fieldid": "topTree"}]
    assert _without_timing(report.steps[-1].data) == {
        "node": "root",
        "label": "001 办公室",
        "name": "内部机构",
        "tree_fieldid": "topTree",
    }


def test_workflow_executor_selects_first_tree_leaf_shortcut_from_single_tree(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=runtime,
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "tree",
                "operation": "select",
                "target": {"node": "first_leaf"},
            },
        ]
    )

    assert report.success is True
    assert runtime.selected_tree_shortcuts == [{"node": "first_leaf", "tree_fieldid": "topTree"}]
    assert _without_timing(report.steps[-1].data) == {
        "node": "first_leaf",
        "label": "001001 秘书处",
        "tree_fieldid": "topTree",
    }


def test_workflow_executor_reports_missing_tree_shortcut_runtime_support(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    class RuntimeWithoutShortcut(FakeRuntime):
        select_tree_root = None

    runtime = RuntimeWithoutShortcut(sample_runtime_elements)
    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=runtime,
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "tree",
                "operation": "select",
                "target": {"node": "root"},
            },
        ]
    )

    assert report.success is False
    assert "当前运行时不支持树节点快捷选择: root" in report.steps[-1].message


def test_workflow_executor_selects_multiple_tree_labels(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=FakeRuntime(sample_runtime_elements),
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "tree",
                "operation": "select",
                "target": {
                    "name": "内部机构",
                    "labels": ["001 办公室", "002 财务处"],
                },
            },
        ]
    )

    assert report.success is True
    assert executor.runtime.selected_tree_nodes == [
        {"label": "001 办公室", "tree_fieldid": "topTree"},
        {"label": "002 财务处", "tree_fieldid": "topTree"},
    ]
    assert _without_timing(report.steps[-1].data) == {
        "labels": ["001 办公室", "002 财务处"],
        "name": "内部机构",
        "tree_fieldid": "topTree",
    }


def test_workflow_executor_resolves_duplicate_tree_name_by_runtime_visibility(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    side_card_children = template_payload["data"]["uidata"][0]["children"][2]["children"]
    hidden_tree = deepcopy(side_card_children[0])
    hidden_tree["key"] = "hidden_org_tree"
    hidden_tree["divCode"] = "topTree_hidden"
    side_card_children.append(hidden_tree)
    runtime = FakeRuntime(sample_runtime_elements, visible_region_fieldids={"topTree"})
    executor = WorkflowExecutor(
        gateway=FakeGateway(template_payload),
        runtime=runtime,
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "tree",
                "operation": "select",
                "target": {"name": "内部机构", "label": "001 办公室"},
            },
        ]
    )

    assert report.success is True
    assert runtime.selected_tree_nodes == [{"label": "001 办公室", "tree_fieldid": "topTree"}]
    assert _without_timing(report.steps[-1].data) == {
        "label": "001 办公室",
        "name": "内部机构",
        "tree_fieldid": "topTree",
    }


def test_workflow_executor_executes_table_row_selection_step(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=FakeRuntime(sample_runtime_elements),
    )

    report = executor.run(
        load_dsl(
            {
                "steps": [
                    {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
                    {
                        "component": "table_row_selection",
                        "operation": "select",
                        "target": {
                            "match": {"column": "项目代码", "equals": "360000241010010000039"},
                        },
                    },
                ]
            }
        )
    )

    assert report.success is True
    assert executor.runtime.selected_rows == [
        {
            "table": "明细表",
            "column": "项目代码",
            "equals": "360000241010010000039",
            "table_fieldid": "main_table",
            "table_columns": ["项目代码", "金额"],
        }
    ]


def test_workflow_executor_executes_table_row_selection_by_rows(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=FakeRuntime(sample_runtime_elements),
    )
    matches = [
        {"column": "项目代码", "equals": "360000240490020009086"},
        {"column": "项目代码", "equals": "360000240490020009085"},
        {"column": "项目代码", "equals": "360000240490020009040"},
    ]

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table_row_selection",
                "operation": "select",
                "target": {"rows": [{"match": match} for match in matches]},
            },
        ]
    )

    assert report.success is True
    assert executor.runtime.selected_rows == [
        {"table": "明细表", **match, "table_fieldid": "main_table", "table_columns": ["项目代码", "金额"]} for match in matches
    ]
    assert report.steps[-1].data["rows"] == matches
    assert report.steps[-1].data["table_fieldid"] == "main_table"
    assert report.steps[-1].data["table_scope"]["required_columns"] == ["项目代码"]


def test_workflow_executor_rejects_table_row_selection_when_any_match_condition_column_is_missing(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=FakeRuntime(sample_runtime_elements),
    )
    conditions = [
        {"column": "三级项目名称", "equals": "tztj513004"},
        {"column": "部门预算支出经济分类", "equals": "30101 基本工资"},
    ]
    match = {"conditions": conditions}

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "table_row_selection", "operation": "select", "target": {"match": match}},
        ]
    )

    assert report.success is False
    assert "缺少必需列" in report.errors[0]
    assert "三级项目名称" in report.errors[0]
    assert "部门预算支出经济分类" in report.errors[0]
    assert executor.runtime.selected_rows == []


def test_workflow_executor_reports_table_tree_search_after_row_selection(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    runtime.last_table_tree_search = {
        "table": "指标额度",
        "table_fieldid": "main_table",
        "match": {"column": "项目代码", "equals": "360000241010010000039"},
        "expanded": 2,
        "scrolled": 1,
        "found": True,
        "elapsed_ms": 900,
    }
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table_row_selection",
                "operation": "select",
                "target": {"match": {"column": "项目代码", "equals": "360000241010010000039"}},
            },
        ]
    )

    assert report.success is True
    assert report.steps[-1].data["row_search"] == runtime.last_table_tree_search


def test_workflow_executor_clicks_table_cell_link_with_scope_notifications_and_dynamic_template(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    detail_template_payload = deepcopy(sample_template_payload)
    detail_template_payload["data"]["uidata"][0]["divCode"] = "PM_DETAIL"
    runtime = FakeRuntime(
        sample_runtime_elements,
        notifications=[{"type": "success", "message": "打开成功"}],
        dynamic_template_payloads_by_toolbar_click={"cell-link": detail_template_payload},
    )
    runtime.last_table_tree_search = {
        "table": "",
        "table_fieldid": "main_table",
        "match": {"column": "项目代码", "equals": "3600001"},
        "found": True,
        "elapsed_ms": 30,
    }
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table",
                "operation": "click_cell_link",
                "target": {
                    "match": {"column": "项目代码", "equals": "3600001"},
                    "column": "项目代码",
                    "link_text": "3600001",
                },
            },
        ]
    )

    assert report.success is True
    assert runtime.notification_capture_count == 1
    assert runtime.table_cell_link_clicks == [
        {
            "column": "项目代码",
            "match": {"column": "项目代码", "equals": "3600001"},
            "row_number": None,
            "link_text": "3600001",
            "table": '明细表',
            "table_fieldid": "main_table",
            "table_columns": ["项目代码", "金额"],
        }
    ]
    assert report.steps[-1].action == "table.click_cell_link"
    assert report.steps[-1].data["column"] == "项目代码"
    assert report.steps[-1].data["match"] == {"column": "项目代码", "equals": "3600001"}
    assert report.steps[-1].data["link_text"] == "3600001"
    assert report.steps[-1].data["table_fieldid"] == "main_table"
    assert report.steps[-1].data["table_scope"]["required_columns"] == ["项目代码"]
    assert report.steps[-1].data["row_search"] == runtime.last_table_tree_search
    assert report.steps[-1].data["notifications"] == [{"type": "success", "message": "打开成功"}]
    assert report.steps[-1].data["dynamic_template"]["page"] == "PM_DETAIL"


def test_workflow_executor_rejects_missing_table_cell_link_column_before_click(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table",
                "operation": "click_cell_link",
                "target": {"column": "不存在列", "row_number": 1},
            },
        ]
    )

    assert report.success is False
    assert runtime.table_cell_link_clicks == []
    assert "缺少必需列" in report.errors[0]


def _template_with_query_region(template_payload: dict, fieldid: str = "dataQueryArea") -> dict:
    payload = deepcopy(template_payload)
    payload["data"]["uidata"][0]["children"].insert(
        1,
        {
            "key": "query_box",
            "divCode": fieldid,
            "nodeType": "form",
            "label": "查询区",
            "name": "LCDQueryString",
            "children": [],
        },
    )
    return payload


def test_workflow_executor_fails_query_search_on_unhandled_error_notification(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = _template_with_query_region(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"][1]["children"].append(
        {
            "key": "query_project_name",
            "divCode": "query_projectName",
            "nodeType": "formItem",
            "label": "项目名称",
            "name": "YDFInput",
            "dataField": "projectName",
        }
    )
    runtime = FakeRuntime(
        [
            *sample_runtime_elements,
            {
                "fieldid": "query_projectName",
                "name": "projectName",
                "placeholder": "项目名称",
                "text": "",
                "role": "textbox",
                "tag_name": "input",
                "visible": True,
                "selector": '[fieldid="query_projectName"] input',
            },
        ],
        notifications=[{"type": "error", "message": "查询失败: loadData of null"}],
    )
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "query",
                "operation": "search",
                "target": {"conditions": [{"field": "项目名称", "equals": "AI-001"}]},
            },
        ]
    )

    assert report.success is False
    assert report.steps[-1].action == "query.search"
    assert report.steps[-1].data["error"]["type"] == "NotificationError"
    assert "查询失败: loadData of null" in report.errors[0]


def test_workflow_executor_executes_query_reset_and_reports_location(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(
        gateway=FakeGateway(_template_with_query_region(sample_template_payload)),
        runtime=runtime,
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "query", "operation": "reset", "target": {}},
        ]
    )

    assert report.success is True
    assert runtime.query_reset_calls == [["dataQueryArea"]]
    assert report.steps[-1].action == "query.reset"
    assert report.steps[-1].message == "查询条件已重置"
    assert _without_timing(report.steps[-1].data) == {
        "query_region_fieldid": "dataQueryArea",
        "button": "重置",
        "locator_source": "exact_text",
    }


def test_workflow_executor_query_reset_rejects_page_without_query_region(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "query", "operation": "reset", "target": {}},
        ]
    )

    assert report.success is False
    assert runtime.query_reset_calls == []
    assert "当前页面不包含查询区" in report.errors[0]


def test_workflow_executor_query_reset_preserves_unsupported_template_gate(
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(
        gateway=FakeGateway(
            {"code": 999, "message": "通用错误: 页面编码不能为空"},
            menu_target=MenuTarget(
                menu_code="PM_INIT",
                menu_name="分析报表",
                path=["分析", "分析报表"],
                service_code="global00_-1_REPORT",
                service_url="#/native/report",
                native_url="tns:///native/report",
            ),
        ),
        runtime=runtime,
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "query", "operation": "reset", "target": {}},
        ]
    )

    assert report.success is False
    assert "当前页面不是单据模板页面，不支持查询操作" in report.errors[0]


def test_workflow_executor_query_reset_propagates_runtime_failure(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    class MissingResetRuntime(FakeRuntime):
        def click_query_reset(self, query_region_fieldids: list[str]) -> dict[str, str]:
            raise RuntimeError("未找到可点击查询重置动作")

    runtime = MissingResetRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(
        gateway=FakeGateway(_template_with_query_region(sample_template_payload)),
        runtime=runtime,
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "query", "operation": "reset", "target": {}},
        ]
    )

    assert report.success is False
    assert "未找到可点击查询重置动作" in report.errors[0]


def test_workflow_executor_executes_query_search_and_asserts_table_column(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    class MultiSelectQueryRuntime(FakeRuntime):
        def fill_query_field(self, bound_element, value: Any) -> dict[str, Any]:
            super().fill_query_field(bound_element, value)
            return {"expected_values": [str(value)], "actual_values": [str(value)]}

    template_payload = deepcopy(sample_template_payload)
    hidden_table = deepcopy(template_payload["data"]["uidata"][0]["children"][3])
    hidden_table.update({"key": "hidden_table", "divCode": "hidden_table", "hide": 1})
    template_payload["data"]["uidata"][0]["children"].append(hidden_table)
    _add_main_table_columns(template_payload, "项目负责人")
    template_payload["data"]["uidata"][0]["children"].insert(
        1,
        {
            "key": "query_box",
            "divCode": "queryBox",
            "nodeType": "card",
            "label": "查询区",
            "children": [
                {
                    "key": "query_pro_manager",
                    "divCode": "query_proManager",
                    "nodeType": "formItem",
                    "label": "项目负责人",
                    "name": "TextInput",
                    "dataField": "proManager",
                },
                {
                    "key": "query_button",
                    "divCode": "query_btn",
                    "nodeType": "leafItem",
                    "label": "查询",
                    "name": "Button",
                    "rightflag": "query",
                },
            ],
        },
    )
    runtime_elements = [
        *sample_runtime_elements,
        {
            "fieldid": "query_proManager",
            "id": None,
            "name": "proManager",
            "placeholder": "项目负责人",
            "text": "",
            "role": "textbox",
            "tag_name": "input",
            "visible": True,
            "selector": '[fieldid="query_proManager"] input',
        },
        {
            "fieldid": "query_btn",
            "id": None,
            "name": None,
            "placeholder": None,
            "text": "查询",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="query_btn"]',
        },
    ]
    runtime = MultiSelectQueryRuntime(
        runtime_elements,
        table_column_values={"项目负责人": ["孙丽娜", "孙丽娜"]},
    )
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "query",
                "operation": "search",
                "target": {"conditions": [{"field": "项目负责人", "equals": "孙丽娜"}]},
            },
            {
                "component": "table",
                "operation": "assert_column_values",
                "target": {"column": "项目负责人", "equals": "孙丽娜"},
            },
        ]
    )

    assert report.success is True
    assert runtime.action_completion_events == [
        {
            "event": "prepare",
            "action": "query.search",
            "context": {"source_page_id": "root", "target_table_fieldid": "main_table_table"},
        },
        {"event": "observe", "action": "query.search", "stage": "notifications"},
        {"event": "observe", "action": "query.search", "stage": "dynamic_template"},
        {"event": "observe", "action": "query.search", "stage": "dom"},
    ]
    assert runtime.query_filled_fields == [{"fieldid": "query_proManager", "value": "孙丽娜"}]
    assert runtime.filled_fields == []
    assert runtime.clicked_targets == ["查询"]
    assert runtime.notification_capture_count == 1
    assert runtime.expanded_query_count == 0
    assert report.steps[1].data["conditions"][0]["expected_values"] == ["孙丽娜"]
    assert report.steps[1].data["conditions"][0]["actual_values"] == ["孙丽娜"]
    assert report.steps[-1].data["column"] == "项目负责人"
    assert report.steps[-1].data["values"] == ["孙丽娜", "孙丽娜"]
    assert report.steps[-1].data["table_scope"]["required_columns"] == ["项目负责人"]


@pytest.mark.parametrize(
    ("visible_fieldids", "second_table_hidden", "expected_fieldid"),
    [
        ({"main_table"}, False, "main_table_table"),
        ({"other_table"}, True, "other_table_table"),
        ({"main_table", "other_table"}, False, ""),
        (set(), False, ""),
        (None, False, ""),
    ],
)
def test_workflow_executor_query_completion_uses_unique_runtime_visible_table(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
    visible_fieldids: set[str] | None,
    second_table_hidden: bool,
    expected_fieldid: str,
) -> None:
    class QueryCompletionRuntime(FakeRuntime):
        def _prepare_action_completion(self, request: ActionCompletionRequest) -> None:
            super()._prepare_action_completion(request)
            self._action_completion_context = dict(request.context)
            self._action_completion_state = {"target_table": "旧结果", "target_busy": 0}
            self._action_completion_seen_busy = False
            self._action_surface_observers = []

        def _capture_action_completion_state(self) -> dict[str, Any]:
            return {"target_table": "新结果", "target_busy": 0}

        def _observe_action_completion(
            self, request: ActionCompletionRequest, stage: str = ""
        ) -> ActionCompletionObservation:
            return ActionCompletionObservation(
                dom_signal=(
                    PlaywrightRuntime._action_dom_completion_signal(self, request.action)
                    if stage == "dom" else ""
                )
            )

    template_payload = deepcopy(sample_template_payload)
    other_table = deepcopy(template_payload["data"]["uidata"][0]["children"][3])
    other_table.update({"key": "other_table", "divCode": "other_table", "hide": int(second_table_hidden)})
    template_payload["data"]["uidata"][0]["children"].append(other_table)
    runtime = QueryCompletionRuntime(sample_runtime_elements, visible_region_fieldids=visible_fieldids)
    if visible_fieldids is None:
        runtime.is_region_visible = None
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "query", "operation": "search", "target": {"conditions": []}},
        ]
    )

    assert report.success is True
    completion = report.steps[-1].data
    assert completion["wait_duration_ms"] == (0 if expected_fieldid else 17500)
    assert completion["completion_signal"] == ("target_component" if expected_fieldid else "compatibility_timeout")
    assert completion["fallback_used"] is (not expected_fieldid)
    assert runtime.action_completion_events[0]["context"]["target_table_fieldid"] == expected_fieldid


@pytest.mark.parametrize('multiple_tables', [False, True])
def test_query_completion_passes_identity_only_for_unique_visible_table(
    sample_template_payload, sample_runtime_elements, multiple_tables,
) -> None:
    payload = deepcopy(sample_template_payload)
    table = payload['data']['uidata'][0]['children'][3]
    table['enty'] = {'info': {'uri': 'PM.PM.project', 'domain': 'project', 'code': 'project'}}
    if multiple_tables:
        other = deepcopy(table)
        other.update(key='other_table', divCode='other_table')
        payload['data']['uidata'][0]['children'].append(other)
    runtime = FakeRuntime(sample_runtime_elements, visible_region_fieldids={'main_table', 'other_table'})
    executor = WorkflowExecutor(gateway=FakeGateway(payload), runtime=runtime)

    report = executor.run([
        {'action': 'open_menu', 'menu_path': '项目管理>>项目立项'},
        {'component': 'query', 'operation': 'search', 'target': {'conditions': [], 'table': 'main_table'}},
    ])

    assert report.success is True
    context = runtime.action_completion_events[0]['context']
    if multiple_tables:
        assert 'target_table_query' not in context
    else:
        assert context['target_table_query'] == {'entity_uri': 'PM.PM.project', 'domain': 'project', 'busi_obj': 'project'}
        assert context['target_table_token']


def test_workflow_executor_passes_query_region_fieldid_candidates_to_runtime(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"].insert(
        1,
        {
            "key": "query_box",
            "divCode": "dataQueryArea",
            "nodeType": "form",
            "label": "查询区",
            "name": "LCDQueryString",
            "children": [
                {
                    "key": "query_pro_manager",
                    "divCode": "query_proManager",
                    "nodeType": "formItem",
                    "label": "项目负责人",
                    "name": "YDFInput",
                    "dataField": "proManager",
                }
            ],
        },
    )
    runtime = FakeRuntime(
        [
            *sample_runtime_elements,
            {
                "fieldid": "dataQueryArea_proManager",
                "id": None,
                "name": "proManager",
                "placeholder": "项目负责人",
                "text": "",
                "role": "textbox",
                "tag_name": "input",
                "visible": True,
                "selector": '[fieldid="dataQueryArea_proManager"] input',
            },
            {
                "fieldid": "dataQueryArea_query_icon",
                "id": None,
                "name": None,
                "placeholder": None,
                "text": "查询",
                "role": "button",
                "tag_name": "button",
                "visible": True,
                "selector": '[fieldid="dataQueryArea_query_icon"]',
            },
        ]
    )
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "query",
                "operation": "search",
                "target": {"conditions": [{"field": "项目负责人", "equals": "孙丽娜"}]},
            },
        ]
    )

    assert report.success is True
    assert runtime.query_filled_fields == [{"fieldid": "dataQueryArea_proManager", "value": "孙丽娜"}]
    assert runtime.query_click_details == [
        {"label": "查询", "fieldids": ["dataQueryArea_query_icon", "dataQueryArea"]}
    ]


def test_workflow_executor_expands_query_only_when_condition_is_not_bound(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"].insert(
        1,
        {
            "key": "query_box",
            "divCode": "queryBox",
            "nodeType": "card",
            "label": "查询区",
            "children": [
                {
                    "key": "query_apply_dept",
                    "divCode": "query_internalDepCode",
                    "nodeType": "formItem",
                    "label": "项目申报部门",
                    "name": "YDFTreeSelect",
                    "dataField": "internalDepCode",
                },
                {
                    "key": "query_button",
                    "divCode": "query_btn",
                    "nodeType": "leafItem",
                    "label": "查询",
                    "name": "Button",
                    "rightflag": "query",
                },
            ],
        },
    )
    query_button = {
        "fieldid": "query_btn",
        "id": None,
        "name": None,
        "placeholder": None,
        "text": "查询",
        "role": "button",
        "tag_name": "button",
        "visible": True,
        "selector": '[fieldid="query_btn"]',
    }
    hidden_query_field = {
        "fieldid": "query_internalDepCode",
        "id": None,
        "name": "internalDepCode",
        "placeholder": "项目申报部门",
        "text": "",
        "role": "combobox",
        "tag_name": "input",
        "visible": True,
        "selector": '[fieldid="query_internalDepCode"] input',
    }
    runtime = FakeRuntime([*sample_runtime_elements, query_button])

    def capture_after_expand(manifest):
        base = [*sample_runtime_elements, query_button]
        if runtime.expanded_query_count:
            base.append(hidden_query_field)
        return base

    runtime.capture_runtime_elements = capture_after_expand  # type: ignore[method-assign]
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "query",
                "operation": "search",
                "target": {"conditions": [{"field": "项目申报部门", "equals": "001 办公室"}]},
            },
        ]
    )

    assert report.success is True
    assert runtime.expanded_query_count == 1
    assert runtime.query_filled_fields == [{"fieldid": "query_internalDepCode", "value": "001 办公室"}]
    assert report.steps[-1].data["expanded_query"] is True


def test_workflow_executor_query_search_preserves_popup_reference_condition_values(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    class RawQueryRuntime(FakeRuntime):
        def fill_query_field(self, bound_element, value: Any) -> None:
            self.query_filled_fields.append({"fieldid": bound_element.candidate.fieldid, "value": value})

    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"].insert(
        1,
        {
            "key": "query_box",
            "divCode": "queryBox",
            "nodeType": "card",
            "label": "查询区",
            "children": [
                {
                    "key": "query_project_catalog",
                    "divCode": "query_proCatalogCode",
                    "nodeType": "formItem",
                    "label": "项目目录",
                    "name": "YDFTreeModalSelect",
                    "dataField": "proCatalogCode",
                    "dataType": "refer",
                },
                {
                    "key": "query_button",
                    "divCode": "query_btn",
                    "nodeType": "leafItem",
                    "label": "查询",
                    "name": "Button",
                    "rightflag": "query",
                },
            ],
        },
    )
    runtime_elements = [
        *sample_runtime_elements,
        {
            "fieldid": "query_proCatalogCode",
            "id": None,
            "name": "proCatalogCode",
            "placeholder": "项目目录",
            "text": "",
            "role": "textbox",
            "tag_name": "input",
            "visible": True,
            "selector": '[fieldid="query_proCatalogCode"] input',
        },
        {
            "fieldid": "query_btn",
            "id": None,
            "name": None,
            "placeholder": None,
            "text": "查询",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="query_btn"]',
        },
    ]
    runtime = RawQueryRuntime(runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)
    values = [
        "101 财政一级",
        ["101 财政一级", "767 财务一级测试"],
        {"match": {"column": "目录名称", "equals": "101 财政一级"}},
    ]

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "query",
                "operation": "search",
                "target": {
                    "conditions": [
                        {"field": "项目目录", "equals": value}
                        for value in values
                    ]
                },
            },
        ]
    )

    assert report.success is True
    assert [item["value"] for item in runtime.query_filled_fields] == values
    assert [item["equals"] for item in report.steps[-1].data["conditions"]] == values


def test_workflow_executor_query_search_reports_popup_reference_result(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    class PopupResultRuntime(FakeRuntime):
        def fill_query_field(self, bound_element, value: Any) -> dict[str, object]:
            super().fill_query_field(bound_element, value)
            return {
                "popup_tab_context": [{"label": "本单位人员账户"}],
                "popup_tree_context": [{"label": "101 财政一级"}],
                "selected": [{"equals": "101 财政一级"}],
                "confirmed": True,
                "confirm_label": "确定",
            }

    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"].insert(
        1,
        {
            "key": "query_box",
            "divCode": "queryBox",
            "nodeType": "card",
            "label": "查询区",
            "children": [
                {
                    "key": "query_project_catalog",
                    "divCode": "query_proCatalogCode",
                    "nodeType": "formItem",
                    "label": "项目目录",
                    "name": "YDFTreeModalSelect",
                    "dataField": "proCatalogCode",
                    "dataType": "refer",
                },
                {
                    "key": "query_button",
                    "divCode": "query_btn",
                    "nodeType": "leafItem",
                    "label": "查询",
                    "name": "Button",
                    "rightflag": "query",
                },
            ],
        },
    )
    runtime_elements = [
        *sample_runtime_elements,
        {
            "fieldid": "query_proCatalogCode",
            "id": None,
            "name": "proCatalogCode",
            "placeholder": "项目目录",
            "text": "",
            "role": "textbox",
            "tag_name": "input",
            "visible": True,
            "selector": '[fieldid="query_proCatalogCode"] input',
        },
        {
            "fieldid": "query_btn",
            "id": None,
            "name": None,
            "placeholder": None,
            "text": "查询",
            "role": "button",
            "tag_name": "button",
            "visible": True,
            "selector": '[fieldid="query_btn"]',
        },
    ]
    runtime = PopupResultRuntime(runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "query",
                "operation": "search",
                "target": {"conditions": [{"field": "项目目录", "equals": "101 财政一级"}]},
            },
        ]
    )

    condition_result = report.steps[-1].data["conditions"][0]
    assert condition_result["equals"] == "101 财政一级"
    assert condition_result["popup_tab_context"] == [{"label": "本单位人员账户"}]
    assert condition_result["popup_tree_context"] == [{"label": "101 财政一级"}]
    assert condition_result["selected"] == [{"equals": "101 财政一级"}]
    assert condition_result["confirmed"] is True
    assert condition_result["confirm_label"] == "确定"


def test_workflow_executor_query_search_does_not_fall_back_to_main_table_field(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"].append(
        {
            "key": "table",
            "divCode": "table",
            "nodeType": "table",
            "label": "项目",
            "children": [
                {
                    "key": "table_apply_dept",
                    "divCode": "table_internalDepCode",
                    "nodeType": "formItem",
                    "label": "项目申报部门",
                    "name": "YDFInput",
                    "dataField": "internalDepCode",
                }
            ],
        }
    )
    runtime_elements = [
        *sample_runtime_elements,
        {
            "fieldid": "table_internalDepCode",
            "id": None,
            "name": None,
            "placeholder": None,
            "text": "项目申报部门",
            "role": None,
            "tag_name": "th",
            "visible": True,
            "selector": '[fieldid="table_internalDepCode"]',
        },
    ]
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=FakeRuntime(runtime_elements))

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "query",
                "operation": "search",
                "target": {"conditions": [{"field": "项目申报部门", "equals": "001 办公室"}]},
            },
        ]
    )

    assert report.success is False
    assert "未绑定查询字段: 项目申报部门" in report.errors[0]
    assert executor.runtime.query_filled_fields == []


def test_workflow_executor_query_search_uses_runtime_only_query_control(
    sample_template_payload: dict[str, Any],
    sample_runtime_elements: list[dict[str, Any]],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"].append(
        {
            "key": "query_box",
            "divCode": "queryBox",
            "nodeType": "form",
            "name": "LCDQueryString",
            "children": [
                {
                    "key": "query_name",
                    "divCode": "queryName",
                    "nodeType": "formItem",
                    "label": "项目名称",
                    "name": "YDFInput",
                    "dataField": "projectName",
                }
            ],
        }
    )
    template_payload["data"]["uidata"][0]["children"] = [
        child for child in template_payload["data"]["uidata"][0]["children"] if child.get("key") != "toolbar_root"
    ]
    template_payload["data"]["actionEL"] = {}
    runtime = FakeRuntime(
        [
            *sample_runtime_elements,
            {
                "fieldid": "dom_query_projectName",
                "label_text": "搜索项目名称",
                "placeholder": "请输入项目名称",
                "role": "textbox",
                "tag_name": "input",
                "visible": True,
                "selector": '[fieldid="dom_query_projectName"]',
            },
        ]
    )
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "query",
                "operation": "search",
                "target": {"conditions": [{"field": "搜索项目名称", "equals": "测试项目"}]},
            },
        ]
    )

    assert report.success is True
    assert runtime.query_filled_fields == [{"fieldid": "runtime:搜索项目名称", "value": "测试项目"}]


def test_workflow_executor_query_search_does_not_fall_back_to_edit_form_field(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["actionEL"] = {
        "save": {
            "key": "save_btn",
            "divCode": "save_btn",
            "nodeType": "leafItem",
            "label": "保存",
            "name": "Button",
            "rightflag": "save",
            "parentKeys": ["root"],
        },
        "cancel": {
            "key": "cancel_btn",
            "divCode": "cancel_btn",
            "nodeType": "leafItem",
            "label": "取消",
            "name": "Button",
            "rightflag": "cancel",
            "parentKeys": ["root"],
        },
    }
    runtime_elements = [
        item for item in sample_runtime_elements if item["fieldid"] not in {"btn_save", "btn_submit"}
    ]
    runtime = FakeRuntime(runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "query",
                "operation": "search",
                "target": {"conditions": [{"field": "项目名称", "equals": "UI财政二级项目测试"}]},
            },
        ]
    )

    assert report.success is False
    assert "未绑定查询字段: 项目名称" in report.errors[0]
    assert runtime.query_filled_fields == []


def test_workflow_executor_executes_table_row_selection_by_single_row_number(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=FakeRuntime(sample_runtime_elements),
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "table_row_selection", "operation": "select", "target": {"row_number": 1}},
        ]
    )

    assert report.success is True
    assert executor.runtime.selected_row_numbers == [
        {
            "row_number": 1,
            "table": '明细表',
            "table_fieldid": "main_table",
            "table_columns": ["项目代码", "金额"],
        }
    ]
    assert report.steps[-1].data["row_numbers"] == [1]
    assert report.steps[-1].data["table_scope"]["table_fieldid"] == "main_table"


def test_workflow_executor_executes_table_row_selection_select_all(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=runtime,
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "table_row_selection", "operation": "select", "target": {"select_all": True}},
        ]
    )

    assert report.success is True
    assert runtime.selected_all_tables == [
        {"table": '明细表', "table_fieldid": "main_table", "table_columns": ["项目代码", "金额"]}
    ]
    assert runtime.selected_row_numbers == []
    assert report.steps[-1].data["select_all"] is True
    assert report.steps[-1].data["table_scope"]["table_fieldid"] == "main_table"


def test_workflow_executor_executes_table_row_selection_by_table_and_row_number(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"].append(
        {
            "key": "detail_table",
            "divCode": "detail_table",
            "nodeType": "table",
            "label": "可用指标",
            "children": [
                {
                    "key": "subject_col",
                    "divCode": "subject_col",
                    "nodeType": "column",
                    "label": "预算编制科目",
                    "name": "TableColumn",
                    "dataField": "subjectCode",
                }
            ],
        }
    )
    executor = WorkflowExecutor(
        gateway=FakeGateway(template_payload),
        runtime=FakeRuntime(sample_runtime_elements),
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table_row_selection",
                "operation": "select",
                "target": {"table": "可用指标", "row_number": 1},
            },
        ]
    )

    assert report.success is True
    assert executor.runtime.selected_row_numbers == [
        {
            "row_number": 1,
            "table": "可用指标",
            "table_fieldid": "detail_table",
            "table_columns": ["预算编制科目"],
        }
    ]
    assert report.steps[-1].data["row_numbers"] == [1]
    assert report.steps[-1].data["table"] == "可用指标"
    assert report.steps[-1].data["table_scope"]["table_fieldid"] == "detail_table"


def test_workflow_executor_reports_table_row_selection_debug(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"].append(
        {
            "key": "detail_table",
            "divCode": "detail_table",
            "nodeType": "table",
            "label": "调出方",
            "children": [
                {
                    "key": "subject_col",
                    "divCode": "subject_col",
                    "nodeType": "column",
                    "label": "预算编制科目",
                    "name": "TableColumn",
                    "dataField": "subjectCode",
                }
            ],
        }
    )
    runtime = FakeRuntime(sample_runtime_elements)
    runtime.last_table_selection_debug = {
        "strategy": "row_click",
        "selected_after": True,
        "table": "调出方",
        "table_fieldid": "detail_table",
        "row_number": 1,
    }
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table_row_selection",
                "operation": "select",
                "target": {"table": "调出方", "row_number": 1},
            },
        ]
    )

    assert report.success is True
    assert report.steps[-1].data["selection_debug"] == {
        "strategy": "row_click",
        "selected_after": True,
        "table": "调出方",
        "table_fieldid": "detail_table",
        "row_number": 1,
    }


def test_workflow_executor_executes_first_available_in_named_table_scope(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"].append(
        {
            "key": "income_received_table",
            "divCode": "dzkxxx_table",
            "nodeType": "table",
            "label": "到账款项信息",
            "children": [
                {
                    "key": "amount_col",
                    "divCode": "dzkxxx_table_amount",
                    "nodeType": "column",
                    "label": "到账金额",
                    "name": "TableColumn",
                    "dataField": "amount",
                }
            ],
        }
    )
    executor = WorkflowExecutor(
        gateway=FakeGateway(template_payload),
        runtime=FakeRuntime(sample_runtime_elements),
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table_row_selection",
                "operation": "select",
                "target": {"table": "到账款项信息", "first_available": True},
            },
        ]
    )

    assert report.success is True
    assert executor.runtime.selected_row_numbers == [
        {
            "row_number": 1,
            "table": "到账款项信息",
            "table_fieldid": "dzkxxx_table",
            "table_columns": ["到账金额"],
        }
    ]
    assert report.steps[-1].data["row_numbers"] == [1]
    assert report.steps[-1].data["table"] == "到账款项信息"
    assert report.steps[-1].data["table_scope"]["table_fieldid"] == "dzkxxx_table"


def test_workflow_executor_inferrs_table_row_selection_scope_from_unique_match_column(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"].append(
        {
            "key": "available_budget_table",
            "divCode": "kyzb_table",
            "nodeType": "table",
            "label": "可用指标",
            "children": [
                {
                    "key": "gov_pur_col",
                    "divCode": "kyzb_table_isGovPurName",
                    "nodeType": "column",
                    "label": "政府采购标识",
                    "name": "TableColumn",
                    "dataField": "isGovPurName",
                }
            ],
        }
    )
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table_row_selection",
                "operation": "select",
                "target": {"match": {"column": "政府采购标识", "equals": "是"}},
            },
        ]
    )

    assert report.success is True
    assert runtime.selected_rows == [
        {
            "table": "可用指标",
            "column": "政府采购标识",
            "equals": "是",
            "table_fieldid": "kyzb_table",
            "table_columns": ["政府采购标识"],
        }
    ]
    assert report.steps[-1].data["match"] == {"column": "政府采购标识", "equals": "是"}
    assert report.steps[-1].data["table_scope"]["table_fieldid"] == "kyzb_table"


def test_workflow_executor_column_scope_can_use_column_owner_outside_runtime_visible_preference(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"].extend(
        [
            {
                "key": "available_budget_table",
                "divCode": "kyzb_table",
                "nodeType": "table",
                "label": "可用指标",
                "children": [
                    {
                        "key": "gov_pur_col",
                        "divCode": "kyzb_table_isGovPurName",
                        "nodeType": "leafItem",
                        "label": "政府采购标识",
                        "name": "column",
                        "dataField": "isGovPurName",
                    }
                ],
            },
            {
                "key": "voucher_table",
                "divCode": "bg_table",
                "nodeType": "table",
                "label": "表格",
                "children": [
                    {
                        "key": "voucher_gov_pur_col",
                        "divCode": "bg_table_isGovPurName",
                        "nodeType": "column",
                        "label": "政府采购标识",
                        "name": "TableColumn",
                        "dataField": "isGovPurName",
                    }
                ],
            },
        ]
    )
    runtime = FakeRuntime(sample_runtime_elements, visible_region_fieldids={"bg_table"})
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table_row_selection",
                "operation": "select",
                "target": {"match": {"column": "政府采购标识", "equals": "是"}},
            },
        ]
    )

    assert report.success is True
    assert runtime.selected_rows == [
        {
            "table": "表格",
            "column": "政府采购标识",
            "equals": "是",
            "table_fieldid": "bg_table",
            "table_columns": ["政府采购标识"],
        }
    ]


def test_workflow_executor_rejects_table_row_selection_when_match_column_is_ambiguous(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"].extend(
        [
            {
                "key": "available_budget_table",
                "divCode": "kyzb_table",
                "nodeType": "table",
                "label": "可用指标",
                "children": [
                    {
                        "key": "available_gov_pur_col",
                        "divCode": "kyzb_table_isGovPurName",
                        "nodeType": "column",
                        "label": "政府采购标识",
                        "name": "TableColumn",
                        "dataField": "isGovPurName",
                    }
                ],
            },
            {
                "key": "voucher_table",
                "divCode": "bg_table",
                "nodeType": "table",
                "label": "表格",
                "children": [
                    {
                        "key": "voucher_gov_pur_col",
                        "divCode": "bg_table_isGovPurName",
                        "nodeType": "column",
                        "label": "政府采购标识",
                        "name": "TableColumn",
                        "dataField": "isGovPurName",
                    }
                ],
            },
        ]
    )
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table_row_selection",
                "operation": "select",
                "target": {"match": {"column": "政府采购标识", "equals": "是"}},
            },
        ]
    )

    assert report.success is False
    assert "请补充 target.table" in report.errors[0]
    assert "政府采购标识" in report.errors[0]
    assert runtime.selected_rows == []


def test_workflow_executor_executes_table_row_selection_select_all_by_table(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"].append(
        {
            "key": "detail_table",
            "divCode": "detail_table",
            "nodeType": "table",
            "label": "可用指标",
            "children": [
                {
                    "key": "subject_col",
                    "divCode": "subject_col",
                    "nodeType": "column",
                    "label": "预算编制科目",
                    "name": "TableColumn",
                    "dataField": "subjectCode",
                }
            ],
        }
    )
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(
        gateway=FakeGateway(template_payload),
        runtime=runtime,
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table_row_selection",
                "operation": "select",
                "target": {"table": "可用指标", "select_all": True},
            },
        ]
    )

    assert report.success is True
    assert runtime.selected_all_tables == [
        {
            "table": "可用指标",
            "table_fieldid": "detail_table",
            "table_columns": ["预算编制科目"],
        }
    ]
    assert report.steps[-1].data["select_all"] is True
    assert report.steps[-1].data["table"] == "可用指标"
    assert report.steps[-1].data["table_scope"]["table_fieldid"] == "detail_table"


def test_workflow_executor_reports_table_row_selection_table_name_mismatch(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"].append(
        {
            "key": "detail_table",
            "divCode": "detail_table",
            "nodeType": "table",
            "label": "可用指标",
            "children": [],
        }
    )
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(
        gateway=FakeGateway(template_payload),
        runtime=runtime,
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table_row_selection",
                "operation": "select",
                "target": {"table": "不存在表格", "row_number": 1},
            },
        ]
    )

    assert report.success is False
    assert "表格名称未匹配: target.table=不存在表格" in report.errors[0]
    assert runtime.selected_row_numbers == []


def test_workflow_executor_rejects_row_number_selection_when_multiple_tables_are_visible(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"].append(
        {
            "key": "detail_table",
            "divCode": "detail_table",
            "nodeType": "table",
            "label": "预算编制科目",
            "children": [
                {
                    "key": "subject_col",
                    "divCode": "subject_col",
                    "nodeType": "column",
                    "label": "预算编制科目",
                    "name": "TableColumn",
                    "dataField": "subjectCode",
                }
            ],
        }
    )
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "table_row_selection", "operation": "select", "target": {"row_number": 1}},
        ]
    )

    assert report.success is False
    assert "无法唯一确定表格作用域" in report.errors[0]
    assert "请补充 target.table" in report.errors[0]
    assert runtime.selected_row_numbers == []


def test_workflow_executor_rejects_select_all_when_multiple_tables_are_visible(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["uidata"][0]["children"].append(
        {
            "key": "detail_table",
            "divCode": "detail_table",
            "nodeType": "table",
            "label": "预算编制科目",
            "children": [
                {
                    "key": "subject_col",
                    "divCode": "subject_col",
                    "nodeType": "column",
                    "label": "预算编制科目",
                    "name": "TableColumn",
                    "dataField": "subjectCode",
                }
            ],
        }
    )
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "table_row_selection", "operation": "select", "target": {"select_all": True}},
        ]
    )

    assert report.success is False
    assert "无法唯一确定表格作用域" in report.errors[0]
    assert "target.table" in report.errors[0]
    assert runtime.selected_all_tables == []


def test_workflow_executor_executes_table_row_selection_by_multiple_row_numbers(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=FakeRuntime(sample_runtime_elements),
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "table_row_selection", "operation": "select", "target": {"row_numbers": [1, 3, 5]}},
        ]
    )

    assert report.success is True
    assert executor.runtime.selected_row_numbers == [
        {
            "row_number": row_number,
            "table": '明细表',
            "table_fieldid": "main_table",
            "table_columns": ["项目代码", "金额"],
        }
        for row_number in [1, 3, 5]
    ]


def test_workflow_executor_reports_table_row_selection_runtime_reason(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=FakeRuntime(sample_runtime_elements, should_select_row=False),
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "table_row_selection", "operation": "select", "target": {"row_number": 1}},
        ]
    )

    assert report.success is False
    assert "未找到可选择的表格行号: [1]" in report.errors[0]
    assert "原因: 未找到表格行选择框: 1" in report.errors[0]


def test_workflow_executor_reports_table_row_selection_match_runtime_reason(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=FakeRuntime(sample_runtime_elements, should_select_row=False),
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table_row_selection",
                "operation": "select",
                "target": {"match": {"column": "项目名称", "equals": "项目A"}},
            },
        ]
    )

    assert report.success is False
    assert "缺少必需列: 项目名称" in report.errors[0]
    assert executor.runtime.selected_rows == []


def test_workflow_executor_reports_table_tree_search_when_row_selection_fails(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    _add_main_table_columns(template_payload, "项目名称")
    runtime = FakeRuntime(sample_runtime_elements, should_select_row=False)
    runtime.last_table_tree_search = {
        "table": "指标额度",
        "table_fieldid": "main_table",
        "match": {"column": "项目名称", "equals": "项目A"},
        "expanded": 2,
        "scrolled": 1,
        "found": False,
        "elapsed_ms": 900,
    }
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table_row_selection",
                "operation": "select",
                "target": {"match": {"column": "项目名称", "equals": "项目A"}},
            },
        ]
    )

    assert report.success is False
    assert "row_search=" in report.errors[0]
    assert "'expanded': 2" in report.errors[0]


def test_workflow_executor_reports_table_row_selection_select_all_runtime_reason(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=FakeRuntime(sample_runtime_elements, should_select_row=False),
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "table_row_selection", "operation": "select", "target": {"select_all": True}},
        ]
    )

    assert report.success is False
    assert "未找到表头全选 checkbox" in report.errors[0]


def test_workflow_executor_rejects_zero_based_row_number(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=FakeRuntime(sample_runtime_elements),
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "table_row_selection", "operation": "select", "target": {"row_number": 0}},
        ]
    )

    assert report.success is False
    assert "表格行号从 1 开始" in report.errors[0]


def test_workflow_executor_stops_when_menu_tab_validation_fails(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=FakeRuntime(sample_runtime_elements, should_validate=False),
    )

    report = executor.run([{"action": "open_menu", "menu_path": "项目管理>>项目立项"}])

    assert report.success is False
    assert "菜单页签校验失败" in report.errors[0]
    assert report.binding is None


def test_workflow_executor_reports_tree_error_with_component_context(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=FakeRuntime(sample_runtime_elements, should_find_tree=False),
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "tree", "operation": "select", "target": {"label": "001 办公室"}},
        ]
    )

    assert report.success is False
    assert "未找到树节点" in report.errors[0]


def test_workflow_executor_reports_row_match_error_with_component_context(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=FakeRuntime(sample_runtime_elements, should_find_row=False),
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table_row_action",
                "operation": "click",
                "target": {
                    "action": "详情",
                    "match": {"column": "项目代码", "equals": "360000241010010000039"},
                },
            },
        ]
    )

    assert report.success is False
    assert "未找到表格行" in report.errors[0]


def test_workflow_executor_reports_missing_row_action_binding(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["actionEL"].pop("detail")
    runtime = FakeRuntime(sample_runtime_elements)
    runtime.click_row_action = None
    executor = WorkflowExecutor(
        gateway=FakeGateway(template_payload),
        runtime=runtime,
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table_row_action",
                "operation": "click",
                "target": {
                    "action": "详情",
                    "match": {"column": "项目代码", "equals": "360000241010010000039"},
                },
            },
        ]
    )

    assert report.success is False
    assert "未绑定表格行动作" in report.errors[0]


def test_workflow_executor_allows_table_action_bar_row_hover_action(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    main_table = template_payload["data"]["uidata"][0]["children"][-1]
    main_table["children"].append(
        {
            "key": "summary_rule_toolbar",
            "divCode": "summary_rule_toolbar",
            "nodeType": "toolbar",
            "label": "按钮工具栏",
            "parentKey": "main_table",
            "children": [
                {
                    "key": "summary_rule_btn",
                    "divCode": "summary_rule_btn",
                    "nodeType": "leafItem",
                    "label": "汇总规则",
                    "name": "YDFButton",
                    "actions": {
                        "onClick": [
                            {
                                "actionType": "table",
                                "key": "summaryRule",
                                "label": "汇总规则",
                            }
                        ]
                    },
                }
            ],
        }
    )
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(
        gateway=FakeGateway(template_payload),
        runtime=runtime,
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table_row_action",
                "operation": "click",
                "target": {"action": "汇总规则", "row_number": 1},
            },
        ]
    )

    assert report.success is True
    assert runtime.focused_rows[0]["row_number"] == 1
    assert runtime.row_action_clicks == ["汇总规则"]


def test_workflow_executor_uses_runtime_row_action_click_without_binding(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["actionEL"].pop("detail")
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(
        gateway=FakeGateway(template_payload),
        runtime=runtime,
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "table_row_action",
                "operation": "click",
                "target": {
                    "action": "详情",
                    "match": {"column": "项目代码", "equals": "360000241010010000039"},
                },
            },
        ]
    )

    assert report.success is True
    assert runtime.row_action_clicks == ["详情"]


def test_toolbar_click_uses_first_action_completion_signal(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    runtime.action_completion_observations = [
        ActionCompletionObservation(
            notifications=(ActionNotification(type="success", message="保存成功"),)
        )
    ]

    def fail_legacy_collection() -> list[dict[str, str]]:
        raise AssertionError("动作完成信号出现后不应再串行收集页面提示")

    runtime.collect_notifications = fail_legacy_collection  # type: ignore[method-assign]
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
        ]
    )

    assert report.success is True
    assert runtime.action_completion_events == [
        {
            "event": "prepare",
            "action": "toolbar.click",
            "context": {"source_page_id": "root", "action": "保存", "sub_label": ""},
        },
        {"event": "observe", "action": "toolbar.click", "stage": "notifications"},
    ]
    assert report.steps[-1].data["completion_signal"] == "notification"
    assert report.steps[-1].data["wait_duration_ms"] == 0
    assert report.steps[-1].data["fallback_used"] is False
    assert report.steps[-1].data["notifications"] == [{"type": "success", "message": "保存成功"}]


def test_dialog_click_records_compatibility_fallback(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    runtime.action_completion_default = ActionCompletionObservation()
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "dialog", "operation": "confirm", "target": {"label": "确定"}},
        ]
    )

    assert report.success is True
    assert report.steps[-1].data["completion_signal"] == "compatibility_timeout"
    assert report.steps[-1].data["wait_duration_ms"] == 24000
    assert report.steps[-1].data["fallback_used"] is True


def test_import_upload_keeps_specialized_completion_protocol(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {
                "component": "import",
                "operation": "upload",
                "target": {"file": "/tmp/payee.xlsx"},
            },
        ]
    )

    assert report.success is True
    assert report.steps[-1].data["import_results"] == [
        {"file": "/tmp/payee.xlsx", "status": "success", "message": "导入完成"}
    ]
    assert runtime.action_completion_events == []


def test_toolbar_download_keeps_specialized_completion_protocol(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    template_payload = deepcopy(sample_template_payload)
    template_payload["data"]["actionEL"]["export"] = {
        "key": "export_btn",
        "divCode": "dc_btn",
        "nodeType": "leafItem",
        "label": "导出",
        "name": "Button",
        "rightflag": "export",
        "parentKeys": ["root", "toolbar_root"],
    }
    runtime = FakeRuntime(sample_runtime_elements)
    runtime.downloaded_files = []  # type: ignore[attr-defined]
    original_click = runtime.click_toolbar_action

    def click_toolbar_action(
        label: str,
        sub_label: str | None = None,
        fieldid: str | None = None,
        aliases: list[str] | None = None,
    ) -> None:
        original_click(label, sub_label=sub_label, fieldid=fieldid, aliases=aliases)
        runtime.downloaded_files.append("/tmp/export.xlsx")  # type: ignore[attr-defined]

    def fail_generic_observation(*_args: Any, **_kwargs: Any) -> ActionCompletionObservation:
        raise AssertionError("工具栏下载应保持专用完成协议")

    runtime.click_toolbar_action = click_toolbar_action  # type: ignore[method-assign]
    runtime._observe_action_completion = fail_generic_observation  # type: ignore[method-assign]
    executor = WorkflowExecutor(gateway=FakeGateway(template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "导出"}},
        ]
    )

    assert report.success is True
    assert report.steps[-1].data["downloaded_files"] == ["/tmp/export.xlsx"]


def test_executor_records_lightweight_step_and_open_menu_phase_timing(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = PageResponseOpenMenuRuntime(
        sample_runtime_elements,
        initial_template_payload=sample_template_payload,
        surface_snapshots=[
            [_surface("main", "main_table", busy=1, signature="loading")],
            [_surface("main", "main_table", terminal=True, signature="row:1")],
        ],
    )
    executor = _browser_executor(FakeGateway(sample_template_payload), runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "query", "operation": "search", "target": {"conditions": []}},
        ]
    )

    assert report.success is True
    assert isinstance(report.steps[0].data["timing"]["duration_ms"], int)
    assert set(report.steps[0].data["timing"]["phases"]) == {
        "resolve_menu_ms",
        "browser_open_ms",
        "menu_ready_ms",
        "initial_template_wait_ms",
        "build_manifest_ms",
        "initial_work_surface_wait_ms",
        "binding_ms",
    }
    assert isinstance(report.steps[1].data["timing"]["duration_ms"], int)
    assert "performance" not in report.steps[0].data


def test_executor_records_lightweight_timing_for_failed_step(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    runtime = FakeRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime)

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "不存在"}},
        ]
    )

    assert report.success is False
    assert isinstance(report.steps[-1].data["timing"]["duration_ms"], int)
    assert report.steps[-1].data["error"]["type"] == "RuntimeError"


def test_first_open_menu_reports_resolution_failure_on_that_step(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    class MissingMenuGateway(FakeGateway):
        def resolve_menu(self, menu_path: str) -> MenuTarget:
            raise RuntimeError(f"菜单路径不存在: {menu_path}")

    executor = WorkflowExecutor(
        gateway=MissingMenuGateway(sample_template_payload),
        runtime=FakeRuntime(sample_runtime_elements),
    )

    report = executor.run(
        [{"action": "open_menu", "menu_path": "项目管理>>不存在"}]
    )

    assert report.success is False
    assert report.steps[-1].action == "open_menu"
    assert report.steps[-1].data["step_index"] == 1
    assert report.steps[-1].data["error"] == {
        "type": "RuntimeError",
        "message": "菜单路径不存在: 项目管理>>不存在",
    }


def _workflow_result_snapshot(*, total: int = 2, succeeded: int = 1, failed: int = 1) -> dict[str, Any]:
    return {
        "status": "observed",
        "frame_index": 0,
        "selector": '[data-ydf-browser-workflow-result="result-1"]',
        "semantics": {"message": "提交请求已执行完毕，部分失败！", "title": "批量审核结果"},
        "counts": {"total": total, "succeeded": succeeded, "failed": failed},
        "actions": {"confirm": "确认", "details": "查看详情"},
    }


@pytest.mark.parametrize("error_notification", [False, True])
def test_workflow_executor_executes_workflow_panel_and_preserves_notification_rules(
    sample_template_payload, sample_runtime_elements, tmp_path, error_notification,
) -> None:
    class PanelRuntime(FakeRuntime):
        def click_workflow_panel_action(self, label):
            self.clicked_targets.append(label)
            if error_notification:
                self.notifications = [{"type": "error", "message": "任务已被处理"}]
            return {"status": "ready", "frame_index": 0, "action": {"label": label}}

    runtime = PanelRuntime(sample_runtime_elements)
    observation = ObservationSession(tmp_path / "events.jsonl", tool_version="0.1.41", run_id="panel",
                                     configuration={"ai_observe": True})
    executor = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime,
                                observation_session=observation)
    report = executor.run([
        {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
        {"component": "workflow_panel", "operation": "click", "target": {"label": "撤回审批"}},
    ])
    assert report.success is (not error_notification)
    step = report.steps[-1]
    assert step.data["workflow_panel"]["action"]["label"] == "撤回审批"
    assert runtime.clicked_targets == ["撤回审批"]
    assert step.data["fallback_used"] is False
    if error_notification:
        assert step.data["notifications"] == [{"type": "error", "message": "任务已被处理"}]
    assert "workflow_panel" in observation.capabilities()["enabled"]


def test_workflow_executor_keeps_panel_evidence_when_completion_times_out(
    sample_template_payload, sample_runtime_elements, tmp_path,
) -> None:
    class PanelRuntime(FakeRuntime):
        def click_workflow_panel_action(self, label):
            return {"status": "ready", "action": {"label": label, "checked": True}}

    runtime = PanelRuntime(sample_runtime_elements)
    runtime.action_completion_default = ActionCompletionObservation()
    observation = ObservationSession(tmp_path / "events.jsonl", tool_version="test", run_id="panel-timeout",
                                     configuration={"ai_observe": True})
    report = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime,
                              observation_session=observation).run([
        {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
        {"component": "workflow_panel", "operation": "click", "target": {"label": "撤回审批"}},
    ])
    assert report.success is False
    assert report.steps[-1].data["workflow_panel"]["action"]["checked"] is True
    assert "完成信号" in report.errors[-1]
    assert report.steps[-1].observation["reason_code"] == "evidence_unavailable"


@pytest.mark.parametrize("status,reason", [("action_missing", "target_unavailable"),
                                          ("evidence_unavailable", "evidence_unavailable")])
def test_workflow_panel_failure_classification_keeps_runtime_evidence(
    sample_template_payload, sample_runtime_elements, tmp_path, status, reason,
) -> None:
    class PanelRuntime(FakeRuntime):
        def click_workflow_panel_action(self, label):
            error = RuntimeError("工作流操作面板动作不可用")
            error.data = {"workflow_panel": {"status": status, "actions": []}}
            raise error

    observation = ObservationSession(tmp_path / "events.jsonl", tool_version="test", run_id="panel-failure",
                                     configuration={"ai_observe": True})
    report = WorkflowExecutor(gateway=FakeGateway(sample_template_payload),
                              runtime=PanelRuntime(sample_runtime_elements), observation_session=observation).run([
        {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
        {"component": "workflow_panel", "operation": "click", "target": {"label": "撤回审批"}},
    ])
    assert report.success is False
    assert report.steps[-1].observation["reason_code"] == reason
    assert report.steps[-1].data["workflow_panel"]["status"] == status


@pytest.mark.parametrize("next_step", ["notification", "workflow_result"])
def test_workflow_panel_reuses_explicit_negative_assertion_and_result_layer_guard(
    sample_template_payload, sample_runtime_elements, next_step,
) -> None:
    class PanelRuntime(FakeRuntime):
        clicked = False

        def click_workflow_panel_action(self, label):
            self.clicked = True
            if next_step == "notification":
                self.notifications = [{"type": "error", "message": "任务已被处理"}]
            return {"action": {"label": label}}

        def observe_workflow_result(self, timeout_ms=0):
            return _workflow_result_snapshot() if self.clicked and next_step == "workflow_result" else None

    steps = [
        {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
        {"component": "workflow_panel", "operation": "click", "target": {"label": "撤回审批"}},
    ]
    if next_step == "notification":
        steps.append({"component": "notification", "operation": "assert",
                      "target": {"type": "error", "contains": "任务已被处理"}})
    report = WorkflowExecutor(gateway=FakeGateway(sample_template_payload),
                              runtime=PanelRuntime(sample_runtime_elements)).run(steps)
    assert report.success is (next_step == "notification")
    if next_step == "workflow_result":
        assert report.steps[-1].data["workflow_result"]["counts"]["failed"] == 1
        assert "workflow_result.assert" in report.errors[-1]


def test_workflow_panel_applies_pending_dynamic_template(
    sample_template_payload, sample_runtime_elements,
) -> None:
    payload = deepcopy(sample_template_payload)
    payload["data"]["uidata"][0]["divCode"] = "panelResultRoot"

    class PanelRuntime(FakeRuntime):
        def click_workflow_panel_action(self, label):
            self.next_dynamic_template_payload = payload
            return {"action": {"label": label}}

    runtime = PanelRuntime(sample_runtime_elements)
    report = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime).run([
        {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
        {"component": "workflow_panel", "operation": "click", "target": {"label": "撤回审批"}},
    ])
    assert report.success is True
    assert report.steps[-1].data["dynamic_template"]["page"] == "panelResultRoot"
    assert runtime.prepared_manifest_keys[-1] == "panelResultRoot"
    assert runtime.next_dynamic_template_payload is None


def test_workflow_executor_asserts_workflow_result_counts_and_keeps_evidence(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
    tmp_path: Path,
) -> None:
    class WorkflowRuntime(FakeRuntime):
        def observe_workflow_result(self, timeout_ms: int = 0) -> dict[str, Any]:
            return _workflow_result_snapshot()

    observation = ObservationSession(
        tmp_path / "events.jsonl",
        tool_version="0.1.19",
        run_id="run-workflow-result",
        configuration={"ai_observe": True},
    )
    observation.write("run_started", {})
    runtime = WorkflowRuntime(sample_runtime_elements)
    executor = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=runtime,
        observation_session=observation,
    )

    report = executor.run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
            {
                "component": "workflow_result",
                "operation": "assert",
                "target": {"total": 2, "succeeded": 1, "failed": 1},
            },
        ]
    )

    assert report.success is True
    result = report.steps[2]
    assert result.data["workflow_result"]["counts"] == {"total": 2, "succeeded": 1, "failed": 1}
    assert result.observation["assertion_receipt"]["expected"] == {
        "total": 2,
        "succeeded": 1,
        "failed": 1,
    }
    assert result.observation["assertion_receipt"]["actual"]["counts"] == {
        "total": 2,
        "succeeded": 1,
        "failed": 1,
    }
    events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert "workflow_result" in events[0]["capabilities"]["available"]
    assert "workflow_result" not in events[0]["capabilities"]["enabled"]
    workflow_events = [item for item in events if item.get("business_target", {}).get("component") == "workflow_result"]
    assert workflow_events
    assert "workflow_result" in workflow_events[-1]["capabilities"]["enabled"]


def test_workflow_executor_stops_on_workflow_result_count_mismatch(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
    tmp_path: Path,
) -> None:
    class WorkflowRuntime(FakeRuntime):
        def observe_workflow_result(self, timeout_ms: int = 0) -> dict[str, Any]:
            return _workflow_result_snapshot()

    observation = ObservationSession(
        tmp_path / "events.jsonl",
        tool_version="0.1.19",
        run_id="run-workflow-mismatch",
        configuration={"ai_observe": True},
    )
    observation.write("run_started", {})
    report = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=WorkflowRuntime(sample_runtime_elements),
        observation_session=observation,
    ).run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
            {
                "component": "workflow_result",
                "operation": "assert",
                "target": {"failed": 0},
            },
            {"component": "workflow_result", "operation": "confirm", "target": {}},
        ]
    )

    assert report.success is False
    assert len(report.steps) == 3
    failed = report.steps[2]
    assert failed.data["error"]["type"] == "BusinessAssertionMismatch"
    assert failed.data["workflow_result"]["counts"]["failed"] == 1
    evidence_path = tmp_path / failed.data["failure_evidence_bundle"]["path"]
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["workflow_result"]["counts"]["failed"] == 1
    assert "业务断言不符合" in report.errors[0]


def test_workflow_executor_blocks_unhandled_workflow_result_after_click(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    class WorkflowRuntime(FakeRuntime):
        def observe_workflow_result(self, timeout_ms: int = 0) -> dict[str, Any]:
            return _workflow_result_snapshot()

    report = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=WorkflowRuntime(sample_runtime_elements),
    ).run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
            {"component": "tab", "operation": "click", "target": {"label": "全部"}},
        ]
    )

    assert report.success is False
    assert len(report.steps) == 2
    assert report.steps[1].success is False
    assert "workflow_result.assert" in report.errors[0]
    assert report.steps[1].data["workflow_result"]["counts"]["total"] == 2


@pytest.mark.parametrize(
    ("snapshot", "reason_code"),
    [
        (None, "target_unavailable"),
        ({"status": "evidence_unavailable", "reason": "统计字段无法解析"}, "evidence_unavailable"),
    ],
)
def test_workflow_executor_classifies_workflow_result_observation_failure(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
    tmp_path: Path,
    snapshot: dict[str, Any] | None,
    reason_code: str,
) -> None:
    class WorkflowRuntime(FakeRuntime):
        def observe_workflow_result(self, timeout_ms: int = 0) -> dict[str, Any] | None:
            return snapshot

    observation = ObservationSession(
        tmp_path / f"events-{reason_code}.jsonl",
        tool_version="0.1.19",
        run_id=f"run-{reason_code}",
        configuration={"ai_observe": True},
    )
    report = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=WorkflowRuntime(sample_runtime_elements),
        observation_session=observation,
    ).run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
            {"component": "workflow_result", "operation": "assert", "target": {"failed": 1}},
        ]
    )

    assert report.success is False
    failed = report.steps[-1]
    assert failed.observation["reason_code"] == reason_code
    assert failed.data["observation_failure"]["reason_code"] == reason_code


def test_workflow_executor_collects_details_and_closes_result_in_layers(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    class WorkflowRuntime(FakeRuntime):
        workflow_result_visible = True

        def __init__(self, runtime_elements: list[dict]) -> None:
            super().__init__(runtime_elements)
            self.details_calls: list[dict[str, Any]] = []
            self.confirm_calls: list[dict[str, Any]] = []

        def observe_workflow_result(self, timeout_ms: int = 0) -> dict[str, Any] | None:
            return _workflow_result_snapshot() if self.workflow_result_visible else None

        def open_workflow_result_details(self, label: str = "查看详情", timeout_ms: int = 0) -> dict[str, Any]:
            self.details_calls.append({"label": label, "timeout_ms": timeout_ms})
            return {
                "details": [
                    {"document_code": "CGJH-001", "error_reason": "预算不足", "error_code": "BUDGET-001"}
                ]
            }

        def confirm_workflow_result(self, label: str = "确认", timeout_ms: int = 0) -> dict[str, Any]:
            self.confirm_calls.append({"label": label, "timeout_ms": timeout_ms})
            self.workflow_result_visible = False
            return {"closed": True}

    runtime = WorkflowRuntime(sample_runtime_elements)
    report = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=runtime,
    ).run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
            {"component": "workflow_result", "operation": "assert", "target": {"failed": 1}},
            {"component": "workflow_result", "operation": "details", "target": {}},
            {"component": "dialog", "operation": "confirm", "target": {"label": "确定"}},
            {"component": "workflow_result", "operation": "confirm", "target": {}},
        ]
    )

    assert report.success is True
    assert report.steps[3].data["workflow_result"]["details"] == [
        {"document_code": "CGJH-001", "error_reason": "预算不足", "error_code": "BUDGET-001"}
    ]
    assert runtime.dialog_clicks == [{"label": "确定", "expect_download": False}]
    assert runtime.confirm_calls[0]["label"] == "确认"


def test_workflow_executor_rejects_workflow_result_details_without_assertion(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    class WorkflowRuntime(FakeRuntime):
        def open_workflow_result_details(self, label: str = "查看详情", timeout_ms: int = 0) -> dict[str, Any]:
            raise AssertionError("详情操作不应越过断言")

    report = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=WorkflowRuntime(sample_runtime_elements),
    ).run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "workflow_result", "operation": "details", "target": {}},
        ]
    )

    assert report.success is False
    assert "尚未完成断言前置条件" in report.errors[0]


def test_workflow_executor_fails_when_workflow_result_confirm_does_not_close(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    class WorkflowRuntime(FakeRuntime):
        def observe_workflow_result(self, timeout_ms: int = 0) -> dict[str, Any]:
            return _workflow_result_snapshot()

        def confirm_workflow_result(self, label: str = "确认", timeout_ms: int = 0) -> dict[str, Any]:
            return {"closed": False}

    report = WorkflowExecutor(
        gateway=FakeGateway(sample_template_payload),
        runtime=WorkflowRuntime(sample_runtime_elements),
    ).run(
        [
            {"action": "open_menu", "menu_path": "项目管理>>项目立项"},
            {"component": "toolbar", "operation": "click", "target": {"label": "保存"}},
            {"component": "workflow_result", "operation": "assert", "target": {"failed": 1}},
            {"component": "workflow_result", "operation": "confirm", "target": {}},
        ]
    )

    assert report.success is False
    assert "仍可见" in report.errors[0]


@pytest.mark.parametrize('enabled,exploration_error', [(False, False), (True, False), (True, True)])
def test_reference_exploration_runs_only_after_business_steps(tmp_path, sample_template_payload, sample_runtime_elements, enabled, exploration_error):
    runtime = FakeRuntime(sample_runtime_elements)
    calls = []
    def explore(target):
        assert runtime.opened_menu is not None
        calls.append(target)
        if exploration_error:
            raise RuntimeError('没有打开参照')
        return {'candidates': [{'text': '实际末级'}], 'complete': False}
    runtime.explore_popup_reference = explore
    session = ObservationSession(tmp_path / 'events.jsonl', tool_version='test', run_id='test',
        configuration={'reference_exploration': {'title': '参照'}} if enabled else {})
    report = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime,
        observation_session=session).run([{'action': 'open_menu', 'menu_path': '项目管理>>项目立项'}])
    assert report.success and len(report.steps) == 1
    if enabled:
        assert calls == [{'title': '参照'}]
        assert report.steps[0].data['reference_exploration']['outcome'] == ('failed' if exploration_error else 'completed')
    else:
        assert not calls and 'reference_exploration' not in report.steps[0].data


def test_reference_exploration_skips_failed_business_case(tmp_path, sample_template_payload, sample_runtime_elements):
    runtime = FakeRuntime(sample_runtime_elements)
    runtime.explore_popup_reference = lambda target: pytest.fail('must not explore a failed case')
    def fail_open(*args, **kwargs):
        raise RuntimeError('导航失败')
    runtime.open_menu = fail_open
    session = ObservationSession(tmp_path / 'events.jsonl', tool_version='test', run_id='test', configuration={'reference_exploration': {}})
    report = WorkflowExecutor(gateway=FakeGateway(sample_template_payload), runtime=runtime,
        observation_session=session).run([{'action': 'open_menu', 'menu_path': '项目管理>>项目立项'}])
    assert not report.success
    assert report.steps[-1].data['reference_exploration']['outcome'] == 'skipped'
