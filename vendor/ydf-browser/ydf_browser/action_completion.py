from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Protocol

from .platform_rendering_contract import build_contract_path


_ACTION_TIMEOUT_MS = {
    "workflow_panel.click": 24000,
    "tab.click": 19000,
    "action.click": 6500,
    "dialog.click": 24000,
    "query.search": 17500,
}
_STANDARD_SUCCESS_MARKERS = (
    "保存成功",
    "提交成功",
    "查询成功",
    "新增成功",
    "删除成功",
    "更新成功",
    "操作成功",
    "打开成功",
)
_POLL_INTERVAL_MS = 100


@dataclass(frozen=True)
class ActionNotification:
    type: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"type": self.type, "message": self.message}


@dataclass(frozen=True)
class ActionCompletionRequest:
    action: str
    context: Mapping[str, Any] = field(default_factory=dict)
    deadline: float | None = None
    cancelled: Callable[[], bool] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "context", MappingProxyType(dict(self.context)))


@dataclass(frozen=True)
class ActionCompletionObservation:
    notifications: tuple[ActionNotification, ...] = ()
    dynamic_template: bool = False
    dynamic_template_fallback: bool = False
    dom_signal: str = ""


@dataclass(frozen=True)
class ActionCompletionResult:
    completion_signal: str = ""
    wait_duration_ms: int = 0
    fallback_used: bool = False
    notifications: tuple[ActionNotification, ...] = ()
    rule_id: str = ""
    fallback_reason: str | None = None
    specialized: bool = False

    def step_data(self) -> dict[str, Any]:
        if self.specialized:
            return {}
        data: dict[str, Any] = {
            "completion_signal": self.completion_signal,
            "wait_duration_ms": self.wait_duration_ms,
            "fallback_used": self.fallback_used,
            "contract_path": build_contract_path(
                "unverified" if self.fallback_used else "verified",
                [self.rule_id],
                self.fallback_reason,
            ),
        }
        if self.notifications:
            data["notifications"] = [item.as_dict() for item in self.notifications]
        return data


class _ActionCompletionAdapter(Protocol):
    def _acquire_action_completion(self) -> None: ...

    def _release_action_completion(self) -> None: ...

    def _prepare_action_completion(self, request: ActionCompletionRequest) -> None: ...

    def _observe_action_completion(
        self,
        request: ActionCompletionRequest,
        stage: str = "",
    ) -> ActionCompletionObservation: ...

    def _action_completion_now(self) -> float: ...

    def _wait_action_completion_poll(self, timeout_ms: int) -> None: ...


class ActionCompletion:
    def __init__(self, adapter: _ActionCompletionAdapter) -> None:
        required = (
            "_acquire_action_completion",
            "_release_action_completion",
            "_prepare_action_completion",
            "_observe_action_completion",
            "_action_completion_now",
            "_wait_action_completion_poll",
        )
        missing = [name for name in required if not callable(getattr(adapter, name, None))]
        if missing:
            raise RuntimeError(f"动作完成 adapter 缺少能力: {', '.join(missing)}")
        self._adapter = adapter

    def execute(
        self,
        request: ActionCompletionRequest,
        action: Callable[[], bool | None],
    ) -> ActionCompletionResult:
        timeout_ms = _action_timeout_ms(request)
        self._raise_if_stopped(request)
        self._adapter._acquire_action_completion()
        try:
            self._adapter._prepare_action_completion(request)
            self._raise_if_stopped(request)
            if action() is False:
                self._raise_if_stopped(request)
                return ActionCompletionResult(specialized=True)
            self._raise_if_stopped(request)
            started = self._adapter._action_completion_now()
            policy_deadline = started + timeout_ms / 1000
            observed_notifications: tuple[ActionNotification, ...] = ()
            while True:
                timeout_result = self._check_wait_limit(
                    request,
                    policy_deadline,
                    started,
                    observed_notifications,
                )
                if timeout_result is not None:
                    return timeout_result
                observation = self._adapter._observe_action_completion(request, stage="notifications")
                observed_notifications = _merge_notifications(
                    observed_notifications,
                    observation.notifications,
                )
                timeout_result = self._check_wait_limit(
                    request,
                    policy_deadline,
                    started,
                    observed_notifications,
                )
                if timeout_result is not None:
                    return timeout_result
                standard_notifications = tuple(
                    item for item in observation.notifications if _is_standard_notification(item)
                )
                if standard_notifications:
                    return self._result(
                        signal="notification",
                        started=started,
                        notifications=observed_notifications,
                        rule_id="PRS-COMPLETE-001",
                    )
                dynamic_observation = self._adapter._observe_action_completion(
                    request,
                    stage="dynamic_template",
                )
                timeout_result = self._check_wait_limit(
                    request,
                    policy_deadline,
                    started,
                    observed_notifications,
                )
                if timeout_result is not None:
                    return timeout_result
                if dynamic_observation.dynamic_template:
                    return self._result(
                        signal="dynamic_template",
                        started=started,
                        notifications=observed_notifications,
                        rule_id="PRS-COMPLETE-002",
                    )
                if dynamic_observation.dynamic_template_fallback:
                    return self._result(
                        signal="dynamic_template",
                        started=started,
                        notifications=observed_notifications,
                        rule_id="PRS-COMPLETE-002",
                        fallback=True,
                        fallback_reason="exact_identity_unavailable",
                    )
                dom_observation = self._adapter._observe_action_completion(request, stage="dom")
                timeout_result = self._check_wait_limit(
                    request,
                    policy_deadline,
                    started,
                    observed_notifications,
                )
                if timeout_result is not None:
                    return timeout_result
                if dom_observation.dom_signal:
                    return self._result(
                        signal=dom_observation.dom_signal,
                        started=started,
                        notifications=observed_notifications,
                        rule_id=(
                            "PRS-COMPLETE-004"
                            if dom_observation.dom_signal == "target_component"
                            else "PRS-COMPLETE-003"
                        ),
                    )
                now = self._adapter._action_completion_now()
                deadline = min(policy_deadline, request.deadline) if request.deadline is not None else policy_deadline
                wait_ms = max(1, min(_POLL_INTERVAL_MS, math.ceil((deadline - now) * 1000)))
                self._adapter._wait_action_completion_poll(wait_ms)
        finally:
            self._adapter._release_action_completion()

    def _result(
        self,
        *,
        signal: str,
        started: float,
        notifications: tuple[ActionNotification, ...],
        rule_id: str,
        fallback: bool = False,
        fallback_reason: str | None = None,
    ) -> ActionCompletionResult:
        elapsed_ms = max(
            0,
            int(round((self._adapter._action_completion_now() - started) * 1000)),
        )
        return ActionCompletionResult(
            completion_signal=signal,
            wait_duration_ms=elapsed_ms,
            fallback_used=fallback,
            notifications=notifications,
            rule_id=rule_id,
            fallback_reason=fallback_reason,
        )

    def _raise_if_stopped(self, request: ActionCompletionRequest) -> None:
        if request.cancelled is not None and request.cancelled():
            raise TimeoutError("AI 观察运行已请求停止")
        if (
            request.deadline is not None
            and self._adapter._action_completion_now() + 1e-9 >= request.deadline
        ):
            raise TimeoutError("动作完成等待超过步骤期限")

    def _check_wait_limit(
        self,
        request: ActionCompletionRequest,
        policy_deadline: float,
        started: float,
        notifications: tuple[ActionNotification, ...],
    ) -> ActionCompletionResult | None:
        self._raise_if_stopped(request)
        if self._adapter._action_completion_now() + 1e-9 < policy_deadline:
            return None
        if request.action == "workflow_panel.click":
            raise TimeoutError("工作流操作面板动作超时，未取得关联完成信号")
        return self._result(
            signal="compatibility_timeout",
            started=started,
            notifications=notifications,
            rule_id="PRS-FALLBACK-001",
            fallback=True,
            fallback_reason="strong_completion_signal_unavailable",
        )


def _action_timeout_ms(request: ActionCompletionRequest) -> int:
    if request.action == "toolbar.click":
        label = str(request.context.get("action") or "")
        return 24000 if label in {"保存", "提交"} or request.context.get("sub_label") else 6500
    try:
        return _ACTION_TIMEOUT_MS[request.action]
    except KeyError as exc:
        raise RuntimeError(f"不支持的动作完成类型: {request.action}") from exc


def _is_standard_notification(notification: ActionNotification) -> bool:
    kind = notification.type.lower()
    if kind == "error":
        return True
    return kind == "success" and any(marker in notification.message for marker in _STANDARD_SUCCESS_MARKERS)


def _merge_notifications(
    *groups: tuple[ActionNotification, ...],
) -> tuple[ActionNotification, ...]:
    merged: list[ActionNotification] = []
    by_message: dict[str, int] = {}
    for group in groups:
        for item in group:
            message = " ".join(item.message.split())
            if not message:
                continue
            notification = ActionNotification(type=item.type or "info", message=message)
            existing_index = by_message.get(message)
            if existing_index is not None:
                if merged[existing_index].type == "info" and notification.type != "info":
                    merged[existing_index] = notification
                continue
            by_message[message] = len(merged)
            merged.append(notification)
    return tuple(merged)
