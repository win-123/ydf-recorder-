from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time
import xml.etree.ElementTree as ElementTree
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from .dsl import _is_business_assertion_step


CONTRACT_VERSION = "1.3"
DEFAULT_STEP_TIMEOUT_SECONDS = 120
DEFAULT_CASE_TIMEOUT_SECONDS = 900
DEFAULT_RUN_TIMEOUT_SECONDS = 1800
DEFAULT_MAX_NETWORK_BODY_BYTES = 10 * 1024 * 1024
DEFAULT_MAX_NETWORK_CASE_BYTES = 200 * 1024 * 1024
AI_OBSERVATION_CAPABILITIES = (
    "semantic_events",
    "controlled_timeouts",
    "failure_evidence_bundle",
    "network_text_bodies",
    "network_redaction",
    "request_forward_provenance",
    "case_console_page_errors",
    "table_assertion_snapshot",
    "business_assertion_receipts",
    "notification_request_associations",
    "verification_entrypoint",
    "atomic_evidence_writes",
    "step_page_observation",
)
DSL_CAPABILITIES = ("workflow_result", "workflow_panel")
AVAILABLE_CAPABILITIES = AI_OBSERVATION_CAPABILITIES + DSL_CAPABILITIES

_AUTH_PATH_SEGMENTS = {
    "auth",
    "login",
    "logout",
    "oauth",
    "signin",
    "signout",
    "token",
    "refreshtoken",
    "switchtenant",
}


class ObservationSession:
    def __init__(
        self,
        events_file: Path,
        *,
        tool_version: str,
        run_id: str,
        configuration: dict[str, Any],
        timestamp: Callable[[], str] | None = None,
        monotonic: Callable[[], float] | None = None,
        event_queue: Any | None = None,
    ) -> None:
        self.events_file = events_file
        self.run_dir = events_file.parent
        self.artifacts_dir = self.run_dir / "artifacts"
        self.tool_version = tool_version
        self.run_id = run_id
        self.configuration = dict(configuration)
        self._max_network_body_bytes = int(
            self.configuration.get("max_network_body_bytes") or DEFAULT_MAX_NETWORK_BODY_BYTES
        )
        self._max_network_case_bytes = int(
            self.configuration.get("max_network_case_bytes") or DEFAULT_MAX_NETWORK_CASE_BYTES
        )
        self._case_network_bytes = 0
        self._timestamp = timestamp or (lambda: datetime.now().astimezone().isoformat())
        self._monotonic = monotonic or time.monotonic
        self._event_queue = event_queue
        self._started_monotonic = self._monotonic()
        self._last_event_monotonic = self._started_monotonic
        self._sequence = 0
        self._request_sequence = 0
        self._network_index_sequence = 0
        self._error_index_sequence = 0
        self._recent_network_records: list[tuple[float, dict[str, Any]]] = []
        self._recent_error_records: list[tuple[float, dict[str, Any]]] = []
        self._candidate_request_start = 1
        self._case_id: str | None = None
        self._observed_network_requests: dict[int, dict[str, Any]] = {}
        self._scope: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self._enabled_capabilities = list(AI_OBSERVATION_CAPABILITIES)

    def capabilities(self) -> dict[str, list[str]]:
        with self._lock:
            return self._capabilities_unlocked()

    def enable_capability(self, capability: str) -> None:
        name = str(capability).strip()
        if name not in AVAILABLE_CAPABILITIES:
            raise ValueError(f"不支持的观察能力: {capability}")
        with self._lock:
            if name not in self._enabled_capabilities:
                self._enabled_capabilities.append(name)

    def _capabilities_unlocked(self) -> dict[str, list[str]]:
        return {
            "available": list(AVAILABLE_CAPABILITIES),
            "enabled": list(self._enabled_capabilities),
        }

    def set_scope(self, **scope: Any) -> None:
        with self._lock:
            case_id = scope.get("case_id")
            if case_id is not None and str(case_id) != self._case_id:
                self._case_id = str(case_id)
                self._candidate_request_start = self._request_sequence + 1
                self._case_network_bytes = 0
            for name, value in scope.items():
                if value is None:
                    self._scope.pop(name, None)
                else:
                    self._scope[name] = value

    def begin_step(self, *, is_business_assertion: bool) -> None:
        if is_business_assertion:
            return
        with self._lock:
            self._candidate_request_start = self._request_sequence + 1

    def start_candidate_request(self) -> str:
        with self._lock:
            self._request_sequence += 1
            return f"request-{self._request_sequence:06d}"

    def assertion_candidate_request_ids(self) -> list[str]:
        with self._lock:
            return [
                f"request-{sequence:06d}"
                for sequence in range(self._candidate_request_start, self._request_sequence + 1)
            ]

    def network_request_started(
        self,
        *,
        request_key: int,
        original_url: str,
        actual_url: str,
        base_url: str,
        resource_type: str,
        method: str,
        headers: dict[str, Any],
        body: bytes | str | None,
        forwarding: dict[str, Any] | None = None,
    ) -> str | None:
        content_type = next(
            (str(value) for key, value in headers.items() if str(key).lower() == "content-type"),
            "",
        )
        classification = classify_network_capture(
            original_url=original_url,
            actual_url=actual_url,
            base_url=base_url,
            resource_type=resource_type,
            content_type=content_type,
        )
        if not classification["candidate"]:
            return None
        request_id = self.start_candidate_request()
        request_headers = self._capture_network_headers(request_id, "request", headers)
        request_body = self._capture_network_body(
            request_id,
            "request",
            body,
            content_type,
            declared_size=_declared_content_length(headers),
        )
        with self._lock:
            started_scope = dict(self._scope)
            self._observed_network_requests[request_key] = {
                "request_id": request_id,
                "original_url": original_url,
                "actual_url": actual_url,
                "method": method,
                "resource_type": resource_type,
                "content_type": content_type,
                "started_scope": started_scope,
                "forwarding": dict(forwarding or {}),
                **classification,
            }
        self._append_network_record(
            {
                "event": "request_started",
                "request_id": request_id,
                "original_url": redact_url(original_url),
                "method": method,
                "resource_type": resource_type,
                "content_type": content_type,
                "started_step_id": started_scope.get("step_id"),
                "started_phase": started_scope.get("phase"),
                "request_headers": request_headers,
                "request_body": request_body,
            }
        )
        return request_id

    def network_request_forwarded(self, *, request_key: int, forwarding: dict[str, Any]) -> None:
        with self._lock:
            request = self._observed_network_requests.get(request_key)
            if request is not None:
                request["forwarding"] = dict(forwarding)

    def network_request_completed(
        self,
        *,
        request_key: int,
        actual_url: str,
        status: int,
        headers: dict[str, Any],
        body: bytes | str | None,
        forwarding: dict[str, Any] | None = None,
        body_read_error: str | None = None,
    ) -> bool:
        with self._lock:
            request = self._observed_network_requests.pop(request_key, None)
            completed_scope = dict(self._scope)
        if request is None:
            return False
        forwarding = forwarding or request.get("forwarding")
        actual_url = str((forwarding or {}).get("actual_url") or actual_url or request["actual_url"])
        response_headers = self._capture_network_headers(request["request_id"], "response", headers)
        response_body = self._capture_network_body(
            request["request_id"],
            "response",
            body,
            _header_value(headers, "content-type"),
            declared_size=_declared_content_length(headers),
            body_read_error=body_read_error,
        )
        self._append_network_record(
            {
                "event": "request_completed",
                "request_id": request["request_id"],
                "actual_url": redact_url(actual_url),
                "status": int(status or 0),
                "response_headers": response_headers,
                "response_body": response_body,
                **({"forwarding": _redact_forwarding(forwarding)} if forwarding else {}),
                "completed_step_id": completed_scope.get("step_id"),
                "completed_phase": completed_scope.get("phase"),
            }
        )
        return True

    def response_body_capture_allowed(self, headers: dict[str, Any]) -> bool:
        declared = _declared_content_length(headers)
        return not declared or declared <= self._max_network_body_bytes

    def network_request_failed(
        self,
        *,
        request_key: int,
        error: str,
        forwarding: dict[str, Any] | None = None,
    ) -> bool:
        with self._lock:
            request = self._observed_network_requests.pop(request_key, None)
            completed_scope = dict(self._scope)
        if request is None:
            return False
        self._append_network_record(
            {
                "event": "request_failed",
                "request_id": request["request_id"],
                "error": str(error),
                **({"forwarding": _redact_forwarding(forwarding or request.get("forwarding"))} if forwarding or request.get("forwarding") else {}),
                "completed_step_id": completed_scope.get("step_id"),
                "completed_phase": completed_scope.get("phase"),
            }
        )
        return True

    def finish_incomplete_network_requests(self) -> None:
        with self._lock:
            pending = list(self._observed_network_requests.values())
            self._observed_network_requests.clear()
            completed_scope = dict(self._scope)
        for request in pending:
            self._append_network_record(
                {
                    "event": "request_incomplete",
                    "request_id": request["request_id"],
                    "completed_step_id": completed_scope.get("step_id"),
                    "completed_phase": completed_scope.get("phase"),
                    "capture_unavailable_reason": "incomplete",
                }
            )

    def _append_network_record(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._network_index_sequence += 1
            record = {
                "sequence": self._network_index_sequence,
                "timestamp": self._timestamp(),
                "run_id": self.run_id,
                "case_id": self._case_id,
                **payload,
            }
            self._recent_network_records.append((self._monotonic(), record))
            self._recent_network_records = self._recent_network_records[-200:]
            index_file = self.artifacts_dir / "network" / "index.jsonl"
            index_file.parent.mkdir(parents=True, exist_ok=True)
            with index_file.open("a", encoding="utf-8") as handle:
                json.dump(record, handle, ensure_ascii=False)
                handle.write("\n")
                handle.flush()

    def _capture_network_headers(
        self,
        request_id: str,
        direction: str,
        headers: dict[str, Any],
    ) -> dict[str, Any]:
        redacted, redactions = redact_headers(headers)
        payload = {
            "headers": redacted,
            "redactions": redactions,
            "redaction_count": len(redactions),
        }
        return self._persist_network_payload(request_id, f"{direction}-headers.json", payload)

    def _capture_network_body(
        self,
        request_id: str,
        direction: str,
        body: bytes | str | None,
        content_type: str,
        *,
        declared_size: int = 0,
        body_read_error: str | None = None,
    ) -> dict[str, Any]:
        if body_read_error:
            return {"capture_unavailable_reason": "body_read_failed", "detail": body_read_error}
        if declared_size > self._max_network_body_bytes:
            return {
                "capture_unavailable_reason": "size_limit_exceeded",
                "declared_size": declared_size,
            }
        prepared = prepare_redacted_body(body, content_type)
        original_size = int(prepared.get("original_size") or 0)
        if original_size > self._max_network_body_bytes:
            return {
                "capture_unavailable_reason": "size_limit_exceeded",
                "measured_size": original_size,
            }
        reason = prepared.get("capture_unavailable_reason")
        if reason:
            return dict(prepared)
        persisted = self._persist_network_payload(request_id, f"{direction}-body.json", prepared)
        if "path" not in persisted:
            return {
                **persisted,
                "original_size": original_size,
                "representation": "redacted_semantic",
            }
        return {
            "path": persisted["path"],
            "stored_size": persisted["stored_size"],
            "original_size": original_size,
            "content_type": prepared["content_type"],
            "charset": prepared["charset"],
            "representation": "redacted_semantic",
            "redaction_count": len(prepared["redactions"]),
        }

    def _persist_network_payload(
        self,
        request_id: str,
        filename: str,
        payload: Any,
    ) -> dict[str, Any]:
        content = json.dumps(payload, ensure_ascii=False, indent=2)
        stored_size = len(content.encode("utf-8"))
        with self._lock:
            if self._case_network_bytes + stored_size > self._max_network_case_bytes:
                return {
                    "capture_unavailable_reason": "size_limit_exceeded",
                    "stored_size": stored_size,
                }
            self._case_network_bytes += stored_size
        relative = Path("network") / request_id / filename
        try:
            atomic_write_text(self.artifacts_dir / relative, content)
        except Exception:
            with self._lock:
                self._case_network_bytes -= stored_size
            raise
        return {"path": (Path("artifacts") / relative).as_posix(), "stored_size": stored_size}

    def record_console_error(self, *, message_type: str, text: str, location: Any) -> None:
        if message_type.lower() != "error":
            return
        redacted = redact_error_text(text)
        safe_location = dict(location) if isinstance(location, dict) else {}
        if safe_location.get("url"):
            safe_location["url"] = redact_url(str(safe_location["url"]))
        self._append_error_record(
            {
                "event": "console_error",
                "message_type": message_type,
                "text": redacted["text"],
                "redaction_count": redacted["redaction_count"],
                "location": safe_location,
                **(
                    {"capture_unavailable_reason": redacted["capture_unavailable_reason"]}
                    if redacted["capture_unavailable_reason"]
                    else {}
                ),
            }
        )

    def record_page_error(self, *, message: str, stack: str) -> None:
        redacted_message = redact_error_text(message)
        redacted_stack = redact_error_text(stack) if stack else {"text": "", "redaction_count": 0, "capture_unavailable_reason": None}
        reasons = [
            item["capture_unavailable_reason"]
            for item in (redacted_message, redacted_stack)
            if item["capture_unavailable_reason"]
        ]
        self._append_error_record(
            {
                "event": "page_error",
                "message": redacted_message["text"],
                "stack": redacted_stack["text"],
                "redaction_count": redacted_message["redaction_count"] + redacted_stack["redaction_count"],
                **({"capture_unavailable_reason": reasons[0]} if reasons else {}),
            }
        )

    def _append_error_record(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._error_index_sequence += 1
            record = {
                "sequence": self._error_index_sequence,
                "timestamp": self._timestamp(),
                "run_id": self.run_id,
                "case_id": self._case_id,
                "step_id": self._scope.get("step_id"),
                "phase": self._scope.get("phase"),
                **payload,
            }
            self._recent_error_records.append((self._monotonic(), record))
            self._recent_error_records = self._recent_error_records[-100:]
            index_file = self.artifacts_dir / "errors" / "index.jsonl"
            index_file.parent.mkdir(parents=True, exist_ok=True)
            with index_file.open("a", encoding="utf-8") as handle:
                json.dump(record, handle, ensure_ascii=False)
                handle.write("\n")
                handle.flush()

    def write(self, event: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            payload = dict(payload)
            if (
                event == "run_started"
                or any(name in self._enabled_capabilities for name in DSL_CAPABILITIES)
                or event in {"suite_completed", "suite_failed", "run_completed", "run_failed"}
            ):
                payload.setdefault("capabilities", self._capabilities_unlocked())
            if self._event_queue is not None:
                message = {"scope": dict(self._scope), "event": event, "payload": payload}
                self._event_queue.put(message)
                return {"event": event, **self._scope, **payload}
            return self._write_locked(event, payload, self._monotonic())

    def write_heartbeat_if_due(self, interval_seconds: float = 5.0) -> bool:
        with self._lock:
            now = self._monotonic()
            if now - self._last_event_monotonic < interval_seconds:
                return False
            last_sequence = self._sequence
            self._write_locked(
                "heartbeat",
                {
                    "active_duration_ms": max(0, int(round((now - self._started_monotonic) * 1000))),
                    "last_event_sequence": last_sequence,
                },
                now,
            )
            return True

    def start_heartbeat(self, interval_seconds: float = 5.0) -> None:
        if self._heartbeat_thread is not None:
            return
        self._heartbeat_stop.clear()

        def _pump() -> None:
            while not self._heartbeat_stop.wait(min(interval_seconds, 1.0)):
                self.write_heartbeat_if_due(interval_seconds)

        self._heartbeat_thread = threading.Thread(target=_pump, name="ydf-browser-heartbeat", daemon=True)
        self._heartbeat_thread.start()

    def stop_heartbeat(self) -> None:
        thread = self._heartbeat_thread
        if thread is None:
            return
        self._heartbeat_stop.set()
        thread.join(timeout=2)
        self._heartbeat_thread = None

    def _write_locked(self, event: str, payload: dict[str, Any], now: float) -> dict[str, Any]:
        self._sequence += 1
        record = {
            "sequence": self._sequence,
            "timestamp": self._timestamp(),
            "event": event,
            "run_id": self.run_id,
            **self._scope,
            **payload,
        }
        record.setdefault("evidence_refs", [])
        if event == "run_started":
            record.update(
                {
                    "tool_version": self.tool_version,
                    "contract_version": CONTRACT_VERSION,
                    "capabilities": self._capabilities_unlocked(),
                    "configuration": self.configuration,
                }
            )
        elif (
            any(name in self._enabled_capabilities for name in DSL_CAPABILITIES)
            or event in {"suite_completed", "suite_failed", "run_completed", "run_failed"}
        ):
            record.setdefault("capabilities", self._capabilities_unlocked())
        self.events_file.parent.mkdir(parents=True, exist_ok=True)
        with self.events_file.open("a", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
        self._last_event_monotonic = now
        return record

    def write_json_artifact(self, relative_path: str, payload: Any) -> str:
        relative = Path(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("artifact 路径必须位于 artifacts 目录内")
        target = self.artifacts_dir / relative
        atomic_write_json(target, payload)
        return target.relative_to(self.run_dir).as_posix()

    def evidence_reference_if_exists(self, relative_path: str) -> str | None:
        target = self.artifacts_dir / relative_path
        return target.relative_to(self.run_dir).as_posix() if target.is_file() else None

    def recent_error_records(self, started_monotonic: float, ended_monotonic: float) -> list[dict[str, Any]]:
        with self._lock:
            return [
                dict(record)
                for recorded_at, record in self._recent_error_records
                if started_monotonic - 5 <= recorded_at <= ended_monotonic + 5
            ]

    def recent_failed_request_records(
        self,
        started_monotonic: float,
        ended_monotonic: float,
    ) -> list[dict[str, Any]]:
        with self._lock:
            return [
                dict(record)
                for recorded_at, record in self._recent_network_records
                if started_monotonic - 5 <= recorded_at <= ended_monotonic + 5
                and (
                    record.get("event") in {"request_failed", "request_incomplete"}
                    or int(record.get("status") or 0) >= 400
                )
            ]

    def recent_notification_request_associations(
        self,
        notifications: list[dict[str, Any]],
        started_monotonic: float,
        ended_monotonic: float,
    ) -> list[dict[str, Any]]:
        error_notifications = [
            _notification_summary(notification)
            for notification in notifications
            if isinstance(notification, dict)
            and str(notification.get("type") or "") == "error"
            and str(notification.get("message") or "")
        ]
        if not error_notifications:
            return []
        snapshots = self.recent_network_request_snapshots(started_monotonic, ended_monotonic)
        associations = []
        for notification in error_notifications:
            matches = [
                snapshot
                for snapshot in snapshots
                if _matches_yondif_code_999_message(self.run_dir, snapshot, notification["message"])
            ]
            if len(matches) == 1:
                associations.append(_confirmed_notification_request_association(notification, matches[0]))
                continue
            unresolved = {
                "notification": notification,
                "status": "unresolved",
                "reason": "ambiguous_confirmed_match" if len(matches) > 1 else (
                    "no_confirmed_match" if snapshots else "no_candidate_requests"
                ),
                "candidate_request_ids": [str(snapshot["request_id"]) for snapshot in snapshots],
            }
            unavailable = _candidate_response_body_unavailable_reasons(snapshots)
            if unavailable:
                unresolved["candidate_response_body_unavailable_reasons"] = unavailable
            associations.append(unresolved)
        return associations

    def recent_network_request_snapshots(
        self,
        started_monotonic: float,
        ended_monotonic: float,
    ) -> list[dict[str, Any]]:
        with self._lock:
            relevant_ids = {
                str(record.get("request_id") or "")
                for recorded_at, record in self._recent_network_records
                if started_monotonic - 5 <= recorded_at <= ended_monotonic + 5
                and record.get("request_id")
            }
            records = [
                dict(record)
                for _recorded_at, record in self._recent_network_records
                if str(record.get("request_id") or "") in relevant_ids
            ]
        return _fold_network_request_records(records)

    def failure_artifact_target(self, filename: str) -> tuple[Path, str]:
        with self._lock:
            case_id = self._case_id or "unknown-case"
        safe_case_id = re.sub(r"[^0-9A-Za-z._-]+", "-", case_id).strip("-") or "unknown-case"
        relative = Path("artifacts") / "cases" / safe_case_id / filename
        target = self.run_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        return target, relative.as_posix()

    def write_failure_json(self, filename: str, payload: Any) -> str:
        target, reference = self.failure_artifact_target(filename)
        atomic_write_json(target, payload)
        return reference


def _notification_summary(notification: dict[str, Any]) -> dict[str, str]:
    return {
        "type": str(notification.get("type") or ""),
        "message": str(notification.get("message") or ""),
    }


def _fold_network_request_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    snapshots: dict[str, dict[str, Any]] = {}
    ordered_ids: list[str] = []
    for record in records:
        request_id = str(record.get("request_id") or "")
        if not request_id:
            continue
        snapshot = snapshots.get(request_id)
        if snapshot is None:
            snapshot = {"request_id": request_id}
            snapshots[request_id] = snapshot
            ordered_ids.append(request_id)
        event = str(record.get("event") or "")
        if event == "request_started":
            _copy_present(
                snapshot,
                record,
                "method",
                "original_url",
                "resource_type",
                "content_type",
                "started_step_id",
                "started_phase",
                "request_body",
            )
            continue
        snapshot["terminal_event"] = event
        _copy_present(
            snapshot,
            record,
            "actual_url",
            "response_body",
            "response_headers",
            "forwarding",
            "completed_step_id",
            "completed_phase",
            "capture_unavailable_reason",
        )
        if "status" in record:
            snapshot["http_status"] = int(record.get("status") or 0)
    return [snapshots[request_id] for request_id in ordered_ids]


def _copy_present(target: dict[str, Any], source: dict[str, Any], *keys: str) -> None:
    for key in keys:
        if key in source:
            target[key] = source[key]


def _matches_yondif_code_999_message(run_dir: Path, snapshot: dict[str, Any], message: str) -> bool:
    content = _load_response_body_content(run_dir, snapshot.get("response_body"))
    if not isinstance(content, dict):
        return False
    return str(content.get("code")) == "999" and str(content.get("message") or "") == message


def _load_response_body_content(run_dir: Path, response_body: Any) -> Any:
    if not isinstance(response_body, dict) or not response_body.get("path"):
        return None
    relative = Path(str(response_body["path"]))
    if relative.is_absolute() or ".." in relative.parts:
        return None
    try:
        payload = json.loads((run_dir / relative).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload.get("content") if isinstance(payload, dict) else None


def _confirmed_notification_request_association(
    notification: dict[str, str],
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    association: dict[str, Any] = {
        "notification": notification,
        "status": "confirmed",
        "evidence_basis": "yondif_code_999_message_exact",
        "request_id": snapshot["request_id"],
    }
    for source_key, target_key in (
        ("method", "method"),
        ("http_status", "http_status"),
        ("original_url", "original_url"),
        ("actual_url", "actual_url"),
        ("forwarding", "forwarding"),
        ("response_body", "response_body"),
    ):
        if source_key in snapshot:
            association[target_key] = snapshot[source_key]
    return association


def _candidate_response_body_unavailable_reasons(snapshots: list[dict[str, Any]]) -> dict[str, str]:
    reasons = {}
    for snapshot in snapshots:
        response_body = snapshot.get("response_body")
        reason = response_body.get("capture_unavailable_reason") if isinstance(response_body, dict) else None
        if not reason and snapshot.get("terminal_event") in {"request_failed", "request_incomplete"}:
            reason = snapshot.get("capture_unavailable_reason") or str(snapshot["terminal_event"]).removeprefix("request_")
        if reason:
            reasons[str(snapshot["request_id"])] = str(reason)
    return reasons


def atomic_write_json(path: Path, payload: Any) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(content)
            handle.flush()
        os.replace(temporary_path, path)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def classify_step_observation(step_result: Any) -> dict[str, Any]:
    if step_result.success:
        return {"outcome": "passed", "evidence_refs": []}
    existing = getattr(step_result, "observation", None)
    if isinstance(existing, dict) and existing.get("outcome") == "terminated":
        return dict(existing)
    error = step_result.data.get("error") if isinstance(step_result.data, dict) else None
    error_type = str((error or {}).get("type") or "") if isinstance(error, dict) else ""
    if error_type == "BusinessAssertionMismatch":
        return {"outcome": "assertion_failed", "reason_code": "assertion_mismatch", "evidence_refs": []}
    failure = step_result.data.get("observation_failure") if isinstance(step_result.data, dict) else None
    if error_type == "WorkflowResultObservationError" or (
        step_result.action == "workflow_panel.click" and isinstance(failure, dict)
    ):
        reason_code = str((failure or {}).get("reason_code") or "target_unavailable")
        if reason_code not in {"target_unavailable", "evidence_unavailable"}:
            reason_code = "target_unavailable"
        return {"outcome": "blocked", "reason_code": reason_code, "evidence_refs": []}
    if step_result.action == "case.setup":
        return {"outcome": "blocked", "reason_code": "environment_unavailable", "evidence_refs": []}
    message = str(step_result.message or "")
    if any(marker in message for marker in ("未绑定", "未找到指定", "不包含表格组件", "无法定位", "目标不可用")):
        return {"outcome": "blocked", "reason_code": "target_unavailable", "evidence_refs": []}
    return {"outcome": "blocked", "reason_code": "tool_error", "evidence_refs": []}


def build_business_assertion_receipt(step: Any, result: Any) -> dict[str, Any] | None:
    if not _is_business_assertion_step(step):
        return None
    target = dict(step.target or {})
    data = result.data if isinstance(result.data, dict) else {}
    comparison = data.get("assertion_comparison")
    if isinstance(comparison, dict):
        expected = comparison.get("expected")
        actual = comparison.get("actual")
        scope = comparison.get("scope")
    else:
        expected, actual = _assertion_expected_actual(result.action, target, data)
        scope = _assertion_scope(result.action, target, data)
    receipt = {
        "action": result.action,
        "business_target": {"component": step.component, "operation": step.operation},
        "expected": expected,
        "actual": actual,
        "candidate_request_ids": [],
    }
    if scope is not None:
        receipt["scope"] = scope
    else:
        receipt["scope_unavailable_reason"] = "assertion handler 未提供目标作用域"
    if result.action == "table.assert_row_values":
        receipt["matched_business_row"] = data.get("match") or target.get("match")
    return receipt


def classify_network_capture(
    *,
    original_url: str,
    actual_url: str,
    base_url: str,
    resource_type: str,
    content_type: str,
) -> dict[str, Any]:
    del actual_url
    original = urlparse(original_url)
    base = urlparse(base_url)
    if _url_origin(original) != _url_origin(base):
        return {"candidate": False, "exclusion_reason": "third_party"}
    if resource_type.lower() not in {"xhr", "fetch"}:
        return {"candidate": False, "exclusion_reason": "unsupported_resource_type"}
    path_segments = {part.lower().replace("-", "").replace("_", "") for part in original.path.split("/") if part}
    if path_segments & _AUTH_PATH_SEGMENTS:
        return {"candidate": False, "exclusion_reason": "authentication_request"}
    result = {"candidate": True}
    media_type = content_type.partition(";")[0].strip().lower()
    if media_type and not (
        media_type == "application/json"
        or media_type.endswith("+json")
        or media_type == "application/x-www-form-urlencoded"
        or media_type in {"application/xml", "text/xml"}
        or media_type.startswith("text/")
    ):
        result["body_capture_unavailable_reason"] = "unsupported_content_type"
    return result


def redact_url(value: str) -> str:
    parsed = urlparse(value)
    host = str(parsed.hostname or "")
    try:
        port = parsed.port
    except ValueError:
        port = None
    netloc = f"[{host}]" if ":" in host and not host.startswith("[") else host
    if port is not None:
        netloc = f"{netloc}:{port}"
    query = urlencode(
        [
            (name, "[REDACTED]" if sensitive_field_rule(name, auth_context=True) else item)
            for name, item in parse_qsl(parsed.query, keep_blank_values=True)
        ],
        doseq=True,
    )
    return urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, query, ""))


def _redact_forwarding(forwarding: dict[str, Any]) -> dict[str, Any]:
    rule = forwarding.get("rule")
    redacted_rule = dict(rule) if isinstance(rule, dict) else {}
    if redacted_rule.get("target"):
        redacted_rule["target"] = redact_url(str(redacted_rule["target"]))
    return {
        "matched": bool(forwarding.get("matched")),
        "rule": redacted_rule,
        "success": bool(forwarding.get("success")),
        "status": int(forwarding.get("status") or 0),
    }


def sensitive_field_rule(name: str, *, auth_context: bool = False) -> str | None:
    normalized = "".join(character for character in str(name).lower() if character.isalnum())
    for token in ("password", "passwd", "authorization", "credential", "privatekey", "apikey", "token", "secret", "session", "cookie"):
        if token in normalized:
            return token
    if auth_context and normalized == "ticket":
        return "ticket"
    return None


def redact_headers(headers: dict[str, Any]) -> tuple[dict[str, str], list[dict[str, str]]]:
    redacted: dict[str, str] = {}
    redactions: list[dict[str, str]] = []
    exact = {"authorization", "proxyauthorization", "cookie", "setcookie"}
    for name, value in headers.items():
        normalized = "".join(character for character in str(name).lower() if character.isalnum())
        rule = normalized if normalized in exact else sensitive_field_rule(str(name), auth_context=True)
        redacted[str(name)] = "[REDACTED]" if rule else str(value)
        if rule:
            redactions.append({"path": f"headers.{name}", "rule": rule})
    return redacted, redactions


def redact_json_body(value: Any) -> tuple[Any, list[dict[str, str]]]:
    redactions: list[dict[str, str]] = []

    def _redact(item: Any, path: str) -> Any:
        if isinstance(item, dict):
            output = {}
            for key, nested in item.items():
                nested_path = f"{path}.{key}"
                rule = sensitive_field_rule(str(key))
                if rule:
                    output[key] = "[REDACTED]"
                    redactions.append({"path": nested_path, "rule": rule})
                else:
                    output[key] = _redact(nested, nested_path)
            return output
        if isinstance(item, list):
            return [_redact(nested, f"{path}[{index}]") for index, nested in enumerate(item)]
        return item

    return _redact(value, "$"), redactions


def redact_form_body(value: str | bytes) -> tuple[list[list[str]], list[dict[str, str]]]:
    text = value.decode("utf-8") if isinstance(value, bytes) else str(value)
    redactions: list[dict[str, str]] = []
    output: list[list[str]] = []
    for index, (name, item) in enumerate(parse_qsl(text, keep_blank_values=True)):
        rule = sensitive_field_rule(name)
        output.append([name, "[REDACTED]" if rule else item])
        if rule:
            redactions.append({"path": f"$[{index}].{name}", "rule": rule})
    return output, redactions


def redact_xml_body(value: str | bytes) -> tuple[str, list[dict[str, str]]]:
    root = ElementTree.fromstring(value)
    redactions: list[dict[str, str]] = []

    def _walk(element: Any, path: str) -> None:
        tag = str(element.tag).rsplit("}", 1)[-1]
        current_path = f"{path}/{tag}"
        rule = sensitive_field_rule(tag)
        if rule and element.text is not None:
            element.text = "[REDACTED]"
            redactions.append({"path": current_path, "rule": rule})
        for name in list(element.attrib):
            attribute_rule = sensitive_field_rule(str(name).rsplit("}", 1)[-1])
            if attribute_rule:
                element.attrib[name] = "[REDACTED]"
                redactions.append({"path": f"{current_path}/@{name}", "rule": attribute_rule})
        for child in element:
            _walk(child, current_path)

    _walk(root, "$")
    return ElementTree.tostring(root, encoding="unicode"), redactions


def prepare_redacted_body(body: bytes | str | None, content_type: str) -> dict[str, Any]:
    if body is None or body == b"" or body == "":
        return {"capture_unavailable_reason": "not_present", "original_size": 0}
    raw = body if isinstance(body, bytes) else str(body).encode("utf-8")
    media_type, charset = _parse_content_type(content_type)
    if not _supported_body_media_type(media_type):
        return {
            "capture_unavailable_reason": "unsupported_content_type",
            "content_type": media_type,
            "charset": charset,
            "original_size": len(raw),
        }
    try:
        text = raw.decode(charset)
    except (LookupError, UnicodeDecodeError):
        return {
            "capture_unavailable_reason": "redaction_unsupported",
            "content_type": media_type,
            "charset": charset,
            "original_size": len(raw),
        }
    try:
        if media_type == "application/json" or media_type.endswith("+json"):
            content, redactions = redact_json_body(json.loads(text))
        elif media_type == "application/x-www-form-urlencoded":
            if "=" not in text:
                raise ValueError("unsafe form body")
            content, redactions = redact_form_body(text)
        elif media_type in {"application/xml", "text/xml"} or media_type.endswith("+xml"):
            content, redactions = redact_xml_body(text)
        elif media_type.startswith("text/"):
            content, redactions = _prepare_redacted_text_body(text)
        else:
            raise ValueError("unsupported content type")
    except (ElementTree.ParseError, json.JSONDecodeError, ValueError):
        return {
            "capture_unavailable_reason": "redaction_unsupported",
            "content_type": media_type,
            "charset": charset,
            "original_size": len(raw),
        }
    return {
        "representation": "redacted_semantic",
        "content_type": media_type,
        "charset": charset,
        "original_size": len(raw),
        "content": content,
        "redactions": redactions,
    }


def redact_error_text(value: str) -> dict[str, Any]:
    text = str(value or "")
    redaction_count = 0

    def _redact_url_match(match: Any) -> str:
        nonlocal redaction_count
        redacted = redact_url(match.group(0))
        if redacted != match.group(0):
            redaction_count += 1
        return redacted

    text = re.sub(r"https?://[^\s'\"]+", _redact_url_match, text)

    def _redact_credential(match: Any) -> str:
        nonlocal redaction_count
        redaction_count += 1
        return f"{match.group(1)}[REDACTED]"

    text = re.sub(
        r"(?i)\b((?:authorization\s*[:=]\s*)?(?:bearer|basic)\s+)[^\s,;]+",
        _redact_credential,
        text,
    )
    text, jwt_count = re.subn(
        r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{6,}(?![A-Za-z0-9_-])",
        "[REDACTED]",
        text,
    )
    redaction_count += jwt_count

    assignment = re.compile(r"(?i)([A-Za-z][A-Za-z0-9_.-]*)\s*([:=])\s*([\"']?)([^\s,;\"']+)([\"']?)")

    def _redact_assignment(match: Any) -> str:
        nonlocal redaction_count
        if sensitive_field_rule(match.group(1), auth_context=True) is None:
            return match.group(0)
        redaction_count += 1
        return f"{match.group(1)}{match.group(2)}{match.group(3)}[REDACTED]{match.group(5)}"

    text = assignment.sub(_redact_assignment, text)
    probe = re.sub(r"https?://[^\s'\"]+", "", text)
    probe = assignment.sub("", probe)
    for name in re.findall(r"[A-Za-z][A-Za-z0-9_.-]*", probe):
        if sensitive_field_rule(name, auth_context=True):
            return {
                "text": None,
                "redaction_count": 0,
                "capture_unavailable_reason": "redaction_unsupported",
            }
    return {"text": text, "redaction_count": redaction_count, "capture_unavailable_reason": None}


def sanitize_evidence_payload(value: Any, *, key: str = "") -> Any:
    if sensitive_field_rule(key, auth_context=True):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(name): sanitize_evidence_payload(item, key=str(name)) for name, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_evidence_payload(item, key=key) for item in value]
    if isinstance(value, str) and value.lower().startswith(("http://", "https://")):
        return redact_url(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def build_table_assertion_snapshot(
    rows: list[dict[str, Any]],
    *,
    assertion_columns: list[str],
    identity_columns: list[str],
    max_bytes: int = 1024 * 1024,
) -> dict[str, Any]:
    safe_rows = [sanitize_evidence_payload(row) for row in rows if isinstance(row, dict)]
    snapshot = {
        "capture_scope": "current_rendered_page",
        "visible_business_row_count": len(safe_rows),
        "sample_row_count": len(safe_rows),
        "sample_truncated": False,
        "rows": safe_rows,
    }
    if len(json.dumps(snapshot, ensure_ascii=False).encode("utf-8")) <= max_bytes:
        return snapshot
    columns = list(dict.fromkeys([*assertion_columns, *identity_columns]))
    sample = [{column: row.get(column) for column in columns if column in row} for row in safe_rows[:10]]
    return {
        **snapshot,
        "sample_row_count": len(sample),
        "sample_truncated": True,
        "rows": sample,
    }


def sanitize_dom_semantic_summary(
    raw_nodes: list[dict[str, Any]],
    *,
    max_bytes: int = 256 * 1024,
) -> dict[str, Any]:
    summary: dict[str, Any] = {"nodes": [], "redaction_count": 0, "truncated": False}
    for raw in raw_nodes:
        if not isinstance(raw, dict) or not bool(raw.get("visible")):
            continue
        tag = str(raw.get("tag") or "").lower()
        input_type = str(raw.get("type") or "").lower()
        if tag in {"script", "style"} or input_type == "hidden":
            continue
        identities = [str(raw.get(key) or "") for key in ("name", "id", "fieldid", "owner_fieldid", "data_field")]
        sensitive = (
            input_type == "password"
            or str(raw.get("autocomplete") or "").lower() in {"current-password", "new-password"}
            or any(sensitive_field_rule(identity, auth_context=True) for identity in identities)
        )
        node = {
            key: str(raw.get(key) or "")[:1000]
            for key in ("frame_url", "tag", "role", "label", "field_label", "placeholder", "name", "id", "fieldid", "owner_fieldid", "data_field", "text", "value")
            if raw.get(key) not in (None, "")
        }
        node.update({key: bool(raw[key]) for key in ("disabled", "selected", "invalid", "text_truncated", "constraints_truncated") if key in raw})
        if "required" in raw:
            node["required"] = raw["required"] if isinstance(raw["required"], bool) else None
            node["required_sources"] = [source for source in (
                "html_required", "aria_required_true", "wui_required_label", "aria_required_false"
            ) if source in (raw.get("required_sources") or [])]
        attributes = raw.get("constraint_attributes")
        if isinstance(attributes, dict):
            node["constraint_attributes"] = {
                key: str(attributes[key])[:1000]
                for key in ("type", "pattern", "minlength", "maxlength", "min", "max", "step")
                if key in attributes
            }
        if sensitive:
            for key in ("text", "value", "placeholder"):
                if key in node:
                    node[key] = "[REDACTED]"
            if "constraint_attributes" in node:
                node["constraint_attributes"] = {key: "[REDACTED]" for key in node["constraint_attributes"]}
            summary["redaction_count"] += 1
        summary["nodes"].append(node)
        if len(json.dumps(summary, ensure_ascii=False).encode("utf-8")) > max_bytes:
            summary["nodes"].pop()
            summary["truncated"] = True
            break
    while summary["nodes"] and len(json.dumps(summary, ensure_ascii=False).encode("utf-8")) > max_bytes:
        summary["nodes"].pop()
        summary["truncated"] = True
    return summary


def _prepare_redacted_text_body(text: str) -> tuple[Any, list[dict[str, str]]]:
    stripped = text.strip()
    if stripped.startswith(("{", "[")):
        return redact_json_body(json.loads(text))
    if stripped.startswith("<"):
        return redact_xml_body(text)
    if "=" in text:
        return redact_form_body(text)
    raise ValueError("unsafe plain text")


def _parse_content_type(value: str) -> tuple[str, str]:
    parts = [part.strip() for part in str(value or "").split(";")]
    media_type = parts[0].lower()
    charset = "utf-8"
    for part in parts[1:]:
        name, separator, item = part.partition("=")
        if separator and name.strip().lower() == "charset" and item.strip():
            charset = item.strip().strip('"').lower()
            break
    return media_type, charset


def _supported_body_media_type(media_type: str) -> bool:
    return bool(
        media_type == "application/json"
        or media_type.endswith("+json")
        or media_type == "application/x-www-form-urlencoded"
        or media_type in {"application/xml", "text/xml"}
        or media_type.endswith("+xml")
        or media_type.startswith("text/")
    )


def _header_value(headers: dict[str, Any], name: str) -> str:
    expected = name.lower()
    return next((str(value) for key, value in headers.items() if str(key).lower() == expected), "")


def _declared_content_length(headers: dict[str, Any]) -> int:
    try:
        return max(0, int(_header_value(headers, "content-length") or 0))
    except (TypeError, ValueError):
        return 0


def _url_origin(parsed: Any) -> tuple[str, str, int | None]:
    try:
        port = parsed.port
    except ValueError:
        port = None
    if port is None:
        port = 443 if parsed.scheme.lower() == "https" else 80 if parsed.scheme.lower() == "http" else None
    return parsed.scheme.lower(), str(parsed.hostname or "").lower(), port


def _assertion_expected_actual(action: str, target: dict[str, Any], data: dict[str, Any]) -> tuple[Any, Any]:
    if action == "form.assert_values":
        fields = target.get("fields") or target.get("values")
        if not isinstance(fields, dict):
            fields = {str(target.get("field") or ""): target.get("equals")}
        actual = {str(item.get("field")): item.get("actual") for item in data.get("fields") or []}
        return {"fields": fields}, {"fields": actual}
    if action == "notification.assert":
        return target, {"notification": data.get("notification")}
    if action == "table.assert_column_values":
        return {key: target.get(key) for key in ("column", "equals")}, {
            "column": data.get("column") or target.get("column"),
            "values": data.get("values"),
        }
    if action == "table.assert_columns":
        return {"present": target.get("present") or [], "absent": target.get("absent") or []}, {
            "headers": data.get("headers")
        }
    if action == "table.assert_empty":
        column = data.get("column") or target.get("column") or "项目名称"
        return {"column": column, "empty": True}, {"column": column, "values": data.get("values")}
    expected_fields = target.get("fields") or target.get("values") or {}
    actual_fields = {str(item.get("field")): item.get("actual") for item in data.get("fields") or []}
    return {"match": target.get("match"), "fields": expected_fields}, {"fields": actual_fields}


def _assertion_scope(action: str, target: dict[str, Any], data: dict[str, Any]) -> Any:
    if isinstance(data.get("table_scope"), dict):
        return data["table_scope"]
    if action == "form.assert_values":
        return {
            "fields": [
                {key: item.get(key) for key in ("field", "fieldid", "property_uri") if item.get(key) is not None}
                for item in data.get("fields") or []
            ]
        }
    if action == "notification.assert":
        return {"surface": "notification"}
    if action == "table.assert_empty":
        return {"table": target.get("table"), "column": data.get("column") or target.get("column")}
    return None
