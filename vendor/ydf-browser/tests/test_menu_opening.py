from copy import deepcopy
from dataclasses import FrozenInstanceError
import time
from types import SimpleNamespace
from typing import Any

import pytest

from ydf_browser.menu_opening import (
    MenuOpening,
    MenuOpeningError,
    MenuOpeningRequest,
    _OPEN_MENU_WORK_SURFACES_SCRIPT,
    _open_menu_work_surface_specs,
)
from ydf_browser.models import MenuTarget, PageManifest, PageMeta, Region
from ydf_browser.runtime import FixtureGateway, FixtureRuntime


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def advance(self, timeout_ms: int) -> None:
        self.now += timeout_ms / 1000


class _BrowserGateway(FixtureGateway):
    def resolve_menu(self, menu_path: str, timeout_seconds: float | None = None) -> MenuTarget:
        return super().resolve_menu(menu_path)

    def fetch_template(self, menu_target: MenuTarget, timeout_seconds: float | None = None) -> dict:
        raise AssertionError("browser 菜单打开不得调用 gateway.fetch_template")


class _BrowserRuntime(FixtureRuntime):
    def __init__(
        self,
        runtime_elements: list[dict],
        template_payload: dict[str, Any],
        *,
        frames: list[dict[str, Any]] | None = None,
        visible_results: list[bool] | None = None,
    ) -> None:
        super().__init__(runtime_elements)
        self.template_payload = template_payload
        self.frames = frames or [
            {"name": "", "url": "https://example.test", "is_main": True, "parent_is_main": False}
        ]
        self.visible_results = visible_results or [True]
        self.reload_count = 0
        self.response_events: list[dict[str, Any]] = []
        self.surface_count = 0
        self.config = SimpleNamespace(
            base_url="https://example.test",
            endpoints=SimpleNamespace(
                service_detail="/service/detail",
                templates="/matchingTemplate",
                template_body="/getTemplateBody",
            ),
        )

    def begin_notification_capture(self) -> None:
        return

    def begin_page_response_capture(self) -> int:
        self.response_events = []
        return 0

    def page_error_cursor(self) -> int:
        return 0

    def page_errors_since(self, cursor: int) -> tuple[int, list[dict[str, Any]]]:
        return cursor, []

    def page_responses_since(self, cursor: int) -> tuple[int, list[dict[str, Any]]]:
        return len(self.response_events), self.response_events[cursor:]

    def pop_dynamic_template_payload(self) -> None:
        return None

    def open_menu(self, menu_target: MenuTarget) -> None:
        super().open_menu(menu_target)
        self.response_events.append(
            {
                "method": "POST",
                "url": "https://example.test/matchingTemplate",
                "status": 200,
                "payload": self.template_payload,
            }
        )

    def wait_for_first_visible(self, selectors: list[str], timeout_ms: int) -> bool:
        return self.visible_results.pop(0) if len(self.visible_results) > 1 else self.visible_results[0]

    def current_page_url(self) -> str:
        return "https://example.test/#/service/fixture_service"

    def reload_page(self) -> None:
        self.reload_count += 1

    def page_frame_states(self) -> list[dict[str, Any]]:
        return list(self.frames)

    def evaluate_all_frames(self, script: str, payload: Any) -> list[dict[str, Any]]:
        self.surface_count += 1
        surface = _surface(
            "main",
            "main_table",
            busy=1 if self.surface_count == 1 else 0,
            terminal=self.surface_count > 1,
            signature="loading" if self.surface_count == 1 else "row:1",
        )
        return [{"frame_name": "bill", "frame_url": "fixture://bill", "value": [surface]}]


class _ReadinessRuntime(FixtureRuntime):
    menu_opening_work_surfaces = True

    def __init__(
        self,
        runtime_elements: list[dict],
        snapshots: list[list[dict[str, Any]]],
        clock: _Clock,
        *,
        notifications: list[dict[str, str]] | None = None,
        page_errors: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(runtime_elements)
        self.snapshots = snapshots
        self.clock = clock
        self.notifications = notifications or []
        self.page_errors = page_errors or []
        self.capture_count = 0
        self.page_closed = False

    def capture_open_menu_work_surfaces(self, manifest) -> list[dict[str, Any]]:
        index = min(self.capture_count, len(self.snapshots) - 1)
        self.capture_count += 1
        return [dict(item) for item in self.snapshots[index]]

    def wait_for_timeout(self, timeout_ms: int) -> None:
        self.clock.advance(timeout_ms)

    def collect_notifications(self) -> list[dict[str, str]]:
        return list(self.notifications)

    def collect_open_menu_page_errors(self) -> list[dict[str, Any]]:
        return list(self.page_errors)


def _surface(
    key: str,
    region_type: str,
    *,
    busy: int = 0,
    terminal: bool = False,
    signature: str = "",
    transition_busy: int | None = None,
    transition_signature: str | None = None,
    nested: bool = False,
    error: str = "",
) -> dict[str, Any]:
    return {
        "key": key,
        "region_type": region_type,
        "busy": busy,
        "terminal": terminal,
        "signature": signature,
        "transition_busy": busy if transition_busy is None else transition_busy,
        "transition_signature": signature if transition_signature is None else transition_signature,
        "error": error,
        "_nested_identity_root": nested,
    }


def test_menu_opening_fixture_returns_bound_immutable_result(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    menu_opening = MenuOpening.for_fixture(
        FixtureGateway(sample_template_payload, "项目管理>>项目立项"),
        FixtureRuntime(sample_runtime_elements),
    )

    result = menu_opening.open(
        MenuOpeningRequest(
            menu_path="项目管理>>项目立项",
            deadline=time.monotonic() + 1,
        )
    )

    assert result.menu_target.menu_name == "项目立项"
    assert result.manifest is not None
    assert result.manifest.page.fieldid == "root"
    assert result.binding is not None
    assert len(result.binding.bound_fields) == 2
    assert result.template_supported is True
    assert result.readiness == {
        "completion_signal": "open_menu_runtime_compatibility",
        "wait_duration_ms": 0,
        "fallback_used": True,
        "work_surfaces": [],
    }
    with pytest.raises(FrozenInstanceError):
        result.template_supported = False  # type: ignore[misc]


def test_menu_opening_fixture_allows_explicit_open_only_menu(
    sample_runtime_elements: list[dict],
) -> None:
    gateway = FixtureGateway({"code": 999, "message": "页面编码不能为空"}, "分析>>分析报表")
    gateway.menu_target.page_code = None
    gateway.menu_target.service_url = "#/native/report"
    gateway.menu_target.native_url = "tns:///native/report"
    runtime = FixtureRuntime(sample_runtime_elements)

    result = MenuOpening.for_fixture(gateway, runtime).open(
        MenuOpeningRequest(menu_path="分析>>分析报表", deadline=time.monotonic() + 1)
    )

    assert runtime.opened_menu is gateway.menu_target
    assert result.manifest is None
    assert result.binding is None
    assert result.template_supported is False
    assert result.readiness["completion_signal"] == "open_menu_open_only"


def test_menu_opening_fixture_preserves_menu_hosting(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    class IframeRuntime(FixtureRuntime):
        def inspect_menu_hosting(self, menu_target) -> dict[str, str]:
            return {
                "mode": "iframe",
                "frame_name": menu_target.service_code or "",
                "frame_url": "https://example.test/apps/project/index.html",
            }

    result = MenuOpening.for_fixture(
        FixtureGateway(sample_template_payload, "项目管理>>项目立项"),
        IframeRuntime(sample_runtime_elements),
    ).open(MenuOpeningRequest(menu_path="项目管理>>项目立项", deadline=time.monotonic() + 1))

    assert result.menu_hosting == {
        "mode": "iframe",
        "frame_name": "fixture_service",
        "frame_url": "https://example.test/apps/project/index.html",
    }


def test_menu_opening_browser_recognizes_iframe_hosting(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    gateway = _BrowserGateway(sample_template_payload, "项目管理>>项目立项")
    runtime = _BrowserRuntime(
        sample_runtime_elements,
        sample_template_payload,
        frames=[
            {"name": "", "url": "https://example.test", "is_main": True, "parent_is_main": False},
            {
                "name": "fixture_service",
                "url": "https://example.test/apps/project/index.html",
                "is_main": False,
                "parent_is_main": True,
            },
        ],
    )

    result = MenuOpening.for_browser(gateway, runtime).open(
        MenuOpeningRequest(menu_path="项目管理>>项目立项", deadline=time.monotonic() + 1)
    )

    assert result.menu_hosting == {
        "mode": "iframe",
        "frame_name": "fixture_service",
        "frame_url": "https://example.test/apps/project/index.html",
    }


@pytest.mark.parametrize(
    ("service_code", "service_url", "frames", "expected_mode"),
    [
        (
            "service-a",
            "/apps/service-a/index.html?locale=zh_CN",
            [{"name": "", "url": "https://example.test/apps/service-a/index.html?timestamp=2", "is_main": False, "parent_is_main": True}],
            "iframe",
        ),
        (
            "service-a",
            "#/BillRender?code=RULE&version=2&domainCode=AMS",
            [{"name": "legacy", "url": "https://example.test/#/BillRender?domainCode=AMS&code=RULE&version=2&refimestamp=1", "is_main": False, "parent_is_main": True}],
            "iframe",
        ),
        (
            "service-a",
            "/apps/BillRender?code=EXPECTED",
            [{"name": "legacy", "url": "https://example.test/apps/BillRender?code=OTHER", "is_main": False, "parent_is_main": True}],
            "direct",
        ),
        (
            "service-a",
            "",
            [
                {"name": "helper_iframe-demo", "url": "https://example.test/helper", "is_main": False, "parent_is_main": True},
                {"name": "service-a", "url": "https://example.test/apps/service-a", "is_main": False, "parent_is_main": False},
            ],
            "direct",
        ),
        (
            "service-a",
            "",
            [
                {"name": "service-a", "url": "https://example.test/apps/a", "is_main": False, "parent_is_main": True},
                {"name": "service-a", "url": "https://example.test/apps/b", "is_main": False, "parent_is_main": True},
            ],
            "unknown",
        ),
    ],
)
def test_menu_opening_browser_hosting_recognition_rules(
    service_code: str,
    service_url: str,
    frames: list[dict[str, Any]],
    expected_mode: str,
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    gateway = _BrowserGateway(sample_template_payload, "项目管理>>项目立项")
    gateway.menu_target.service_code = service_code
    gateway.menu_target.service_url = service_url
    runtime = _BrowserRuntime(
        sample_runtime_elements,
        sample_template_payload,
        frames=[
            {"name": "", "url": "https://example.test", "is_main": True, "parent_is_main": False},
            *frames,
        ],
    )

    result = MenuOpening.for_browser(gateway, runtime).open(
        MenuOpeningRequest(menu_path="项目管理>>项目立项", deadline=time.monotonic() + 1)
    )

    assert result.menu_hosting["mode"] == expected_mode


def test_menu_opening_browser_reloads_blank_service_route_once_for_menu_tab(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    gateway = _BrowserGateway(sample_template_payload, "项目管理>>项目立项")
    runtime = _BrowserRuntime(
        sample_runtime_elements,
        sample_template_payload,
        visible_results=[False, True],
    )

    result = MenuOpening.for_browser(gateway, runtime).open(
        MenuOpeningRequest(menu_path="项目管理>>项目立项", deadline=time.monotonic() + 1)
    )

    assert result.template_supported is True
    assert runtime.reload_count == 1


def test_menu_opening_browser_uses_page_responses_and_recovers_from_technical_template_error(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    class BrowserGateway:
        def __init__(self) -> None:
            self.menu_target = MenuTarget(
                menu_code="PM_INIT",
                menu_name="项目立项",
                path=["项目管理", "项目立项"],
                service_code="global00_-1_PM_INIT",
            )

        def resolve_menu(self, menu_path: str, timeout_seconds: float | None = None) -> MenuTarget:
            assert menu_path == "项目管理>>项目立项"
            assert timeout_seconds is not None
            return self.menu_target

        def fetch_template(self, menu_target: MenuTarget, timeout_seconds: float | None = None) -> dict:
            raise AssertionError("browser 菜单打开不得调用 gateway.fetch_template")

    class BrowserRuntime(FixtureRuntime):
        def __init__(self) -> None:
            super().__init__(sample_runtime_elements)
            self.config = SimpleNamespace(
                base_url="https://example.test",
                endpoints=SimpleNamespace(
                    service_detail="/service/detail",
                    templates="/matchingTemplate",
                    template_body="/getTemplateBody",
                )
            )
            self.response_events: list[dict[str, Any]] = []
            self.surface_payloads: list[list[dict[str, Any]]] = []

        def begin_notification_capture(self) -> None:
            return

        def wait_for_first_visible(self, selectors: list[str], timeout_ms: int) -> bool:
            return True

        def current_page_url(self) -> str:
            return "https://example.test/#/service/global00_-1_PM_INIT"

        def reload_page(self) -> None:
            return

        def page_frame_states(self) -> list[dict[str, Any]]:
            return [{"name": "", "url": "https://example.test", "is_main": True, "parent_is_main": False}]

        def begin_page_response_capture(self) -> int:
            self.response_events = []
            return 0

        def page_error_cursor(self) -> int:
            return 0

        def page_errors_since(self, cursor: int) -> tuple[int, list[dict[str, Any]]]:
            return cursor, []

        def open_menu(self, menu_target: MenuTarget) -> None:
            super().open_menu(menu_target)
            self.response_events = [
                {
                    "method": "GET",
                    "url": "https://example.test/service/detail",
                    "status": 200,
                    "payload": {
                        "data": {
                            "serviceCode": "global00_-1_PM_INIT",
                            "serviceName": "项目立项",
                            "nativeUrl": "tns:///bill/ydf/#/BillRender?code=PM_INIT",
                            "templateCode": "PM_INIT",
                        }
                    },
                },
                {
                    "method": "POST",
                    "url": "https://example.test/matchingTemplate",
                    "status": 200,
                    "payload": {"message": "页面编码暂未就绪"},
                },
                {
                    "method": "POST",
                    "url": "https://example.test/matchingTemplate",
                    "status": 200,
                    "payload": sample_template_payload,
                },
            ]
            self.surface_payloads = [
                [_surface("main", "main_table", busy=1, signature="loading")],
                [_surface("main", "main_table", terminal=True, signature="row:1")],
            ]

        def page_responses_since(self, cursor: int) -> tuple[int, list[dict[str, Any]]]:
            return len(self.response_events), self.response_events[cursor:]

        def pop_dynamic_template_payload(self) -> None:
            return None

        def evaluate_all_frames(self, script: str, payload: Any) -> list[dict[str, Any]]:
            surfaces = self.surface_payloads.pop(0) if len(self.surface_payloads) > 1 else self.surface_payloads[0]
            return [{"frame_name": "bill", "frame_url": "fixture://bill", "value": surfaces}]

        def wait_for_timeout(self, timeout_ms: int) -> None:
            return

    gateway = BrowserGateway()
    result = MenuOpening.for_browser(gateway, BrowserRuntime()).open(
        MenuOpeningRequest(menu_path="项目管理>>项目立项", deadline=time.monotonic() + 1)
    )

    assert result.manifest is not None
    assert result.manifest.page.fieldid == "root"
    assert result.menu_target.native_url == "tns:///bill/ydf/#/BillRender?code=PM_INIT"
    assert result.menu_target.template_code == "PM_INIT"
    assert result.template_error is not None
    assert result.template_error["message"] == "页面编码暂未就绪"


def test_menu_opening_returns_manifest_history_when_page_template_changes_during_readiness(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    clock = _Clock()
    next_template = deepcopy(sample_template_payload)
    next_template["data"]["uidata"][0]["divCode"] = "new_root"

    class DynamicTemplateRuntime(_BrowserRuntime):
        def evaluate_all_frames(self, script: str, payload: Any) -> list[dict[str, Any]]:
            result = super().evaluate_all_frames(script, payload)
            if self.surface_count == 1:
                self.response_events.append(
                    {
                        "method": "POST",
                        "url": "https://example.test/matchingTemplate",
                        "status": 200,
                        "payload": next_template,
                    }
                )
            return result

        def wait_for_timeout(self, timeout_ms: int) -> None:
            clock.advance(timeout_ms)

    gateway = _BrowserGateway(sample_template_payload, "项目管理>>项目立项")
    runtime = DynamicTemplateRuntime(sample_runtime_elements, sample_template_payload)

    result = MenuOpening.for_browser(gateway, runtime, now=clock.monotonic).open(
        MenuOpeningRequest(menu_path="项目管理>>项目立项", deadline=2)
    )

    assert result.manifest is not None
    assert result.manifest.page.fieldid == "new_root"
    assert [manifest.page.fieldid for manifest in result.manifest_history] == ["root", "new_root"]


def test_menu_opening_waits_for_dynamic_work_surfaces_and_transitions(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    clock = _Clock()
    runtime = _ReadinessRuntime(
        sample_runtime_elements,
        [
            [_surface("main", "main_table", busy=1, signature="table-loading")],
            [
                _surface("main", "main_table", busy=1, signature="table-loading"),
                _surface("category", "tree", busy=1, signature="tree-loading"),
            ],
            [
                _surface("main", "main_table", terminal=True, signature="row:1"),
                _surface("category", "tree", terminal=True, signature="node:1"),
            ],
        ],
        clock,
    )

    result = MenuOpening.for_fixture(
        FixtureGateway(sample_template_payload, "项目管理>>项目立项"),
        runtime,
        now=clock.monotonic,
    ).open(MenuOpeningRequest(menu_path="项目管理>>项目立项", deadline=2))

    assert runtime.capture_count == 3
    assert result.readiness["completion_signal"] == "open_menu_work_surfaces"
    assert {item["key"] for item in result.readiness["work_surfaces"]} == {"main", "category"}


def test_menu_opening_uses_500ms_stable_snapshot(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    clock = _Clock()
    runtime = _ReadinessRuntime(
        sample_runtime_elements,
        [[_surface("form", "content_card", terminal=True, signature="field:project_name")]],
        clock,
    )

    result = MenuOpening.for_fixture(
        FixtureGateway(sample_template_payload, "项目管理>>项目立项"),
        runtime,
        now=clock.monotonic,
    ).open(MenuOpeningRequest(menu_path="项目管理>>项目立项", deadline=2))

    assert runtime.capture_count >= 6
    assert result.readiness["completion_signal"] == "open_menu_stable_snapshot"
    assert result.readiness["wait_duration_ms"] >= 500


def test_menu_opening_discards_nested_duplicate_work_surface_root(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    clock = _Clock()
    runtime = _ReadinessRuntime(
        sample_runtime_elements,
        [[
            _surface("table#1", "main_table", terminal=True, signature="empty:暂无数据"),
            _surface("table#2", "main_table", signature="empty:", nested=True),
            _surface("table#3", "main_table", terminal=True, signature="row:1"),
        ]],
        clock,
    )

    result = MenuOpening.for_fixture(
        FixtureGateway(sample_template_payload, "项目管理>>项目立项"),
        runtime,
        now=clock.monotonic,
    ).open(MenuOpeningRequest(menu_path="项目管理>>项目立项", deadline=2))

    assert [item["key"] for item in result.readiness["work_surfaces"]] == ["table#1", "table#3"]


def test_menu_opening_maps_browser_template_business_error(
    sample_runtime_elements: list[dict],
) -> None:
    class BrowserGateway(FixtureGateway):
        def resolve_menu(self, menu_path: str, timeout_seconds: float | None = None) -> MenuTarget:
            return super().resolve_menu(menu_path)

        def fetch_template(self, menu_target: MenuTarget, timeout_seconds: float | None = None) -> dict:
            raise AssertionError("browser 菜单打开不得调用 gateway.fetch_template")

    class BusinessErrorRuntime(FixtureRuntime):
        def __init__(self) -> None:
            super().__init__(sample_runtime_elements)
            self.config = SimpleNamespace(
                base_url="https://example.test",
                endpoints=SimpleNamespace(
                    service_detail="/service/detail",
                    templates="/matchingTemplate",
                    template_body="/getTemplateBody",
                )
            )
            self.response_events: list[dict[str, Any]] = []
            self.page_closed = False

        def begin_notification_capture(self) -> None:
            return

        def wait_for_first_visible(self, selectors: list[str], timeout_ms: int) -> bool:
            return True

        def current_page_url(self) -> str:
            return "https://example.test/#/service/global00_-1_PM_INIT"

        def reload_page(self) -> None:
            return

        def page_frame_states(self) -> list[dict[str, Any]]:
            return [{"name": "", "url": "https://example.test", "is_main": True, "parent_is_main": False}]

        def begin_page_response_capture(self) -> int:
            self.response_events = []
            return 0

        def page_error_cursor(self) -> int:
            return 0

        def page_errors_since(self, cursor: int) -> tuple[int, list[dict[str, Any]]]:
            return cursor, []

        def open_menu(self, menu_target: MenuTarget) -> None:
            super().open_menu(menu_target)
            self.response_events = [{
                "method": "POST",
                "url": "https://example.test/matchingTemplate",
                "status": 200,
                "payload": {
                    "code": 999,
                    "message": "当前产品未授权‘支付管理’子系统",
                    "displayCode": "AUTH-001",
                    "traceId": "trace-001",
                },
            }]

        def page_responses_since(self, cursor: int) -> tuple[int, list[dict[str, Any]]]:
            return len(self.response_events), self.response_events[cursor:]

        def pop_dynamic_template_payload(self) -> None:
            return None

    runtime = BusinessErrorRuntime()
    opening = MenuOpening.for_browser(BrowserGateway({}, "项目管理>>项目立项"), runtime)

    with pytest.raises(MenuOpeningError) as captured:
        opening.open(MenuOpeningRequest(menu_path="项目管理>>项目立项", deadline=time.monotonic() + 1))

    assert runtime.opened_menu is not None
    assert runtime.page_closed is False
    assert captured.value.data["completion_signal"] == "open_menu_failure_evidence"
    assert captured.value.data["template_error"] == {
        "type": "RuntimeError",
        "message": "当前产品未授权‘支付管理’子系统",
        "code": 999,
        "display_code": "AUTH-001",
        "trace_id": "trace-001",
    }


def test_menu_opening_maps_work_surface_business_error(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    clock = _Clock()
    runtime = _ReadinessRuntime(
        sample_runtime_elements,
        [[_surface("main", "main_table", error="列表加载失败")]],
        clock,
        notifications=[{"type": "error", "message": "查询失败"}],
    )

    with pytest.raises(MenuOpeningError) as captured:
        MenuOpening.for_fixture(
            FixtureGateway(sample_template_payload, "项目管理>>项目立项"),
            runtime,
            now=clock.monotonic,
        ).open(MenuOpeningRequest(menu_path="项目管理>>项目立项", deadline=1))

    assert str(captured.value) == "open_menu 首次展示失败: 列表加载失败; 查询失败"
    assert captured.value.data["completion_signal"] == "open_menu_failure_evidence"
    assert captured.value.data["notifications"] == [{"type": "error", "message": "查询失败"}]


def test_menu_opening_timeout_uses_shared_deadline_and_preserves_page_evidence(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    clock = _Clock()
    runtime = _ReadinessRuntime(
        sample_runtime_elements,
        [[_surface("main", "main_table", busy=1, signature="loading")]],
        clock,
        page_errors=[{"message": "render crashed"}],
    )

    with pytest.raises(MenuOpeningError) as captured:
        MenuOpening.for_fixture(
            FixtureGateway(sample_template_payload, "项目管理>>项目立项"),
            runtime,
            now=clock.monotonic,
        ).open(MenuOpeningRequest(menu_path="项目管理>>项目立项", deadline=1))

    assert runtime.opened_menu is not None
    assert runtime.page_closed is False
    assert str(captured.value) == "open_menu 等待首次展示工作面稳定超时"
    assert 900 <= captured.value.data["wait_duration_ms"] <= 1000
    assert captured.value.data["page_errors"] == [{"message": "render crashed"}]


def test_menu_opening_returns_page_binding_hosting_and_phase_timing(
    sample_template_payload: dict,
    sample_runtime_elements: list[dict],
) -> None:
    clock = _Clock()

    class TimedGateway(FixtureGateway):
        def resolve_menu(self, menu_path: str) -> MenuTarget:
            clock.advance(10)
            return super().resolve_menu(menu_path)

        def fetch_template(self, menu_target: MenuTarget) -> dict:
            clock.advance(20)
            return super().fetch_template(menu_target)

    class TimedRuntime(FixtureRuntime):
        def open_menu(self, menu_target: MenuTarget) -> None:
            clock.advance(30)
            super().open_menu(menu_target)

        def ensure_menu_tab(self, menu_target: MenuTarget) -> None:
            clock.advance(40)
            super().ensure_menu_tab(menu_target)

        def prepare_binding(self, manifest) -> None:
            clock.advance(50)

        def inspect_menu_hosting(self, menu_target: MenuTarget) -> dict[str, str]:
            return {"mode": "direct"}

    result = MenuOpening.for_fixture(
        TimedGateway(sample_template_payload, "项目管理>>项目立项"),
        TimedRuntime(sample_runtime_elements),
        now=clock.monotonic,
    ).open(MenuOpeningRequest(menu_path="项目管理>>项目立项", deadline=2))

    assert result.page_state == {
        "url": "fixture://page",
        "title": "Fixture Page",
        "frames": [{"index": 0, "name": "", "url": "fixture://page"}],
        "frame_count": 1,
    }
    assert result.menu_hosting == {"mode": "direct"}
    assert result.binding is not None
    assert len(result.binding.bound_fields) == 2
    assert len(result.binding.bound_actions) == 2
    assert result.phases == {
        "resolve_menu_ms": 10,
        "fetch_template_ms": 20,
        "build_manifest_ms": 0,
        "browser_open_ms": 30,
        "menu_ready_ms": 40,
        "initial_work_surface_wait_ms": 0,
        "binding_ms": 50,
    }
    assert result.menu_business_stable_ms == 70


def test_menu_opening_fixture_maps_template_failure(
    sample_runtime_elements: list[dict],
) -> None:
    opening = MenuOpening.for_fixture(
        FixtureGateway({"code": 999, "message": "通用错误: 页面编码不能为空"}),
        FixtureRuntime(sample_runtime_elements),
    )

    with pytest.raises(MenuOpeningError) as captured:
        opening.open(MenuOpeningRequest(menu_path="项目管理>>项目立项", deadline=time.monotonic() + 1))

    assert str(captured.value) == "通用错误: 页面编码不能为空"
    assert captured.value.data == {
        "template_error": {
            "type": "ValueError",
            "message": "通用错误: 页面编码不能为空",
            "code": 999,
            "exception_message": "matchingTemplate 响应缺少 data.uidata[0]",
        },
        "template_supported": False,
    }


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


def test_open_menu_work_surfaces_attribute_page_spinner_to_overlapping_surface(_popup_reference_page) -> None:
    page = _popup_reference_page
    page.set_content(
        """
        <style>
          [fieldid="covered"] { position: absolute; left: 20px; top: 20px; width: 300px; height: 200px; }
          [fieldid="clear"] { position: absolute; left: 20px; top: 400px; width: 300px; height: 200px; }
          .wui-empty { width: 100px; height: 30px; }
          .wui-spin-backdrop { position: fixed; left: 0; top: 0; width: 400px; height: 300px; }
        </style>
        <section fieldid="covered"><div class="wui-empty">暂无数据</div></section>
        <section fieldid="clear"><div class="wui-empty">暂无数据</div></section>
        <div class="wui-spin-backdrop">加载中，请耐心等待......</div>
        """
    )

    surfaces = page.evaluate(
        _OPEN_MENU_WORK_SURFACES_SCRIPT,
        [
            {
                "key": "covered",
                "region_type": "main_table",
                "root_mode": "identity",
                "identities": ["covered"],
                "fieldids": [],
            },
            {
                "key": "clear",
                "region_type": "main_table",
                "root_mode": "identity",
                "identities": ["clear"],
                "fieldids": [],
            },
        ],
    )

    assert [(item["key"], item["busy"], item["transition_busy"], item["terminal"]) for item in surfaces] == [
        ("covered", 1, 0, False),
        ("clear", 0, 0, True),
    ]


def test_open_menu_work_surface_accepts_visible_empty_content_card(_popup_reference_page) -> None:
    page = _popup_reference_page
    page.set_content(
        """
        <style>
          [fieldid="EMPTY_CARD"] { width: 500px; height: 300px; }
        </style>
        <section fieldid="EMPTY_CARD"></section>
        """
    )

    surfaces = page.evaluate(
        _OPEN_MENU_WORK_SURFACES_SCRIPT,
        [
            {
                "key": "empty_card",
                "region_type": "content_card",
                "root_mode": "component",
                "identities": ["EMPTY_CARD"],
                "fieldids": [],
            }
        ],
    )

    assert len(surfaces) == 1
    assert surfaces[0]["busy"] == 0
    assert surfaces[0]["field_count"] == 0
    assert surfaces[0]["empty_state"] == ""
    assert surfaces[0]["empty_content"] is True
    assert surfaces[0]["terminal"] is True


def test_open_menu_work_surface_keeps_empty_content_card_waiting_for_local_loading(
    _popup_reference_page,
) -> None:
    page = _popup_reference_page
    page.set_content(
        """
        <style>
          [fieldid="EMPTY_CARD"] { position: relative; width: 500px; height: 300px; }
          .wui-spin-spinning { position: absolute; width: 500px; height: 300px; }
        </style>
        <section fieldid="EMPTY_CARD"><div class="wui-spin-spinning"></div></section>
        """
    )

    surfaces = page.evaluate(
        _OPEN_MENU_WORK_SURFACES_SCRIPT,
        [
            {
                "key": "empty_card",
                "region_type": "content_card",
                "root_mode": "component",
                "identities": ["EMPTY_CARD"],
                "fieldids": [],
            }
        ],
    )

    assert len(surfaces) == 1
    assert surfaces[0]["busy"] == 1
    assert surfaces[0]["terminal"] is False
    assert surfaces[0]["empty_content"] is False


def test_open_menu_work_surface_keeps_empty_content_card_waiting_for_overlapping_page_loading(
    _popup_reference_page,
) -> None:
    page = _popup_reference_page
    page.set_content(
        """
        <style>
          [fieldid="EMPTY_CARD"] { position: absolute; left: 20px; top: 20px; width: 500px; height: 300px; }
          .wui-spin-backdrop { position: fixed; left: 0; top: 0; width: 600px; height: 400px; }
        </style>
        <section fieldid="EMPTY_CARD"></section>
        <div class="wui-spin-backdrop"></div>
        """
    )

    surfaces = page.evaluate(
        _OPEN_MENU_WORK_SURFACES_SCRIPT,
        [
            {
                "key": "empty_card",
                "region_type": "content_card",
                "root_mode": "component",
                "identities": ["EMPTY_CARD"],
                "fieldids": [],
            }
        ],
    )

    assert len(surfaces) == 1
    assert surfaces[0]["busy"] == 1
    assert surfaces[0]["terminal"] is False
    assert surfaces[0]["empty_content"] is False


def test_open_menu_work_surface_keeps_empty_content_card_waiting_for_error_evidence(_popup_reference_page) -> None:
    page = _popup_reference_page
    page.set_content(
        """
        <style>
          [fieldid="EMPTY_CARD"] { width: 500px; height: 300px; }
          .wui-result-error { width: 300px; height: 80px; }
        </style>
        <section fieldid="EMPTY_CARD">
          <div class="wui-result-error">加载失败</div>
        </section>
        """
    )

    surfaces = page.evaluate(
        _OPEN_MENU_WORK_SURFACES_SCRIPT,
        [
            {
                "key": "empty_card",
                "region_type": "content_card",
                "root_mode": "component",
                "identities": ["EMPTY_CARD"],
                "fieldids": [],
            }
        ],
    )

    assert len(surfaces) == 1
    assert surfaces[0]["busy"] == 0
    assert surfaces[0]["error"] == "加载失败"
    assert surfaces[0]["terminal"] is False
    assert surfaces[0]["empty_content"] is False


def test_open_menu_work_surface_recalculates_empty_content_card_after_content_appears(_popup_reference_page) -> None:
    page = _popup_reference_page
    page.set_content(
        """
        <style>
          [fieldid="EMPTY_CARD"] { width: 500px; height: 300px; }
        </style>
        <section fieldid="EMPTY_CARD"></section>
        """
    )
    spec = [
        {
            "key": "empty_card",
            "region_type": "content_card",
            "root_mode": "component",
            "identities": ["EMPTY_CARD"],
            "fieldids": [],
        }
    ]

    before = page.evaluate(_OPEN_MENU_WORK_SURFACES_SCRIPT, spec)
    page.evaluate("document.querySelector('[fieldid=EMPTY_CARD]').textContent = '已加载内容'")
    after = page.evaluate(_OPEN_MENU_WORK_SURFACES_SCRIPT, spec)

    assert before[0]["empty_content"] is True
    assert before[0]["terminal"] is True
    assert after[0]["empty_content"] is False
    assert after[0]["terminal"] is True


def test_open_menu_work_surface_does_not_apply_empty_content_to_empty_non_card_surface(_popup_reference_page) -> None:
    page = _popup_reference_page
    page.set_content(
        """
        <style>
          [fieldid="EMPTY_DIALOG"] { width: 500px; height: 300px; }
        </style>
        <section fieldid="EMPTY_DIALOG"></section>
        """
    )

    surfaces = page.evaluate(
        _OPEN_MENU_WORK_SURFACES_SCRIPT,
        [
            {
                "key": "empty_dialog",
                "region_type": "dialog_page",
                "root_mode": "component",
                "identities": ["EMPTY_DIALOG"],
                "fieldids": [],
            }
        ],
    )

    assert len(surfaces) == 1
    assert surfaces[0]["empty_content"] is False
    assert surfaces[0]["terminal"] is False


def test_open_menu_work_surface_promotes_lcd_table_with_sibling_empty_state(_popup_reference_page) -> None:
    page = _popup_reference_page
    page.set_content(
        """
        <style>
          .lcd-table { position: relative; width: 500px; height: 300px; }
          [fieldid="DEMAND_TABLE_table"] { width: 500px; height: 240px; }
          .ydf-table-placeholder-nodata { width: 120px; height: 40px; }
        </style>
        <div class="lcd-table">
          <div fieldid="DEMAND_TABLE_table"></div>
          <div class="ydf-table-placeholder-nodata">暂无数据</div>
        </div>
        """
    )

    surfaces = page.evaluate(
        _OPEN_MENU_WORK_SURFACES_SCRIPT,
        [
            {
                "key": "DEMAND_TABLE",
                "region_type": "main_table",
                "root_mode": "identity",
                "identities": ["DEMAND_TABLE_table"],
                "fieldids": [],
            }
        ],
    )

    assert len(surfaces) == 1
    assert surfaces[0]["terminal"] is True
    assert surfaces[0]["busy"] == 0
    assert surfaces[0]["empty_state"] == "暂无数据"


def test_open_menu_work_surface_waits_while_lcd_table_has_loading_mask(_popup_reference_page) -> None:
    page = _popup_reference_page
    page.set_content(
        """
        <style>
          .lcd-table { position: relative; width: 500px; height: 300px; }
          [fieldid="DEMAND_TABLE_table"] { width: 500px; height: 240px; }
          .ydf-table-placeholder-nodata { width: 120px; height: 40px; }
          .wui-spin-spinning { position: absolute; left: 0; top: 0; width: 500px; height: 300px; }
        </style>
        <div class="lcd-table">
          <div fieldid="DEMAND_TABLE_table"></div>
          <div class="ydf-table-placeholder-nodata">暂无数据</div>
          <div class="wui-spin-spinning"></div>
        </div>
        """
    )

    surfaces = page.evaluate(
        _OPEN_MENU_WORK_SURFACES_SCRIPT,
        [
            {
                "key": "DEMAND_TABLE",
                "region_type": "main_table",
                "root_mode": "identity",
                "identities": ["DEMAND_TABLE_table"],
                "fieldids": [],
            }
        ],
    )

    assert len(surfaces) == 1
    assert surfaces[0]["busy"] == 1
    assert surfaces[0]["transition_busy"] == 1
    assert surfaces[0]["terminal"] is False


def test_open_menu_work_surface_does_not_use_empty_state_outside_lcd_table(_popup_reference_page) -> None:
    page = _popup_reference_page
    page.set_content(
        """
        <style>
          .lcd-table { width: 500px; height: 300px; }
          [fieldid="DEMAND_TABLE_table"] { width: 500px; height: 240px; }
          .outside-empty, .ydf-table-placeholder-nodata { width: 120px; height: 40px; }
        </style>
        <div class="lcd-table"><div fieldid="DEMAND_TABLE_table"></div></div>
        <div class="outside-empty">暂无数据</div>
        """
    )

    surfaces = page.evaluate(
        _OPEN_MENU_WORK_SURFACES_SCRIPT,
        [
            {
                "key": "DEMAND_TABLE",
                "region_type": "main_table",
                "root_mode": "identity",
                "identities": ["DEMAND_TABLE_table"],
                "fieldids": [],
            }
        ],
    )

    assert len(surfaces) == 1
    assert surfaces[0]["terminal"] is False
    assert surfaces[0]["empty_state"] == ""


def test_open_menu_work_surface_falls_back_to_physical_table_without_lcd_table(_popup_reference_page) -> None:
    page = _popup_reference_page
    page.set_content(
        """
        <style>
          [fieldid="PLAIN_TABLE_table"] { width: 500px; height: 300px; }
          .ydf-table-placeholder-nodata { width: 120px; height: 40px; }
        </style>
        <div fieldid="PLAIN_TABLE_table">
          <div class="ydf-table-placeholder-nodata">暂无数据</div>
        </div>
        """
    )

    surfaces = page.evaluate(
        _OPEN_MENU_WORK_SURFACES_SCRIPT,
        [
            {
                "key": "PLAIN_TABLE",
                "region_type": "main_table",
                "root_mode": "identity",
                "identities": ["PLAIN_TABLE_table"],
                "fieldids": [],
            }
        ],
    )

    assert len(surfaces) == 1
    assert surfaces[0]["terminal"] is True
    assert surfaces[0]["empty_state"] == "暂无数据"


def test_open_menu_work_surface_keeps_parallel_tables_in_shared_lcd_table_independent(_popup_reference_page) -> None:
    page = _popup_reference_page
    page.set_content(
        """
        <style>
          .lcd-table { position: relative; width: 500px; height: 500px; }
          [fieldid="FIRST_TABLE_table"], [fieldid="SECOND_TABLE_table"] {
            width: 500px; height: 180px;
          }
          .ydf-table-placeholder-nodata { width: 120px; height: 40px; }
        </style>
        <div class="lcd-table">
          <div fieldid="FIRST_TABLE_table">
            <table><tbody><tr><td>第一表数据</td></tr></tbody></table>
          </div>
          <div class="ydf-table-placeholder-nodata">暂无数据</div>
          <div fieldid="SECOND_TABLE_table"></div>
        </div>
        """
    )

    surfaces = page.evaluate(
        _OPEN_MENU_WORK_SURFACES_SCRIPT,
        [
            {
                "key": "FIRST_TABLE",
                "region_type": "main_table",
                "root_mode": "identity",
                "identities": ["FIRST_TABLE_table"],
                "fieldids": [],
            },
            {
                "key": "SECOND_TABLE",
                "region_type": "main_table",
                "root_mode": "identity",
                "identities": ["SECOND_TABLE_table"],
                "fieldids": [],
            },
        ],
    )

    assert [(item["key"], item["terminal"], item["empty_state"]) for item in surfaces] == [
        ("FIRST_TABLE", True, ""),
        ("SECOND_TABLE", False, ""),
    ]


def test_open_menu_work_surface_specs_use_table_wrapper_and_tree_root() -> None:
    manifest = PageManifest(
        page=PageMeta(fieldid="root", biz_obj_code="demo", app_code="demo", domain_key="demo"),
        regions=[
            Region(
                "table",
                "BAS_FUND_COUNTERPART_TABLE",
                "主表",
                "main_table",
                "table",
                "LCDTable",
                "root",
                True,
                40,
                runtime_fieldids=["BAS_FUND_COUNTERPART_TABLE_table"],
            ),
            Region(
                "tree",
                "BAS_FUND_COUNTERPART_TREE",
                "分类树",
                "tree",
                "tree",
                "LCDTree",
                "root",
                True,
                60,
                runtime_fieldids=[
                    "BAS_FUND_COUNTERPART_TREE",
                    "BAS_FUND_COUNTERPART_TREE_search_input",
                    "BAS_FUND_COUNTERPART_TREE_search_suffix",
                ],
            ),
        ],
    )

    specs = _open_menu_work_surface_specs(manifest)

    assert [(item["key"], item["identities"], item["root_mode"]) for item in specs] == [
        ("table", ["BAS_FUND_COUNTERPART_TABLE_table"], "identity"),
        ("tree", ["BAS_FUND_COUNTERPART_TREE"], "identity"),
    ]
