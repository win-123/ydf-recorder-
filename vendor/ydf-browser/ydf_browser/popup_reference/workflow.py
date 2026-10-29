from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Callable
from typing import Any

from ..platform_rendering_contract import build_contract_path
from .discovery import DiscoveryStage
from .completion import CompletionStage
from .evidence import EvidenceStage
from .model import (
    BoundReferenceSource,
    OpenReferenceSource,
    PopupReferenceCompletion,
    PopupReferenceError,
    PopupReferenceRequest,
    PopupReferenceResult,
    PopupReferenceStage,
    ReferenceOwnerIdentity,
)
from .origin import OriginStage
from .selection import (
    SelectionStage,
    _bound_element_has_verified_form_identity,
    _editable_table_value_has_structured_popup_reference_target,
    _is_scalar_reference_value,
    _normalize_popup_reference_target,
    _popup_reference_filter_conditions,
    _popup_reference_filter_text,
    _popup_reference_explicit_filter_text,
    _popup_reference_has_explicit_filter,
    _popup_reference_implicit_value_filter_text,
    _popup_reference_row_numbers,
    _popup_reference_selection_targets,
    _popup_reference_target_match,
    _popup_reference_text_matches,
    _popup_reference_target_table,
    _popup_reference_tree_targets,
    _wants_first_available,
)
from .surface import SurfaceStage


class PopupReference(DiscoveryStage, OriginStage, SurfaceStage, SelectionStage, CompletionStage, EvidenceStage):
    """Execute complete popup-reference workflows behind one public operation."""

    def __init__(
        self,
        *,
        page: Callable[[], Any],
        select_choice: Callable[..., Any],
        resolve_visible_locator: Callable[[str], Any] | None = None,
        resolve_fill_locator: Callable[[str], Any] | None = None,
        diagnostic_files: list[str] | None = None,
        observation_session: Any | None = None,
        notifications: Callable[[], list[dict[str, str]]] | None = None,
        begin_notifications: Callable[[], None] | None = None,
        network_events: Callable[[], list[dict[str, Any]]] | None = None,
        console_events: Callable[[], list[dict[str, Any]]] | None = None,
        page_errors: Callable[[], list[dict[str, Any]]] | None = None,
    ) -> None:
        self._page_provider = page
        self._select_choice = select_choice
        self._visible_locator_resolver = resolve_visible_locator
        self._fill_locator_resolver = resolve_fill_locator
        self.diagnostic_files = diagnostic_files if diagnostic_files is not None else []
        self.observation_session = observation_session
        self._notifications = notifications or (lambda: [])
        self._begin_notifications = begin_notifications or (lambda: None)
        self._selection_target: object = None
        self._selection_identity: dict[str, Any] = {}
        self._network_events_provider = network_events or (lambda: [])
        self._console_events_provider = console_events or (lambda: [])
        self._page_errors_provider = page_errors or (lambda: [])
        self._network_events: list[dict[str, Any]] = []
        self._console_events: list[dict[str, Any]] = []
        self._page_errors: list[dict[str, Any]] = []
        self._request_diagnostic_refs: list[str] = []
        self._result_data: dict[str, Any] | None = None
        self._request_deadline: float | None = None
        self._cancelled: Callable[[], bool] | None = None
        self._current_stage = PopupReferenceStage.RECOGNIZE_ORIGIN
        self._popup_reference_source_contract_verified = False
        self._last_popup_reference_open_debug: dict[str, Any] | None = None
        self._last_popup_reference_first_candidate: dict[str, Any] | None = None
        self._last_popup_reference_first_candidate_error = ""
        self._last_popup_reference_first_candidate_saw_table = False

    def select(self, request: PopupReferenceRequest) -> PopupReferenceResult:
        """Select and complete a popup reference according to its source policy."""

        self._request_deadline = request.deadline
        self._cancelled = request.cancelled
        self._request_diagnostic_refs = []
        self._current_stage = PopupReferenceStage.RECOGNIZE_ORIGIN
        self._network_events = list(self._network_events_provider())
        self._console_events = list(self._console_events_provider())
        self._page_errors = list(self._page_errors_provider())
        self._check_cancelled()
        try:
            self._selection_target = request.target
            self._selection_identity = {"title": request.title} if isinstance(request.source, OpenReferenceSource) else {
                "field": request.source.identity.label, "fieldid": request.source.identity.fieldid,
            }
            self._begin_notifications()
            if isinstance(request.source, OpenReferenceSource):
                self._current_stage = PopupReferenceStage.RESOLVE_SURFACE
                data = self._select_open_surface(
                    title=request.title,
                    target=dict(request.target) if isinstance(request.target, dict) else request.target,
                    confirm=request.confirm,
                )
            else:
                identity = request.source.identity
                self._current_stage = PopupReferenceStage.RESOLVE_OWNER
                root, owner_selector = self._resolve_owner(identity)
                try:
                    fill_locator = (
                        self._fill_locator_resolver(owner_selector)
                        if self._fill_locator_resolver is not None
                        else self._resolve_fill_locator_from_root(root)
                    )
                except Exception:
                    # A reference owner can itself be the clickable surface (not an input).
                    fill_locator = root
                self._popup_reference_source_contract_verified = identity.contract_verified
                self._result_data = None
                editable = request.source.kind == "editable_table"
                self._current_stage = PopupReferenceStage.OPEN_SURFACE
                if editable:
                    structured_target = _editable_table_value_has_structured_popup_reference_target(
                        request.target
                    )
                    self._select_bound_source(
                        root,
                        fill_locator,
                        request.target,
                        require_confirm_if_dialog_still_visible=True,
                        reuse_existing_dialog=structured_target,
                        origin_root=root if structured_target else None,
                    )
                else:
                    self._select_bound_source(root, fill_locator, request.target)
                data = self._result_data or {
                    "selected": [],
                    "confirmed": True,
                    "_suppress_report": True,
                }
            return self._result_from_runtime_dict(data, request)
        except PopupReferenceError:
            raise
        except Exception as exc:
            raise PopupReferenceError(
                str(exc),
                stage=self._current_stage,
                reason=self._failure_reason(self._current_stage),
                evidence=self._failure_evidence(request),
                diagnostic_refs=tuple(self._request_diagnostic_refs),
            ) from exc
        finally:
            self._request_deadline = None
            self._cancelled = None

    def _check_selection_rejection(self) -> None:
        notifications = [item for item in self._notifications()
                         if item.get("type") in {"error", "warning"}]
        if not notifications:
            return
        error = PopupReferenceError(
            "弹出参照选择被拒绝: " + "；".join(item.get("message", "") for item in notifications),
            stage=self._current_stage,
            reason="selection_rejected",
            evidence={"target": self._selection_target, "notifications": notifications},
        )
        error.data = {"notifications": notifications, "popup_reference": {
            "reason": "selection_rejected", "stage": self._current_stage.value,
            "target": self._selection_target, **self._selection_identity,
        }}
        raise error

    def looks_like_field(self, locator: Any, bound_element: Any) -> bool:
        return self._looks_like_popup_reference_field(locator, bound_element)

    def root_has_trigger(self, locator: Any) -> bool:
        return self._root_has_popup_reference_trigger(locator)

    def editable_cell_looks_like_reference(
        self,
        cell: Any,
        cell_selector: str,
        column_candidate: Any | None,
    ) -> bool:
        return self._editable_table_cell_looks_like_popup_reference(
            cell,
            cell_selector,
            column_candidate,
        )

    @staticmethod
    def is_scalar_target(value: object) -> bool:
        return _is_scalar_reference_value(value)

    @staticmethod
    def wants_first_available(value: object) -> bool:
        return _wants_first_available(value)

    @staticmethod
    def target_is_structured(value: object) -> bool:
        return _editable_table_value_has_structured_popup_reference_target(value)

    @staticmethod
    def target_has_explicit_selection(value: object) -> bool:
        if not isinstance(value, dict):
            return False
        if _popup_reference_target_match(value) or _wants_first_available(value):
            return True
        if _popup_reference_row_numbers(value):
            return True
        matches = value.get("matches")
        if isinstance(matches, list) and matches:
            return True
        selections = value.get("selections", value.get("selection"))
        return isinstance(selections, (dict, list)) and bool(selections)

    @staticmethod
    def value_matches(actual: object, expected: object) -> bool:
        return _popup_reference_text_matches(actual, expected)

    def _result_from_runtime_dict(
        self,
        data: dict[str, Any],
        request: PopupReferenceRequest,
    ) -> PopupReferenceResult:
        details = {
            key: value
            for key, value in data.items()
            if key
            not in {
                "selected",
                "confirmed",
                "confirm_label",
                "close_action",
                "root_backfilled",
                "dialog_hidden",
                "popup_tab_context",
                "popup_tree_context",
                "contract_path",
            }
        }
        completion: PopupReferenceCompletion
        if data.get("confirmed"):
            completion = "confirmed"
        elif isinstance(request.source, BoundReferenceSource) and request.source.kind == "editable_table":
            completion = "caller_verification_required"
        elif data.get("root_backfilled") and data.get("dialog_hidden"):
            completion = "auto_closed_backfilled"
        else:
            completion = "caller_verification_required"
        return PopupReferenceResult(
            selected=tuple(dict(item) for item in data.get("selected") or []),
            confirmed=bool(data.get("confirmed")),
            confirm_label=data.get("confirm_label"),
            close_action=data.get("close_action"),
            root_backfilled=data.get("root_backfilled"),
            dialog_hidden=data.get("dialog_hidden"),
            completion=completion,
            popup_tab_context=(
                tuple(dict(item) for item in data.get("popup_tab_context") or []) or None
            ),
            popup_tree_context=(
                tuple(dict(item) for item in data.get("popup_tree_context") or []) or None
            ),
            contract_path=data.get("contract_path"),
            diagnostic_refs=tuple(self._request_diagnostic_refs),
            details=details,
        )

    @staticmethod
    def _failure_reason(stage: PopupReferenceStage) -> str:
        return {
            PopupReferenceStage.RECOGNIZE_ORIGIN: "origin_not_applicable",
            PopupReferenceStage.RESOLVE_OWNER: "owner_unavailable",
            PopupReferenceStage.OPEN_SURFACE: "surface_open_failed",
            PopupReferenceStage.RESOLVE_SURFACE: "surface_unavailable",
            PopupReferenceStage.APPLY_CONTEXT: "context_application_failed",
            PopupReferenceStage.FILTER_CANDIDATES: "candidate_filter_failed",
            PopupReferenceStage.SELECT_CANDIDATE: "selection_failed",
            PopupReferenceStage.VERIFY_SELECTION: "selection_unverified",
            PopupReferenceStage.CONFIRM: "confirmation_failed",
            PopupReferenceStage.VERIFY_COMPLETION: "completion_unverified",
            PopupReferenceStage.WRITE_EVIDENCE: "evidence_write_failed",
        }[stage]

    def _failure_evidence(self, request: PopupReferenceRequest) -> dict[str, Any]:
        source = request.source
        evidence: dict[str, Any] = {"source_kind": source.kind, "target": request.target}
        if isinstance(source, BoundReferenceSource):
            evidence.update(
                {
                    "fieldid": source.identity.fieldid,
                    "label": source.identity.label,
                    "selector": source.identity.selector,
                }
            )
        return evidence

    def _check_cancelled(self) -> None:
        if self._cancelled is not None and self._cancelled():
            raise PopupReferenceError(
                "弹出参照选择已取消",
                stage=PopupReferenceStage.SELECT_CANDIDATE,
                reason="cancelled",
            )
        if self._request_deadline is not None and time.monotonic() >= self._request_deadline:
            raise PopupReferenceError(
                "弹出参照选择超时",
                stage=PopupReferenceStage.VERIFY_COMPLETION,
                reason="deadline_exceeded",
            )

    def _require_page(self):
        page = self._page_provider()
        if page is None:
            raise RuntimeError("浏览器运行时尚未启动")
        return page

    def _wait_for_timeout(self, timeout_ms: int) -> None:
        self._check_cancelled()
        effective_timeout_ms = max(0, int(timeout_ms))
        if self._request_deadline is not None:
            remaining_seconds = self._request_deadline - time.monotonic()
            if remaining_seconds <= 0:
                self._check_cancelled()
            remaining_ms = max(1, int(remaining_seconds * 1000))
            effective_timeout_ms = min(effective_timeout_ms, remaining_ms)
        self._require_page().wait_for_timeout(effective_timeout_ms)
        self._check_cancelled()

    def _all_search_contexts(self) -> list[Any]:
        page = self._require_page()
        return [page, *getattr(page, "frames", [])]

    def _resolve_visible_locator(self, selector: str):
        if self._visible_locator_resolver is not None:
            return self._visible_locator_resolver(selector)
        fallback = None
        for context in self._all_search_contexts():
            locator = context.locator(selector)
            try:
                count = locator.count()
            except Exception:
                if fallback is None:
                    fallback = getattr(locator, "first", None)
                continue
            if fallback is None and count:
                fallback = locator.first
            for index in range(count):
                candidate = locator.nth(index)
                try:
                    if candidate.is_visible(timeout=500):
                        return candidate
                except Exception:
                    continue
        if fallback is not None:
            return fallback
        return self._require_page().locator(selector).first

    def _resolve_owner(self, identity: ReferenceOwnerIdentity) -> tuple[Any, str]:
        selectors = tuple(
            selector
            for selector in (identity.selector, identity.fallback_selector)
            if selector
        )
        first_resolved: tuple[Any, str] | None = None
        last_error: Exception | None = None
        for selector in selectors:
            try:
                locator = self._resolve_visible_locator(selector)
            except Exception as exc:
                last_error = exc
                continue
            if first_resolved is None:
                first_resolved = (locator, selector)
            count = getattr(locator, "count", None)
            if not callable(count):
                return locator, selector
            try:
                if count() > 0:
                    return locator, selector
            except Exception:
                return locator, selector
        if last_error is not None:
            raise last_error
        if first_resolved is not None:
            return first_resolved
        raise RuntimeError(f"无法恢复弹出参照来源字段身份: {identity.fieldid or identity.label}")

    def _resolve_fill_locator_from_root(self, locator):
        input_locator = locator.locator("input,textarea,[contenteditable='true']").first
        try:
            if input_locator.count() > 0:
                return input_locator
        except Exception:
            pass
        return locator

    def _first_visible_child_locator(self, root, selectors: list[str]):
        for selector in selectors:
            locator = root.locator(selector)
            try:
                count = locator.count()
            except Exception:
                continue
            for index in range(count):
                candidate = locator.nth(index)
                try:
                    if candidate.is_visible(timeout=300):
                        return candidate
                except Exception:
                    continue
        return None

    def _safe_has_visible_choice_dropdown(self) -> bool:
        selectors = (
            ".w-select-dropdown",
            ".wui-select-dropdown",
            ".ant-select-dropdown",
            ".u-select-dropdown",
            '[role="listbox"]',
        )
        for context in self._all_search_contexts():
            for selector in selectors:
                try:
                    locator = context.locator(selector)
                    if any(locator.nth(index).is_visible(timeout=200) for index in range(locator.count())):
                        return True
                except Exception:
                    continue
        return False

    def _collect_choice_diagnostic_text(self) -> str:
        snippets: list[str] = []
        selectors = (
            ".w-select-dropdown",
            ".wui-select-dropdown",
            ".ant-select-dropdown",
            ".u-select-dropdown",
            '[class*="popup"]',
            '[class*="dropdown"]',
            '[class*="refer"]',
            '[class*="ref"]',
        )
        for context in self._all_search_contexts():
            for selector in selectors:
                try:
                    locator = context.locator(selector)
                    count = locator.count()
                except Exception:
                    continue
                for index in range(min(count, 3)):
                    item = locator.nth(index)
                    try:
                        if item.is_visible(timeout=200):
                            text = " ".join((item.inner_text(timeout=500) or "").split())
                            if text:
                                snippets.append(f"{selector}[{index}]={text[:500]}")
                    except Exception:
                        continue
        return " | ".join(snippets[:6]) or "无可见下拉/参照候选"

    def _select_query_choice(self, root, fill_locator, value: Any, **kwargs: Any):
        return self._select_choice(root, fill_locator, value, **kwargs)

    def _select_open_surface(
        self,
        *,
        title: str | None = None,
        target: object = None,
        confirm: bool = True,
    ) -> dict[str, Any]:
        self._check_cancelled()
        page = self._require_page()
        target = _normalize_popup_reference_target(target or {})
        source_contract_verified = bool(getattr(self, "_popup_reference_source_contract_verified", False))
        self._popup_reference_source_contract_verified = False
        self._current_stage = PopupReferenceStage.RESOLVE_SURFACE
        shell_dialog = self._resolve_current_popup_reference_shell(title)
        if title and not self._popup_reference_dialog_has_title(shell_dialog, title):
            diagnostic = self._collect_popup_reference_diagnostic_text(shell_dialog)
            raise RuntimeError(f"当前弹出参照标题不匹配: expected={title}, actual={diagnostic}")
        choice_root = self._resolve_current_popup_reference_choice_root(shell_dialog, title) or shell_dialog
        choice_root = self._wait_for_popup_reference_choice_root_ready(shell_dialog, choice_root)

        def click_target(selection_root, selection_target: dict[str, Any]) -> bool:
            if _wants_first_available(selection_target):
                return self._click_popup_reference_target(
                    selection_root,
                    selection_target,
                    shell_dialog=shell_dialog,
                )
            return self._click_popup_reference_target(selection_root, selection_target)

        self._current_stage = PopupReferenceStage.SELECT_CANDIDATE
        selection_targets = _popup_reference_selection_targets(_normalize_popup_reference_target(target))
        selected: list[dict[str, Any]] = []
        popup_tab_context: list[dict[str, Any]] = []
        popup_tree_context: list[dict[str, Any]] = []
        for selection_target in selection_targets:
            self._current_stage = PopupReferenceStage.APPLY_CONTEXT
            tab_context = self._apply_popup_reference_tab_context(choice_root, selection_target)
            if tab_context:
                popup_tab_context.extend(tab_context)
                choice_root = self._resolve_current_popup_reference_choice_root(shell_dialog, title) or choice_root
                choice_root = self._wait_for_popup_reference_choice_root_ready(shell_dialog, choice_root)
            tree_context = self._apply_popup_reference_tree_context(shell_dialog, selection_target)
            if tree_context:
                popup_tree_context.extend(tree_context)
                choice_root = self._resolve_current_popup_reference_choice_root(shell_dialog, title) or choice_root
                choice_root = self._wait_for_popup_reference_choice_root_ready(shell_dialog, choice_root)
            selection_root = self._resolve_popup_reference_selection_root(shell_dialog, choice_root, selection_target)
            self._current_stage = PopupReferenceStage.FILTER_CANDIDATES
            self._apply_current_popup_reference_filter(selection_root, selection_target)
            self._current_stage = PopupReferenceStage.SELECT_CANDIDATE

            def refresh_selection_root_after_filter_submit() -> None:
                nonlocal choice_root, selection_root
                choice_root = self._resolve_current_popup_reference_choice_root(shell_dialog, title) or choice_root
                choice_root = self._wait_for_popup_reference_choice_root_ready(shell_dialog, choice_root)
                selection_root = self._resolve_popup_reference_selection_root(shell_dialog, choice_root, selection_target)

            row_numbers = _popup_reference_row_numbers(selection_target)
            if row_numbers:
                for row_number in row_numbers:
                    if not self._click_popup_reference_table_row_by_index(selection_root, row_number):
                        diagnostic = self._collect_popup_reference_diagnostic_text(selection_root)
                        screenshot = self._save_diagnostic_screenshot("popup-reference-row-number-missing")
                        if screenshot:
                            diagnostic = f"{diagnostic} | screenshot={screenshot}"
                        raise RuntimeError(f"未找到弹出参照第 {row_number} 行: {diagnostic}")
                    selected_item = {
                        key: value
                        for key, value in selection_target.items()
                        if key not in {"row_number", "row_numbers", "row_index", "rows"}
                    }
                    selected_item["row_number"] = row_number
                    selected.append(selected_item)
            else:
                target_retry_attempted = False
                try:
                    target_clicked = click_target(selection_root, selection_target)
                except RuntimeError as exc:
                    if (
                        "filter" not in selection_target
                        and _popup_reference_implicit_value_filter_text(selection_target)
                        and "标量值匹配到" in str(exc)
                    ):
                        self._submit_popup_reference_filter(selection_root)
                        self._wait_for_timeout(800)
                        refresh_selection_root_after_filter_submit()
                        target_retry_attempted = True
                        target_clicked = click_target(selection_root, selection_target)
                    else:
                        raise
                if not target_clicked and not target_retry_attempted:
                    self._submit_popup_reference_filter(selection_root)
                    self._wait_for_timeout(800)
                    refresh_selection_root_after_filter_submit()
                    if not click_target(selection_root, selection_target):
                        diagnostic = self._collect_popup_reference_diagnostic_text(selection_root)
                        match = _popup_reference_target_match(selection_target)
                        if match:
                            table_debug = self._collect_popup_reference_table_match_debug(selection_root, match)
                            if table_debug:
                                diagnostic = f"{diagnostic} | row_debug={table_debug}"
                        screenshot = self._save_diagnostic_screenshot("popup-reference-choice-missing")
                        if screenshot:
                            diagnostic = f"{diagnostic} | screenshot={screenshot}"
                        raise RuntimeError(f"未找到弹出参照可选值: {selection_target}: {diagnostic}")
                selected.append(selection_target)
            self._wait_for_timeout(500)
            self._current_stage = PopupReferenceStage.VERIFY_SELECTION
            self._ensure_popup_reference_selected_control_checked(selection_root)
            choice_root = self._resolve_current_popup_reference_choice_root(shell_dialog, title) or shell_dialog
            choice_root = self._wait_for_popup_reference_choice_root_ready(shell_dialog, choice_root)
        confirmed = False
        if confirm:
            self._current_stage = PopupReferenceStage.CONFIRM
            if self._popup_reference_dialog_hidden_now(shell_dialog):
                self._wait_for_timeout(500)
                result = {"selected": selected, "confirmed": False, "closed_before_confirm": True}
                if popup_tab_context:
                    result["popup_tab_context"] = popup_tab_context
                if popup_tree_context:
                    result["popup_tree_context"] = popup_tree_context
                verified = bool(source_contract_verified and target.get("fieldid"))
                result["contract_path"] = build_contract_path(
                    "verified" if verified else "unverified",
                    ["PRS-POPUP-001", "PRS-POPUP-002"],
                    None if verified else "surface_variant_unverified",
                )
                return result
            confirm_label = str(target.get("confirm_label") or "").strip()
            if confirm_label:
                self._click_popup_reference_confirm_with_label(shell_dialog, confirm_label)
            else:
                self._click_popup_reference_confirm(shell_dialog)
            self._current_stage = PopupReferenceStage.VERIFY_COMPLETION
            if not self._wait_for_popup_reference_dialog_to_close(shell_dialog):
                diagnostic = self._collect_popup_reference_diagnostic_text(shell_dialog)
                screenshot = self._save_diagnostic_screenshot("popup-reference-dialog-still-open")
                if screenshot:
                    diagnostic = f"{diagnostic} | screenshot={screenshot}"
                raise RuntimeError(f"弹出参照选择框未关闭: {diagnostic}")
            confirmed = True
        self._wait_for_timeout(500)
        result = {"selected": selected, "confirmed": confirmed}
        if popup_tab_context:
            result["popup_tab_context"] = popup_tab_context
        if popup_tree_context:
            result["popup_tree_context"] = popup_tree_context
        result["contract_path"] = build_contract_path(
            "verified" if source_contract_verified and target.get("fieldid") and confirmed else "unverified",
            ["PRS-POPUP-001", "PRS-POPUP-002"],
            None if source_contract_verified and target.get("fieldid") and confirmed else "surface_variant_unverified",
        )
        return result

    def _select_bound_source(
        self,
        root,
        _fill_locator,
        value: Any,
        *,
        require_confirm_if_dialog_still_visible: bool = False,
        reuse_existing_dialog: bool = False,
        origin_root: Any | None = None,
    ) -> None:
        self._check_cancelled()
        page = self._require_page()

        self._last_popup_reference_debug = ""
        self._last_popup_reference_close_action = ""
        self._last_popup_reference_confirm_debug = ""
        self._last_popup_reference_confirm_label = ""
        self._last_popup_reference_first_candidate = None
        self._last_popup_reference_first_candidate_error = ""
        self._last_popup_reference_first_candidate_attempted = False
        self._result_data = None
        source_contract_verified = bool(getattr(self, "_popup_reference_source_contract_verified", False))
        self._popup_reference_source_contract_verified = False
        target = _normalize_popup_reference_target(value)
        selection_targets = _popup_reference_selection_targets(target)
        popup_tab_context: list[dict[str, Any]] = []
        popup_tree_context: list[dict[str, Any]] = []

        def record_result(
            *,
            confirmed: bool = False,
            root_backfilled: bool | None = None,
            dialog_hidden: bool | None = None,
        ) -> None:
            result: dict[str, Any] = {"selected": selection_targets, "confirmed": confirmed}
            if popup_tab_context:
                result["popup_tab_context"] = list(popup_tab_context)
            if popup_tree_context:
                result["popup_tree_context"] = list(popup_tree_context)
            close_action = str(getattr(self, "_last_popup_reference_close_action", "") or "").strip()
            if close_action:
                result["close_action"] = close_action
            if root_backfilled is not None:
                result["root_backfilled"] = root_backfilled
            if dialog_hidden is not None:
                result["dialog_hidden"] = dialog_hidden
            label = str(target.get("confirm_label") or getattr(self, "_last_popup_reference_confirm_label", "") or "").strip()
            if label:
                result["confirm_label"] = label
            first_candidate = getattr(self, "_last_popup_reference_first_candidate", None)
            if isinstance(first_candidate, dict):
                for key in (
                    "candidate_kind",
                    "candidate_source",
                    "candidate_text",
                    "candidate_requires_selection",
                    "candidate_selected",
                ):
                    if key in first_candidate:
                        result[key] = first_candidate[key]
            completed = confirmed or bool(root_backfilled) or bool(dialog_hidden)
            result["contract_path"] = build_contract_path(
                "verified" if source_contract_verified and completed else "unverified",
                ["PRS-POPUP-001", "PRS-POPUP-002"],
                None if source_contract_verified and completed else "surface_variant_unverified",
            )
            self._result_data = result

        initial_root_value = self._read_popup_reference_root_value(root)
        dialog = None
        existing_dialog_counts: dict[str, int] = {}
        existing_dialog_marker = ""
        if reuse_existing_dialog:
            existing_dialog_counts = self._visible_popup_reference_dialog_counts()
        if max(existing_dialog_counts.values(), default=0) > 0:
            try:
                candidate_dialog = self._resolve_popup_reference_dialog()
                if not self._popup_reference_dialog_contains_origin(candidate_dialog, origin_root):
                    dialog = candidate_dialog
            except RuntimeError:
                dialog = None
        if dialog is None:
            if not reuse_existing_dialog:
                existing_dialog_marker = self._mark_visible_popup_reference_dialogs()
            self._open_popup_reference_dialog(root)
            try:
                try:
                    dialog = self._resolve_popup_reference_dialog(
                        exclude_counts=existing_dialog_counts if reuse_existing_dialog else None,
                        exclude_marker=existing_dialog_marker or None,
                    )
                finally:
                    if existing_dialog_marker:
                        self._clear_popup_reference_dialog_marker(existing_dialog_marker)
            except RuntimeError:
                if _is_scalar_reference_value(value) and self._safe_has_visible_choice_dropdown():
                    self._select_query_choice(root, _fill_locator, value, root_already_active=True)
                    return
                raise
            if self._popup_reference_dialog_contains_origin(dialog, origin_root):
                dialog = self._wait_for_popup_reference_dialog_outside_origin(
                    origin_root,
                    exclude_counts=existing_dialog_counts,
                )
        self._current_stage = PopupReferenceStage.RESOLVE_SURFACE
        choice_root = self._resolve_current_popup_reference_choice_root(dialog) or dialog
        choice_root = self._wait_for_popup_reference_choice_root_ready(dialog, choice_root)

        def click_target(selection_root, selection_target: dict[str, Any]) -> bool:
            if _wants_first_available(selection_target):
                return self._click_popup_reference_target(
                    selection_root,
                    selection_target,
                    shell_dialog=dialog,
                )
            return self._click_popup_reference_target(selection_root, selection_target)

        self._current_stage = PopupReferenceStage.SELECT_CANDIDATE
        selection_debug: list[str] = []
        for index, selection_target in enumerate(selection_targets, start=1):
            self._current_stage = PopupReferenceStage.APPLY_CONTEXT
            tab_context = self._apply_popup_reference_tab_context(choice_root, selection_target)
            if tab_context:
                popup_tab_context.extend(tab_context)
                selection_debug.append(f"{index}:popup_tab_context={json.dumps(tab_context, ensure_ascii=False)}")
                choice_root = self._resolve_current_popup_reference_choice_root(dialog) or choice_root
                choice_root = self._wait_for_popup_reference_choice_root_ready(dialog, choice_root)
            tree_context = self._apply_popup_reference_tree_context(dialog, selection_target)
            if tree_context:
                popup_tree_context.extend(tree_context)
                selection_debug.append(f"{index}:popup_tree_context={json.dumps(tree_context, ensure_ascii=False)}")
                choice_root = self._resolve_current_popup_reference_choice_root(dialog) or choice_root
                choice_root = self._wait_for_popup_reference_choice_root_ready(dialog, choice_root)
            filter_text = _popup_reference_filter_text(selection_target)
            explicit_filter_text = _popup_reference_explicit_filter_text(selection_target)
            filter_conditions, filter_conditions_explicit = _popup_reference_filter_conditions(selection_target)
            row_numbers = _popup_reference_row_numbers(selection_target)
            match = _popup_reference_target_match(selection_target)
            has_explicit_filter = _popup_reference_has_explicit_filter(selection_target)
            selection_root = self._resolve_popup_reference_selection_root(dialog, choice_root, selection_target)
            self._current_stage = PopupReferenceStage.FILTER_CANDIDATES
            if (
                match
                and _popup_reference_tree_targets(selection_target)
                and not has_explicit_filter
                and not _popup_reference_target_table(selection_target)
            ):
                selection_root = dialog
            if (
                _wants_first_available(selection_target)
                and _popup_reference_tree_targets(selection_target)
                and not _popup_reference_target_table(selection_target)
            ):
                selection_root = dialog

            def refresh_selection_root_after_filter_submit() -> None:
                nonlocal choice_root, selection_root
                choice_root = self._resolve_current_popup_reference_choice_root(dialog) or choice_root
                choice_root = self._wait_for_popup_reference_choice_root_ready(dialog, choice_root)
                selection_root = self._resolve_popup_reference_selection_root(dialog, choice_root, selection_target)

            def return_if_backfilled_or_closed() -> bool:
                root_backfilled_now = self._popup_reference_root_backfilled(root, initial_root_value, selection_targets)
                dialog_hidden_now = self._popup_reference_dialog_hidden_now(dialog)
                if root_backfilled_now and dialog_hidden_now:
                    self._last_popup_reference_debug = " | ".join(selection_debug)
                    self._last_popup_reference_close_action = "target-backfill"
                    record_result(
                        confirmed=not require_confirm_if_dialog_still_visible,
                        root_backfilled=root_backfilled_now,
                        dialog_hidden=dialog_hidden_now,
                    )
                    return True
                if require_confirm_if_dialog_still_visible and dialog_hidden_now:
                    self._last_popup_reference_debug = " | ".join(selection_debug)
                    self._last_popup_reference_close_action = "target"
                    record_result(confirmed=False)
                    return True
                return False

            filter_was_applied = False
            filter_was_submitted = False
            target_retry_attempted = False
            target_clicked = False
            if has_explicit_filter:
                if filter_conditions:
                    try:
                        self._fill_popup_reference_filter_fields(selection_root, filter_conditions)
                        self._submit_popup_reference_filter(selection_root)
                        filter_was_applied = True
                        filter_was_submitted = True
                    except RuntimeError as exc:
                        if filter_conditions_explicit:
                            raise
                        if explicit_filter_text:
                            self._fill_popup_reference_filter(selection_root, explicit_filter_text)
                            self._submit_popup_reference_filter(selection_root)
                            filter_was_applied = True
                            filter_was_submitted = True
                elif explicit_filter_text:
                    self._fill_popup_reference_filter(selection_root, explicit_filter_text)
                    self._submit_popup_reference_filter(selection_root)
                    filter_was_applied = True
                    filter_was_submitted = True
                if filter_was_applied:
                    self._wait_for_timeout(800)
            elif match:
                self._current_stage = PopupReferenceStage.SELECT_CANDIDATE
                target_clicked = click_target(selection_root, selection_target)
            if not target_clicked:
                if not has_explicit_filter and not match and filter_conditions:
                    try:
                        self._fill_popup_reference_filter_fields(selection_root, filter_conditions)
                        self._submit_popup_reference_filter(selection_root)
                        filter_was_applied = True
                        filter_was_submitted = True
                    except RuntimeError as exc:
                        if filter_conditions_explicit:
                            raise
                        if filter_text:
                            self._fill_popup_reference_filter(selection_root, filter_text)
                            filter_was_applied = True
                    self._wait_for_timeout(800)
                elif not has_explicit_filter and not match and filter_text:
                    try:
                        self._fill_popup_reference_filter(selection_root, filter_text)
                        filter_was_applied = True
                    except RuntimeError as exc:
                        if "未找到弹出参照过滤框" not in str(exc):
                            raise
                    self._wait_for_timeout(800)
                self._current_stage = PopupReferenceStage.SELECT_CANDIDATE
                if row_numbers:
                    missing_row_number = None
                    for row_number in row_numbers:
                        if not self._click_popup_reference_table_row_by_index(selection_root, row_number):
                            missing_row_number = row_number
                            break
                    if missing_row_number is not None:
                        diagnostic = self._collect_popup_reference_diagnostic_text(selection_root)
                        screenshot = self._save_diagnostic_screenshot("popup-reference-row-number-missing")
                        if screenshot:
                            diagnostic = f"{diagnostic} | screenshot={screenshot}"
                        raise RuntimeError(f"未找到弹出参照第 {missing_row_number} 行: {diagnostic}")
                    target_clicked = True
                if not target_clicked:
                    try:
                        target_clicked = click_target(selection_root, selection_target)
                    except RuntimeError as exc:
                        if (
                            not filter_was_submitted
                            and filter_was_applied
                            and not has_explicit_filter
                            and _popup_reference_implicit_value_filter_text(selection_target)
                            and "标量值匹配到" in str(exc)
                        ):
                            self._submit_popup_reference_filter(selection_root)
                            filter_was_submitted = True
                            self._wait_for_timeout(800)
                            refresh_selection_root_after_filter_submit()
                            target_retry_attempted = True
                            target_clicked = click_target(selection_root, selection_target)
                        else:
                            raise
                if not target_clicked:
                    if return_if_backfilled_or_closed():
                        return
                    if filter_was_applied and not filter_was_submitted:
                        self._submit_popup_reference_filter(selection_root)
                        filter_was_submitted = True
                        self._wait_for_timeout(800)
                        refresh_selection_root_after_filter_submit()
                    if filter_was_submitted and not target_retry_attempted:
                        target_clicked = click_target(selection_root, selection_target)
                    if not target_clicked:
                        if return_if_backfilled_or_closed():
                            return
                        diagnostic = self._collect_popup_reference_diagnostic_text(selection_root)
                        if match:
                            table_debug = self._collect_popup_reference_table_match_debug(selection_root, match)
                            if table_debug:
                                diagnostic = f"{diagnostic} | row_debug={table_debug}"
                        first_available_debug = str(getattr(self, "_last_popup_reference_first_candidate_error", "") or "")
                        if (
                            _wants_first_available(selection_target)
                            or _popup_reference_implicit_value_filter_text(selection_target)
                        ) and first_available_debug:
                            debug_label = (
                                "first_available_debug"
                                if _wants_first_available(selection_target)
                                else "candidate_debug"
                            )
                            diagnostic = f"{diagnostic} | {debug_label}={first_available_debug}"
                        screenshot = self._save_diagnostic_screenshot("popup-reference-choice-missing")
                        if screenshot:
                            diagnostic = f"{diagnostic} | screenshot={screenshot}"
                        message = f"未找到弹出参照可选值: {filter_text}"
                        if match and not has_explicit_filter:
                            message = f"{message}（DSL 未写 filter，已按语义仅在当前可见结果中匹配，未执行过滤查询）"
                        raise RuntimeError(f"{message}: {diagnostic}")
            self._current_stage = PopupReferenceStage.VERIFY_SELECTION
            debug_enabled = bool(os.environ.get("YDF_BROWSER_DEBUG_POPUP_REFERENCE"))
            if debug_enabled:
                print("[ydf-browser] popup-reference-after-select stage=ensure", file=sys.stderr, flush=True)
            self._ensure_popup_reference_selected_control_checked(selection_root)
            if debug_enabled:
                print("[ydf-browser] popup-reference-after-select stage=selection-debug", file=sys.stderr, flush=True)
            current_debug = self._collect_popup_reference_selection_debug(selection_root)
            if current_debug:
                selection_debug.append(f"{index}:{current_debug}")
            if debug_enabled:
                print("[ydf-browser] popup-reference-after-select stage=root-backfill", file=sys.stderr, flush=True)
            root_backfilled = self._popup_reference_root_backfilled(root, initial_root_value, selection_targets)
            if debug_enabled:
                print(f"[ydf-browser] popup-reference-after-select stage=root-backfill value={root_backfilled}", file=sys.stderr, flush=True)
            if root_backfilled:
                if len(selection_targets) > 1 and index < len(selection_targets):
                    raise RuntimeError("多选弹出参照在选择全部目标前已回填并关闭")
                self._last_popup_reference_debug = " | ".join(selection_debug)
                if self._popup_reference_dialog_hidden_now(dialog):
                    self._last_popup_reference_close_action = "target-backfill"
                    record_result(
                        confirmed=not require_confirm_if_dialog_still_visible,
                        root_backfilled=root_backfilled,
                        dialog_hidden=True,
                    )
                    return
            elif self._popup_reference_dialog_hidden_now(dialog):
                if len(selection_targets) > 1 and index < len(selection_targets):
                    raise RuntimeError("多选弹出参照在选择全部目标前已关闭")
                self._last_popup_reference_debug = " | ".join(selection_debug)
                self._last_popup_reference_close_action = "target"
                record_result(confirmed=False, root_backfilled=root_backfilled, dialog_hidden=True)
                return
        self._last_popup_reference_debug = " | ".join(selection_debug) or self._collect_popup_reference_selection_debug(choice_root)
        confirm_label = str(target.get("confirm_label") or "").strip()

        def return_for_editable_backfill_check(exc: RuntimeError) -> bool:
            if require_confirm_if_dialog_still_visible and "未找到弹出参照确认按钮" in str(exc):
                self._last_popup_reference_close_action = "confirm-missing-backfill-check"
                record_result(confirmed=False)
                return True
            return False

        self._current_stage = PopupReferenceStage.CONFIRM
        try:
            if os.environ.get("YDF_BROWSER_DEBUG_POPUP_REFERENCE"):
                print("[ydf-browser] popup-reference-confirm stage=click", file=sys.stderr, flush=True)
            if confirm_label:
                self._click_popup_reference_confirm_with_label(dialog, confirm_label)
            else:
                self._click_popup_reference_confirm(dialog)
        except RuntimeError as exc:
            if return_for_editable_backfill_check(exc):
                return
            raise
        self._current_stage = PopupReferenceStage.VERIFY_COMPLETION
        if not self._wait_for_popup_reference_dialog_to_close(dialog):
            if self._activate_popup_reference_selected_item(dialog):
                if self._wait_for_popup_reference_dialog_to_close(dialog, timeout_ms=1500):
                    if not self._wait_for_popup_reference_root_backfill(root, initial_root_value, selection_targets):
                        diagnostic = self._collect_popup_reference_diagnostic_text(dialog)
                        screenshot = self._save_diagnostic_screenshot("popup-reference-backfill-missing")
                        if screenshot:
                            diagnostic = f"{diagnostic} | screenshot={screenshot}"
                        raise RuntimeError(f"弹出参照选择未回填到字段: {diagnostic}")
                    record_result(confirmed=True)
                    return
            diagnostic = self._collect_popup_reference_diagnostic_text(dialog)
            if "无可见下拉/参照候选" in diagnostic:
                self._last_popup_reference_close_action = "choice-surface-gone"
                record_result(confirmed=True)
                return
            try:
                if confirm_label:
                    self._click_popup_reference_confirm_with_label(dialog, confirm_label)
                else:
                    self._click_popup_reference_confirm(dialog)
            except RuntimeError as exc:
                if return_for_editable_backfill_check(exc):
                    return
                raise
            if not self._wait_for_popup_reference_dialog_to_close(dialog):
                diagnostic = self._collect_popup_reference_diagnostic_text(dialog)
                if "无可见下拉/参照候选" in diagnostic:
                    self._last_popup_reference_close_action = "choice-surface-gone"
                    record_result(confirmed=True)
                    return
                screenshot = self._save_diagnostic_screenshot("popup-reference-dialog-still-open")
                if screenshot:
                    diagnostic = f"{diagnostic} | screenshot={screenshot}"
                if self._close_popup_reference_dialog_if_visible(dialog):
                    diagnostic = f"{diagnostic} | 已清理关闭未确认的参照框"
                raise RuntimeError(f"弹出参照选择框未关闭: {diagnostic}")
        self._last_popup_reference_close_action = "confirm"
        if not self._wait_for_popup_reference_root_backfill(root, initial_root_value, selection_targets):
            if require_confirm_if_dialog_still_visible:
                self._last_popup_reference_close_action = "confirm-backfill-check"
                record_result(confirmed=True)
                return
            diagnostic = self._collect_popup_reference_diagnostic_text(dialog)
            screenshot = self._save_diagnostic_screenshot("popup-reference-backfill-missing")
            if screenshot:
                diagnostic = f"{diagnostic} | screenshot={screenshot}"
            raise RuntimeError(f"弹出参照选择未回填到字段: {diagnostic}")
        record_result(confirmed=True)
