from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from ydf_browser.action_completion import (
    ActionCompletion,
    ActionCompletionObservation,
    ActionCompletionRequest,
    ActionNotification,
)


class InMemoryActionCompletionAdapter:
    def __init__(self, observations: list[ActionCompletionObservation] | None = None) -> None:
        self.observations = list(observations or [])
        self.events: list[str] = []
        self.now = 0.0
        self.active = False
        self.current_observation: ActionCompletionObservation | None = None

    def _acquire_action_completion(self) -> None:
        if self.active:
            raise RuntimeError("已有动作正在等待完成")
        self.active = True

    def _release_action_completion(self) -> None:
        self.active = False

    def _prepare_action_completion(self, request: ActionCompletionRequest) -> None:
        self.events.append(f"prepare:{request.action}")
        self.current_observation = None

    def _observe_action_completion(
        self,
        request: ActionCompletionRequest,
        stage: str = "",
    ) -> ActionCompletionObservation:
        self.events.append(f"observe:{stage or 'all'}:{request.action}")
        if self.current_observation is None:
            self.current_observation = (
                self.observations.pop(0) if self.observations else ActionCompletionObservation()
            )
        observation = self.current_observation
        if stage == "notifications":
            return ActionCompletionObservation(notifications=observation.notifications)
        if stage == "dynamic_template":
            return ActionCompletionObservation(
                dynamic_template=observation.dynamic_template,
                dynamic_template_fallback=observation.dynamic_template_fallback,
            )
        if stage == "dom":
            self.current_observation = None
            return ActionCompletionObservation(dom_signal=observation.dom_signal)
        self.current_observation = None
        return observation

    def _action_completion_now(self) -> float:
        return self.now

    def _wait_action_completion_poll(self, timeout_ms: int) -> None:
        self.events.append(f"wait:{timeout_ms}")
        self.now += timeout_ms / 1000


def test_execute_captures_baseline_before_action_and_prefers_notification() -> None:
    adapter = InMemoryActionCompletionAdapter(
        [
            ActionCompletionObservation(
                notifications=(ActionNotification(type="success", message="保存成功"),),
                dynamic_template=True,
                dom_signal="foreground_state",
            )
        ]
    )
    completion = ActionCompletion(adapter)

    def click() -> None:
        adapter.events.append("click")

    result = completion.execute(
        ActionCompletionRequest(action="toolbar.click", context={"action": "保存"}),
        click,
    )

    assert adapter.events == [
        "prepare:toolbar.click",
        "click",
        "observe:notifications:toolbar.click",
    ]
    assert result.step_data() == {
        "completion_signal": "notification",
        "wait_duration_ms": 0,
        "fallback_used": False,
        "notifications": [{"type": "success", "message": "保存成功"}],
        "contract_path": {
            "contract_version": "1.0.1",
            "applicability": "verified",
            "rule_ids": ["PRS-COMPLETE-001"],
            "fallback_reason": None,
        },
    }


def test_workflow_panel_without_completion_signal_fails_instead_of_falling_back() -> None:
    adapter = InMemoryActionCompletionAdapter()
    with pytest.raises(TimeoutError, match="工作流操作面板.*完成信号"):
        ActionCompletion(adapter).execute(ActionCompletionRequest("workflow_panel.click"), lambda: None)
    assert adapter.active is False


def test_execute_prefers_dynamic_template_before_dom_signal() -> None:
    adapter = InMemoryActionCompletionAdapter(
        [ActionCompletionObservation(dynamic_template=True, dom_signal="foreground_state")]
    )

    result = ActionCompletion(adapter).execute(
        ActionCompletionRequest(action="dialog.click"),
        lambda: None,
    )

    assert result.completion_signal == "dynamic_template"
    assert result.fallback_used is False
    assert result.step_data()["contract_path"]["rule_ids"] == ["PRS-COMPLETE-002"]
    assert adapter.events == [
        "prepare:dialog.click",
        "observe:notifications:dialog.click",
        "observe:dynamic_template:dialog.click",
    ]


def test_execute_keeps_captured_notification_when_dom_signal_completes() -> None:
    adapter = InMemoryActionCompletionAdapter(
        [
            ActionCompletionObservation(
                notifications=(ActionNotification(type="warning", message="请确认当前数据"),),
                dom_signal="foreground_state",
            )
        ]
    )

    result = ActionCompletion(adapter).execute(
        ActionCompletionRequest(action="dialog.click"),
        lambda: None,
    )

    assert result.step_data()["notifications"] == [
        {"type": "warning", "message": "请确认当前数据"}
    ]


def test_execute_records_unverified_dynamic_template_fallback() -> None:
    adapter = InMemoryActionCompletionAdapter(
        [ActionCompletionObservation(dynamic_template_fallback=True)]
    )

    result = ActionCompletion(adapter).execute(
        ActionCompletionRequest(action="toolbar.click", context={"action": "新增"}),
        lambda: None,
    )

    assert result.completion_signal == "dynamic_template"
    assert result.fallback_used is True
    assert result.step_data()["contract_path"] == {
        "contract_version": "1.0.1",
        "applicability": "unverified",
        "rule_ids": ["PRS-COMPLETE-002"],
        "fallback_reason": "exact_identity_unavailable",
    }


@pytest.mark.parametrize(
    ("action", "context", "timeout_ms"),
    [
        ("tab.click", {}, 19000),
        ("toolbar.click", {"action": "新增"}, 6500),
        ("toolbar.click", {"action": "保存"}, 24000),
        ("toolbar.click", {"action": "更多", "sub_label": "导出"}, 24000),
        ("action.click", {}, 6500),
        ("dialog.click", {}, 24000),
        ("query.search", {}, 17500),
    ],
)
def test_execute_owns_action_timeout_policy(
    action: str,
    context: dict[str, Any],
    timeout_ms: int,
) -> None:
    adapter = InMemoryActionCompletionAdapter()

    result = ActionCompletion(adapter).execute(
        ActionCompletionRequest(action=action, context=context),
        lambda: None,
    )

    assert result.completion_signal == "compatibility_timeout"
    assert result.wait_duration_ms == timeout_ms
    assert result.fallback_used is True


def test_execute_returns_target_component_contract_path() -> None:
    adapter = InMemoryActionCompletionAdapter(
        [ActionCompletionObservation(dom_signal="target_component")]
    )

    result = ActionCompletion(adapter).execute(
        ActionCompletionRequest(action="query.search"),
        lambda: None,
    )

    assert result.step_data()["contract_path"]["rule_ids"] == ["PRS-COMPLETE-004"]


def test_execute_leaves_specialized_completion_outside_generic_wait() -> None:
    adapter = InMemoryActionCompletionAdapter()

    result = ActionCompletion(adapter).execute(
        ActionCompletionRequest(action="dialog.click"),
        lambda: False,
    )

    assert adapter.events == ["prepare:dialog.click"]
    assert result.specialized is True
    assert result.step_data() == {}


def test_request_and_result_are_immutable() -> None:
    request = ActionCompletionRequest(action="tab.click", context={"tab": "待提交"})
    adapter = InMemoryActionCompletionAdapter(
        [ActionCompletionObservation(dom_signal="tab_active")]
    )
    result = ActionCompletion(adapter).execute(request, lambda: None)

    with pytest.raises(TypeError):
        request.context["tab"] = "草稿"  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        result.completion_signal = "other"  # type: ignore[misc]


def test_execute_rejects_reentry_and_cleans_state_after_action_error() -> None:
    adapter = InMemoryActionCompletionAdapter(
        [ActionCompletionObservation(dom_signal="tab_active")]
    )
    completion = ActionCompletion(adapter)
    request = ActionCompletionRequest(action="tab.click")

    def reenter() -> None:
        completion.execute(request, lambda: None)

    with pytest.raises(RuntimeError, match="已有动作正在等待完成"):
        completion.execute(request, reenter)

    result = completion.execute(request, lambda: None)
    assert result.completion_signal == "tab_active"


def test_execute_reraises_original_action_error_and_cleans_state() -> None:
    adapter = InMemoryActionCompletionAdapter(
        [ActionCompletionObservation(dom_signal="foreground_state")]
    )
    completion = ActionCompletion(adapter)

    def fail() -> None:
        raise ValueError("click failed")

    with pytest.raises(ValueError, match="click failed"):
        completion.execute(ActionCompletionRequest(action="action.click"), fail)

    result = completion.execute(ActionCompletionRequest(action="action.click"), lambda: None)
    assert result.completion_signal == "foreground_state"


def test_constructor_rejects_missing_adapter_capability() -> None:
    with pytest.raises(RuntimeError, match="动作完成 adapter 缺少能力"):
        ActionCompletion(object())


def test_execute_honors_cancellation_before_click() -> None:
    adapter = InMemoryActionCompletionAdapter()
    clicked: list[bool] = []

    with pytest.raises(TimeoutError, match="已请求停止"):
        ActionCompletion(adapter).execute(
            ActionCompletionRequest(action="toolbar.click", cancelled=lambda: True),
            lambda: clicked.append(True),
        )

    assert clicked == []


def test_execute_rejects_expired_deadline_before_click() -> None:
    adapter = InMemoryActionCompletionAdapter()
    clicked: list[bool] = []

    with pytest.raises(TimeoutError, match="步骤期限"):
        ActionCompletion(adapter).execute(
            ActionCompletionRequest(action="toolbar.click", deadline=0.0),
            lambda: clicked.append(True),
        )

    assert clicked == []


def test_execute_rejects_signal_observed_after_deadline() -> None:
    adapter = InMemoryActionCompletionAdapter(
        [ActionCompletionObservation(dom_signal="foreground_state")]
    )
    original_observe = adapter._observe_action_completion

    def observe(
        request: ActionCompletionRequest,
        stage: str = "",
    ) -> ActionCompletionObservation:
        result = original_observe(request, stage)
        adapter.now = 0.2
        return result

    adapter._observe_action_completion = observe  # type: ignore[method-assign]

    with pytest.raises(TimeoutError, match="步骤期限"):
        ActionCompletion(adapter).execute(
            ActionCompletionRequest(action="dialog.click", deadline=0.1),
            lambda: None,
        )


def test_execute_rejects_signal_when_cancelled_during_observation() -> None:
    adapter = InMemoryActionCompletionAdapter(
        [ActionCompletionObservation(dom_signal="foreground_state")]
    )
    cancelled = False
    original_observe = adapter._observe_action_completion

    def observe(
        request: ActionCompletionRequest,
        stage: str = "",
    ) -> ActionCompletionObservation:
        nonlocal cancelled
        result = original_observe(request, stage)
        cancelled = True
        return result

    adapter._observe_action_completion = observe  # type: ignore[method-assign]

    with pytest.raises(TimeoutError, match="已请求停止"):
        ActionCompletion(adapter).execute(
            ActionCompletionRequest(
                action="dialog.click",
                cancelled=lambda: cancelled,
            ),
            lambda: None,
        )


def test_execute_rejects_reentry_across_modules_sharing_adapter() -> None:
    adapter = InMemoryActionCompletionAdapter(
        [ActionCompletionObservation(dom_signal="foreground_state")]
    )
    first = ActionCompletion(adapter)
    second = ActionCompletion(adapter)

    with pytest.raises(RuntimeError, match="已有动作正在等待完成"):
        first.execute(
            ActionCompletionRequest(action="action.click"),
            lambda: second.execute(
                ActionCompletionRequest(action="action.click"),
                lambda: None,
            ),
        )
