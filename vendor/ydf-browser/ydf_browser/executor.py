from __future__ import annotations

import inspect
import random
import re
import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from .action_completion import ActionCompletion, ActionCompletionRequest, ActionCompletionResult
from .binder import bind_runtime_form_field, bind_runtime_readable_form_field
from .dsl import _is_business_assertion_step, normalize_step
from .menu_opening import MenuOpening, MenuOpeningError, MenuOpeningRequest
from .models import ActionStep, BindingResult, BoundElement, ExecutionReport, StepResult
from .observation import (
    DEFAULT_STEP_TIMEOUT_SECONDS,
    build_business_assertion_receipt,
    build_table_assertion_snapshot,
    classify_step_observation,
    redact_error_text,
    sanitize_evidence_payload,
)
from .platform_rendering_contract import build_contract_path, merge_contract_paths
from .runtime import _summarize_network_events
from .table_scope import ResolvedTableScope, RuntimeTableScopeAdapter, TableScopeError, TableScopeRequest, TableScopeResolver
from .template_restoration import RuntimeTemplateAdapter, TemplateRestoration
from .variables import FULL_VARIABLE_PATTERN, RuntimeVariableContext, VARIABLE_PATTERN


_STABLE_EDIT_ACTION_ALIASES = {"取消", "保存", "提交", "保存并提交", "暂存"}
_CLICK_ACTIONS_WITH_NOTIFICATIONS = {
    "workflow_panel.click",
    "toolbar.click",
    "action.click",
    "dialog.click",
    "tab.click",
    "table_row_action.click",
    "table.click_cell_link",
    "query.search",
}


class BusinessAssertionMismatch(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        expected: Any,
        actual: Any,
        scope: Any = None,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.data = {
            "assertion_comparison": {"expected": expected, "actual": actual, "scope": scope},
            **{key: value for key, value in dict(evidence or {}).items() if value is not None},
        }


class ContractPathError(RuntimeError):
    def __init__(self, message: str, contract_path: dict[str, Any]) -> None:
        super().__init__(message)
        self.data = {"contract_path": contract_path, "fallback_used": False}


class WorkflowResultObservationError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str, snapshot: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.data = {
            "workflow_result": dict(snapshot or {}),
            "observation_failure": {"reason_code": reason_code},
        }


class OpenMenuCompletionError(RuntimeError):
    def __init__(self, message: str, data: dict[str, Any]) -> None:
        super().__init__(message)
        self.data = data


class WorkflowExecutor:
    def __init__(
        self,
        gateway: Any,
        runtime: Any,
        progress_logger: Callable[[int, int, ActionStep], None] | None = None,
        performance_enabled: bool = False,
        runtime_variables: list[str] | set[str] | None = None,
        runtime_context: RuntimeVariableContext | None = None,
        observation_session: Any | None = None,
        cancellation_event: Any | None = None,
        menu_opening: MenuOpening | None = None,
    ) -> None:
        self.gateway = gateway
        self.runtime = runtime
        self._menu_opening = menu_opening or MenuOpening.for_fixture(gateway, runtime, now=time.monotonic)
        self._action_completion = ActionCompletion(runtime)
        self.progress_logger = progress_logger
        self.performance_enabled = performance_enabled
        self.current_menu = None
        self._templates = TemplateRestoration(
            RuntimeTemplateAdapter(runtime), on_action_notifications=self._remember_action_notifications,
        )
        self.current_page_supported = False
        self.current_template_error: dict[str, Any] | None = None
        self._field_property_uri_by_name: dict[str, str] = {}
        self._last_notifications: list[dict[str, str]] = []
        self._generated_values: dict[str, str] = {}
        self.runtime_variables = set(runtime_variables or [])
        self.runtime_context = runtime_context or RuntimeVariableContext()
        self.observation_session = observation_session
        self.cancellation_event = cancellation_event
        self._last_tree_select_debug: dict[str, Any] | None = None
        self._active_bpr_session: dict[str, Any] | None = None
        self._bpr_sessions: list[dict[str, Any]] = []
        self._current_step_index: int = 0
        self._current_step_deadline: float | None = None
        self._last_query_completion_signal: str | None = None
        self._workflow_result_snapshot: dict[str, Any] | None = None
        self._workflow_result_asserted = False
        self._used_components: set[str] = set()

    @property
    def current_manifest(self):
        return self._templates.manifest

    @property
    def current_binding(self) -> BindingResult | None:
        return self._templates.binding

    @property
    def current_page_state(self) -> dict[str, Any] | None:
        return self._templates.page_state

    def run(self, steps: list[ActionStep] | list[dict[str, Any]]) -> ExecutionReport:
        normalized = [step if isinstance(step, ActionStep) else normalize_step(step) for step in steps]
        report = ExecutionReport(success=True)
        self._active_bpr_session = None
        self._bpr_sessions = []
        self._workflow_result_snapshot = None
        self._workflow_result_asserted = False
        self._used_components = set()
        run_started = time.monotonic()
        for index, step in enumerate(normalized, start=1):
            diagnostic_start = len(getattr(self.runtime, "diagnostic_files", []) or [])
            step_started = time.monotonic()
            self._current_step_deadline = step_started + self._step_timeout_seconds()
            self._current_step_index = index
            self._begin_step_performance(index, step)
            if self.observation_session is not None:
                self.observation_session.begin_step(is_business_assertion=_is_business_assertion_step(step))
            self._observe_step_event("step_started", step, index=index)
            self._observe_step_event("phase_started", step, index=index, phase="execute")
            try:
                if self.cancellation_event is not None and self.cancellation_event.is_set():
                    raise TimeoutError("AI 观察运行已请求停止")
                if self.progress_logger is not None:
                    self.progress_logger(index, len(normalized), step)
                result = self._run_step(step)
                if result.action in _CLICK_ACTIONS_WITH_NOTIFICATIONS:
                    drain = getattr(self.runtime, "_drain_buffered_notifications", None)
                    if drain is not None:
                        # Notifications can arrive during template restoration after the completion wait.
                        notifications = self.runtime._merge_notifications(
                            result.data.get("notifications") or [], drain(),
                        )
                        if notifications:
                            result.data["notifications"] = notifications
                            self._last_notifications = notifications
                self._attach_contract_path(result.data)
                self._templates.record_step(result.action)
                result.data.setdefault("timing", {})["duration_ms"] = _elapsed_ms(step_started)
                self._attach_step_performance(result, step_started)
                next_step = normalized[index] if index < len(normalized) else None
                workflow_result_error = self._unhandled_workflow_result_error(result, next_step)
                if workflow_result_error:
                    report.success = False
                    result.success = False
                    result.message = workflow_result_error
                    result.data.setdefault("step_index", index)
                    result.data.setdefault("step", step.to_dict())
                    result.data.setdefault(
                        "error",
                        {"type": "WorkflowResultError", "message": workflow_result_error},
                    )
                    self._record_bpr_business_step(index, step, result)
                    page_state = self._capture_page_state()
                    if page_state:
                        result.data.setdefault("page_state", page_state)
                    report.errors.append(workflow_result_error)
                    self._finish_step_observation(result, step, index, step_started)
                    report.step_results.append(result)
                    break
                notification_error = _unhandled_error_notification_message(result, next_step)
                if notification_error:
                    report.success = False
                    result.success = False
                    result.message = notification_error
                    result.data.setdefault("step_index", index)
                    result.data.setdefault("step", step.to_dict())
                    result.data.setdefault("error", {"type": "NotificationError", "message": notification_error})
                    self._record_bpr_business_step(index, step, result)
                    page_state = self._capture_page_state()
                    if page_state:
                        result.data.setdefault("page_state", page_state)
                    report.errors.append(notification_error)
                    self._finish_step_observation(result, step, index, step_started)
                    report.step_results.append(result)
                    break
                self._record_bpr_business_step(index, step, result)
                self._finish_step_observation(result, step, index, step_started)
                report.step_results.append(result)
            except Exception as exc:
                report.success = False
                message = str(exc)
                report.errors.append(message)
                if _is_bpr_stop_step(step) and self._active_bpr_session is not None:
                    self._finalize_bpr_session_error(message=message)
                failed_data = self._failed_step_data(step, index, exc, diagnostic_start)
                self._attach_contract_path(failed_data)
                failed_data["timing"] = {"duration_ms": _elapsed_ms(step_started)}
                if self.performance_enabled:
                    failed_data["performance"] = self._step_performance(step_started)
                failed_result = StepResult(
                    action=_step_label(step),
                    success=False,
                    message=message,
                    data=failed_data,
                )
                self._record_bpr_business_step(index, step, failed_result)
                self._finish_step_observation(failed_result, step, index, step_started)
                report.step_results.append(failed_result)
                break
            finally:
                self._end_step_performance()
                self._current_step_deadline = None
        if self._active_bpr_session is not None:
            message = "BPR 录制缺少 bpr.stop"
            report.success = False
            if message not in report.errors:
                report.errors.append(message)
            session = self._finalize_bpr_session_error(message=message)
            report.step_results.append(
                StepResult(
                    action="bpr.stop",
                    success=False,
                    message=message,
                    data={"bpr_session": session, "error": {"type": "BprStateError", "message": message}},
                )
            )
        report.menu_target = self.current_menu
        report.manifest = self.current_manifest
        report.binding = self.current_binding
        report.page_state = self.current_page_state
        report.bpr_sessions = list(self._bpr_sessions)
        report.success = report.success and all(item.success for item in report.step_results)
        if self.performance_enabled:
            report.performance = self._case_performance(report, run_started)
        self._finish_reference_exploration(report)
        self._current_step_index = 0
        return report

    def _finish_reference_exploration(self, report: ExecutionReport) -> None:
        session = self.observation_session
        target = (getattr(session, "configuration", {}) or {}).get("reference_exploration")
        if target is None or not report.step_results:
            return
        result = {"outcome": "skipped", "reason": "case_failed"}
        if report.success:
            try:
                result = {"outcome": "completed", **self._require_runtime_method("explore_popup_reference")(target)}
            except Exception as exc:
                result = {"outcome": "failed", "error": str(exc), **getattr(exc, "data", {})}
        from .observation import sanitize_evidence_payload
        result = sanitize_evidence_payload(result)
        reference = session.write_failure_json("reference-exploration.json", result)
        report.step_results[-1].data["reference_exploration"] = {"outcome": result["outcome"], "path": reference}
        session.write("reference_exploration_completed", {"outcome": result["outcome"], "evidence_refs": [reference]})

    def _observe_step_event(
        self,
        event: str,
        step: ActionStep,
        *,
        index: int,
        phase: str | None = None,
        **payload: Any,
    ) -> None:
        if self.observation_session is None:
            return
        self.observation_session.set_scope(step_id=str(index), phase=phase)
        self.observation_session.write(
            event,
            {
                "business_target": _step_business_target(step),
                **payload,
            },
        )

    def _finish_step_observation(
        self,
        result: StepResult,
        step: ActionStep,
        index: int,
        started: float,
    ) -> None:
        if self.observation_session is None:
            return
        duration_ms = _elapsed_ms(started)
        result.observation = {
            **classify_step_observation(result),
            "phase": "execute",
            "business_target": _step_business_target(step),
            "duration_ms": duration_ms,
        }
        receipt = build_business_assertion_receipt(step, result)
        if receipt is not None:
            receipt["candidate_request_ids"] = self.observation_session.assertion_candidate_request_ids()
            result.observation["assertion_receipt"] = receipt
        if result.success and not _is_business_assertion_step(step):
            capture_dom = getattr(self.runtime, "capture_step_dom_summary", None)
            if capture_dom is not None:
                try:
                    summary = capture_dom(index)
                except Exception as exc:
                    summary = {"capture_unavailable_reason": "dom_capture_failed", "error_type": type(exc).__name__}
                result.data["page_observation"] = summary
                if summary.get("path"):
                    result.observation["evidence_refs"].append(summary["path"])
        if not result.success:
            capture_screenshot = getattr(self.runtime, "capture_safe_failure_screenshot", None)
            if capture_screenshot is not None:
                screenshot = capture_screenshot()
                result.data["failure_screenshot"] = screenshot
                if screenshot.get("path"):
                    result.observation["evidence_refs"].append(screenshot["path"])
            capture_dom = getattr(self.runtime, "capture_safe_dom_summary", None)
            if capture_dom is not None:
                dom_summary = capture_dom()
                result.data["failure_dom_summary"] = dom_summary
                if dom_summary.get("path"):
                    result.observation["evidence_refs"].append(dom_summary["path"])
            self._capture_failure_evidence_bundle(result, step, index, started)
        terminal = "completed" if result.success else "failed"
        payload = {
            key: value
            for key, value in result.observation.items()
            if key in {"outcome", "reason_code", "operation_reason", "duration_ms", "evidence_refs"}
        }
        self._observe_step_event(f"phase_{terminal}", step, index=index, phase="execute", **payload)
        self._observe_step_event(f"step_{terminal}", step, index=index, **payload)

    def _capture_failure_evidence_bundle(
        self,
        result: StepResult,
        step: ActionStep,
        index: int,
        started: float,
    ) -> None:
        ended = time.monotonic()
        safe_message = redact_error_text(result.message)
        page = sanitize_evidence_payload(result.data.get("page_state") or self.current_page_state)
        capture_foreground = getattr(self.runtime, "capture_foreground_summary", None)
        try:
            foreground = capture_foreground() if capture_foreground is not None else None
        except Exception:
            foreground = None
        recent_errors = getattr(self.observation_session, "recent_error_records", lambda *_: [])(started, ended)
        failed_requests = getattr(
            self.observation_session,
            "recent_failed_request_records",
            lambda *_: [],
        )(started, ended)
        raw_notifications = result.data.get("notifications") or self._last_notifications
        notification_summary = _notification_evidence_summary(raw_notifications)
        notification_request_associations = getattr(
            self.observation_session,
            "recent_notification_request_associations",
            lambda *_: [],
        )(notification_summary, started, ended)
        evidence_reference = getattr(self.observation_session, "evidence_reference_if_exists", lambda *_: None)
        candidate_request_ids = list(
            (result.observation.get("assertion_receipt") or {}).get("candidate_request_ids") or []
        )
        bundle = {
            "failure": {
                "step_id": str(index),
                "phase": "execute",
                "business_target": _step_business_target(step),
                "outcome": result.observation.get("outcome"),
                "reason_code": result.observation.get("reason_code"),
                "operation_reason": result.observation.get("operation_reason"),
                "message": safe_message["text"],
                **(
                    {"message_unavailable_reason": safe_message["capture_unavailable_reason"]}
                    if safe_message["capture_unavailable_reason"]
                    else {}
                ),
            },
            "page": page or {"capture_unavailable_reason": "not_available"},
            "foreground_layer": sanitize_evidence_payload(foreground)
            if foreground
            else {"capture_unavailable_reason": "not_available"},
            "manifest": _manifest_evidence_summary(self.current_manifest),
            "notifications": notification_summary,
            "binding": _binding_evidence_summary(self.current_binding),
            "screenshot": result.data.get("failure_screenshot")
            or {"capture_unavailable_reason": "not_available"},
            "dom_summary": result.data.get("failure_dom_summary")
            or {"capture_unavailable_reason": "not_available"},
            "errors": {
                "adjacent": recent_errors,
                "index": evidence_reference("errors/index.jsonl")
                or {"capture_unavailable_reason": "not_available"},
            },
            "network": {
                "candidate_request_ids": candidate_request_ids,
                "failed_requests": failed_requests,
                "index": evidence_reference("network/index.jsonl")
                or {"capture_unavailable_reason": "not_available"},
            },
            **(
                {"workflow_result": sanitize_evidence_payload(result.data["workflow_result"])}
                if isinstance(result.data.get("workflow_result"), dict)
                else {}
            ),
            **(
                {"table_assertion_snapshot": result.data["table_assertion_snapshot"]}
                if "table_assertion_snapshot" in result.data
                else {}
            ),
            **(
                {"notification_request_associations": notification_request_associations}
                if notification_request_associations
                else {}
            ),
        }
        reference = self.observation_session.write_failure_json("failure-evidence.json", bundle)
        result.data["failure_evidence_bundle"] = {"path": reference}
        result.observation["evidence_refs"].append(reference)
        self._observe_step_event(
            "diagnostic_file_created",
            step,
            index=index,
            phase="execute",
            kind="failure_evidence_bundle",
            evidence_refs=[reference],
        )

    def _failed_step_data(
        self, step: ActionStep, step_index: int, exc: Exception, diagnostic_start: int,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "step_index": step_index,
            "step": step.to_dict(),
            "error": {"type": exc.__class__.__name__, "message": str(exc)},
        }
        current: BaseException | None = exc
        seen: set[int] = set()
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            structured = getattr(current, "data", None)
            if isinstance(structured, dict):
                for key, value in structured.items():
                    if key not in data:
                        data[key] = value
                break
            current = current.__cause__ or current.__context__
        notifications = self._safe_collect_notifications()
        if notifications:
            data["notifications"] = [*data.get("notifications", []), *notifications]
        page_state = self._capture_page_state()
        if page_state:
            data["page_state"] = page_state
        diagnostic_files = list(getattr(self.runtime, "diagnostic_files", []) or [])[diagnostic_start:]
        if diagnostic_files:
            data["diagnostic_files"] = diagnostic_files
        tree_search = getattr(self.runtime, "last_tree_search", None)
        if isinstance(tree_search, dict) and tree_search:
            data["tree_search"] = dict(tree_search)
        if self._last_tree_select_debug:
            data["tree_select_debug"] = dict(self._last_tree_select_debug)
        downloaded_files = list(getattr(self.runtime, "downloaded_files", []) or [])
        if downloaded_files:
            data["downloaded_files"] = downloaded_files
        return data

    @staticmethod
    def _attach_contract_path(data: dict[str, Any]) -> None:
        paths: list[dict[str, Any]] = []

        def collect(value: Any) -> None:
            if isinstance(value, dict):
                path = value.get("contract_path")
                if isinstance(path, dict):
                    paths.append(path)
                for item in value.values():
                    collect(item)
            elif isinstance(value, list):
                for item in value:
                    collect(item)

        collect(data)
        merged = merge_contract_paths(paths)
        if merged is not None:
            data["contract_path"] = merged
            data["fallback_used"] = merged["applicability"] == "unverified"

    def _safe_collect_notifications(self) -> list[dict[str, str]]:
        try:
            return self._collect_notifications()
        except Exception:
            return []

    def _run_step(self, step: ActionStep) -> StepResult:
        if step.kind == "component":
            step = replace(step, target=self._resolve_step_value(step.target))
            self._used_components.add(str(step.component))
            if step.component in {"workflow_result", "workflow_panel"} and self.observation_session is not None:
                enable_capability = getattr(self.observation_session, "enable_capability", None)
                if enable_capability is not None:
                    enable_capability(str(step.component))
            # form.fill already synchronizes with its own reference-restoration semantics.
            pending = None if (step.component, step.operation) == ("form", "fill") else self._templates.prepare_step()
            result = self._handle_component_step(step)
            if pending:
                result.data.setdefault("dynamic_template", pending)
            return result
        handler = getattr(self, f"_handle_{step.action}", None)
        if handler is None:
            raise ValueError(f"不支持的 DSL 动作: {step.action}")
        return handler(step)

    def _handle_open_menu(self, step: ActionStep) -> StepResult:
        menu_path = str(step.params["menu_path"])
        self.current_menu = None
        self._templates.initialize()
        self.current_page_supported = False
        self.current_template_error = None
        cancellation = self.cancellation_event.is_set if self.cancellation_event is not None else None
        deadline = self._current_step_deadline or (time.monotonic() + self._step_timeout_seconds())
        try:
            opened = self._menu_opening.open(
                MenuOpeningRequest(
                    menu_path=menu_path,
                    deadline=deadline,
                    cancelled=cancellation,
                    performance_enabled=self.performance_enabled,
                )
            )
        except MenuOpeningError as exc:
            template_error = exc.data.get("template_error")
            if isinstance(template_error, dict):
                self.current_template_error = dict(template_error)
            raise OpenMenuCompletionError(str(exc), dict(exc.data)) from exc

        self.current_menu = opened.menu_target
        self._templates.initialize(
            opened.manifest, opened.binding, opened.page_state, manifest_history=opened.manifest_history,
        )
        self.current_page_supported = opened.manifest is not None
        self.current_template_error = opened.template_error
        data = {
            "menu_target": opened.menu_target.to_dict(),
            "page_state": opened.page_state,
            "template_supported": opened.template_supported,
            "menu_hosting": opened.menu_hosting,
            **opened.readiness,
        }
        if opened.template_error:
            data["template_error"] = opened.template_error
        if opened.binding is not None:
            data.update(
                {
                    "runtime_element_count": opened.runtime_element_count,
                    "bound_field_count": len(opened.binding.bound_fields),
                    "bound_action_count": len(opened.binding.bound_actions),
                    "missing_fields": opened.binding.missing_fields,
                    "missing_actions": opened.binding.missing_actions,
                }
            )
        data["timing"] = {
            "phases": opened.phases,
            "menu_business_stable_ms": opened.menu_business_stable_ms,
        }
        if self.performance_enabled:
            data["performance"] = {
                "phases": opened.phases,
                "menu_business_stable_ms": opened.menu_business_stable_ms,
            }
        return StepResult(
            action=step.action,
            success=True,
            message=f"菜单已打开: {menu_path}（承载方式: {opened.menu_hosting['mode']}）",
            data=data,
        )

    def _step_timeout_seconds(self) -> float:
        configuration = getattr(self.observation_session, "configuration", {}) or {}
        try:
            value = float(configuration.get("step_timeout_seconds") or DEFAULT_STEP_TIMEOUT_SECONDS)
        except (TypeError, ValueError):
            value = float(DEFAULT_STEP_TIMEOUT_SECONDS)
        return max(value, 0.001)

    def _remaining_step_timeout_ms(self) -> int:
        if self._current_step_deadline is None:
            return DEFAULT_STEP_TIMEOUT_SECONDS * 1000
        return max(0, int(round((self._current_step_deadline - time.monotonic()) * 1000)))

    def _capture_page_state(self) -> dict[str, Any] | None:
        capture = getattr(self.runtime, "capture_page_state", None)
        if capture is None:
            return None
        try:
            return capture()
        except Exception:
            return None

    def _attach_step_performance(self, result: StepResult, started: float) -> None:
        if not self.performance_enabled:
            return
        performance = dict(result.data.get("performance") or {})
        performance.update(self._step_performance(started))
        result.data["performance"] = performance

    def _begin_step_performance(self, index: int, step: ActionStep) -> None:
        if not self.performance_enabled:
            return
        begin = getattr(self.runtime, "begin_performance_step", None)
        if begin is None:
            return
        begin({"step_context": "step", "step_index": index, "action": _step_label(step)})

    def _end_step_performance(self) -> None:
        if not self.performance_enabled:
            return
        end = getattr(self.runtime, "end_performance_step", None)
        if end is None:
            return
        end()

    def _step_performance(self, started: float) -> dict[str, Any]:
        duration_ms = _elapsed_ms(started)
        memory = self._capture_page_memory()
        return {
            "duration_ms": duration_ms,
            "network": self._collect_network_summary(reset=True),
            "memory": memory,
        }

    def _capture_page_memory(self) -> dict[str, Any]:
        capture = getattr(self.runtime, "capture_page_memory", None)
        if capture is None:
            return {
                "available": False,
                "used_js_heap_size": 0,
                "unavailable_reason": "runtime_not_supported",
            }
        try:
            memory = dict(capture() or {})
        except Exception:
            memory = {}
        if not memory:
            return {
                "available": False,
                "used_js_heap_size": 0,
                "unavailable_reason": "capture_failed",
            }
        return memory

    def _collect_network_summary(self, reset: bool = False) -> dict[str, Any]:
        collect = getattr(self.runtime, "collect_network_summary", None)
        if collect is None:
            return {
                "network_available": False,
                "request_count": 0,
                "failed_count": 0,
                "api_request_count": 0,
                "static_resource_count": 0,
                "status_counts": {},
                "encoded_body_size": 0,
                "requests": [],
                "top_slow_requests": [],
                "top_slow_api_requests": [],
                "top_slow_static_resources": [],
            }
        try:
            summary = dict(collect(reset=reset) or {})
        except TypeError:
            summary = dict(collect() or {})
        except Exception:
            return {
                "network_available": False,
                "request_count": 0,
                "failed_count": 0,
                "api_request_count": 0,
                "static_resource_count": 0,
                "status_counts": {},
                "encoded_body_size": 0,
                "requests": [],
                "top_slow_requests": [],
                "top_slow_api_requests": [],
                "top_slow_static_resources": [],
            }
        summary.setdefault("network_available", True)
        summary.setdefault("request_count", 0)
        summary.setdefault("failed_count", 0)
        summary.setdefault("api_request_count", 0)
        summary.setdefault("static_resource_count", 0)
        summary.setdefault("status_counts", {})
        summary.setdefault("encoded_body_size", 0)
        summary.setdefault("requests", [])
        summary.setdefault("top_slow_requests", [])
        summary.setdefault("top_slow_api_requests", [])
        summary.setdefault("top_slow_static_resources", [])
        return summary

    def _case_performance(self, report: ExecutionReport, started: float) -> dict[str, Any]:
        collect_events = getattr(self.runtime, "collect_network_events", None)
        network_events: list[dict[str, Any]] = []
        network_events_collected = False
        if collect_events is not None:
            try:
                network_events = list(collect_events() or [])
                network_events_collected = True
            except Exception:
                pass
        steps = []
        network_available = False
        for index, step in enumerate(report.step_results, start=1):
            performance = dict(step.data.get("performance") or {})
            network = dict(performance.get("network") or {})
            if network_events_collected:
                network.update(
                    _summarize_network_events(
                        [event for event in network_events if int(event.get("step_index") or 0) == index]
                    )
                )
                performance["network"] = network
                step.data["performance"] = performance
            network_available = network_available or bool(network.get("network_available"))
            steps.append(
                {
                    "index": index,
                    "action": step.action,
                    "success": step.success,
                    "duration_ms": int(performance.get("duration_ms") or 0),
                    "network": network,
                }
            )
        data = {
            "enabled": True,
            "cache_mode": "cold_ephemeral",
            "network_available": network_available,
            "cold": {
                "duration_ms": _elapsed_ms(started),
                "step_count": len(report.step_results),
            },
            "steps": steps,
        }
        if collect_events is not None:
            data["network_events"] = network_events
        return data

    def _handle_component_step(self, step: ActionStep) -> StepResult:
        if step.component == "bpr" and step.operation == "start":
            return self._execute_bpr_start(step)
        if step.component == "bpr" and step.operation == "stop":
            return self._execute_bpr_stop(step)
        if step.component == "tree" and step.operation == "select":
            return self._execute_tree_select(step)
        if step.component == "tab" and step.operation == "click":
            return self._execute_tab_click(step)
        if step.component == "toolbar" and step.operation == "click":
            return self._execute_toolbar_click(step)
        if step.component == "popup_reference" and step.operation == "select":
            return self._execute_popup_reference_select(step)
        if step.component == "transfer_dialog" and step.operation == "select":
            return self._execute_transfer_dialog_select(step)
        if step.component == "action" and step.operation == "click":
            return self._execute_action_click(step)
        if step.component == "amount_unit" and step.operation == "set":
            return self._execute_amount_unit_set(step)
        if step.component == "form" and step.operation == "fill":
            return self._execute_form_fill(step)
        if step.component == "form" and step.operation == "assert_values":
            return self._execute_form_assert_values(step)
        if step.component == "form" and step.operation == "capture_values":
            return self._execute_form_capture_values(step)
        if step.component == "table_row_selection" and step.operation == "select":
            return self._execute_table_row_selection_select(step)
        if step.component == "table_row_action" and step.operation == "click":
            return self._execute_table_row_action_click(step)
        if step.component == "query" and step.operation == "search":
            return self._execute_query_search(step)
        if step.component == "query" and step.operation == "reset":
            return self._execute_query_reset()
        if step.component == "table" and step.operation == "assert_column_values":
            return self._execute_table_assert_column_values(step)
        if step.component == "table" and step.operation == "assert_columns":
            return self._execute_table_assert_columns(step)
        if step.component == "table" and step.operation == "assert_empty":
            return self._execute_table_assert_empty(step)
        if step.component == "table" and step.operation == "capture_row_values":
            return self._execute_table_capture_row_values(step)
        if step.component == "table" and step.operation == "click_cell_link":
            return self._execute_table_click_cell_link(step)
        if step.component == "table" and step.operation == "assert_row_values":
            return self._execute_table_assert_row_values(step)
        if step.component == "editable_table" and step.operation == "add_row":
            return self._execute_editable_table_add_row(step)
        if step.component == "editable_table" and step.operation == "fill_row":
            return self._execute_editable_table_fill_row(step)
        if step.component == "dialog" and step.operation in {"confirm", "cancel", "click"}:
            return self._execute_dialog_click(step)
        if step.component == "notification" and step.operation == "assert":
            return self._execute_notification_assert(step)
        if step.component == "notification" and step.operation == "close":
            return self._execute_notification_close(step)
        if step.component == "workflow_result" and step.operation == "assert":
            return self._execute_workflow_result_assert(step)
        if step.component == "workflow_panel" and step.operation == "click":
            return self._execute_workflow_panel_click(step)
        if step.component == "workflow_result" and step.operation == "details":
            return self._execute_workflow_result_details(step)
        if step.component == "workflow_result" and step.operation == "confirm":
            return self._execute_workflow_result_confirm(step)
        if step.component == "import" and step.operation == "upload":
            return self._execute_import_upload(step)
        if step.component == "import" and step.operation == "download_template":
            return self._execute_import_download_template(step)
        if step.component == "attachment" and step.operation == "upload":
            return self._execute_attachment_upload(step)
        raise ValueError(f"不支持的组件 DSL: {step.component}.{step.operation}")

    def _execute_bpr_start(self, step: ActionStep) -> StepResult:
        if self._active_bpr_session is not None:
            raise RuntimeError("不支持嵌套 BPR 录制，请先执行 bpr.stop")
        start_bpr = getattr(self.runtime, "start_bpr", None)
        if start_bpr is None:
            raise RuntimeError("当前运行时不支持 BPR 录制")
        index = len(self._bpr_sessions) + 1
        name = str(step.target.get("name") or "").strip()
        description = str(step.target.get("description") or "").strip()
        started = self._call_bpr_start(
            start_bpr,
            {
                "index": index,
                "name": name,
                "description": description,
                "control_step": self._current_step_index,
            },
        )
        session = _normalize_bpr_session_payload(started)
        session.update(
            {
                "index": index,
                "name": name or session.get("name") or f"BPR录制{index}",
                "description": description,
                "start_control_step": self._current_step_index,
                "end_control_step": None,
                "start_step": None,
                "end_step": None,
                "range": "",
                "actions": [],
                "success": False,
                "status": "recording",
                "error": "",
            }
        )
        self._active_bpr_session = session
        return StepResult(
            action="bpr.start",
            success=True,
            message=f"BPR 录制已开始: {session.get('name') or session.get('bpr_id') or index}",
            data={"bpr_session": _bpr_control_step_payload(session)},
        )

    def _execute_bpr_stop(self, step: ActionStep) -> StepResult:
        if self._active_bpr_session is None:
            raise RuntimeError("没有正在录制的 BPR session，不能执行 bpr.stop")
        stop_bpr = getattr(self.runtime, "stop_bpr", None)
        if stop_bpr is None:
            raise RuntimeError("当前运行时不支持 BPR 录制")
        session = self._active_bpr_session
        stopped = self._call_bpr_stop(stop_bpr, session)
        stop_payload = _normalize_bpr_session_payload(stopped)
        session.update({key: value for key, value in stop_payload.items() if value not in (None, "")})
        report_url = str(session.get("report_url") or session.get("url") or "").strip()
        if not report_url.startswith("http"):
            raise RuntimeError("BPR stop 未返回在线报告链接")
        session["report_url"] = report_url
        session["success"] = True
        session["status"] = "success"
        session["error"] = ""
        session["end_control_step"] = self._current_step_index
        self._finalize_bpr_session_success(session)
        return StepResult(
            action="bpr.stop",
            success=True,
            message=f"BPR 录制已结束: {report_url}",
            data={"bpr_session": _bpr_control_step_payload(session)},
        )

    def _call_bpr_start(self, start_bpr, payload: dict[str, Any]) -> Any:
        kwargs = {key: value for key, value in payload.items() if value not in (None, "")}
        if _callable_accepts_keyword(start_bpr, "name") or _callable_accepts_keyword(start_bpr, "description"):
            return start_bpr(**kwargs)
        return start_bpr()

    def _call_bpr_stop(self, stop_bpr, session: dict[str, Any]) -> Any:
        if _callable_accepts_keyword(stop_bpr, "session"):
            return stop_bpr(session=session)
        try:
            signature = inspect.signature(stop_bpr)
        except (TypeError, ValueError):
            return stop_bpr(session)
        required_positionals = [
            parameter
            for parameter in signature.parameters.values()
            if parameter.default is inspect.Parameter.empty
            and parameter.kind in {inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD}
        ]
        if required_positionals:
            return stop_bpr(session)
        return stop_bpr()

    def _record_bpr_business_step(self, index: int, step: ActionStep, result: StepResult) -> None:
        session = self._active_bpr_session
        if session is None or _is_bpr_control_step(step):
            return
        action = {
            "step_index": index,
            "action": result.action or _step_label(step),
            "success": result.success,
            "message": result.message,
            "step": step.to_dict(),
        }
        actions = session.setdefault("actions", [])
        actions.append(action)
        session["start_step"] = session.get("start_step") or index
        session["end_step"] = index
        session["range"] = _bpr_range_text(session)

    def _finalize_bpr_session_success(self, session: dict[str, Any]) -> None:
        session["range"] = _bpr_range_text(session)
        _fill_bpr_duration(session)
        self._bpr_sessions.append(dict(session))
        self._active_bpr_session = None

    def _finalize_bpr_session_error(self, *, message: str) -> dict[str, Any]:
        session = self._active_bpr_session
        if session is None:
            return {}
        session["success"] = False
        session["status"] = "failed"
        session["error"] = message
        session["range"] = _bpr_range_text(session)
        _fill_bpr_duration(session)
        archived = dict(session)
        self._bpr_sessions.append(archived)
        self._active_bpr_session = None
        return archived

    def _execute_tree_select(self, step: ActionStep) -> StepResult:
        self._ensure_menu_open_for_component("树")
        if not self.current_manifest or not any(region.region_type == "tree" for region in self.current_manifest.regions):
            raise RuntimeError("当前页面不包含树组件")
        tree_name = _extract_component_name(step.target)
        tree_region = self._resolve_region("tree", tree_name) if tree_name else self._resolve_single_region("tree")
        shortcut = _tree_select_node_shortcut(step.target)
        if shortcut:
            return self._execute_tree_select_shortcut(step, shortcut, tree_name, tree_region)
        labels = _tree_select_labels(step.target)
        select_tree_node = getattr(self.runtime, "select_tree_node", None) or getattr(self.runtime, "select_tree_context", None) or getattr(self.runtime, "click_tree_node", None)
        if select_tree_node is None:
            raise RuntimeError("当前运行时不支持树节点选择")
        selected: list[str] = []
        tree_searches: list[dict[str, Any]] = []
        for label in labels:
            self._last_tree_select_debug = {
                "label": label,
                "tree_fieldid": tree_region.fieldid if tree_region else None,
                "runtime_method": getattr(select_tree_node, "__name__", select_tree_node.__class__.__name__),
                "called": False,
            }
            try:
                self._last_tree_select_debug["called"] = True
                self._call_tree_select(select_tree_node, label, tree_region.fieldid if tree_region else None)
                selected.append(label)
                tree_search = getattr(self.runtime, "last_tree_search", None)
                if isinstance(tree_search, dict) and tree_search:
                    tree_searches.append(dict(tree_search))
            except Exception as exc:
                self._last_tree_select_debug["error"] = str(exc)
                tree_context = f"({tree_name})" if tree_name else ""
                raise RuntimeError(f"未找到树节点{tree_context}: {label}") from exc
        data = {"label": selected[0]} if len(selected) == 1 else {"labels": selected}
        if tree_name:
            data["name"] = tree_name
        if tree_region:
            data["tree_fieldid"] = tree_region.fieldid
        if tree_searches:
            data["tree_search"] = tree_searches[0] if len(tree_searches) == 1 else tree_searches
        message_label = selected[0] if len(selected) == 1 else "、".join(selected)
        return StepResult(action="tree.select", success=True, message=f"树节点已选中: {message_label}", data=data)

    def _execute_tree_select_shortcut(self, step: ActionStep, shortcut: str, tree_name: str, tree_region) -> StepResult:
        method_name = {
            "root": "select_tree_root",
            "first_leaf": "select_first_tree_leaf",
        }.get(shortcut)
        if not method_name:
            raise RuntimeError(f"不支持的树节点快捷选择: {shortcut}")
        select_tree_shortcut = getattr(self.runtime, method_name, None)
        if not callable(select_tree_shortcut):
            raise RuntimeError(f"当前运行时不支持树节点快捷选择: {shortcut}")
        try:
            selected_label = self._call_tree_shortcut_select(
                select_tree_shortcut,
                tree_region.fieldid if tree_region else None,
            )
        except Exception as exc:
            tree_context = f"({tree_name})" if tree_name else ""
            raise RuntimeError(f"未找到树节点快捷选择{tree_context}: {shortcut}") from exc
        data = {"node": shortcut, "label": str(selected_label or "")}
        if tree_name:
            data["name"] = tree_name
        if tree_region:
            data["tree_fieldid"] = tree_region.fieldid
        return StepResult(action="tree.select", success=True, message=f"树节点已选中: {data['label']}", data=data)

    def _call_tree_select(self, select_tree_node, label: str, tree_fieldid: str | None) -> None:
        if not tree_fieldid:
            select_tree_node(label)
            return
        try:
            signature = inspect.signature(select_tree_node)
        except (TypeError, ValueError):
            select_tree_node(label)
            return
        if "tree_fieldid" in signature.parameters:
            select_tree_node(label, tree_fieldid=tree_fieldid)
            return
        select_tree_node(label)

    def _call_tree_shortcut_select(self, select_tree_shortcut, tree_fieldid: str | None) -> str:
        if not tree_fieldid:
            return str(select_tree_shortcut() or "")
        try:
            signature = inspect.signature(select_tree_shortcut)
        except (TypeError, ValueError):
            return str(select_tree_shortcut() or "")
        if "tree_fieldid" in signature.parameters:
            return str(select_tree_shortcut(tree_fieldid=tree_fieldid) or "")
        return str(select_tree_shortcut() or "")

    def _execute_tab_click(self, step: ActionStep) -> StepResult:
        self._ensure_menu_open_for_component("页签")
        label = str(step.target["label"])
        candidate = self._find_tab_candidate(label)
        bound = self.current_binding.tabs_by_alias.get(label) if self.current_binding else None
        fieldid = candidate.fieldid if candidate else (bound.candidate.fieldid if bound is not None else None)
        click_tab_action = getattr(self.runtime, "click_tab_action", None)
        def click_tab() -> None:
            if click_tab_action is not None:
                click_tab_action(label, fieldid)
            elif bound is not None:
                self.runtime.click(bound)
            else:
                raise RuntimeError(f"未绑定页签动作: {label}")

        def perform():
            completion_result = self._execute_action_completion(
                "tab.click",
                {
                    "source_page_id": self._current_page_identity(),
                    "tab": label,
                    "tab_fieldid": fieldid or "",
                },
                click_tab,
            )
            notifications, completion = self._action_completion_step_data(completion_result)
            self._last_notifications = notifications
            data = {"label": label}
            data.update(completion)
            if fieldid:
                data["fieldid"] = fieldid
            if notifications:
                data["notifications"] = notifications
            return data

        transition = self._templates.execute("tab.click", perform)
        data = {**transition.value, **transition.changes}
        return StepResult(action="tab.click", success=True, message=f"页签已点击: {label}", data=data)

    def _resolve_region(self, region_type: str, name: str):
        assert self.current_manifest is not None
        matches = [
            region
            for region in self.current_manifest.regions
            if region.region_type == region_type and name in _region_aliases(region)
        ]
        if not matches:
            raise RuntimeError(f"未找到{name}组件")
        matches = self._prefer_runtime_visible_regions(matches)
        matches = self._prefer_config_visible_regions(matches)
        if len(matches) > 1:
            labels = [f"{item.label}({item.fieldid})" for item in matches]
            raise RuntimeError(f"{name}组件匹配不唯一: {labels}")
        return matches[0]

    def _resolve_single_region(self, region_type: str):
        assert self.current_manifest is not None
        matches = [region for region in self.current_manifest.regions if region.region_type == region_type]
        matches = self._prefer_runtime_visible_regions(matches)
        matches = self._prefer_config_visible_regions(matches)
        if len(matches) == 1:
            return matches[0]
        return None

    def _prefer_runtime_visible_regions(self, regions: list[Any]) -> list[Any]:
        if len(regions) <= 1:
            return regions
        is_region_visible = getattr(self.runtime, "is_region_visible", None)
        if is_region_visible is None:
            return regions
        visible_regions = []
        for region in regions:
            try:
                if any(is_region_visible(fieldid) for fieldid in _region_fieldids_for_runtime(region)):
                    visible_regions.append(region)
            except Exception:
                continue
        return visible_regions or regions

    def _prefer_config_visible_regions(self, regions: list[Any]) -> list[Any]:
        if len(regions) <= 1:
            return regions
        visible_regions = [region for region in regions if region.visible_by_config]
        return visible_regions or regions

    def _execute_toolbar_click(self, step: ActionStep) -> StepResult:
        self._ensure_menu_open_for_component("工具栏")
        label = str(step.target["label"])
        sub_label = _toolbar_sub_label(step.target)
        action_candidate = self._find_action_candidate(label)
        if label not in self.current_binding.actions_by_alias and action_candidate is None:
            has_runtime_identity = getattr(self.runtime, "has_visible_toolbar_action", None)
            if has_runtime_identity is None or not has_runtime_identity(label):
                raise RuntimeError(f"未绑定工具栏动作: {label}")
        previous_download_count = len(getattr(self.runtime, "downloaded_files", []))
        def perform():
            self._clear_pending_dynamic_template()
            click_toolbar_action = getattr(self.runtime, "click_toolbar_action", None)
            def click_toolbar() -> bool:
                if click_toolbar_action is not None:
                    self._call_toolbar_click(click_toolbar_action, label, sub_label, action_candidate)
                else:
                    self.runtime.click(self._require_action(label))
                return len(getattr(self.runtime, "downloaded_files", [])) == previous_download_count

            completion_result = self._execute_action_completion(
                "toolbar.click",
                {
                    "source_page_id": self._current_page_identity(),
                    "action": label,
                    "sub_label": sub_label or "",
                },
                click_toolbar,
            )
            downloaded_files = getattr(self.runtime, "downloaded_files", [])[previous_download_count:]
            data = {"label": label}
            if sub_label:
                data["sub_label"] = sub_label
            if completion_result.specialized:
                data["downloaded_files"] = downloaded_files
                notifications = self._collect_notifications()
                self._wait_for_pending_dynamic_template()
                completion = {}
            else:
                notifications, completion = self._action_completion_step_data(completion_result)
            self._last_notifications = notifications
            data.update(completion)
            if notifications:
                data["notifications"] = notifications
            return data

        transition = self._templates.execute(
            "toolbar.click", perform,
            restore_previous=bool(step.target.get("restore_previous") or step.target.get("restore_template")),
        )
        data = {**transition.value, **transition.changes}
        return StepResult(action="toolbar.click", success=True, message=f"工具栏按钮已点击: {label}", data=data)

    def _call_toolbar_click(self, click_toolbar_action, label: str, sub_label: str | None, action_candidate) -> None:
        aliases = _candidate_alias_list(action_candidate)
        fieldid = getattr(action_candidate, "fieldid", None) if action_candidate is not None else None
        try:
            signature = inspect.signature(click_toolbar_action)
        except (TypeError, ValueError):
            click_toolbar_action(label, sub_label=sub_label)
            return
        kwargs: dict[str, Any] = {"sub_label": sub_label}
        if "fieldid" in signature.parameters:
            kwargs["fieldid"] = fieldid
        if "aliases" in signature.parameters:
            kwargs["aliases"] = aliases
        click_toolbar_action(label, **kwargs)

    def _execute_transfer_dialog_select(self, step: ActionStep) -> StepResult:
        self._ensure_menu_open_for_component("穿梭选择框")
        target = self._resolve_step_value(step.target)
        title = _optional_text(target.get("title") or target.get("label") or target.get("name"))
        move = str(target.get("move") or target.get("direction") or "to_right")
        confirm = bool(target.get("confirm", True))
        items = _extract_transfer_items(target)
        select_transfer_dialog = self._require_runtime_method("select_transfer_dialog")
        result = dict(select_transfer_dialog(title=title, items=items, move=move, confirm=confirm) or {})
        data = {"title": title, "items": items, "move": move, "confirm": confirm}
        data.update(result)
        return StepResult(
            action="transfer_dialog.select",
            success=True,
            message="双列表选择窗口已处理",
            data=data,
        )

    def _execute_popup_reference_select(self, step: ActionStep) -> StepResult:
        self._ensure_menu_open_for_component("弹出参照")
        target = self._resolve_step_value(step.target)
        title = _optional_text(target.get("title") or target.get("label") or target.get("name"))
        confirm = bool(target.get("confirm", True))
        select_popup_reference = self._require_runtime_method("select_popup_reference")
        def perform():
            result = dict(select_popup_reference(title=title, target=target, confirm=confirm) or {})
            data = {"title": title, "target": target, "confirm": confirm}
            data.update(result)
            return data

        transition = self._templates.execute("popup_reference.select", perform)
        data = {**transition.value, **transition.changes}
        return StepResult(
            action="popup_reference.select",
            success=True,
            message="弹出参照已选择",
            data=data,
        )

    def _remember_action_notifications(self, notifications: list[dict[str, str]]) -> None:
        self._last_notifications = notifications

    def _execute_action_click(self, step: ActionStep) -> StepResult:
        self._ensure_menu_open_for_component("动作")
        target = step.target
        fieldid = str(target.get("fieldid") or "").strip()
        label = str(target.get("label") or "").strip()
        def perform():
            if fieldid:
                self._clear_pending_dynamic_template()
                click_by_fieldid = getattr(self.runtime, "click_action_by_fieldid", None)

                def click_action() -> None:
                    if click_by_fieldid is not None:
                        click_by_fieldid(fieldid)
                    else:
                        self.runtime.click(self._require_action(fieldid))

                action_identity = fieldid
                data = {"fieldid": fieldid}
            elif label:
                self._clear_pending_dynamic_template()

                def click_action() -> None:
                    self.runtime.click(self._require_action(label))

                action_identity = label
                data = {"label": label}
            else:
                raise ValueError(f"动作点击缺少 fieldid 或 label: {target}")
            completion_result = self._execute_action_completion(
                "action.click",
                {"source_page_id": self._current_page_identity(), "action": action_identity},
                click_action,
            )
            notifications, completion = self._action_completion_step_data(completion_result)
            data.update(completion)
            if notifications:
                data["notifications"] = notifications
            return data

        transition = self._templates.execute("action.click", perform, target=target)
        data = {**transition.value, **transition.changes}
        return StepResult(action="action.click", success=True, message="动作已点击", data=data)

    def _execute_workflow_panel_click(self, step: ActionStep) -> StepResult:
        self._ensure_menu_open_for_component("工作流操作面板")
        label = str(step.target["label"])
        click = self._require_runtime_method("click_workflow_panel_action")
        snapshot: dict[str, Any] = {}

        def perform():
            self._clear_pending_dynamic_template()

            def click_panel():
                snapshot.update(click(label))

            result = self._execute_action_completion(
                "workflow_panel.click",
                {"source_page_id": self._current_page_identity(), "action": label, "workflow_panel": True},
                click_panel,
            )
            notifications, completion = self._action_completion_step_data(result)
            self._last_notifications = notifications
            snapshot["status"] = "confirmation_required" if result.completion_signal == "confirmation_required" else "triggered"
            return {"label": label, "workflow_panel": snapshot, "notifications": notifications, **completion}

        try:
            transition = self._templates.execute("workflow_panel.click", perform)
        except Exception as exc:
            data = dict(getattr(exc, "data", {}) or {})
            observe = getattr(self.runtime, "observe_workflow_panel", None)
            if "workflow_panel" not in data:
                data["workflow_panel"] = snapshot
                if observe is not None:
                    try:
                        data["workflow_panel"] = {**snapshot, "last_state": observe(label)}
                    except Exception:
                        pass
            panel = data["workflow_panel"]
            status = panel.get("last_state", panel).get("status")
            reason = {
                "missing": "target_unavailable", "ambiguous": "target_unavailable",
                "action_missing": "target_unavailable", "ambiguous_action": "target_unavailable",
                "action_blocked": "target_unavailable", "evidence_unavailable": "evidence_unavailable",
            }.get(status)
            if reason is None and type(exc).__name__ == "TimeoutError":
                reason = "evidence_unavailable"
            if reason:
                data["observation_failure"] = {"reason_code": reason}
            exc.data = data
            raise
        return StepResult(
            action="workflow_panel.click", success=True, message=f"工作流面板操作已触发: {label}",
            data={**transition.value, **transition.changes},
        )

    def _execute_dialog_click(self, step: ActionStep) -> StepResult:
        self._ensure_menu_open_for_component("弹窗")
        target = step.target
        label = str(target.get("label") or "").strip()
        if not label:
            label = "取消" if step.operation == "cancel" else "确定"
        expect_download = bool(target.get("expect_download") or target.get("download"))
        previous_download_count = len(getattr(self.runtime, "downloaded_files", []))
        click_dialog_button = getattr(self.runtime, "click_dialog_button", None)
        if click_dialog_button is None:
            raise RuntimeError("当前运行时不支持弹窗按钮点击")
        def perform():
            self._clear_pending_dynamic_template()
            def click_dialog() -> bool:
                click_dialog_button(label, expect_download=expect_download)
                return not expect_download

            completion_result = self._execute_action_completion(
                "dialog.click",
                {"source_page_id": self._current_page_identity(), "action": label},
                click_dialog,
            )
            downloaded_files = getattr(self.runtime, "downloaded_files", [])[previous_download_count:]
            data = {"label": label}
            if expect_download:
                data["expect_download"] = True
            if downloaded_files:
                data["downloaded_files"] = downloaded_files
            if completion_result.specialized:
                notifications = self._collect_notifications()
                self._wait_for_pending_dynamic_template()
                completion = {}
            else:
                notifications, completion = self._action_completion_step_data(completion_result)
            self._last_notifications = notifications
            data.update(completion)
            if notifications:
                data["notifications"] = notifications
            return data

        transition = self._templates.execute(
            "dialog.click", perform,
            restore_previous=bool(target.get("restore_previous") or target.get("restore_template")),
        )
        data = {**transition.value, **transition.changes}
        return StepResult(action="dialog.click", success=True, message=f"弹窗按钮已点击: {label}", data=data)

    def _execute_notification_assert(self, step: ActionStep) -> StepResult:
        notifications = list(self._last_notifications or [])
        if not notifications:
            notifications = self._collect_notifications()
        expected_type, contains, equals, message = _notification_match_values(step.target)
        matches = _matching_notifications(
            notifications,
            expected_type=expected_type,
            contains=contains,
            equals=equals,
            message=message,
        )
        if not matches:
            deadline = time.monotonic() + 60
            fresh_notifications = self._collect_notifications()
            while True:
                if fresh_notifications:
                    notifications = _deduplicate_notifications([*notifications, *fresh_notifications])
                    matches = _matching_notifications(
                        notifications,
                        expected_type=expected_type,
                        contains=contains,
                        equals=equals,
                        message=message,
                    )
                    if matches:
                        break
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.25)
                fresh_notifications = self._collect_notifications()
            if fresh_notifications and not matches:
                notifications = _deduplicate_notifications([*notifications, *fresh_notifications])
        if not matches:
            expected = {key: value for key, value in step.target.items() if value not in (None, "")}
            raise BusinessAssertionMismatch(
                "未找到匹配页面提示: "
                f"type={expected_type or '*'} contains={contains or '*'} "
                f"equals={equals or '*'} message={message or '*'} actual={notifications}",
                expected=expected,
                actual={"notifications": notifications},
                scope={"surface": "notification"},
            )
        return StepResult(
            action="notification.assert",
            success=True,
            message="页面提示校验通过",
            data={"notification": matches[0], "notifications": notifications},
        )

    def _execute_notification_close(self, step: ActionStep) -> StepResult:
        expected_type, contains, equals, message = _notification_match_values(step.target)
        label = str(step.target.get("label") or step.target.get("button") or "").strip()
        close_notification = self._require_runtime_method("close_notification")
        result = dict(
            close_notification(
                expected_type=expected_type,
                contains=contains,
                equals=equals,
                message=message,
                label=label,
            )
            or {}
        )
        if "remaining_notifications" in result and isinstance(result.get("remaining_notifications"), list):
            remaining_notifications = list(result.get("remaining_notifications") or [])
        else:
            remaining_notifications = self._collect_notifications()
            result["remaining_notifications"] = remaining_notifications
        self._last_notifications = remaining_notifications
        return StepResult(
            action="notification.close",
            success=True,
            message="页面提示已关闭",
            data=result,
        )

    def _execute_workflow_result_assert(self, step: ActionStep) -> StepResult:
        self._ensure_menu_open_for_component("工作流批量结果层")
        observe = self._require_runtime_method("observe_workflow_result")
        timeout_ms = self._remaining_step_timeout_ms()
        snapshot = self._call_workflow_result_observer(observe, timeout_ms)
        if snapshot is None:
            pending = dict(self._workflow_result_snapshot or {})
            raise WorkflowResultObservationError(
                "未观察到工作流批量结果层",
                reason_code="target_unavailable",
                snapshot=pending,
            )
        snapshot = dict(snapshot)
        status = str(snapshot.get("status") or "").strip()
        if status != "observed":
            raise WorkflowResultObservationError(
                "工作流批量结果层统计证据不可解析",
                reason_code="evidence_unavailable",
                snapshot=snapshot,
            )
        counts = dict(snapshot.get("counts") or {})
        expected = {
            key: step.target[key]
            for key in ("total", "succeeded", "failed", "title", "message", "contains")
            if key in step.target
        }
        actual = {
            "counts": counts,
            "semantics": dict(snapshot.get("semantics") or {}),
        }
        mismatches: list[str] = []
        for key in ("total", "succeeded", "failed"):
            if key in expected and counts.get(key) != expected[key]:
                mismatches.append(f"{key}: expected={expected[key]} actual={counts.get(key)}")
        semantics = actual["semantics"]
        text = str(semantics.get("message") or snapshot.get("text") or "")
        title = str(semantics.get("title") or "")
        if "title" in expected and expected["title"] not in title:
            mismatches.append(f"title: expected={expected['title']} actual={title}")
        if "message" in expected and not _workflow_result_text_matches(text, str(expected["message"])):
            mismatches.append(f"message: expected={expected['message']} actual={text}")
        if "contains" in expected and str(expected["contains"]) not in text:
            mismatches.append(f"contains: expected={expected['contains']} actual={text}")
        if mismatches:
            raise BusinessAssertionMismatch(
                "工作流批量结果层业务断言不符合: " + "; ".join(mismatches),
                expected=expected,
                actual=actual,
                scope={"surface": "workflow_result"},
                evidence={"workflow_result": snapshot},
            )
        snapshot["asserted"] = True
        self._workflow_result_snapshot = snapshot
        self._workflow_result_asserted = True
        return StepResult(
            action="workflow_result.assert",
            success=True,
            message="工作流批量结果层校验通过",
            data={
                "workflow_result": snapshot,
                "assertion_comparison": {
                    "expected": expected,
                    "actual": actual,
                    "scope": {"surface": "workflow_result"},
                },
            },
        )

    def _execute_workflow_result_details(self, step: ActionStep) -> StepResult:
        self._ensure_workflow_result_asserted()
        open_details = self._require_runtime_method("open_workflow_result_details")
        label = str(step.target.get("label") or "查看详情").strip()
        result = dict(
            self._call_workflow_result_operation(
                open_details,
                label=label,
                timeout_ms=self._remaining_step_timeout_ms(),
            )
            or {}
        )
        details = result.get("details")
        if not isinstance(details, list):
            raise WorkflowResultObservationError(
                "工作流批量结果层详情证据不可用",
                reason_code="evidence_unavailable",
                snapshot={**(self._workflow_result_snapshot or {}), **result},
            )
        workflow_result = {
            **dict(self._workflow_result_snapshot or {}),
            "details": details,
            "operation": {"name": "details", "label": label, "opened": True},
        }
        self._workflow_result_snapshot = workflow_result
        return StepResult(
            action="workflow_result.details",
            success=True,
            message="工作流批量结果层详情已采集",
            data={"workflow_result": workflow_result},
        )

    def _execute_workflow_result_confirm(self, step: ActionStep) -> StepResult:
        self._ensure_workflow_result_asserted()
        confirm = self._require_runtime_method("confirm_workflow_result")
        label = str(step.target.get("label") or "确认").strip()
        result = dict(
            self._call_workflow_result_operation(
                confirm,
                label=label,
                timeout_ms=self._remaining_step_timeout_ms(),
            )
            or {}
        )
        if result.get("closed") is False:
            raise WorkflowResultObservationError(
                "工作流批量结果层确认后仍可见",
                reason_code="target_unavailable",
                snapshot={**(self._workflow_result_snapshot or {}), **result},
            )
        workflow_result = {
            **dict(self._workflow_result_snapshot or {}),
            "operation": {"name": "confirm", "label": label, "closed": True},
        }
        self._workflow_result_snapshot = None
        self._workflow_result_asserted = False
        return StepResult(
            action="workflow_result.confirm",
            success=True,
            message="工作流批量结果层已关闭",
            data={"workflow_result": workflow_result},
        )

    def _ensure_workflow_result_asserted(self) -> None:
        if self._workflow_result_asserted and self._workflow_result_snapshot:
            return
        raise WorkflowResultObservationError(
            "工作流批量结果层尚未完成断言前置条件",
            reason_code="target_unavailable",
            snapshot=dict(self._workflow_result_snapshot or {}),
        )

    @staticmethod
    def _call_workflow_result_observer(observe, timeout_ms: int) -> dict[str, Any] | None:
        if _callable_accepts_keyword(observe, "timeout_ms"):
            return observe(timeout_ms=timeout_ms)
        return observe(timeout_ms)

    @staticmethod
    def _call_workflow_result_operation(operation, *, label: str, timeout_ms: int) -> Any:
        kwargs: dict[str, Any] = {}
        if _callable_accepts_keyword(operation, "label"):
            kwargs["label"] = label
        if _callable_accepts_keyword(operation, "timeout_ms"):
            kwargs["timeout_ms"] = timeout_ms
        if kwargs:
            return operation(**kwargs)
        return operation(label)

    def _unhandled_workflow_result_error(
        self, result: StepResult, next_step: ActionStep | None
    ) -> str | None:
        if result.action not in _CLICK_ACTIONS_WITH_NOTIFICATIONS:
            return None
        observe = getattr(self.runtime, "observe_workflow_result", None)
        if observe is None:
            return None
        try:
            snapshot = self._call_workflow_result_observer(observe, 0)
        except Exception:
            return None
        if not snapshot:
            return None
        snapshot = dict(snapshot)
        result.data["workflow_result"] = snapshot
        self._workflow_result_snapshot = snapshot
        if self._workflow_result_asserted:
            if _is_workflow_result_operation(next_step, {"details", "confirm"}):
                return None
            return _unhandled_workflow_result_message(result, next_step, asserted=True)
        if _is_workflow_result_assert_step(next_step):
            return None
        return _unhandled_workflow_result_message(result, next_step, asserted=False)

    def _execute_import_upload(self, step: ActionStep) -> StepResult:
        self._ensure_menu_open_for_component("导入")
        label = str(step.target.get("label") or "导入")
        fieldid = str(step.target.get("fieldid") or "").strip() or None
        files = _extract_import_files(step.target)
        assertion = step.target.get("assert")
        assertion_payload = assertion if isinstance(assertion, dict) else {}
        expected_status = str(assertion_payload.get("status") or "success").strip().lower()
        import_upload = self._require_runtime_method("import_upload")
        kwargs: dict[str, Any] = {}
        if self.current_manifest is not None and _callable_accepts_keyword(import_upload, "action_candidates"):
            kwargs["action_candidates"] = _manifest_action_candidates(self.current_manifest)
        if _callable_accepts_keyword(import_upload, "fieldid"):
            kwargs["fieldid"] = fieldid
        if _callable_accepts_keyword(import_upload, "expected_status"):
            kwargs["expected_status"] = expected_status
        result = dict(import_upload(label, files, **kwargs) or {})
        import_results = _extract_import_results(result)
        _assert_import_results(import_results, assertion)
        data = {"label": label, "fieldid": fieldid, "files": files, "import_results": import_results}
        if result:
            data.update({key: value for key, value in result.items() if key not in {"results", "import_results"}})
        return StepResult(action="import.upload", success=True, message="导入文件已处理", data=data)

    def _execute_import_download_template(self, step: ActionStep) -> StepResult:
        self._ensure_menu_open_for_component("导入")
        label = str(step.target.get("label") or "导入")
        template = step.target.get("template") or step.target.get("template_name") or step.target.get("name")
        template_text = str(template).strip() if template is not None else None
        import_download_template = self._require_runtime_method("import_download_template")
        result = dict(import_download_template(label, template_text) or {})
        downloaded_files = list(result.get("downloaded_files") or [])
        if not downloaded_files:
            raise RuntimeError(f"下载模版后未捕获到下载文件: template={template_text or '*'}")
        data = {"label": label, "template": template_text, "downloaded_files": downloaded_files}
        data.update({key: value for key, value in result.items() if key not in data})
        return StepResult(action="import.download_template", success=True, message="导入模版已下载", data=data)

    def _execute_amount_unit_set(self, step: ActionStep) -> StepResult:
        self._ensure_menu_open_for_component("金额单位")
        value = str(step.target["value"]).strip()
        set_amount_unit = self._require_runtime_method("set_amount_unit")
        kwargs: dict[str, Any] = {}
        if self.current_manifest is not None and _callable_accepts_keyword(set_amount_unit, "action_candidates"):
            kwargs["action_candidates"] = _manifest_action_candidates(self.current_manifest)
        result = dict(set_amount_unit(value, **kwargs) or {})
        data = {"value": value}
        data.update(result)
        return StepResult(action="amount_unit.set", success=True, message=f"金额单位已设置: {value}", data=data)

    def _execute_attachment_upload(self, step: ActionStep) -> StepResult:
        self._ensure_menu_open_for_component("附件")
        attachments = _extract_attachments(step.target)
        upload_attachments = self._require_runtime_method("upload_attachments")
        kwargs: dict[str, Any] = {}
        if self.current_manifest is not None and _callable_accepts_keyword(upload_attachments, "attachment_candidates"):
            kwargs["attachment_candidates"] = _manifest_attachment_upload_candidates(self.current_manifest)
        result = dict(upload_attachments(attachments, **kwargs) or {})
        data = {"attachments": result.get("attachments") or attachments}
        data.update({key: value for key, value in result.items() if key != "attachments"})
        return StepResult(action="attachment.upload", success=True, message="附件已上传", data=data)

    def _execute_form_fill(self, step: ActionStep) -> StepResult:
        self._ensure_menu_open_for_component("表单")
        def perform():
            fields = _extract_field_values(step.target)
            filled: list[dict[str, Any]] = []
            contract_paths: list[dict[str, Any]] = []
            for field_name, value in fields:
                value = self._resolve_step_value(value)
                bound = self._require_form_field(field_name, value)
                if bound.contract_path is not None:
                    contract_paths.append(bound.contract_path)
                try:
                    fill_form_field = getattr(self.runtime, "fill_form_field", None)
                    if fill_form_field is not None:
                        fill_result = fill_form_field(bound, value)
                    else:
                        self.runtime.fill_field(bound, str(value))
                        fill_result = None
                except Exception as exc:
                    raise RuntimeError(f"表单字段[{field_name}]录入失败: {exc}") from exc
                property_uri = bound.candidate.property_uri
                if property_uri:
                    self._field_property_uri_by_name[str(field_name)] = property_uri
                filled_item = {"field": field_name, "equals": str(value), "fieldid": bound.candidate.fieldid}
                if property_uri:
                    filled_item["property_uri"] = property_uri
                if isinstance(fill_result, dict):
                    for key, item_value in fill_result.items():
                        if key == "contract_path" and isinstance(item_value, dict):
                            contract_paths.append(item_value)
                            continue
                        if key not in filled_item:
                            filled_item[key] = item_value
                if isinstance(fill_result, dict) and fill_result.get("selected"):
                    popup_completed = _popup_reference_completed(fill_result)
                    if not popup_completed:
                        details = _popup_reference_unconfirmed_diagnostics(fill_result)
                        raise RuntimeError(f"表单字段[{field_name}]录入失败: 弹出参照未确认完成: {details}")
                filled.append(filled_item)
            data: dict[str, Any] = {"fields": filled}
            merged_contract_path = merge_contract_paths(contract_paths)
            if merged_contract_path is not None:
                data["contract_path"] = merged_contract_path
            return data

        transition = self._templates.execute("form.fill", perform)
        data = {**transition.value, **transition.changes}
        return StepResult(action="form.fill", success=True, message="表单已录入", data=data)

    def _execute_form_assert_values(self, step: ActionStep) -> StepResult:
        self._ensure_menu_open_for_component("表单")
        fields = _extract_field_values(step.target)
        checked: list[dict[str, Any]] = []
        contract_paths: list[dict[str, Any]] = []
        read_value = getattr(self.runtime, "read_field_value", None)
        if read_value is None:
            raise RuntimeError("当前运行时不支持字段值读取")
        for field_name, expected in fields:
            expected = self._resolve_step_value(expected)
            bound = self._resolve_assert_form_field(field_name)
            if bound.contract_path is not None:
                contract_paths.append(bound.contract_path)
            expected_text = str(expected)
            actual = self._read_field_value_until_match(read_value, bound, expected_text)
            if not _values_match(actual, expected_text, checkbox=_is_checkbox_bound_element(bound)):
                raise BusinessAssertionMismatch(
                    f"字段 {field_name} 值不匹配: expected={expected_text!r}, actual={actual!r}",
                    expected={"fields": {field_name: expected_text}},
                    actual={"fields": {field_name: actual}},
                    scope={
                        "fields": [
                            {
                                "field": field_name,
                                "fieldid": bound.candidate.fieldid,
                                "property_uri": bound.candidate.property_uri,
                            }
                        ]
                    },
                )
            checked.append(
                {
                    "field": field_name,
                    "equals": expected_text,
                    "actual": actual,
                    "fieldid": bound.candidate.fieldid,
                    "property_uri": bound.candidate.property_uri,
                }
            )
        data = {"fields": checked}
        merged_contract_path = merge_contract_paths(contract_paths)
        if merged_contract_path is not None:
            data["contract_path"] = merged_contract_path
        return StepResult(action="form.assert_values", success=True, message="表单字段校验通过", data=data)

    def _execute_form_capture_values(self, step: ActionStep) -> StepResult:
        self._ensure_menu_open_for_component("表单")
        target = self._resolve_step_value(step.target)
        raw_capture = target.get("capture")
        if not isinstance(raw_capture, dict) or not raw_capture:
            raise ValueError(f"表单字段捕获缺少 capture: {target}")
        capture_sources = {str(name): str(field).strip() for name, field in raw_capture.items()}
        if any(not field for field in capture_sources.values()):
            raise ValueError(f"表单字段捕获来源字段不能为空: {target}")
        read_value = getattr(self.runtime, "read_field_value", None)
        if read_value is None:
            raise RuntimeError("当前运行时不支持字段值读取")
        captured: dict[str, str] = {}
        fields: list[dict[str, Any]] = []
        empty_fields: list[str] = []
        for variable_name, field_name in capture_sources.items():
            bound = self._resolve_assert_form_field(field_name)
            value = " ".join(str(read_value(bound) or "").split())
            fields.append(
                {
                    "variable": variable_name,
                    "field": field_name,
                    "actual": value,
                    "fieldid": bound.candidate.fieldid,
                    "property_uri": bound.candidate.property_uri,
                }
            )
            if not value:
                empty_fields.append(field_name)
                continue
            captured[variable_name] = value
        if empty_fields:
            raise RuntimeError(f"表单字段捕获失败: capture={capture_sources}; 捕获值为空: {empty_fields}")
        self.runtime_context.set_many(captured)
        return StepResult(
            action="form.capture_values",
            success=True,
            message="表单字段已捕获",
            data={
                "capture": capture_sources,
                "captured": dict(captured),
                "capture_sources": dict(capture_sources),
                "fields": fields,
            },
        )

    def _execute_editable_table_add_row(self, step: ActionStep) -> StepResult:
        self._ensure_menu_open_for_component("可编辑表格")
        target = self._resolve_step_value(step.target)
        label = str(target.get("label") or target.get("action") or "新增")
        table = _extract_optional_table_name(target)
        scope = self._resolve_table_scope(table, [], region_types=("main_table",))
        runtime_table = scope.label
        editor = _normalize_editable_table_editor(target.get("editor"))
        add_row = self._require_runtime_method("add_editable_table_row")
        def perform():
            self._clear_pending_dynamic_template()
            result = dict(add_row(label=label, table_scope=scope) or {})
            data = {"label": label}
            if runtime_table:
                data["table"] = runtime_table
            if table and runtime_table != table:
                data["requested_table"] = table
            data["table_fieldid"] = scope.region_fieldid
            data["table_scope"] = scope.to_dict()
            if editor:
                data["editor"] = editor
            data.update(result)
            inline_growth_confirmed = (
                result.get("row_state_reliable") is True
                and result.get("row_state_changed") is True
            )
            if editor == "form" or not inline_growth_confirmed:
                self._wait_for_pending_dynamic_template()
            return data

        transition = self._templates.execute("editable_table.add_row", perform)
        result = transition.value
        data = {**result, **transition.changes}
        dynamic = transition.changes.get("dynamic_template")
        if dynamic:
            if editor == "inline":
                raise RuntimeError(f"可编辑表格新增行打开了表单模板，但 target.editor 要求 inline: table={table or '*'}")
            data["dynamic_template"] = dynamic
            message = "可编辑表格新增行表单已打开"
        else:
            before = result.get("row_state_before") if isinstance(result.get("row_state_before"), dict) else {}
            after = result.get("row_state") if isinstance(result.get("row_state"), dict) else {}
            if result.get("row_state_reliable") is False or result.get("row_state_changed") is False:
                rows = "、".join(str(text) for text in list(after.get("rowTexts") or [])[:5])
                fieldid_part = f"; table_fieldid={scope.region_fieldid}"
                retry_part = f"; retry_count={result['retry_count']}" if result.get("retry_count") else ""
                root_source = str(result.get("validation_root_source") or "")
                root_diag = result.get("validation_root") if isinstance(result.get("validation_root"), dict) else {}
                root_text = str(root_diag.get("text") or "").strip() if isinstance(root_diag, dict) else ""
                root_class = str(root_diag.get("className") or "").strip() if isinstance(root_diag, dict) else ""
                root_part = ""
                if root_source:
                    root_part += f"; validation_root_source={root_source}"
                if root_class:
                    root_part += f"; validation_root_class={root_class[:80]}"
                if root_text:
                    root_part += f"; validation_root={root_text[:160]}"
                chosen_part = _format_editable_table_add_row_candidate(
                    "chosen",
                    result.get("chosen_candidate"),
                )
                first_chosen_part = ""
                first_attempt = result.get("first_attempt")
                if isinstance(first_attempt, dict):
                    first_chosen_part = _format_editable_table_add_row_candidate(
                        "first_chosen",
                        first_attempt.get("chosen_candidate"),
                    )
                raise RuntimeError(
                    "可编辑表格新增行未生效: "
                    f"table={runtime_table or table or ''}{fieldid_part}; label={label}; "
                    f"before_rows={before.get('dataRowCount')}; after_rows={after.get('dataRowCount')}; "
                    f"rows={rows or '无可编辑数据行'}{root_part}{retry_part}{first_chosen_part}{chosen_part}"
                )
            if editor == "form":
                raise RuntimeError(f"可编辑表格新增行未打开表单模板: table={table or '*'}, label={label}")
            message = "可编辑表格已新增行"
        return StepResult(action="editable_table.add_row", success=True, message=message, data=data)

    def _execute_editable_table_fill_row(self, step: ActionStep) -> StepResult:
        self._ensure_menu_open_for_component("可编辑表格")
        row_number = _extract_editable_row_number(step.target)
        table = _extract_optional_table_name(step.target)
        field_specs = _extract_editable_table_field_values(step.target)
        requested_columns = [str(spec.get("field") or "") for spec in field_specs if str(spec.get("field") or "")]
        scope = self._resolve_table_scope(
            table,
            requested_columns,
            region_types=("main_table",),
            allow_manifest_column_aliases=True,
        )
        runtime_table = scope.label
        values, column_specs = _editable_table_runtime_values(field_specs)
        column_candidates = self._editable_table_column_candidates(column_specs, runtime_table)
        fill_row = self._require_runtime_method("fill_editable_table_row")
        result = dict(fill_row(values, row_number=row_number, table_scope=scope,
                               column_candidates=column_candidates) or {})
        data = {"row_number": row_number, "fields": values}
        if runtime_table:
            data["table"] = runtime_table
        if table and runtime_table != table:
            data["requested_table"] = table
        data["table_fieldid"] = scope.region_fieldid
        data["table_scope"] = scope.to_dict()
        data.update(result)
        return StepResult(action="editable_table.fill_row", success=True, message="可编辑表格行已录入", data=data)

    def _editable_table_column_candidates(self, columns: Any, table: str | None) -> dict[str, Any]:
        if self.current_manifest is None:
            return {}
        regions_by_key = {region.key: region for region in self.current_manifest.regions}
        regions_by_fieldid = {region.fieldid: region for region in self.current_manifest.regions}
        result: dict[str, Any] = {}
        for column in columns:
            label = str(column.get("field") if isinstance(column, dict) else column)
            result_key = str(column.get("key") if isinstance(column, dict) and column.get("key") else label)
            column_groups = list(column.get("column_groups") or []) if isinstance(column, dict) else []
            matches = [
                candidate
                for candidate in self.current_manifest.table_columns
                if _editable_table_column_label_matches(label, candidate)
            ]
            if table:
                matches = [
                    candidate
                    for candidate in matches
                    if _table_column_belongs_to_table(candidate, table, regions_by_key, regions_by_fieldid)
                ]
            if column_groups:
                matches = [
                    candidate
                    for candidate in matches
                    if _column_groups_match(column_groups, getattr(candidate, "column_groups", []) or [])
                ]
                if not matches:
                    raise RuntimeError(
                        "可编辑表格列未匹配父表头: "
                        f"column={label}; column_group={' > '.join(column_groups)}; "
                        f"可用列: {_format_editable_table_column_paths(self.current_manifest.table_columns, label)}"
                    )
            elif _has_ambiguous_grouped_columns(matches):
                raise RuntimeError(
                    "可编辑表格列名不唯一: "
                    f"column={label}; "
                    f"请补充 column_group; 可用列: {_format_editable_table_column_paths(matches, label)}"
                )
            if matches:
                result[result_key] = _select_best_editable_table_column_candidate(label, matches)
        return result

    def _read_field_value_until_match(self, read_value, bound, expected_text: str, timeout_ms: int = 8000) -> str:
        deadline = time.monotonic() + timeout_ms / 1000
        last_actual = ""
        is_checkbox = _is_checkbox_bound_element(bound)
        while True:
            last_actual = str(read_value(bound))
            if _values_match(last_actual, expected_text, checkbox=is_checkbox) or time.monotonic() >= deadline:
                return last_actual
            wait = getattr(self.runtime, "_require_page", None)
            if wait is not None:
                try:
                    wait().wait_for_timeout(300)
                except Exception:
                    time.sleep(0.3)
            else:
                time.sleep(0.3)

    def _clear_pending_dynamic_template(self) -> None:
        pop_payload = getattr(self.runtime, "pop_dynamic_template_payload", None)
        if pop_payload is not None:
            pop_payload()

    def _wait_for_pending_dynamic_template(self) -> None:
        wait = getattr(self.runtime, "wait_for_dynamic_template_payload", None)
        if wait is not None:
            wait()

    def _execute_action_completion(
        self,
        action: str,
        context: dict[str, Any],
        click: Callable[[], bool | None],
    ) -> ActionCompletionResult:
        return self._action_completion.execute(
            ActionCompletionRequest(
                action=action,
                context=context,
                deadline=self._current_step_deadline,
                cancelled=(
                    (lambda: bool(self.cancellation_event.is_set()))
                    if self.cancellation_event is not None
                    else None
                ),
            ),
            click,
        )

    @staticmethod
    def _action_completion_step_data(
        result: ActionCompletionResult,
    ) -> tuple[list[dict[str, str]], dict[str, Any]]:
        data = result.step_data()
        notifications = list(data.pop("notifications", []) or [])
        return notifications, data

    def _current_page_identity(self) -> str:
        manifest = getattr(self, "current_manifest", None)
        page = getattr(manifest, "page", None)
        return str(getattr(page, "fieldid", "") or "")


    def _current_manifest_has_main_table(self) -> bool:
        return bool(
            self.current_manifest
            and any(region.region_type == "main_table" for region in self.current_manifest.regions)
        )


    def _collect_notifications(self) -> list[dict[str, str]]:
        collect = getattr(self.runtime, "collect_notifications", None)
        if collect is None:
            return []
        return collect()

    def _begin_notification_capture(self) -> None:
        begin = getattr(self.runtime, "begin_notification_capture", None)
        if begin is None:
            return
        begin()

    def _resolve_step_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return self._resolve_runtime_string(value)
        if isinstance(value, dict):
            return {key: self._resolve_step_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._resolve_step_value(item) for item in value]
        return value

    def _resolve_runtime_string(self, value: str) -> Any:
        full_match = FULL_VARIABLE_PATTERN.fullmatch(value)
        if full_match:
            name = full_match.group(1).strip()
            if name.startswith("random."):
                return self._generated_random_value(name.split(".", 1)[1])
            if name in self.runtime_variables:
                return self._runtime_variable_value(name)
            return value

        def _replace(match: re.Match[str]) -> str:
            name = match.group(1).strip()
            if name.startswith("random."):
                return self._generated_random_value(name.split(".", 1)[1])
            if name in self.runtime_variables:
                resolved = self._runtime_variable_value(name)
                if isinstance(resolved, (dict, list)):
                    raise ValueError(f"运行期变量不能用于字符串拼接: {name}")
                return "" if resolved is None else str(resolved)
            return match.group(0)

        return VARIABLE_PATTERN.sub(_replace, value)

    def _runtime_variable_value(self, name: str) -> Any:
        if not self.runtime_context.has(name):
            raise ValueError(f"未定义运行期变量: {name}")
        return self.runtime_context.get(name)

    def _generated_random_value(self, name: str) -> str:
        key = f"random.{name}"
        if key not in self._generated_values:
            self._generated_values[key] = _generate_random_value(name)
        return self._generated_values[key]

    def _execute_table_row_action_click(self, step: ActionStep) -> StepResult:
        self._ensure_menu_open_for_component("表格行按钮")
        if not self._templates.execute("table.scope", self._current_manifest_has_main_table).value:
            raise RuntimeError("当前页面不包含表格组件")
        target = self._resolve_step_value(step.target)
        action_label = str(target["action"])
        def perform():
            table = _extract_optional_table_name(target)
            required_columns = _extract_row_match_columns(dict(target.get("match") or {}))
            scope = self._resolve_table_scope(table, required_columns, region_types=("main_table",))
            runtime_table = scope.label
            table_fieldid = scope.region_fieldid
            table_columns = list(scope.columns)
            focus_table_row = self._require_runtime_method("focus_table_row")
            row_numbers = _extract_row_numbers(target)
            match: dict[str, Any] | None = None
            try:
                self._clear_pending_dynamic_template()
                if row_numbers:
                    row_number = row_numbers[0]
                    focus_by_index = getattr(self.runtime, "focus_table_row_by_index", None)
                    if focus_by_index is None:
                        raise RuntimeError("当前运行时不支持按行号定位表格行")
                    focus_by_index(row_number, table_scope=scope)
                else:
                    match = dict(target["match"])
                    focus_table_row(match, table_scope=scope)
            except Exception as exc:
                details = f"未找到表格行: {target}"
                if runtime_table:
                    details = f"{details}; 表格: {runtime_table}"
                if table_fieldid:
                    details = f"{details}; table_fieldid={table_fieldid}"
                reason = str(exc).strip()
                if reason:
                    details = f"{details}; 原因: {reason}"
                raise RuntimeError(details) from exc
            self._templates.refresh_binding(source="row.hover")
            click_row_action = getattr(self.runtime, "click_row_action", None)
            self._begin_notification_capture()
            if click_row_action is not None:
                click_row_action(action_label)
            else:
                bound = self.current_binding.actions_by_alias.get(action_label)
                if bound is None:
                    raise RuntimeError(f"未绑定表格行动作: {action_label}")
                self.runtime.click(bound)
            data = {"action": action_label, **({"row_number": row_numbers[0]} if row_numbers else {"match": match})}
            if runtime_table:
                data["table"] = runtime_table
            if table_fieldid:
                data["table_fieldid"] = table_fieldid
            data["table_scope"] = scope.to_dict()
            row_search = getattr(self.runtime, "last_table_tree_search", None)
            if row_search:
                data["row_search"] = row_search
            self._wait_for_pending_dynamic_template()
            return data

        transition = self._templates.execute("table_row_action.click", perform)
        data = {**transition.value, **transition.changes}
        notifications = self._collect_notifications()
        self._last_notifications = notifications
        if notifications:
            data["notifications"] = notifications
        return StepResult(
            action="table_row_action.click",
            success=True,
            message=f"表格行按钮已点击: {action_label}",
            data=data,
        )

    def _execute_table_row_selection_select(self, step: ActionStep) -> StepResult:
        self._ensure_menu_open_for_component("表格行选择")
        if not self._templates.execute("table.scope", self._current_manifest_has_main_table).value:
            raise RuntimeError("当前页面不包含表格组件")
        target = self._resolve_step_value(step.target)
        table = _extract_optional_table_name(target)
        match_columns = _extract_row_selection_target_columns(target)
        scope = self._resolve_table_scope(table, match_columns, region_types=("main_table",))
        table_fieldid = scope.region_fieldid
        table_columns = list(scope.columns)
        if _wants_select_all(target):
            return self._select_all_table_rows(
                table=table,
                table_fieldid=table_fieldid,
                table_columns=table_columns,
                scope=scope,
            )
        row_numbers = _extract_row_numbers(target)
        if row_numbers:
            return self._select_table_rows_by_number(
                row_numbers,
                table=table,
                table_fieldid=table_fieldid,
                table_columns=table_columns,
                scope=scope,
            )
        rows = _extract_row_selection_rows(target)
        if rows:
            return self._select_table_rows_by_matches(
                rows,
                table=table,
                table_fieldid=table_fieldid,
                table_columns=table_columns,
                scope=scope,
            )
        match = _extract_row_selection_match(target)
        try:
            select_row = self._require_runtime_method("select_table_row")
            select_row(match, table_scope=scope)
        except Exception as exc:
            reason = str(exc).strip()
            message = f"未找到可选择的表格行: {match}"
            if table:
                message = f"{message}; 表格: {table}"
            if reason:
                message = f"{message}; 原因: {reason}"
            row_search = getattr(self.runtime, "last_table_tree_search", None)
            if row_search:
                message = f"{message}; row_search={row_search}"
            raise RuntimeError(message) from exc
        data = {"match": match}
        if table:
            data["table"] = table
        if table_fieldid:
            data["table_fieldid"] = table_fieldid
        data["table_scope"] = scope.to_dict()
        row_search = getattr(self.runtime, "last_table_tree_search", None)
        if row_search:
            data["row_search"] = dict(row_search)
        self._attach_table_selection_debug(data, table=table, table_fieldid=table_fieldid)
        return StepResult(
            action="table_row_selection.select",
            success=True,
            message="表格行已选中",
            data=data,
        )

    def _select_all_table_rows(
        self,
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        scope: ResolvedTableScope | None = None,
    ) -> StepResult:
        try:
            select_all = self._require_runtime_method("select_all_table_rows")
            select_all(table_scope=scope)
        except Exception as exc:
            reason = str(exc).strip()
            message = "未找到表头全选 checkbox"
            if table:
                message = f"{message}; 表格: {table}"
            if reason:
                message = f"{message}; 原因: {reason}"
            raise RuntimeError(message) from exc
        data: dict[str, Any] = {"select_all": True}
        if table:
            data["table"] = table
        if table_fieldid:
            data["table_fieldid"] = table_fieldid
        if scope is not None:
            data["table_scope"] = scope.to_dict()
        self._attach_table_selection_debug(data, table=table, table_fieldid=table_fieldid)
        return StepResult(
            action="table_row_selection.select",
            success=True,
            message="表格行已全选",
            data=data,
        )

    def _select_table_rows_by_matches(
        self,
        matches: list[dict[str, Any]],
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        scope: ResolvedTableScope | None = None,
    ) -> StepResult:
        try:
            select_row = self._require_runtime_method("select_table_row")
            for match in matches:
                select_row(match, table_scope=scope)
        except Exception as exc:
            reason = str(exc).strip()
            message = f"未找到可选择的表格行: {matches}"
            if table:
                message = f"{message}; 表格: {table}"
            if reason:
                message = f"{message}; 原因: {reason}"
            raise RuntimeError(message) from exc
        data: dict[str, Any] = {"rows": matches}
        if table:
            data["table"] = table
        if table_fieldid:
            data["table_fieldid"] = table_fieldid
        if scope is not None:
            data["table_scope"] = scope.to_dict()
        return StepResult(
            action="table_row_selection.select",
            success=True,
            message="表格行已选中",
            data=data,
        )

    def _select_table_rows_by_number(
        self,
        row_numbers: list[int],
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        scope: ResolvedTableScope | None = None,
    ) -> StepResult:
        try:
            select_rows = getattr(self.runtime, "select_table_rows_by_indices", None)
            if select_rows is not None:
                select_rows(row_numbers, table_scope=scope)
            else:
                select_row = self._require_runtime_method("select_table_row_by_index")
                for row_number in row_numbers:
                    select_row(row_number, table_scope=scope)
        except Exception as exc:
            reason = str(exc).strip()
            message = f"未找到可选择的表格行号: {row_numbers}"
            if table:
                message = f"{message}; 表格: {table}"
            if reason:
                message = f"{message}; 原因: {reason}"
            raise RuntimeError(message) from exc
        data: dict[str, Any] = {"row_numbers": row_numbers}
        if table:
            data["table"] = table
        if table_fieldid:
            data["table_fieldid"] = table_fieldid
        if scope is not None:
            data["table_scope"] = scope.to_dict()
        self._attach_table_selection_debug(
            data,
            table=table,
            table_fieldid=table_fieldid,
            row_numbers=row_numbers,
        )
        return StepResult(
            action="table_row_selection.select",
            success=True,
            message="表格行已选中",
            data=data,
        )

    def _attach_table_selection_debug(
        self,
        data: dict[str, Any],
        *,
        table: str | None = None,
        table_fieldid: str | None = None,
        row_numbers: list[int] | None = None,
    ) -> None:
        debug = getattr(self.runtime, "last_table_selection_debug", None)
        if not isinstance(debug, dict) or not debug:
            return
        payload = dict(debug)
        if table and "table" not in payload:
            payload["table"] = table
        if table_fieldid and "table_fieldid" not in payload:
            payload["table_fieldid"] = table_fieldid
        if row_numbers and "row_number" not in payload:
            if len(row_numbers) == 1:
                payload["row_number"] = row_numbers[0]
            else:
                payload["row_numbers"] = list(row_numbers)
        data["selection_debug"] = payload

    def _resolve_table_scope(
        self,
        table: str | None,
        required_columns: list[str],
        *,
        region_types: tuple[str, ...],
        allow_manifest_column_aliases: bool = False,
    ) -> ResolvedTableScope:
        assert self.current_manifest is not None
        required_columns = list(dict.fromkeys(column for column in required_columns if str(column).strip()))
        try:
            return TableScopeResolver(RuntimeTableScopeAdapter(self.runtime)).resolve_for_execution(
                self.current_manifest,
                TableScopeRequest(
                    target=table,
                    required_columns=tuple(required_columns),
                    region_types=region_types,
                    allow_manifest_column_aliases=allow_manifest_column_aliases,
                ),
            )
        except TableScopeError as exc:
            evidence = f"; candidates={exc.evidence}" if exc.evidence else ""
            raise RuntimeError(f"{exc.message}{evidence}") from exc

    def _resolve_table_value_assertion_scope(
        self,
        target: dict[str, Any],
        required_columns: list[str],
    ) -> ResolvedTableScope:
        if not self._templates.execute("table.scope", self._current_manifest_has_main_table).value:
            raise RuntimeError("当前页面不包含表格组件")
        table = _extract_optional_table_name(target)
        return self._resolve_table_scope(table, required_columns, region_types=("main_table",))

    def _capture_table_assertion_snapshot(
        self,
        *,
        scope: ResolvedTableScope,
        assertion_columns: list[str],
        table: str | None,
    ) -> dict[str, Any] | None:
        if self.observation_session is None:
            return None
        collect_rows = getattr(self.runtime, "collect_table_assertion_rows", None)
        if collect_rows is None:
            return {"capture_unavailable_reason": "runtime_unsupported"}
        try:
            raw = collect_rows(table_scope=scope)
        except Exception as exc:
            return {"capture_unavailable_reason": "capture_failed", "detail": str(exc)}
        raw = dict(raw or {})
        snapshot = build_table_assertion_snapshot(
            list(raw.get("rows") or []),
            assertion_columns=assertion_columns,
            identity_columns=[str(item) for item in raw.get("identity_columns") or []],
        )
        snapshot.update(
            {
                "table_identity": {
                    "label": scope.label,
                    "region_fieldid": scope.region_fieldid,
                    "runtime_fieldid": scope.runtime_fieldid,
                },
                "scope": scope.to_dict(),
                "query_completion_signal": self._last_query_completion_signal
                or {"capture_unavailable_reason": "not_available"},
                "pagination": raw.get("pagination")
                or {"capture_unavailable_reason": "not_available"},
                "empty_state": raw.get("empty_state"),
            }
        )
        return snapshot

    def _execute_query_search(self, step: ActionStep) -> StepResult:
        self._ensure_menu_open_for_component("查询")
        if not self.current_manifest:
            raise RuntimeError("当前页面不包含查询区")
        target = self._resolve_step_value(step.target)
        conditions = _extract_query_conditions(target)
        expanded = self._expand_query_conditions_if_needed([str(item["field"]) for item in conditions])
        filled: list[dict[str, Any]] = []
        contract_paths: list[dict[str, Any]] = []
        for condition in conditions:
            field_name = str(condition["field"])
            value = condition["equals"]
            bound = self._require_query_field(field_name)
            if bound.contract_path is not None:
                contract_paths.append(bound.contract_path)
            fill_query_field = getattr(self.runtime, "fill_query_field", None)
            if fill_query_field is not None:
                fill_result = fill_query_field(bound, value)
            else:
                self.runtime.fill_field(bound, str(value))
                fill_result = None
            filled_item = {"field": field_name, "equals": value}
            if isinstance(fill_result, dict):
                for key, item_value in fill_result.items():
                    if key == "contract_path" and isinstance(item_value, dict):
                        contract_paths.append(item_value)
                        continue
                    if key not in filled_item:
                        filled_item[key] = item_value
            filled.append(filled_item)
        query_label = str(target.get("button") or "查询")
        click_query_action = getattr(self.runtime, "click_query_action", None)
        table_target = str(target.get("table") or "").strip() or None
        main_tables = self._prefer_runtime_visible_regions(
            [region for region in self.current_manifest.regions if region.region_type == "main_table"]
        )
        main_tables = self._prefer_config_visible_regions(main_tables)
        target_table_fieldid = ""
        query_identity: dict[str, str] = {}
        if table_target or len(main_tables) == 1:
            table_scope = self._resolve_table_scope(
                table_target or main_tables[0].fieldid, [], region_types=("main_table",)
            )
            target_table_fieldid = table_scope.runtime_fieldid
            if len(main_tables) == 1:
                nodes = [node for node in self.current_manifest.template_nodes
                         if node.fieldid == table_scope.region_fieldid]
                if len(nodes) == 1:
                    info = (nodes[0].raw.get("enty") or {}).get("info") or {}
                    query_identity = {key: str(info.get(source) or "").strip() for key, source in (
                        ("entity_uri", "uri"), ("domain", "domain"), ("busi_obj", "code"),
                    )}
                    if not all(query_identity.values()):
                        query_identity = {}
        def click_query() -> None:
            if click_query_action is not None:
                kwargs: dict[str, Any] = {}
                if _callable_accepts_keyword(click_query_action, "fieldids"):
                    kwargs["fieldids"] = self._query_action_fieldids()
                click_query_action(query_label, **kwargs)
            else:
                self.runtime.click(self._require_action(query_label))

        completion_result = self._execute_action_completion(
            "query.search",
            {
                "source_page_id": self._current_page_identity(),
                "target_table_fieldid": target_table_fieldid,
                **({"target_table_query": query_identity, "target_table_token": table_scope.token}
                   if query_identity else {}),
            },
            click_query,
        )
        notifications, completion = self._action_completion_step_data(completion_result)
        self._last_query_completion_signal = str(completion.get("completion_signal") or "") or None
        self._last_notifications = notifications
        data = {"conditions": filled, "button": query_label, **completion}
        merged_contract_path = merge_contract_paths(contract_paths + ([completion["contract_path"]] if completion.get("contract_path") else []))
        if merged_contract_path is not None:
            data["contract_path"] = merged_contract_path
        if notifications:
            data["notifications"] = notifications
        return StepResult(
            action="query.search",
            success=True,
            message="查询已执行",
            data={**data, **({"expanded_query": True} if expanded else {})},
        )

    def _execute_query_reset(self) -> StepResult:
        self._ensure_menu_open_for_component("查询")
        if not self.current_manifest:
            raise RuntimeError("当前页面不包含查询区")
        query_region_fieldids = [
            region.fieldid
            for region in self.current_manifest.regions
            if region.region_type == "query_box" and region.fieldid
        ]
        if not query_region_fieldids:
            raise RuntimeError("当前页面不包含查询区")
        click_query_reset = getattr(self.runtime, "click_query_reset", None)
        if click_query_reset is None:
            raise RuntimeError("当前运行时不支持查询重置")
        data = dict(click_query_reset(query_region_fieldids) or {})
        return StepResult(
            action="query.reset",
            success=True,
            message="查询条件已重置",
            data=data,
        )

    def _expand_query_conditions_if_needed(self, field_names: list[str]) -> bool:
        if not field_names:
            return False
        if all(self._has_query_field(field_name) for field_name in field_names):
            return False
        expand = getattr(self.runtime, "expand_query_conditions", None)
        if expand is None or not expand():
            return False
        if self.current_manifest is None:
            return True
        self._templates.refresh_binding(source="query.expand")
        return True

    def _execute_table_assert_column_values(self, step: ActionStep) -> StepResult:
        self._ensure_menu_open_for_component("表格")
        target = self._resolve_step_value(step.target)
        column = str(target["column"])
        expected = str(target["equals"])
        table = _extract_optional_table_name(target)
        scope = self._resolve_table_value_assertion_scope(target, [column])
        table_fieldid = scope.region_fieldid
        table_columns = list(scope.columns)
        collect_values = getattr(self.runtime, "collect_table_column_values", None)
        if collect_values is None:
            raise RuntimeError("当前运行时不支持表格列值采集")
        values = collect_values(column, table_scope=scope)
        scope_data = scope.to_dict()
        if not values:
            debug = self._collect_table_debug()
            suffix = f": {debug}" if debug else ""
            scope_text = f"; table={table or ''}; table_fieldid={table_fieldid or ''}; headers={table_columns}"
            raise BusinessAssertionMismatch(
                f"表格列无可验证数据: {column}{scope_text}{suffix}",
                expected={"column": column, "equals": expected},
                actual={"column": column, "values": []},
                scope=scope_data,
                evidence={
                    "table_assertion_snapshot": self._capture_table_assertion_snapshot(
                        scope=scope,
                        assertion_columns=[column],
                        table=table,
                    )
                },
            )
        mismatches = [value for value in values if value != expected]
        if mismatches:
            scope_text = f"table={table or ''}, table_fieldid={table_fieldid or ''}, headers={table_columns}"
            raise BusinessAssertionMismatch(
                f"表格列 {column} 存在不匹配数据: {mismatches}; {scope_text}",
                expected={"column": column, "equals": expected},
                actual={"column": column, "values": values},
                scope=scope_data,
                evidence={
                    "table_assertion_snapshot": self._capture_table_assertion_snapshot(
                        scope=scope,
                        assertion_columns=[column],
                        table=table,
                    )
                },
            )
        data: dict[str, Any] = {"column": column, "equals": expected, "values": values}
        if table:
            data["table"] = table
        if table_fieldid:
            data["table_fieldid"] = table_fieldid
        data["table_scope"] = scope_data
        return StepResult(
            action="table.assert_column_values",
            success=True,
            message=f"表格列校验通过: {column}",
            data=data,
        )

    def _execute_table_assert_empty(self, step: ActionStep) -> StepResult:
        self._ensure_menu_open_for_component("表格")
        target = self._resolve_step_value(step.target)
        column = str(target.get("column") or "项目名称")
        table = _extract_optional_table_name(target)
        scope = self._resolve_table_value_assertion_scope(target, [])
        collect_values = getattr(self.runtime, "collect_table_column_values", None)
        if collect_values is None:
            raise RuntimeError("当前运行时不支持表格列值采集")
        values = collect_values(column, table_scope=scope)
        if values:
            raise BusinessAssertionMismatch(
                f"表格预期为空，但列 {column} 存在数据: {values}",
                expected={"column": column, "empty": True},
                actual={"column": column, "values": values},
                scope=scope.to_dict(),
                evidence={
                    "table_assertion_snapshot": self._capture_table_assertion_snapshot(
                        scope=scope,
                        assertion_columns=[column],
                        table=table,
                    )
                },
            )
        return StepResult(
            action="table.assert_empty",
            success=True,
            message="表格为空",
            data={"column": column, "values": [], "table_scope": scope.to_dict()},
        )

    def _execute_table_assert_columns(self, step: ActionStep) -> StepResult:
        self._ensure_menu_open_for_component("表格")
        if not self._templates.execute("table.scope", self._current_manifest_has_main_table).value:
            raise RuntimeError("当前页面不包含表格组件")
        target = self._resolve_step_value(step.target)
        table = _extract_optional_table_name(target)
        present = [str(item).strip() for item in target.get("present") or [] if str(item).strip()]
        absent = [str(item).strip() for item in target.get("absent") or [] if str(item).strip()]
        scope = self._resolve_table_scope(table, present, region_types=("main_table",))
        table_fieldid = scope.region_fieldid
        table_columns = list(scope.columns)
        collect_headers = getattr(self.runtime, "collect_table_headers", None)
        if collect_headers is None:
            raise RuntimeError("当前运行时不支持表格表头采集")
        headers = self._collect_table_headers(
            collect_headers,
            table=table,
            table_fieldid=table_fieldid,
            table_columns=table_columns,
            scope=scope,
        )
        if not headers:
            raise RuntimeError(
                f"无法采集表格表头: table={table or ''}; table_fieldid={table_fieldid or ''}; headers=[]"
            )
        normalized_headers = {_normalize_table_header_label(header) for header in headers}
        missing = [column for column in present if _normalize_table_header_label(column) not in normalized_headers]
        unexpected = [column for column in absent if _normalize_table_header_label(column) in normalized_headers]
        if missing:
            raise BusinessAssertionMismatch(
                f"表格列缺失: {missing}; headers={headers}",
                expected={"present": present, "absent": absent},
                actual={"headers": headers},
                scope=scope.to_dict(),
                evidence={
                    "table_assertion_snapshot": self._capture_table_assertion_snapshot(
                        scope=scope,
                        assertion_columns=[*present, *absent],
                        table=table,
                    )
                },
            )
        if unexpected:
            raise BusinessAssertionMismatch(
                f"表格列不应存在: {unexpected}; headers={headers}",
                expected={"present": present, "absent": absent},
                actual={"headers": headers},
                scope=scope.to_dict(),
                evidence={
                    "table_assertion_snapshot": self._capture_table_assertion_snapshot(
                        scope=scope,
                        assertion_columns=[*present, *absent],
                        table=table,
                    )
                },
            )
        data: dict[str, Any] = {"headers": headers}
        if table:
            data["table"] = table
        if table_fieldid:
            data["table_fieldid"] = table_fieldid
        if present:
            data["present"] = present
        if absent:
            data["absent"] = absent
        data["table_scope"] = scope.to_dict()
        return StepResult(
            action="table.assert_columns",
            success=True,
            message="表格列集合校验通过",
            data=data,
        )

    def _collect_table_headers(
        self,
        method: Any,
        *,
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        scope: ResolvedTableScope | None = None,
    ) -> list[str]:
        raw_headers = method(table_scope=scope)
        return [str(header) for header in list(raw_headers or []) if str(header or "").strip()]

    def _execute_table_capture_row_values(self, step: ActionStep) -> StepResult:
        self._ensure_menu_open_for_component("表格")
        target = self._resolve_step_value(step.target)
        match = dict(target.get("match") or {})
        if not match:
            raise ValueError(f"表格行捕获缺少 match: {target}")
        raw_capture = target.get("capture")
        if not isinstance(raw_capture, dict) or not raw_capture:
            raise ValueError(f"表格行捕获缺少 capture: {target}")
        capture_sources = {str(name): str(column).strip() for name, column in raw_capture.items()}
        if any(not column for column in capture_sources.values()):
            raise ValueError(f"表格行捕获来源列不能为空: {target}")
        required_columns = [*_extract_row_match_columns(match), *capture_sources.values()]
        table = _extract_optional_table_name(target)
        scope = self._resolve_table_value_assertion_scope(target, required_columns)
        table_fieldid = scope.region_fieldid
        table_columns = list(scope.columns)
        collect_row_values = getattr(self.runtime, "collect_table_row_values", None)
        if collect_row_values is None:
            raise RuntimeError("当前运行时不支持表格行值采集")
        try:
            raw_values = collect_row_values(match, list(capture_sources.values()), table_scope=scope)
        except Exception as exc:
            reason = str(exc).strip()
            message = f"表格行捕获失败: match={match}; capture={capture_sources}"
            if table:
                message = f"{message}; 表格: {table}"
            if reason:
                message = f"{message}; 原因: {reason}"
            row_search = getattr(self.runtime, "last_table_tree_search", None)
            if row_search:
                message = f"{message}; row_search={row_search}"
            raise RuntimeError(message) from exc
        values = {str(key): "" if value is None else str(value) for key, value in dict(raw_values or {}).items()}
        captured: dict[str, str] = {}
        missing_columns: list[str] = []
        empty_columns: list[str] = []
        for variable_name, column in capture_sources.items():
            if column not in values:
                missing_columns.append(column)
                continue
            value = values.get(column, "")
            if not str(value).strip():
                empty_columns.append(column)
                continue
            captured[variable_name] = value
        if missing_columns or empty_columns:
            details = []
            if missing_columns:
                details.append(f"来源列不存在: {missing_columns}")
            if empty_columns:
                details.append(f"捕获值为空: {empty_columns}")
            raise RuntimeError(
                f"表格行捕获失败: match={match}; capture={capture_sources}; " + "; ".join(details)
            )
        self.runtime_context.set_many(captured)
        data: dict[str, Any] = {
            "match": match,
            "capture": capture_sources,
            "captured": dict(captured),
            "capture_sources": dict(capture_sources),
        }
        if table:
            data["table"] = table
        if table_fieldid:
            data["table_fieldid"] = table_fieldid
        data["table_scope"] = scope.to_dict()
        row_search = getattr(self.runtime, "last_table_tree_search", None)
        if row_search:
            data["row_search"] = dict(row_search)
        return StepResult(
            action="table.capture_row_values",
            success=True,
            message="表格行字段已捕获",
            data=data,
        )

    def _execute_table_click_cell_link(self, step: ActionStep) -> StepResult:
        self._ensure_menu_open_for_component("表格")
        target = self._resolve_step_value(step.target)
        column = str(target.get("column") or "").strip()
        if not column:
            raise ValueError(f"表格单元格链接点击缺少 column: {target}")
        row_numbers = _extract_row_numbers(target)
        match: dict[str, Any] | None = None
        required_columns = [column]
        if row_numbers:
            row_number = row_numbers[0]
        else:
            row_number = None
            match = dict(target.get("match") or {})
            if not match:
                raise ValueError(f"表格单元格链接点击缺少 match / row_number: {target}")
            required_columns.extend(_extract_row_match_columns(match))
        table = _extract_optional_table_name(target)
        scope = self._resolve_table_value_assertion_scope(target, required_columns)
        table_fieldid = scope.region_fieldid
        table_columns = list(scope.columns)
        click_cell_link = self._require_runtime_method("click_table_cell_link")
        link_text = str(target.get("link_text") or "").strip() or None
        def perform():
            try:
                self._begin_notification_capture()
                click_kwargs: dict[str, Any] = {
                    "column": column,
                    "match": match,
                    "row_number": row_number,
                    "link_text": link_text,
                }
                click_kwargs["table_scope"] = scope
                result = click_cell_link(**click_kwargs)
            except Exception as exc:
                reason = str(exc).strip()
                row_locator = {"row_number": row_number} if row_number is not None else {"match": match}
                message = f"表格单元格链接点击失败: column={column}; {row_locator}"
                if table:
                    message = f"{message}; 表格: {table}"
                if table_fieldid:
                    message = f"{message}; table_fieldid={table_fieldid}"
                if reason:
                    message = f"{message}; 原因: {reason}"
                row_search = getattr(self.runtime, "last_table_tree_search", None)
                if row_search:
                    message = f"{message}; row_search={row_search}"
                raise RuntimeError(message) from exc
            data: dict[str, Any] = {"column": column}
            if match is not None:
                data["match"] = match
            if row_number is not None:
                data["row_number"] = row_number
            if link_text:
                data["link_text"] = link_text
            if table:
                data["table"] = table
            if table_fieldid:
                data["table_fieldid"] = table_fieldid
            data["table_scope"] = scope.to_dict()
            if isinstance(result, dict):
                data.update({key: value for key, value in result.items() if key not in data})
            row_search = getattr(self.runtime, "last_table_tree_search", None)
            if row_search:
                data["row_search"] = row_search
            self._wait_for_pending_dynamic_template()
            return data

        transition = self._templates.execute("table.click_cell_link", perform)
        data = {**transition.value, **transition.changes}
        notifications = self._collect_notifications()
        self._last_notifications = notifications
        if notifications:
            data["notifications"] = notifications
        return StepResult(
            action="table.click_cell_link",
            success=True,
            message=f"表格单元格链接已点击: {column}",
            data=data,
        )

    def _execute_table_assert_row_values(self, step: ActionStep) -> StepResult:
        self._ensure_menu_open_for_component("表格")
        target = self._resolve_step_value(step.target)
        match = dict(target.get("match") or {})
        if not match:
            raise ValueError(f"表格行校验缺少 match: {target}")
        fields = _extract_field_values(target)
        required_columns = [*_extract_row_match_columns(match), *[str(field_name) for field_name, _ in fields]]
        table = _extract_optional_table_name(target)
        scope = self._resolve_table_value_assertion_scope(target, required_columns)
        table_fieldid = scope.region_fieldid
        table_columns = list(scope.columns)
        collect_row_values = getattr(self.runtime, "collect_table_row_values", None)
        if collect_row_values is None:
            raise RuntimeError("当前运行时不支持表格行值采集")
        expected_by_field = {str(field_name): str(expected) for field_name, expected in fields}
        actual_values = self._collect_table_row_values_until_match(
            collect_row_values,
            match,
            list(expected_by_field),
            expected_by_field,
            table=table,
            table_fieldid=table_fieldid,
            table_columns=table_columns,
            scope=scope,
        )
        checked: list[dict[str, str]] = []
        mismatches: list[dict[str, str]] = []
        for field_name, expected in fields:
            field_text = str(field_name)
            expected_text = str(expected)
            actual = str(actual_values.get(field_text) or "")
            item = {"field": field_text, "equals": expected_text, "actual": actual}
            checked.append(item)
            if not _values_match(actual, expected_text):
                mismatches.append(item)
        if mismatches:
            scope_text = f"table={table or ''}, table_fieldid={table_fieldid or ''}, headers={table_columns}"
            raise BusinessAssertionMismatch(
                f"表格行字段值不匹配: match={match}, mismatches={mismatches}; {scope_text}",
                expected={"match": match, "fields": expected_by_field},
                actual={"fields": actual_values},
                scope=scope.to_dict(),
                evidence={
                    "table_assertion_snapshot": self._capture_table_assertion_snapshot(
                        scope=scope,
                        assertion_columns=required_columns,
                        table=table,
                    )
                },
            )
        data: dict[str, Any] = {"match": match, "fields": checked}
        if table:
            data["table"] = table
        if table_fieldid:
            data["table_fieldid"] = table_fieldid
        data["table_scope"] = scope.to_dict()
        return StepResult(
            action="table.assert_row_values",
            success=True,
            message="表格行字段校验通过",
            data=data,
        )

    def _collect_table_row_values_until_match(
        self,
        collect_row_values,
        match: dict[str, Any],
        columns: list[str],
        expected_by_field: dict[str, str],
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        scope: ResolvedTableScope | None = None,
        timeout_ms: int = 8000,
    ) -> dict[str, str]:
        deadline = time.monotonic() + timeout_ms / 1000
        last_values: dict[str, str] = {}
        while True:
            raw_values = collect_row_values(match, columns, table_scope=scope)
            last_values = {str(key): str(value) for key, value in dict(raw_values or {}).items()}
            if all(_values_match(last_values.get(column, ""), expected) for column, expected in expected_by_field.items()):
                return last_values
            if time.monotonic() >= deadline:
                return last_values
            wait = getattr(self.runtime, "_require_page", None)
            if wait is not None:
                try:
                    wait().wait_for_timeout(300)
                    continue
                except Exception:
                    pass
            time.sleep(0.3)

    def _collect_table_debug(self) -> str:
        collect = getattr(self.runtime, "collect_table_debug_text", None)
        if collect is None:
            return ""
        return collect()

    def _require_query_field(self, name: str):
        if self.current_binding is None:
            raise RuntimeError("执行查询动作前必须先 open_menu")
        candidates = self._query_field_candidates(name)
        if not candidates and self.current_manifest is not None and any(
            _matches_any_alias(name, candidate.aliases()) for candidate in self.current_manifest.query_fields
        ):
            deadline = time.monotonic() + 5
            while not candidates:
                self._templates.refresh_binding()
                candidates = self._query_field_candidates(name)
                if candidates or time.monotonic() >= deadline:
                    break
                self._wait_for_runtime_settle(300)
        if not candidates:
            if self._has_current_template_stable_edit_action():
                raise RuntimeError(f"未绑定查询字段: {name}")
            capture = getattr(self.runtime, "capture_runtime_elements", None)
            if capture is not None and self.current_manifest is not None:
                deadline = time.monotonic() + (10000 / 1000 if getattr(self.runtime, "_page", None) is not None else 0)
                while True:
                    runtime_only = bind_runtime_form_field(name, capture(self.current_manifest))
                    if runtime_only is not None:
                        return runtime_only
                    if time.monotonic() >= deadline:
                        break
                    page = getattr(self.runtime, "_require_page", lambda: None)()
                    if page is not None:
                        page.wait_for_timeout(250)
            raise RuntimeError(f"未绑定查询字段: {name}")
        return candidates[0]

    def _has_query_field(self, name: str) -> bool:
        if self.current_binding is None:
            return False
        return bool(self._query_field_candidates(name))

    def _query_field_candidates(self, name: str):
        if self.current_binding is None:
            return []
        explicit_query_fields = [
            bound
            for bound in self.current_binding.bound_fields
            if name in bound.candidate.aliases() and self._is_query_field(bound.candidate)
        ]
        if explicit_query_fields:
            return explicit_query_fields
        if self._has_current_template_stable_edit_action():
            return []
        return [
            bound
            for bound in self.current_binding.bound_fields
            if name in bound.candidate.aliases() and not self._is_table_like_field(bound.candidate)
        ]

    def _has_current_template_stable_edit_action(self) -> bool:
        if self.current_manifest is None:
            return False
        return any(
            _STABLE_EDIT_ACTION_ALIASES.intersection(action.aliases())
            for action in self.current_manifest.actions
        )

    def _require_form_field(self, name: str, value: Any | None = None):
        if self.current_binding is None:
            raise RuntimeError("执行表单动作前必须先 open_menu")
        candidates = self._form_field_candidates(name, value)
        if not candidates and self.current_manifest is not None and any(
            _matches_any_alias(name, candidate.aliases())
            and not self._is_table_like_field(candidate)
            and not self._is_query_field(candidate)
            for candidate in self.current_manifest.fields
        ):
            candidates = self._refresh_binding_until_form_field(name, value)
        if not candidates:
            contract_path = self._incompatible_form_contract_path(name)
            if contract_path is not None:
                raise ContractPathError(f"表单字段[{name}]的平台精确身份状态不兼容", contract_path)
            if self._should_reject_missing_dynamic_form_field_fallback():
                raise RuntimeError(self._missing_form_field_message(name))
            runtime_bound = self._resolve_runtime_form_field(name)
            if runtime_bound is not None:
                return runtime_bound
        if not candidates:
            raise RuntimeError(self._missing_form_field_message(name))
        return candidates[0]

    def _should_reject_missing_dynamic_form_field_fallback(self) -> bool:
        return self._templates.has_parent and self._has_current_template_stable_edit_action()

    def _missing_form_field_message(self, name: str) -> str:
        labels: list[str] = []
        if self.current_manifest is not None:
            for candidate in self.current_manifest.fields:
                if self._is_table_like_field(candidate) or self._is_query_field(candidate):
                    continue
                label = str(candidate.label or candidate.title or candidate.key or candidate.data_field or "").strip()
                if label and label not in labels:
                    labels.append(label)
        available = "、".join(labels) or "无"
        return f"未找到表单字段: {name}; 当前表单字段: {available}"

    def _incompatible_form_contract_path(self, name: str) -> dict[str, Any] | None:
        if self.current_binding is None:
            return None
        return self.current_binding.incompatible_fields.get(str(name))

    def _form_field_candidates(self, name: str, value: Any | None = None):
        if self.current_binding is None:
            return []
        candidates = [
            bound
            for bound in self.current_binding.bound_fields
            if _matches_any_alias(name, bound.candidate.aliases())
            and not self._is_table_like_field(bound.candidate)
            and not self._is_query_field(bound.candidate)
        ]
        candidates.sort(key=lambda bound: self._form_field_sort_key(bound, value))
        return candidates

    def _refresh_binding_until_form_field(self, name: str, value: Any | None = None, timeout_ms: int = 5000):
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            self._templates.refresh_binding()
            candidates = self._form_field_candidates(name, value)
            if candidates:
                return candidates
            if time.monotonic() >= deadline:
                return []
            self._wait_for_runtime_settle(300)


    def _resolve_runtime_form_field(self, name: str):
        if self.current_manifest is None:
            return None
        try:
            runtime_elements = self.runtime.capture_runtime_elements(self.current_manifest)
        except Exception:
            return None
        bound = bind_runtime_form_field(str(name), runtime_elements)
        if bound is None:
            return None
        if self._has_query_field(name) and not bound.runtime.in_dialog:
            return None
        self._templates.include_field(bound)
        return bound

    def _wait_for_runtime_settle(self, timeout_ms: int) -> None:
        wait = getattr(self.runtime, "_require_page", None)
        if wait is not None:
            try:
                wait().wait_for_timeout(timeout_ms)
                return
            except Exception:
                pass
        time.sleep(timeout_ms / 1000)

    def _resolve_assert_form_field(self, name: str):
        property_uri = self._field_property_uri_by_name.get(str(name))
        if property_uri and self.current_binding is not None:
            candidates = [
                bound
                for bound in self.current_binding.bound_fields
                if bound.candidate.property_uri == property_uri
                and not self._is_table_like_field(bound.candidate)
                and not self._is_query_field(bound.candidate)
            ]
            if candidates:
                candidates.sort(key=self._form_field_sort_key)
                return candidates[0]
        candidates = self._form_field_candidates(name)
        if candidates:
            return candidates[0]
        readable = self._resolve_readable_form_field(name, property_uri)
        if readable is not None:
            return readable
        return self._require_form_field(name)

    def _resolve_readable_form_field(self, name: str, property_uri: str | None = None) -> BoundElement | None:
        if self.current_manifest is None:
            return None
        candidates = [
            candidate
            for candidate in self.current_manifest.fields
            if not self._is_table_like_field(candidate)
            and not self._is_query_field(candidate)
            and (property_uri and candidate.property_uri == property_uri or _matches_any_alias(name, candidate.aliases()))
        ]
        try:
            runtime_elements = self.runtime.capture_runtime_elements(self.current_manifest)
        except Exception:
            return None
        return bind_runtime_readable_form_field(candidates, runtime_elements)

    def _form_field_sort_key(self, bound, value: Any | None = None) -> tuple[int, int, int, int, int, int]:
        active_tab_rank = 0 if self._candidate_in_active_tab(bound.candidate) else 1
        return (active_tab_rank, *_form_field_priority(bound, value))

    def _candidate_in_active_tab(self, candidate) -> bool:
        active = self._templates.active_tab_region_fieldid
        if not active or self.current_manifest is None:
            return False
        regions_by_key = {region.key: region for region in self.current_manifest.regions}
        regions_by_fieldid = {region.fieldid: region for region in self.current_manifest.regions}
        region = regions_by_key.get(candidate.region_key or "") or regions_by_fieldid.get(candidate.region_fieldid or "")
        visited: set[str] = set()
        while region is not None:
            region_key = str(region.key or "")
            region_fieldid = str(region.fieldid or "")
            if active in {region_key, region_fieldid}:
                return True
            if region_key in visited:
                return False
            visited.add(region_key)
            region = regions_by_key.get(region.parent_region_key or "")
        return False

    def _is_query_field(self, candidate) -> bool:
        if self.current_manifest is None:
            return False
        return any(candidate.region_key == region.key and region.region_type == "query_box" for region in self.current_manifest.regions)

    def _query_action_fieldids(self) -> list[str]:
        if self.current_manifest is None:
            return []
        values: list[str] = []
        for region in self.current_manifest.regions:
            if region.region_type != "query_box":
                continue
            for fieldid in getattr(region, "runtime_fieldids", None) or []:
                if fieldid == region.fieldid or str(fieldid).endswith("_query_icon"):
                    values.append(str(fieldid))
            if region.fieldid:
                values.append(str(region.fieldid))
        return list(dict.fromkeys(value for value in values if value))

    def _is_table_like_field(self, candidate) -> bool:
        if self._is_main_table_field(candidate):
            return True
        return str(candidate.fieldid or "").startswith(("table_", "bg_table_"))

    def _is_main_table_field(self, candidate) -> bool:
        if self.current_manifest is None:
            return False
        return any(
            region.region_type == "main_table"
            and candidate.region_key == region.key
            for region in self.current_manifest.regions
        )

    def _ensure_menu_open_for_component(self, component_name: str) -> None:
        if self.current_menu is None:
            raise RuntimeError(f"执行{component_name}组件动作前必须先 open_menu")
        if not self.current_page_supported:
            message = (
                str((self.current_template_error or {}).get("message") or "")
                or "未识别到单据模板"
            )
            raise RuntimeError(f"当前页面不是单据模板页面，不支持{component_name}操作: {message}")
        if self.current_binding is None or self.current_manifest is None:
            raise RuntimeError(f"执行{component_name}组件动作前必须先 open_menu")

    def _manifest_has_action_alias(self, label: str) -> bool:
        if self.current_manifest is None:
            return False
        return any(label in action.aliases() for action in self.current_manifest.actions)

    def _find_action_candidate(self, label: str):
        if self.current_manifest is None:
            return None
        for action in self.current_manifest.actions:
            if label in {action.label, action.title}:
                return action
        normalized_label = _normalize_field_alias(label)
        for action in self.current_manifest.actions:
            if normalized_label and normalized_label in {
                _normalize_field_alias(action.label),
                _normalize_field_alias(action.title),
            }:
                return action
        for action in self.current_manifest.actions:
            if label in action.aliases():
                return action
        return None

    def _find_tab_candidate(self, label: str):
        if self.current_manifest is None:
            return None
        for tab in self.current_manifest.tabs:
            if label in tab.aliases():
                return tab
        return None

    def _require_runtime_method(self, name: str):
        method = getattr(self.runtime, name, None)
        if method is None:
            raise RuntimeError(f"当前运行时不支持: {name}")
        return method

    def _require_field(self, name: str):
        if self.current_binding is None:
            raise RuntimeError("执行字段动作前必须先 open_menu")
        bound = self.current_binding.fields_by_alias.get(str(name))
        if bound is None:
            raise KeyError(f"未绑定字段: {name}")
        return bound

    def _require_action(self, name: str):
        if self.current_binding is None:
            raise RuntimeError("执行动作前必须先 open_menu")
        bound = self.current_binding.actions_by_alias.get(str(name))
        if bound is None:
            raise KeyError(f"未绑定动作: {name}")
        return bound


def _extract_row_numbers(target: dict[str, Any]) -> list[int]:
    raw = target.get("row_numbers", None)
    if raw is None and target.get("row_number", None) is not None:
        raw = [target["row_number"]]
    if raw is None and target.get("row_index", None) is not None:
        raw = [target["row_index"]]
    if raw is None and _wants_first_available(target):
        raw = [1]
    if raw is None:
        return []
    if isinstance(raw, int) and not isinstance(raw, bool):
        raw = [raw]
    if not isinstance(raw, list):
        raise ValueError(f"表格行号必须是列表或单个整数: {raw!r}")
    row_numbers = [int(item) for item in raw]
    if any(item < 1 for item in row_numbers):
        raise ValueError(f"表格行号从 1 开始: {row_numbers}")
    return row_numbers


def _format_region_labels(regions: list[Any]) -> str:
    labels: list[str] = []
    for region in regions:
        label = str(getattr(region, "label", "") or "").strip()
        fieldid = str(getattr(region, "fieldid", "") or "").strip()
        if label and fieldid:
            labels.append(f"{label}({fieldid})")
        elif label:
            labels.append(label)
        elif fieldid:
            labels.append(fieldid)
    return "、".join(labels) or "未识别"


def _region_aliases(region: Any) -> set[str]:
    return {
        value
        for value in (
            str(getattr(region, "label", "") or ""),
            str(getattr(region, "fieldid", "") or ""),
            str(getattr(region, "key", "") or ""),
            *(str(item or "") for item in (getattr(region, "runtime_fieldids", None) or [])),
        )
        if value
    }


def _region_fieldids_for_runtime(region: Any) -> list[str]:
    values = [str(getattr(region, "fieldid", "") or "")]
    values.extend(str(item or "") for item in (getattr(region, "runtime_fieldids", None) or []))
    return list(dict.fromkeys(value for value in values if value))


def _extract_row_selection_match(target: dict[str, Any]) -> dict[str, Any]:
    match = target.get("match")
    if not isinstance(match, dict) or not match:
        raise ValueError(f"表格行选择缺少 match / rows / row_number: {target}")
    return dict(match)


def _extract_row_selection_target_columns(target: dict[str, Any]) -> list[str]:
    columns: list[str] = []

    def add_from_match(match: dict[str, Any]) -> None:
        raw_conditions = match.get("conditions") or match.get("all")
        if raw_conditions is None:
            column = str(match.get("column") or match.get("field") or "").strip()
            if column and column not in columns:
                columns.append(column)
            return
        if isinstance(raw_conditions, dict):
            raw_conditions = [raw_conditions]
        if not isinstance(raw_conditions, list):
            return
        for item in raw_conditions:
            if not isinstance(item, dict):
                continue
            column = str(item.get("column") or item.get("field") or "").strip()
            if column and column not in columns:
                columns.append(column)

    match = target.get("match")
    if isinstance(match, dict):
        add_from_match(match)
    rows = target.get("rows")
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            row_match = row.get("match")
            if isinstance(row_match, dict):
                add_from_match(row_match)
    return columns


def _extract_row_selection_rows(target: dict[str, Any]) -> list[dict[str, Any]]:
    raw = target.get("rows")
    if raw is None:
        return []
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"表格多行选择 rows 必须是非空列表: {raw!r}")
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"表格多行选择 rows[{index}] 必须是对象: {item!r}")
        match = item.get("match")
        if not isinstance(match, dict) or not match:
            raise ValueError(f"表格多行选择 rows[{index}].match 必须是对象: {item!r}")
        rows.append(dict(match))
    return rows


def _wants_first_available(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return bool(value.get("first_available") or value.get("select_first_available"))


def _wants_select_all(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return value.get("select_all") is True


_RANDOM_TOKEN_RE = re.compile(r"\{\{\s*random\.([a-zA-Z0-9_]+)\s*\}\}")


def _generate_random_value(name: str) -> str:
    normalized = name.strip().lower()
    if normalized == "suffix":
        return f"{time.strftime('%m%d%H%M%S')}{random.randint(100, 999)}"
    if normalized in {"id_card", "idcard", "identity_card"}:
        return _generate_chinese_id_card()
    if normalized in {"mobile", "phone", "phone_number"}:
        prefix = random.choice(["130", "131", "132", "155", "156", "185", "186", "188"])
        return prefix + "".join(str(random.randint(0, 9)) for _ in range(8))
    if normalized in {"bank_card", "bankcard", "card"}:
        body = "6222" + "".join(str(random.randint(0, 9)) for _ in range(14))
        return body + _luhn_checksum_digit(body)
    if normalized in {"digits", "number"}:
        return "".join(str(random.randint(0, 9)) for _ in range(8))
    return f"{time.strftime('%m%d%H%M%S')}{random.randint(100, 999)}"


def _generate_chinese_id_card() -> str:
    area = "110101"
    year = random.randint(1980, 2004)
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    sequence = random.randint(100, 999)
    body = f"{area}{year:04d}{month:02d}{day:02d}{sequence:03d}"
    weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    checks = "10X98765432"
    checksum = sum(int(char) * weight for char, weight in zip(body, weights, strict=True)) % 11
    return body + checks[checksum]


def _luhn_checksum_digit(body: str) -> str:
    total = 0
    parity = (len(body) + 1) % 2
    for index, char in enumerate(body):
        digit = int(char)
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return str((10 - total % 10) % 10)


def _has_success_notification(notifications: list[dict[str, str]]) -> bool:
    return any(
        item.get("type") == "success" or "成功" in str(item.get("message") or "")
        for item in notifications
    )


def _has_error_notification(notifications: list[dict[str, str]]) -> bool:
    return any(
        item.get("type") == "error" or "未通过" in str(item.get("message") or "") or "失败" in str(item.get("message") or "")
        for item in notifications
    )


def _unhandled_error_notification_message(result: StepResult, next_step: ActionStep | None) -> str | None:
    if result.action not in _CLICK_ACTIONS_WITH_NOTIFICATIONS:
        return None
    notifications = result.data.get("notifications") if isinstance(result.data, dict) else None
    if not isinstance(notifications, list) or not _has_error_notification(notifications):
        return None
    if _is_notification_assert_step(next_step):
        return None
    messages = _error_notification_messages(notifications)
    if not messages:
        return None
    label = ""
    if isinstance(result.data, dict):
        label = str(result.data.get("label") or result.data.get("fieldid") or "").strip()
    subject = f"{result.action}({label})" if label else result.action
    return (
        f"{subject} 后出现错误提示: {'; '.join(messages)}。"
        "如该错误是预期结果，请在该动作后紧接 notification.assert 断言。"
    )


def _is_notification_assert_step(step: ActionStep | None) -> bool:
    return bool(step and step.kind == "component" and step.component == "notification" and step.operation == "assert")


def _is_workflow_result_assert_step(step: ActionStep | None) -> bool:
    return bool(
        step
        and step.kind == "component"
        and step.component == "workflow_result"
        and step.operation == "assert"
    )


def _is_workflow_result_operation(step: ActionStep | None, operations: set[str]) -> bool:
    return bool(
        step
        and step.kind == "component"
        and step.component == "workflow_result"
        and step.operation in operations
    )


def _workflow_result_text_matches(actual: str, expected: str) -> bool:
    normalize = lambda value: re.sub(r"\s+", "", str(value or "")).strip().rstrip("!！。.;；,，")
    return normalize(actual) == normalize(expected)


def _unhandled_workflow_result_message(
    result: StepResult,
    next_step: ActionStep | None,
    *,
    asserted: bool,
) -> str:
    snapshot = result.data.get("workflow_result") if isinstance(result.data, dict) else {}
    counts = snapshot.get("counts") if isinstance(snapshot, dict) else {}
    next_label = _step_label(next_step) if next_step is not None else "用例结束"
    if asserted:
        return (
            f"{result.action} 后工作流批量结果层仍可见，下一步 {next_label} 未处理外层结果层。"
            f"实际统计={counts}，请执行 workflow_result.details 或 workflow_result.confirm。"
        )
    return (
        f"{result.action} 后出现工作流批量结果层，下一步为 {next_label}。"
        f"实际统计={counts}，请在该动作后紧接 workflow_result.assert。"
    )


def _error_notification_messages(notifications: list[dict[str, str]]) -> list[str]:
    messages: list[str] = []
    for item in notifications:
        message = str(item.get("message") or "").strip()
        if item.get("type") == "error" or "未通过" in message or "失败" in message:
            if message:
                messages.append(message)
    return messages


def _notification_match_values(target: dict[str, Any]) -> tuple[str, str, str, str]:
    expected_type = str(target.get("type") or "").strip()
    contains = str(
        target.get("contains")
        or target.get("message_contains")
        or target.get("text_contains")
        or ""
    ).strip()
    equals = str(target.get("equals") or "").strip()
    message = str(target.get("message") or "").strip()
    return expected_type, contains, equals, message


def _notification_message_matches(actual: str, expected: str) -> bool:
    if actual == expected:
        return True
    return _normalize_notification_message(actual) == _normalize_notification_message(expected)


def _matching_notifications(
    notifications: list[dict[str, str]],
    *,
    expected_type: str,
    contains: str,
    equals: str,
    message: str,
) -> list[dict[str, str]]:
    return [
        item
        for item in notifications
        if (not expected_type or item.get("type") == expected_type)
        and (not contains or contains in item.get("message", ""))
        and (not equals or item.get("message") == equals)
        and (not message or _notification_message_matches(item.get("message", ""), message))
    ]


def _normalize_notification_message(value: str) -> str:
    normalized = re.sub(r"\s+", "", str(value or "")).strip()
    return normalized.rstrip("!！。.;；,，")


def _deduplicate_notifications(notifications: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, str]] = []
    for item in notifications:
        key = (str(item.get("type") or ""), str(item.get("message") or ""))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _extract_query_conditions(target: dict[str, Any]) -> list[dict[str, Any]]:
    raw = target.get("conditions")
    if raw is None:
        raw = target.get("condition")
    if raw is None and "field" in target:
        raw = [{"field": target["field"], "equals": target.get("equals")}]
    if raw is None:
        raise ValueError(f"查询条件缺少 conditions: {target}")
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        raise ValueError(f"查询条件必须是对象或对象列表: {raw!r}")
    conditions = [dict(item) for item in raw]
    if not conditions:
        return []
    for condition in conditions:
        if not condition.get("field") or condition.get("equals") is None:
            raise ValueError(f"查询条件必须包含 field 和 equals: {condition}")
    return conditions


def _extract_optional_table_name(target: dict[str, Any]) -> str | None:
    raw = target.get("table") or target.get("name") or target.get("table_name")
    if raw is None:
        return None
    value = str(raw).strip()
    return value or None


def _looks_like_runtime_fieldid(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_:\-.]*", str(value or "").strip()))


def _extract_row_match_columns(match: dict[str, Any]) -> list[str]:
    columns: list[str] = []
    raw_conditions = match.get("conditions")
    if isinstance(raw_conditions, list):
        for condition in raw_conditions:
            if not isinstance(condition, dict):
                continue
            column = str(condition.get("column") or condition.get("field") or "").strip()
            if column and column not in columns:
                columns.append(column)
    column = str(match.get("column") or match.get("field") or "").strip()
    if column and column not in columns:
        columns.append(column)
    return columns


def _normalize_editable_table_editor(raw: Any) -> str | None:
    if raw is None:
        return None
    value = str(raw).strip().lower()
    aliases = {
        "auto": "auto",
        "form": "form",
        "dialog": "form",
        "modal": "form",
        "popup": "form",
        "表单": "form",
        "弹窗": "form",
        "inline": "inline",
        "cell": "inline",
        "grid": "inline",
        "单元格": "inline",
        "行内": "inline",
    }
    if value not in aliases:
        raise ValueError(f"可编辑表格 editor 只支持 auto/form/inline: {raw}")
    return aliases[value]


def _callable_accepts_keyword(callable_obj: Any, keyword: str) -> bool:
    try:
        signature = inspect.signature(callable_obj)
    except (TypeError, ValueError):
        return False
    return keyword in signature.parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )



def _manifest_attachment_upload_candidates(manifest: Any) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for node in getattr(manifest, "template_nodes", []) or []:
        node_type = str(getattr(node, "node_type", "") or "")
        component_name = str(getattr(node, "component_name", "") or "")
        if node_type != "upload" and component_name != "LCDUploadNext":
            continue
        raw = getattr(node, "raw", {}) or {}
        candidates.append(
            {
                "key": getattr(node, "key", "") or "",
                "fieldid": getattr(node, "fieldid", "") or "",
                "label": getattr(node, "label", "") or "",
                "node_type": node_type,
                "component_name": component_name,
                "raw": raw,
            }
        )
    return candidates


def _manifest_action_candidates(manifest: Any) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for action in getattr(manifest, "actions", []) or []:
        to_dict = getattr(action, "to_dict", None)
        candidates.append(to_dict() if callable(to_dict) else dict(action))
    return candidates


def _labels_equal(left: str, right: str) -> bool:
    return _normalize_semantic_label(left) == _normalize_semantic_label(right)


def _labels_equal_ignoring_unit_suffix(left: str, right: str) -> bool:
    return _normalize_semantic_label(_strip_unit_suffix(left)) == _normalize_semantic_label(_strip_unit_suffix(right))


def _strip_unit_suffix(value: str) -> str:
    text = str(value or "").strip()
    return re.sub(r"\s*[（(][^（）()]*[）)]\s*$", "", text).strip() or text


def _normalize_semantic_label(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip()


def _normalize_table_header_label(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return re.sub(r"^[\s*＊✱✳※]+", "", text).strip()


def _table_column_belongs_to_table(
    candidate: Any,
    table: str,
    regions_by_key: dict[str, Any],
    regions_by_fieldid: dict[str, Any],
) -> bool:
    region = regions_by_key.get(candidate.region_key or "") or regions_by_fieldid.get(candidate.region_fieldid or "")
    if region is None:
        return False
    table_label = _normalize_semantic_label(table)
    region_label = _normalize_semantic_label(getattr(region, "label", ""))
    if not table_label or not region_label:
        return False
    return table_label == region_label or table_label in region_label or region_label in table_label


def _column_groups_match(expected: list[str], actual: list[str]) -> bool:
    return [_normalize_semantic_label(item) for item in expected] == [
        _normalize_semantic_label(item) for item in actual
    ]


def _has_ambiguous_grouped_columns(matches: list[Any]) -> bool:
    grouped = [candidate for candidate in matches if getattr(candidate, "column_groups", None)]
    return len(grouped) > 1


def _editable_table_column_label_matches(label: str, candidate: Any) -> bool:
    return (
        _labels_equal(label, getattr(candidate, "label", ""))
        or _labels_equal(label, getattr(candidate, "title", ""))
        or _labels_equal(label, getattr(candidate, "data_field", "") or "")
        or _labels_equal_ignoring_unit_suffix(label, getattr(candidate, "label", ""))
        or _labels_equal_ignoring_unit_suffix(label, getattr(candidate, "title", ""))
    )


def _format_editable_table_column_paths(candidates: list[Any], label: str) -> str:
    paths: list[str] = []
    for candidate in candidates:
        if not _editable_table_column_label_matches(label, candidate):
            continue
        groups = [str(item).strip() for item in getattr(candidate, "column_groups", []) or [] if str(item).strip()]
        leaf = str(getattr(candidate, "label", "") or getattr(candidate, "title", "") or label).strip()
        path = " > ".join([*groups, leaf] if leaf else groups)
        if path and path not in paths:
            paths.append(path)
    return "、".join(paths) or "无"


def _format_editable_table_add_row_candidate(prefix: str, candidate: Any) -> str:
    if not isinstance(candidate, dict):
        return ""
    text = str(candidate.get("text") or "").strip() or "?"
    x = candidate.get("x")
    y = candidate.get("y")
    position = f"@{x},{y}" if x is not None and y is not None else ""
    class_name = str(candidate.get("className") or "").strip()
    class_part = f",class={class_name[:80]}" if class_name else ""
    root_class = str(candidate.get("rootClassName") or "").strip()
    root_class_part = f",root_class={root_class[:80]}" if root_class else ""
    row_scoped = candidate.get("rowScopedAction")
    row_scoped_part = f",row_scoped={row_scoped}" if row_scoped is not None else ""
    table_level = candidate.get("tableLevelAction")
    table_level_part = f",table_level={table_level}" if table_level is not None else ""
    table_body = candidate.get("tableBodyAction")
    table_body_part = f",table_body={table_body}" if table_body is not None else ""
    sticky_body = candidate.get("stickyTableBodyAction")
    sticky_body_part = f",sticky_body={sticky_body}" if sticky_body is not None else ""
    root_text = str(candidate.get("rootText") or "").strip()
    root_part = f",root={root_text[:80]}" if root_text else ""
    return (
        f"; {prefix}={text}{position}{class_part}{root_class_part}"
        f"{row_scoped_part}{table_level_part}{table_body_part}{sticky_body_part}{root_part}"
    )


def _select_best_editable_table_column_candidate(label: str, matches: list[Any]) -> Any:
    return sorted(
        enumerate(matches),
        key=lambda item: _editable_table_column_candidate_rank(label, item[1], item[0]),
    )[0][1]


def _editable_table_column_candidate_rank(label: str, candidate: Any, index: int) -> tuple[int, int, int, int]:
    hidden_rank = 1 if _candidate_hidden_by_config(candidate) else 0
    label_rank = _editable_table_column_label_rank(label, candidate)
    component_rank = _editable_table_column_component_rank(candidate)
    return (hidden_rank, label_rank, component_rank, index)


def _candidate_hidden_by_config(candidate: Any) -> bool:
    if getattr(candidate, "visible_by_config", True) is False:
        return True
    raw = getattr(candidate, "raw", {}) or {}
    if not isinstance(raw, dict):
        return False
    hide = raw.get("hide")
    if isinstance(hide, bool):
        return hide
    if isinstance(hide, (int, float)):
        return hide != 0
    return str(hide).strip().lower() in {"1", "true", "yes", "y", "on", "是", "隐藏"}


def _editable_table_column_label_rank(label: str, candidate: Any) -> int:
    if _labels_equal(label, getattr(candidate, "label", "")):
        return 0
    if _labels_equal(label, getattr(candidate, "title", "")):
        return 1
    if _labels_equal(label, getattr(candidate, "data_field", "") or ""):
        return 2
    if _labels_equal_ignoring_unit_suffix(label, getattr(candidate, "label", "")):
        return 3
    if _labels_equal_ignoring_unit_suffix(label, getattr(candidate, "title", "")):
        return 4
    return 5


def _editable_table_column_component_rank(candidate: Any) -> int:
    component = str(getattr(candidate, "component_name", "") or "").lower().replace("-", "").replace("_", "")
    if any(token in component for token in ("modalselect", "refer", "reference", "treeselect", "select", "picker", "cascader")):
        return 0
    return 1


def _optional_text(raw: Any) -> str | None:
    if raw is None:
        return None
    value = str(raw).strip()
    return value or None


def _extract_editable_row_number(target: dict[str, Any]) -> int:
    raw = target.get("row_number", target.get("row_index", -1))
    row_number = int(raw)
    if row_number == 0 or row_number < -1:
        raise ValueError(f"可编辑表格行号必须为 1-based 或 -1 表示末行: {row_number}")
    return row_number


def _extract_field_values(target: dict[str, Any]) -> list[tuple[str, Any]]:
    raw = target.get("fields")
    if raw is None:
        raw = target.get("values")
    if raw is None and "field" in target:
        raw = [{"field": target["field"], "equals": target.get("equals")}]
    if raw is None:
        raise ValueError(f"表单字段缺少 fields: {target}")
    if isinstance(raw, dict):
        return [(str(key), value) for key, value in raw.items()]
    if not isinstance(raw, list):
        raise ValueError(f"表单字段必须是对象或列表: {raw!r}")
    fields: list[tuple[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict) or not item.get("field") or item.get("equals") is None:
            raise ValueError(f"表单字段必须包含 field 和 equals: {item}")
        fields.append((str(item["field"]), item["equals"]))
    if not fields:
        raise ValueError("表单字段列表不能为空")
    return fields


def _extract_editable_table_field_values(target: dict[str, Any]) -> list[dict[str, Any]]:
    raw = target.get("fields")
    if raw is None:
        raw = target.get("values")
    if raw is None and "field" in target:
        raw = [{"field": target["field"], "equals": target.get("equals")}]
    if raw is None:
        raise ValueError(f"表单字段缺少 fields: {target}")
    fields: list[dict[str, Any]] = []
    if isinstance(raw, dict):
        for field, value in raw.items():
            if isinstance(value, dict) and "column_group" in value:
                fields.append(
                    {
                        "field": str(field),
                        "value": value.get("value", value.get("equals")),
                        "column_groups": _normalize_column_groups(value.get("column_group")),
                    }
                )
            else:
                fields.append({"field": str(field), "value": value, "column_groups": []})
    elif isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict) or not item.get("field") or ("value" not in item and "equals" not in item):
                raise ValueError(f"表单字段必须包含 field 和 value/equals: {item}")
            fields.append(
                {
                    "field": str(item["field"]),
                    "value": item.get("value", item.get("equals")),
                    "column_groups": _normalize_column_groups(item.get("column_group")),
                }
            )
    else:
        raise ValueError(f"表单字段必须是对象或列表: {raw!r}")
    if not fields:
        raise ValueError("表单字段列表不能为空")
    return fields


def _editable_table_runtime_values(field_specs: list[dict[str, Any]]) -> tuple[Any, list[dict[str, Any]]]:
    counts: dict[str, int] = {}
    for spec in field_specs:
        field = str(spec["field"])
        counts[field] = counts.get(field, 0) + 1
    if not any(count > 1 for count in counts.values()):
        return {str(spec["field"]): spec["value"] for spec in field_specs}, field_specs

    seen: dict[str, int] = {}
    values: list[dict[str, Any]] = []
    column_specs: list[dict[str, Any]] = []
    for spec in field_specs:
        field = str(spec["field"])
        seen[field] = seen.get(field, 0) + 1
        key = f"{field}#{seen[field]}" if counts[field] > 1 else field
        values.append({"key": key, "column": field, "value": spec["value"]})
        column_specs.append({**spec, "key": key})
    return values, column_specs


def _normalize_column_groups(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        value = raw.strip()
        return [value] if value else []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def _extract_import_files(target: dict[str, Any]) -> list[str]:
    raw = target.get("files")
    if raw is None:
        raw = target.get("file")
    if raw is None:
        raw = target.get("path")
    if raw is None:
        raise ValueError(f"导入缺少 file 或 files: {target}")
    if isinstance(raw, (str, int)):
        files = [str(raw)]
    elif isinstance(raw, list):
        files = [str(item) for item in raw]
    else:
        raise ValueError(f"导入文件必须是字符串或字符串列表: {raw!r}")
    files = [item.strip() for item in files if item and str(item).strip()]
    if not files:
        raise ValueError("导入文件列表不能为空")
    return files


def _extract_attachments(target: dict[str, Any]) -> list[dict[str, str]]:
    raw = target.get("attachments")
    if raw is None and (target.get("file") or target.get("path")):
        raw = [
            {
                "type": target.get("type") or target.get("attachment_type") or target.get("name"),
                "file": target.get("file") or target.get("path"),
            }
        ]
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"附件上传缺少 attachments 列表: {target}")
    attachments: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError(f"附件项必须是对象: {item!r}")
        attachment_type = str(item.get("type") or item.get("attachment_type") or item.get("name") or "").strip()
        file_path = str(item.get("file") or item.get("path") or "").strip()
        if not attachment_type or not file_path:
            raise ValueError(f"附件项必须包含 type 和 file: {item}")
        attachments.append({"type": attachment_type, "file": file_path})
    return attachments


def _extract_transfer_items(target: dict[str, Any]) -> list[dict[str, Any]]:
    raw = target.get("items") or target.get("targets") or target.get("matches") or target.get("match")
    left = target.get("left") or target.get("source")
    if raw is None and isinstance(left, dict):
        raw = left.get("items") or left.get("targets") or left.get("matches") or left.get("match")
    if raw is None and "equals" in target:
        raw = [{"equals": target["equals"], **({"column": target["column"]} if target.get("column") else {})}]
    if raw is None:
        raise ValueError(f"双列表选择缺少 items 或 left.matches: {target}")
    if isinstance(raw, (str, int)):
        raw = [{"equals": str(raw)}]
    elif isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"双列表选择项必须是非空列表: {raw!r}")
    return [_normalize_transfer_item(item) for item in raw]


def _normalize_transfer_item(item: Any) -> dict[str, Any]:
    if isinstance(item, (str, int)):
        return {"match": {"equals": str(item)}}
    if not isinstance(item, dict):
        raise ValueError(f"双列表选择项必须是对象或文本: {item!r}")
    if isinstance(item.get("match"), dict):
        return {"match": dict(item["match"])}
    match: dict[str, Any] = {}
    for key in ("column", "equals", "contains", "value", "label", "text"):
        if item.get(key) is not None:
            match[key] = item[key]
    if "equals" not in match:
        for key in ("value", "label", "text"):
            if match.get(key) is not None:
                match["equals"] = match[key]
                break
    if not match.get("equals") and not match.get("contains"):
        raise ValueError(f"双列表选择项必须包含 equals/contains 或 match: {item}")
    normalized = {"match": match}
    if item.get("side"):
        normalized["side"] = str(item["side"])
    return normalized


def _toolbar_sub_label(target: dict[str, Any]) -> str | None:
    for key in ("sub_label", "sub_action", "child_label", "child_action", "item", "option"):
        value = target.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _candidate_alias_list(candidate) -> list[str]:
    if candidate is None:
        return []
    return sorted(str(alias) for alias in candidate.aliases() if str(alias))


def _form_field_priority(bound, value: Any | None = None) -> tuple[int, int, int, int, int]:
    candidate = bound.candidate
    runtime = bound.runtime
    element_type = str(candidate.element_type or "").lower()
    component_name = str(candidate.component_name or "").lower()
    fieldid = str(candidate.fieldid or "").lower()
    role = str(runtime.role or "").lower()
    tag_name = str(runtime.tag_name or "").lower()
    editable = getattr(runtime, "editable", None)
    disabled = bool(getattr(runtime, "disabled", False))
    readonly = bool(getattr(runtime, "readonly", False))
    candidate_disabled = _candidate_declares_disabled(candidate)
    if editable is True and not disabled and not readonly:
        editability_rank = 0
    elif editable is False or disabled or readonly:
        editability_rank = 10
    else:
        editability_rank = 1
    if candidate_disabled:
        editability_rank = max(editability_rank, 10)
    reference_rank = 0 if _structured_reference_target(value) and _candidate_declares_reference(candidate) else 1
    editable_rank = 0 if element_type == "formitem" else 10
    summary_rank = 10 if component_name in {"lcdkeyitem", "keyitem"} or "_card_" in fieldid else 0
    runtime_rank = 0 if role in {"textbox", "combobox"} or tag_name in {"input", "textarea", "select"} else 1
    return (editability_rank, reference_rank, editable_rank, summary_rank, runtime_rank)


def _candidate_declares_disabled(candidate: Any) -> bool:
    raw = getattr(candidate, "raw", None)
    if not isinstance(raw, dict):
        return False
    values = [raw.get("disabled"), raw.get("readonly"), raw.get("readOnly")]
    props = raw.get("props")
    if isinstance(props, dict):
        values.extend([props.get("disabled"), props.get("readonly"), props.get("readOnly")])
    return any(str(value).strip().lower() in {"1", "true", "yes"} for value in values if value is not None)


def _candidate_declares_reference(candidate: Any) -> bool:
    component_name = str(getattr(candidate, "component_name", "") or "").lower().replace("-", "").replace("_", "")
    raw = getattr(candidate, "raw", None)
    data_type = str(raw.get("dataType") or raw.get("datatype") or "").lower() if isinstance(raw, dict) else ""
    return "refer" in component_name or "reference" in component_name or "modalselect" in component_name or data_type == "refer"


def _structured_reference_target(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return any(
        key in value
        for key in (
            "match",
            "matches",
            "row_number",
            "row_numbers",
            "row_index",
            "first_available",
            "select_first_available",
            "selections",
            "selection",
            "tree",
            "trees",
        )
    )


def _extract_import_results(result: dict[str, Any]) -> list[dict[str, Any]]:
    raw = result.get("import_results")
    if raw is None:
        raw = result.get("results")
    if raw is None:
        raise RuntimeError(f"导入结果缺少 import_results: {result}")
    if not isinstance(raw, list) or not raw:
        raise RuntimeError(f"导入结果必须是非空列表: {raw!r}")
    return [dict(item) for item in raw]


def _assert_import_results(import_results: list[dict[str, Any]], assertion: Any) -> None:
    assertion_payload = assertion if isinstance(assertion, dict) else {}
    expected_status = str(assertion_payload.get("status") or "success").strip().lower()
    if expected_status and expected_status != "any":
        mismatches = []
        for item in import_results:
            actual_status = _normalize_import_status(item.get("status"))
            if actual_status == expected_status:
                continue
            if expected_status == "submitted" and actual_status == "success":
                continue
            mismatches.append(item)
        if mismatches:
            raise RuntimeError(f"导入结果状态不匹配: expected={expected_status}, actual={import_results}")
    error_contains = str(
        assertion_payload.get("error_contains")
        or assertion_payload.get("message_contains")
        or assertion_payload.get("contains")
        or ""
    ).strip()
    if error_contains and not any(error_contains in _import_result_message(item) for item in import_results):
        raise RuntimeError(f"导入失败原因不匹配: expected_contains={error_contains!r}, actual={import_results}")


def _normalize_import_status(status: Any) -> str:
    value = str(status or "").strip().lower()
    if value in {"success", "succeeded", "done", "complete", "completed"} or "完成" in value or "成功" in value:
        return "success"
    if value in {"failure", "failed", "error"} or "失败" in value:
        return "failure"
    return value


def _import_result_message(item: dict[str, Any]) -> str:
    return str(item.get("message") or item.get("error") or item.get("reason") or "")


def _values_match(actual: str, expected: str, *, checkbox: bool = False) -> bool:
    actual_norm = _normalize_value(actual)
    expected_norm = _normalize_value(expected)
    if checkbox:
        actual_checkbox = _normalize_checkbox_state(actual_norm)
        expected_checkbox = _normalize_checkbox_state(expected_norm)
        if actual_checkbox is not None and expected_checkbox is not None:
            return actual_checkbox == expected_checkbox
    return actual_norm == expected_norm or expected_norm in actual_norm


def _has_success_notification(notifications: list[dict[str, str]]) -> bool:
    return any(item.get("type") == "success" or "成功" in item.get("message", "") for item in notifications)


def _normalize_value(value: str) -> str:
    return "".join(str(value).replace(",", "").split())


def _normalize_checkbox_state(value: str) -> str | None:
    text = str(value or "").strip().lower()
    truthy = {"on", "true", "1", "yes", "y", "checked", "是", "启用", "开启", "打开", "勾选", "已勾选", "选中", "已选中"}
    falsy = {
        "off",
        "false",
        "0",
        "no",
        "n",
        "unchecked",
        "否",
        "停用",
        "关闭",
        "未勾选",
        "不勾选",
        "未选中",
        "未选择",
    }
    if text in truthy:
        return "on"
    if text in falsy:
        return "off"
    return None


def _is_checkbox_bound_element(bound) -> bool:
    candidate = getattr(bound, "candidate", None)
    runtime = getattr(bound, "runtime", None)
    component_name = str(getattr(candidate, "component_name", "") or "").lower().replace("-", "").replace("_", "")
    role = str(getattr(runtime, "role", "") or "").lower()
    tag_name = str(getattr(runtime, "tag_name", "") or "").lower()
    selector = str(getattr(runtime, "selector", "") or "").lower()
    if "checkbox" in component_name or role == "checkbox":
        return True
    return tag_name == "input" and "checkbox" in selector


def _matches_any_alias(name: str, aliases: set[str]) -> bool:
    if name in aliases:
        return True
    normalized_name = _normalize_field_alias(name)
    return any(normalized_name == _normalize_field_alias(alias) for alias in aliases)


def _normalize_field_alias(value: str) -> str:
    normalized = "".join(str(value).split())
    normalized = normalized.replace("模版", "模板")
    normalized = normalized.replace("开始", "起始")
    return normalized


def _popup_reference_unconfirmed_diagnostics(result: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("close_action", "root_backfilled", "dialog_hidden", "confirm_label"):
        if key in result:
            parts.append(f"{key}={result.get(key)}")
    selected = result.get("selected")
    if selected:
        parts.append(f"selected={str(selected)[:300]}")
    return "; ".join(parts) or "confirmed=false"


def _popup_reference_completed(result: dict[str, Any]) -> bool:
    return bool(result.get("confirmed") or result.get("root_backfilled") or result.get("dialog_hidden"))


def _extract_component_name(target: dict[str, Any]) -> str:
    return str(
        target.get("name")
        or target.get("component_name")
        or target.get("component_label")
        or target.get("region_label")
        or ""
    ).strip()


def _tree_select_labels(target: dict[str, Any]) -> list[str]:
    raw_labels = target.get("labels")
    if raw_labels is None:
        raw_labels = target.get("values")
    if raw_labels is None:
        raw_labels = target.get("label")
    if isinstance(raw_labels, (list, tuple, set)):
        labels = [str(item).strip() for item in raw_labels if str(item or "").strip()]
    else:
        labels = [str(raw_labels or "").strip()]
    if not labels:
        raise RuntimeError("缺少树节点 label")
    return labels


def _tree_select_node_shortcut(target: dict[str, Any]) -> str:
    return str(target.get("node") or "").strip()


def _step_label(step: ActionStep) -> str:
    if step.kind == "component":
        return f"{step.component}.{step.operation}"
    return str(step.action or "unknown")


def _is_bpr_control_step(step: ActionStep) -> bool:
    return bool(step.kind == "component" and step.component == "bpr" and step.operation in {"start", "stop"})


def _is_bpr_stop_step(step: ActionStep) -> bool:
    return bool(step.kind == "component" and step.component == "bpr" and step.operation == "stop")


def _normalize_bpr_session_payload(payload: Any) -> dict[str, Any]:
    if payload is None:
        return {}
    if isinstance(payload, dict):
        return dict(payload)
    if hasattr(payload, "to_dict"):
        converted = payload.to_dict()
        return dict(converted) if isinstance(converted, dict) else {}
    data: dict[str, Any] = {}
    for source, target in (
        ("bpr_id", "bpr_id"),
        ("bprId", "bpr_id"),
        ("report_url", "report_url"),
        ("reportUrl", "report_url"),
        ("start_ts", "start_ts"),
        ("startTs", "start_ts"),
        ("end_ts", "end_ts"),
        ("endTs", "end_ts"),
    ):
        if hasattr(payload, source):
            data[target] = getattr(payload, source)
    return data


def _bpr_control_step_payload(session: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "index",
        "name",
        "description",
        "bpr_id",
        "start_control_step",
        "end_control_step",
        "start_step",
        "end_step",
        "range",
        "report_url",
        "status",
        "success",
        "error",
    )
    return {key: session.get(key) for key in keys if key in session}


def _bpr_range_text(session: dict[str, Any]) -> str:
    start = session.get("start_step")
    end = session.get("end_step")
    if not start or not end:
        return ""
    if start == end:
        return f"step {start}"
    return f"step {start} - step {end}"


def _fill_bpr_duration(session: dict[str, Any]) -> None:
    start = _int_or_none(session.get("start_ts") or session.get("start_time"))
    end = _int_or_none(session.get("end_ts") or session.get("end_time"))
    if start is not None and end is not None and end >= start:
        session["duration_ms"] = end - start


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _elapsed_ms(started: float) -> int:
    return max(0, int(round((time.monotonic() - started) * 1000)))


def _step_business_target(step: ActionStep) -> dict[str, str]:
    if step.kind == "component":
        return {
            "component": str(step.component or ""),
            "operation": str(step.operation or ""),
        }
    return {"action": str(step.action or "")}


def _manifest_evidence_summary(manifest: Any) -> dict[str, Any]:
    if manifest is None:
        return {"capture_unavailable_reason": "not_available"}
    return {
        "page": str(manifest.page.fieldid or ""),
        "biz_obj_code": manifest.page.biz_obj_code,
        "app_code": manifest.page.app_code,
        "domain_key": manifest.page.domain_key,
        "region_count": len(manifest.regions),
        "field_count": len(manifest.fields),
        "action_count": len(manifest.actions),
        "tab_count": len(manifest.tabs),
        "table_column_count": len(manifest.table_columns),
    }


def _binding_evidence_summary(binding: BindingResult | None) -> dict[str, Any]:
    if binding is None:
        return {"capture_unavailable_reason": "not_available"}
    candidates = []
    for kind, items in (
        ("field", binding.bound_fields),
        ("action", binding.bound_actions),
        ("tab", binding.bound_tabs),
    ):
        candidates.extend(
            {
                "kind": kind,
                "fieldid": item.candidate.fieldid,
                "label": item.candidate.label,
                "confidence": item.confidence,
                "reasons": list(item.reasons),
            }
            for item in items
        )
    return {
        "bound_field_count": len(binding.bound_fields),
        "bound_action_count": len(binding.bound_actions),
        "bound_tab_count": len(binding.bound_tabs),
        "candidates": candidates[:50],
        "excluded": [
            {"kind": kind, "label": label, "reason": "not_bound"}
            for kind, labels in (
                ("field", binding.missing_fields),
                ("action", binding.missing_actions),
                ("tab", binding.missing_tabs),
            )
            for label in labels
        ][:50],
    }


def _notification_evidence_summary(notifications: Any) -> list[dict[str, Any]]:
    output = []
    for notification in notifications if isinstance(notifications, list) else []:
        if not isinstance(notification, dict):
            continue
        message = redact_error_text(str(notification.get("message") or ""))
        output.append(
            {
                "type": str(notification.get("type") or ""),
                "message": message["text"],
                **(
                    {"capture_unavailable_reason": message["capture_unavailable_reason"]}
                    if message["capture_unavailable_reason"]
                    else {}
                ),
            }
        )
    return output
