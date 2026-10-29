from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import parse_qsl, urljoin, urlparse

from .binder import bind_manifest
from .gateway import parse_service_detail
from .models import BindingResult, MenuTarget, PageManifest
from .template_parser import build_page_manifest


_OPEN_MENU_WORK_SURFACES_SCRIPT = r"""(specs) => {
  const normalize = (value) => String(value || '').replace(/\s+/g, ' ').trim();
  const visible = (node) => {
    if (!node || !(node instanceof Element)) return false;
    const style = window.getComputedStyle(node);
    const rect = node.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden'
      && rect.width > 0 && rect.height > 0;
  };
  const fieldSelector = (value) => {
    const escaped = CSS.escape(String(value || ''));
    return `[fieldid="${escaped}"], [data-fieldid="${escaped}"], [id="${escaped}"]`;
  };
  const tableSelector = 'table, .ant-table, .wui-table, .w-table, .u-table, [role="grid"], [role="table"]';
  const treeSelector = '[role="tree"], .ant-tree, .wui-tree, .w-tree, .u-tree';
  const busySelector = '[aria-busy="true"], .ant-spin-spinning, .wui-spin-spinning, .w-spin-spinning, .u-loading, [class*="loading"]';
  const emptySelector = '.ant-empty-description, .wui-empty, .w-empty, .u-empty, .ydf-table-placeholder-nodata, [class*="empty"]';
  const emptyPattern = /暂无数据|暂时没有数据|没有数据|无数据|点击上方查询条件搜索数据/;
  const errorPattern = /加载失败|请求失败|服务异常|系统异常|页面崩溃/;
  const unique = (items) => Array.from(new Set(items));
  const physicalRootsFor = (spec) => {
    const candidates = [];
    for (const identity of spec.identities || []) {
      for (const node of document.querySelectorAll(fieldSelector(identity))) {
        let root = node;
        if (spec.root_mode !== 'identity' && spec.region_type === 'main_table') {
          root = node.matches(tableSelector) ? node : (node.querySelector(tableSelector) || node.closest(tableSelector) || node);
        } else if (spec.root_mode !== 'identity' && spec.region_type === 'tree') {
          root = node.matches(treeSelector) ? node : (node.querySelector(treeSelector) || node.closest(treeSelector) || node);
        }
        if (visible(root)) candidates.push(root);
      }
    }
    return unique(candidates);
  };
  const rootsFor = (spec, allSpecs = []) => {
    let candidates = physicalRootsFor(spec);
    if (spec.region_type === 'main_table' && spec.root_mode === 'identity') {
      const mainSpecs = (allSpecs || []).filter((item) => item.region_type === 'main_table');
      const physicalRoots = unique(mainSpecs.flatMap((item) => physicalRootsFor(item)));
      candidates = candidates.map((root) => {
        const logicalRoot = root.closest('.lcd-table');
        if (!logicalRoot || !visible(logicalRoot) || !logicalRoot.contains(root)) return root;
        const siblingPhysicalRoots = physicalRoots.filter((item) => logicalRoot.contains(item));
        return siblingPhysicalRoots.length === 1 && siblingPhysicalRoots[0] === root ? logicalRoot : root;
      });
    }
    return unique(candidates);
  };
  const visibleMatches = (root, selector) => {
    const nodes = Array.from(root.querySelectorAll(selector));
    if (root.matches && root.matches(selector)) nodes.unshift(root);
    return unique(nodes).filter(visible);
  };
  const overlaps = (left, right) => {
    const leftRect = left.getBoundingClientRect();
    const rightRect = right.getBoundingClientRect();
    return Math.min(leftRect.right, rightRect.right) > Math.max(leftRect.left, rightRect.left)
      && Math.min(leftRect.bottom, rightRect.bottom) > Math.max(leftRect.top, rightRect.top);
  };
  const pageBusyNodes = visibleMatches(document.documentElement, '.wui-spin-backdrop');
  const explicitEmpty = (root) => visibleMatches(root, emptySelector)
    .map((node) => normalize(node.innerText || node.textContent))
    .find((text) => emptyPattern.test(text)) || '';
  const errorText = (root) => visibleMatches(
    root,
    '.ant-result-error, .wui-result-error, .w-result-error, [class*="load-error"], [class*="error-page"]'
  ).map((node) => normalize(node.innerText || node.textContent))
    .find((text) => errorPattern.test(text)) || '';
  const tableRows = (root) => visibleMatches(
    root,
    'tbody tr, [role="row"], .ant-table-row, .wui-table-row, .w-table-row, .u-table-row'
  ).filter((row) => !row.closest(
    'thead, .ant-table-header, .wui-table-header, .w-table-header, .u-table-header'
  )).map((row) => normalize(row.innerText || row.textContent))
    .filter((text) => text && !emptyPattern.test(text) && !/^(小计|合计|汇总|总计)(\s|$)/.test(text));
  const treeNodes = (root) => visibleMatches(
    root,
    '[role="treeitem"], .ant-tree-node-content-wrapper, .wui-tree-node-content-wrapper, .w-tree-node-content-wrapper, .u-tree-node-content'
  ).map((node) => normalize(node.innerText || node.textContent)).filter(Boolean);
  const fieldValues = (root, fieldids) => {
    const values = [];
    for (const fieldid of fieldids || []) {
      for (const node of root.querySelectorAll(fieldSelector(fieldid))) {
        if (!visible(node)) continue;
        const control = node.matches('input, textarea, select') ? node : node.querySelector('input, textarea, select');
        values.push(normalize(control && 'value' in control ? control.value : (node.innerText || node.textContent)));
      }
    }
    return values.filter(Boolean);
  };
  const results = [];
  for (const spec of specs || []) {
    const roots = rootsFor(spec, specs);
    roots.forEach((root, index) => {
      const nestedIdentityRoot = roots.some((other) => other !== root && other.contains(root));
      const localBusyNodes = visibleMatches(root, busySelector);
      const overlappingPageBusyNodes = pageBusyNodes.filter((node) => overlaps(root, node));
      const busy = unique([
        ...localBusyNodes,
        ...overlappingPageBusyNodes,
      ]).length;
      const transitionBusy = localBusyNodes.length;
      const empty = explicitEmpty(root);
      const error = errorText(root);
      const rows = spec.region_type === 'main_table' ? tableRows(root) : [];
      const nodes = spec.region_type === 'tree' ? treeNodes(root) : [];
      const fields = fieldValues(root, spec.fieldids || []);
      const interactive = visibleMatches(
        root,
        'input, textarea, select, button, [role="button"], [role="textbox"], [role="combobox"]'
      ).filter((node) => !node.disabled && node.getAttribute('aria-disabled') !== 'true').length;
      const text = normalize(root.innerText || root.textContent).slice(0, 1200);
      const emptyContent = spec.region_type === 'content_card'
        && busy === 0
        && !error
        && fields.length === 0
        && interactive === 0
        && !text
        && !empty;
      let terminal = false;
      let signature = '';
      let transitionSignature = '';
      if (spec.region_type === 'main_table') {
        terminal = busy === 0 && (rows.length > 0 || Boolean(empty));
        signature = `rows:${rows.join('|').slice(0, 800)};empty:${empty};busy:${busy}`;
        transitionSignature = `rows:${rows.join('|').slice(0, 800)};empty:${empty};busy:${transitionBusy}`;
      } else if (spec.region_type === 'tree') {
        terminal = busy === 0 && (nodes.length > 0 || Boolean(empty));
        signature = `nodes:${nodes.join('|').slice(0, 800)};empty:${empty};busy:${busy}`;
        transitionSignature = `nodes:${nodes.join('|').slice(0, 800)};empty:${empty};busy:${transitionBusy}`;
      } else {
        terminal = !error && (emptyContent || (busy === 0 && (fields.length > 0 || interactive > 0 || Boolean(text))));
        signature = `fields:${fields.join('|').slice(0, 800)};interactive:${interactive};text:${text};busy:${busy};empty_content:${emptyContent}`;
        transitionSignature = `fields:${fields.join('|').slice(0, 800)};interactive:${interactive};text:${text};busy:${transitionBusy};empty_content:${emptyContent}`;
      }
      results.push({
        key: roots.length === 1 ? spec.key : `${spec.key}#${index + 1}`,
        region_type: spec.region_type,
        busy,
        transition_busy: transitionBusy,
        terminal,
        signature,
        transition_signature: transitionSignature,
        error,
        row_count: rows.length,
        node_count: nodes.length,
        field_count: fields.length,
        empty_state: empty,
        empty_content: emptyContent,
        _nested_identity_root: nestedIdentityRoot,
      });
    });
  }
  return results;
}"""



def _open_menu_work_surface_specs(manifest: PageManifest) -> list[dict[str, Any]]:
    surface_types = {"main_table", "tree", "content_card", "dialog_page"}
    regions = [region for region in manifest.regions if region.region_type in surface_types]
    if not regions:
        regions = [region for region in manifest.regions if region.region_type == "page_root"]
    if not regions:
        return [
            {
                "key": manifest.page.fieldid or "page",
                "region_type": "page_root",
                "identities": [manifest.page.fieldid] if manifest.page.fieldid else [],
                "fieldids": [],
            }
        ]

    specs: list[dict[str, Any]] = []
    for region in regions:
        identities = list(dict.fromkeys([region.fieldid, *region.runtime_fieldids]))
        root_mode = "component"
        if region.region_type == "main_table":
            wrapper_identities = [item for item in region.runtime_fieldids if str(item).endswith("_table")]
            if wrapper_identities:
                identities = list(dict.fromkeys(wrapper_identities))
                root_mode = "identity"
        elif region.region_type == "tree" and region.fieldid:
            identities = [region.fieldid]
            root_mode = "identity"
        fieldids: list[str] = []
        for field in manifest.fields:
            if field.region_key != region.key:
                continue
            fieldids.extend([field.fieldid, *field.runtime_fieldids])
        specs.append(
            {
                "key": region.key,
                "region_type": region.region_type,
                "identities": [item for item in identities if item],
                "root_mode": root_mode,
                "fieldids": list(dict.fromkeys(item for item in fieldids if item)),
            }
        )
    return specs



@dataclass(frozen=True, slots=True)
class MenuOpeningRequest:
    menu_path: str
    deadline: float
    cancelled: Callable[[], bool] | None = None
    performance_enabled: bool = False


@dataclass(frozen=True, slots=True)
class MenuOpeningResult:
    menu_target: MenuTarget
    manifest: PageManifest | None
    binding: BindingResult | None
    page_state: dict[str, Any] | None
    template_supported: bool
    menu_hosting: dict[str, Any]
    readiness: dict[str, Any]
    phases: dict[str, int]
    menu_business_stable_ms: int
    template_error: dict[str, Any] | None = None
    runtime_element_count: int = 0
    manifest_history: tuple[PageManifest, ...] = ()


class MenuOpeningError(RuntimeError):
    report_error_type = "OpenMenuCompletionError"

    def __init__(self, message: str, data: dict[str, Any]) -> None:
        super().__init__(message)
        self.data = data


class _MenuOpeningAdapter(Protocol):
    template_before_open: bool
    supports_work_surface_capture: bool

    def resolve_menu(self, menu_path: str, remaining_seconds: float) -> MenuTarget: ...

    def initial_template(self, menu_target: MenuTarget, remaining_seconds: float) -> dict[str, Any]: ...

    def begin_opening(self) -> None: ...

    def open_menu(self, menu_target: MenuTarget) -> None: ...

    def ensure_menu_tab(self, menu_target: MenuTarget) -> None: ...

    def capture_page_state(self) -> dict[str, Any] | None: ...

    def inspect_menu_hosting(self, menu_target: MenuTarget) -> dict[str, Any]: ...

    def prepare_binding(self, manifest: PageManifest) -> None: ...

    def capture_runtime_elements(self, manifest: PageManifest) -> list[dict[str, Any]]: ...

    def capture_work_surfaces(self, manifest: PageManifest) -> list[dict[str, Any]] | None: ...

    def wait(self, timeout_ms: int) -> None: ...

    def collect_notifications(self) -> list[dict[str, str]]: ...

    def collect_page_errors(self) -> list[dict[str, Any]]: ...


class _FixtureMenuOpeningAdapter:
    template_before_open = True

    def __init__(self, gateway: Any, runtime: Any) -> None:
        self.gateway = gateway
        self.runtime = runtime
        self.supports_work_surface_capture = runtime.menu_opening_work_surfaces

    def resolve_menu(self, menu_path: str, remaining_seconds: float) -> MenuTarget:
        return self.gateway.resolve_menu(menu_path)

    def initial_template(self, menu_target: MenuTarget, remaining_seconds: float) -> dict[str, Any]:
        return self.gateway.fetch_template(menu_target)

    def begin_opening(self) -> None:
        return

    def open_menu(self, menu_target: MenuTarget) -> None:
        self.runtime.open_menu(menu_target)

    def ensure_menu_tab(self, menu_target: MenuTarget) -> None:
        self.runtime.ensure_menu_tab(menu_target)

    def capture_page_state(self) -> dict[str, Any] | None:
        return self.runtime.capture_page_state()

    def inspect_menu_hosting(self, menu_target: MenuTarget) -> dict[str, Any]:
        return dict(self.runtime.inspect_menu_hosting(menu_target))

    def prepare_binding(self, manifest: PageManifest) -> None:
        self.runtime.prepare_binding(manifest)

    def capture_runtime_elements(self, manifest: PageManifest) -> list[dict[str, Any]]:
        return list(self.runtime.capture_runtime_elements(manifest))

    def capture_work_surfaces(self, manifest: PageManifest) -> list[dict[str, Any]] | None:
        surfaces = self.runtime.capture_open_menu_work_surfaces(manifest)
        return None if surfaces is None else list(surfaces)

    def wait(self, timeout_ms: int) -> None:
        self.runtime.wait_for_timeout(timeout_ms)

    def collect_notifications(self) -> list[dict[str, str]]:
        return list(self.runtime.collect_notifications())

    def collect_page_errors(self) -> list[dict[str, Any]]:
        return list(self.runtime.collect_open_menu_page_errors())


class _BrowserMenuOpeningAdapter:
    template_before_open = False
    supports_work_surface_capture = True

    def __init__(self, gateway: Any, runtime: Any) -> None:
        self.gateway = gateway
        self.runtime = runtime
        self._response_cursor = 0
        self._page_error_cursor = 0
        self._service_details: list[dict[str, Any]] = []
        self._templates: list[dict[str, Any]] = []
        self._template_errors: list[dict[str, Any]] = []

    def resolve_menu(self, menu_path: str, remaining_seconds: float) -> MenuTarget:
        return self.gateway.resolve_menu(menu_path, timeout_seconds=remaining_seconds)

    def initial_template(self, menu_target: MenuTarget, remaining_seconds: float) -> dict[str, Any]:
        raise AssertionError("browser 菜单打开必须消费页面实际模板响应")

    def begin_opening(self) -> None:
        self.runtime.begin_notification_capture()
        self._response_cursor = self.runtime.begin_page_response_capture()
        self._page_error_cursor = self.runtime.page_error_cursor()
        self._service_details = []
        self._templates = []
        self._template_errors = []
        self.runtime.pop_dynamic_template_payload()

    def open_menu(self, menu_target: MenuTarget) -> None:
        self.runtime.open_menu(menu_target)

    def ensure_menu_tab(self, menu_target: MenuTarget) -> None:
        menu_name = menu_target.menu_name.strip()
        if not menu_name:
            raise RuntimeError("菜单页签校验失败: 菜单名称为空")
        selectors = [f'text="{menu_name}"', f'[title="{menu_name}"]']
        for attempt in range(2):
            if self.runtime.wait_for_first_visible(selectors, timeout_ms=8000):
                return
            if attempt == 0 and "/#/service/" in self.runtime.current_page_url():
                self.runtime.reload_page()
                continue
            break
        raise RuntimeError(f"菜单页签校验失败: {menu_name}")

    def capture_page_state(self) -> dict[str, Any] | None:
        return self.runtime.capture_page_state()

    def inspect_menu_hosting(self, menu_target: MenuTarget) -> dict[str, Any]:
        service_code = str(menu_target.service_code or "").strip()
        service_url = str(menu_target.service_url or "").strip()
        base_url = str(self.runtime.config.base_url or "")
        if not service_code and _normalized_menu_frame_url(base_url, service_url) is None:
            return {"mode": "unknown", "reason": "菜单缺少 service_code 和可比较的 service_url"}
        matches = []
        for frame in self.runtime.page_frame_states():
            if frame.get("is_main") or not frame.get("parent_is_main"):
                continue
            frame_name = str(frame.get("name") or "").strip()
            if frame_name.startswith("helper_iframe-"):
                continue
            frame_url = str(frame.get("url") or "").strip()
            if frame_name == service_code or _menu_frame_url_matches(base_url, service_url, frame_url):
                matches.append({"frame_name": frame_name, "frame_url": frame_url})
        if not matches:
            return {"mode": "direct"}
        if len(matches) > 1:
            return {"mode": "unknown", "reason": f"找到多个菜单业务 frame: {len(matches)}"}
        return {"mode": "iframe", **matches[0]}

    def prepare_binding(self, manifest: PageManifest) -> None:
        self.runtime.prepare_binding(manifest)

    def capture_runtime_elements(self, manifest: PageManifest) -> list[dict[str, Any]]:
        return list(self.runtime.capture_runtime_elements(manifest))

    def capture_work_surfaces(self, manifest: PageManifest) -> list[dict[str, Any]]:
        surfaces: list[dict[str, Any]] = []
        for frame in self.runtime.evaluate_all_frames(
            _OPEN_MENU_WORK_SURFACES_SCRIPT,
            _open_menu_work_surface_specs(manifest),
        ):
            for item in frame.get("value") or []:
                if not isinstance(item, dict):
                    continue
                surfaces.append(
                    {
                        **item,
                        "frame_name": str(frame.get("frame_name") or ""),
                        "frame_url": str(frame.get("frame_url") or ""),
                    }
                )
        return surfaces

    def pop_service_detail(self) -> dict[str, Any] | None:
        self._drain_response_events()
        return self._service_details.pop(0) if self._service_details else None

    def pop_template_error(self) -> dict[str, Any] | None:
        self._drain_response_events()
        return self._template_errors.pop(0) if self._template_errors else None

    def pop_template(self) -> dict[str, Any] | None:
        self._drain_response_events()
        if not self._templates:
            return None
        self.runtime.pop_dynamic_template_payload()
        return self._templates.pop(0)

    def wait(self, timeout_ms: int) -> None:
        self.runtime.wait_for_timeout(timeout_ms)

    def collect_notifications(self) -> list[dict[str, str]]:
        try:
            return list(self.runtime.collect_notifications(timeout_ms=0))
        except Exception:
            return []

    def collect_page_errors(self) -> list[dict[str, Any]]:
        self._page_error_cursor, errors = self.runtime.page_errors_since(self._page_error_cursor)
        return errors

    def _drain_response_events(self) -> None:
        self._response_cursor, events = self.runtime.page_responses_since(self._response_cursor)
        endpoints = self.runtime.config.endpoints
        template_body_endpoint = getattr(
            endpoints,
            "template_body",
            "/yondif-ams-be/ytemplate/template/getTemplateBody",
        )
        for event in events:
            method = str(event.get("method") or "").upper()
            url = str(event.get("url") or "")
            status = int(event.get("status") or 0)
            if status >= 400:
                continue
            if method == "GET" and endpoints.service_detail in url:
                payload = _page_response_payload(event)
                if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
                    self._service_details.append(payload)
                continue
            if method != "POST":
                continue
            matched_endpoint = next(
                (endpoint for endpoint in (endpoints.templates, template_body_endpoint) if endpoint and endpoint in url),
                None,
            )
            if matched_endpoint is None:
                continue
            payload = _page_response_payload(event)
            normalized = _normalize_menu_template_payload(
                payload,
                source="template_body" if matched_endpoint == template_body_endpoint else "matching_template",
            )
            if normalized is not None:
                self._templates.append(normalized)
            elif _is_template_business_error_payload(payload):
                self._template_errors.append(payload)
            elif isinstance(payload, dict):
                self._templates.append(payload)


class MenuOpening:
    def __init__(
        self,
        adapter: _MenuOpeningAdapter,
        *,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._adapter = adapter
        self._now = now

    @classmethod
    def for_fixture(
        cls,
        gateway: Any,
        runtime: Any,
        *,
        now: Callable[[], float] = time.monotonic,
    ) -> MenuOpening:
        return cls(_FixtureMenuOpeningAdapter(gateway, runtime), now=now)

    @classmethod
    def for_browser(
        cls,
        gateway: Any,
        runtime: Any,
        *,
        now: Callable[[], float] = time.monotonic,
    ) -> MenuOpening:
        return cls(_BrowserMenuOpeningAdapter(gateway, runtime), now=now)

    def open(self, request: MenuOpeningRequest) -> MenuOpeningResult:
        phases: dict[str, int] = {}

        phase_started = self._now()
        menu_target = self._adapter.resolve_menu(request.menu_path, self._remaining_seconds(request))
        phases["resolve_menu_ms"] = self._elapsed_ms(phase_started)
        self._raise_if_stopped(request, "菜单解析")

        template_payload: dict[str, Any] | None = None
        template_error: dict[str, Any] | None = None
        manifest: PageManifest | None = None
        if self._adapter.template_before_open:
            try:
                phase_started = self._now()
                template_payload = self._adapter.initial_template(menu_target, self._remaining_seconds(request))
                phases["fetch_template_ms"] = self._elapsed_ms(phase_started)
                self._raise_if_stopped(request, "模板获取")

                phase_started = self._now()
                manifest = build_page_manifest(template_payload)
                phases["build_manifest_ms"] = self._elapsed_ms(phase_started)
                self._raise_if_stopped(request, "模板解析")
            except MenuOpeningError:
                raise
            except Exception as exc:
                template_error = _template_error_payload(exc, template_payload)
                if not _is_explicit_open_only_menu(menu_target):
                    raise MenuOpeningError(
                        template_error["message"],
                        {"template_error": template_error, "template_supported": False},
                    ) from exc

        self._adapter.begin_opening()
        business_started = self._now()
        phase_started = self._now()
        self._adapter.open_menu(menu_target)
        phases["browser_open_ms"] = self._elapsed_ms(phase_started)
        self._raise_if_stopped(request, "菜单触发")

        phase_started = self._now()
        self._adapter.ensure_menu_tab(menu_target)
        page_state = self._capture_page_state()
        phases["menu_ready_ms"] = self._elapsed_ms(phase_started)

        if isinstance(self._adapter, _BrowserMenuOpeningAdapter):
            manifest, template_error, wait_ms, build_ms = self._wait_for_initial_browser_manifest(
                self._adapter,
                menu_target,
                request,
            )
            phases["initial_template_wait_ms"] = wait_ms
            if manifest is not None:
                phases["build_manifest_ms"] = build_ms

        manifest_history: tuple[PageManifest, ...] = ()
        if manifest is None:
            readiness = {
                "completion_signal": "open_menu_open_only",
                "wait_duration_ms": 0,
                "fallback_used": False,
                "work_surfaces": [],
            }
        else:
            readiness, manifest, manifest_history = self._wait_for_work_surfaces(
                self._adapter,
                manifest,
                request,
            )
        phases["initial_work_surface_wait_ms"] = int(readiness["wait_duration_ms"])
        menu_business_stable_ms = self._elapsed_ms(business_started)
        menu_hosting = self._inspect_menu_hosting(menu_target)

        binding: BindingResult | None = None
        runtime_elements: list[dict[str, Any]] = []
        if manifest is not None:
            phase_started = self._now()
            self._adapter.prepare_binding(manifest)
            runtime_elements = self._adapter.capture_runtime_elements(manifest)
            page_state = self._capture_page_state()
            binding = bind_manifest(manifest, runtime_elements)
            phases["binding_ms"] = self._elapsed_ms(phase_started)
            self._raise_if_stopped(request, "运行时绑定")

        return MenuOpeningResult(
            menu_target=menu_target,
            manifest=manifest,
            binding=binding,
            page_state=page_state,
            template_supported=manifest is not None,
            menu_hosting=menu_hosting,
            readiness=readiness,
            phases=phases,
            menu_business_stable_ms=menu_business_stable_ms,
            template_error=template_error,
            runtime_element_count=len(runtime_elements),
            manifest_history=manifest_history,
        )

    def _wait_for_work_surfaces(
        self,
        adapter: _MenuOpeningAdapter,
        manifest: PageManifest,
        request: MenuOpeningRequest,
    ) -> tuple[dict[str, Any], PageManifest, tuple[PageManifest, ...]]:
        if not adapter.supports_work_surface_capture:
            return (
                {
                    "completion_signal": "open_menu_runtime_compatibility",
                    "wait_duration_ms": 0,
                    "fallback_used": True,
                    "work_surfaces": [],
                },
                manifest,
                (),
            )

        started = self._now()
        history: dict[str, dict[str, Any]] = {}
        previous_keys: set[str] | None = None
        empty_content_keys: set[str] = set()
        stable_fingerprint: tuple[Any, ...] | None = None
        stable_started: float | None = None
        observed_page_errors: list[dict[str, Any]] = []
        manifest_history: list[PageManifest] = []
        last_surfaces: list[dict[str, Any]] = []
        while True:
            self._raise_if_cancelled(request)
            if isinstance(adapter, _BrowserMenuOpeningAdapter):
                error_payload = adapter.pop_template_error()
                if error_payload:
                    message = str(error_payload.get("message") or error_payload.get("msg") or "页面模板返回业务错误")
                    error = _template_error_payload(RuntimeError(message), error_payload)
                    raise MenuOpeningError(
                        message,
                        {
                            "template_error": error,
                            "template_supported": False,
                            "completion_signal": "open_menu_failure_evidence",
                        },
                    )
                payload = adapter.pop_template()
                if payload:
                    try:
                        next_manifest = build_page_manifest(payload)
                    except Exception as exc:
                        error = _template_error_payload(exc, payload)
                        raise MenuOpeningError(
                            error["message"],
                            {"template_error": error, "completion_signal": "open_menu_failure_evidence"},
                        ) from exc
                    for remembered in (manifest, next_manifest):
                        page_fieldid = remembered.page.fieldid
                        manifest_history = [
                            item for item in manifest_history if item.page.fieldid != page_fieldid
                        ]
                        manifest_history.append(remembered)
                    manifest = next_manifest
                    history = {}
                    previous_keys = None
                    empty_content_keys = set()
                    stable_fingerprint = None
                    stable_started = None

            if self._now() >= request.deadline:
                wait_ms = min(
                    self._elapsed_ms(started),
                    max(0, int(round((request.deadline - started) * 1000))),
                )
                raise MenuOpeningError(
                    "open_menu 等待首次展示工作面稳定超时",
                    {
                        "completion_signal": "open_menu_timeout",
                        "wait_duration_ms": wait_ms,
                        "fallback_used": False,
                        "work_surfaces": last_surfaces,
                        "page_errors": observed_page_errors,
                        "open_menu_readiness": {"work_surfaces": last_surfaces},
                    },
                )

            surfaces = adapter.capture_work_surfaces(manifest)
            last_surfaces = []
            for item in surfaces or []:
                if not isinstance(item, dict):
                    continue
                surface = dict(item)
                if surface.pop("_nested_identity_root", False):
                    continue
                last_surfaces.append(surface)

            surface_errors = [str(item.get("error") or "").strip() for item in last_surfaces if item.get("error")]
            notifications = adapter.collect_notifications()
            known_page_errors = {str(item.get("message") or item).strip() for item in observed_page_errors}
            for item in adapter.collect_page_errors():
                message = str(item.get("message") or item).strip()
                if message in {"", "Object", "[object Object]"} or message in known_page_errors:
                    continue
                observed_page_errors.append(item)
                known_page_errors.add(message)
            if surface_errors or _has_error_notification(notifications):
                messages = [*surface_errors, *_error_notification_messages(notifications)]
                raise MenuOpeningError(
                    f"open_menu 首次展示失败: {'; '.join(messages)}",
                    {
                        "completion_signal": "open_menu_failure_evidence",
                        "wait_duration_ms": self._elapsed_ms(started),
                        "fallback_used": False,
                        "work_surfaces": last_surfaces,
                        "notifications": notifications,
                        "page_errors": observed_page_errors,
                    },
                )

            keys = {str(item.get("key") or "") for item in last_surfaces}
            if previous_keys is not None and keys != previous_keys:
                stable_fingerprint = None
                stable_started = None
                empty_content_keys.intersection_update(keys)
                history = {key: state for key, state in history.items() if key in keys}
            previous_keys = keys

            for surface in last_surfaces:
                key = str(surface.get("key") or "")
                if bool(surface.get("empty_content")):
                    empty_content_keys.add(key)
                signature = str(surface.get("signature") or "")
                busy = int(surface.get("busy") or 0)
                transition_signature = str(surface.get("transition_signature") or signature)
                transition_busy = int(surface.get("transition_busy", busy) or 0)
                state = history.get(key)
                if state is None:
                    history[key] = {
                        "transition_signature": transition_signature,
                        "seen_busy": transition_busy > 0,
                        "transition": False,
                    }
                    continue
                if transition_busy > 0:
                    state["seen_busy"] = True
                if transition_signature != state["transition_signature"] or (
                    state["seen_busy"] and transition_busy == 0
                ):
                    state["transition"] = True
                state["transition_signature"] = transition_signature

            all_terminal = bool(last_surfaces) and all(bool(item.get("terminal")) for item in last_surfaces)
            if all_terminal and not empty_content_keys and all(
                history.get(key, {}).get("transition") for key in keys
            ):
                return (
                    {
                        "completion_signal": "open_menu_work_surfaces",
                        "wait_duration_ms": self._elapsed_ms(started),
                        "fallback_used": False,
                        "work_surfaces": last_surfaces,
                        **({"page_errors": observed_page_errors} if observed_page_errors else {}),
                    },
                    manifest,
                    tuple(manifest_history),
                )

            now = self._now()
            fingerprint = tuple(
                sorted(
                    (
                        str(item.get("key") or ""),
                        str(item.get("region_type") or ""),
                        int(item.get("busy") or 0),
                        bool(item.get("terminal")),
                        str(item.get("signature") or ""),
                    )
                    for item in last_surfaces
                )
            )
            if all_terminal:
                if fingerprint != stable_fingerprint:
                    stable_fingerprint = fingerprint
                    stable_started = now
                elif stable_started is not None and now - stable_started >= 0.5:
                    return (
                        {
                            "completion_signal": "open_menu_stable_snapshot",
                            "wait_duration_ms": self._elapsed_ms(started),
                            "fallback_used": True,
                            "work_surfaces": last_surfaces,
                            **({"page_errors": observed_page_errors} if observed_page_errors else {}),
                        },
                        manifest,
                        tuple(manifest_history),
                    )
            else:
                stable_fingerprint = None
                stable_started = None

            adapter.wait(min(100, max(1, int(round((request.deadline - self._now()) * 1000)))))

    def _wait_for_initial_browser_manifest(
        self,
        adapter: _BrowserMenuOpeningAdapter,
        menu_target: MenuTarget,
        request: MenuOpeningRequest,
    ) -> tuple[PageManifest | None, dict[str, Any] | None, int, int]:
        started = self._now()
        build_manifest_ms = 0
        template_error: dict[str, Any] | None = None
        while True:
            self._raise_if_cancelled(request)
            service_payload = adapter.pop_service_detail()
            if service_payload:
                detail = parse_service_detail(service_payload, menu_target.service_code or "")
                if detail["service_code"] == (menu_target.service_code or ""):
                    menu_target.service_url = detail["service_url"]
                    menu_target.native_url = detail["native_url"]
                    menu_target.template_code = detail["code"]
                    menu_target.transtype_code = detail["transtypeCode"]
                    menu_target.business_step = detail["businessStep"]
                    if detail["service_name"]:
                        menu_target.raw = {**menu_target.raw, "serviceName": detail["service_name"]}

            error_payload = adapter.pop_template_error()
            if error_payload:
                message = str(error_payload.get("message") or error_payload.get("msg") or "页面模板返回业务错误")
                error = _template_error_payload(RuntimeError(message), error_payload)
                raise MenuOpeningError(
                    message,
                    {
                        "template_error": error,
                        "template_supported": False,
                        "completion_signal": "open_menu_failure_evidence",
                    },
                )

            payload = adapter.pop_template()
            if payload:
                build_started = self._now()
                try:
                    manifest = build_page_manifest(payload)
                except Exception as exc:
                    template_error = _template_error_payload(exc, payload)
                    build_manifest_ms += self._elapsed_ms(build_started)
                else:
                    build_manifest_ms += self._elapsed_ms(build_started)
                    elapsed_ms = self._elapsed_ms(started)
                    return manifest, template_error, max(elapsed_ms - build_manifest_ms, 0), build_manifest_ms

            if _is_explicit_open_only_menu(menu_target):
                return None, template_error, self._elapsed_ms(started), build_manifest_ms
            if self._now() >= request.deadline:
                data: dict[str, Any] = {
                    "completion_signal": "open_menu_timeout",
                    "wait_duration_ms": self._elapsed_ms(started),
                    "fallback_used": False,
                    "template_supported": False,
                    "open_menu_readiness": {"phase": "页面初始模板响应", "work_surfaces": []},
                }
                if template_error:
                    data["template_error"] = template_error
                raise MenuOpeningError("open_menu 页面初始模板响应不可用", data)

            adapter.wait(min(100, max(1, int(round((request.deadline - self._now()) * 1000)))))

    def _capture_page_state(self) -> dict[str, Any] | None:
        try:
            return self._adapter.capture_page_state()
        except Exception:
            return None

    def _inspect_menu_hosting(self, menu_target: MenuTarget) -> dict[str, Any]:
        try:
            result = dict(self._adapter.inspect_menu_hosting(menu_target) or {})
        except Exception as exc:
            return {"mode": "unknown", "reason": f"菜单承载方式检查失败: {exc}"}
        if result.get("mode") not in {"iframe", "direct", "unknown"}:
            return {"mode": "unknown", "reason": "菜单承载方式检查未返回有效 mode"}
        return result

    def _raise_if_cancelled(self, request: MenuOpeningRequest) -> None:
        if request.cancelled is not None and request.cancelled():
            raise TimeoutError("AI 观察运行已请求停止")

    def _remaining_seconds(self, request: MenuOpeningRequest) -> float:
        return max(request.deadline - self._now(), 0.001)

    def _raise_if_stopped(self, request: MenuOpeningRequest, phase: str) -> None:
        self._raise_if_cancelled(request)
        if self._now() < request.deadline:
            return
        raise MenuOpeningError(
            f"open_menu 超时: {phase}",
            {
                "completion_signal": "open_menu_timeout",
                "wait_duration_ms": 0,
                "fallback_used": False,
                "open_menu_readiness": {"phase": phase, "work_surfaces": []},
            },
        )

    def _elapsed_ms(self, started: float) -> int:
        return max(0, int(round((self._now() - started) * 1000)))


def _is_explicit_open_only_menu(menu_target: MenuTarget) -> bool:
    urls = [menu_target.service_url or "", menu_target.native_url or ""]
    return bool(any(urls)) and not (menu_target.template_code or "").strip() and not any(
        "billrender" in value.lower() for value in urls
    )


_VOLATILE_MENU_FRAME_URL_PARAMS = {"_", "locale", "refimestamp", "t", "timestamp"}


def _normalized_menu_frame_url(
    base_url: str,
    value: str | None,
) -> tuple[str, str, str, tuple[tuple[str, str], ...]] | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    parsed = urlparse(urljoin(f"{base_url.rstrip('/')}/", raw))
    fragment_path, _, fragment_query = parsed.fragment.partition("?")
    path = parsed.path.rstrip("/") or "/"
    fragment_path = fragment_path.rstrip("/")
    if path == "/" and not fragment_path:
        return None
    params = [
        (key, item)
        for key, item in [
            *parse_qsl(parsed.query, keep_blank_values=True),
            *parse_qsl(fragment_query, keep_blank_values=True),
        ]
        if key.lower() not in _VOLATILE_MENU_FRAME_URL_PARAMS
    ]
    return (str(parsed.hostname or "").lower(), path, fragment_path, tuple(sorted(params)))


def _menu_frame_url_matches(base_url: str, expected: str | None, actual: str | None) -> bool:
    expected_identity = _normalized_menu_frame_url(base_url, expected)
    actual_identity = _normalized_menu_frame_url(base_url, actual)
    if expected_identity is None or actual_identity is None:
        return False
    return expected_identity[:3] == actual_identity[:3] and set(expected_identity[3]).issubset(actual_identity[3])


def _page_response_payload(event: dict[str, Any]) -> Any:
    if "payload" in event:
        return event.get("payload")
    response = event.get("response")
    try:
        return response.json()
    except Exception:
        return None


def _normalize_menu_template_payload(payload: Any, *, source: str) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    uidata = data.get("uidata") if isinstance(data, dict) else None
    if isinstance(uidata, list) and uidata and isinstance(uidata[0], dict):
        normalized = dict(payload)
    else:
        direct_uidata = payload.get("uidata")
        ui_data = payload.get("uiData")
        if isinstance(ui_data, dict):
            direct_uidata = ui_data.get("uidata")
        if isinstance(direct_uidata, str):
            try:
                direct_uidata = json.loads(direct_uidata)
            except (TypeError, ValueError):
                direct_uidata = None
        if not isinstance(direct_uidata, list) or not direct_uidata or not isinstance(direct_uidata[0], dict):
            return None
        normalized = dict(payload)
        normalized["data"] = {
            **(data if isinstance(data, dict) else {}),
            "uidata": direct_uidata,
        }
        if isinstance(ui_data, dict):
            normalized["data"].update({key: value for key, value in ui_data.items() if key != "uidata"})
        for key in ("pageId", "bizObjCode", "appCode", "domainKey", "actionEL"):
            if key in payload and key not in normalized["data"]:
                normalized["data"][key] = payload[key]
    if source == "template_body":
        normalized["_ydf_dynamic_template_source"] = source
    return normalized


def _is_template_business_error_payload(payload: Any) -> bool:
    if not isinstance(payload, dict) or not str(payload.get("message") or payload.get("msg") or "").strip():
        return False
    code = payload.get("code")
    return code is not None and str(code).strip().lower() not in {"0", "0000", "000000", "200", "success"}


def _has_error_notification(notifications: list[dict[str, str]]) -> bool:
    return any(
        item.get("type") == "error"
        or "未通过" in str(item.get("message") or "")
        or "失败" in str(item.get("message") or "")
        for item in notifications
    )


def _error_notification_messages(notifications: list[dict[str, str]]) -> list[str]:
    return [
        message
        for item in notifications
        if (message := str(item.get("message") or "").strip())
        and (item.get("type") == "error" or "未通过" in message or "失败" in message)
    ]


def _template_error_payload(exc: Exception, template_payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = template_payload if isinstance(template_payload, dict) else {}
    message = str(payload.get("message") or payload.get("msg") or str(exc))
    data: dict[str, Any] = {"type": exc.__class__.__name__, "message": message}
    if "code" in payload:
        data["code"] = payload.get("code")
    if payload.get("displayCode"):
        data["display_code"] = payload.get("displayCode")
    if payload.get("traceId"):
        data["trace_id"] = payload.get("traceId")
    if str(exc) and str(exc) != message:
        data["exception_message"] = str(exc)
    return data
