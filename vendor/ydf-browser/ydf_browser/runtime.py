from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any
from urllib.parse import quote, unquote, urljoin, urlparse

import requests

from .action_completion import (
    ActionCompletionObservation,
    ActionCompletionRequest,
    ActionNotification,
)
from .adapters import default_render_adapter_registry, guess_action_fieldid, guess_row_action_fieldid
from .browser_profile import cookie_visible_to_url
from .config import EnvironmentConfig
from .models import BoundElement, ElementCandidate, MenuTarget, PageManifest, Region, RuntimeElement
from .observation import redact_url, sanitize_dom_semantic_summary, sanitize_evidence_payload, sensitive_field_rule
from .platform_rendering_contract import build_contract_path
from .popup_reference import (
    PopupReference,
    PopupReferenceRequest,
    ReferenceOwnerIdentity,
)
from .request_forwarding import RequestForwardRule, match_request_forwarding, rewrite_forwarded_url
from .table_scope import ResolvedTableScope, TableRuntimeEvidence, table_scoped
from .template_parser import build_page_manifest


def _diag_dir() -> Path:
    """诊断产物（截图/JSON）落盘目录。

    POSIX 沿用 /tmp（保持既有行为与文档一致）；Windows 没有 /tmp，
    Path("/tmp") 会落到当前盘符根目录且通常不可写，导致诊断静默丢失。
    """
    if os.name == "nt":
        from tempfile import gettempdir

        return Path(gettempdir())
    return Path("/tmp")

_TAB_RETRY_INTERVAL_S = 0.5
_TAB_RETRY_TIMEOUT_S = 5.0

RENDER_ADAPTERS = default_render_adapter_registry()
GEOMETRY_FALLBACK_VIEWPORT = {"width": 1440, "height": 900}

_DOM_SEMANTIC_SUMMARY_SCRIPT = r"""() => {
const visible = (node) => {
  const style = window.getComputedStyle(node);
  const rect = node.getBoundingClientRect();
  return style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
};
return Array.from(document.querySelectorAll(
  'input, textarea, select, button, label, h1, h2, h3, h4, h5, h6, td, th, [role], ' +
  '.ydf-dropdownbtn-content .wui-dropdown-menu-item, .wui-select-dropdown .wui-select-item-option, ' +
  '.form-overlay-popover .wui-popover-inner-content, .wui-modal-title, ' +
  '.wui-tree-title, .wui-select-tree-title'
)).filter(visible).slice(0, 2001).map((node) => {
  const text = String(node.innerText || node.textContent || '').replace(/\s+/g, ' ').trim();
  const formItem = node.closest('.wui-form-item');
  const labels = [...new Set([
    ...(node.labels || []),
    ...(formItem ? Array.from(formItem.querySelectorAll('label')).filter(
      label => label.closest('.wui-form-item') === formItem
    ) : [])
  ])].filter(visible);
  const control = node.matches('input, textarea, select, [role="combobox"]');
  const requiredSources = [];
  if (node.hasAttribute('required')) requiredSources.push('html_required');
  if (node.getAttribute('aria-required') === 'true') requiredSources.push('aria_required_true');
  if (labels.some(label => label.classList.contains('wui-form-item-required')))
    requiredSources.push('wui_required_label');
  if (node.getAttribute('aria-required') === 'false') requiredSources.push('aria_required_false');
  const required = requiredSources.some(source => source !== 'aria_required_false') ? true
    : requiredSources.includes('aria_required_false') ? false : null;
  const fieldLabel = labels.map(label => String(label.innerText || '').trim()).filter(Boolean).join(' ');
  const constraintNames = ['type', 'pattern', 'minlength', 'maxlength', 'min', 'max', 'step'];
  return {
    visible: true,
    tag: String(node.tagName || '').toLowerCase(),
    type: node.getAttribute('type') || '',
    role: node.getAttribute('role') || '',
    label: node.getAttribute('aria-label') || node.getAttribute('title') || '',
    ...(control ? {
      field_label: fieldLabel.slice(0, 1000),
      required, required_sources: requiredSources,
      constraint_attributes: Object.fromEntries(
        constraintNames
          .filter(name => node.hasAttribute(name))
          .map(name => [name, node.getAttribute(name).slice(0, 1000)])
      ),
      constraints_truncated: fieldLabel.length > 1000 ||
        ['placeholder', ...constraintNames].some(name => (node.getAttribute(name) || '').length > 1000),
      placeholder: (node.getAttribute('placeholder') || '').slice(0, 1000)
    } : {}),
    name: node.getAttribute('name') || '',
    id: node.id || '',
    fieldid: node.getAttribute('fieldid') || '',
    owner_fieldid: node.closest('.ydf-dropdownbtn-content, .wui-form-item, [role="tree-node"][fieldid], [role="tree"][fieldid]')?.getAttribute('fieldid') || '',
    disabled: Boolean(node.disabled || node.closest('[aria-disabled="true"], .wui-tree-treenode-disabled, .wui-select-tree-treenode-disabled') || node.classList.contains('wui-select-item-option-disabled')),
    selected: Boolean(node.closest('[aria-selected="true"], .wui-tree-node-selected, .wui-select-tree-node-selected')) || node.classList.contains('wui-select-item-option-selected'),
    invalid: node.getAttribute('aria-invalid') === 'true' || Boolean(node.closest('.wui-form-item-has-error')),
    data_field: node.getAttribute('data-field') || '',
    autocomplete: node.getAttribute('autocomplete') || '',
    text: text.slice(0, 1000),
    text_truncated: text.length > 1000,
    value: 'value' in node ? String(node.value || '').slice(0, 1000) : ''
  };
});
}"""

def _resolved_table_scope_values(
    scope: ResolvedTableScope | None,
    table: str | None,
    table_fieldid: str | None,
    table_columns: list[str] | None,
) -> tuple[str | None, str | None, list[str] | None]:
    if scope is None:
        return table, table_fieldid, table_columns
    scope = scope.current
    return scope.label, scope.runtime_fieldid, list(scope.columns)

_MULTI_SELECT_SURFACE_SCRIPT = r"""(node, payload) => {
    const normalize = (value) => String(value || '').replace(/\s+/g, ' ').trim();
    const visible = (el) => {
      if (!el) return false;
      const style = window.getComputedStyle(el);
      const rect = el.getBoundingClientRect();
      return style && style.visibility !== 'hidden' && style.display !== 'none'
        && rect.width > 0 && rect.height > 0;
    };
    const action = payload.action;
    const token = payload.token;
    const surfaceSelector = [
      '.w-select-dropdown', '.wui-select-dropdown', '.ant-select-dropdown',
      '.u-select-dropdown', '[role="listbox"]'
    ].join(',');
    const allSurfaces = Array.from(node.ownerDocument.querySelectorAll(surfaceSelector)).filter(visible)
      .filter((surface) => !surface.parentElement?.closest(surfaceSelector));
    if (action === 'prepare') {
      node.setAttribute('data-ydf-multi-select-owner', token);
      for (const surface of allSurfaces) surface.setAttribute('data-ydf-multi-select-preexisting', token);
      const active = node === node.ownerDocument.activeElement || node.contains(node.ownerDocument.activeElement);
      if (payload.allowExistingSingle && active && allSurfaces.length === 1) {
        allSurfaces[0].setAttribute('data-ydf-multi-select-owner', token);
      }
      return { ok: true, count: allSurfaces.length };
    }
    const owners = [node, ...node.querySelectorAll('[aria-controls], [aria-owns]')];
    const controlledIds = owners.flatMap((owner) => [
      owner.getAttribute('aria-controls'), owner.getAttribute('aria-owns')
    ]).filter(Boolean).flatMap((value) => value.split(/\s+/)).filter(Boolean);
    let surfaces = allSurfaces.filter((surface) => surface.getAttribute('data-ydf-multi-select-owner') === token);
    if (!surfaces.length) surfaces = [...new Set(
      controlledIds.map((id) => node.ownerDocument.getElementById(id)).filter(visible)
    )];
    if (!surfaces.length && action === 'attach') {
      surfaces = allSurfaces.filter((surface) => surface.getAttribute('data-ydf-multi-select-preexisting') !== token);
    }
    if (surfaces.length !== 1) return action === 'visible' ? false : {
      ok: false,
      count: surfaces.length,
      items: surfaces.map((surface) => ({
        id: surface.id || '', role: surface.getAttribute('role') || '',
        className: String(surface.className || '').slice(0, 160),
        text: normalize(surface.innerText || surface.textContent).slice(0, 160)
      }))
    };
    const surface = surfaces[0];
    surface.setAttribute('data-ydf-multi-select-owner', token);
    if (action === 'attach') return { ok: true, count: 1 };
    if (action === 'visible') return true;
    const candidateSelector = [
      '[role="option"]', '[role="treeitem"]',
      '.w-select-dropdown-menu-item', '.wui-select-dropdown-menu-item',
      '.ant-select-item-option', '.u-select-dropdown-menu-item',
      '.wui-select-tree-title', '.w-select-tree-title', '.wui-tree-title', '.w-tree-title',
      '.wui-select-tree-node-content-wrapper', '.w-select-tree-node-content-wrapper',
      '.wui-tree-node-content-wrapper', '.w-tree-node-content-wrapper',
      '[class*="tree"][class*="title"]', '[class*="Tree"][class*="Title"]',
      '[class*="tree"][class*="content"]', '[class*="Tree"][class*="Content"]',
      '[class*="select"][class*="item"]', '[class*="Select"][class*="Item"]',
      'li'
    ].join(',');
    const candidateNodes = Array.from(surface.querySelectorAll(candidateSelector)).filter(visible);
    const leafCandidateNodes = candidateNodes.filter((item) => !candidateNodes.some(
      (other) => other !== item && item.contains(other)
    ));
    if (action === 'candidates') {
      return leafCandidateNodes
        .map((item) => normalize(item.getAttribute('title') || item.innerText || item.textContent))
        .filter(Boolean);
    }
    if (action === 'click-candidate') {
      const wanted = normalize(payload.value);
      const matches = leafCandidateNodes
        .filter((item) => normalize(item.getAttribute('title') || item.innerText || item.textContent) === wanted);
      if (matches.length !== 1) return { ok: false, count: matches.length };
      matches[0].click();
      return { ok: true, count: 1 };
    }
    const rawOptions = Array.from(surface.querySelectorAll([
      '[role="option"][aria-selected="true"]',
      '.w-select-dropdown-menu-item-selected',
      '.wui-select-dropdown-menu-item-selected',
      '.ant-select-item-option-selected',
      '.u-select-dropdown-menu-item-selected',
      'input[type="checkbox"]:checked'
    ].join(',')));
    const options = [...new Set(rawOptions.map((raw) => raw.matches('input[type="checkbox"]')
      ? raw.closest('[role="option"], li, [class*="item"], [class*="Item"]') || raw
      : raw))];
    if (action === 'clear') {
      const selectAll = options.filter((option) => /^(全选|select all)(?:\s|$)/i.test(normalize(
        option.getAttribute('title') || option.innerText || option.textContent
      )));
      const targets = selectAll.length ? [selectAll[0]] : options;
      for (const option of targets) option.click();
      return { ok: true, count: targets.length };
    }
    return options.map((option) => normalize(
      option.getAttribute('title') || option.innerText || option.textContent
    )).filter((text) => text && !/^(全选|select all)$/i.test(text));
}"""


class MultiSelectAssignmentError(RuntimeError):
    def __init__(self, message: str, data: dict[str, Any]) -> None:
        super().__init__(message)
        self.data = data


class PlaywrightRuntime:
    def __init__(
        self,
        config: EnvironmentConfig,
        session: requests.Session,
        headless: bool = True,
        request_forward_rules: list[RequestForwardRule] | None = None,
        profile_dir: str | Path | None = None,
        window_size: tuple[int, int] | None = None,
        observation_session: Any | None = None,
    ) -> None:
        self.config = config
        self.session = session
        self.headless = headless
        self.request_forward_rules = list(request_forward_rules or [])
        self.profile_dir = Path(profile_dir).expanduser() if profile_dir is not None else None
        self.window_size = window_size
        self.observation_session = observation_session
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._cookies_applied = False
        self.downloaded_files: list[str] = []
        self.diagnostic_files: list[str] = []
        self._dynamic_template_payload: dict[str, Any] | None = None
        self._page_response_events: list[dict[str, Any]] = []
        self.last_table_tree_search: dict[str, Any] | None = None
        self.last_tree_search: dict[str, Any] | None = None
        self.last_table_selection_root: dict[str, Any] | None = None
        self.last_table_selection_debug: dict[str, Any] | None = None
        self.table_selection_debug_files: list[str] = []
        self._performance_enabled = False
        self._network_events: list[dict[str, Any]] = []
        self._network_event_by_request_id: dict[int, int] = {}
        self._network_request_started_at: dict[int, float] = {}
        self._network_collect_cursor = 0
        self._performance_step_context: dict[str, Any] | None = None
        self._request_forward_events: list[dict[str, Any]] = []
        self._request_forward_facts: dict[int, dict[str, Any]] = {}
        self._console_events: list[dict[str, Any]] = []
        self._page_errors: list[dict[str, Any]] = []
        self._last_table_selection_context = None
        self._active_multi_select_surface_token = ""
        self._direct_import_network_events: dict[int, dict[str, Any]] | None = None
        self._direct_import_filenames: list[str] = []
        self._direct_import_network_seeded = False
        self._direct_import_last_activity = 0.0
        self._action_completion_state: dict[str, Any] | None = None
        self._action_completion_active = False
        self._action_completion_action = ""
        self._action_surface_observers: list[Any] = []
        self._action_completion_seen_busy = False
        self._action_completion_context: dict[str, Any] = {}
        self._action_completion_existing_notifications: set[str] = set()
        self._query_completion_frame = None
        self._query_completion_requests: dict[int, tuple[Any, bool | None]] = {}
        self._ai_failure_screenshot_attempted = False
        self._ai_failure_dom_attempted = False
        self._manual_browser_app_name: str | None = None
        self._manual_browser_seen_windows = False
        self._popup_reference: PopupReference | None = None

    def _popup_reference_module(self) -> PopupReference:
        popup_reference = getattr(self, "_popup_reference", None)
        if popup_reference is None:
            diagnostic_files = getattr(self, "diagnostic_files", None)
            if diagnostic_files is None:
                diagnostic_files = []
                self.diagnostic_files = diagnostic_files
            popup_reference = PopupReference(
                page=lambda: getattr(self, "_page", None),
                select_choice=lambda *args, **kwargs: self._select_query_choice(*args, **kwargs),
                resolve_visible_locator=lambda selector: self._resolve_visible_locator(selector),
                resolve_fill_locator=lambda selector: self._resolve_fill_locator(selector),
                diagnostic_files=diagnostic_files,
                observation_session=getattr(self, "observation_session", None),
                notifications=self._drain_buffered_notifications,
                begin_notifications=lambda: self._install_notification_observers(reset=True, ignore_existing=True),
                network_events=lambda: list(getattr(self, "_network_events", [])),
                console_events=lambda: list(getattr(self, "_console_events", [])),
                page_errors=lambda: list(getattr(self, "_page_errors", [])),
            )
            self._popup_reference = popup_reference
        return popup_reference

    def start(self) -> None:
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        context_options = {
            "locale": "zh-CN",
            "accept_downloads": True,
        }
        if self.headless:
            if self.window_size is not None:
                width, height = self.window_size
                context_options["viewport"] = {"width": width, "height": height}
            else:
                context_options["viewport"] = dict(GEOMETRY_FALLBACK_VIEWPORT)
        elif not self.headless:
            context_options["no_viewport"] = True
        if self.request_forward_rules:
            context_options["service_workers"] = "block"
        if self.profile_dir is not None:
            self.profile_dir.mkdir(parents=True, exist_ok=True)
            launch_options = dict(context_options)
            if self.window_size is not None and not self.headless:
                width, height = self.window_size
                launch_options["args"] = [f"--window-size={width},{height}"]
            self._context = self._playwright.chromium.launch_persistent_context(
                str(self.profile_dir),
                headless=self.headless,
                **launch_options,
            )
        else:
            self._browser = self._launch_browser()
            self._context = self._browser.new_context(**context_options)
        self._install_request_forwarding()
        if not self.headless:
            self._manual_browser_app_name = _browser_app_name(self._context)
        existing_pages = list(self._context.pages) if self.profile_dir is not None else []
        self._page = self._attach_page_handlers(existing_pages[0]) if existing_pages else self._new_page()
        self._cookies_applied = False

    def enable_performance_collection(self) -> None:
        self._performance_enabled = True
        self._network_events = []
        self._network_event_by_request_id = {}
        self._network_request_started_at = {}
        self._network_collect_cursor = 0
        self._performance_step_context = None

    def collect_network_summary(self, reset: bool = False) -> dict[str, Any]:
        events = self._network_events[self._network_collect_cursor :]
        summary = _summarize_network_events(events)
        summary["network_available"] = True
        if reset:
            self._network_collect_cursor = len(self._network_events)
        return summary

    def collect_network_events(self) -> list[dict[str, Any]]:
        return [_network_event_payload(item) for item in self._network_events]

    def capture_page_memory(self) -> dict[str, Any]:
        unavailable = {
            "available": False,
            "used_js_heap_size": 0,
            "unavailable_reason": "page_not_available",
        }
        page = self._page
        if page is None:
            return unavailable
        try:
            if page.is_closed():
                unavailable["unavailable_reason"] = "page_closed"
                return unavailable
            value = page.evaluate(
                "() => performance.memory && Number.isFinite(performance.memory.usedJSHeapSize) "
                "? performance.memory.usedJSHeapSize : null"
            )
        except Exception:
            unavailable["unavailable_reason"] = "capture_failed"
            return unavailable
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            unavailable["unavailable_reason"] = "performance_memory_not_supported"
            return unavailable
        return {
            "available": True,
            "used_js_heap_size": value,
            "unavailable_reason": "",
        }

    def begin_performance_step(self, context: dict[str, Any]) -> None:
        self._performance_step_context = dict(context)

    def end_performance_step(self) -> None:
        self._performance_step_context = None

    def start_bpr(
        self,
        *,
        index: int | None = None,
        name: str = "",
        description: str = "",
        control_step: int | None = None,
    ) -> dict[str, Any]:
        page = self._require_page()
        host = _runtime_business_host(self.config.base_url, page.url)
        parsed = urlparse(host)
        cookie_url = f"{parsed.scheme}://{parsed.netloc}/"
        start_ts = int(time.time() * 1000)
        bpr_id = f"ydf{start_ts:x}{uuid.uuid4().hex[:8]}"
        context = self._bpr_user_context()
        cookies = [
            {
                "name": "mdd_monitor_uid",
                "value": bpr_id,
                "url": cookie_url,
                "httpOnly": False,
                "secure": parsed.scheme == "https",
                "sameSite": "Lax",
            },
            {
                "name": "ymc_flag",
                "value": quote(f"bprId={bpr_id};bprStartTs={start_ts}", safe=""),
                "url": cookie_url,
                "httpOnly": False,
                "secure": parsed.scheme == "https",
                "sameSite": "Lax",
            },
            {
                "name": "mdd_monitor_record",
                "value": "true",
                "url": cookie_url,
                "httpOnly": False,
                "secure": parsed.scheme == "https",
                "sameSite": "Lax",
            },
            {
                "name": "ymc_recording",
                "value": "true",
                "url": cookie_url,
                "httpOnly": False,
                "secure": parsed.scheme == "https",
                "sameSite": "Lax",
            },
        ]
        page.context.add_cookies(cookies)
        self._install_bpr_event_collector(page, bpr_id)
        warnings: list[str] = []
        monitor_url = (
            f"{host}/iuap-ymc-agent/monitor/record"
            f"?uid={quote(bpr_id, safe='')}"
            f"&userId={quote(context['user_id'], safe='')}"
            f"&userName={quote(context['user_name'], safe='')}"
            f"&isDiwork=true"
        )
        try:
            response = page.evaluate(
                """async ({ url }) => {
                    try {
                      const res = await fetch(url, { method: 'GET', credentials: 'include' });
                      return { status: res.status, text: await res.text() };
                    } catch (error) {
                      return { status: 0, text: String(error && error.message || error) };
                    }
                  }""",
                {"url": monitor_url},
            )
            if not isinstance(response, dict) or int(response.get("status") or 0) >= 400 or int(response.get("status") or 0) <= 0:
                warnings.append(f"monitor/record 调用未成功: {response}")
        except Exception as exc:
            warnings.append(f"monitor/record 调用异常: {exc}")
        return {
            "index": index,
            "name": name,
            "description": description,
            "bpr_id": bpr_id,
            "start_ts": start_ts,
            "start_time": start_ts,
            "host": host,
            "user_id": context["user_id"],
            "user_name": context["user_name"],
            "tenant_id": context["tenant_id"],
            "sdk_version": "15.13.502",
            "sdk_id": "ydf-browser",
            "start_control_step": control_step,
            "warnings": warnings,
        }

    def stop_bpr(self, session: dict[str, Any]) -> dict[str, Any]:
        page = self._require_page()
        host = str(session.get("host") or _runtime_business_host(self.config.base_url, page.url)).rstrip("/")
        end_ts = int(time.time() * 1000)
        start_ts = int(session.get("start_ts") or session.get("start_time") or end_ts)
        bpr_id = str(session.get("bpr_id") or "")
        if not bpr_id:
            raise RuntimeError("BPR session 缺少 bpr_id")
        user_id = str(session.get("user_id") or self.config.username or "ydf-browser")
        user_name = str(session.get("user_name") or self.config.username or user_id)
        tenant_id = str(session.get("tenant_id") or self.config.tenantid or "")
        sdk_version = str(session.get("sdk_version") or "15.13.502")
        sdk_id = str(session.get("sdk_id") or "ydf-browser")
        tgap = int(session.get("tgap") or 0)
        content = self._collect_bpr_uba_events(page, bpr_id, start_ts, end_ts)
        uba_data = [
            {
                "header": {
                    "v": sdk_version,
                    "sdkid": sdk_id,
                    "jt": "web",
                    "userid": user_id,
                    "username": user_name,
                    "ytid": tenant_id,
                    "host": urlparse(host).hostname or host,
                    "topHost": urlparse(host).hostname or host,
                    "url": f"{host}/",
                    "topUrl": f"{host}/",
                    "tgap": tgap,
                    "ert": end_ts,
                },
                "content": content,
            }
        ]
        bpr_url = (
            f"{host}/iuap-ymc-agent/bprcall"
            f"?userId={quote(user_id, safe='')}"
            f"&bprId={quote(bpr_id, safe='')}"
            f"&userName={quote(user_name, safe='')}"
            f"&startTime={start_ts}"
            f"&endTime={end_ts}"
            f"&ubainfo={quote(f'{sdk_version},{sdk_id},{_bpr_event_count(uba_data)}', safe='')}"
            f"&tgap={tgap}"
        )
        response = page.evaluate(
            """async ({ url, body }) => {
                const res = await fetch(url, {
                  method: 'POST',
                  credentials: 'include',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify(body)
                });
                return { status: res.status, text: await res.text() };
              }""",
            {"url": bpr_url, "body": {"ubaData": uba_data}},
        )
        if not isinstance(response, dict):
            raise RuntimeError(f"BPR stop 响应格式异常: {response!r}")
        status = int(response.get("status") or 0)
        text = str(response.get("text") or "")
        if status < 200 or status >= 300:
            raise RuntimeError(f"BPR stop failed: HTTP {status}, {text}")
        report_url = _extract_bpr_report_url(text)
        if not report_url:
            raise RuntimeError(f"BPR stop 响应未包含报告 URL: {text}")
        return {
            "bpr_id": bpr_id,
            "end_ts": end_ts,
            "end_time": end_ts,
            "duration_ms": max(0, end_ts - start_ts),
            "report_url": report_url,
            "uba_event_count": _bpr_event_count(uba_data),
            "stop_response": _safe_json_text(text),
        }

    def download_bpr_report(
        self,
        report_url: str,
        bpr_id: str,
        target: str | Path,
        timeout_ms: int = 60000,
    ) -> Path:
        report_url = str(report_url or "").strip()
        bpr_id = str(bpr_id or "").strip()
        if not report_url or not bpr_id:
            raise ValueError("BPR 报告 URL 和 session BPR ID 不能为空")

        deadline = time.monotonic() + timeout_ms / 1000

        def remaining_ms() -> int:
            remaining = int((deadline - time.monotonic()) * 1000)
            if remaining <= 0:
                raise TimeoutError("BPR 报告下载超过 60 秒总期限")
            return remaining

        page = self._require_page()
        self._apply_api_session_cookies()
        page.goto(report_url, wait_until="domcontentloaded", timeout=remaining_ms())
        try:
            page.wait_for_function(
                "bprId => window.pageData?.bprBaseInfo?.bprId === bprId",
                arg=bpr_id,
                timeout=remaining_ms(),
            )
        except Exception as exc:
            raise TimeoutError("页面 BPR ID 未在总期限内与 session 匹配") from exc
        button = page.get_by_role("button", name="下载", exact=True)
        button.wait_for(state="visible", timeout=remaining_ms())
        with page.expect_download(timeout=remaining_ms()) as download_info:
            button.click(timeout=remaining_ms())
        target_path = Path(target).expanduser()
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".ydf-browser-bpr-", dir=target_path.parent) as private_dir:
            private_path = Path(private_dir) / target_path.name
            download_info.value.save_as(str(private_path))
            private_path.chmod(0o600)
            private_path.replace(target_path)
        return target_path

    def _bpr_user_context(self) -> dict[str, str]:
        page = self._require_page()
        context: dict[str, str] = {}
        try:
            raw = page.evaluate(
                """() => {
                    const keys = ['userId', 'userid', 'user_id', 'userName', 'username', 'tenantId', 'tenantid', 'ytid'];
                    const data = {};
                    const readStore = (store) => {
                      if (!store) return;
                      for (const key of keys) {
                        const value = store.getItem(key);
                        if (value && data[key] == null) data[key] = value;
                      }
                      for (let i = 0; i < store.length; i += 1) {
                        const key = store.key(i);
                        const value = key ? store.getItem(key) : '';
                        if (!value || value.length > 8000) continue;
                        try {
                          const parsed = JSON.parse(value);
                          if (parsed && typeof parsed === 'object') {
                            for (const probe of keys) {
                              if (parsed[probe] && data[probe] == null) data[probe] = String(parsed[probe]);
                            }
                            if (parsed.data && typeof parsed.data === 'object') {
                              for (const probe of keys) {
                                if (parsed.data[probe] && data[probe] == null) data[probe] = String(parsed.data[probe]);
                              }
                            }
                          }
                        } catch (_) {}
                      }
                    };
                    readStore(window.localStorage);
                    readStore(window.sessionStorage);
                    const globals = [window.userInfo, window.currentUser, window.__USER_INFO__, window.__INITIAL_STATE__];
                    for (const item of globals) {
                      if (!item || typeof item !== 'object') continue;
                      for (const probe of keys) {
                        if (item[probe] && data[probe] == null) data[probe] = String(item[probe]);
                      }
                      if (item.data && typeof item.data === 'object') {
                        for (const probe of keys) {
                          if (item.data[probe] && data[probe] == null) data[probe] = String(item.data[probe]);
                        }
                      }
                    }
                    return data;
                  }"""
            )
            if isinstance(raw, dict):
                context = {str(key): str(value) for key, value in raw.items() if value is not None and str(value).strip()}
        except Exception:
            context = {}
        user_id = _first_non_empty(context, "userId", "userid", "user_id") or self.config.username or "ydf-browser"
        user_name = _first_non_empty(context, "userName", "username") or self.config.username or user_id
        tenant_id = _first_non_empty(context, "tenantId", "tenantid", "ytid") or self.config.tenantid or ""
        return {"user_id": user_id, "user_name": user_name, "tenant_id": tenant_id}

    def _install_bpr_event_collector(self, page, bpr_id: str) -> None:
        try:
            page.evaluate(
                """({ bprId }) => {
                    if (window.__ydfBrowserBprCollectorInstalled) {
                      window.__ydfBrowserBprEvents = [];
                      window.__ydfBrowserBprId = bprId;
                      return;
                    }
                    window.__ydfBrowserBprEvents = [];
                    window.__ydfBrowserBprId = bprId;
                    window.__ydfBrowserBprCollectorInstalled = true;
                    document.addEventListener('click', (event) => {
                      const target = event.target instanceof HTMLElement ? event.target : null;
                      const text = target && target.innerText ? target.innerText.slice(0, 80) : '';
                      const title = target ? (target.getAttribute('title') || target.getAttribute('aria-label') || '') : '';
                      window.__ydfBrowserBprEvents.push({
                        en: 'HBClick',
                        evt: Date.now(),
                        attrs: { bprId: window.__ydfBrowserBprId, isTrustedEv: event.isTrusted },
                        ntxt: text,
                        tits: title
                      });
                    }, true);
                    window.addEventListener('error', (event) => {
                      window.__ydfBrowserBprEvents.push({
                        en: 'HBError',
                        evt: Date.now(),
                        attrs: { bprId: window.__ydfBrowserBprId },
                        et: 'Error',
                        msg: event.message,
                        fn: event.filename,
                        lno: event.lineno,
                        cno: event.colno
                      });
                    });
                  }""",
                {"bprId": bpr_id},
            )
        except Exception:
            return

    def _collect_bpr_uba_events(self, page, bpr_id: str, start_ts: int, end_ts: int) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        try:
            raw = page.evaluate("""() => window.__ydfBrowserBprEvents || []""")
            if isinstance(raw, list):
                events = [item for item in raw if isinstance(item, dict)]
        except Exception:
            events = []
        return [
            {
                "en": "HBClick",
                "evt": start_ts,
                "attrs": {"bprId": bpr_id, "isTrustedEv": True},
                "ntxt": "ydf-browser-bpr-start",
                "tits": "ydf-browser-bpr-start",
            },
            *events,
            {
                "en": "HBClick",
                "evt": end_ts,
                "attrs": {"bprId": bpr_id, "isTrustedEv": True},
                "ntxt": "ydf-browser-bpr-end",
                "tits": "ydf-browser-bpr-end",
            },
        ]

    def _install_request_forwarding(self) -> None:
        if not self.request_forward_rules or self._context is None:
            return
        self._context.route("**/*", self._handle_request_forward)

    def _handle_request_forward(self, route, request) -> None:
        original_url = str(getattr(request, "url", "") or "")
        match = match_request_forwarding(original_url, self.request_forward_rules)
        if match is None:
            _route_fallback(route)
            return
        rule, target_url = match
        event: dict[str, Any] = {
            "url": original_url,
            "target_url": target_url,
            "method": str(getattr(request, "method", "") or ""),
            "status": 0,
            "success": False,
            "rule": rule.to_dict(),
        }
        try:
            response = self._context.request.fetch(
                target_url,
                method=event["method"] or None,
                headers=_forward_request_headers(getattr(request, "headers", {}) or {}),
                data=_request_post_data_buffer(request),
                ignore_https_errors=True,
            )
            status = int(getattr(response, "status", 0) or 0)
            headers = _forward_response_headers(getattr(response, "headers", {}) or {})
            body_reader = getattr(response, "body", None)
            body = body_reader() if callable(body_reader) else None
            route.fulfill(status=status, headers=headers, body=body, response=response if body is None else None)
            event.update({"status": status, "success": True})
        except Exception as exc:
            event["error"] = str(exc)
            try:
                route.abort()
            except Exception:
                pass
        finally:
            forwarding = {
                "matched": True,
                "rule": rule.to_dict(),
                "success": bool(event["success"]),
                "status": int(event["status"]),
                "actual_url": target_url,
            }
            self._request_forward_facts[id(request)] = forwarding
            if self.observation_session is not None:
                observed = getattr(self.observation_session, "network_request_forwarded", None)
                if observed is not None:
                    observed(request_key=id(request), forwarding=forwarding)
            self._record_request_forward_event(event)

    def _record_request_forward_event(self, event: dict[str, Any]) -> None:
        self._request_forward_events.append(event)
        if len(self._request_forward_events) > 20:
            self._request_forward_events = self._request_forward_events[-20:]

    def _request_forwarding_state(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.request_forward_rules),
            "rules": [rule.to_dict() for rule in self.request_forward_rules],
            "recent_events": list(self._request_forward_events[-10:]),
        }

    def stop(self) -> None:
        if self.observation_session is not None:
            self.observation_session.finish_incomplete_network_requests()
        if self._context and self.profile_dir is not None:
            try:
                self._context.close()
            except Exception as exc:
                if not _is_browser_closed_error(exc):
                    raise
        if self._browser:
            try:
                self._browser.close()
            except Exception as exc:
                if not _is_browser_closed_error(exc):
                    raise
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception as exc:
                if not _is_browser_closed_error(exc):
                    raise

    def has_open_page(self) -> bool:
        if self._page is None:
            return False
        try:
            if self._page.is_closed():
                return False
        except Exception:
            return False
        evaluate = getattr(self._page, "evaluate", None)
        if callable(evaluate):
            try:
                evaluate("() => true")
            except Exception as exc:
                return not _is_browser_closed_error(exc)
        return True

    def clear_visible_cookies(self, base_url: str) -> None:
        if self._context is None:
            return
        try:
            cookies = list(self._context.cookies())
        except Exception:
            cookies = []
        for cookie in cookies:
            if not cookie_visible_to_url(cookie, base_url):
                continue
            kwargs = {
                "name": str(cookie.get("name") or ""),
                "domain": str(cookie.get("domain") or ""),
                "path": str(cookie.get("path") or "/"),
            }
            try:
                self._context.clear_cookies(**kwargs)
            except TypeError:
                self._context.clear_cookies()
                break

    def close_case_pages(self) -> None:
        if self.observation_session is not None:
            self.observation_session.finish_incomplete_network_requests()
        if self._context is None:
            self._page = None
            return
        pages = []
        try:
            pages = list(getattr(self._context, "pages", []) or [])
        except Exception:
            pages = []
        if not pages and self._page is not None:
            pages = [self._page]
        holder_page = None
        if self.profile_dir is not None:
            try:
                holder_page = self._new_page()
            except Exception as exc:
                if not _is_browser_closed_error(exc):
                    raise
        for page in pages:
            try:
                page.close()
            except Exception:
                continue
        self._page = holder_page
        self._cookies_applied = False
        self._ai_failure_screenshot_attempted = False
        self._ai_failure_dom_attempted = False

    def open_home(self) -> None:
        page = self._require_page()
        self._apply_api_session_cookies()
        page.goto(f"{self.config.base_url.rstrip('/')}/")

    def sync_manual_session_cookies(self) -> None:
        bridge = getattr(self.session, "_ydf_cookie_bridge", None)
        if bridge is not None:
            try:
                bridge.pull()
            except Exception as exc:
                if not _is_browser_closed_error(exc):
                    raise
                # ponytail: closure can lose the final polling interval; next run probes the saved snapshot.

    def wait_for_manual_session(self, poll_interval_seconds: float = 0.2) -> str:
        seen_page_ids: set[int] = set()
        page_urls: dict[int, str] = {}
        while True:
            try:
                is_closed = getattr(self._context, "is_closed", None) if self._context is not None else None
                if callable(is_closed) and is_closed():
                    return "browser_closed"
                manual_window_count = _manual_browser_window_count(self._manual_browser_app_name)
                if manual_window_count and manual_window_count > 0:
                    self._manual_browser_seen_windows = True
                if self._manual_browser_seen_windows and manual_window_count == 0:
                    return "browser_closed"
                pages = list(getattr(self._context, "pages", []) or []) if self._context is not None else []
            except Exception as exc:
                if "target page, context or browser has been closed" in str(exc).lower():
                    return "browser_closed"
                raise
            open_pages = {}
            for page in pages:
                page_is_closed = getattr(page, "is_closed", None)
                if not callable(page_is_closed) or not page_is_closed():
                    open_pages[id(page)] = page
            open_page_ids = set(open_pages)
            if not open_page_ids:
                return "browser_closed"
            if seen_page_ids and not (seen_page_ids & open_page_ids):
                return "browser_closed"
            if len(open_pages) == 1:
                page_id, page = next(iter(open_pages.items()))
                evaluate = getattr(page, "evaluate", None)
                if callable(evaluate):
                    try:
                        evaluate("() => true")
                    except Exception as exc:
                        if _is_browser_closed_error(exc):
                            return "browser_closed"
                current_url = str(getattr(page, "url", "") or "")
                previous_url = page_urls.get(page_id, "")
                new_tab_urls = ("chrome://newtab", "chrome://new-tab-page")
                if previous_url and current_url.startswith(new_tab_urls) and not previous_url.startswith(new_tab_urls):
                    return "browser_closed"
            seen_page_ids.update(open_page_ids)
            page_urls.update({page_id: str(getattr(page, "url", "") or "") for page_id, page in open_pages.items()})
            self.sync_manual_session_cookies()
            # ponytail: bounded polling; the sync API has close state but no blocking wait primitive.
            self._wait_for_manual_session_tick(open_pages, poll_interval_seconds)

    def _wait_for_manual_session_tick(self, open_pages: dict[int, Any], poll_interval_seconds: float) -> None:
        timeout_ms = max(1, int(poll_interval_seconds * 1000))
        for page in open_pages.values():
            wait_for_timeout = getattr(page, "wait_for_timeout", None)
            if not callable(wait_for_timeout):
                continue
            try:
                wait_for_timeout(timeout_ms)
                return
            except Exception as exc:
                if _is_browser_closed_error(exc):
                    return
        time.sleep(poll_interval_seconds)

    def open_menu(self, menu_target: MenuTarget) -> None:
        if self.profile_dir is not None:
            self._replace_page_for_menu()
        page = self._require_page()
        self._apply_api_session_cookies()
        if menu_target.service_code:
            for url in build_menu_open_urls(self.config.base_url, menu_target):
                if should_open_menu_in_new_tab(page.url, url):
                    page = self._open_in_new_tab(url)
                else:
                    page.goto(url)
            return
        self._dismiss_privacy_dialog()
        self._open_global_navigation()
        for index, part in enumerate(menu_target.path):
            selectors = []
            if index == 0:
                selectors.extend([f'span.domain-item-text:has-text("{part}")', f'[title="{part}"]'])
            selectors.extend(
                [
                    f'text="{part}"',
                    f'span:has-text("{part}")',
                    f'a:has-text("{part}")',
                    f'li:has-text("{part}")',
                    f'div:has-text("{part}")',
                ]
            )
            self._click_first(selectors)
            page.wait_for_timeout(800)

    def _new_page(self):
        return self._attach_page_handlers(self._context.new_page())

    def _attach_page_handlers(self, page):
        page.on("request", self._capture_network_request)
        page.on("response", self._handle_response)
        page.on("requestfinished", self._capture_network_finished)
        page.on("requestfailed", self._capture_network_failure)
        page.on("console", self._capture_console_event)
        page.on("pageerror", self._capture_page_error)
        return page

    def _replace_page_for_menu(self) -> None:
        old_page = self._page
        self._page = self._new_page()
        if old_page is not None:
            try:
                old_page.close()
            except Exception:
                pass
        self._cookies_applied = False

    def capture_runtime_elements(self, manifest: PageManifest | None) -> list[dict[str, Any]]:
        runtime_elements: list[dict[str, Any]] = []
        for frame_index, frame in enumerate(self._require_page().frames):
            runtime_elements.extend(self._scan_frame(frame, frame_index))
        return runtime_elements

    def evaluate_all_frames(self, script: str, payload: Any) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for frame in self._require_page().frames:
            try:
                value = frame.evaluate(script, payload)
            except Exception:
                continue
            results.append(
                {
                    "frame_name": str(getattr(frame, "name", "") or ""),
                    "frame_url": str(getattr(frame, "url", "") or ""),
                    "value": value,
                }
            )
        return results

    def is_region_visible(self, fieldid: str) -> bool:
        if not fieldid:
            return False
        selector = f'[fieldid="{fieldid}"], [data-fieldid="{fieldid}"]'
        for context in self._all_search_contexts():
            locator = context.locator(selector)
            try:
                count = locator.count()
            except Exception:
                continue
            for index in range(count):
                try:
                    candidate = locator.nth(index)
                    if candidate.is_visible(timeout=200) and self._locator_intersects_viewport(candidate):
                        return True
                except Exception:
                    continue
        return False

    def resolve_visible_page_identity(self, fieldids: list[str]) -> str | None:
        visible = [fieldid for fieldid in dict.fromkeys(fieldids) if self.is_region_visible(fieldid)]
        return visible[0] if len(visible) == 1 else None

    def inspect_table_scope_regions(
        self, regions: list[Region], *, collect_columns: bool = False,
    ) -> list[TableRuntimeEvidence]:
        contexts = self._all_search_contexts()
        foreground_exists = False
        for context in contexts:
            try:
                if bool(context.evaluate(_TABLE_SCOPE_FOREGROUND_EXISTS_SCRIPT)):
                    foreground_exists = True
                    break
            except Exception:
                continue
        evidence: list[TableRuntimeEvidence] = []
        for region in regions:
            region_items: list[tuple[str, dict[str, Any]]] = []
            for fieldid in dict.fromkeys([region.fieldid, *region.runtime_fieldids]):
                token = f"table-scope-{uuid.uuid4().hex}"
                for context in contexts:
                    try:
                        candidate = context.evaluate(
                            _TABLE_SCOPE_REGION_EVIDENCE_SCRIPT,
                            {"fieldid": fieldid, "token": token},
                        )
                    except Exception:
                        continue
                    items = candidate if isinstance(candidate, list) else [candidate]
                    items = [item for item in items if isinstance(item, dict) and item.get("exists")]
                    if items:
                        region_items.extend((fieldid, item) for item in items)
                        break
            logical_items: list[tuple[str, dict[str, Any], list[tuple[str, str]], bool]] = []
            for fieldid in dict.fromkeys(item_fieldid for item_fieldid, _item in region_items):
                physical_items = [item for item_fieldid, item in region_items if item_fieldid == fieldid]
                groups: dict[tuple[bool, bool, bool], list[dict[str, Any]]] = {}
                for item in physical_items:
                    key = (
                        bool(item.get("visible")),
                        bool(item.get("interactive")),
                        bool(item.get("inForeground")),
                    )
                    groups.setdefault(key, []).append(item)
                for group_items in groups.values():
                    header_groups = [_table_header_records(item) for item in group_items]
                    columns = [[text for text, _identity in headers] for headers in header_groups]
                    row_texts = [
                        tuple(str(value) for value in item.get("rowTexts", []) if str(value).strip())
                        for item in group_items
                    ]
                    header_and_body_split = (
                        len(group_items) == 2
                        and any(column and int(item.get("rowCount") or 0) == 0 for column, item in zip(columns, group_items))
                        and any(not column and int(item.get("rowCount") or 0) > 0 for column, item in zip(columns, group_items))
                    )
                    equivalent_rows = bool(row_texts and all(rows for rows in row_texts) and len(set(row_texts)) == 1)
                    if header_and_body_split or equivalent_rows:
                        merged_headers = _merge_header_records(header_groups)
                        item = max(
                            group_items,
                            key=lambda value: (int(value.get("rowCount") or 0), float(value.get("area") or 0)),
                        )
                        logical_items.append((fieldid, item, merged_headers, False))
                        continue
                    for item, item_headers in zip(group_items, header_groups):
                        logical_items.append((fieldid, item, item_headers, len(group_items) > 1))
            equivalent_items: dict[
                tuple[object, ...],
                tuple[str, dict[str, Any], list[tuple[str, str]]],
            ] = {}
            for fieldid, item, headers, preserve_physical_copy in logical_items:
                key = (
                    bool(item.get("visible")),
                    bool(item.get("interactive")),
                    bool(item.get("inForeground")),
                    tuple(text for text, _identity in headers),
                    tuple(str(value) for value in item.get("rowTexts", []) if str(value).strip()),
                    (fieldid, str(item.get("token") or "")) if preserve_physical_copy else (),
                )
                current_fieldid, current, _current_headers = equivalent_items.get(key, ("", {}, []))
                score = (int(item.get("rowCount") or 0), float(item.get("area") or 0))
                current_score = (int(current.get("rowCount") or 0), float(current.get("area") or 0))
                if not current_fieldid or score > current_score:
                    equivalent_items[key] = (fieldid, item, headers)
            resolved_items = list(equivalent_items.values())
            if collect_columns and len(resolved_items) == 1:
                fieldid, item, headers = resolved_items[0]
                try:
                    collected_headers = self._collect_table_header_records(table_fieldid=fieldid)
                except Exception:
                    collected_headers = []
                if collected_headers:
                    resolved_items[0] = (
                        fieldid,
                        item,
                        _merge_collected_header_records(headers, collected_headers),
                    )
            for fieldid, item, headers in resolved_items:
                evidence.append(
                    TableRuntimeEvidence(
                        region_fieldid=region.fieldid,
                        runtime_fieldid=fieldid,
                        exists=True,
                        visible=bool(item.get("visible")),
                        interactive=bool(item.get("interactive")),
                        foreground=bool(item.get("inForeground") or not foreground_exists),
                        columns=tuple(text for text, _identity in headers),
                        columns_observed=True,
                        token=str(item.get("token") or ""),
                    )
                )
            if not equivalent_items:
                evidence.append(
                    TableRuntimeEvidence(
                        region_fieldid=region.fieldid,
                        runtime_fieldid=region.fieldid,
                        exists=False,
                        visible=False,
                        interactive=False,
                        foreground=False,
                    )
                )
        return evidence

    def wait_before_table_scope_retry(self, timeout_ms: int) -> None:
        self._require_page().wait_for_timeout(timeout_ms)

    def is_table_scope_token_valid(self, token: str) -> bool:
        return bool(token) and self._table_scope_token_context(token) is not None

    def _table_scope_token_context(self, token: str):
        page = self._require_page()
        matches = []
        for context in self._all_search_contexts():
            if context is not page and context is getattr(page, "main_frame", None):
                continue
            try:
                if context.evaluate(_TABLE_SCOPE_TOKEN_VALID_SCRIPT, token):
                    matches.append(context)
            except Exception:
                continue
        return matches[0] if len(matches) == 1 else None

    def _locator_intersects_viewport(self, locator) -> bool:
        try:
            return bool(
                locator.evaluate(
                    """(node) => {
                        const style = window.getComputedStyle(node);
                        const rect = node.getBoundingClientRect();
                        const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 0;
                        const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
                        return Boolean(style)
                          && style.visibility !== 'hidden'
                          && style.display !== 'none'
                          && rect.width > 0
                          && rect.height > 0
                          && rect.right > 0
                          && rect.bottom > 0
                          && rect.left < viewportWidth
                          && rect.top < viewportHeight;
                    }""",
                    timeout=500,
                )
            )
        except Exception:
            return True

    def prepare_binding(self, manifest: PageManifest) -> None:
        bridge = getattr(self.session, "_ydf_cookie_bridge", None)
        if bridge is not None:
            bridge.verify_browser_context()

    def expand_query_conditions(self) -> bool:
        if self._try_click_first(build_query_expand_selectors()):
            self._require_page().wait_for_timeout(500)
            return True
        return False

    def page_frame_states(self) -> list[dict[str, Any]]:
        page = self._require_page()
        return [
            {
                "name": str(frame.name or ""),
                "url": str(frame.url or ""),
                "is_main": frame is page.main_frame,
                "parent_is_main": frame.parent_frame is page.main_frame,
            }
            for frame in page.frames
        ]

    def current_page_url(self) -> str:
        return str(self._require_page().url or "")

    def reload_page(self) -> None:
        self._require_page().reload(wait_until="domcontentloaded")

    def wait_for_first_visible(self, selectors: list[str], timeout_ms: int) -> bool:
        page = self._require_page()
        for selector in selectors:
            try:
                page.locator(selector).first.wait_for(state="visible", timeout=timeout_ms)
                return True
            except Exception:
                continue
        return False

    def capture_page_state(self) -> dict[str, Any]:
        page = self._require_page()
        frames = []
        for index, frame in enumerate(page.frames):
            frames.append(
                {
                    "index": index,
                    "name": frame.name,
                    "url": frame.url,
                }
            )
        return {
            "url": page.url,
            "title": page.title(),
            "frames": frames,
            "frame_count": len(frames),
            "request_forwarding": self._request_forwarding_state(),
        }

    def begin_notification_capture(self) -> None:
        self._install_notification_observers(reset=True)

    def observe_workflow_panel(self, label: str) -> dict[str, Any]:
        panels = []
        for index, frame in enumerate(self._require_page().frames):
            try:
                snapshots = frame.evaluate(
                    _WORKFLOW_PANEL_SCAN_SCRIPT, {"label": label, "token": uuid.uuid4().hex},
                )
            except Exception as exc:
                return {"status": "evidence_unavailable", "frame_index": index,
                        "error_type": type(exc).__name__, "panels": panels}
            panels.extend({**snapshot, "frame_index": index} for snapshot in snapshots)
        if len(panels) != 1:
            return {"status": "ambiguous" if panels else "missing", "panels": panels}
        return panels[0]

    def click_workflow_panel_action(self, label: str) -> dict[str, Any]:
        snapshot = self.observe_workflow_panel(label)
        if snapshot.get("status") != "ready":
            error = RuntimeError(f"工作流操作面板动作不可用: {label} ({snapshot.get('status')})")
            error.data = {"workflow_panel": snapshot}
            raise error
        frame = self._require_page().frames[snapshot["frame_index"]]
        locator = frame.locator(snapshot["action"]["selector"])
        locator.click(trial=True, timeout=1500)
        self._prepare_action_surface(locator)
        locator.click(timeout=1500)
        return snapshot

    def observe_workflow_result(self, timeout_ms: int = 0) -> dict[str, Any] | None:
        """观察当前前景工作流批量结果层，返回结构化快照或不可用证据。"""
        page = self._require_page()
        deadline = time.monotonic() + max(int(timeout_ms), 0) / 1000
        evidence: dict[str, Any] | None = None
        while True:
            frames = list(getattr(page, "frames", []) or [page])
            for frame_index, frame in enumerate(frames):
                try:
                    candidates = frame.evaluate(_WORKFLOW_RESULT_SCAN_SCRIPT)
                except Exception:
                    continue
                for candidate in candidates if isinstance(candidates, list) else []:
                    if not isinstance(candidate, dict):
                        continue
                    status = str(candidate.get("status") or "").strip()
                    if status not in {"observed", "evidence_unavailable"}:
                        continue
                    snapshot = {**candidate, "frame_index": frame_index}
                    if status == "observed":
                        self._last_workflow_result_snapshot = snapshot
                        return snapshot
                    if evidence is None:
                        evidence = snapshot
            if evidence is not None or time.monotonic() >= deadline:
                if evidence is not None:
                    self._last_workflow_result_snapshot = evidence
                return evidence
            remaining_ms = max(1, int((deadline - time.monotonic()) * 1000))
            page.wait_for_timeout(min(150, remaining_ms))

    def open_workflow_result_details(
        self,
        label: str = "查看详情",
        timeout_ms: int = 10000,
    ) -> dict[str, Any]:
        snapshot = self._last_workflow_result_snapshot or self.observe_workflow_result(timeout_ms=0)
        if not snapshot or str(snapshot.get("status") or "") != "observed":
            raise RuntimeError("未找到可操作的工作流批量结果层")
        frame, root = self._workflow_result_root(snapshot)
        action = self._workflow_result_action(frame, root, snapshot, "details", label)
        if action is None:
            raise RuntimeError(f"未找到工作流批量结果层详情入口: {label}")
        remaining_ms = max(1, int(timeout_ms))
        action.click(timeout=remaining_ms)
        evidence = self._wait_for_workflow_result_details(timeout_ms=remaining_ms)
        if evidence is None:
            raise RuntimeError("工作流批量结果层详情证据不可用")
        return evidence

    def confirm_workflow_result(self, label: str = "确认", timeout_ms: int = 10000) -> dict[str, Any]:
        snapshot = self._last_workflow_result_snapshot or self.observe_workflow_result(timeout_ms=0)
        if not snapshot or str(snapshot.get("status") or "") != "observed":
            raise RuntimeError("未找到可关闭的工作流批量结果层")
        frame, root = self._workflow_result_root(snapshot)
        action = self._workflow_result_action(frame, root, snapshot, "confirm", label)
        if action is None:
            raise RuntimeError(f"未找到工作流批量结果层确认入口: {label}")
        action.click(timeout=max(1, int(timeout_ms)))
        deadline = time.monotonic() + max(int(timeout_ms), 1) / 1000
        while time.monotonic() < deadline:
            try:
                if not root.is_visible(timeout=300):
                    self._last_workflow_result_snapshot = None
                    return {"closed": True, "label": label}
            except Exception:
                self._last_workflow_result_snapshot = None
                return {"closed": True, "label": label}
            self._require_page().wait_for_timeout(150)
        return {
            "closed": False,
            "label": label,
            "workflow_result": dict(snapshot),
        }

    def _workflow_result_root(self, snapshot: dict[str, Any]):
        frames = list(getattr(self._require_page(), "frames", []) or [self._require_page()])
        frame_index = int(snapshot.get("frame_index") or 0)
        if frame_index < 0 or frame_index >= len(frames):
            raise RuntimeError("工作流批量结果层所在 frame 已失效")
        frame = frames[frame_index]
        selector = str(snapshot.get("selector") or "").strip()
        if not selector:
            raise RuntimeError("工作流批量结果层缺少根定位证据")
        root = frame.locator(selector).first
        try:
            if not root.is_visible(timeout=300):
                raise RuntimeError("工作流批量结果层已不可见")
        except Exception as exc:
            if isinstance(exc, RuntimeError):
                raise
            raise RuntimeError(f"工作流批量结果层根不可用: {exc}") from exc
        return frame, root

    def _workflow_result_action(self, frame, root, snapshot: dict[str, Any], operation: str, label: str):
        actions = snapshot.get("actions") if isinstance(snapshot.get("actions"), dict) else {}
        selector = str(actions.get(operation) or "").strip()
        if selector:
            try:
                candidate = frame.locator(selector).first
                if candidate.count() and candidate.is_visible(timeout=300):
                    return candidate
            except Exception:
                pass
        expected = str(label or "").strip()
        for selector in (
            'button, [role="button"], a, span',
            '[aria-label], [title]',
        ):
            try:
                candidates = root.locator(selector)
                count = candidates.count()
            except Exception:
                continue
            for index in range(count):
                candidate = candidates.nth(index)
                try:
                    if not candidate.is_visible(timeout=300):
                        continue
                    text = " ".join(
                        str(
                            candidate.inner_text(timeout=300)
                            or candidate.get_attribute("aria-label", timeout=300)
                            or candidate.get_attribute("title", timeout=300)
                            or ""
                        ).split()
                    )
                    if text == expected:
                        return candidate
                except Exception:
                    continue
        return None

    def _wait_for_workflow_result_details(self, timeout_ms: int = 10000) -> dict[str, Any] | None:
        page = self._require_page()
        deadline = time.monotonic() + max(int(timeout_ms), 1) / 1000
        while time.monotonic() < deadline:
            frames = list(getattr(page, "frames", []) or [page])
            for frame_index, frame in enumerate(frames):
                try:
                    payloads = frame.evaluate(_WORKFLOW_RESULT_DETAILS_SCAN_SCRIPT)
                except Exception:
                    continue
                for payload in payloads if isinstance(payloads, list) else []:
                    if not isinstance(payload, dict) or payload.get("status") != "observed":
                        continue
                    details = payload.get("details")
                    if isinstance(details, list) and details:
                        return {"details": details, "dialog": {**payload, "frame_index": frame_index}}
            page.wait_for_timeout(150)
        return None

    def begin_page_response_capture(self) -> int:
        self._page_response_events.clear()
        return 0

    def page_response_cursor(self) -> int:
        return len(self._page_response_events)

    def page_responses_since(self, cursor: int) -> tuple[int, list[dict[str, Any]]]:
        return len(self._page_response_events), list(self._page_response_events[max(0, cursor) :])

    def page_error_cursor(self) -> int:
        return len(self._page_errors)

    def page_errors_since(self, cursor: int) -> tuple[int, list[dict[str, Any]]]:
        return len(self._page_errors), [dict(item) for item in self._page_errors[max(0, cursor) :]]

    def _acquire_action_completion(self) -> None:
        if self._action_completion_active:
            raise RuntimeError("已有动作正在等待完成")
        self._action_completion_active = True

    def _release_action_completion(self) -> None:
        self._action_completion_active = False
        self._query_completion_requests.clear()
        self._query_completion_frame = None
        for observer in self._action_surface_observers:
            try:
                observer.dispose()
            except Exception:
                pass
        self._action_surface_observers.clear()

    def _prepare_action_surface(self, locator) -> None:
        if not self._action_completion_active or self._action_completion_action not in {
            "toolbar.click", "dialog.click", "action.click", "workflow_panel.click",
        } or self._action_surface_observers:
            return
        try:
            element = locator.element_handle(timeout=500)
            while element is not None:
                try:
                    self._action_surface_observers.append(element.evaluate_handle(
                        _ACTION_SURFACE_OBSERVER_SCRIPT, self._action_completion_context,
                    ))
                    frame = element.owner_frame()
                finally:
                    element.dispose()
                # Keep an observer in each ancestor document so removing an iframe
                # cannot destroy the only reference to its enclosing work surface.
                element = frame.frame_element() if frame is not None and frame.parent_frame is not None else None
        except Exception:
            pass  # Missing browser evidence leaves the existing completion policy in charge.

    def _prepare_action_completion(self, request: ActionCompletionRequest) -> None:
        self._action_completion_action = request.action
        self._action_completion_context = dict(request.context)
        self._query_completion_requests.clear()
        self._query_completion_frame = None
        try:
            self._action_completion_existing_notifications = {
                str(item.get("message") or "")
                for item in self._scan_notifications()
                if str(item.get("message") or "")
            }
        except Exception:
            self._action_completion_existing_notifications = set()
        self._action_completion_state = self._capture_action_completion_state()
        busy_key = (
            "target_busy"
            if request.action == "query.search" and self._action_completion_context.get("target_table_fieldid")
            else "busy"
        )
        self._action_completion_seen_busy = int(self._action_completion_state.get(busy_key) or 0) > 0
        self.begin_notification_capture()

    def _observe_action_completion(
        self,
        request: ActionCompletionRequest,
        stage: str = "",
    ) -> ActionCompletionObservation:
        notifications: list[dict[str, str]] = []
        if stage in {"", "notifications"}:
            buffered = self._drain_buffered_notifications()
            scanned = [
                item
                for item in self._scan_notifications()
                if str(item.get("message") or "") not in self._action_completion_existing_notifications
            ]
            notifications = self._merge_notifications(buffered, scanned)
            if stage == "notifications":
                return ActionCompletionObservation(
                    notifications=tuple(
                        ActionNotification(
                            type=str(item.get("type") or "info"),
                            message=str(item.get("message") or ""),
                        )
                        for item in notifications
                    )
                )
        dynamic_template = False
        dynamic_template_fallback = False
        if stage in {"", "dynamic_template"}:
            payload = self._dynamic_template_payload
            dynamic_template = bool(
                payload is not None
                and self._dynamic_template_payload_matches_action(payload)
                and self._dynamic_template_payload_work_surface_ready(payload)
            )
            dynamic_template_fallback = bool(
                request.action == "toolbar.click"
                and not self._action_completion_context.get("target_page_id")
                and payload is not None
                and self.dynamic_template_payload_can_apply_as_fallback(payload)
            )
            if stage == "dynamic_template":
                return ActionCompletionObservation(
                    dynamic_template=dynamic_template,
                    dynamic_template_fallback=dynamic_template_fallback,
                )
        dom_signal = self._action_dom_completion_signal(request.action)
        if stage == "dom":
            return ActionCompletionObservation(dom_signal=dom_signal)
        return ActionCompletionObservation(
            notifications=tuple(
                ActionNotification(
                    type=str(item.get("type") or "info"),
                    message=str(item.get("message") or ""),
                )
                for item in notifications
            ),
            dynamic_template=dynamic_template,
            dynamic_template_fallback=dynamic_template_fallback,
            dom_signal=dom_signal,
        )

    @staticmethod
    def _action_completion_now() -> float:
        return time.monotonic()

    def _wait_action_completion_poll(self, timeout_ms: int) -> None:
        self._require_page().wait_for_timeout(timeout_ms)

    def collect_notifications(self, timeout_ms: int = 1500) -> list[dict[str, str]]:
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            notifications = self._merge_notifications(
                self._drain_buffered_notifications(),
                self._scan_notifications(),
            )
            if notifications or time.monotonic() >= deadline:
                return notifications
            self._require_page().wait_for_timeout(150)

    def _dynamic_template_payload_matches_action(self, payload: dict[str, Any] | None = None) -> bool:
        expected = str(self._action_completion_context.get("target_page_id") or "").strip()
        if not expected:
            return False
        payload = payload if isinstance(payload, dict) else self._dynamic_template_payload or {}
        candidates = _dynamic_template_payload_identity_candidates(payload)
        return expected in candidates

    def dynamic_template_payload_can_apply_as_fallback(self, payload: dict[str, Any]) -> bool:
        if self._action_completion_context.get("target_page_id"):
            return self._dynamic_template_payload_matches_action(payload)
        identities = _dynamic_template_payload_identity_candidates(payload)
        source = str(self._action_completion_context.get("source_page_id") or "").strip()
        if not any(identity != source for identity in identities):
            return False
        return self._dynamic_template_payload_work_surface_ready(payload)

    def _dynamic_template_payload_work_surface_ready(self, payload: dict[str, Any]) -> bool:
        identities = _dynamic_template_payload_identity_candidates(payload)
        if not identities:
            return False
        expected = str(self._action_completion_context.get("target_page_id") or "").strip()
        source = str(self._action_completion_context.get("source_page_id") or "").strip()
        ready_context = [source, expected]
        cache_key = "_ydf_browser_work_surface_ready_cache"
        cached = payload.get(cache_key)
        if isinstance(cached, dict) and cached.get("context") == ready_context:
            if self._dynamic_template_cached_field_ready(cached):
                return True
            payload.pop(cache_key, None)
        if expected:
            identities = [expected]
        elif source:
            target_identities = [identity for identity in identities if identity != source]
            if target_identities:
                identities = target_identities
        data = payload.get("data")
        page_id = str(data.get("pageId") or "").strip() if isinstance(data, dict) else ""
        page_holder_identity = f"page{page_id}" if page_id and page_id != source else ""
        if page_holder_identity and page_holder_identity not in identities:
            identities.append(page_holder_identity)
        table_identity = _dynamic_template_payload_first_table_identity(payload)
        if table_identity and table_identity not in identities:
            identities.append(table_identity)
        field_identities = _dynamic_template_payload_form_field_identities(payload)
        manifest = build_page_manifest(payload) if table_identity else None
        fields = [field for field in manifest.fields if field.visible_by_config] if manifest is not None else []
        readonly_table = bool(fields) and all(
            (field.raw.get("props") or {}).get("readOnly") in (True, 1) for field in fields
        )
        if readonly_table:
            # 平台只读文本不保留输入控件身份，必须由目标表格独立证明就绪。
            table = next((region for region in manifest.regions if region.fieldid == table_identity), None)
            identities = list(dict.fromkeys([table_identity, *(table.runtime_fieldids if table else [])]))
            field_identities = []
        identity_sets = (
            [[*identities]] if table_identity or not field_identities else []
        )
        identity_sets.extend(
            [
                [*identities, field_identity]
                for field_identity in field_identities
                if field_identity not in identities
            ]
        )
        surface_ready = False
        for surface_identities in identity_sets:
            root_count = 0
            interactive_count = 0
            for frame in self._require_page().frames:
                try:
                    state = dict(frame.evaluate(_DYNAMIC_TEMPLATE_WORK_SURFACE_SCRIPT, surface_identities) or {})
                except Exception:
                    continue
                if state.get("root"):
                    root_count += int(state.get("root_count") or 1)
                if state.get("interactive"):
                    interactive_count += int(state.get("interactive_count") or 1)
            if root_count == 1 and interactive_count == 1:
                surface_ready = True
                break
        if not surface_ready:
            if readonly_table:
                return False
            return self._dynamic_template_payload_field_labels_ready(payload, ready_context)
        for field_identity in field_identities:
            for frame in self._require_page().frames:
                try:
                    state = dict(frame.evaluate(_DYNAMIC_TEMPLATE_WORK_SURFACE_SCRIPT, [field_identity]) or {})
                except Exception:
                    continue
                if state.get("root") and int(state.get("root_count") or 1) == 1:
                    return True
        if not field_identities:
            return True
        return self._dynamic_template_payload_field_labels_ready(payload, ready_context)

    def _dynamic_template_cached_field_ready(self, cached: dict[str, Any]) -> bool:
        frame_index = cached.get("frame_index")
        selector = str(cached.get("selector") or "")
        frames = self._require_page().frames
        if not isinstance(frame_index, int) or frame_index < 0 or frame_index >= len(frames) or not selector:
            return False
        try:
            locator = frames[frame_index].locator(selector)
            if locator.count() != 1 or not locator.is_visible(timeout=300) or not locator.is_enabled(timeout=300):
                return False
            if not locator.is_editable(timeout=300):
                return False
            locator.click(trial=True, timeout=300)
            return True
        except Exception:
            return False

    def _dynamic_template_payload_field_labels_ready(
        self,
        payload: dict[str, Any],
        ready_context: list[str] | None = None,
    ) -> bool:
        labels = _dynamic_template_payload_form_field_labels(payload)
        runtime_matches: list[dict[str, Any]] = []
        for frame_index, frame in enumerate(self._require_page().frames):
            try:
                items = self._scan_frame(frame, frame_index)
            except Exception:
                continue
            runtime_matches.extend(
                {**item, "_frame_index": frame_index}
                for item in items
                if item.get("label_text") in labels and item.get("visible") and item.get("editable")
                and item.get("pointer_receivable")
            )
        dialog_matches = [item for item in runtime_matches if item.get("in_dialog")]
        if dialog_matches:
            cache_match = next(
                (
                    item
                    for item in dialog_matches
                    if str(item.get("tag_name") or "").lower() in {"input", "textarea", "select"}
                    or item.get("role") == "textbox"
                ),
                None,
            )
            selector = str((cache_match or {}).get("selector") or "")
            frame_index = (cache_match or {}).get("_frame_index")
            if selector and isinstance(frame_index, int):
                payload["_ydf_browser_work_surface_ready_cache"] = {
                    "context": list(ready_context or []),
                    "frame_index": frame_index,
                    "selector": selector,
                }
            return True
        return any(self._dynamic_template_payload_field_label_ready(label) for label in labels)

    def _dynamic_template_payload_field_label_ready(self, label: str) -> bool:
        if not label:
            return False
        for frame in self._require_page().frames:
            try:
                state = dict(frame.evaluate(_DYNAMIC_TEMPLATE_FIELD_LABEL_SCRIPT, label) or {})
            except Exception:
                continue
            if state.get("root") and state.get("interactive"):
                return int(state.get("root_count") or 1) == 1 and int(state.get("interactive_count") or 1) == 1
        return False

    def _action_dom_completion_signal(self, action: str) -> str:
        signals = []
        for observer in self._action_surface_observers:
            try:
                signals.append(observer.evaluate("observe => observe()"))
            except Exception:
                continue
        if "confirmation_pending" in signals or signals.count("confirmation_required") > 1:
            return ""
        if "confirmation_required" in signals:
            return "confirmation_required"
        if "foreground_closed" in signals:
            return "foreground_closed"
        if action == "workflow_panel.click":
            return ""
        if "popup_reference_ready" in signals and "popup_reference_pending" not in signals:
            return "popup_reference_ready"
        before = self._action_completion_state
        if not before:
            return ""
        current = self._capture_action_completion_state()
        before_foreground = before.get("foreground_signature", before.get("foreground"))
        current_foreground = current.get("foreground_signature", current.get("foreground"))
        foreground_identity = str(self._action_completion_context.get("foreground_identity") or "").strip()
        if (
            foreground_identity
            and before.get("foreground_signature")
            and current.get("foreground_signature")
            and current_foreground != before_foreground
            and foreground_identity in str(current_foreground)
        ):
            return "foreground_state"
        if action == "tab.click":
            target_label = str(self._action_completion_context.get("tab") or "").strip()
            target_fieldid = str(self._action_completion_context.get("tab_fieldid") or "").strip()
            before_step_active = before.get("target_step_active")
            current_step_active = current.get("target_step_active")
            if before_step_active is not None or current_step_active is not None:
                if before_step_active is False and current_step_active is True:
                    return "tab_active"
                if before_step_active is True and current_step_active is True:
                    return "tab_already_active"
                return ""
            current_tab_ids = str(current.get("active_tab_ids") or "")
            before_tab_ids = str(before.get("active_tab_ids") or "")
            current_tab_id_values = set(filter(None, current_tab_ids.split("|")))
            before_tab_id_values = set(filter(None, before_tab_ids.split("|")))
            current_target_id_active = bool(target_fieldid and target_fieldid in current_tab_id_values)
            before_target_id_active = bool(target_fieldid and target_fieldid in before_tab_id_values)
            current_matches = (target_label and target_label in str(current.get("active_tabs") or "")) or (
                current_target_id_active
            )
            before_matches = (target_label and target_label in str(before.get("active_tabs") or "")) or (
                before_target_id_active
            )
            if current_target_id_active and before_target_id_active:
                return "tab_already_active"
            if current_matches and not before_matches:
                return "tab_active"
        if action == "query.search":
            context = self._action_completion_context
            if not context.get("target_table_fieldid"):
                return ""
            target_changed = current.get("target_table") != before.get("target_table")
            current_busy = int(current.get("target_busy") or 0)
            before_busy = int(before.get("target_busy") or 0)
            if current_busy > 0 or before_busy > 0:
                self._action_completion_seen_busy = True
            if target_changed or (
                self._action_completion_seen_busy and current_busy == 0
            ):
                return "target_component"
            responses = getattr(self, "_query_completion_requests", {})
            if (current.get("target_ready") and current_busy == 0 and responses
                    and all(success is True for _, success in responses.values())):
                return "target_component"
        return ""

    def _capture_action_completion_state(self) -> dict[str, Any]:
        foreground: list[str] = []
        foreground_signatures: list[str] = []
        active_tabs: list[str] = []
        active_tab_ids: list[str] = []
        tables: list[str] = []
        target_tables: list[str] = []
        busy = 0
        target_busy = 0
        target_step_states: list[bool] = []
        target_step_count = 0
        target_frames = []
        target_ready = False
        target_table_fieldid = str(self._action_completion_context.get("target_table_fieldid") or "").strip()
        target_table_token = str(self._action_completion_context.get("target_table_token") or "")
        target_tab_fieldid = str(self._action_completion_context.get("tab_fieldid") or "").strip()
        for frame in self._require_page().frames:
            try:
                state = dict(
                    frame.evaluate(
                        """({ targetTableFieldid, targetTableToken, targetTabFieldid }) => {
                            const visible = (node) => {
                              if (!node) return false;
                              const style = window.getComputedStyle(node);
                              const rect = node.getBoundingClientRect();
                              return style.display !== 'none' && style.visibility !== 'hidden'
                                && rect.width > 0 && rect.height > 0;
                            };
                            const text = (nodes) => Array.from(nodes).filter(visible)
                              .map((node) => String(node.innerText || node.textContent || '').replace(/\\s+/g, ' ').trim())
                              .filter(Boolean).join('|').slice(0, 1200);
                            const foregroundNodes = Array.from(document.querySelectorAll(
                              '.ant-modal-wrap, .ant-drawer-content-wrapper, .wui-modal, .w-drawer, [role="dialog"]'
                            )).filter(visible);
                            const tableRoots = Array.from(document.querySelectorAll(
                              'table, .ant-table, .wui-table, .w-table, [role="grid"], [role="table"], [class*="table"], [class*="Table"]'
                            ));
                            const targetRoots = targetTableToken
                              ? Array.from(document.querySelectorAll('[data-ydf-table-scope-token]'))
                                .filter(root => String(root.getAttribute('data-ydf-table-scope-token') || '').split(' ').includes(targetTableToken))
                              : targetTableFieldid
                              ? tableRoots.filter((root) => Array.from(root.querySelectorAll('[fieldid], [data-fieldid]'))
                                .some((node) => String(node.getAttribute('fieldid') || node.getAttribute('data-fieldid') || '') === targetTableFieldid)
                                || String(root.getAttribute('fieldid') || root.getAttribute('data-fieldid') || '') === targetTableFieldid)
                              : [];
                            const targetBodies = targetRoots.flatMap((root) => Array.from(root.querySelectorAll(
                              'tbody, .ant-table-tbody, .wui-table-tbody, .w-table-tbody, [role="rowgroup"]'
                            ))).filter(visible);
                            const targetBusyNodes = targetRoots.flatMap((root) => Array.from(root.querySelectorAll(
                              '[aria-busy="true"], .ant-spin-spinning, .wui-spin-spinning, .w-spin-spinning'
                            ))).filter(visible);
                            const targetIdentities = targetTableToken ? targetRoots.filter(visible)
                              : Array.from(document.querySelectorAll('[fieldid], [data-fieldid]'))
                              .filter(node => visible(node) && targetTableFieldid && String(
                                node.getAttribute('fieldid') || node.getAttribute('data-fieldid') || ''
                              ) === targetTableFieldid);
                            const targetRows = targetBodies.flatMap(body => Array.from(body.querySelectorAll('tr, [role="row"]')));
                            const targetReady = targetRows.some(row => visible(row)
                              && !row.matches('.wui-table-placeholder, .ant-table-placeholder')
                              && !/暂无数据|无数据|No data|加载中|点击上方查询条件搜索数据/i.test(row.textContent || '')
                              && Array.from(row.querySelectorAll('td, [role="gridcell"], [role="cell"]'))
                                .some(cell => visible(cell) && String(cell.textContent || '').trim()))
                              || targetRoots.some(root => Array.from(root.querySelectorAll(
                                '.wui-table-placeholder, .ant-table-placeholder, .wui-empty, .ant-empty'
                              )).some(node => visible(node) && /暂无数据|无数据|No data/i.test(node.textContent || '')));
                            const targetStepNodes = targetTabFieldid
                              ? Array.from(document.querySelectorAll('.wui-steps-item-wrap'))
                                .filter((node) => visible(node))
                                .filter((node) => String(
                                  node.getAttribute('fieldid') || node.getAttribute('data-fieldid') || ''
                                ) === targetTabFieldid)
                              : [];
                            const targetStepActive = targetStepNodes.length === 1
                              ? Boolean(
                                targetStepNodes[0].matches('.wui-steps-item-process')
                                || targetStepNodes[0].querySelector('.wui-steps-item-process')
                              )
                              : null;
                            return {
                              foreground: text(foregroundNodes),
                              foreground_signature: foregroundNodes.map((node) => {
                                const title = node.querySelector(
                                  '.ant-modal-title, .wui-modal-title, .w-modal-title, [role="heading"]'
                                );
                                return [
                                  node.id || '',
                                  node.getAttribute('role') || '',
                                  String(node.className || ''),
                                  String(title?.textContent || '').replace(/\\s+/g, ' ').trim()
                                ].join(':');
                              }).join('|'),
                              active_tabs: text(document.querySelectorAll(
                                '[role="tab"][aria-selected="true"], .ant-tabs-tab-active, .wui-tabs-tab-active, .w-tabs-tab-active'
                              )),
                              active_tab_ids: Array.from(document.querySelectorAll(
                                '[role="tab"][aria-selected="true"], .ant-tabs-tab-active, .wui-tabs-tab-active, .w-tabs-tab-active'
                              )).map((node) => String(node.getAttribute('fieldid') || node.getAttribute('data-fieldid') || '')).filter(Boolean).join('|'),
                              table: text(document.querySelectorAll(
                                'table tbody, .ant-table-tbody, .wui-table-tbody, .w-table-tbody'
                              )),
                              target_table: text(targetBodies),
                              target_busy: targetBusyNodes.length,
                              target_present: targetIdentities.length === 1,
                              target_ready: targetReady,
                              target_step_active: targetStepActive,
                              target_step_count: targetStepNodes.length,
                              busy: Array.from(document.querySelectorAll(
                                '[aria-busy="true"], .ant-spin-spinning, .wui-spin-spinning, .w-spin-spinning'
                              )).filter(visible).length
                            };
                          }""",
                        {
                            "targetTableFieldid": target_table_fieldid,
                            "targetTableToken": target_table_token,
                            "targetTabFieldid": target_tab_fieldid,
                        },
                    )
                    or {}
                )
            except Exception:
                continue
            if state.get("foreground"):
                foreground.append(str(state["foreground"]))
            if state.get("foreground_signature"):
                foreground_signatures.append(f"{frame.url}::{state['foreground_signature']}")
            if state.get("active_tabs"):
                active_tabs.append(str(state["active_tabs"]))
            if state.get("active_tab_ids"):
                active_tab_ids.append(str(state["active_tab_ids"]))
            if state.get("table"):
                tables.append(str(state["table"]))
            if state.get("target_table"):
                target_tables.append(str(state["target_table"]))
            if state.get("target_present"):
                target_frames.append(frame)
                target_ready = target_ready or bool(state.get("target_ready"))
            if isinstance(state.get("target_step_active"), bool):
                target_step_states.append(state["target_step_active"])
            try:
                target_step_count += int(state.get("target_step_count") or 0)
            except (TypeError, ValueError):
                pass
            busy += int(state.get("busy") or 0)
            target_busy += int(state.get("target_busy") or 0)
        self._query_completion_frame = target_frames[0] if len(target_frames) == 1 else None
        return {
            "foreground": "|".join(foreground),
            "foreground_signature": "|".join(foreground_signatures),
            "active_tabs": "|".join(active_tabs),
            "active_tab_ids": "|".join(active_tab_ids),
            "table": "|".join(tables),
            "target_table": "|".join(target_tables),
            "busy": busy,
            "target_busy": target_busy,
            "target_ready": len(target_frames) == 1 and target_ready,
            "target_step_active": target_step_states[0] if target_step_count == 1 and len(target_step_states) == 1 else None,
        }

    def close_notification(
        self,
        *,
        expected_type: str = "",
        contains: str = "",
        equals: str = "",
        message: str = "",
        label: str = "",
    ) -> dict[str, Any]:
        page = self._require_page()
        payload = {
            "expectedType": expected_type,
            "contains": contains,
            "equals": equals,
            "message": message,
            "label": label,
        }
        result = dict(page.evaluate(_NOTIFICATION_CLOSE_SCRIPT, payload) or {})
        if not result.get("closed"):
            raise RuntimeError(_notification_close_error_message(payload, result))
        close_selector = str(result.get("close_selector") or "").strip()
        if close_selector:
            try:
                page.locator(close_selector).first.click(timeout=1500)
            except Exception as exc:
                close_action = str(result.get("close_action") or "").strip()
                action_text = f" close_action={close_action}" if close_action else ""
                raise RuntimeError(
                    "页面提示关闭入口点击失败: "
                    f"expected={_notification_expectation_text(payload)} selector={close_selector}{action_text} "
                    f"error={exc}"
                ) from exc
        page.wait_for_timeout(300)
        closed_notification = dict(result.get("closed_notification") or {})
        try:
            remaining = self._scan_notifications()
        except Exception:
            remaining = result.get("remaining_notifications")
        if not isinstance(remaining, list):
            remaining = []
        still_visible = [
            item
            for item in remaining
            if _runtime_notification_matches(
                item,
                expected_type=expected_type,
                contains=contains,
                equals=equals,
                message=message,
            )
        ]
        if still_visible:
            close_action = str(result.get("close_action") or "").strip()
            action_text = f" close_action={close_action}" if close_action else ""
            raise RuntimeError(
                "页面提示关闭后仍可见: "
                f"expected={_notification_expectation_text(payload)} actual={still_visible}{action_text}"
            )
        return {
            "closed_notification": closed_notification,
            "remaining_notifications": list(remaining),
            "close_action": str(result.get("close_action") or ""),
        }

    def wait_after_action(self) -> None:
        self._wait_ready()

    def fill_field(self, bound_element: BoundElement, value: str) -> None:
        locator = self._resolve_fill_locator(bound_element.runtime.selector)
        locator.fill(str(value))

    def fill_form_field(self, bound_element: BoundElement, value: Any) -> dict[str, Any] | None:
        root = self._resolve_visible_locator(bound_element.runtime.selector)
        runtime_only_root = self._resolve_runtime_only_form_field_root(bound_element)
        runtime_only_resolved = False
        if runtime_only_root is not None:
            root = runtime_only_root
            runtime_only_resolved = True
        candidate = getattr(bound_element, "candidate", None)
        raw_candidate = getattr(candidate, "raw", None)
        runtime_only = isinstance(raw_candidate, dict) and bool(raw_candidate.get("runtime_only"))
        runtime_fieldid = str(getattr(bound_element.runtime, "fieldid", "") or "").strip()
        popup_reference_field = self._popup_reference_module().looks_like_field(root, bound_element)
        if runtime_only and not _candidate_raw_claims_reference(raw_candidate) and not re.search(
            r"(?:^|_)input(?:_search)?_input$", runtime_fieldid
        ) and not self._popup_reference_module().target_is_structured(value):
            popup_reference_field = False
        foreground_root = None
        if popup_reference_field and not runtime_only_resolved:
            try:
                foreground_root = self._resolve_foreground_form_field_root(bound_element)
            except Exception:
                foreground_root = None
        if not runtime_only_resolved:
            if foreground_root is None:
                try:
                    foreground_root = self._resolve_pointer_receiving_form_field_root(bound_element)
                except Exception:
                    foreground_root = None
        if foreground_root is None and not runtime_only_resolved and not bool(
            getattr(bound_element.runtime, "in_dialog", False)
        ):
            try:
                foreground_root = self._resolve_foreground_form_field_root(bound_element)
            except Exception:
                foreground_root = None
        if popup_reference_field:
            for _ in range(12):
                foreground_root = foreground_root or self._resolve_foreground_form_field_root(bound_element)
                if foreground_root is None:
                    narrowed_root = self._narrow_form_field_root(root, bound_element)
                    if narrowed_root is not root:
                        foreground_root = narrowed_root
                if foreground_root is None:
                    position_root = self._resolve_form_field_root_by_label_position(bound_element)
                    if position_root is not None and self._popup_reference_module().root_has_trigger(position_root):
                        foreground_root = position_root
                if foreground_root is not None:
                    break
                self._require_page().wait_for_timeout(250)
        initial_root = root
        if runtime_only_resolved:
            field_root = root
        elif foreground_root is None and self._has_precise_form_field_binding(bound_element):
            field_root = root
        else:
            field_root = foreground_root or self._narrow_form_field_root(root, bound_element)
        root = field_root
        if self._looks_like_switch_field(root, bound_element):
            self._set_switch_field_value(root, value)
            return
        if self._looks_like_radio_field(root, bound_element):
            self._set_radio_field_value(root, value)
            return
        fill_locator = None
        if not popup_reference_field:
            fill_locator = (
                self._resolve_fill_locator_from_root(field_root)
                if field_root is not initial_root
                else self._resolve_fill_locator(bound_element.runtime.selector)
            )
        if self._looks_like_date_range_field(bound_element):
            return self._set_date_range_field_value(root, fill_locator, str(value), bound_element)
        if self._looks_like_date_field(bound_element):
            self._set_date_field_value(fill_locator, str(value))
            return self._confirm_plain_field_value(fill_locator, value, bound_element)
        _ensure_table_reference_target_uses_match(
            candidate,
            value,
            target_has_selection=self._popup_reference_module().target_has_explicit_selection(value),
        )
        runtime_only_text = (
            runtime_only
            and not _candidate_raw_claims_reference(raw_candidate)
            and not re.search(r"(?:^|_)input(?:_search)?_input$", runtime_fieldid)
        )
        choice_field = not popup_reference_field and self._looks_like_choice_field(root, bound_element)
        plain_choice_field = (
            not _candidate_component_claims_modal_reference(candidate)
            and not popup_reference_field
            and choice_field
        )
        multi_select_choice = plain_choice_field and self._choice_field_is_multi_select(root, candidate)
        if not multi_select_choice and self._popup_reference_module().is_scalar_target(value):
            committed = popup_reference_field or (
                choice_field and self._choice_root_committed_value_matches(root, str(value))
            )
            if committed:
                actual = self._read_field_value_from_container(bound_element)
                if self._popup_reference_module().value_matches(actual, value):
                    return {"actual": actual, "confirmed": True, "skipped": True}
        if plain_choice_field:
            return self._select_choice_for_field(
                root,
                fill_locator,
                value,
                candidate=candidate,
                require_value_match=True,
            )
        if popup_reference_field:
            props = raw_candidate.get("props", {}) if isinstance(raw_candidate, dict) else {}
            if (
                getattr(candidate, "component_name", "") == "YDFReferSelect"
                and isinstance(props, dict)
                and props.get("referType") in ("uidata", "link")
                and str(props.get("caninput", "")).lower() in ("1", "true")
                and self._popup_reference_module().is_scalar_target(value)
            ):
                fill_locator = self._resolve_fill_locator_from_root(field_root)
                fill_locator.fill(str(value))
                fill_locator.press("Tab")
                return self._confirm_plain_field_value(fill_locator, value, bound_element)
            if runtime_only_text and self._popup_reference_module().is_scalar_target(value):
                fill_locator = (
                    self._resolve_fill_locator_from_root(field_root)
                    if field_root is not initial_root
                    else self._resolve_fill_locator(bound_element.runtime.selector)
                )
                self._set_text_field_value(fill_locator, str(value))
                return self._confirm_plain_field_value(fill_locator, value, bound_element)
            identity = ReferenceOwnerIdentity.from_locator(
                root,
                fieldid=str(getattr(bound_element.candidate, "fieldid", "") or ""),
                label=str(getattr(bound_element.candidate, "label", "") or ""),
                contract_verified=_bound_element_has_verified_form_identity(bound_element),
                fallback_selector=bound_element.runtime.selector,
            )
            result = self._popup_reference_module().select(
                PopupReferenceRequest.from_bound_target(
                    source_kind="form",
                    identity=identity,
                    target=value,
                )
            ).to_runtime_dict()
            return result or None
        if self._looks_like_choice_field(root, bound_element):
            return self._select_choice_for_field(
                root,
                fill_locator,
                value,
                candidate=candidate,
                require_value_match=True,
            )
        if self._popup_reference_module().wants_first_available(value):
            raise RuntimeError("first_available 仅支持下拉、树下拉或弹出参照字段")
        self._set_text_field_value(fill_locator, str(value))
        return self._confirm_plain_field_value(fill_locator, value, bound_element)

    def _confirm_plain_field_value(self, locator, value: Any, bound_element: BoundElement) -> dict[str, Any]:
        expected = str(value)
        actual = ""
        date_field = self._looks_like_date_field(bound_element)
        for _ in range(16):
            actual = (
                _normalize_plain_field_value(locator.input_value(timeout=200))
                if date_field
                else self._read_plain_fill_value(locator)
            )
            if _plain_field_value_matches(actual, expected):
                return {
                    "actual": actual,
                    "selector": bound_element.runtime.selector,
                    "confirmed": True,
                    "in_dialog": bool(getattr(bound_element.runtime, "in_dialog", False)),
                }
            try:
                self._require_page().wait_for_timeout(100)
            except Exception:
                break
        candidate = getattr(bound_element, "candidate", None)
        label = str(getattr(candidate, "label", "") or getattr(candidate, "fieldid", "") or "")
        selector = str(getattr(bound_element.runtime, "selector", "") or "")
        raise RuntimeError(
            f"字段录入后未回填: field={label}, expected={expected!r}, actual={actual!r}, selector={selector}"
        )

    def _read_plain_fill_value(self, locator) -> str:
        for method_name in ("input_value", "text_content"):
            method = getattr(locator, method_name, None)
            if method is None:
                continue
            try:
                value = method(timeout=200)
            except TypeError:
                try:
                    value = method()
                except Exception:
                    value = ""
            except Exception:
                value = ""
            value = _normalize_plain_field_value(value)
            if value:
                return value
        get_attribute = getattr(locator, "get_attribute", None)
        if get_attribute is not None:
            try:
                return _normalize_plain_field_value(get_attribute("title", timeout=200))
            except TypeError:
                try:
                    return _normalize_plain_field_value(get_attribute("title"))
                except Exception:
                    return ""
            except Exception:
                return ""
        return ""

    def _resolve_runtime_only_form_field_root(self, bound_element: BoundElement):
        candidate = getattr(bound_element, "candidate", None)
        raw = getattr(candidate, "raw", {}) if candidate is not None else {}
        if not isinstance(raw, dict) or not raw.get("runtime_only"):
            return None
        selector = str(getattr(getattr(bound_element, "runtime", None), "selector", "") or "").strip()
        if selector:
            if getattr(getattr(bound_element, "runtime", None), "pointer_receivable", None) is not False:
                try:
                    resolved = self._resolve_visible_locator(selector)
                except Exception:
                    resolved = None
                if resolved is not None:
                    return resolved
        for resolver in (
            self._resolve_form_field_root_by_label_position,
            self._resolve_foreground_form_field_root,
        ):
            try:
                resolved = resolver(bound_element)
            except Exception:
                resolved = None
            if resolved is not None:
                return resolved
        return None

    def _resolve_pointer_receiving_form_field_root(self, bound_element: BoundElement):
        candidate = getattr(bound_element, "candidate", None)
        identities = [
            str(getattr(candidate, "fieldid", "") or "").strip(),
            str(getattr(candidate, "data_field", "") or "").strip(),
        ]
        selectors = [str(getattr(bound_element.runtime, "selector", "") or "").strip()]
        for identity in identities:
            if identity:
                selectors.append(_fieldid_selector(identity))
        key = str(getattr(candidate, "key", "") or "").strip()
        if key:
            escaped = key.replace("\\", "\\\\").replace('"', '\\"')
            selectors.append(f'[uikey="{escaped}"]')
        for selector in dict.fromkeys(item for item in selectors if item):
            for context in self._all_search_contexts():
                locator = context.locator(selector)
                for index in range(min(locator.count(), 20)):
                    root = locator.nth(index)
                    if not root.is_visible(timeout=300):
                        continue
                    fill_locator = self._resolve_fill_locator_from_root(root)
                    if self._receives_pointer_events(fill_locator):
                        return root
        return None

    def _set_text_field_value(self, locator, value: str) -> None:
        locator.click(timeout=1000)
        try:
            locator.press("Meta+A", timeout=1000)
            locator.press("Control+A", timeout=1000)
            locator.press("Backspace", timeout=1000)
            locator.type(value, delay=10)
        except Exception:
            locator.fill(value)
        try:
            locator.evaluate(
                """(node, value) => {
                    const tag = String(node.tagName || '').toUpperCase();
                    const proto = tag === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
                    const descriptor = Object.getOwnPropertyDescriptor(proto, 'value');
                    if (node.isContentEditable) {
                        node.textContent = value;
                    } else if (descriptor && descriptor.set) {
                        descriptor.set.call(node, value);
                        node.defaultValue = value;
                        node.textContent = value;
                        node.setAttribute('title', value);
                    } else {
                        node.value = value;
                        node.defaultValue = value;
                        node.textContent = value;
                        node.setAttribute('title', value);
                    }
                    for (const eventName of ['input', 'change', 'blur']) {
                        const event = eventName === 'input' && typeof InputEvent !== 'undefined'
                            ? new InputEvent(eventName, { bubbles: true, inputType: 'insertText', data: value })
                            : new Event(eventName, { bubbles: true });
                        node.dispatchEvent(event);
                    }
                }""",
                value,
            )
        except Exception:
            pass
        try:
            locator.press("Tab", timeout=1000)
        except Exception:
            try:
                locator.press("Enter", timeout=1000)
            except Exception:
                pass

    def _looks_like_radio_field(self, locator, bound_element: BoundElement) -> bool:
        runtime = bound_element.runtime
        candidate = getattr(bound_element, "candidate", None)
        component_name = str(getattr(candidate, "component_name", "") or getattr(runtime, "name", "") or "")
        normalized_component = component_name.lower().replace("-", "").replace("_", "")
        runtime_role = str(getattr(runtime, "role", "") or "").lower()
        if "radio" in normalized_component or runtime_role == "radio":
            return True
        runtime_tag = str(getattr(runtime, "tag_name", "") or "").lower()
        if normalized_component:
            if any(token in normalized_component for token in ("select", "refer", "reference", "ref", "switch")):
                return False
            if normalized_component in {"ydfinput", "ydftextarea", "ydfinputnumber", "ydfdatepicker"}:
                return False
        if runtime_role in {"combobox", "listbox", "switch"} or runtime_tag == "select":
            return False
        try:
            return bool(
                locator.evaluate(
                    """(node) => {
                        const visible = (el) => {
                          const style = window.getComputedStyle(el);
                          const rect = el.getBoundingClientRect();
                          return style && style.visibility !== 'hidden' && style.display !== 'none'
                            && rect.width > 0 && rect.height > 0;
                        };
                        const radioSelector = [
                          'input[type="radio"]',
                          '[role="radio"]',
                          '.wui-radio-wrapper',
                          '.ant-radio-wrapper',
                          '.u-radio-wrapper',
                          '[class*="radio-wrapper"]',
                          '[class*="RadioWrapper"]'
                        ].join(',');
                        const textInputSelector = [
                          'input:not([type="hidden"]):not([type="radio"]):not([type="checkbox"])',
                          'textarea',
                          'select',
                          '[contenteditable="true"]',
                          '[role="textbox"]',
                          '[role="combobox"]'
                        ].join(',');
                        const radios = Array.from(node.querySelectorAll(radioSelector)).filter((el) => {
                          if (el.matches('input[type="radio"]')) return true;
                          return visible(el);
                        });
                        if (!radios.length) return false;
                        return !Array.from(node.querySelectorAll(textInputSelector)).some(visible);
                    }"""
                )
            )
        except Exception:
            return False

    def _looks_like_checkbox_field(self, locator, bound_element: BoundElement) -> bool:
        runtime = bound_element.runtime
        candidate = getattr(bound_element, "candidate", None)
        component_name = str(getattr(candidate, "component_name", "") or getattr(runtime, "name", "") or "")
        normalized_component = component_name.lower().replace("-", "").replace("_", "")
        runtime_role = str(getattr(runtime, "role", "") or "").lower()
        runtime_tag = str(getattr(runtime, "tag_name", "") or "").lower()
        if any(token in normalized_component for token in ("switch", "radio", "select", "refer", "reference")):
            return False
        if runtime_role in {"switch", "radio", "combobox", "listbox"} or runtime_tag == "select":
            return False
        if "checkbox" in normalized_component or runtime_role == "checkbox":
            return True
        probe = (
            f"{getattr(runtime, 'selector', '')} {getattr(runtime, 'name', '') or ''} "
            f"{getattr(runtime, 'text', '') or ''} {getattr(runtime, 'label_text', '') or ''}"
        ).lower()
        if "checkbox" in probe:
            return True
        try:
            return bool(
                locator.evaluate(
                    """(node) => {
                        const visible = (el) => {
                          const style = window.getComputedStyle(el);
                          const rect = el.getBoundingClientRect();
                          return style && style.visibility !== 'hidden' && style.display !== 'none'
                            && rect.width > 0 && rect.height > 0;
                        };
                        const checkboxSelector = [
                          'input[type="checkbox"]',
                          '[role="checkbox"]',
                          '.wui-checkbox',
                          '.ant-checkbox',
                          '.u-checkbox',
                          '.w-checkbox',
                          '[class*="checkbox"]',
                          '[class*="Checkbox"]'
                        ].join(',');
                        const textInputSelector = [
                          'input:not([type="hidden"]):not([type="radio"]):not([type="checkbox"])',
                          'textarea',
                          'select',
                          '[contenteditable="true"]',
                          '[role="textbox"]',
                          '[role="combobox"]'
                        ].join(',');
                        const isSwitchLike = (el) => {
                          const role = String(el.getAttribute && el.getAttribute('role') || '').toLowerCase();
                          const className = String(el.className || '').toLowerCase();
                          return role === 'switch' || /switch/i.test(className);
                        };
                        const checkboxes = Array.from(node.querySelectorAll(checkboxSelector)).filter((el) => {
                          if (isSwitchLike(el)) return false;
                          if (el.matches('input[type="checkbox"]')) return true;
                          return visible(el);
                        });
                        if (!checkboxes.length) return false;
                        return !Array.from(node.querySelectorAll(textInputSelector)).some(visible);
                    }"""
                )
            )
        except Exception:
            return False

    def _set_radio_field_value(self, root, value: Any) -> None:
        selection = self._mark_radio_field_option(root, value)
        if not selection.get("found"):
            raise RuntimeError(f"未找到单选控件选项: {value!r}")
        if selection.get("selected"):
            return
        selector = str(selection.get("selector") or "")
        clicked = False
        if selector:
            try:
                root.locator(selector).click(timeout=1500)
                clicked = True
            except Exception:
                clicked = False
        if not clicked:
            try:
                clicked = bool(
                    root.evaluate(
                        """(node, selector) => {
                            const target = selector ? node.querySelector(selector) : null;
                            if (!target) return false;
                            target.click();
                            return true;
                        }""",
                        selector,
                    )
                )
            except Exception:
                clicked = False
        if not clicked:
            try:
                root.click(timeout=1000)
                clicked = True
            except Exception:
                clicked = False
        if not clicked:
            raise RuntimeError(f"无法点击单选控件选项: {value!r}")
        try:
            self._require_page().wait_for_timeout(300)
        except Exception:
            pass
        updated = self._mark_radio_field_option(root, value)
        if updated.get("found") and not updated.get("selected"):
            raise RuntimeError(f"单选控件未切换到目标值: {value!r}")

    def _mark_radio_field_option(self, root, value: Any) -> dict[str, Any]:
        marker = f"ydf-radio-target-{int(time.time() * 1000)}"
        try:
            result = root.evaluate(
                """(node, args) => {
                    const normalize = (text) => String(text || '').replace(/\\s+/g, ' ').trim();
                    const compact = (text) => normalize(text).replace(/\\s+/g, '').toLowerCase();
                    const visible = (el) => {
                      const style = window.getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style && style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width > 0 && rect.height > 0;
                    };
                    const aliasesFor = (value) => {
                      const wanted = compact(value);
                      const truthy = new Set(['是', '启用', '启用中', '开启', '打开', '开', 'true', '1', 'yes', 'y', 'on']);
                      const falsy = new Set(['否', '停用', '未启用', '禁用', '关闭', '关', 'false', '0', 'no', 'n', 'off']);
                      const aliases = new Set([wanted]);
                      if (truthy.has(wanted)) ['是', '1', 'true', 'yes', 'y', 'on'].forEach((item) => aliases.add(compact(item)));
                      if (falsy.has(wanted)) ['否', '0', 'false', 'no', 'n', 'off'].forEach((item) => aliases.add(compact(item)));
                      return aliases;
                    };
                    const wantedAliases = aliasesFor(args.value);
                    const optionSelector = [
                      'label',
                      '[role="radio"]',
                      '.wui-radio-wrapper',
                      '.ant-radio-wrapper',
                      '.u-radio-wrapper',
                      '[class*="radio-wrapper"]',
                      '[class*="RadioWrapper"]',
                      'input[type="radio"]'
                    ].join(',');
                    const wrapperSelector = [
                      'label',
                      '[role="radio"]',
                      '.wui-radio-wrapper',
                      '.ant-radio-wrapper',
                      '.u-radio-wrapper',
                      '[class*="radio-wrapper"]',
                      '[class*="RadioWrapper"]'
                    ].join(',');
                    const inputOf = (option) => {
                      if (!option) return null;
                      if (option.matches && option.matches('input[type="radio"]')) return option;
                      return option.querySelector && option.querySelector('input[type="radio"]');
                    };
                    const optionRootOf = (input) => {
                      if (!input) return null;
                      return input.closest(wrapperSelector) || input.closest('label') || input.parentElement || input;
                    };
                    const textPartsFor = (option) => {
                      const input = inputOf(option);
                      const parts = [
                        option.getAttribute && option.getAttribute('title'),
                        option.getAttribute && option.getAttribute('aria-label'),
                        option.innerText,
                        option.textContent,
                      ];
                      if (input) {
                        const id = input.getAttribute('id');
                        const explicitLabel = id ? node.querySelector(`label[for="${CSS.escape(id)}"]`) : null;
                        parts.push(
                          input.value,
                          input.getAttribute('value'),
                          input.getAttribute('title'),
                          input.getAttribute('aria-label'),
                          explicitLabel && (explicitLabel.innerText || explicitLabel.textContent),
                          input.nextElementSibling && (input.nextElementSibling.innerText || input.nextElementSibling.textContent)
                        );
                      }
                      return parts.map(normalize).filter(Boolean);
                    };
                    const optionMatches = (option) => {
                      for (const text of textPartsFor(option)) {
                        if (wantedAliases.has(compact(text))) return true;
                      }
                      return false;
                    };
                    const selected = (option) => {
                      const input = inputOf(option);
                      if (input && input.checked) return true;
                      const aria = String(option.getAttribute && option.getAttribute('aria-checked') || '').toLowerCase();
                      if (['true', '1', 'checked'].includes(aria)) return true;
                      const className = String(option.className || '').toLowerCase();
                      return /(^|[-_\\s])(checked|selected|active)([-_\\s]|$)/.test(className);
                    };
                    const options = [];
                    for (const input of Array.from(node.querySelectorAll('input[type="radio"]'))) {
                      const optionRoot = optionRootOf(input);
                      if (optionRoot && !options.includes(optionRoot)) options.push(optionRoot);
                      if (!options.includes(input)) options.push(input);
                    }
                    for (const option of Array.from(node.querySelectorAll(optionSelector))) {
                      if ((option.matches('input[type="radio"]') || visible(option)) && !options.includes(option)) {
                        options.push(option);
                      }
                    }
                    const target = options.find(optionMatches);
                    if (!target) return { found: false, selected: false, selector: '' };
                    for (const item of Array.from(node.querySelectorAll(`[data-ydf-browser-radio-target="${args.marker}"]`))) {
                      item.removeAttribute('data-ydf-browser-radio-target');
                    }
                    const input = inputOf(target);
                    const clickTarget = visible(target) ? target : input || target;
                    clickTarget.setAttribute('data-ydf-browser-radio-target', args.marker);
                    return {
                      found: true,
                      selected: selected(target) || (input ? selected(input) : false),
                      selector: `[data-ydf-browser-radio-target="${args.marker}"]`
                    };
                }""",
                {"value": str(value), "marker": marker},
            )
        except Exception:
            return {"found": False, "selected": False, "selector": ""}
        if isinstance(result, dict):
            return result
        return {"found": False, "selected": False, "selector": ""}

    def _read_radio_field_value(self, root) -> str:
        try:
            value = root.evaluate(
                """(node) => {
                    const normalize = (text) => String(text || '').replace(/\\s+/g, ' ').trim();
                    const visible = (el) => {
                      const style = window.getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style && style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width > 0 && rect.height > 0;
                    };
                    const wrapperSelector = [
                      'label',
                      '[role="radio"]',
                      '.wui-radio-wrapper',
                      '.ant-radio-wrapper',
                      '.u-radio-wrapper',
                      '[class*="radio-wrapper"]',
                      '[class*="RadioWrapper"]'
                    ].join(',');
                    const optionRootOf = (input) => input.closest(wrapperSelector) || input.closest('label') || input.parentElement || input;
                    const textOf = (option, input) => {
                      const id = input && input.getAttribute('id');
                      const explicitLabel = id ? node.querySelector(`label[for="${CSS.escape(id)}"]`) : null;
                      const parts = [
                        option && option.getAttribute && option.getAttribute('title'),
                        option && option.getAttribute && option.getAttribute('aria-label'),
                        option && option.innerText,
                        option && option.textContent,
                        explicitLabel && (explicitLabel.innerText || explicitLabel.textContent),
                        input && input.nextElementSibling && (input.nextElementSibling.innerText || input.nextElementSibling.textContent),
                        input && input.value,
                      ];
                      return parts.map(normalize).find(Boolean) || '';
                    };
                    for (const input of Array.from(node.querySelectorAll('input[type="radio"]'))) {
                      if (!input.checked) continue;
                      const option = optionRootOf(input);
                      return textOf(option, input);
                    }
                    for (const option of Array.from(node.querySelectorAll('[role="radio"], .wui-radio-wrapper, .ant-radio-wrapper, .u-radio-wrapper, [class*="radio-wrapper"], [class*="RadioWrapper"]'))) {
                      if (!visible(option)) continue;
                      const aria = String(option.getAttribute('aria-checked') || '').toLowerCase();
                      const className = String(option.className || '').toLowerCase();
                      if (['true', '1', 'checked'].includes(aria) || /(^|[-_\\s])(checked|selected|active)([-_\\s]|$)/.test(className)) {
                        return textOf(option, option.querySelector('input[type="radio"]'));
                      }
                    }
                    return '';
                }"""
            )
        except Exception:
            return ""
        return str(value or "").strip()

    def _read_checkbox_field_state(self, root) -> bool | None:
        try:
            state = root.evaluate(
                """(node) => {
                    const visible = (el) => {
                      const style = window.getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style && style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width > 0 && rect.height > 0;
                    };
                    const checkboxSelector = [
                      'input[type="checkbox"]',
                      '[role="checkbox"]',
                      '.wui-checkbox',
                      '.ant-checkbox',
                      '.u-checkbox',
                      '.w-checkbox',
                      '[class*="checkbox"]',
                      '[class*="Checkbox"]'
                    ].join(',');
                    const isSwitchLike = (el) => {
                      const role = String(el.getAttribute && el.getAttribute('role') || '').toLowerCase();
                      const className = String(el.className || '').toLowerCase();
                      return role === 'switch' || /switch/i.test(className);
                    };
                    const classTextOf = (el) => String([
                      el && el.className,
                      el && el.parentElement && el.parentElement.className,
                      el && el.closest && el.closest('label, [class*="checkbox"], [class*="Checkbox"]') && el.closest('label, [class*="checkbox"], [class*="Checkbox"]').className,
                    ].join(' ')).toLowerCase();
                    const parseState = (el) => {
                      if (!el) return null;
                      const tag = String(el.tagName || '').toUpperCase();
                      if (tag === 'INPUT' && String(el.type || '').toLowerCase() === 'checkbox') {
                        return Boolean(el.checked);
                      }
                      const aria = String(el.getAttribute && el.getAttribute('aria-checked') || '').toLowerCase();
                      if (['true', '1', 'checked'].includes(aria)) return true;
                      if (['false', '0', 'unchecked'].includes(aria)) return false;
                      if (aria === 'mixed') return null;
                      const classText = classTextOf(el);
                      if (/(^|\\s|_|-)(checked|is-checked)($|\\s|_|-)/.test(classText)) return true;
                      if (/(ant-checkbox-checked|wui-checkbox-checked|u-checkbox-checked|el-checkbox-checked)/.test(classText)) return true;
                      if (/(^|\\s|_|-)(unchecked|is-unchecked)($|\\s|_|-)/.test(classText)) return false;
                      return null;
                    };
                    const controls = [];
                    if (node.matches && node.matches(checkboxSelector) && !isSwitchLike(node)) controls.push(node);
                    for (const item of Array.from(node.querySelectorAll(checkboxSelector))) {
                      if (!isSwitchLike(item)) controls.push(item);
                    }
                    const candidates = controls.filter((el) => {
                      if (el.matches && el.matches('input[type="checkbox"]')) return true;
                      return visible(el);
                    });
                    if (!candidates.length) return null;
                    for (const item of candidates) {
                      const parsed = parseState(item);
                      if (parsed !== null) return parsed;
                    }
                    return false;
                }"""
            )
        except Exception:
            return None
        if state is None:
            return None
        return bool(state)

    def _has_precise_form_field_binding(self, bound_element: BoundElement) -> bool:
        reasons = {str(reason) for reason in (getattr(bound_element, "reasons", None) or [])}
        if reasons.intersection({"fieldid", "template_key", "id", "data_field", "data_field:name"}):
            return True
        candidate = getattr(bound_element, "candidate", None)
        runtime = getattr(bound_element, "runtime", None)
        if candidate is None or runtime is None:
            return False
        candidate_fieldid = str(getattr(candidate, "fieldid", "") or "")
        candidate_key = str(getattr(candidate, "key", "") or "")
        data_field = str(getattr(candidate, "data_field", "") or "")
        runtime_fieldid = str(getattr(runtime, "fieldid", "") or "")
        runtime_id = str(getattr(runtime, "id", "") or "")
        runtime_name = str(getattr(runtime, "name", "") or "")
        if candidate_fieldid and candidate_fieldid == runtime_fieldid:
            return True
        if candidate_key and candidate_key == runtime_fieldid:
            return True
        return bool(data_field and data_field in {runtime_id, runtime_name})

    def _looks_like_switch_field(self, locator, bound_element: BoundElement) -> bool:
        runtime = bound_element.runtime
        candidate = getattr(bound_element, "candidate", None)
        component_name = str(getattr(candidate, "component_name", "") or getattr(runtime, "name", "") or "")
        normalized_component = component_name.lower().replace("-", "").replace("_", "")
        runtime_role = getattr(runtime, "role", None)
        runtime_tag = getattr(runtime, "tag_name", None)
        if runtime_role in {"combobox", "listbox"} or runtime_tag == "select" or "select" in normalized_component:
            return False
        if "switch" in normalized_component:
            return True
        if runtime_role == "switch":
            return True
        if normalized_component in {"ydfinput", "ydftextarea", "ydfinputnumber"}:
            return False
        probe = (
            f"{getattr(runtime, 'selector', '')} {runtime_role or ''} "
            f"{runtime_tag or ''} {getattr(runtime, 'name', '') or ''}"
        ).lower()
        if "switch" in probe and "switcher" not in probe:
            return True
        try:
            return bool(
                locator.evaluate(
                    """(node) => {
                        const switchSelector = [
                          '[role="switch"]',
                          '.wui-switch',
                          '.ant-switch',
                          '.u-switch',
                          '[class*="Switch"]',
                          '[class*="switch"]'
                        ].join(',');
                        const text = [
                          node.className,
                          node.getAttribute && node.getAttribute('role'),
                          node.getAttribute && node.getAttribute('aria-checked')
                        ].join(' ');
                        const looksLikeSwitch = /switch/i.test(text) && !/switcher/i.test(text);
                        if (looksLikeSwitch) return true;
                        return Array.from(node.querySelectorAll(switchSelector)).some((el) => {
                          const className = String(el.className || '');
                          return !/switcher/i.test(className);
                        });
                    }"""
                )
            )
        except Exception:
            return False

    def _set_switch_field_value(self, root, value: Any) -> None:
        expected = self._coerce_switch_value(value)
        current = self._read_switch_field_state(root)
        if current is None:
            debug = self._collect_switch_field_debug(root)
            suffix = f": {debug}" if debug else ""
            raise RuntimeError(f"无法读取开关控件当前状态{suffix}")
        if current == expected:
            return
        self._click_switch_field(root)
        try:
            self._require_page().wait_for_timeout(300)
        except Exception:
            pass
        updated = self._read_switch_field_state(root)
        if updated is not None and updated != expected:
            debug = self._collect_switch_field_debug(root)
            suffix = f" | switch_debug={debug}" if debug else ""
            raise RuntimeError(f"开关控件状态未切换到目标值: expected={'是' if expected else '否'}{suffix}")

    def _coerce_switch_value(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in {0, 1}:
            return bool(value)
        text = "".join(str(value).strip().lower().split())
        truthy = {"是", "启用", "启用中", "开启", "打开", "开", "true", "1", "yes", "y", "on"}
        falsy = {"否", "停用", "未启用", "禁用", "关闭", "关", "false", "0", "no", "n", "off"}
        if text in truthy:
            return True
        if text in falsy:
            return False
        if text.startswith("1") and any(token in text for token in ("是", "启用", "开启", "打开")):
            return True
        if text.startswith("0") and any(token in text for token in ("否", "停用", "禁用", "关闭")):
            return False
        raise RuntimeError(f"开关控件只支持是否/true/false/1/0: {value!r}")

    def _read_switch_field_state(self, root) -> bool | None:
        try:
            state = root.evaluate(
                """(node) => {
                    const visible = (el) => {
                      const style = window.getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style && style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width > 0 && rect.height > 0;
                    };
                    const isDecorativeSwitchPart = (el) => {
                      const className = String(el && el.className || '');
                      return /switch-(inner|handle|thumb|knob|text|label)/i.test(className)
                        || /(^|[-_\\s])(inner|handle|thumb|knob)([-_\\s]|$)/i.test(className);
                    };
                    const isSwitchControl = (el) => {
                      if (!el || isDecorativeSwitchPart(el)) return false;
                      const tag = String(el.tagName || '').toUpperCase();
                      if (tag === 'INPUT' && String(el.type || '').toLowerCase() === 'checkbox') return true;
                      const role = String(el.getAttribute && el.getAttribute('role') || '').toLowerCase();
                      const className = String(el.className || '');
                      if (role === 'switch') return true;
                      if (/(^|\\s)(wui-switch|ant-switch|w-switch|u-switch)(\\s|$)/i.test(className)) return true;
                      const isSwitchContainer = /form-item|lcd-panel-item|wx-item|wui-row|wui-col/i.test(className);
                      return !isSwitchContainer && /switch/i.test(className) && !/switcher/i.test(className);
                    };
                    const parseState = (el) => {
                      if (!el) return null;
                      const tag = String(el.tagName || '').toUpperCase();
                      if (tag === 'INPUT' && String(el.type || '').toLowerCase() === 'checkbox') {
                        return Boolean(el.checked);
                      }
                      const role = String(el.getAttribute && el.getAttribute('role') || '').toLowerCase();
                      const className = String(el.className || '').toLowerCase();
                      const isSwitchLike = isSwitchControl(el) || role === 'switch';
                      for (const attr of ['aria-checked', 'aria-pressed', 'checked', 'data-checked', 'data-value', 'value']) {
                        const value = el.getAttribute && el.getAttribute(attr);
                        if (value == null || value === '') continue;
                        const normalized = String(value).trim().toLowerCase();
                        if (['true', '1', 'yes', 'on', 'checked', '是', '启用'].includes(normalized)) return true;
                        if (['false', '0', 'no', 'off', 'unchecked', '否', '停用'].includes(normalized)) return false;
                      }
                      if (/(^|[-_\\s])(checked|active|on|open|true)([-_\\s]|$)/.test(className)) return true;
                      if (/(^|[-_\\s])(unchecked|inactive|off|close|false)([-_\\s]|$)/.test(className)) return false;
                      if (isSwitchLike) return false;
                      return null;
                    };
                    const switchSelector = [
                      '[role="switch"]',
                      '.wui-switch',
                      '.ant-switch',
                      '.w-switch',
                      '.u-switch',
                      '[class*="Switch"]',
                      '[class*="switch"]',
                      'input[type="checkbox"]'
                    ].join(',');
                    const descendants = Array.from(node.querySelectorAll(switchSelector))
                      .filter((el) => {
                        return isSwitchControl(el) && (visible(el) || el.matches('input[type="checkbox"]'));
                      });
                    const rootIsSwitchLike = isSwitchControl(node);
                    const visibleControls = descendants.filter((el) => visible(el) && !el.matches('input[type="checkbox"]'));
                    const checkboxControls = descendants.filter((el) => el.matches('input[type="checkbox"]'));
                    const otherControls = descendants.filter((el) => !visibleControls.includes(el) && !checkboxControls.includes(el));
                    const nodes = rootIsSwitchLike
                      ? [node, ...visibleControls, ...checkboxControls, ...otherControls]
                      : [...visibleControls, ...checkboxControls, ...otherControls, node];
                    for (const el of nodes) {
                      const state = parseState(el);
                      if (state !== null) return state;
                    }
                    return null;
                }"""
            )
        except Exception:
            return None
        if state is None:
            return None
        return bool(state)

    def _click_switch_field(self, root) -> None:
        target_selector = ""
        try:
            target_selector = str(
                root.evaluate(
                    """(node) => {
                        const visible = (el) => {
                          const style = window.getComputedStyle(el);
                          const rect = el.getBoundingClientRect();
                          return style && style.visibility !== 'hidden' && style.display !== 'none'
                            && rect.width > 0 && rect.height > 0;
                        };
                        const switchSelector = [
                          '[role="switch"]',
                          '.wui-switch',
                          '.ant-switch',
                          '.w-switch',
                          '.u-switch',
                          '[class*="Switch"]',
                          '[class*="switch"]',
                          'input[type="checkbox"]'
                        ].join(',');
                        const isDecorativeSwitchPart = (el) => {
                          const className = String(el && el.className || '');
                          return /switch-(inner|handle|thumb|knob|text|label)/i.test(className)
                            || /(^|[-_\\s])(inner|handle|thumb|knob)([-_\\s]|$)/i.test(className);
                        };
                        const isSwitchControl = (el) => {
                          if (!el || isDecorativeSwitchPart(el)) return false;
                          const tag = String(el.tagName || '').toUpperCase();
                          if (tag === 'INPUT' && String(el.type || '').toLowerCase() === 'checkbox') return true;
                          const role = String(el.getAttribute && el.getAttribute('role') || '').toLowerCase();
                          const className = String(el.className || '');
                          if (role === 'switch') return true;
                          if (/(^|\\s)(wui-switch|ant-switch|w-switch|u-switch)(\\s|$)/i.test(className)) return true;
                          const isSwitchContainer = /form-item|lcd-panel-item|wx-item|wui-row|wui-col/i.test(className);
                          return !isSwitchContainer && /switch/i.test(className) && !/switcher/i.test(className);
                        };
                        const descendants = Array.from(node.querySelectorAll(switchSelector))
                          .filter((el) => {
                            return isSwitchControl(el) && (visible(el) || el.matches('input[type="checkbox"]'));
                          });
                        const rootIsSwitchLike = isSwitchControl(node);
                        const candidates = rootIsSwitchLike ? [node, ...descendants] : descendants;
                        const target = candidates.find((el) => visible(el) && !el.matches('input[type="checkbox"]'))
                          || candidates.find((el) => el.matches('input[type="checkbox"]'))
                          || node;
                        const marker = `switch-${Date.now()}-${Math.random().toString(36).slice(2)}`;
                        target.setAttribute('data-ydf-browser-switch-target', marker);
                        return `[data-ydf-browser-switch-target="${marker}"]`;
                    }"""
                )
                or ""
            )
        except Exception:
            target_selector = ""
        if target_selector:
            try:
                root.locator(target_selector).click(timeout=1000)
                return
            except Exception:
                pass
        root.click(timeout=1000)

    def _collect_switch_field_debug(self, root) -> str:
        try:
            data = root.evaluate(
                """(node) => {
                    const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                    const visible = (el) => {
                      const style = window.getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style && style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width > 0 && rect.height > 0;
                    };
                    const describe = (el) => {
                      const rect = el.getBoundingClientRect();
                      return {
                        tag: String(el.tagName || '').toLowerCase(),
                        type: el.getAttribute && el.getAttribute('type'),
                        role: el.getAttribute && el.getAttribute('role'),
                        className: String(el.className || '').slice(0, 180),
                        ariaChecked: el.getAttribute && el.getAttribute('aria-checked'),
                        ariaPressed: el.getAttribute && el.getAttribute('aria-pressed'),
                        dataChecked: el.getAttribute && el.getAttribute('data-checked'),
                        dataValue: el.getAttribute && el.getAttribute('data-value'),
                        value: el.value != null ? String(el.value) : (el.getAttribute && el.getAttribute('value')),
                        checked: Boolean(el.checked),
                        disabled: Boolean(el.disabled) || (el.getAttribute && el.getAttribute('aria-disabled') === 'true'),
                        visible: visible(el),
                        rect: {x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width), height: Math.round(rect.height)},
                        text: normalize(el.innerText || el.textContent || '').slice(0, 120)
                      };
                    };
                    const selector = [
                      '[role="switch"]',
                      '.wui-switch',
                      '.ant-switch',
                      '.w-switch',
                      '.u-switch',
                      '[class*="Switch"]',
                      '[class*="switch"]',
                      'input[type="checkbox"]'
                    ].join(',');
                    return {
                      root: describe(node),
                      candidates: Array.from(node.querySelectorAll(selector)).map(describe).slice(0, 12)
                    };
                }"""
            )
        except Exception:
            return ""
        try:
            return json.dumps(data, ensure_ascii=False)[:2000]
        except Exception:
            return str(data)[:2000]

    def _looks_like_date_field(self, bound_element: BoundElement) -> bool:
        runtime = bound_element.runtime
        candidate = getattr(bound_element, "candidate", None)
        component_name = str(getattr(candidate, "component_name", "") or "")
        probe = f"{runtime.selector} {getattr(runtime, 'name', '') or ''} {component_name}".lower()
        return "date" in probe

    def _looks_like_date_range_field(self, bound_element: BoundElement) -> bool:
        runtime = bound_element.runtime
        candidate = getattr(bound_element, "candidate", None)
        component_name = str(getattr(candidate, "component_name", "") or getattr(runtime, "name", "") or "")
        probe = f"{runtime.selector} {getattr(runtime, 'name', '') or ''} {component_name}".lower()
        return "daterange" in probe or "date_range" in probe or ("range" in probe and "date" in probe)

    def _set_date_field_value(self, locator, value: str) -> None:
        if not locator.evaluate("(node) => node.tagName === 'INPUT'"):
            raise RuntimeError("日期录入目标必须是 input")
        try:
            locator.evaluate(
                """(node, value) => {
                    node.removeAttribute('readonly');
                    node.value = value;
                    node.setAttribute('title', value);
                    for (const eventName of ['input', 'change', 'blur']) {
                        node.dispatchEvent(new Event(eventName, { bubbles: true }));
                    }
                }""",
                value,
            )
        except Exception:
            locator.fill(value, timeout=1000)
        try:
            locator.press("Tab", timeout=1000)
        except Exception:
            pass

    def _set_date_range_field_value(self, root, fill_locator, value: str, bound_element: BoundElement) -> dict[str, Any]:
        start, end, normalized = _parse_date_range_value(value)
        try:
            root.click(timeout=1000)
        except Exception:
            try:
                fill_locator.click(timeout=1000)
            except Exception:
                pass
        self._try_set_date_range_inputs(root, start, end, normalized)
        actual = self._read_date_range_field_value(root)
        if not _date_range_values_match(actual, normalized):
            self._click_date_range_popup_date(start)
            self._click_date_range_popup_date(end)
            try:
                self._require_page().wait_for_timeout(300)
            except Exception:
                pass
            actual = self._read_date_range_field_value(root)
        if _date_range_values_match(actual, normalized):
            return {
                "actual": _parse_date_range_value(actual)[2],
                "selector": bound_element.runtime.selector,
                "confirmed": True,
                "in_dialog": bool(getattr(bound_element.runtime, "in_dialog", False)),
            }
        candidate = getattr(bound_element, "candidate", None)
        label = str(getattr(candidate, "label", "") or getattr(candidate, "fieldid", "") or "")
        selector = str(getattr(bound_element.runtime, "selector", "") or "")
        raise RuntimeError(
            f"日期范围字段录入后未回填: field={label}, expected={normalized!r}, actual={actual!r}, selector={selector}"
        )

    def _try_set_date_range_inputs(self, root, start: str, end: str, normalized: str) -> None:
        try:
            root.evaluate(
                """(node, args) => {
                    const visible = (el) => {
                      const style = window.getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style && style.display !== 'none' && style.visibility !== 'hidden'
                        && rect.width > 0 && rect.height > 0;
                    };
                    const setValue = (input, value) => {
                      const proto = input.tagName === 'TEXTAREA'
                        ? window.HTMLTextAreaElement.prototype
                        : window.HTMLInputElement.prototype;
                      const descriptor = Object.getOwnPropertyDescriptor(proto, 'value');
                      if (descriptor && descriptor.set) descriptor.set.call(input, value);
                      else input.value = value;
                      input.setAttribute('title', value);
                      for (const eventName of ['input', 'change', 'blur']) {
                        input.dispatchEvent(new Event(eventName, { bubbles: true }));
                      }
                    };
                    const inputs = Array.from(node.querySelectorAll('input:not([type="hidden"]), textarea'))
                      .filter((input) => !input.disabled && visible(input));
                    if (inputs.length >= 2) {
                      setValue(inputs[0], args.start);
                      setValue(inputs[1], args.end);
                    } else if (inputs.length === 1) {
                      setValue(inputs[0], args.normalized);
                    }
                }""",
                {"start": start, "end": end, "normalized": normalized},
            )
        except Exception:
            return

    def _read_date_range_field_value(self, root) -> str:
        try:
            return str(
                root.evaluate(
                    """(node) => {
                        const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                        const normalizeRange = (value) => {
                          const match = normalize(value).match(/(\\d{4}-\\d{2}-\\d{2})\\s*~\\s*(\\d{4}-\\d{2}-\\d{2})/);
                          return match ? `${match[1]}~${match[2]}` : '';
                        };
                        const inputs = Array.from(node.querySelectorAll('input:not([type="hidden"]), textarea'))
                          .filter((input) => !input.disabled);
                        const values = inputs.map((input) => normalize(input.value || input.getAttribute('title') || ''))
                          .filter(Boolean);
                        const dates = values.flatMap((value) => Array.from(value.matchAll(/\\d{4}-\\d{2}-\\d{2}/g)).map((item) => item[0]));
                        if (dates.length >= 2) return `${dates[0]}~${dates[1]}`;
                        for (const value of values) {
                          const range = normalizeRange(value);
                          if (range) return range;
                        }
                        return normalizeRange(node.innerText || node.textContent || '');
                    }"""
                )
                or ""
            )
        except Exception:
            return ""

    def _click_date_range_popup_date(self, value: str) -> None:
        selectors = [
            f'[title="{value}"]',
            f'[data-date="{value}"]',
            f'[data-value="{value}"]',
            f'[aria-label="{value}"]',
            f'td[title="{value}"]',
            f'button[title="{value}"]',
        ]
        last_error = ""
        for context in self._all_search_contexts():
            for selector in selectors:
                try:
                    locator = context.locator(selector)
                    count = locator.count()
                except Exception as exc:
                    last_error = str(exc)
                    continue
                for index in range(count):
                    target = locator.nth(index)
                    try:
                        if not target.is_visible(timeout=300):
                            continue
                        target.click(timeout=1500)
                        return
                    except Exception as exc:
                        last_error = str(exc)
        raise RuntimeError(f"未找到日期范围候选日期: {value}{f' ({last_error})' if last_error else ''}")

    def fill_query_field(self, bound_element: BoundElement, value: Any) -> dict[str, list[str]] | None:
        root = self._resolve_visible_locator(bound_element.runtime.selector)
        fill_locator = self._resolve_fill_locator(bound_element.runtime.selector)
        candidate = getattr(bound_element, "candidate", None)
        _ensure_table_reference_target_uses_match(
            candidate,
            value,
            target_has_selection=self._popup_reference_module().target_has_explicit_selection(value),
        )
        if not _candidate_component_claims_modal_reference(candidate) and self._looks_like_choice_field(root, bound_element):
            component_name = str(getattr(candidate, "component_name", "") or "").lower().replace("-", "").replace("_", "")
            raw = getattr(candidate, "raw", None)
            if component_name == "lcdenum" or _candidate_has_enum_type(raw):
                return self._select_choice_for_field(
                    root,
                    fill_locator,
                    value,
                    candidate=candidate,
                    require_value_match=True,
                    root_already_active=True,
                )
            else:
                return self._select_choice_for_field(
                    root,
                    fill_locator,
                    value,
                    candidate=candidate,
                )
            return None
        if self._popup_reference_module().looks_like_field(root, bound_element):
            identity = ReferenceOwnerIdentity.from_locator(
                root,
                fieldid=str(getattr(bound_element.candidate, "fieldid", "") or ""),
                label=str(getattr(bound_element.candidate, "label", "") or ""),
                contract_verified=_bound_element_has_verified_form_identity(bound_element),
                fallback_selector=bound_element.runtime.selector,
            )
            result = self._popup_reference_module().select(
                PopupReferenceRequest.from_bound_target(
                    source_kind="query",
                    identity=identity,
                    target=value,
                )
            ).to_runtime_dict()
            return result or None
        if not self._looks_like_choice_field(root, bound_element):
            fill_locator.fill(str(value))
            return
        return self._select_choice_for_field(
            root,
            fill_locator,
            value,
            candidate=candidate,
        )

    def _select_choice_for_field(
        self,
        root,
        fill_locator,
        value: Any,
        *,
        candidate: Any | None,
        require_value_match: bool = False,
        root_already_active: bool = False,
    ) -> dict[str, Any] | None:
        kwargs: dict[str, Any] = {}
        if require_value_match:
            kwargs["require_value_match"] = True
        if root_already_active:
            kwargs["root_already_active"] = True
        if self._choice_field_is_multi_select(root, candidate):
            kwargs["multi_select"] = True
        return self._select_query_choice(root, fill_locator, value, **kwargs)

    def _choice_field_is_multi_select(self, root, candidate: Any | None) -> bool:
        runtime_state = self._runtime_choice_multi_select_state(root)
        if runtime_state is not None:
            return runtime_state
        return _candidate_claims_multi_select(candidate)

    def _runtime_choice_multi_select_state(self, root) -> bool | None:
        try:
            return root.evaluate(
                    """(node) => {
                        const attr = (name) => String(node.getAttribute(name) || '').toLowerCase();
                        if (['true', '1', 'multiple'].includes(attr('aria-multiselectable'))) return true;
                        if (node.matches('select[multiple], [multiple], [mode="multiple"], [mode="tags"]')) return true;
                        if (node.querySelector([
                          'select[multiple]', '[aria-multiselectable="true"]',
                          '[multiple]', '[mode="multiple"]', '[mode="tags"]',
                          '.w-select-selection--multiple', '.wui-select-selection--multiple',
                          '.ant-select-multiple', '.u-select-multiple',
                          '[class*="select-multiple"]', '[class*="SelectMultiple"]'
                        ].join(','))) return true;
                        if (attr('aria-multiselectable') === 'false') return false;
                        if (node.matches('select:not([multiple]), .ant-select-single, .u-select-single, [class*="selection--single"]')) return false;
                        if (node.querySelector('select:not([multiple]), .ant-select-single, .u-select-single, [class*="selection--single"]')) return false;
                        return null;
                    }"""
                )
        except Exception:
            return None

    def fill_grid_row(self, bound_element: BoundElement, row_index: int, values: dict[str, Any]) -> None:
        locator = self._page.locator(bound_element.runtime.selector).nth(row_index)
        locator.click()
        locator.fill(json.dumps(values, ensure_ascii=False))

    def click(self, bound_element: BoundElement) -> None:
        locator = self._resolve_visible_locator(bound_element.runtime.selector)
        self._prepare_action_surface(locator)
        clickability = self._inspect_action_clickability(locator)
        position = self._click_position_from_clickability(clickability)
        if position is None and clickability.get("blocked") and self._expand_viewport_for_action(clickability):
            clickability = self._inspect_action_clickability(locator)
            position = self._click_position_from_clickability(clickability)
        if position is not None:
            locator.click(position=position)
        elif clickability.get("blocked"):
            try:
                locator.click(timeout=1000)
            except Exception as exc:
                diagnostic = self._clickability_diagnostic(clickability)
                raise RuntimeError(f"目标元素没有可接收 pointer event 的点击点: {diagnostic}") from exc
        else:
            locator.click()
        self._page.wait_for_timeout(600)

    def click_tree_node(self, label: str, timeout_ms: int = 20000, tree_fieldid: str | None = None) -> None:
        selectors = build_tree_node_selectors(label)
        tree_context = None
        search_context = None
        context_error: Exception | None = None
        deadline = time.monotonic() + timeout_ms / 1000
        searched = False
        self.last_tree_search = {"label": label, "used": False, "found": False, "reason": "not_attempted"}
        while time.monotonic() < deadline:
            if tree_fieldid and tree_context is None:
                try:
                    tree_context = self._tree_search_context(tree_fieldid)
                except Exception as exc:
                    context_error = exc
                    self._page.wait_for_timeout(500)
                    continue
                search_context = tree_context
                try:
                    search_context = self._tree_search_context(tree_fieldid, include_search_scope=True)
                except Exception:
                    pass
            if self._try_check_tree_node(label, context=tree_context):
                self._page.wait_for_timeout(1200)
                return
            if self._try_click_first(selectors, context=tree_context) if tree_context else self._try_click_first(selectors):
                self._page.wait_for_timeout(1200)
                return
            if not searched:
                searched = True
                if self._try_search_tree_node(label, context=search_context):
                    if self._try_check_tree_node(label, context=tree_context):
                        self._page.wait_for_timeout(1200)
                        return
                    if self._try_click_first(selectors, context=tree_context) if tree_context else self._try_click_first(selectors):
                        self._page.wait_for_timeout(1200)
                        return
            self._expand_tree_until_visible(label, context=tree_context) if tree_context else self._expand_tree_until_visible(label)
            if self._try_check_tree_node(label, context=tree_context):
                self._page.wait_for_timeout(1200)
                return
            if self._try_click_first(selectors, context=tree_context) if tree_context else self._try_click_first(selectors):
                self._page.wait_for_timeout(1200)
                return
            self._page.wait_for_timeout(500)
        clicked = self._try_check_tree_node(label, context=tree_context) or (
            self._try_click_first(selectors, context=tree_context) if tree_context else self._try_click_first(selectors)
        )
        if not clicked:
            if tree_fieldid and tree_context is None and context_error is not None:
                raise context_error
            suffix = f" in {tree_fieldid}" if tree_fieldid else ""
            raise RuntimeError(f"未找到树节点{suffix}: {label}")
        self._page.wait_for_timeout(1200)

    def _try_search_tree_node(self, label: str, context=None) -> bool:
        search_context = context or self._require_page()
        self.last_tree_search = {"label": label, "used": False, "found": False, "reason": "search_input_missing"}
        if not hasattr(search_context, "locator"):
            self.last_tree_search["reason"] = "context_unavailable"
            return False
        input_selector = self._find_tree_search_input_selector(search_context)
        if not input_selector:
            self.last_tree_search["context_debug"] = self._tree_search_context_debug()
            return False
        self.last_tree_search.update({"used": True, "input_selector": input_selector, "reason": ""})
        search_input = search_context.locator(input_selector).first
        try:
            search_input.fill(label, timeout=1500)
        except Exception:
            try:
                search_input.click(timeout=1000)
                search_input.press("Meta+A", timeout=500)
                search_input.press("Control+A", timeout=500)
                search_input.type(label, timeout=1500)
            except Exception:
                self.last_tree_search["reason"] = "fill_failed"
                return False
        triggered = False
        try:
            search_input.press("Enter", timeout=1000)
            triggered = True
        except Exception:
            pass
        trigger_selector = self._find_tree_search_trigger_selector(search_context, input_selector)
        if trigger_selector:
            try:
                search_context.locator(trigger_selector).first.click(timeout=1200)
                triggered = True
            except Exception:
                try:
                    search_context.locator(trigger_selector).first.click(force=True, timeout=1200)
                    triggered = True
                except Exception:
                    pass
        try:
            self._require_page().wait_for_timeout(900 if triggered else 500)
        except Exception:
            time.sleep(0.5)
        found = self._is_any_visible(build_tree_node_selectors(label), context=search_context)
        self.last_tree_search.update(
            {
                "found": found,
                "triggered": triggered,
                "trigger_selector": trigger_selector,
                "reason": "" if found else "search_result_empty",
            }
        )
        return found

    def _find_tree_search_input_selector(self, context) -> str | None:
        selectors = [
            'input[placeholder*="搜索"]',
            'input[placeholder*="查询"]',
            'input[class*="search"]',
            '.wui-input-search input',
            '.ant-input-search input',
            '[class*="tree"] input:not([type="hidden"])',
            'input:not([type="hidden"])',
        ]
        for selector in selectors:
            locator = context.locator(selector)
            try:
                count = locator.count()
            except Exception:
                continue
            for index in range(count):
                candidate = locator.nth(index)
                try:
                    if candidate.is_visible(timeout=300):
                        return _selector_at_index(selector, index)
                except Exception:
                    continue
        return None

    def _find_tree_search_trigger_selector(self, context, input_selector: str) -> str | None:
        selectors = [
            'button:has(.icon-sousuo)',
            'button:has-text("搜索")',
            'button:has-text("查询")',
            '[role="button"]:has(.icon-sousuo)',
            '[class*="search"] button',
            '[class*="Search"] button',
        ]
        for selector in selectors:
            locator = context.locator(selector)
            try:
                count = locator.count()
            except Exception:
                continue
            for index in range(count):
                candidate = locator.nth(index)
                try:
                    if not candidate.is_visible(timeout=300):
                        continue
                    return _selector_at_index(selector, index)
                except Exception:
                    continue
        return None

    def hover_row_by_text(self, text: str, column: str | None = None) -> None:
        try:
            self._hover_visible_table_data_row(text, column=column)
        except Exception:
            self._expand_table_tree_until_row_visible(text, column=column)
            self._hover_visible_table_data_row(text, column=column)
        self._page.wait_for_timeout(800)

    def select_tree_context(self, label: str) -> None:
        self.click_tree_node(label)

    def focus_row_by_text(self, text: str) -> None:
        self.hover_row_by_text(text)

    def click_row_action(self, action_label: str) -> None:
        self.click(self._resolve_visible_row_action(action_label))

    def click_action_by_fieldid(self, fieldid: str) -> None:
        selector = self._find_first_visible_fieldid_action_selector(fieldid)
        if selector is None:
            diagnostic = self._collect_page_diagnostic_text()
            screenshot = self._save_diagnostic_screenshot("fieldid-action-missing")
            if screenshot:
                diagnostic = f"{diagnostic} | screenshot={screenshot}"
            raise RuntimeError(f"未找到可点击动作 fieldid={fieldid}: {diagnostic}")
        self.click(self._build_fieldid_action_bound_element(fieldid, selector))

    def pop_dynamic_template_payload(self) -> dict[str, Any] | None:
        payload = self._dynamic_template_payload
        self._dynamic_template_payload = None
        return payload

    def pop_dynamic_template_payload_if_current(self, expected: dict[str, Any]) -> dict[str, Any] | None:
        if self._dynamic_template_payload is not expected:
            return None
        return self.pop_dynamic_template_payload()

    def peek_dynamic_template_payload(self) -> dict[str, Any] | None:
        return self._dynamic_template_payload

    def wait_for_dynamic_template_payload(self, timeout_ms: int = 5000) -> None:
        deadline = time.monotonic() + timeout_ms / 1000
        while self._dynamic_template_payload is None and time.monotonic() < deadline:
            self._require_page().wait_for_timeout(250)

    def wait_for_timeout(self, timeout_ms: int) -> None:
        self._require_page().wait_for_timeout(timeout_ms)

    def select_tree_node(self, label: str, tree_fieldid: str | None = None) -> None:
        if tree_fieldid:
            self.click_tree_node(label, tree_fieldid=tree_fieldid)
            return
        self.click_tree_node(label)

    def select_tree_root(self, tree_fieldid: str | None = None) -> str:
        return self._select_tree_shortcut("root", tree_fieldid=tree_fieldid)

    def select_first_tree_leaf(self, tree_fieldid: str | None = None) -> str:
        return self._select_tree_shortcut("first_leaf", tree_fieldid=tree_fieldid)

    def _select_tree_shortcut(self, node: str, tree_fieldid: str | None = None, timeout_ms: int = 20000) -> str:
        context = self._tree_search_context(tree_fieldid) if tree_fieldid else self._require_page().locator("body").first
        if not hasattr(context, "evaluate") or not hasattr(context, "locator"):
            raise RuntimeError(f"当前运行时无法解析树节点快捷选择: {node}")
        page = self._require_page()
        deadline = time.monotonic() + timeout_ms / 1000
        last_result: dict[str, Any] = {}
        while time.monotonic() < deadline:
            marker = f"ydf-tree-shortcut-{node}-{int(time.monotonic() * 1000)}"
            try:
                result = context.evaluate(_TREE_SHORTCUT_TARGET_SCRIPT, {"node": node, "marker": marker})
            except Exception as exc:
                raise RuntimeError(f"树节点快捷选择扫描失败: {node}") from exc
            if isinstance(result, dict):
                last_result = result
            action = str(last_result.get("action") or "")
            label = str(last_result.get("label") or "").strip()
            selector = str(last_result.get("selector") or "").strip()
            if action == "already_selected" and label:
                page.wait_for_timeout(1200)
                return label
            if action in {"select", "expand"} and selector:
                self._click_tree_shortcut_selector(context, selector)
                if action == "select":
                    page.wait_for_timeout(1200)
                    return label
                page.wait_for_timeout(400)
                continue
            page.wait_for_timeout(500)
        suffix = f" in {tree_fieldid}" if tree_fieldid else ""
        diagnostic = self._tree_shortcut_diagnostic(last_result)
        raise RuntimeError(f"未找到树节点快捷选择{suffix}: {node}{diagnostic}")

    def _click_tree_shortcut_selector(self, context, selector: str) -> None:
        target = context.locator(selector).first
        try:
            target.click(timeout=3000)
            return
        except Exception:
            pass
        try:
            target.click(force=True, timeout=3000)
            return
        except Exception:
            pass
        try:
            clicked = bool(
                context.evaluate(
                    """(root, selector) => {
                        const target = root.querySelector(selector);
                        if (!target) return false;
                        target.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                        target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                        target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                        target.click();
                        target.dispatchEvent(new Event('input', { bubbles: true }));
                        target.dispatchEvent(new Event('change', { bubbles: true }));
                        return true;
                    }""",
                    selector,
                )
            )
            if clicked:
                return
        except Exception:
            pass
        raise RuntimeError(f"未找到可点击树节点快捷目标: {selector}")

    def _tree_shortcut_diagnostic(self, last_result: dict[str, Any]) -> str:
        details: list[str] = []
        reason = str(last_result.get("reason") or "").strip()
        if reason:
            details.append(reason)
        try:
            page_text = self._collect_page_diagnostic_text()
        except Exception:
            page_text = ""
        if page_text:
            details.append(page_text)
        try:
            screenshot = self._save_diagnostic_screenshot("tree-shortcut-missing")
        except Exception:
            screenshot = ""
        if screenshot:
            details.append(f"screenshot={screenshot}")
        return f"; {' | '.join(details)}" if details else ""

    def click_toolbar_action(
        self,
        label: str,
        sub_label: str | None = None,
        fieldid: str | None = None,
        aliases: list[str] | None = None,
    ) -> None:
        if sub_label:
            try:
                self._click_toolbar_dropdown_sub_action(label, sub_label, fieldid=fieldid, aliases=aliases)
            except TypeError:
                if fieldid is not None or aliases:
                    raise
                self._click_toolbar_dropdown_sub_action(label, sub_label)
            return
        try:
            self._click_toolbar_bound_action(label, fieldid=fieldid, aliases=aliases)
            return
        except RuntimeError as exc:
            if "未找到可点击工具栏动作" not in str(exc):
                raise
            if self._page is not None:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    self._page.wait_for_timeout(250)
                    try:
                        self._click_toolbar_bound_action(label, fieldid=fieldid, aliases=aliases)
                        return
                    except RuntimeError as retry_exc:
                        if "未找到可点击工具栏动作" not in str(retry_exc):
                            raise
            self._reveal_toolbar_overflow(label)
        try:
            self._click_toolbar_bound_action(label, fieldid=fieldid, aliases=aliases)
        except RuntimeError as exc:
            if "未找到可点击工具栏动作" not in str(exc):
                raise
            diagnostic = self._collect_page_diagnostic_text()
            screenshot = self._save_diagnostic_screenshot("toolbar-action-missing")
            if screenshot:
                diagnostic = f"{diagnostic} | screenshot={screenshot}"
            raise RuntimeError(f"未找到可点击工具栏动作: {label}: {diagnostic}") from exc

    def has_visible_toolbar_action(self, label: str) -> bool:
        try:
            self._resolve_visible_toolbar_action(label)
        except RuntimeError as exc:
            if "未找到可点击工具栏动作" in str(exc):
                return False
            raise
        return True

    def select_transfer_dialog(
        self,
        *,
        title: str | None = None,
        items: list[dict[str, Any]] | None = None,
        move: str = "to_right",
        confirm: bool = True,
    ) -> dict[str, Any]:
        page = self._require_page()
        payload = {
            "title": title,
            "items": items or [],
            "move": move,
            "confirm": confirm,
            "selectors": {
                "dialogs": build_transfer_dialog_dialog_selectors(),
                "move_to_target": build_transfer_dialog_move_to_target_selectors(),
                "confirm": build_transfer_dialog_confirm_selectors("确定"),
            },
        }
        result = page.evaluate(_TRANSFER_DIALOG_SELECT_SCRIPT, payload)
        page.wait_for_timeout(500)
        return dict(result or {})

    def explore_popup_reference(self, target: dict[str, Any]) -> dict[str, Any]:
        return self._popup_reference_module().discover(title=target.get("title"), target=target)

    def select_popup_reference(
        self,
        *,
        title: str | None = None,
        target: dict[str, Any] | None = None,
        confirm: bool = True,
    ) -> dict[str, Any]:
        return self._popup_reference_module().select(
            PopupReferenceRequest.from_open_surface(
                target=dict(target or {}),
                title=title,
                confirm=confirm,
            )
        ).to_runtime_dict()

    def click_tab_action(self, label: str, fieldid: str | None = None) -> None:
        try:
            bound = self._resolve_visible_tab_action(label, fieldid=fieldid)
        except RuntimeError as exc:
            tab_diagnostic = self._collect_tab_diagnostic(fieldid, label)
            page_diagnostic = self._collect_page_diagnostic_text()
            diagnostic = f"{tab_diagnostic} | {page_diagnostic}" if page_diagnostic else tab_diagnostic
            screenshot = self._save_diagnostic_screenshot("tab-action-missing")
            if screenshot:
                diagnostic = f"{diagnostic} | screenshot={screenshot}"
            raise RuntimeError(f"未找到可点击页签: {label}: {diagnostic}") from exc
        self.click(bound)

    def click_query_action(self, label: str = "查询", fieldids: list[str] | None = None) -> None:
        selector = self._find_first_visible_selector(build_query_action_selectors(label, fieldids=fieldids))
        if selector is None:
            diagnostic = self._collect_page_diagnostic_text()
            screenshot = self._save_diagnostic_screenshot("query-action-missing")
            if screenshot:
                diagnostic = f"{diagnostic} | screenshot={screenshot}"
            raise RuntimeError(f"未找到可点击查询动作: {label}: {diagnostic}")
        self.click(self._build_visible_action_bound_element(label, selector, reason="visible_query_action"))

    def click_query_reset(self, query_region_fieldids: list[str]) -> dict[str, str]:
        regions = self._query_reset_regions(query_region_fieldids)
        foreground_exists = self._has_visible_foreground_layer()
        target_regions = [region for region in regions if region["in_foreground"]] if foreground_exists else regions
        if not target_regions:
            diagnostic = self._collect_page_diagnostic_text()
            screenshot = self._save_diagnostic_screenshot("query-reset-missing")
            if screenshot:
                diagnostic = f"{diagnostic} | screenshot={screenshot}"
            if foreground_exists:
                raise RuntimeError(f"未找到前景可见查询区: {diagnostic}")
            raise RuntimeError(f"未找到可见查询区: {diagnostic}")
        if len(target_regions) > 1:
            regions = [region["query_region_fieldid"] for region in target_regions]
            raise RuntimeError(f"查询区匹配不唯一: {regions}")
        target_region = target_regions[0]
        candidates: list[dict[str, Any]] = []
        for source in ("reset_btn", "exact_text"):
            candidates = self._query_reset_candidates(target_region, source)
            if candidates:
                break
        if not candidates:
            diagnostic = self._collect_page_diagnostic_text()
            screenshot = self._save_diagnostic_screenshot("query-reset-missing")
            if screenshot:
                diagnostic = f"{diagnostic} | screenshot={screenshot}"
            raise RuntimeError(f"未找到可点击查询重置动作: {diagnostic}")
        if len(candidates) > 1:
            raise RuntimeError(f'查询重置按钮匹配不唯一: {target_region["query_region_fieldid"]}')
        candidate = candidates[0]
        self.click(
            self._build_visible_action_bound_element(
                "重置",
                candidate["selector"],
                reason=f'query_reset:{candidate["locator_source"]}',
            )
        )
        self._wait_ready()
        return {
            "query_region_fieldid": target_region["query_region_fieldid"],
            "button": "重置",
            "locator_source": candidate["locator_source"],
        }

    def _query_reset_regions(self, query_region_fieldids: list[str]) -> list[dict[str, Any]]:
        page = self._require_page()
        contexts = list(getattr(page, "frames", []) or [page])
        regions_by_token: dict[str, dict[str, Any]] = {}
        for query_region_fieldid in dict.fromkeys(str(value) for value in query_region_fieldids if str(value)):
            root_selectors = [
                f'[fieldid="{query_region_fieldid}_drag"]',
                f'[data-fieldid="{query_region_fieldid}_drag"]',
                f'[fieldid="{query_region_fieldid}"]',
                f'[data-fieldid="{query_region_fieldid}"]',
            ]
            for frame_index, context in enumerate(contexts):
                for root_selector in root_selectors:
                    locator = context.locator(root_selector)
                    try:
                        count = locator.count()
                    except Exception:
                        continue
                    for index in range(count):
                        root = locator.nth(index)
                        try:
                            if not root.is_visible(timeout=300):
                                continue
                            evidence = root.evaluate(
                                """(node, params) => {
                                    const { fieldid, marker } = params;
                                    const readFieldid = (candidate) =>
                                      candidate?.getAttribute('fieldid') || candidate?.getAttribute('data-fieldid') || '';
                                    const visible = (candidate) => {
                                      if (!candidate) return false;
                                      const style = getComputedStyle(candidate);
                                      const rect = candidate.getBoundingClientRect();
                                      return style.display !== 'none' && style.visibility !== 'hidden'
                                        && Number(style.opacity || 1) > 0 && rect.width > 0 && rect.height > 0;
                                    };
                                    const dragFieldid = `${fieldid}_drag`;
                                    let canonical = node;
                                    for (let current = node; current; current = current.parentElement) {
                                      if (readFieldid(current) === dragFieldid && visible(current)) {
                                        canonical = current;
                                        break;
                                      }
                                    }
                                    if (readFieldid(canonical) !== dragFieldid) {
                                      const nested = Array.from(node.querySelectorAll('[fieldid], [data-fieldid]')).find(
                                        (candidate) => readFieldid(candidate) === dragFieldid && visible(candidate)
                                      );
                                      if (nested) canonical = nested;
                                    }
                                        const attr = 'data-ydf-query-reset-region';
                                    const token = canonical.getAttribute(attr) || marker;
                                    canonical.setAttribute(attr, token);
                                    const inForeground = Boolean(canonical.closest([
                                        '[role="dialog"]', '[aria-modal="true"]',
                                        '.ant-modal', '.wui-modal', '.u-modal', '.yy-modal',
                                        '.ant-drawer', '.wui-drawer', '.u-drawer', '.yy-drawer',
                                        '[class*="modal"]', '[class*="Modal"]',
                                        '[class*="drawer"]', '[class*="Drawer"]'
                                    ].join(',')));
                                    return { token, inForeground };
                                }""",
                                {
                                    "fieldid": query_region_fieldid,
                                    "marker": f"query-reset-region-{uuid.uuid4().hex}",
                                },
                            )
                            token = str(evidence["token"])
                            in_foreground = bool(evidence["inForeground"])
                        except Exception:
                            continue
                        regions_by_token.setdefault(
                            token,
                            {
                                "query_region_fieldid": query_region_fieldid,
                                "context": context,
                                "frame_index": frame_index,
                                "root_selector": f'[data-ydf-query-reset-region="{token}"]',
                                "root_source": root_selector,
                                "in_foreground": in_foreground,
                            },
                        )
        return list(regions_by_token.values())

    def _has_visible_foreground_layer(self) -> bool:
        page = self._require_page()
        for context in list(getattr(page, "frames", []) or [page]):
            try:
                if context.evaluate(_TABLE_SCOPE_FOREGROUND_EXISTS_SCRIPT):
                    return True
            except Exception:
                continue
        return False

    def _query_reset_candidates(self, region: dict[str, Any], source: str) -> list[dict[str, Any]]:
        context = region["context"]
        root = context.locator(region["root_selector"])
        targets = build_query_reset_identity_selectors() if source == "reset_btn" else build_query_reset_text_selectors()
        candidates_by_token: dict[str, dict[str, Any]] = {}
        for target in targets:
            locator = root.locator(target)
            try:
                count = locator.count()
            except Exception:
                continue
            for index in range(count):
                button = locator.nth(index)
                try:
                    if not button.is_visible(timeout=300) or not self._is_clickable_action_target(button):
                        continue
                    if not self._is_exact_query_reset_target(button, source):
                        continue
                    token = str(
                        button.evaluate(
                            """(node, marker) => {
                                const attr = 'data-ydf-query-reset-candidate';
                                const current = node.getAttribute(attr);
                                if (current) return current;
                                node.setAttribute(attr, marker);
                                return marker;
                            }""",
                            f"query-reset-{uuid.uuid4().hex}",
                        )
                    )
                except Exception:
                    continue
                candidates_by_token.setdefault(
                    token,
                    {
                        "selector": f'[data-ydf-query-reset-candidate="{token}"]',
                        "locator_source": source,
                    },
                )
        return list(candidates_by_token.values())

    def _is_exact_query_reset_target(self, locator, source: str) -> bool:
        if source == "reset_btn":
            return True
        try:
            return _normalize_visible_text(locator.inner_text(timeout=300)) == "重置"
        except Exception:
            return False

    def click_dialog_button(self, label: str, expect_download: bool = False) -> None:
        selectors = build_dialog_button_selectors(label)
        deadline = time.monotonic() + 10
        while True:
            selector = self._find_first_visible_selector(selectors)
            if selector is not None or time.monotonic() >= deadline:
                break
            self._require_page().wait_for_timeout(max(1, min(100, _remaining_timeout_ms(deadline))))
        if selector is None:
            diagnostic = self._collect_page_diagnostic_text()
            screenshot = self._save_diagnostic_screenshot("dialog-action-missing")
            if screenshot:
                diagnostic = f"{diagnostic} | screenshot={screenshot}"
            raise RuntimeError(f"未找到可点击弹窗按钮: {label}: {diagnostic}")
        if expect_download:
            self._click_selector_and_save_download(selector)
            return
        self.click(self._build_visible_action_bound_element(label, selector, reason="visible_dialog_action"))

    def import_upload(
        self,
        label: str,
        files: list[str],
        action_candidates: list[dict[str, Any]] | None = None,
        fieldid: str | None = None,
        expected_status: str = "success",
    ) -> dict[str, Any]:
        resolved_files = [str(_resolve_import_file(file)) for file in files]
        candidates = action_candidates or []
        direct_action = self._resolve_direct_import_action(label, candidates, fieldid=fieldid)
        direct_result: dict[str, Any] | None = None
        progress_opened = False
        if direct_action is not None:
            self._start_direct_import_network_tracking(resolved_files)
            try:
                self._select_direct_import_file(direct_action, resolved_files)
            except Exception:
                self._stop_direct_import_network_tracking()
                raise
        elif _should_probe_direct_import(label, fieldid, candidates):
            action = self._resolve_import_action(label, fieldid, candidates)
            self._start_direct_import_network_tracking(resolved_files)
            if self._try_select_direct_import_file(action, resolved_files):
                direct_action = action
            else:
                self._stop_direct_import_network_tracking()
                if expected_status == "submitted":
                    raise RuntimeError("公共导入组件不支持 `assert.status: submitted`")
                self._open_import_sub_action(label, "导入")
                self._select_import_workbench_file(resolved_files)
                self._submit_import_workbench()
        else:
            if expected_status == "submitted":
                raise RuntimeError("公共导入组件不支持 `assert.status: submitted`")
            self._open_import_sub_action(label, "导入")
            self._select_import_workbench_file(resolved_files)
            self._submit_import_workbench()
        progress_opened = True
        try:
            if direct_action is None:
                import_results = self._wait_for_import_results(resolved_files)
            else:
                notification_results = self._notification_import_results(resolved_files)
                if notification_results:
                    direct_result = {"import_results": notification_results, "network_requests": []}
                else:
                    direct_result = self._wait_for_direct_import_network_result(resolved_files)
                    notification_results = self._notification_import_results(resolved_files)
                    if notification_results:
                        direct_result["import_results"] = notification_results
                import_results = list(direct_result["import_results"])
                if expected_status != "submitted" and all(
                    _normalize_direct_import_status(item.get("status")) == "submitted"
                    for item in import_results
                ):
                    try:
                        import_results = self._wait_for_import_results(
                            resolved_files,
                            notification_fallback=True,
                        )
                    except RuntimeError as exc:
                        raise RuntimeError(
                            "直连导入后端请求已完成，但当前证据只足以判定 submitted；"
                            "如业务结果由后续页面断言验证，请显式设置 `assert.status: submitted`"
                        ) from exc
        finally:
            self._stop_direct_import_network_tracking()
            if progress_opened:
                self._close_import_progress_dialog()
        result = {"files": resolved_files, "import_results": import_results}
        if direct_action is not None:
            result["entry"] = "direct_file"
            result["network_requests"] = list((direct_result or {}).get("network_requests") or [])
        return result

    def import_download_template(self, label: str, template: str | None = None) -> dict[str, Any]:
        self._open_import_sub_action(label, "下载模版")
        try:
            return self._download_template_from_dialog(template)
        finally:
            self._close_template_download_dialog()

    def set_amount_unit(
        self,
        value: str,
        action_candidates: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        value = str(value or "").strip()
        if value not in {"元", "万元"}:
            raise RuntimeError("金额单位只支持 `元` 和 `万元`")
        self._click_amount_unit_entry(action_candidates or [])
        dialog = self._resolve_amount_unit_dialog()
        self._set_radio_field_value(dialog, value)
        actual_value = self._read_radio_field_value(dialog)
        self._click_amount_unit_confirm(dialog)
        data = {"value": value}
        if actual_value:
            data["actual_value"] = actual_value
        return data

    def upload_attachments(
        self,
        attachments: list[dict[str, str]],
        attachment_candidates: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        candidates = attachment_candidates or []
        initial_view = self._read_attachment_view(candidates)
        needs_restore = initial_view == "table"
        results: list[dict[str, Any]] = []
        upload_error: Exception | None = None
        try:
            if needs_restore:
                self._switch_attachment_view("card", candidates)
            for attachment in attachments:
                attachment_type = str(attachment["type"]).strip()
                file_path = str(_resolve_import_file(attachment["file"]))
                target = self._resolve_attachment_file_input_target(attachment_type, candidates)
                self._validate_attachment_file_type(attachment_type, file_path, target)
                self._require_page().locator(target["input_selector"]).set_input_files(file_path, timeout=10000)
                wait_started = time.monotonic()
                state = self._wait_for_attachment_upload(attachment_type, file_path, target)
                wait_duration_ms = int((time.monotonic() - wait_started) * 1000)
                results.append(
                    {
                        "type": attachment_type,
                        "file": file_path,
                        "status": "success",
                        "target_label": str(target.get("label") or attachment_type),
                        "target_fieldid": str(target.get("fieldid") or ""),
                        "completion_signal": str(state.get("signal") or "accepted"),
                        "wait_duration_ms": wait_duration_ms,
                    }
                )
        except Exception as exc:
            upload_error = exc

        restore_error: Exception | None = None
        if needs_restore:
            try:
                self._switch_attachment_view("table", candidates)
            except Exception as exc:
                restore_error = exc

        if upload_error is not None:
            if restore_error is not None:
                raise RuntimeError(f"{upload_error}；恢复附件表格视图失败: {restore_error}") from upload_error
            raise upload_error
        if restore_error is not None:
            uploaded = ", ".join(Path(item["file"]).name for item in results)
            raise RuntimeError(f"附件已上传: {uploaded}；恢复附件表格视图失败: {restore_error}") from restore_error
        return {
            "attachments": results,
            "initial_view": initial_view,
            "upload_view": "card",
            "view_restored": True,
        }

    @table_scoped
    def add_editable_table_row(
        self,
        label: str = "新增",
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        table_scope: ResolvedTableScope | None = None,
    ) -> dict[str, Any]:
        table_scope_token = table_scope.token if table_scope is not None else ""
        table, table_fieldid, table_columns = _resolved_table_scope_values(
            table_scope, table, table_fieldid, table_columns
        )
        page = self._require_page()
        payload = {
            "label": label,
            "table": table or "",
            "tableFieldid": table_fieldid or "",
            "tableColumns": table_columns or [],
        }
        if table_scope_token:
            payload["tableScopeToken"] = table_scope_token
            payload["tableRegionFieldid"] = table_scope.region_fieldid
        self._settle_editable_table_add_row_interactions()
        result, debug_items = self._run_editable_table_add_row_script(payload)
        if _editable_table_add_row_should_retry(result):
            first_attempt = dict(result)
            self._settle_editable_table_add_row_interactions()
            retry_result, retry_debug_items = self._run_editable_table_add_row_script(payload)
            if retry_result:
                result = dict(retry_result)
            else:
                debug_items.extend(retry_debug_items)
            if isinstance(result, dict):
                result["retry_count"] = 1
                result["first_attempt"] = first_attempt
        if not result:
            scope_message = _editable_table_add_row_scope_message(label, table, debug_items)
            if scope_message:
                raise RuntimeError(scope_message)
            if table_scope_token:
                raise RuntimeError(
                    f"未在已解析可编辑表格作用域内找到新增行入口: table={table or ''}; "
                    f"table_fieldid={table_fieldid or ''}; label={label}; 未点击新增。"
                )
            empty_message = _editable_table_add_row_empty_message(label, table, debug_items)
            if empty_message and _editable_table_add_row_debug_clicked_candidate(debug_items):
                screenshot = self._save_diagnostic_screenshot("editable-table-add-row-empty")
                if screenshot:
                    empty_message = f"{empty_message} | screenshot={screenshot}"
                raise RuntimeError(empty_message)
            selector = self._find_first_visible_selector(build_editable_table_add_row_selectors(label))
            if selector is None:
                if empty_message:
                    screenshot = self._save_diagnostic_screenshot("editable-table-add-row-empty")
                    if screenshot:
                        empty_message = f"{empty_message} | screenshot={screenshot}"
                    raise RuntimeError(empty_message)
                mismatch_message = _editable_table_add_row_name_mismatch_message(label, table, debug_items)
                if mismatch_message:
                    screenshot = self._save_diagnostic_screenshot("editable-table-add-row-mismatch")
                    if screenshot:
                        mismatch_message = f"{mismatch_message} | screenshot={screenshot}"
                    raise RuntimeError(mismatch_message)
                diagnostic = self._collect_page_diagnostic_text()
                if debug_items:
                    diagnostic = f"{diagnostic} | add_row_debug={json.dumps(debug_items, ensure_ascii=False)[:2500]}"
                screenshot = self._save_diagnostic_screenshot("editable-table-add-row-missing")
                if screenshot:
                    diagnostic = f"{diagnostic} | screenshot={screenshot}"
                raise RuntimeError(f"未找到可编辑表格新增行入口: {label}: {diagnostic}")
            self._resolve_visible_locator(selector).click(timeout=3000)
            result = {"label": label, "table": table, "selector": selector}
        if not result.get("foreground_opened"):
            page.wait_for_timeout(800)
        return dict(result)

    def _run_editable_table_add_row_script(self, payload: dict[str, Any]) -> tuple[Any | None, list[dict[str, Any]]]:
        debug_items: list[dict[str, Any]] = []
        for context in self._editable_table_search_contexts():
            try:
                result = context.evaluate(_EDITABLE_TABLE_ADD_ROW_SCRIPT, payload)
            except Exception:
                continue
            if result:
                return result, debug_items
            debug = self._read_editable_table_add_row_debug(context)
            if debug:
                debug_items.append({"context": _search_context_label(context), "debug": debug})
        return None, debug_items

    def _settle_editable_table_add_row_interactions(self) -> None:
        page = self._require_page()
        try:
            page.evaluate(
                """() => {
                    const active = document.activeElement;
                    if (active && typeof active.blur === 'function') active.blur();
                    if (active) {
                      active.dispatchEvent(new FocusEvent('focusout', { bubbles: true }));
                      active.dispatchEvent(new Event('blur', { bubbles: true }));
                    }
                    document.body?.dispatchEvent(new MouseEvent('mousemove', {
                      bubbles: true,
                      clientX: 1,
                      clientY: 1
                    }));
                    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
                }"""
            )
        except Exception:
            pass
        try:
            keyboard = getattr(page, "keyboard", None)
            if keyboard is not None:
                keyboard.press("Escape")
        except Exception:
            pass
        try:
            mouse = getattr(page, "mouse", None)
            if mouse is not None:
                mouse.move(1, 1)
        except Exception:
            pass
        try:
            page.wait_for_timeout(150)
        except Exception:
            pass

    def _read_editable_table_add_row_debug(self, context) -> Any | None:
        try:
            return context.evaluate("() => window.__ydfEditableTableAddRowDebug || null")
        except Exception:
            return None

    @table_scoped
    def fill_editable_table_row(
        self,
        values: Any,
        row_number: int = -1,
        table: str | None = None,
        column_candidates: dict[str, Any] | None = None,
        table_scope: ResolvedTableScope | None = None,
    ) -> dict[str, Any]:
        table, table_fieldid, _table_columns = _resolved_table_scope_values(table_scope, table, None, None)
        filled: list[dict[str, Any]] = []
        for candidate_key, column_label, value in _iter_editable_table_values(values):
            column_candidate = (column_candidates or {}).get(candidate_key) or (column_candidates or {}).get(column_label)
            self._last_editable_table_cell_resolution = None
            row_action_overlay_result: dict[str, Any] | None = None
            try:
                activation_kwargs = {
                    "row_number": row_number,
                    "table": table,
                    "column_candidate": column_candidate,
                }
                if table_fieldid:
                    activation_kwargs["table_fieldid"] = table_fieldid
                if table_scope is not None:
                    activation_kwargs["table_scope_token"] = table_scope.token
                selector = self._activate_editable_table_cell(column_label, **activation_kwargs)
                fill_result = self._fill_active_editable_table_cell(
                    selector,
                    value,
                    column_candidate=column_candidate,
                )
                try:
                    row_action_overlay_result = self._restore_last_editable_table_row_action_overlay()
                except Exception as restore_exc:
                    row_action_overlay_result = {
                        "restore": {"restored": False, "error": str(restore_exc)[:200]}
                    }
            except Exception as exc:
                component = str(getattr(column_candidate, "component_name", "") or "未知组件")
                raise RuntimeError(
                    "可编辑表格列录入失败: "
                    f"table={table or ''}; "
                    f"row={row_number}; "
                    f"column={column_label}; "
                    f"component={component}; "
                    f"value={_display_step_value(value)}; "
                    f"原因: {exc}"
                ) from exc
            field_result = {"column": column_label, "value": _display_step_value(value)}
            if isinstance(fill_result, dict):
                field_result.update(fill_result)
            field_result.update(_editable_table_column_candidate_diagnostics(column_candidate))
            resolution = getattr(self, "_last_editable_table_cell_resolution", None)
            if isinstance(resolution, dict):
                field_result.update(_editable_table_cell_resolution_diagnostics(resolution))
            if row_action_overlay_result:
                field_result["row_action_overlay"] = row_action_overlay_result
            filled.append(field_result)
        return {"table": table, "row_number": row_number, "fields": filled}

    @table_scoped
    def focus_table_row(
        self,
        match: dict[str, Any],
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        table_scope: ResolvedTableScope | None = None,
    ) -> None:
        table, table_fieldid, table_columns = _resolved_table_scope_values(
            table_scope, table, table_fieldid, table_columns
        )
        values = _extract_row_match_values(match)
        if not values:
            raise RuntimeError(f"表格行匹配暂只支持 equals: {match}")
        column = _first_row_match_column(match)
        if table or table_fieldid or table_columns:
            row = self._find_visible_table_data_row_by_values(
                values,
                column=column,
                table=table,
                table_fieldid=table_fieldid,
                table_columns=table_columns,
                match=match,
            )
            if row is None:
                message = self._format_table_selection_failure(
                    f"未找到表格行: {_format_column_match_for_error(column, values)}",
                    table=table,
                    table_fieldid=table_fieldid,
                    column=column,
                )
                raise RuntimeError(message)
            row.hover(timeout=3000)
            self._page.wait_for_timeout(800)
            return
        if len(values) == 1:
            self.hover_row_by_text(values[0], column=column)
            return
        self._hover_row_by_all_text(values)

    @table_scoped
    def focus_table_row_by_index(
        self,
        row_number: int,
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        table_scope: ResolvedTableScope | None = None,
    ) -> None:
        table, table_fieldid, table_columns = _resolved_table_scope_values(
            table_scope, table, table_fieldid, table_columns
        )
        if row_number < 1:
            raise RuntimeError(f"表格行号从 1 开始: {row_number}")
        scoped = bool(table or table_fieldid or table_columns or getattr(self, "_active_table_scope", None))
        selectors = _table_data_row_selectors(scoped=scoped)
        page = self._require_page()
        context = (
            self._table_selection_context(
                table,
                table_fieldid=table_fieldid,
                table_columns=table_columns,
                require_selectable_rows=False,
            )
            if scoped
            else page
        )
        for selector in selectors:
            locator = context.locator(selector)
            try:
                count = locator.count()
            except Exception:
                continue
            visible_data_index = 0
            for index in range(count):
                candidate = locator.nth(index)
                try:
                    if not candidate.is_visible(timeout=500):
                        continue
                    if not self._row_looks_like_table_data_row(candidate):
                        continue
                    visible_data_index += 1
                    if visible_data_index != row_number:
                        continue
                    candidate.hover(timeout=3000)
                    page.wait_for_timeout(800)
                    return
                except Exception:
                    continue
        message = self._format_table_selection_failure(
            f"未找到第 {row_number} 行表格数据",
            table=table,
            table_fieldid=table_fieldid,
        )
        raise RuntimeError(message)

    def _row_looks_like_table_data_row(self, row) -> bool:
        try:
            return bool(
                row.evaluate(
                    """(node) => {
                        const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                        const compact = (value) => normalize(value).replace(/\\s+/g, '');
                        if (!node || !(node instanceof HTMLElement)) return false;
                        if (node.closest('thead, tfoot, .ant-table-thead, .wui-table-thead, .u-table-thead, .ant-table-footer, .wui-table-footer, .u-table-footer')) return false;
                        const className = String(node.className || '');
                        if (/(summary|footer|total|subtotal)/i.test(className)) return false;
                        const text = normalize(node.innerText || node.textContent);
                        const compactText = compact(text);
                        if (!text) return false;
                        if (/暂无数据|搜索无结果|点击上方查询条件搜索数据/.test(text)) return false;
                        if (/^(小计|合计|汇总|总计)(\\s|$)/.test(text) || /^(小计|合计|汇总|总计)/.test(compactText)) return false;
                        return Boolean(node.querySelector('td, [role="gridcell"], [role="cell"], .ant-table-cell, .wui-table-cell, .u-table-cell'));
                    }"""
                )
            )
        except Exception:
            pass
        try:
            text = " ".join((row.inner_text(timeout=300) or "").split())
        except Exception:
            return True
        compact_text = "".join(text.split())
        if not text:
            return False
        if "暂无数据" in text or "搜索无结果" in text or "点击上方查询条件搜索数据" in text:
            return False
        return not (
            text.startswith(("小计", "合计", "汇总", "总计"))
            or compact_text.startswith(("小计", "合计", "汇总", "总计"))
        )

    @table_scoped
    def select_table_row(
        self,
        match: dict[str, Any],
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        table_scope: ResolvedTableScope | None = None,
    ) -> None:
        table, table_fieldid, table_columns = _resolved_table_scope_values(
            table_scope, table, table_fieldid, table_columns
        )
        self.last_table_selection_debug = None
        values = _extract_row_match_values(match)
        if not values:
            raise RuntimeError(f"表格行匹配暂只支持 equals: {match}")
        column = _first_row_match_column(match)
        self.last_table_tree_search = None
        try:
            self._click_row_checkbox_by_match_values(
                values,
                column=column,
                table=table,
                table_fieldid=table_fieldid,
                table_columns=table_columns,
                match=match,
            )
        finally:
            if self.last_table_tree_search is not None:
                self.last_table_tree_search.update(
                    {
                        "match": match,
                        "table": table,
                        "table_fieldid": table_fieldid,
                    }
                )
        self._page.wait_for_timeout(600)

    @table_scoped
    def select_table_row_by_index(
        self,
        row_number: int,
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        table_scope: ResolvedTableScope | None = None,
    ) -> None:
        table, table_fieldid, table_columns = _resolved_table_scope_values(
            table_scope, table, table_fieldid, table_columns
        )
        self.last_table_selection_debug = None
        deadline = time.monotonic() + 5
        while True:
            try:
                if table or table_fieldid:
                    self._click_row_checkbox_by_index(
                        row_number,
                        table=table,
                        table_fieldid=table_fieldid,
                        table_columns=table_columns,
                    )
                else:
                    self._click_row_checkbox_by_index(row_number)
                break
            except RuntimeError as exc:
                remaining_ms = int((deadline - time.monotonic()) * 1000)
                if "当前可见有效行数=0" not in str(exc) or remaining_ms <= 0:
                    raise
                self._page.wait_for_timeout(min(250, remaining_ms))
        self._page.wait_for_timeout(300)

    @table_scoped
    def select_table_rows_by_indices(
        self,
        row_numbers: list[int],
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        table_scope: ResolvedTableScope | None = None,
    ) -> None:
        table, table_fieldid, table_columns = _resolved_table_scope_values(
            table_scope, table, table_fieldid, table_columns
        )
        for row_number in row_numbers:
            if table or table_fieldid:
                self.select_table_row_by_index(
                    row_number,
                    table=table,
                    table_fieldid=table_fieldid,
                    table_columns=table_columns,
                    **({"table_scope": table_scope} if table_scope is not None else {}),
                )
            else:
                self.select_table_row_by_index(row_number)

    @table_scoped
    def select_all_table_rows(
        self,
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        table_scope: ResolvedTableScope | None = None,
    ) -> None:
        table, table_fieldid, table_columns = _resolved_table_scope_values(
            table_scope, table, table_fieldid, table_columns
        )
        self._click_table_header_checkbox(
            table=table,
            table_fieldid=table_fieldid,
            table_columns=table_columns,
        )
        self._page.wait_for_timeout(300)

    @table_scoped
    def collect_table_headers(
        self,
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        table_scope: ResolvedTableScope | None = None,
    ) -> list[str]:
        records = self._collect_table_header_records(
            table=table,
            table_fieldid=table_fieldid,
            table_columns=table_columns,
            table_scope=table_scope,
        )
        headers: list[str] = []
        seen: set[str] = set()
        for text, _identity in records:
            key = _normalize_table_header_key(text)
            if key and key not in seen:
                headers.append(text)
                seen.add(key)
        return headers

    def _collect_table_header_records(
        self,
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        table_scope: ResolvedTableScope | None = None,
    ) -> list[tuple[str, str]]:
        table, table_fieldid, table_columns = _resolved_table_scope_values(
            table_scope, table, table_fieldid, table_columns
        )
        page = self._require_page()
        context = (
            self._table_selection_context(
                table,
                table_fieldid=table_fieldid,
                table_columns=table_columns,
                require_selectable_rows=False,
            )
            if (table or table_fieldid)
            else page
        )
        payload = {
            "table": table,
            "tableFieldid": table_fieldid,
            "columns": table_columns or [],
            "includeIdentity": True,
        }
        scroll_payload = {**payload, "rememberScrollLeft": True}
        required_header_keys = {
            _normalize_table_header_key(column) for column in table_columns or [] if str(column).strip()
        }
        records: list[tuple[str, str]] = []
        seen_identities: set[str] = set()
        seen_header_keys: set[str] = set()
        scroll_changed = False
        try:
            try:
                if context.evaluate(
                    _SCROLL_TABLE_HEADERS_RIGHT_SCRIPT,
                    {**scroll_payload, "rewindToLeft": True},
                ):
                    scroll_changed = True
                    page.wait_for_timeout(250)
            except Exception:
                pass
            for _ in range(12):
                try:
                    raw_headers = context.evaluate(_TABLE_HEADERS_SCRIPT, payload)
                except Exception:
                    raw_headers = []
                for raw_header in raw_headers or []:
                    if isinstance(raw_header, dict):
                        header = " ".join(str(raw_header.get("text") or "").split())
                        identity = str(raw_header.get("identity") or "").strip()
                    else:
                        header = " ".join(str(raw_header).split())
                        identity = ""
                    key = _normalize_table_header_key(header)
                    identity = identity or f"text:{key}"
                    if not header or not key or identity in seen_identities:
                        continue
                    records.append((header, identity))
                    seen_identities.add(identity)
                    seen_header_keys.add(key)
                if required_header_keys and required_header_keys.issubset(seen_header_keys):
                    break
                try:
                    if not context.evaluate(_SCROLL_TABLE_HEADERS_RIGHT_SCRIPT, scroll_payload):
                        break
                except Exception:
                    break
                scroll_changed = True
                page.wait_for_timeout(250)
        finally:
            if scroll_changed:
                try:
                    if context.evaluate(
                        _SCROLL_TABLE_HEADERS_RIGHT_SCRIPT,
                        {**scroll_payload, "restoreScrollLeft": True},
                    ):
                        page.wait_for_timeout(250)
                except Exception:
                    pass
        return records

    @table_scoped
    def collect_table_column_values(
        self,
        column: str,
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        table_scope: ResolvedTableScope | None = None,
    ) -> list[str]:
        table, table_fieldid, table_columns = _resolved_table_scope_values(
            table_scope, table, table_fieldid, table_columns
        )
        page = self._require_page()
        context = (
            self._table_selection_context(
                table,
                table_fieldid=table_fieldid,
                table_columns=table_columns,
                require_selectable_rows=False,
            )
            if (table or table_fieldid)
            else page
        )
        payload = {"column": column, "table": table, "tableFieldid": table_fieldid, "columns": table_columns or []}
        for _ in range(12):
            values = context.evaluate(_TABLE_COLUMN_VALUES_SCRIPT, payload)
            cleaned = [" ".join(str(value).split()) for value in values if " ".join(str(value).split())]
            if cleaned:
                return cleaned
            if not context.evaluate(_SCROLL_TABLE_HEADERS_RIGHT_SCRIPT, payload):
                break
            page.wait_for_timeout(500)
        if table or table_fieldid:
            return []
        return self._collect_table_column_values_from_debug_text(column)

    @table_scoped
    def collect_table_assertion_rows(
        self,
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        table_scope: ResolvedTableScope | None = None,
    ) -> dict[str, Any]:
        table, table_fieldid, table_columns = _resolved_table_scope_values(
            table_scope, table, table_fieldid, table_columns
        )
        context = self._table_selection_context(
            table,
            table_fieldid=table_fieldid,
            table_columns=table_columns,
            require_selectable_rows=False,
        )
        return dict(
            context.evaluate(
                _TABLE_ASSERTION_ROWS_SCRIPT,
                {"table": table, "tableFieldid": table_fieldid, "columns": table_columns or []},
            )
            or {}
        )

    @table_scoped
    def collect_table_row_values(
        self,
        match: dict[str, Any],
        columns: list[str],
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        table_scope: ResolvedTableScope | None = None,
    ) -> dict[str, str]:
        table, table_fieldid, table_columns = _resolved_table_scope_values(
            table_scope, table, table_fieldid, table_columns
        )
        values = _extract_row_match_values(match)
        if not values:
            raise RuntimeError(f"表格行匹配暂只支持 equals: {match}")
        page = self._require_page()
        self._expand_table_tree_until_row_visible(values[0], column=str(match.get("column") or "").strip() or None)
        context = (
            self._table_selection_context(
                table,
                table_fieldid=table_fieldid,
                table_columns=table_columns,
                require_selectable_rows=False,
            )
            if (table or table_fieldid)
            else page
        )
        payload = {
            "match": match,
            "matchValues": values,
            "columns": columns,
            "table": table,
            "tableFieldid": table_fieldid,
            "tableColumns": table_columns or [],
        }
        for _ in range(12):
            result = context.evaluate(_TABLE_ROW_VALUES_SCRIPT, payload)
            cleaned = {str(key): " ".join(str(value).split()) for key, value in dict(result or {}).items()}
            if any(cleaned.get(column) for column in columns):
                return cleaned
            if not context.evaluate(_SCROLL_TABLE_HEADERS_RIGHT_SCRIPT, payload):
                break
            page.wait_for_timeout(500)
        return {}

    @table_scoped
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
        table_scope: ResolvedTableScope | None = None,
    ) -> dict[str, Any]:
        table, table_fieldid, table_columns = _resolved_table_scope_values(
            table_scope, table, table_fieldid, table_columns
        )
        column = str(column or "").strip()
        if not column:
            raise RuntimeError("表格单元格链接点击缺少目标列")
        page = self._require_page()
        values = _extract_row_match_values(match or {}) if match else []
        if match and values:
            self._expand_table_tree_until_row_visible(values[0], column=_first_row_match_column(match))
        context = (
            self._table_selection_context(
                table,
                table_fieldid=table_fieldid,
                table_columns=table_columns,
                require_selectable_rows=False,
            )
            if (table or table_fieldid)
            else page
        )
        payload = {
            "column": column,
            "linkText": str(link_text or "").strip(),
            "match": match or {},
            "matchValues": values,
            "rowNumber": row_number,
            "table": table,
            "tableFieldid": table_fieldid,
            "tableColumns": table_columns or [],
        }
        last_result: dict[str, Any] = {}
        for _ in range(12):
            result = context.evaluate(_TABLE_CELL_LINK_CLICK_SCRIPT, payload)
            if isinstance(result, dict):
                last_result = result
                if result.get("clicked"):
                    page.wait_for_timeout(600)
                    return result
            if not context.evaluate(_SCROLL_TABLE_HEADERS_RIGHT_SCRIPT, payload):
                break
            page.wait_for_timeout(500)
        reason = str(last_result.get("reason") or "link-not-clicked")
        raise RuntimeError(f"未能点击表格单元格链接: column={column}; reason={reason}; result={last_result}")

    def _collect_table_column_values_from_debug_text(self, column: str) -> list[str]:
        try:
            data = self._require_page().evaluate(_TABLE_DEBUG_SCRIPT)
        except Exception:
            return []
        headers = list(data.get("headers") or [])
        if column not in headers:
            return []
        index_from_right = len(headers) - headers.index(column) - 1
        values: list[str] = []
        for row in data.get("rows") or []:
            parts = str(row).split()
            if len(parts) < len(headers) or parts[0] in {"小计", "合计"}:
                continue
            value_index = len(parts) - index_from_right - 1
            if value_index < 0 or value_index >= len(parts):
                continue
            values.append(parts[value_index])
        return list(dict.fromkeys(values))

    def collect_table_debug_text(self) -> str:
        try:
            data = self._require_page().evaluate(_TABLE_DEBUG_SCRIPT)
        except Exception:
            return ""
        return json.dumps(data, ensure_ascii=False)[:1200]

    def _activate_editable_table_cell(
        self,
        column: str,
        row_number: int = -1,
        table: str | None = None,
        table_fieldid: str | None = None,
        table_scope_token: str | None = None,
        column_candidate: Any | None = None,
    ) -> str:
        page = self._require_page()
        self._last_editable_table_row_action_overlay = None
        self._last_editable_table_row_action_overlay_result = None
        payload = {"column": column, "rowNumber": row_number, "table": table or ""}
        if table_fieldid:
            payload["tableFieldid"] = table_fieldid
        if table_scope_token:
            payload["tableScopeToken"] = table_scope_token
        payload.update(_editable_table_column_identity_payload(column_candidate))
        try:
            selector = self._find_editable_table_cell_selector(payload)
        except Exception as exc:
            raise RuntimeError(f"定位可编辑表格单元格失败: column={column}; 原因: {exc}") from exc
        if not selector:
            diagnostic = self.collect_table_debug_text() or self._collect_page_diagnostic_text()
            editable_debug = getattr(self, "_last_editable_table_cell_debug", None)
            if editable_debug:
                diagnostic = f"{diagnostic} | editable_debug={json.dumps(editable_debug, ensure_ascii=False)[:2000]}"
            screenshot = self._save_diagnostic_screenshot("editable-table-cell-missing")
            if screenshot:
                diagnostic = f"{diagnostic} | screenshot={screenshot}"
            raise RuntimeError(f"未找到可编辑表格单元格: column={column}, row={row_number}: {diagnostic}")
        cell = self._resolve_visible_locator(selector)
        self._editable_table_choice_dropdown_before_activation = self._safe_has_visible_choice_dropdown()
        if self._reveal_editable_table_cell_for_activation(cell):
            try:
                page.wait_for_timeout(250)
            except Exception:
                pass
            refreshed_selector = self._find_editable_table_cell_selector(payload)
            if refreshed_selector:
                selector = refreshed_selector
                cell = self._resolve_visible_locator(selector)
        visible_in_viewport = self._locator_intersects_viewport(cell)
        if not visible_in_viewport:
            try:
                cell.scroll_into_view_if_needed(timeout=2000)
            except Exception:
                pass
        activators = (
            (
                ("dispatch-click", lambda: self._dispatch_editable_table_cell_activation(cell, double=False)),
                ("dispatch-dblclick", lambda: self._dispatch_editable_table_cell_activation(cell, double=True)),
                ("playwright-click", lambda: cell.click(timeout=3000)),
                ("playwright-dblclick", lambda: cell.dblclick(timeout=3000)),
            )
            if visible_in_viewport
            else (
                ("playwright-click", lambda: cell.click(timeout=3000)),
                ("playwright-dblclick", lambda: cell.dblclick(timeout=3000)),
                ("dispatch-click", lambda: self._dispatch_editable_table_cell_activation(cell, double=False)),
            )
        )
        self._last_editable_table_activation_attempts = []
        editor_ready = False
        for action, activate in activators:
            try:
                activate()
                ready = self._wait_for_editable_table_cell_editor(cell, timeout_ms=600)
                self._last_editable_table_activation_attempts.append({"action": action, "ready": ready})
                if ready:
                    editor_ready = True
                    break
            except Exception as exc:
                self._last_editable_table_activation_attempts.append({"action": action, "error": str(exc)[:200]})
                continue
        if not editor_ready:
            try:
                mouse = getattr(page, "mouse", None)
                if mouse is not None:
                    mouse.move(1, 1)
                page.wait_for_timeout(120)
                refreshed_selector = self._find_editable_table_cell_selector(payload)
                if refreshed_selector:
                    selector = refreshed_selector
                    cell = self._resolve_visible_locator(selector)
                self._dispatch_editable_table_cell_activation(cell, double=False)
                ready = self._wait_for_editable_table_cell_editor(cell, timeout_ms=600)
                self._last_editable_table_activation_attempts.append({"action": "fallback-dispatch-click", "ready": ready})
                if ready:
                    editor_ready = True
            except Exception as exc:
                self._last_editable_table_activation_attempts.append(
                    {"action": "fallback-dispatch-click", "error": str(exc)[:200]}
                )
        if not editor_ready:
            try:
                collapse_result = self._collapse_editable_table_row_action_overlay(cell)
            except Exception as exc:
                self._last_editable_table_activation_attempts.append(
                    {"action": "row-action-collapse", "error": str(exc)[:200]}
                )
            else:
                collapsed = isinstance(collapse_result, dict) and bool(collapse_result.get("collapsed"))
                self._last_editable_table_activation_attempts.append(
                    {"action": "row-action-collapse", "ready": False, "result": collapse_result}
                )
                if collapsed:
                    try:
                        page.wait_for_timeout(120)
                    except Exception:
                        pass
                    refreshed_selector = self._find_editable_table_cell_selector(payload)
                    if refreshed_selector:
                        selector = refreshed_selector
                        cell = self._resolve_visible_locator(selector)
                    self._last_editable_table_row_action_overlay = {
                        "collapse": collapse_result,
                        "cell_selector": selector,
                    }
                    for action, activate in (
                        ("post-collapse-dispatch-click", lambda: self._dispatch_editable_table_cell_activation(cell, double=False)),
                        ("post-collapse-dispatch-dblclick", lambda: self._dispatch_editable_table_cell_activation(cell, double=True)),
                        ("post-collapse-playwright-click", lambda: cell.click(timeout=3000, force=True)),
                        ("post-collapse-playwright-dblclick", lambda: cell.dblclick(timeout=3000, force=True)),
                    ):
                        try:
                            activate()
                            ready = self._wait_for_editable_table_cell_editor(cell, timeout_ms=600)
                            self._last_editable_table_activation_attempts.append({"action": action, "ready": ready})
                            if ready:
                                editor_ready = True
                                break
                        except Exception as exc:
                            self._last_editable_table_activation_attempts.append({"action": action, "error": str(exc)[:200]})
                            continue
        return selector

    def _collapse_editable_table_row_action_overlay(self, cell) -> dict[str, Any]:
        result = dict(
            cell.evaluate(
                """(node) => {
                    const visible = (el) => {
                      if (!el || !(el instanceof HTMLElement)) return false;
                      const style = window.getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style && style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width > 0 && rect.height > 0;
                    };
                    const textOf = (el) => String(
                      el.innerText || el.textContent || el.getAttribute('title') || el.getAttribute('aria-label') || ''
                    ).replace(/\\s+/g, ' ').trim();
                    const classOf = (el) => String(el.className || '');
                    const iconOnlyToggle = (item) => {
                      const probe = `${item.text} ${item.className}`;
                      if (/>>|>|›|»|收起|折叠|collapse|more|ellipsis|arrow|chevron|caret/i.test(probe)) return true;
                      if (item.text) return false;
                      const hasIcon = Boolean(item.el.querySelector?.('svg, i, [class*="icon"], [class*="Icon"]'));
                      return hasIcon && item.rect.width <= 40 && item.rect.height <= 40;
                    };
                    const row = node.closest('tr, [role="row"], .wui-table-row, .ant-table-row, .u-table-row, [class*="table-row"], [class*="TableRow"]');
                    if (!row) return { collapsed: false, reason: 'missing-row' };
                    const tableRoot = row.closest('.wui-table, .ant-table, .u-table, [role="grid"], [class*="table"], [class*="Table"]');
                    if (!tableRoot) return { collapsed: false, reason: 'missing-table-root' };
                    const rowRect = row.getBoundingClientRect();
                    const cellRect = node.getBoundingClientRect();
                    const tableRect = tableRoot.getBoundingClientRect();
                    const actionSelector = 'button, a, [role="button"], .wui-button, .ant-btn, .u-button, [class*="button"], [class*="Button"], [class*="action"], [class*="Action"], [class*="operation"], [class*="Operation"], [class*="icon"], [class*="Icon"]';
                    const searchRoot = tableRoot.getRootNode?.() || tableRoot.ownerDocument?.body || tableRoot;
                    const rawActions = Array.from(tableRoot.querySelectorAll(actionSelector));
                    for (const item of Array.from(searchRoot.querySelectorAll(actionSelector))) {
                      if (!rawActions.includes(item)) rawActions.push(item);
                    }
                    const actions = rawActions
                      .filter(visible)
                      .map((el) => ({ el, text: textOf(el), className: classOf(el), rect: el.getBoundingClientRect(), inTable: tableRoot.contains(el) }))
                      .filter((item) => item.rect.top < rowRect.bottom + 24 && item.rect.bottom > rowRect.top - 24)
                      .filter((item) => item.inTable || (item.rect.right >= tableRect.left && item.rect.left <= tableRect.right + 4))
                      .filter((item) => item.rect.left >= cellRect.left - 8 || />>|›|»|收起|折叠|collapse|more|ellipsis|right/i.test(`${item.text} ${item.className}`));
                    const toggles = actions.filter(iconOnlyToggle);
                    const target = toggles.sort((a, b) => b.rect.right - a.rect.right)[0];
                    if (!target) {
                      return {
                        collapsed: false,
                        reason: 'missing-row-action-toggle',
                        candidates: actions
                          .sort((a, b) => b.rect.right - a.rect.right)
                          .slice(0, 6)
                          .map((item) => ({
                            text: item.text,
                            className: String(item.className || '').slice(0, 120),
                            width: Math.round(item.rect.width),
                            height: Math.round(item.rect.height),
                            right: Math.round(item.rect.right),
                            inTable: item.inTable
                          }))
                      };
                    }
                    const token = `collapse-${Date.now()}-${Math.floor(Math.random() * 100000)}`;
                    target.el.setAttribute('data-ydf-browser-row-action-toggle', token);
                    return {
                      collapsed: true,
                      selector: `[data-ydf-browser-row-action-toggle="${token}"]`,
                      text: target.text,
                      className: String(target.className || '').slice(0, 160),
                      tableScoped: tableRoot.contains(row),
                      targetInTable: target.inTable
                    };
                }"""
            )
            or {}
        )
        selector = str(result.get("selector") or "").strip()
        if result.get("collapsed") and selector:
            try:
                self._resolve_visible_locator(selector).click(timeout=1500, force=True)
                result["clicked"] = True
            except Exception as exc:
                result["collapsed"] = False
                result["clicked"] = False
                result["error"] = str(exc)[:200]
        return result

    def _restore_last_editable_table_row_action_overlay(self) -> dict[str, Any] | None:
        state = getattr(self, "_last_editable_table_row_action_overlay", None)
        self._last_editable_table_row_action_overlay = None
        if not isinstance(state, dict) or not state:
            return None
        result = dict(state)
        selector = str(state.get("cell_selector") or "").strip()
        if not selector:
            result["restore"] = {"restored": False, "error": "missing-cell-selector"}
            self._last_editable_table_row_action_overlay_result = result
            return result
        try:
            cell = self._resolve_visible_locator(selector)
            result["restore"] = self._restore_editable_table_row_action_overlay(cell)
        except Exception as exc:
            result["restore"] = {"restored": False, "error": str(exc)[:200]}
        self._last_editable_table_row_action_overlay_result = result
        return result

    def _restore_editable_table_row_action_overlay(self, cell) -> dict[str, Any]:
        result = dict(
            cell.evaluate(
                """(node) => {
                    const visible = (el) => {
                      if (!el || !(el instanceof HTMLElement)) return false;
                      const style = window.getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style && style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width > 0 && rect.height > 0;
                    };
                    const textOf = (el) => String(
                      el.innerText || el.textContent || el.getAttribute('title') || el.getAttribute('aria-label') || ''
                    ).replace(/\\s+/g, ' ').trim();
                    const classOf = (el) => String(el.className || '');
                    const iconOnlyToggle = (item) => {
                      const probe = `${item.text} ${item.className}`;
                      if (/<<|<|‹|«|展开|恢复|expand|more|ellipsis|arrow|chevron|caret/i.test(probe)) return true;
                      return false;
                    };
                    const row = node.closest('tr, [role="row"], .wui-table-row, .ant-table-row, .u-table-row, [class*="table-row"], [class*="TableRow"]');
                    if (!row) return { restored: false, reason: 'missing-row' };
                    const tableRoot = row.closest('.wui-table, .ant-table, .u-table, [role="grid"], [class*="table"], [class*="Table"]');
                    if (!tableRoot) return { restored: false, reason: 'missing-table-root' };
                    const rowRect = row.getBoundingClientRect();
                    const tableRect = tableRoot.getBoundingClientRect();
                    const actionSelector = 'button, a, [role="button"], .wui-button, .ant-btn, .u-button, [class*="button"], [class*="Button"], [class*="action"], [class*="Action"], [class*="operation"], [class*="Operation"], [class*="icon"], [class*="Icon"]';
                    const searchRoot = tableRoot.getRootNode?.() || tableRoot.ownerDocument?.body || tableRoot;
                    const rawActions = Array.from(tableRoot.querySelectorAll(actionSelector));
                    for (const item of Array.from(searchRoot.querySelectorAll(actionSelector))) {
                      if (!rawActions.includes(item)) rawActions.push(item);
                    }
                    const actions = rawActions
                      .filter(visible)
                      .map((el) => ({ el, text: textOf(el), className: classOf(el), rect: el.getBoundingClientRect(), inTable: tableRoot.contains(el) }))
                      .filter((item) => item.rect.top < rowRect.bottom + 24 && item.rect.bottom > rowRect.top - 24)
                      .filter((item) => item.inTable || (item.rect.right >= tableRect.left && item.rect.left <= tableRect.right + 4));
                    const toggles = actions.filter(iconOnlyToggle).sort((a, b) => b.rect.right - a.rect.right);
                    const target = toggles[0];
                    if (!target) {
                      return {
                        restored: false,
                        reason: 'missing-row-action-toggle',
                        candidates: actions
                          .sort((a, b) => b.rect.right - a.rect.right)
                          .slice(0, 6)
                          .map((item) => ({
                            text: item.text,
                            className: String(item.className || '').slice(0, 120),
                            width: Math.round(item.rect.width),
                            height: Math.round(item.rect.height),
                            right: Math.round(item.rect.right),
                            inTable: item.inTable
                          }))
                      };
                    }
                    const token = `restore-${Date.now()}-${Math.floor(Math.random() * 100000)}`;
                    target.el.setAttribute('data-ydf-browser-row-action-toggle', token);
                    return {
                      restored: true,
                      selector: `[data-ydf-browser-row-action-toggle="${token}"]`,
                      text: target.text,
                      className: String(target.className || '').slice(0, 160),
                      tableScoped: tableRoot.contains(row),
                      targetInTable: target.inTable
                    };
                }"""
            )
            or {}
        )
        selector = str(result.get("selector") or "").strip()
        if result.get("restored") and selector:
            try:
                self._resolve_visible_locator(selector).click(timeout=1500, force=True)
                result["clicked"] = True
            except Exception as exc:
                result["restored"] = False
                result["clicked"] = False
                result["error"] = str(exc)[:200]
        return result

    def _reveal_editable_table_cell_for_activation(self, cell) -> bool:
        try:
            return bool(
                cell.evaluate(
                    """(node) => {
                        if (!node || !(node instanceof HTMLElement)) return false;
                        const rect = node.getBoundingClientRect();
                        if (rect.width <= 0 || rect.height <= 0) return false;
                        const canScrollX = (el) => {
                          if (!el || !(el instanceof HTMLElement)) return false;
                          const style = window.getComputedStyle(el);
                          const overflowX = `${style.overflowX || ''} ${style.overflow || ''}`.toLowerCase();
                          return el.scrollWidth > el.clientWidth + 4 && /(auto|scroll|overlay)/.test(overflowX);
                        };
                        let scroller = node.parentElement;
                        while (scroller && scroller !== document.body && !canScrollX(scroller)) {
                          scroller = scroller.parentElement;
                        }
                        if (!canScrollX(scroller)) return false;
                        const scrollerRect = scroller.getBoundingClientRect();
                        const nearHorizontalEdge = rect.left < scrollerRect.left + 80 || rect.right > scrollerRect.right - 180;
                        const tooNarrow = rect.width < 24;
                        if (!nearHorizontalEdge && !tooNarrow) return false;
                        const cellCenter = rect.left + rect.width / 2;
                        const desiredCenter = scrollerRect.left + scrollerRect.width * 0.58;
                        const delta = cellCenter - desiredCenter;
                        if (Math.abs(delta) < 8) return false;
                        const before = scroller.scrollLeft;
                        scroller.scrollLeft += delta;
                        return Math.abs(scroller.scrollLeft - before) > 2;
                    }"""
                )
            )
        except Exception:
            return False

    def _locator_intersects_viewport(self, locator) -> bool:
        try:
            return bool(
                locator.evaluate(
                    """(node) => {
                        if (!node || !(node instanceof HTMLElement)) return false;
                        const rect = node.getBoundingClientRect();
                        const width = window.innerWidth || document.documentElement.clientWidth || 0;
                        const height = window.innerHeight || document.documentElement.clientHeight || 0;
                        return rect.width > 0 && rect.height > 0
                          && rect.right > 0 && rect.bottom > 0
                          && rect.left < width && rect.top < height;
                    }"""
                )
            )
        except Exception:
            return False

    def _dispatch_editable_table_cell_activation(self, cell, *, double: bool = False) -> None:
        cell.evaluate(
            """(node, double) => {
                const rect = node.getBoundingClientRect();
                const isActionTarget = (el) => {
                  const actionable = el && el.closest?.([
                    'button',
                    'a',
                    '[role="button"]',
                    '.wui-button',
                    '.ant-btn',
                    '.u-button',
                    '[class*="button"]',
                    '[class*="Button"]'
                  ].join(','));
                  if (!actionable) return false;
                  const text = String(actionable.innerText || actionable.textContent || actionable.getAttribute('title') || '').trim();
                  if (/增行|删行|新增|插入|复制|删除|更多|>>|›|…|\\.\\.\\./.test(text)) return true;
                  const className = String(actionable.className || '');
                  if (/(action|operation|toolbar|more|ellipsis|dropdown|popover)/i.test(className)) return true;
                  return actionable !== node;
                };
                const clampX = (x) => Math.max(rect.left + 1, Math.min(x, rect.right - 1));
                const y = Math.max(rect.top + 1, Math.min(rect.top + rect.height / 2, rect.bottom - 1));
                const points = [
                  clampX(rect.left + rect.width / 2),
                  clampX(rect.left + rect.width * 0.25),
                  clampX(rect.right - 8),
                  clampX(rect.left + 24),
                  clampX(rect.left + 8),
                ];
                let x = points[0];
                let target = node;
                let foundUsableTarget = false;
                for (const candidateX of points) {
                  const candidate = document.elementFromPoint(candidateX, y) || node;
                  if (!isActionTarget(candidate)) {
                    x = candidateX;
                    target = candidate;
                    foundUsableTarget = true;
                    break;
                  }
                }
                if (!foundUsableTarget) target = node;
                const init = { bubbles: true, cancelable: true, clientX: x, clientY: y, view: window };
                for (const eventName of ['mouseover', 'mousemove', 'mousedown', 'mouseup', 'click']) {
                  target.dispatchEvent(new MouseEvent(eventName, init));
                }
                if (double) target.dispatchEvent(new MouseEvent('dblclick', init));
            }""",
            double,
        )

    def _find_editable_table_cell_selector(self, payload: dict[str, Any]) -> str:
        debug_items: list[dict[str, Any]] = []
        first_error: Exception | None = None
        evaluated = False
        self._last_editable_table_cell_resolution = None
        for context in self._editable_table_search_contexts():
            try:
                selector_result = context.evaluate(_EDITABLE_TABLE_CELL_SELECTOR_SCRIPT, payload)
                evaluated = True
            except Exception as exc:
                if first_error is None:
                    first_error = exc
                continue
            if isinstance(selector_result, dict):
                if selector_result.get("identityConflict"):
                    self._last_editable_table_cell_resolution = selector_result
                    self._last_editable_table_cell_debug = debug_items
                    raise RuntimeError(_editable_table_cell_identity_conflict_message(payload, selector_result))
                selector = str(selector_result.get("selector") or "")
                if selector:
                    resolution = dict(selector_result)
                    resolution["context"] = _search_context_label(context)
                    if "locator_source" not in resolution and resolution.get("source"):
                        resolution["locator_source"] = resolution.get("source")
                    self._last_editable_table_cell_resolution = resolution
                    self._last_editable_table_cell_debug = debug_items
                    return selector
                debug = self._read_editable_table_cell_debug(context)
                if debug:
                    debug_items.append({"context": _search_context_label(context), "debug": debug})
                continue
            selector = selector_result
            if selector:
                self._last_editable_table_cell_resolution = {
                    "locator_source": "legacy-selector",
                    "context": _search_context_label(context),
                }
                self._last_editable_table_cell_debug = debug_items
                return str(selector)
            debug = self._read_editable_table_cell_debug(context)
            if debug:
                debug_items.append({"context": _search_context_label(context), "debug": debug})
        self._last_editable_table_cell_debug = debug_items
        if not evaluated and first_error is not None:
            raise first_error
        return ""

    def _read_editable_table_cell_debug(self, context) -> Any | None:
        try:
            return context.evaluate("() => window.__ydfEditableTableCellDebug || null")
        except Exception:
            return None

    def _editable_table_search_contexts(self) -> list[Any]:
        contexts = self._all_search_contexts()
        if len(contexts) <= 1:
            return contexts
        return [*reversed(contexts[1:]), contexts[0]]

    def _wait_for_editable_table_cell_editor(self, cell, timeout_ms: int = 600, dropdown_before: bool | None = None) -> bool:
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            if self._editable_table_cell_has_active_editor(cell):
                return True
            before = getattr(self, "_editable_table_choice_dropdown_before_activation", None) if dropdown_before is None else dropdown_before
            if before is False and self._safe_has_visible_choice_dropdown():
                return True
            if time.monotonic() >= deadline:
                return False
            try:
                self._require_page().wait_for_timeout(120)
            except Exception:
                time.sleep(0.12)

    def _editable_table_cell_has_active_editor(self, cell) -> bool:
        if self._first_visible_child_locator(cell, _editable_table_editor_selectors()) is not None:
            return True
        if self._active_editable_locator_within(cell) is not None:
            return True
        return self._locator_is_directly_editable(cell)

    def _locator_is_directly_editable(self, locator) -> bool:
        try:
            return bool(
                locator.evaluate(
                    """(node) => {
                        if (!node || !(node instanceof HTMLElement)) return false;
                        const tag = String(node.tagName || '').toLowerCase();
                        return tag === 'input'
                          || tag === 'textarea'
                          || node.isContentEditable
                          || node.getAttribute('contenteditable') === 'true'
                          || ['textbox', 'combobox'].includes(node.getAttribute('role') || '');
                    }"""
                )
            )
        except Exception:
            return False

    def _fill_active_editable_table_cell(
        self,
        cell_selector: str,
        value: Any,
        column_candidate: Any | None = None,
    ) -> dict[str, Any] | None:
        cell = self._resolve_visible_locator(cell_selector)
        fill_locator = self._first_visible_child_locator(
            cell,
            _editable_table_editor_selectors(),
        )
        if fill_locator is None:
            active = self._active_editable_locator_within(cell)
            if active is not None:
                fill_locator = active
        if fill_locator is None and self._locator_is_directly_editable(cell):
            fill_locator = cell
        _ensure_table_reference_target_uses_match(
            column_candidate,
            value,
            target_has_selection=self._popup_reference_module().target_has_explicit_selection(value),
        )
        multi_select_choice = (
            not _candidate_component_claims_modal_reference(column_candidate)
            and self._choice_field_is_multi_select(cell, column_candidate)
        )
        if multi_select_choice:
            return self._select_query_choice(
                cell,
                fill_locator,
                value,
                root_already_active=self._safe_has_visible_choice_dropdown(),
                multi_select=True,
            )
        if (
            (fill_locator is None or self._popup_reference_module().wants_first_available(value))
            and getattr(self, "_editable_table_choice_dropdown_before_activation", False) is False
            and self._safe_has_visible_choice_dropdown()
        ):
            before_text = self._read_editable_table_cell_text(cell)
            if self._try_select_current_editable_table_choice(cell, value):
                if self._popup_reference_module().wants_first_available(value):
                    if self._wait_for_editable_table_cell_backfill(cell, before_text):
                        return
                else:
                    after_text = self._wait_for_editable_table_cell_value(cell, value)
                    if self._editable_table_cell_value_matches(after_text, value):
                        return
        if fill_locator is None:
            try:
                self._coerce_switch_value(value)
            except RuntimeError:
                pass
            else:
                switch_state = self._read_switch_field_state(cell)
                if switch_state is not None:
                    self._set_switch_field_value(cell, value)
                    return
        plain_editor_overrides_metadata = self._editable_table_cell_plain_editor_overrides_reference_metadata(
            cell,
            fill_locator,
            column_candidate,
        )
        looks_like_choice = False
        choice_dropdown_open = False
        if fill_locator is not None and not plain_editor_overrides_metadata:
            looks_like_choice = self._editable_table_cell_looks_like_choice(cell, cell_selector, column_candidate)
            if looks_like_choice:
                try:
                    choice_dropdown_open = self._has_visible_choice_dropdown()
                except Exception:
                    choice_dropdown_open = False
        choice_should_precede_popup = looks_like_choice and (
            choice_dropdown_open or not _candidate_component_claims_modal_reference(column_candidate)
        )
        structured_popup_target = self._popup_reference_module().target_is_structured(value)
        if (
            (structured_popup_target or not choice_should_precede_popup)
            and not plain_editor_overrides_metadata
            and (
                structured_popup_target
                or self._popup_reference_module().editable_cell_looks_like_reference(
                    cell,
                    cell_selector,
                    column_candidate,
                )
            )
        ):
            before_text = self._read_editable_table_cell_text(cell)
            try:
                identity = ReferenceOwnerIdentity.from_locator(
                    cell,
                    fieldid=str(getattr(column_candidate, "fieldid", "") or ""),
                    label=str(getattr(column_candidate, "label", "") or ""),
                    contract_verified=False,
                    fallback_selector=cell_selector,
                )
                popup_result = self._popup_reference_module().select(
                    PopupReferenceRequest.from_bound_target(
                        source_kind="editable_table",
                        identity=identity,
                        target=value,
                    )
                ).to_runtime_dict()
            except RuntimeError as exc:
                if structured_popup_target:
                    raise RuntimeError(f"结构化弹出参照目标录入失败: value={_display_step_value(value)}; 原因: {exc}") from exc
                can_retry_choice = not _candidate_component_claims_modal_reference(column_candidate)
                if (
                    not structured_popup_target
                    and can_retry_choice
                    and self._try_select_current_editable_table_choice(cell, value)
                ):
                    after_text = self._wait_for_editable_table_cell_value(cell, value)
                    if self._editable_table_cell_value_matches(after_text, value):
                        return
                    diagnostic = self._describe_editable_table_cell(cell)
                    screenshot = self._save_diagnostic_screenshot("editable-table-backfill-missing")
                    if screenshot:
                        diagnostic = f"{diagnostic} | screenshot={screenshot}"
                    raise RuntimeError(f"可编辑表格单元格录入后未回填: {diagnostic}") from exc
                raise
            after_text = self._wait_for_editable_table_cell_backfill(cell, before_text)
            if before_text == "" and after_text == "":
                diagnostic = self._describe_editable_table_cell(cell)
                diagnostic = self._append_editable_table_scope_diagnostic(diagnostic)
                close_action = str(popup_result.get("close_action") or "")
                if close_action:
                    diagnostic = f"{diagnostic} | close_action={close_action}"
                diagnostic_refs = popup_result.get("diagnostic_refs")
                if diagnostic_refs:
                    diagnostic = f"{diagnostic} | diagnostic_refs={diagnostic_refs}"
                screenshot = self._save_diagnostic_screenshot("popup-reference-backfill-missing")
                if screenshot:
                    diagnostic = f"{diagnostic} | screenshot={screenshot}"
                raise RuntimeError(f"弹出参照选择未回填到字段: {diagnostic}")
            return popup_result or None
        if fill_locator is not None:
            text_value = str(value)
            if (
                not plain_editor_overrides_metadata
                and looks_like_choice
            ):
                choice_result = self._select_query_choice(
                    cell,
                    fill_locator,
                    value,
                    require_value_match=True,
                    root_already_active=True,
                )
                if isinstance(choice_result, dict):
                    return choice_result
            else:
                self._set_text_field_value(fill_locator, text_value)
                if self._has_visible_choice_dropdown():
                    if self._try_click_query_choice_with_wait(text_value, timeout_ms=5000):
                        self._wait_for_query_choice_dropdown_to_settle()
            after_text = self._wait_for_editable_table_cell_value(cell, text_value)
            if not self._editable_table_cell_value_matches(after_text, text_value):
                diagnostic = self._describe_editable_table_cell(cell)
                diagnostic = self._append_editable_table_scope_diagnostic(diagnostic)
                screenshot = self._save_diagnostic_screenshot("editable-table-backfill-missing")
                if screenshot:
                    diagnostic = f"{diagnostic} | screenshot={screenshot}"
                raise RuntimeError(f"可编辑表格单元格录入后未回填: {diagnostic}")
            return
        diagnostic = self._describe_editable_table_cell(cell)
        diagnostic = self._append_editable_table_scope_diagnostic(diagnostic)
        activation_state = self._describe_editable_table_activation_state(cell)
        if activation_state:
            diagnostic = f"{diagnostic} | activation_state={activation_state}"
        screenshot = self._save_diagnostic_screenshot("editable-table-editor-missing")
        if screenshot:
            diagnostic = f"{diagnostic} | screenshot={screenshot}"
        raise RuntimeError(f"可编辑表格单元格激活后未出现可输入控件: {diagnostic}")

    def _try_select_current_editable_table_choice(self, cell, value: Any) -> bool:
        if isinstance(value, (dict, list, tuple)) and not self._popup_reference_module().wants_first_available(value):
            return False
        try:
            if not self._has_visible_choice_dropdown():
                return False
            if self._popup_reference_module().wants_first_available(value):
                deadline = time.monotonic() + 5
                while True:
                    if self._click_first_query_choice():
                        self._wait_for_query_choice_dropdown_to_settle()
                        return True
                    if time.monotonic() >= deadline:
                        return False
                    self._require_page().wait_for_timeout(250)
            text_value = str(value)
            if self._try_click_query_choice_with_wait(text_value, timeout_ms=5000):
                return self._query_choice_selection_settled(cell, text_value)
            if self._try_click_query_choice_text_fallback(text_value):
                return self._query_choice_selection_settled(cell, text_value)
        except Exception:
            return False
        return False

    def _editable_table_cell_plain_editor_overrides_reference_metadata(
        self,
        cell,
        fill_locator,
        column_candidate: Any | None,
    ) -> bool:
        if fill_locator is None or not _candidate_component_claims_modal_reference(column_candidate):
            return False
        if self._popup_reference_module().root_has_trigger(cell):
            return False
        try:
            return bool(
                cell.evaluate(
                    """(node) => {
                        const visible = (el) => {
                          if (!el) return false;
                          const style = window.getComputedStyle(el);
                          const rect = el.getBoundingClientRect();
                          return style && style.visibility !== 'hidden' && style.display !== 'none'
                            && rect.width > 0 && rect.height > 0;
                        };
                        const editors = Array.from(node.querySelectorAll(
                          'input:not([type="hidden"]), textarea, [contenteditable="true"], [role="textbox"]'
                        ));
                        const editor = editors.find(visible);
                        if (!editor) return false;
                        const ancestors = [];
                        for (let el = editor; el && el !== node.parentElement && ancestors.length < 6; el = el.parentElement) {
                          ancestors.push([
                            el.className,
                            el.getAttribute('role'),
                            el.getAttribute('aria-label'),
                            el.getAttribute('title'),
                          ].join(' '));
                          if (el === node) break;
                        }
                        const probe = ancestors.join(' ').toLowerCase();
                        if (/(select|picker|cascader|dropdown|tree|refer|reference|modal|ref|参照|选择|sousuo|fangdajing)/i.test(probe)) {
                          return false;
                        }
                        const tag = String(editor.tagName || '').toLowerCase();
                        const type = String(editor.getAttribute('type') || '').toLowerCase();
                        return tag === 'textarea'
                          || editor.isContentEditable
                          || editor.getAttribute('contenteditable') === 'true'
                          || editor.getAttribute('role') === 'textbox'
                          || (tag === 'input' && !['checkbox', 'radio', 'file', 'button', 'submit'].includes(type));
                    }"""
                )
            )
        except Exception:
            return False

    def _read_editable_table_cell_text(self, cell, timeout_ms: int = 1000) -> str | None:
        if timeout_ms <= 0:
            return None
        try:
            return str(
                cell.evaluate(
                    """(node) => {
                        const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                        const input = Array.from(node.querySelectorAll('input:not([type="hidden"]), textarea, [contenteditable="true"], [role="textbox"]'))
                          .find((item) => {
                            const style = window.getComputedStyle(item);
                            const rect = item.getBoundingClientRect();
                            return style && style.visibility !== 'hidden' && style.display !== 'none'
                              && rect.width > 0 && rect.height > 0;
                          });
                        if (input) {
                          return normalize(input.value || input.getAttribute('title') || input.innerText || input.textContent);
                        }
                        const title = Array.from(node.querySelectorAll('[title]'))
                          .map((item) => normalize(item.getAttribute('title')))
                          .find(Boolean);
                        if (title) return title;
                        return normalize(node.innerText || node.textContent);
                    }""",
                    timeout=max(1, timeout_ms),
                )
            ).strip()
        except Exception:
            return None

    def _wait_for_editable_table_cell_backfill(self, cell, before_text: str | None, timeout_ms: int = 3500) -> str | None:
        deadline = time.monotonic() + timeout_ms / 1000
        last_text = None
        while True:
            remaining_ms = _remaining_timeout_ms(deadline)
            if remaining_ms <= 0:
                return last_text
            last_text = self._read_editable_table_cell_text(cell, timeout_ms=min(1000, remaining_ms))
            if before_text == "" and last_text:
                return last_text
            if before_text not in ("", None) and last_text != before_text:
                return last_text
            remaining_ms = _remaining_timeout_ms(deadline)
            if remaining_ms <= 0:
                return last_text
            poll_ms = min(250, remaining_ms)
            try:
                self._require_page().wait_for_timeout(poll_ms)
            except Exception:
                time.sleep(poll_ms / 1000)

    def _wait_for_editable_table_cell_value(self, cell, expected_value: Any, timeout_ms: int = 3500) -> str | None:
        deadline = time.monotonic() + timeout_ms / 1000
        last_text = None
        while True:
            remaining_ms = _remaining_timeout_ms(deadline)
            if remaining_ms <= 0:
                return last_text
            last_text = self._read_editable_table_cell_text(cell, timeout_ms=min(1000, remaining_ms))
            if self._editable_table_cell_value_matches(last_text, expected_value):
                return last_text
            remaining_ms = _remaining_timeout_ms(deadline)
            if remaining_ms <= 0:
                return last_text
            poll_ms = min(250, remaining_ms)
            try:
                self._require_page().wait_for_timeout(poll_ms)
            except Exception:
                time.sleep(poll_ms / 1000)

    def _editable_table_cell_value_matches(self, actual_value: Any, expected_value: Any) -> bool:
        if self._popup_reference_module().wants_first_available(expected_value):
            return bool(str(actual_value or "").strip())
        expected = " ".join(str(expected_value or "").split())
        if not expected:
            return True
        actual = " ".join(str(actual_value or "").split())
        if not actual:
            return False
        if actual == expected or expected in actual or actual in expected:
            return True
        if _editable_table_numeric_values_match(actual, expected):
            return True
        return actual.replace(" ", "") == expected.replace(" ", "")

    def _describe_editable_table_cell(self, cell) -> str:
        try:
            data = cell.evaluate(
                """(node) => {
                    const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                    const row = node.closest('tr, [role="row"], .wui-table-row, .ant-table-row, .u-table-row');
                    return {
                      cell: normalize(node.innerText || node.textContent).slice(0, 300),
                      row: row ? normalize(row.innerText || row.textContent).slice(0, 800) : '',
                      inputs: Array.from(node.querySelectorAll('input, textarea, [contenteditable="true"], [role="textbox"]'))
                        .map((item) => ({
                          value: normalize(item.value || item.getAttribute('title') || item.innerText || item.textContent),
                          placeholder: item.getAttribute('placeholder') || '',
                          className: String(item.className || '').slice(0, 120),
                        }))
                        .slice(0, 10),
                    };
                }"""
            )
            return json.dumps(data, ensure_ascii=False)[:1200]
        except Exception:
            return self._collect_page_diagnostic_text()

    def _describe_editable_table_activation_state(self, cell) -> str:
        try:
            focused = self._active_editable_locator()
            focused_summary = None
            if focused is not None:
                try:
                    focused_summary = focused.evaluate(
                        """(node) => ({
                            tag: String(node.tagName || '').toLowerCase(),
                            className: String(node.className || '').slice(0, 160),
                            role: node.getAttribute('role') || '',
                            value: String(node.value || node.innerText || node.textContent || '').slice(0, 200),
                        })"""
                    )
                except Exception:
                    focused_summary = {"present": True}
            resolution = getattr(self, "_last_editable_table_cell_resolution", None) or {}
            return json.dumps(
                {
                    "choice_dropdown_visible": self._safe_has_visible_choice_dropdown(),
                    "has_cell_editor": self._editable_table_cell_has_active_editor(cell),
                    "has_focused_editor": self._active_editable_locator_within(cell) is not None,
                    "activation_attempts": getattr(self, "_last_editable_table_activation_attempts", []),
                    "focused_editor": focused_summary,
                    "choice_surface": self._collect_choice_diagnostic_text(),
                    "locator_source": resolution.get("locator_source") or resolution.get("source") or "",
                    "target_identity": resolution.get("targetIdentity") or {},
                    "actual_identity": resolution.get("actualIdentity") or {},
                },
                ensure_ascii=False,
            )[:1600]
        except Exception:
            return ""

    def _append_editable_table_scope_diagnostic(self, diagnostic: str) -> str:
        scope = _editable_table_scope_from_resolution(getattr(self, "_last_editable_table_cell_resolution", None))
        if not scope:
            return diagnostic
        parts = []
        for key in ("table", "table_fieldid", "root_source", "row_index", "row_text"):
            value = scope.get(key)
            if value is None or value == "":
                continue
            parts.append(f"{key}={value}")
        if not parts:
            return diagnostic
        return f"{diagnostic} | table_scope: {'; '.join(parts)}"

    def _editable_table_cell_looks_like_choice(
        self,
        cell,
        cell_selector: str,
        column_candidate: Any | None,
    ) -> bool:
        if column_candidate is not None:
            bound = SimpleNamespace(
                candidate=column_candidate,
                runtime=SimpleNamespace(
                    selector=cell_selector,
                    role=None,
                    tag_name=None,
                    name=getattr(column_candidate, "component_name", ""),
                ),
            )
            return self._looks_like_choice_field(cell, bound)
        try:
            return bool(
                cell.evaluate(
                    """(node) => {
                        const text = [
                          node.className,
                          node.getAttribute('role'),
                          node.innerText,
                          node.textContent,
                        ].join(' ').toLowerCase();
                        return /select|picker|cascader|dropdown|tree/.test(text);
                    }"""
                )
            )
        except Exception:
            return False

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

    def _active_editable_locator(self):
        for selector in (
            "input:not([type='hidden']):focus",
            "textarea:focus",
            "[contenteditable='true']:focus",
            '[role="textbox"]:focus',
            '[role="combobox"]:focus',
        ):
            for context in self._editable_table_search_contexts():
                locator = context.locator(selector).first
                try:
                    if locator.count() > 0 and locator.is_visible(timeout=300):
                        return locator
                except Exception:
                    continue
        return None

    def _active_editable_locator_within(self, root):
        if not hasattr(root, "locator"):
            return None
        for selector in (
            "input:not([type='hidden']):focus",
            "textarea:focus",
            "[contenteditable='true']:focus",
            '[role="textbox"]:focus',
            '[role="combobox"]:focus',
        ):
            try:
                locator = root.locator(selector).first
                if locator.count() > 0 and locator.is_visible(timeout=300):
                    return locator
            except Exception:
                continue
        return None

    def _has_visible_choice_dropdown(self) -> bool:
        return self._is_any_visible(
            [
                ".w-select-dropdown",
                ".wui-select-dropdown",
                ".ant-select-dropdown",
                ".u-select-dropdown",
                '[role="listbox"]',
            ]
        )

    def _safe_has_visible_choice_dropdown(self) -> bool:
        try:
            return self._has_visible_choice_dropdown()
        except Exception:
            return False

    def _resolve_attachment_file_input_selector(self, attachment_type: str) -> str:
        return self._resolve_attachment_file_input_target(attachment_type).get("input_selector", "")

    def _read_attachment_view(self, attachment_candidates: list[dict[str, Any]]) -> str:
        view = self._require_page().evaluate(
            _ATTACHMENT_VIEW_SCRIPT,
            _normalize_attachment_candidates(attachment_candidates, ""),
        )
        if view in {"card", "table"}:
            return str(view)
        diagnostic = self._collect_attachment_diagnostic_text()
        raise RuntimeError(f"无法识别附件组件当前视图: {diagnostic}")

    def _switch_attachment_view(self, target_view: str, attachment_candidates: list[dict[str, Any]]) -> None:
        selector = self._require_page().evaluate(
            _ATTACHMENT_VIEW_SWITCH_SCRIPT,
            {
                "target_view": target_view,
                "candidates": _normalize_attachment_candidates(attachment_candidates, ""),
            },
        )
        if not selector:
            raise RuntimeError(f"未找到附件{_attachment_view_label(target_view)}切换入口")
        self._require_page().locator(str(selector)).click(timeout=5000)
        self._require_page().wait_for_timeout(300)
        actual_view = self._read_attachment_view(attachment_candidates)
        if actual_view != target_view:
            raise RuntimeError(
                f"附件视图切换未生效: target={target_view}, actual={actual_view}"
            )

    def _resolve_attachment_file_input_target(
        self,
        attachment_type: str,
        attachment_candidates: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        page = self._require_page()
        candidates = _normalize_attachment_candidates(attachment_candidates or [], attachment_type)
        target = page.evaluate(
            _ATTACHMENT_FILE_INPUT_SELECTOR_SCRIPT,
            {"attachment_type": attachment_type, "candidates": candidates},
        )
        if isinstance(target, str) and target:
            return {
                "input_selector": target,
                "root_selector": "",
                "label": attachment_type,
                "fieldid": "",
                "allowed_extensions": _allowed_attachment_extensions(candidates[0] if candidates else {}),
            }
        if isinstance(target, dict) and target.get("input_selector"):
            candidate = _first_matching_attachment_candidate(candidates, attachment_type)
            allowed_extensions = _allowed_attachment_extensions(candidate or {})
            dom_extensions = _normalize_extension_list(target.get("allowed_extensions"))
            if dom_extensions:
                allowed_extensions = dom_extensions
            return {
                "input_selector": str(target.get("input_selector") or ""),
                "root_selector": str(target.get("root_selector") or ""),
                "label": str(target.get("label") or (candidate or {}).get("label") or attachment_type),
                "fieldid": str(target.get("fieldid") or (candidate or {}).get("fieldid") or ""),
                "allowed_extensions": allowed_extensions,
            }
        diagnostic = self._collect_attachment_diagnostic_text()
        screenshot = self._save_diagnostic_screenshot("attachment-input-missing")
        if screenshot:
            diagnostic = f"{diagnostic} | screenshot={screenshot}"
        raise RuntimeError(f"未找到附件上传入口: {attachment_type}: {diagnostic}")

    def _validate_attachment_file_type(self, attachment_type: str, file_path: str, target: dict[str, Any]) -> None:
        allowed_extensions = _normalize_extension_list(target.get("allowed_extensions"))
        if not allowed_extensions or "*" in allowed_extensions:
            return
        suffix = Path(file_path).suffix.lower().lstrip(".")
        if suffix and suffix in allowed_extensions:
            return
        allowed = ",".join(sorted(allowed_extensions))
        raise RuntimeError(
            f"附件文件类型不匹配: type={attachment_type}, file={Path(file_path).name}, allowed={allowed}"
        )

    def _wait_for_attachment_upload(
        self,
        attachment_type: str,
        file_path: str,
        target: dict[str, Any] | None = None,
        timeout_ms: int = 30000,
    ) -> dict[str, Any]:
        page = self._require_page()
        filename = Path(file_path).name
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            state = self._read_attachment_upload_state(attachment_type, filename, target or {})
            if state.get("completed"):
                return state
            page.wait_for_timeout(500)
        diagnostic = self._collect_attachment_diagnostic_text((target or {}).get("root_selector") or None)
        screenshot = self._save_diagnostic_screenshot("attachment-upload-timeout")
        if screenshot:
            diagnostic = f"{diagnostic} | screenshot={screenshot}"
        raise RuntimeError(f"等待附件上传完成超时: type={attachment_type}, file={filename}: {diagnostic}")

    def _read_attachment_upload_state(
        self,
        attachment_type: str,
        filename: str,
        target: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "attachment_type": attachment_type,
            "filename": filename,
            "root_selector": target.get("root_selector") or "",
        }
        try:
            state = self._require_page().evaluate(_ATTACHMENT_STATE_SCRIPT, payload) or {}
        except Exception:
            state = {}
        if isinstance(state, dict):
            return dict(state)
        return {"completed": False, "signal": "", "text": str(state)}

    def _collect_attachment_text(self, root_selector: str | None = None) -> str:
        try:
            return str(self._require_page().evaluate(_ATTACHMENT_TEXT_SCRIPT, {"root_selector": root_selector or ""}) or "")
        except Exception:
            return ""

    def _collect_attachment_diagnostic_text(self, root_selector: str | None = None) -> str:
        text = " ".join(self._collect_attachment_text(root_selector).split())
        if text:
            return text[:1000]
        return self._collect_page_diagnostic_text()

    def read_field_value(self, bound_element: BoundElement) -> str:
        root = self._resolve_visible_locator(bound_element.runtime.selector)
        if "read_only_assertion" in getattr(bound_element, "reasons", ()) and bound_element.runtime.is_identity_root:
            return str(root.evaluate(_FIELD_VALUE_FROM_ROOT_SCRIPT, bound_element.candidate.label) or "")
        if self._looks_like_switch_field(root, bound_element):
            state = self._read_switch_field_state(root)
            if state is not None:
                return "是" if state else "否"
        if self._looks_like_radio_field(root, bound_element):
            radio_value = self._read_radio_field_value(root)
            if radio_value:
                return radio_value
        if self._looks_like_checkbox_field(root, bound_element):
            state = self._read_checkbox_field_state(root)
            if state is not None:
                return "on" if state else "off"
            candidate = getattr(bound_element, "candidate", None)
            label = str(getattr(candidate, "label", "") or getattr(candidate, "fieldid", "") or "")
            suffix = f": {label}" if label else ""
            raise RuntimeError(f"checkbox 状态不可读{suffix}")
        locator = self._resolve_fill_locator(bound_element.runtime.selector)
        try:
            value = locator.input_value()
        except Exception:
            value = locator.text_content() or ""
        value = " ".join(str(value).split())
        label = str(getattr(bound_element.candidate, "label", "") or "")
        candidate_aliases = set(getattr(bound_element.candidate, "aliases", lambda: set())())
        normalized_value = "".join(value.split())
        normalized_aliases = {"".join(str(alias).split()) for alias in candidate_aliases}
        if value and normalized_value not in normalized_aliases:
            return value
        fallback = self._read_field_value_from_container(bound_element)
        if fallback:
            return fallback
        text_fallback = self._read_field_value_from_page_text(label or value)
        if text_fallback:
            return text_fallback
        return value

    def read_text(self, bound_element: BoundElement) -> str:
        return self._resolve_visible_locator(bound_element.runtime.selector).text_content() or ""

    def _apply_cookies(self) -> None:
        bridge = getattr(self.session, "_ydf_cookie_bridge", None)
        if bridge is not None:
            bridge.install()
            return
        parsed = urlparse(self.config.base_url)
        cookies = []
        for cookie in self.session.cookies:
            cookies.append(
                {
                    "name": cookie.name,
                    "value": cookie.value,
                    "domain": cookie.domain or parsed.hostname or "",
                    "path": cookie.path or "/",
                    "secure": bool(cookie.secure),
                    **({"expires": float(cookie.expires)} if cookie.expires else {}),
                }
            )
        if cookies:
            self._context.add_cookies(cookies)

    def _apply_api_session_cookies(self) -> None:
        if self._cookies_applied:
            return
        self._apply_cookies()
        self._cookies_applied = True

    def _wait_ready(self) -> None:
        page = self._require_page()
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            page.wait_for_timeout(1500)
        page.wait_for_timeout(1000)

    def _handle_response(self, response) -> None:
        if getattr(self.session, "_ydf_cookie_bridge", None) is not None:
            target = urlparse(self.config.base_url)
            actual = urlparse(str(getattr(response, "url", "") or ""))
            target_origin = (target.scheme, target.hostname, target.port or (443 if target.scheme == "https" else 80))
            actual_origin = (actual.scheme, actual.hostname, actual.port or (443 if actual.scheme == "https" else 80))
            if getattr(response, "status", None) == 401 and actual_origin == target_origin:
                self.session._ydf_auth_invalid = True
        self._page_response_events.append(
            {
                "method": str(getattr(getattr(response, "request", None), "method", "") or ""),
                "url": str(getattr(response, "url", "") or ""),
                "status": int(getattr(response, "status", 0) or 0),
                "response": response,
            }
        )
        self._capture_dynamic_template_response(response)
        self._capture_network_response(response)

    def _capture_dynamic_template_response(self, response) -> None:
        try:
            if response.request.method.upper() != "POST":
                return
            template_body_endpoint = getattr(
                self.config.endpoints,
                "template_body",
                "/yondif-ams-be/ytemplate/template/getTemplateBody",
            )
            endpoints = (self.config.endpoints.templates, template_body_endpoint)
            matched_endpoint = next((endpoint for endpoint in endpoints if endpoint and endpoint in response.url), None)
            if matched_endpoint is None:
                return
            if int(getattr(response, "status", 200) or 0) >= 400:
                return
            payload = response.json()
        except Exception:
            return
        normalized = _normalize_dynamic_template_payload(
            payload,
            source="template_body" if matched_endpoint == template_body_endpoint else "matching_template",
        )
        if normalized is not None:
            self._dynamic_template_payload = normalized

    def _capture_query_completion_request(self, request) -> None:
        identity = self._action_completion_context.get("target_table_query")
        if (not self._action_completion_active or self._action_completion_action != "query.search"
                or not identity or self._query_completion_frame is None):
            return
        try:
            if request.frame != self._query_completion_frame or request.method != "POST":
                return
            url = urlparse(request.url)
            if url.netloc != urlparse(self.config.base_url).netloc:
                return
            body = request.post_data_json
            if not isinstance(body, dict):
                return
            domain = str(identity["domain"]).removesuffix("-be")
            if url.path in {f"/{domain}/bill/list", f"/{domain}-be/bill/list"}:
                matches = body.get("busiObj") == identity["busi_obj"]
            elif url.path == f"/{domain}-be/ybill/query":
                matches = body.get("fullName") == identity["entity_uri"]
            else:
                matches = False
            if matches:
                self._query_completion_requests[id(request)] = (request, None)
        except Exception:
            return

    def _capture_network_request(self, request) -> None:
        self._capture_query_completion_request(request)
        self._capture_direct_import_network_request(request)
        if self.observation_session is not None:
            self.observation_session.network_request_started(
                request_key=id(request),
                original_url=_request_attr(request, "url"),
                actual_url=_request_attr(request, "url"),
                base_url=self.config.base_url,
                resource_type=_request_attr(request, "resource_type"),
                method=_request_attr(request, "method"),
                headers=_request_headers(request),
                body=_request_post_data_buffer(request),
                forwarding=self._request_forward_facts.get(id(request)),
            )
        if not self._performance_enabled:
            return
        request_id = id(request)
        self._network_request_started_at[request_id] = time.monotonic()
        self._record_or_update_network_event(request, response=None, failed=False, started=True)

    def _capture_network_response(self, response) -> None:
        self._capture_direct_import_network_response(response)
        if not self._performance_enabled:
            return
        request = getattr(response, "request", None)
        self._record_or_update_network_event(request, response=response, failed=False)

    def _capture_network_finished(self, request) -> None:
        if id(request) in self._query_completion_requests:
            success = False
            try:
                response = request.response()
                body = response.json() if 200 <= response.status < 300 else None
                success = (isinstance(body, dict) and str(body.get("code")) in {"0", "200"}
                           and body.get("success") is not False and isinstance(body.get("data"), (list, dict)))
            except Exception:
                pass
            self._query_completion_requests[id(request)] = (request, success)
        if self.observation_session is not None:
            response = _request_response(request)
            forwarding = self._request_forward_facts.pop(id(request), None)
            completed = getattr(self.observation_session, "network_request_completed", None)
            if completed is not None:
                response_headers = _response_headers(response)
                body = None
                body_read_error = None
                body_reader = getattr(response, "body", None)
                capture_allowed = getattr(self.observation_session, "response_body_capture_allowed", None)
                if callable(body_reader) and (capture_allowed is None or capture_allowed(response_headers)):
                    try:
                        body = body_reader()
                    except Exception as exc:
                        body_read_error = str(exc)
                completed(
                    request_key=id(request),
                    actual_url=str((forwarding or {}).get("actual_url") or _request_attr(response, "url") or _request_attr(request, "url")),
                    status=int(getattr(response, "status", 0) or 0),
                    headers=response_headers,
                    body=body,
                    forwarding=forwarding,
                    body_read_error=body_read_error,
                )
        if not self._performance_enabled:
            return
        self._record_or_update_network_event(
            request,
            response=_request_response(request),
            failed=False,
            completed=True,
        )

    def _capture_network_failure(self, request) -> None:
        if id(request) in self._query_completion_requests:
            self._query_completion_requests[id(request)] = (request, False)
        self._capture_direct_import_network_failure(request)
        if self.observation_session is not None:
            forwarding = self._request_forward_facts.pop(id(request), None)
            failed = getattr(self.observation_session, "network_request_failed", None)
            if failed is not None:
                failed(request_key=id(request), error=_request_failure_text(request), forwarding=forwarding)
        if not self._performance_enabled:
            return
        self._record_or_update_network_event(request, response=None, failed=True, completed=True)

    def _capture_console_event(self, message) -> None:
        try:
            item = {
                "type": str(getattr(message, "type", "") or ""),
                "text": str(getattr(message, "text", "") or "")[:1000],
                "location": getattr(message, "location", None),
                "time": time.time(),
            }
        except Exception:
            return
        self._console_events.append(item)
        self._console_events = self._console_events[-50:]
        if self.observation_session is not None:
            self.observation_session.record_console_error(
                message_type=item["type"],
                text=item["text"],
                location=item["location"],
            )

    def _capture_page_error(self, error) -> None:
        self._page_errors.append({"message": str(error)[:2000], "time": time.time()})
        if self.observation_session is not None:
            self.observation_session.record_page_error(
                message=str(getattr(error, "message", "") or error)[:2000],
                stack=str(getattr(error, "stack", "") or "")[:4000],
            )

    def _record_or_update_network_event(
        self,
        request,
        *,
        response=None,
        failed: bool,
        started: bool = False,
        completed: bool = False,
    ) -> None:
        request_id = id(request) if request is not None else 0
        started_at = self._network_request_started_at.get(request_id)
        now = time.monotonic()
        url = str(getattr(response, "url", "") or getattr(request, "url", "") or "")
        request_body_size, request_body_size_available, request_body_size_unavailable_reason = _request_body_size(request)
        event = {
            "url": url,
            "method": _request_attr(request, "method"),
            "resource_type": _request_attr(request, "resource_type"),
            "status": int(getattr(response, "status", 0) or 0),
            "encoded_body_size": _response_body_size(request, response),
            "request_body_size": request_body_size,
            "request_body_size_available": request_body_size_available,
            "request_body_size_unavailable_reason": request_body_size_unavailable_reason,
            "duration_ms": 0 if started else _request_duration_ms(request, started_at=started_at),
            "failed": failed,
            "request_id": request_id,
            "started_at_monotonic": started_at or now,
            "updated_at_monotonic": now,
            "step_context": "unknown",
        }
        event.update(_performance_step_context_payload(self._performance_step_context))
        if completed:
            completion = _performance_step_context_payload(self._performance_step_context)
            event.update(
                {
                    "completed_step_context": completion.get("step_context", "unknown"),
                    "completed_step_index": int(completion.get("step_index") or 0),
                    "completed_action": str(completion.get("action") or ""),
                }
            )
        if failed:
            event["error"] = _request_failure_text(request)
        event["category"] = _network_category(event["url"], event["resource_type"])
        if request_id and request_id in self._network_event_by_request_id:
            index = self._network_event_by_request_id[request_id]
            if 0 <= index < len(self._network_events):
                current = self._network_events[index]
                preserved_context = {
                    key: current.get(key)
                    for key in ("step_context", "suite_code", "case_code", "step_index", "action")
                    if current.get(key) not in (None, "")
                }
                current.update({key: value for key, value in event.items() if value not in {"", 0, False, None}})
                for key in (
                    "request_body_size",
                    "request_body_size_available",
                    "request_body_size_unavailable_reason",
                ):
                    current[key] = event[key]
                current.update(preserved_context)
                current["failed"] = failed
                current["duration_ms"] = max(int(current.get("duration_ms") or 0), int(event.get("duration_ms") or 0))
                return
        self._network_events.append(event)
        if request_id:
            self._network_event_by_request_id[request_id] = len(self._network_events) - 1

    def _capture_direct_import_network_request(self, request: Any) -> None:
        if self._direct_import_network_events is None:
            return
        method = _request_attr(request, "method").upper()
        resource_type = _request_attr(request, "resource_type").lower()
        if resource_type not in {"xhr", "fetch"}:
            return
        seed = _is_direct_import_seed_request(request, self._direct_import_filenames)
        if not self._direct_import_network_seeded and not seed:
            return
        if self._direct_import_network_seeded and method == "GET" and not seed:
            return
        self._direct_import_network_seeded = True
        now = time.monotonic()
        self._direct_import_last_activity = now
        self._direct_import_network_events[id(request)] = {
            "url": _request_attr(request, "url"),
            "method": method,
            "resource_type": resource_type,
            "status": 0,
            "failed": False,
            "error": "",
            "business_status": "",
            "message": "",
            "seed": seed,
            "updated_at_monotonic": now,
        }

    def _capture_direct_import_network_response(self, response: Any) -> None:
        if self._direct_import_network_events is None:
            return
        request = getattr(response, "request", None)
        event = self._direct_import_network_events.get(id(request))
        if event is None:
            return
        event["status"] = int(getattr(response, "status", 0) or 0)
        business_status, message = _direct_import_response_outcome(response)
        event["business_status"] = business_status
        event["message"] = message
        event["updated_at_monotonic"] = time.monotonic()
        self._direct_import_last_activity = event["updated_at_monotonic"]

    def _capture_direct_import_network_failure(self, request: Any) -> None:
        if self._direct_import_network_events is None:
            return
        event = self._direct_import_network_events.get(id(request))
        if event is None:
            return
        event["failed"] = True
        event["error"] = _request_failure_text(request)
        event["updated_at_monotonic"] = time.monotonic()
        self._direct_import_last_activity = event["updated_at_monotonic"]

    def _dismiss_privacy_dialog(self) -> None:
        try:
            self._page.get_by_role("button", name="接受").click(timeout=2000)
            self._page.wait_for_timeout(500)
        except Exception:
            return

    def _ensure_authenticated(self) -> None:
        page = self._require_page()
        self._dismiss_privacy_dialog()
        login_context, username_locator = self._first_visible_locator(build_login_probe_selectors()["username"], timeout=1500)
        if username_locator is None:
            return
        _, password_locator = self._first_visible_locator(
            build_login_probe_selectors()["password"],
            timeout=500,
            contexts=[login_context] if login_context is not None else None,
        )
        if password_locator is None:
            raise RuntimeError("浏览器登录失败: 未找到密码输入框")
        username_locator.fill(self.config.username)
        password_locator.fill(self.config.password)
        _, submit_locator = self._first_visible_locator(
            build_login_probe_selectors()["submit"],
            timeout=1500,
            contexts=[login_context] if login_context is not None else None,
        )
        if submit_locator is None:
            raise RuntimeError("浏览器登录失败: 未找到登录按钮")
        self._submit_login(submit_locator)
        try:
            username_locator.wait_for(state="hidden", timeout=20000)
        except Exception:
            page.wait_for_timeout(5000)
        self._wait_ready()

    def _first_visible_locator(self, selectors: list[str], timeout: int = 1000, contexts: list[Any] | None = None):
        search_contexts = contexts or self._all_search_contexts()
        for selector in selectors:
            for context in search_contexts:
                locator = context.locator(selector).first
                try:
                    locator.wait_for(state="visible", timeout=timeout)
                    return context, locator
                except Exception:
                    continue
        return None, None

    def _all_search_contexts(self) -> list[Any]:
        page = self._require_page()
        return [page, *getattr(page, "frames", [])]

    def _open_in_new_tab(self, url: str):
        previous_page = self._require_page()
        new_page = self._context.new_page()
        new_page.goto(url)
        self._page = new_page
        try:
            previous_page.close()
        except Exception:
            pass
        return new_page

    def _submit_login(self, submit_locator) -> None:
        for submit in (
            lambda: submit_locator.click(timeout=5000),
            lambda: submit_locator.click(force=True, timeout=5000),
            lambda: submit_locator.evaluate("(node) => node.click()"),
        ):
            try:
                submit()
                return
            except Exception:
                continue
        raise RuntimeError("浏览器登录失败: 无法提交登录表单")

    def _open_global_navigation(self) -> None:
        candidates = [
            '[fieldid="menu_img"]',
            '[id="menu_img"]',
            '[data-fieldid="menu_img"]',
        ]
        for selector in candidates:
            locator = self._page.locator(selector).first
            try:
                if locator.count() == 0:
                    continue
                locator.hover(timeout=3000)
                self._page.wait_for_timeout(1000)
                return
            except Exception:
                continue

    def _click_first(self, selectors: list[str]) -> None:
        if self._try_click_first(selectors):
            return
        raise RuntimeError(f"未找到可点击元素: {selectors}")

    def _try_click_first(self, selectors: list[str], context=None) -> bool:
        search_context = context or self._page
        for selector in selectors:
            locator = search_context.locator(selector).first
            try:
                if locator.count() == 0 or not locator.is_visible(timeout=500):
                    continue
                locator.click(timeout=3000)
                return True
            except Exception:
                continue
        return False

    def _try_check_tree_node(self, label: str, context=None) -> bool:
        if context is None and not hasattr(self._page, "locator"):
            return False
        root = context or self._page.locator("body").first
        if not hasattr(root, "evaluate") or not hasattr(root, "locator"):
            return False
        marker = f"ydf-tree-checkbox-{int(time.monotonic() * 1000)}"
        try:
            result = root.evaluate(
                """(root, args) => {
                    const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                    const expected = normalize(args.label);
                    if (!expected) return { found: false, selected: false, selector: '' };
                    const visible = (el) => {
                      if (!el || !el.ownerDocument || !el.isConnected) return false;
                      const style = el.ownerDocument.defaultView.getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style && style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width > 0 && rect.height > 0
                        && rect.bottom >= 0 && rect.right >= 0
                        && rect.top <= el.ownerDocument.defaultView.innerHeight
                        && rect.left <= el.ownerDocument.defaultView.innerWidth;
                    };
                    const rootEl = root && root.querySelectorAll ? root : document.body;
                    for (const old of Array.from(rootEl.querySelectorAll('[data-ydf-browser-tree-checkbox-target]'))) {
                      old.removeAttribute('data-ydf-browser-tree-checkbox-target');
                    }
                    const nodeSelector = [
                      '.wui-tree-treenode',
                      '.wui-select-tree-treenode',
                      '.ant-tree-treenode',
                      '.u-tree-treenode',
                      '[role="treeitem"]',
                      'li'
                    ].join(',');
                    const labelSelector = [
                      '.wui-tree-title',
                      '.wui-select-tree-title',
                      '.ant-tree-title',
                      '.u-tree-title',
                      '.wui-tree-node-content-wrapper',
                      '.wui-select-tree-node-content-wrapper',
                      '.ant-tree-node-content-wrapper',
                      '.u-tree-node-content-wrapper',
                      '[title]',
                      '[role="treeitem"]',
                      'span',
                      'a',
                      'div'
                    ].join(',');
                    const textMatches = (el, exactOnly = true) => {
                      const title = normalize(el.getAttribute && el.getAttribute('title'));
                      const text = normalize(el.innerText || el.textContent);
                      if (title === expected || text === expected) return true;
                      return !exactOnly && expected && text.includes(expected);
                    };
                    const nodes = [];
                    const pushNode = (node) => {
                      if (!node || nodes.includes(node) || !visible(node)) return;
                      nodes.push(node);
                    };
                    for (const labelEl of Array.from(rootEl.querySelectorAll(labelSelector))) {
                      if (!visible(labelEl) || !textMatches(labelEl, true)) continue;
                      pushNode(labelEl.closest(nodeSelector) || labelEl);
                    }
                    if (!nodes.length) {
                      for (const node of Array.from(rootEl.querySelectorAll(nodeSelector))) {
                        if (!visible(node) || !textMatches(node, false)) continue;
                        pushNode(node);
                      }
                    }
                    const controlSelector = [
                      'input[type="checkbox"]',
                      'input[type="radio"]',
                      '[role="checkbox"]',
                      '[role="radio"]',
                      '.wui-checkbox-wrapper',
                      '.ant-checkbox-wrapper',
                      '.u-checkbox-wrapper',
                      '[class*="checkbox-wrapper"]',
                      '[class*="CheckboxWrapper"]',
                      '[class*="radio-wrapper"]',
                      '[class*="RadioWrapper"]',
                      '.wui-checkbox',
                      '.ant-checkbox',
                      '.u-checkbox',
                      '[class*="checkbox"]',
                      '[class*="Checkbox"]',
                      '[class*="radio"]',
                      '[class*="Radio"]'
                    ].join(',');
                    const isDisabled = (el) => {
                      const className = String(el.className || '').toLowerCase();
                      return el.disabled === true
                        || el.getAttribute('disabled') != null
                        || el.getAttribute('aria-disabled') === 'true'
                        || /disabled/.test(className);
                    };
                    const isTreeSwitcher = (el) => {
                      const className = String(el.className || '').toLowerCase();
                      return /switcher|expand|collapse/.test(className) && !/checkbox|radio/.test(className);
                    };
                    const controlScore = (el) => {
                      const tag = String(el.tagName || '').toLowerCase();
                      const type = String(el.getAttribute('type') || '').toLowerCase();
                      const role = String(el.getAttribute('role') || '').toLowerCase();
                      const className = String(el.className || '').toLowerCase();
                      if (tag === 'input' && (type === 'checkbox' || type === 'radio')) return 0;
                      if (role === 'checkbox' || role === 'radio') return 1;
                      if (/checkbox-wrapper|radio-wrapper/.test(className)) return 2;
                      if (/checkbox|radio/.test(className)) return 3;
                      return 9;
                    };
                    const selected = (el) => {
                      if (!el) return false;
                      const tag = String(el.tagName || '').toLowerCase();
                      const type = String(el.getAttribute('type') || '').toLowerCase();
                      if (tag === 'input' && (type === 'checkbox' || type === 'radio') && el.checked === true) return true;
                      const aria = String(el.getAttribute && el.getAttribute('aria-checked') || '').toLowerCase();
                      if (['true', '1', 'checked'].includes(aria)) return true;
                      const className = String(el.className || '').toLowerCase();
                      return /(^|[-_\\s])(checked|selected|active)([-_\\s]|$)/.test(className);
                    };
                    const nearestVisibleClickTarget = (control, input) => {
                      const candidates = [
                        control,
                        control.closest && control.closest('.wui-checkbox-wrapper, .ant-checkbox-wrapper, .u-checkbox-wrapper, [class*="checkbox-wrapper"], [class*="CheckboxWrapper"], .wui-radio-wrapper, .ant-radio-wrapper, .u-radio-wrapper, [class*="radio-wrapper"], [class*="RadioWrapper"], label'),
                        input && input.closest && input.closest('label'),
                        input && input.parentElement,
                        control.parentElement,
                      ].filter(Boolean);
                      return candidates.find(visible) || input || control;
                    };
                    for (const node of nodes) {
                      const controls = Array.from(node.querySelectorAll(controlSelector))
                        .filter((el) => !isDisabled(el) && !isTreeSwitcher(el))
                        .sort((a, b) => controlScore(a) - controlScore(b));
                      for (const control of controls) {
                        const input = control.matches('input[type="checkbox"], input[type="radio"]')
                          ? control
                          : control.querySelector('input[type="checkbox"], input[type="radio"]');
                        if (selected(control) || selected(input)) {
                          return { found: true, selected: true, selector: '' };
                        }
                        const target = nearestVisibleClickTarget(control, input);
                        if (!target) continue;
                        target.setAttribute('data-ydf-browser-tree-checkbox-target', args.marker);
                        return {
                          found: true,
                          selected: false,
                          selector: `[data-ydf-browser-tree-checkbox-target="${args.marker}"]`
                        };
                      }
                    }
                    return { found: false, selected: false, selector: '' };
                }""",
                {"label": label, "marker": marker},
            )
        except Exception:
            return False
        if not isinstance(result, dict) or not result.get("found"):
            return False
        if result.get("selected"):
            return True
        selector = str(result.get("selector") or "")
        if not selector:
            return False
        target = root.locator(selector).first
        try:
            target.click(timeout=3000)
            return True
        except Exception:
            try:
                target.click(force=True, timeout=3000)
                return True
            except Exception:
                pass
        try:
            return bool(
                root.evaluate(
                    """(root, marker) => {
                        const target = root.querySelector(`[data-ydf-browser-tree-checkbox-target="${marker}"]`);
                        if (!target) return false;
                        target.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                        target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                        target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                        target.click();
                        target.dispatchEvent(new Event('input', { bubbles: true }));
                        target.dispatchEvent(new Event('change', { bubbles: true }));
                        return true;
                    }""",
                    marker,
                )
            )
        except Exception:
            return False

    def _hover_first(self, selectors: list[str]) -> None:
        for selector in selectors:
            locator = self._page.locator(selector).first
            try:
                if locator.count() == 0 or not locator.is_visible(timeout=500):
                    continue
                locator.hover(timeout=3000)
                return
            except Exception:
                continue
        raise RuntimeError(f"未找到可悬停元素: {selectors}")

    def _hover_row_by_all_text(self, values: list[str]) -> None:
        page = self._require_page()
        for row_selector in build_table_data_row_selectors():
            rows = page.locator(row_selector)
            try:
                count = rows.count()
            except Exception:
                continue
            for index in range(count):
                row = rows.nth(index)
                try:
                    if not row.is_visible(timeout=300):
                        continue
                    text = " ".join((row.inner_text(timeout=500) or "").split())
                    if all(value in text for value in values):
                        row.hover(timeout=3000)
                        page.wait_for_timeout(800)
                        return
                except Exception:
                    continue
        self._expand_table_tree_until_row_visible(values[0])
        for row_selector in build_table_data_row_selectors():
            rows = page.locator(row_selector)
            try:
                count = rows.count()
            except Exception:
                continue
            for index in range(count):
                row = rows.nth(index)
                try:
                    if not row.is_visible(timeout=300):
                        continue
                    text = " ".join((row.inner_text(timeout=500) or "").split())
                    if all(value in text for value in values):
                        row.hover(timeout=3000)
                        page.wait_for_timeout(800)
                        return
                except Exception:
                    continue
        raise RuntimeError(f"未找到同时包含这些文本的表格行: {values}")

    def _click_row_checkbox_by_text(
        self,
        text: str,
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
    ) -> None:
        row = (
            self._find_visible_table_data_row(
                text,
                table=table,
                table_fieldid=table_fieldid,
                table_columns=table_columns,
            )
            if table or table_fieldid
            else self._find_visible_table_data_row(text)
        )
        if row is not None and self._try_click_row_checkbox(row):
            return
        if (table or table_fieldid) and row is not None and self._try_click_table_row_for_selection(row):
            return
        row_click_not_confirmed = _table_row_click_not_confirmed(self.last_table_selection_debug)
        self._expand_table_tree_until_row_visible(
            text,
            table=table,
            table_fieldid=table_fieldid,
            table_columns=table_columns,
        )
        row = (
            self._find_visible_table_data_row(
                text,
                table=table,
                table_fieldid=table_fieldid,
                table_columns=table_columns,
            )
            if table or table_fieldid
            else self._find_visible_table_data_row(text)
        )
        if row is not None and self._try_click_row_checkbox(row):
            return
        if (table or table_fieldid) and row is not None and self._try_click_table_row_for_selection(row):
            return
        failure = "已点击业务行但未确认表格行选中" if row_click_not_confirmed else "未找到表格行选择框"
        message = self._format_table_selection_failure(
            f"{failure}: {text}",
            table=table,
            table_fieldid=table_fieldid,
            column=None,
        )
        raise RuntimeError(message)

    def _click_row_checkbox_by_match_values(
        self,
        values: list[str],
        column: str | None = None,
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        match: dict[str, Any] | None = None,
    ) -> None:
        scoped = bool(table or table_fieldid or table_columns or getattr(self, "_active_table_scope", None))
        clean_values = [" ".join(str(value).split()) for value in values if " ".join(str(value).split())]
        if not clean_values:
            raise RuntimeError(f"未找到表格行选择框: {values}")
        if len(clean_values) == 1 and not column:
            if table or table_fieldid:
                self._click_row_checkbox_by_text(
                    clean_values[0],
                    table=table,
                    table_fieldid=table_fieldid,
                    table_columns=table_columns,
                )
            else:
                self._click_row_checkbox_by_text(clean_values[0])
            return
        row = (
            self._find_visible_table_data_row_by_values(
                clean_values,
                column=column,
                table=table,
                table_fieldid=table_fieldid,
                table_columns=table_columns,
                match=match,
            )
            if table or table_fieldid
            else self._find_visible_table_data_row_by_values(clean_values, column=column, match=match)
        )
        if row is not None and self._try_click_row_checkbox(row):
            return
        if row is not None and scoped and self._try_click_table_row_for_selection(row):
            return
        if row is not None:
            failure = (
                "已点击业务行但未确认表格行选中"
                if _table_row_click_not_confirmed(self.last_table_selection_debug)
                else "未找到表格行选择框"
            )
            message = self._format_table_selection_failure(
                f"{failure}: {_format_column_match_for_error(column, clean_values)}",
                table=table,
                table_fieldid=table_fieldid,
                column=column,
            )
            raise RuntimeError(message)
        self._expand_table_tree_until_values_visible(
            clean_values,
            column=column,
            table=table,
            table_fieldid=table_fieldid,
            table_columns=table_columns,
            match=match,
        )
        row = (
            self._find_visible_table_data_row_by_values(
                clean_values,
                column=column,
                table=table,
                table_fieldid=table_fieldid,
                table_columns=table_columns,
                match=match,
            )
            if table or table_fieldid
            else self._find_visible_table_data_row_by_values(clean_values, column=column, match=match)
        )
        if row is not None and self._try_click_row_checkbox(row):
            return
        if row is not None and scoped and self._try_click_table_row_for_selection(row):
            return
        if row is not None:
            failure = (
                "已点击业务行但未确认表格行选中"
                if _table_row_click_not_confirmed(self.last_table_selection_debug)
                else "未找到表格行选择框"
            )
        else:
            failure = "未找到匹配表格行"
        message = self._format_table_selection_failure(
            f"{failure}: {_format_column_match_for_error(column, clean_values)}",
            table=table,
            table_fieldid=table_fieldid,
            column=column,
        )
        raise RuntimeError(message)

    def _expand_table_tree_until_row_visible(
        self,
        text: str,
        max_rounds: int = 200,
        column: str | None = None,
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        match: dict[str, Any] | None = None,
    ) -> None:
        self._expand_table_tree_until_values_visible(
            [text],
            max_rounds=max_rounds,
            column=column,
            table=table,
            table_fieldid=table_fieldid,
            table_columns=table_columns,
        )

    def _expand_table_tree_until_values_visible(
        self,
        values: list[str],
        max_rounds: int = 200,
        column: str | None = None,
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        match: dict[str, Any] | None = None,
    ) -> None:
        page = self._require_page()
        scoped = bool(table or table_fieldid or table_columns or getattr(self, "_active_table_scope", None))

        def tree_context():
            if not scoped:
                return page
            return self._table_selection_context(
                table,
                table_fieldid=table_fieldid,
                table_columns=table_columns,
                require_selectable_rows=False,
            )

        started_at = time.monotonic()
        target_values = [" ".join(str(value).split()) for value in values if " ".join(str(value).split())]
        if not target_values:
            return
        target_text = target_values[0]
        stats_target = target_text if len(target_values) == 1 else target_values
        stats: dict[str, Any] = {
            "target": stats_target,
            "table": table,
            "table_fieldid": table_fieldid,
            "expanded": 0,
            "scrolled": 0,
            "found": False,
            "elapsed_ms": 0,
        }
        if column:
            stats["column"] = column
        target_code = _leading_code(target_text) if len(target_values) == 1 else ""
        expanded_keys: set[str] = set()
        stalled_attempt_limit = 2
        stalled_attempts: dict[str, int] = {}

        def target_visible() -> bool:
            if len(target_values) == 1:
                return self._find_visible_table_data_row(
                    target_text,
                    table=table,
                    table_fieldid=table_fieldid,
                    table_columns=table_columns,
                ) is not None
            return self._find_visible_table_data_row_by_values(
                target_values,
                table=table,
                table_fieldid=table_fieldid,
                table_columns=table_columns,
                match=match,
            ) is not None

        def target_visible_with_column() -> bool:
            if len(target_values) == 1:
                return self._find_visible_table_data_row(
                    target_text,
                    column=column,
                    table=table,
                    table_fieldid=table_fieldid,
                    table_columns=table_columns,
                ) is not None
            return self._find_visible_table_data_row_by_values(
                target_values,
                column=column,
                table=table,
                table_fieldid=table_fieldid,
                table_columns=table_columns,
                match=match,
            ) is not None

        def record_found() -> None:
            stats["found"] = True
            stats["elapsed_ms"] = round((time.monotonic() - started_at) * 1000)
            self.last_table_tree_search = stats

        def record_expanded(candidate_key: str) -> None:
            if candidate_key not in expanded_keys:
                expanded_keys.add(candidate_key)
                stats["expanded"] += 1

        for _ in range(max_rounds):
            if target_visible():
                record_found()
                return
            if column and stats["expanded"] and stats["expanded"] % 20 == 0 and target_visible_with_column():
                record_found()
                return
            expanded = False
            attempted_unexpanded = False
            context = tree_context()
            if column:
                self._scroll_table_left(context=context)
            for selector in build_table_tree_expand_selectors():
                candidates = self._visible_table_tree_expanders(selector, context=context)
                if target_code:
                    candidates = [candidate for candidate in candidates if self._is_related_table_tree_expander(candidate, target_code)]
                else:
                    candidates = [candidate for candidate in candidates if self._table_tree_expander_key(candidate) not in expanded_keys]
                if target_code and not candidates:
                    continue
                for candidate in candidates:
                    try:
                        candidate_key = self._table_tree_expander_key(candidate)
                        if stalled_attempts.get(candidate_key, 0) >= stalled_attempt_limit:
                            continue
                        before_rows = self._visible_table_row_signature(context=context)
                        if self._click_table_tree_expander(candidate):
                            page.wait_for_timeout(400)
                            if target_visible():
                                record_expanded(candidate_key)
                                record_found()
                                return
                            context = tree_context()
                            after_click_rows = self._visible_table_row_signature(context=context)
                            if after_click_rows != before_rows:
                                record_expanded(candidate_key)
                                expanded = True
                                break
                            if self._table_tree_expander_still_collapsed(candidate, candidate_key):
                                before_dispatch_rows = after_click_rows
                                if self._dispatch_table_tree_expander_click(candidate):
                                    page.wait_for_timeout(400)
                                if target_visible():
                                    record_expanded(candidate_key)
                                    record_found()
                                    return
                                if self._visible_table_row_signature(context=context) != before_dispatch_rows:
                                    record_expanded(candidate_key)
                                    expanded = True
                                    break
                                if self._table_tree_expander_still_collapsed(candidate, candidate_key):
                                    stalled_attempts[candidate_key] = stalled_attempts.get(candidate_key, 0) + 1
                                    if stalled_attempts[candidate_key] < stalled_attempt_limit:
                                        attempted_unexpanded = True
                                        break
                                    continue
                            record_expanded(candidate_key)
                            expanded = True
                            if target_visible():
                                record_found()
                                return
                            break
                    except Exception:
                        continue
                if expanded or attempted_unexpanded:
                    break
            if attempted_unexpanded:
                continue
            if not expanded:
                if column and target_visible_with_column():
                    record_found()
                    return
                context = tree_context()
                if column:
                    self._scroll_table_left(context=context)
                if self._scroll_table_down(context=context):
                    stats["scrolled"] += 1
                    page.wait_for_timeout(500)
                    continue
                break
        stats["found"] = target_visible() or bool(column and target_visible_with_column())
        stats["elapsed_ms"] = round((time.monotonic() - started_at) * 1000)
        self.last_table_tree_search = stats

    def _is_visible_table_data_row(self, text: str, column: str | None = None) -> bool:
        return self._find_visible_table_data_row(text, column=column) is not None

    def _hover_visible_table_data_row(self, text: str, column: str | None = None) -> None:
        row = self._find_visible_table_data_row(text, column=column)
        if row is None:
            raise RuntimeError(f"未找到可见表格行: {text}")
        self._scroll_table_row_into_stable_view(row)
        row.hover(timeout=3000)

    def _find_visible_table_data_row(
        self,
        text: str,
        column: str | None = None,
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        match: dict[str, Any] | None = None,
    ):
        context = self._table_selection_context(table, table_fieldid=table_fieldid, table_columns=table_columns)
        expected = " ".join(str(text).split())
        if column and not self._scroll_table_column_into_view(column):
            return None
        for row_selector in _table_data_row_selectors(scoped=bool(table or table_fieldid or table_columns)):
            rows = context.locator(row_selector)
            try:
                count = rows.count()
            except Exception:
                continue
            for index in range(count):
                row = rows.nth(index)
                try:
                    if not row.is_visible(timeout=300):
                        continue
                    row_text = " ".join((row.inner_text(timeout=500) or "").split())
                    if expected and expected in row_text:
                        return row
                except Exception:
                    continue
        return None

    def _find_visible_table_data_row_by_values(
        self,
        values: list[str],
        column: str | None = None,
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        match: dict[str, Any] | None = None,
    ):
        context = self._table_selection_context(table, table_fieldid=table_fieldid, table_columns=table_columns)
        expected_values = [" ".join(str(value).split()) for value in values if " ".join(str(value).split())]
        if not expected_values:
            return None
        if column:
            marker = f"table-row-match-{int(time.monotonic() * 1000000)}"
            row_match = match if isinstance(match, dict) and match else {"column": column, "equals": expected_values[0]}
            columns = _row_match_columns(row_match) or [column]
            payload = {
                "match": row_match,
                "matchValues": expected_values,
                "columns": columns,
                "table": table,
                "tableFieldid": table_fieldid,
                "tableColumns": table_columns or [],
                "selectorMarker": marker,
            }
            try:
                result = context.evaluate(_TABLE_ROW_VALUES_SCRIPT, payload)
            except Exception:
                result = {}
            selector = str((result or {}).get("__selector") or "").strip() if isinstance(result, dict) else ""
            if selector:
                return context.locator(selector).first
            return None
        for row_selector in _table_data_row_selectors(scoped=bool(table or table_fieldid or table_columns)):
            rows = context.locator(row_selector)
            try:
                count = rows.count()
            except Exception:
                continue
            for index in range(count):
                row = rows.nth(index)
                try:
                    if not row.is_visible(timeout=300):
                        continue
                    row_text = " ".join((row.inner_text(timeout=500) or "").split())
                    if all(value in row_text for value in expected_values):
                        return row
                except Exception:
                    continue
        return None

    def _scroll_table_column_into_view(self, column: str) -> bool:
        page = self._require_page()
        for _ in range(12):
            try:
                if page.evaluate(_TABLE_COLUMN_VISIBLE_SCRIPT, column):
                    return True
                if not page.evaluate(_SCROLL_TABLE_RIGHT_SCRIPT):
                    return False
                page.wait_for_timeout(250)
            except Exception:
                return False
        return False

    def _scroll_table_row_into_stable_view(self, row) -> None:
        page = self._require_page()
        try:
            row.evaluate("(node) => node.scrollIntoView({ block: 'center', inline: 'nearest' })")
            page.wait_for_timeout(300)
        except Exception:
            return

    def _visible_table_tree_expanders(self, selector: str, context=None) -> list[Any]:
        locator = (context or self._require_page()).locator(selector)
        try:
            count = locator.count()
        except Exception:
            return []
        candidates = []
        for index in range(count):
            candidate = locator.nth(index)
            try:
                if candidate.is_visible(timeout=300):
                    candidates.append(candidate)
            except Exception:
                continue
        return candidates

    def _visible_table_row_signature(self, context=None) -> tuple[str, ...]:
        rows = (context or self._require_page()).locator(
            "tbody tr, [role='row'], .ant-table-row, .wui-table-row, .u-table-row"
        )
        try:
            count = rows.count()
        except Exception:
            return ()
        signature: list[str] = []
        for index in range(min(count, 80)):
            row = rows.nth(index)
            try:
                if not row.is_visible(timeout=100):
                    continue
                signature.append(" ".join((row.inner_text(timeout=200) or "").split()))
            except Exception:
                continue
        return tuple(signature)

    def _is_related_table_tree_expander(self, candidate, target_code: str) -> bool:
        candidate_code = _leading_code(self._table_tree_expander_text(candidate))
        return bool(candidate_code and candidate_code != target_code and target_code.startswith(candidate_code))

    def _table_tree_expander_text(self, candidate) -> str:
        try:
            return str(
                candidate.evaluate(
                    """(node) => {
                        const row = node.closest('tr, [role="row"], .ant-table-row, .wui-table-row, .u-table-row') || node;
                        return (row.innerText || row.textContent || '').replace(/\\s+/g, ' ').trim();
                    }"""
                )
            )
        except Exception:
            return ""

    def _table_tree_expander_key(self, candidate) -> str:
        text = " ".join(self._table_tree_expander_text(candidate).split())
        return text or str(id(candidate))

    def _table_tree_expander_still_collapsed(self, candidate, key: str) -> bool:
        if not key:
            return False
        try:
            return bool(
                candidate.evaluate(
                    """(node) => {
                        const row = node.closest('tr, [role="row"], .ant-table-row, .wui-table-row, .u-table-row') || node;
                        const classText = [node.className || '', row.className || ''].join(' ');
                        const ariaExpanded = node.getAttribute('aria-expanded') || row.getAttribute('aria-expanded') || '';
                        if (ariaExpanded === 'true') return false;
                        if (/(^|\\s|_|-)expanded($|\\s|_|-)/i.test(classText) && !/(collapsed|close)/i.test(classText)) return false;
                        if (/(^|\\s|_|-)(open|down)($|\\s|_|-)/i.test(classText) && !/(collapsed|close|right)/i.test(classText)) return false;
                        const collapsedMarker = row.querySelector(
                            '.wui-table-row-expand-icon-collapsed, .ant-table-row-expand-icon-collapsed, .u-table-row-expand-icon-collapsed, ' +
                            '[class*="expand-icon"][class*="collapsed"], [class*="tree-switcher"][class*="close"], ' +
                            '[class*="switcher"][class*="close"], [class*="uf-triangle-right"], button[aria-expanded="false"]'
                        );
                        return Boolean(collapsedMarker);
                    }"""
                )
            )
        except Exception:
            return False

    def _dispatch_table_tree_expander_click(self, candidate) -> bool:
        try:
            candidate.evaluate(
                """(node) => {
                    const target = node.matches && node.matches('.expand-icon-con, .switcher-icon, .uf-triangle-right')
                        ? node
                        : (node.querySelector('.expand-icon-con, .switcher-icon, .uf-triangle-right') || node);
                    target.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                    target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                    target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                    target.click();
                }"""
            )
            return True
        except Exception:
            return False

    def _scroll_table_down(self, context=None) -> bool:
        try:
            return bool((context or self._require_page()).evaluate(_SCROLL_TABLE_DOWN_SCRIPT))
        except Exception:
            return False

    def _scroll_table_left(self, context=None) -> bool:
        try:
            return bool((context or self._require_page()).evaluate(_SCROLL_TABLE_LEFT_SCRIPT))
        except Exception:
            return False

    def _click_table_tree_expander(self, candidate) -> bool:
        try:
            position = candidate.evaluate(
                """(node) => {
                    const icon = node.matches && node.matches('.expand-icon-con, .switcher-icon, .uf-triangle-right')
                        ? node
                        : node.querySelector('.expand-icon-con, .switcher-icon, .uf-triangle-right');
                    if (!icon) return null;
                    const nodeRect = node.getBoundingClientRect();
                    const iconRect = icon.getBoundingClientRect();
                    return {
                        x: Math.max(1, iconRect.left - nodeRect.left + iconRect.width / 2),
                        y: Math.max(1, iconRect.top - nodeRect.top + iconRect.height / 2),
                    };
                }"""
            )
            if position:
                candidate.click(position=position, force=True, timeout=2000)
                return True
        except Exception:
            pass
        try:
            candidate.click(position={"x": 16, "y": 17}, timeout=2000)
            return True
        except Exception:
            pass
        try:
            candidate.click(timeout=2000)
            return True
        except Exception:
            pass
        try:
            candidate.click(force=True, timeout=2000)
            return True
        except Exception:
            pass
        try:
            candidate.evaluate(
                """(node) => {
                    node.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
                    node.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                    node.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                    node.click();
                }"""
            )
            return True
        except Exception:
            return False

    def _click_row_checkbox_by_index(
        self,
        row_number: int,
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
    ) -> None:
        if row_number < 1:
            raise RuntimeError(f"表格行号从 1 开始: {row_number}")
        scoped = bool(table or table_fieldid or table_columns or getattr(self, "_active_table_scope", None))
        context = self._table_selection_context(table, table_fieldid=table_fieldid, table_columns=table_columns)
        max_visible_selectable_count = 0
        max_visible_data_count = 0
        selector_summaries: list[str] = []
        for row_selector in _table_data_row_selectors(scoped=scoped):
            rows = context.locator(row_selector)
            try:
                count = rows.count()
            except Exception:
                continue
            visible_selectable_index = 0
            for index in range(count):
                row = rows.nth(index)
                try:
                    if not row.is_visible(timeout=500):
                        continue
                    if not self._row_looks_like_table_data_row(row):
                        continue
                    if not self._row_has_receivable_cell(row):
                        continue
                    if not self._row_has_selection_checkbox(row):
                        continue
                except Exception:
                    continue
                visible_selectable_index += 1
                if visible_selectable_index != row_number:
                    continue
                if self._try_click_row_checkbox(row):
                    self.last_table_selection_debug = {
                        "strategy": "checkbox",
                        "selected_after": True,
                        "row_number": row_number,
                        "row_selector": row_selector,
                        "selectable_index": visible_selectable_index,
                    }
                    self._attach_table_root_selection_debug()
                    self._capture_table_selection_debug(
                        table=table,
                        row_number=row_number,
                        row_selector=row_selector,
                        selectable_index=visible_selectable_index,
                    )
                    return
                break
            max_visible_selectable_count = max(max_visible_selectable_count, visible_selectable_index)
            if count or visible_selectable_index:
                selector_summaries.append(f"{row_selector}: rows={count}, selectable={visible_selectable_index}")
        if scoped:
            for row_selector in _table_data_row_selectors(scoped=True):
                rows = context.locator(row_selector)
                try:
                    count = rows.count()
                except Exception:
                    continue
                visible_data_index = 0
                for index in range(count):
                    row = rows.nth(index)
                    try:
                        if not row.is_visible(timeout=500):
                            continue
                        if not self._row_looks_like_table_data_row(row):
                            continue
                        if not self._row_has_receivable_cell(row):
                            continue
                    except Exception:
                        continue
                    visible_data_index += 1
                    if visible_data_index != row_number:
                        continue
                    if self._try_click_table_row_for_selection(row):
                        if self.last_table_selection_debug is not None:
                            self.last_table_selection_debug.update(
                                {
                                    "row_number": row_number,
                                    "row_selector": row_selector,
                                    "selectable_index": visible_data_index,
                                }
                            )
                            self._attach_table_root_selection_debug()
                        self._capture_table_selection_debug(
                            table=table,
                            row_number=row_number,
                            row_selector=row_selector,
                            selectable_index=visible_data_index,
                        )
                        return
                    break
                max_visible_data_count = max(max_visible_data_count, visible_data_index)
        details = (
            f"目标行号={row_number}; 当前可见可勾选行数={max_visible_selectable_count}; "
            f"当前可见有效行数={max_visible_data_count}"
        )
        if table:
            details = f"{details}; 表格={table}"
        if table and self.last_table_selection_root:
            root = self.last_table_selection_root
            details = (
                f"{details}; 表格根="
                f"source={root.get('source')}, fieldid={root.get('fieldid')}, "
                f"tag={root.get('tag')}, class={root.get('className')}, "
                f"rows={root.get('rows')}, selectableRows={root.get('selectableRows')}, "
                f"text={root.get('text')}"
            )
        if selector_summaries:
            details = f"{details}; 选择器统计: {' | '.join(selector_summaries[:3])}"
        if _table_row_click_not_confirmed(self.last_table_selection_debug):
            details = f"{details}; 已点击业务行但未确认表格行选中"
        if self.last_table_selection_debug:
            debug_text = json.dumps(self.last_table_selection_debug, ensure_ascii=False, default=str)
            details = f"{details}; selection_debug={debug_text[:1800]}"
        raise RuntimeError(f"未找到表格行选择框: {details}")

    def _row_has_selection_checkbox(self, row) -> bool:
        for checkbox_selector in build_row_selection_checkbox_selectors():
            try:
                if row.locator(checkbox_selector).count() > 0:
                    return True
            except Exception:
                continue
        return False

    def _row_has_receivable_cell(self, row) -> bool:
        try:
            return bool(
                row.evaluate(
                    """(row) => {
                        const visible = (el) => {
                            if (!el || !el.getBoundingClientRect) return false;
                            const style = window.getComputedStyle(el);
                            const rect = el.getBoundingClientRect();
                            return style && style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                        };
                        const cells = Array.from(row.querySelectorAll('td, [role="gridcell"], .wui-table-cell, .ant-table-cell, .u-table-cell, .el-table__cell'))
                            .filter(visible)
                            .filter((item) => !item.closest('thead, .ant-table-header, .wui-table-header, .u-table-header, .el-table__header'));
                        for (const cell of cells) {
                            const rect = cell.getBoundingClientRect();
                            const points = [
                                [rect.left + Math.min(Math.max(rect.width / 2, 8), 24), rect.top + rect.height / 2],
                                [rect.left + rect.width / 2, rect.top + rect.height / 2],
                            ];
                            for (const [x, y] of points) {
                                if (x < 0 || y < 0 || x > window.innerWidth || y > window.innerHeight) continue;
                                const top = document.elementFromPoint(x, y);
                                if (top && (cell === top || cell.contains(top) || top.contains(cell))) return true;
                            }
                        }
                        return false;
                    }"""
                )
            )
        except Exception:
            return True

    def _try_click_row_checkbox(self, row) -> bool:
        row_text = _table_row_debug_text(row)
        for checkbox_selector in build_row_selection_checkbox_selectors():
            try:
                checkbox = row.locator(checkbox_selector).first
                if checkbox.count() == 0:
                    continue
                checkbox.click(timeout=3000)
                selected = self._confirm_checkbox_selected(checkbox, row=row)
                self.last_table_selection_debug = {"strategy": "checkbox", "selected_after": selected}
                if row_text:
                    self.last_table_selection_debug["row_text"] = row_text
                self._attach_table_root_selection_debug()
                return selected
            except Exception:
                scope = getattr(self, "_active_table_scope", None)
                if scope is not None:
                    self._table_scope_context(scope)
                try:
                    checkbox.click(force=True, timeout=3000)
                    selected = self._confirm_checkbox_selected(checkbox, row=row)
                    self.last_table_selection_debug = {"strategy": "checkbox", "selected_after": selected}
                    if row_text:
                        self.last_table_selection_debug["row_text"] = row_text
                    self._attach_table_root_selection_debug()
                    return selected
                except Exception:
                    continue
        if self._try_click_aligned_row_checkbox(row):
            self.last_table_selection_debug = {"strategy": "checkbox", "selected_after": True}
            if row_text:
                self.last_table_selection_debug["row_text"] = row_text
            self._attach_table_root_selection_debug()
            return True
        return False

    def _try_click_aligned_row_checkbox(self, row) -> bool:
        marker = f"row-checkbox-{int(time.monotonic() * 1000000)}"
        try:
            selector = row.evaluate(
                """(row, marker) => {
                    const visible = (el) => {
                        if (!el || !el.getBoundingClientRect) return false;
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style && style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                    };
                    const rowRect = row.getBoundingClientRect();
                    const localRoot = row.closest('[data-ydf-browser-table-selection-root]');
                    const tableRoot = row.closest('.wui-table, .ant-table, .u-table, .el-table, [role="grid"], [class*="Table"], [class*="table"]');
                    const scopeRoot = row.closest('[data-ydf-table-scope-token]');
                    const searchRoots = scopeRoot ? [scopeRoot] : [localRoot, tableRoot, document].filter(Boolean);
                    const checkboxSelector = [
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
                    ].join(',');
                    const centerY = rowRect.top + rowRect.height / 2;
                    let target = null;
                    for (const root of searchRoots) {
                        const candidates = Array.from(root.querySelectorAll(checkboxSelector))
                            .filter(visible)
                            .filter((item) => !item.closest('thead, .ant-table-header, .wui-table-header, .u-table-header, .el-table__header'))
                            .map((item) => ({ item, rect: item.getBoundingClientRect() }))
                            .filter(({ rect }) => centerY >= rect.top - 4 && centerY <= rect.bottom + 4)
                            .sort((a, b) => Math.abs((a.rect.top + a.rect.height / 2) - centerY) - Math.abs((b.rect.top + b.rect.height / 2) - centerY));
                        target = candidates[0] && candidates[0].item;
                        if (target) break;
                    }
                    if (!target) return '';
                    target.setAttribute('data-ydf-browser-row-checkbox-target', marker);
                    return `[data-ydf-browser-row-checkbox-target="${marker}"]`;
                }""",
                marker,
            )
        except Exception:
            return False
        selector = str(selector or "").strip()
        if not selector:
            return False
        scope = getattr(self, "_active_table_scope", None)
        context = self._table_scope_context(scope) if scope is not None else self._page
        checkbox = context.locator(selector).first
        try:
            checkbox.click(timeout=3000)
            return self._confirm_checkbox_selected(checkbox)
        except Exception:
            try:
                checkbox.click(force=True, timeout=3000)
                return self._confirm_checkbox_selected(checkbox)
            except Exception:
                return False

    def _confirm_checkbox_selected(self, checkbox, *, row=None) -> bool:
        page = self._page
        if page is not None:
            try:
                page.wait_for_timeout(200)
            except Exception:
                pass
        scope = getattr(self, "_active_table_scope", None)
        if scope is not None:
            self._table_scope_context(scope)
        if self._selection_checkbox_state(checkbox) in {"checked", "mixed"}:
            return True
        if row is not None:
            return self._table_row_checkbox_selection_state(row) in {"checked", "mixed"}
        return False

    def _table_row_checkbox_selection_state(self, row) -> str:
        try:
            state = str(row.evaluate(_ROW_CHECKBOX_SELECTION_STATE_SCRIPT) or "").strip().lower()
        except Exception:
            return "unchecked"
        if state in {"checked", "mixed", "unchecked"}:
            return state
        return "unchecked"

    def _try_click_table_row_for_selection(self, row) -> bool:
        self.last_table_selection_debug = {"strategy": "row_click", "selected_after": False}
        left_cell_point = self._aligned_row_left_cell_point_for_selection(row)
        if left_cell_point is not None:
            return self._click_point_and_confirm_row_selection(
                left_cell_point,
                row,
                "aligned_left_cell",
                accept_unconfirmed=True,
            )
        if self._click_candidate_and_confirm_row_selection(
            row,
            row,
            "row_left_edge",
            position=self._row_left_edge_click_position(row),
        ):
            return True
        try:
            text = " ".join((row.inner_text(timeout=300) or "").split())
        except Exception:
            text = ""
        if text:
            self.last_table_selection_debug["row_text"] = text[:160]
        return False

    def _aligned_row_left_cell_point_for_selection(self, row) -> dict[str, Any] | None:
        marker = f"row-selection-cell-{int(time.monotonic() * 1000000)}"
        try:
            point = row.evaluate(
                """(row, marker) => {
                    const visible = (el) => {
                        if (!el || !el.getBoundingClientRect) return false;
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style && style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                    };
                    const rowRect = row.getBoundingClientRect();
                    const centerY = rowRect.top + rowRect.height / 2;
                    const receivesPointer = (item, rect) => {
                        const x = rect.left + Math.min(Math.max(rect.width / 2, 8), 24);
                        const y = rect.top + rect.height / 2;
                        if (x < 0 || y < 0 || x > window.innerWidth || y > window.innerHeight) return false;
                        const top = document.elementFromPoint(x, y);
                        return Boolean(top && (item === top || item.contains(top) || top.contains(item)));
                    };
                    const localRoot = row.closest('[data-ydf-browser-table-selection-root]');
                    const tableRoot = row.closest('.wui-table, .ant-table, .u-table, .el-table, [role="grid"], [class*="Table"], [class*="table"]');
                    const scopeRoot = row.closest('[data-ydf-table-scope-token]');
                    const searchRoots = scopeRoot ? [scopeRoot] : [localRoot, tableRoot, document].filter(Boolean);
                    const cellSelector = [
                        'td',
                        '[role="gridcell"]',
                        '.wui-table-cell',
                        '.ant-table-cell',
                        '.u-table-cell',
                        '.el-table__cell'
                    ].join(',');
                    for (const root of searchRoots) {
                        const candidates = Array.from(root.querySelectorAll(cellSelector))
                            .filter(visible)
                            .filter((item) => !item.closest('thead, .ant-table-header, .wui-table-header, .u-table-header, .el-table__header'))
                            .map((item) => ({
                                item,
                                rect: item.getBoundingClientRect(),
                                text: String(item.innerText || item.textContent || '').replace(/\\s+/g, ' ').trim()
                            }))
                            .filter(({ rect }) => centerY >= rect.top - 4 && centerY <= rect.bottom + 4)
                            .filter(({ item, rect }) => receivesPointer(item, rect))
                            .sort((a, b) => a.rect.left - b.rect.left || a.rect.width - b.rect.width);
                        const targetCandidate = candidates.find(({ text }) => text && !/^\\d+$/.test(text)) || candidates[0];
                        const target = targetCandidate && targetCandidate.item;
                        if (target) {
                            target.setAttribute('data-ydf-browser-row-selection-cell-target', marker);
                            const rect = target.getBoundingClientRect();
                            return {
                                x: rect.left + Math.min(Math.max(rect.width / 2, 8), 24),
                                y: rect.top + rect.height / 2,
                                text: targetCandidate.text,
                                className: String(target.className || '').slice(0, 160),
                                selector: `[data-ydf-browser-row-selection-cell-target="${marker}"]`,
                            };
                        }
                    }
                    return null;
                }""",
                marker,
            )
        except Exception:
            return None
        if not isinstance(point, dict):
            return None
        try:
            x = float(point.get("x"))
            y = float(point.get("y"))
        except Exception:
            return None
        if x <= 0 or y <= 0:
            return None
        point["x"] = x
        point["y"] = y
        return point

    def _row_left_edge_click_position(self, row) -> dict[str, float | int]:
        try:
            box = row.bounding_box(timeout=300)
        except Exception:
            box = None
        if not isinstance(box, dict):
            return {"x": 12, "y": 12}
        width = float(box.get("width") or 0)
        height = float(box.get("height") or 0)
        x = max(4, min(12, width / 2 if width else 12))
        y = max(4, min(12, height / 2 if height else 12))
        return {"x": x, "y": y}

    def _click_candidate_and_confirm_row_selection(
        self,
        target,
        row,
        source: str,
        *,
        position: dict[str, float | int] | None = None,
        accept_unconfirmed: bool = False,
    ) -> bool:
        click_kwargs: dict[str, Any] = {"timeout": 3000}
        if position is not None:
            click_kwargs["position"] = position
        try:
            target.click(**click_kwargs)
        except Exception:
            try:
                force_kwargs = dict(click_kwargs)
                force_kwargs["force"] = True
                target.click(**force_kwargs)
            except Exception:
                return False
        page = self._page
        if page is not None:
            try:
                page.wait_for_timeout(200)
            except Exception:
                pass
        row_state = self._table_row_selection_state(row)
        selected = bool(row_state.get("selected")) if isinstance(row_state, dict) else bool(row_state)
        self.last_table_selection_debug = {
            "strategy": "row_click",
            "selected_after": selected,
            "click_source": source,
        }
        if isinstance(row_state, dict):
            self.last_table_selection_debug["row_state"] = row_state
        self._attach_table_root_selection_debug()
        if accept_unconfirmed and not selected:
            self.last_table_selection_debug["accepted_unconfirmed"] = True
            return True
        return selected

    def _click_point_and_confirm_row_selection(
        self,
        point: dict[str, Any],
        row,
        source: str,
        *,
        accept_unconfirmed: bool = False,
    ) -> bool:
        page = self._page
        if page is None:
            return False
        try:
            page.mouse.click(float(point["x"]), float(point["y"]))
        except Exception:
            return False
        try:
            page.wait_for_timeout(200)
        except Exception:
            pass
        row_state = self._table_row_selection_state(row)
        selected = bool(row_state.get("selected")) if isinstance(row_state, dict) else bool(row_state)
        self.last_table_selection_debug = {
            "strategy": "row_click",
            "selected_after": selected,
            "click_source": source,
            "click_point": {
                "x": point.get("x"),
                "y": point.get("y"),
                "text": point.get("text"),
                "className": point.get("className"),
            },
        }
        if isinstance(row_state, dict):
            self.last_table_selection_debug["row_state"] = row_state
        self._attach_table_root_selection_debug()
        if accept_unconfirmed and not selected:
            self.last_table_selection_debug["accepted_unconfirmed"] = True
            return True
        return selected

    def _attach_table_root_selection_debug(self) -> None:
        if not isinstance(self.last_table_selection_debug, dict):
            return
        root = self.last_table_selection_root
        if not isinstance(root, dict):
            return
        if root.get("fieldid"):
            self.last_table_selection_debug["root_fieldid"] = root.get("fieldid")
        if root.get("source"):
            self.last_table_selection_debug["root_source"] = root.get("source")
        if root.get("selectableRows") is not None:
            self.last_table_selection_debug["root_selectable_rows"] = root.get("selectableRows")
        if root.get("rows") is not None:
            self.last_table_selection_debug["root_rows"] = root.get("rows")

    def _table_row_has_selection_state(self, row) -> bool:
        row_state = self._table_row_selection_state(row)
        if isinstance(row_state, dict):
            return bool(row_state.get("selected"))
        return bool(row_state)

    def _table_row_selection_state(self, row) -> dict[str, Any] | bool:
        try:
            return row.evaluate(
                """(node) => {
                    const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                    const row = node && (node.closest && node.closest('tr, [role="row"], .wui-table-row, .ant-table-row, .u-table-row, .el-table__row')) || node;
                    const selected = (el) => {
                        if (!el) return false;
                        const ariaSelected = String(el.getAttribute && el.getAttribute('aria-selected') || '').toLowerCase();
                        if (ariaSelected === 'true') return true;
                        const ariaCurrent = String(el.getAttribute && el.getAttribute('aria-current') || '').toLowerCase();
                        if (ariaCurrent && ariaCurrent !== 'false') return true;
                        const className = String(el.className || '');
                        return /(^|[-_\\s])(selected|current|active|focused?|checked)([-_\\s]|$)|row-selected|row-current|cell-selected|cell-current|is-selected|is-current|is-active|ant-table-row-selected|wui-table-row-selected|u-table-row-selected|el-table__row--current/i.test(className);
                    };
                    const active = document.activeElement;
                    const activeInside = Boolean(active && row && row.contains && row.contains(active));
                    const direct = row && row.querySelector && row.querySelector('[aria-selected="true"], [aria-current]:not([aria-current="false"]), .selected, .current, .active, .checked, .focused, .focus, .is-selected, .is-current, .is-active, .row-selected, .row-current, .cell-selected, .cell-current, .ant-table-row-selected, .wui-table-row-selected, .u-table-row-selected, .el-table__row--current');
                    const descendants = row && row.querySelectorAll ? Array.from(row.querySelectorAll('*')) : [];
                    const matched = descendants
                        .filter((el) => selected(el))
                        .slice(0, 8)
                        .map((el) => ({
                            tag: String(el.tagName || '').toLowerCase(),
                            className: String(el.className || '').slice(0, 160),
                            role: String(el.getAttribute && el.getAttribute('role') || ''),
                            ariaSelected: String(el.getAttribute && el.getAttribute('aria-selected') || ''),
                            ariaCurrent: String(el.getAttribute && el.getAttribute('aria-current') || ''),
                            text: normalize(el.innerText || el.textContent || '').slice(0, 80),
                        }));
                    const selectedResult = selected(row) || activeInside || Boolean(direct) || matched.length > 0;
                    return {
                        selected: selectedResult,
                        rowTag: String(row && row.tagName || '').toLowerCase(),
                        rowClass: String(row && row.className || '').slice(0, 200),
                        rowRole: String(row && row.getAttribute && row.getAttribute('role') || ''),
                        rowAriaSelected: String(row && row.getAttribute && row.getAttribute('aria-selected') || ''),
                        rowAriaCurrent: String(row && row.getAttribute && row.getAttribute('aria-current') || ''),
                        activeInside,
                        activeTag: String(active && active.tagName || '').toLowerCase(),
                        activeClass: String(active && active.className || '').slice(0, 160),
                        activeText: normalize(active && (active.innerText || active.textContent) || '').slice(0, 80),
                        matched,
                    };
                }"""
            )
        except Exception:
            return False

    def _click_table_header_checkbox(
        self,
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
    ) -> None:
        context = self._table_selection_context(table, table_fieldid=table_fieldid, table_columns=table_columns)
        selector_summaries: list[str] = []
        for checkbox_selector in build_table_header_selection_checkbox_selectors():
            checkboxes = context.locator(checkbox_selector)
            try:
                count = checkboxes.count()
            except Exception:
                continue
            if count:
                selector_summaries.append(f"{checkbox_selector}: {count}")
            for index in range(count):
                checkbox = checkboxes.nth(index)
                try:
                    if not checkbox.is_visible(timeout=500):
                        continue
                    state = self._selection_checkbox_state(checkbox)
                    if state == "checked":
                        return
                    try:
                        checkbox.click(timeout=3000)
                        return
                    except Exception:
                        checkbox.click(force=True, timeout=3000)
                        return
                except Exception:
                    continue
        details = "未找到表头全选 checkbox"
        if table:
            details = f"{details}; 表格={table}"
        if table and self.last_table_selection_root:
            root = self.last_table_selection_root
            details = (
                f"{details}; 表格根="
                f"tag={root.get('tag')}, class={root.get('className')}, "
                f"rows={root.get('rows')}, selectableRows={root.get('selectableRows')}, "
                f"text={root.get('text')}"
            )
        if selector_summaries:
            details = f"{details}; 表头选择器统计: {' | '.join(selector_summaries[:3])}"
        raise RuntimeError(details)

    def _selection_checkbox_state(self, checkbox) -> str:
        try:
            state = str(checkbox.evaluate(_CHECKBOX_SELECTION_STATE_SCRIPT) or "").strip().lower()
        except Exception:
            return "unchecked"
        if state in {"checked", "mixed", "unchecked"}:
            return state
        return "unchecked"

    def _table_scope_context(self, scope: ResolvedTableScope):
        context = self._table_scope_token_context(scope.token)
        if context is None:
            raise RuntimeError(f"表格作用域执行令牌失效: table={scope.label}; token={scope.token}")
        return context.locator(f'[data-ydf-table-scope-token~="{scope.token}"]').first

    def _table_selection_context(
        self,
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        require_selectable_rows: bool = True,
    ):
        scope = getattr(self, "_active_table_scope", None)
        if scope is not None:
            return self._table_scope_context(scope)
        page = self._require_page()
        fieldid = str(table_fieldid or "").strip()
        if fieldid:
            selector = self._resolve_table_selection_fieldid_root_selector(
                [f"{fieldid}_drag", fieldid],
                table_columns=table_columns,
                require_selectable_rows=require_selectable_rows,
            )
            if selector:
                context = self._last_table_selection_context or page
                return context.locator(selector).first
            details = f"表格作用域未匹配: table_fieldid={fieldid}"
            if table:
                details = f"{details}; 表格={table}"
            if self.last_table_selection_root:
                root = self.last_table_selection_root
                details = (
                    f"{details}; 表格根="
                    f"source={root.get('source')}, fieldid={root.get('fieldid')}, "
                    f"rows={root.get('rows')}, selectableRows={root.get('selectableRows')}, "
                    f"text={root.get('text')}"
                )
            raise RuntimeError(details)
        table_name = str(table or "").strip()
        if not table_name:
            return page
        selector = self._resolve_table_selection_root_selector(
            table_name,
            table_columns=table_columns,
            require_selectable_rows=require_selectable_rows,
        )
        context = self._last_table_selection_context or page
        return context.locator(selector).first

    def _selection_context_has_receivable_row(self, context) -> bool:
        for row_selector in _table_data_row_selectors(scoped=True):
            try:
                rows = context.locator(row_selector)
                count = rows.count()
            except Exception:
                continue
            for index in range(min(count, 12)):
                row = rows.nth(index)
                try:
                    if not row.is_visible(timeout=300):
                        continue
                    if not self._row_looks_like_table_data_row(row):
                        continue
                    if self._row_has_receivable_cell(row):
                        return True
                except Exception:
                    continue
        return False

    def _format_table_selection_failure(
        self,
        message: str,
        *,
        table: str | None = None,
        table_fieldid: str | None = None,
        column: str | None = None,
    ) -> str:
        details = message
        if table:
            details = f"{details}; 表格={table}"
        if table_fieldid:
            details = f"{details}; table_fieldid={table_fieldid}"
        if column:
            details = f"{details}; column={column}"
        root = self.last_table_selection_root
        if root:
            details = (
                f"{details}; 表格根="
                f"tag={root.get('tag')}, class={root.get('className')}, "
                f"rows={root.get('rows')}, selectableRows={root.get('selectableRows')}, "
                f"source={root.get('source')}, fieldid={root.get('fieldid')}, "
                f"text={root.get('text')}"
            )
        try:
            context = self._table_selection_context(
                table,
                table_fieldid=table_fieldid,
                require_selectable_rows=False,
            )
        except Exception:
            context = None
        if context is not None:
            summaries: list[str] = []
            for row_selector in _table_data_row_selectors(scoped=bool(table or table_fieldid)):
                try:
                    count = context.locator(row_selector).count()
                except Exception:
                    continue
                summaries.append(f"{row_selector}: rows={count}")
                if len(summaries) >= 3:
                    break
            if summaries:
                details = f"{details}; 行选择器统计: {' | '.join(summaries)}"
        return details

    def _resolve_table_selection_fieldid_root_selector(
        self,
        fieldids: list[str],
        table_columns: list[str] | None = None,
        require_selectable_rows: bool = True,
    ) -> str | None:
        page = self._require_page()
        marker = f"table-fieldid-selection-{int(time.monotonic() * 1000000)}"
        cleaned = [str(item).strip() for item in fieldids if str(item).strip()]
        if not cleaned:
            return None
        self._last_table_selection_context = page
        payload = {
            "fieldids": cleaned,
            "marker": marker,
            "columns": table_columns or [],
            "requireSelectableRows": require_selectable_rows,
        }
        last_result: Any = None
        for context in self._all_search_contexts():
            try:
                result = context.evaluate(_TABLE_FIELDID_ROOT_SELECTOR_SCRIPT, payload)
            except Exception:
                continue
            last_result = result
            self.last_table_selection_root = result if isinstance(result, dict) else None
            selector = str((result or {}).get("selector") or "").strip() if isinstance(result, dict) else str(result or "").strip()
            if selector:
                self._last_table_selection_context = context
                return selector
        self.last_table_selection_root = last_result if isinstance(last_result, dict) else None
        return None

    def _resolve_table_selection_root_selector(
        self,
        table: str,
        table_columns: list[str] | None = None,
        require_selectable_rows: bool = True,
    ) -> str:
        page = self._require_page()
        marker = f"table-selection-{int(time.monotonic() * 1000000)}"
        self._last_table_selection_context = page
        payload = {
            "table": table,
            "marker": marker,
            "columns": table_columns or [],
            "requireSelectableRows": require_selectable_rows,
        }
        last_result: Any = None
        last_error: Exception | None = None
        for context in self._all_search_contexts():
            try:
                result = context.evaluate(_TABLE_SELECTION_ROOT_SELECTOR_SCRIPT, payload)
            except Exception as exc:
                last_error = exc
                continue
            last_result = result
            self.last_table_selection_root = result if isinstance(result, dict) else None
            selector = str(result.get("selector") or "").strip() if isinstance(result, dict) else str(result or "").strip()
            if selector:
                self._last_table_selection_context = context
                return selector
        if last_error is not None and last_result is None:
            raise RuntimeError(f"表格名称未匹配: target.table={table}; 原因: {last_error}") from last_error
        self.last_table_selection_root = last_result if isinstance(last_result, dict) else None
        if isinstance(last_result, dict):
            table_names = [str(item).strip() for item in last_result.get("tables") or [] if str(item).strip()]
        else:
            table_names = []
        details = "、".join(table_names[:8]) or "未识别"
        raise RuntimeError(f"表格名称未匹配: target.table={table}; 当前页面可选表格包括: {details}")
        raise RuntimeError(f"表格名称未匹配: target.table={table}")

    def _capture_table_selection_debug(
        self,
        *,
        table: str | None,
        row_number: int,
        row_selector: str,
        selectable_index: int,
    ) -> None:
        if self.observation_session is not None or not os.environ.get("YDF_BROWSER_DEBUG_TABLE_SELECTION"):
            return
        page = self._require_page()
        wait_ms = _env_int("YDF_BROWSER_DEBUG_TABLE_SELECTION_WAIT_MS", 1500)
        if wait_ms > 0:
            page.wait_for_timeout(wait_ms)
        safe_table = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", str(table or "default")).strip("_") or "default"
        target = _diag_dir() / f"ydf-browser-table-selection-{int(time.time() * 1000)}-{safe_table}-row{row_number}.png"
        try:
            page.screenshot(path=str(target), full_page=True)
        except Exception as exc:
            print(f"[ydf-browser] table-selection-debug screenshot_failed={exc}", file=sys.stderr, flush=True)
            return
        self.diagnostic_files.append(str(target))
        self.table_selection_debug_files.append(str(target))
        root = self.last_table_selection_root or {}
        print(
            "[ydf-browser] table-selection-debug "
            f"screenshot={target} table={table or ''} row_number={row_number} "
            f"row_selector={row_selector} selectable_index={selectable_index} "
            f"root_source={root.get('source')} root_fieldid={root.get('fieldid')} "
            f"root_tag={root.get('tag')} root_class={root.get('className')} "
            f"root_rows={root.get('rows')} root_selectable_rows={root.get('selectableRows')}",
            file=sys.stderr,
            flush=True,
        )

    def _try_hover_first(self, selectors: list[str]) -> bool:
        for selector in selectors:
            locator = self._page.locator(selector).first
            try:
                if locator.count() == 0 or not locator.is_visible(timeout=500):
                    continue
                locator.hover(timeout=3000)
                return True
            except Exception:
                continue
        return False

    def _expand_tree_until_visible(self, label: str, max_rounds: int = 24, context=None) -> None:
        page = self._require_page()
        search_context = context or page
        for _ in range(max_rounds):
            if self._is_any_visible(build_tree_node_selectors(label), context=search_context):
                return
            expanded = False
            for selector in build_tree_closed_switcher_selectors():
                locator = search_context.locator(selector)
                try:
                    count = locator.count()
                except Exception:
                    continue
                for index in range(count):
                    candidate = locator.nth(index)
                    try:
                        if not candidate.is_visible(timeout=300):
                            continue
                        candidate.click(timeout=2000)
                        page.wait_for_timeout(400)
                        expanded = True
                        break
                    except Exception:
                        continue
                if expanded:
                    break
            if not expanded:
                break

    def _is_any_visible(self, selectors: list[str], context=None) -> bool:
        search_context = context or self._require_page()
        for selector in selectors:
            locator = search_context.locator(selector)
            try:
                count = locator.count()
            except Exception:
                continue
            for index in range(count):
                try:
                    if locator.nth(index).is_visible(timeout=200):
                        return True
                except Exception:
                    continue
        return False

    def _tree_search_context(self, tree_fieldid: str | None, *, include_search_scope: bool = False):
        if not tree_fieldid:
            return self._require_page()
        selector = f'[fieldid="{tree_fieldid}"], [data-fieldid="{tree_fieldid}"]'
        last_error = None
        for context in self._all_search_contexts():
            locator = context.locator(selector).first
            try:
                locator.wait_for(state="visible", timeout=3000)
                if include_search_scope:
                    return self._tree_locator_search_scope(context, locator) or locator
                return locator
            except Exception as exc:
                last_error = exc
                continue
        fallback = self._unique_visible_tree_locator_context()
        if fallback is not None:
            return fallback
        fallback = self._unique_visible_tree_search_context()
        if fallback is not None:
            return fallback
        self.last_tree_search = {
            "used": False,
            "found": False,
            "reason": "tree_context_missing",
            "tree_fieldid": tree_fieldid,
            "context_debug": self._tree_search_context_debug(),
        }
        raise RuntimeError(f"未找到树组件: {tree_fieldid}") from last_error

    def _unique_visible_tree_locator_context(self):
        selectors = [
            ".wui-tree, .ant-tree, .u-tree, [role='tree']",
            "[class*='tree'], [class*='Tree']",
        ]
        for context in self._all_search_contexts():
            for selector in selectors:
                locator = context.locator(selector)
                try:
                    count = locator.count()
                except Exception:
                    continue
                visible_indexes: list[int] = []
                for index in range(min(count, 30)):
                    try:
                        if locator.nth(index).is_visible(timeout=200):
                            visible_indexes.append(index)
                    except Exception:
                        continue
                if len(visible_indexes) == 1:
                    return locator.nth(visible_indexes[0])
        return None

    def _tree_locator_search_scope(self, context, tree_locator):
        marker = f"tree-scope-{int(time.monotonic() * 1000)}"
        try:
            selector = str(
                tree_locator.evaluate(
                    """(node, marker) => {
                        const visible = (el) => {
                          if (!el || !(el instanceof HTMLElement)) return false;
                          const style = window.getComputedStyle(el);
                          const rect = el.getBoundingClientRect();
                          return style && style.visibility !== 'hidden' && style.display !== 'none'
                            && rect.width > 0 && rect.height > 0
                            && rect.bottom >= 0 && rect.right >= 0
                            && rect.top <= window.innerHeight && rect.left <= window.innerWidth;
                        };
                        const usableInput = (input) => {
                          if (!visible(input)) return false;
                          const fieldid = input.getAttribute('fieldid') || input.getAttribute('data-fieldid') || '';
                          const className = String(input.className || '');
                          if (fieldid === 'workbench-search') return false;
                          if (className.includes('wui-select-selection-search-input')) return false;
                          return true;
                        };
                        const hasInput = (el) => Array.from(el.querySelectorAll('input:not([type="hidden"])')).some(usableInput);
                        const component = node.closest('[class*="LCDTree"]')
                          || node.closest('[class*="lcd-tree"]')
                          || node;
                        if (visible(component) && hasInput(component)) {
                          component.setAttribute('data-ydf-browser-tree-search-root', marker);
                          return `[data-ydf-browser-tree-search-root="${marker}"]`;
                        }
                        return '';
                    }""",
                    marker,
                )
                or ""
            )
        except Exception:
            return None
        if not selector:
            return None
        try:
            locator = context.locator(selector).first
            if locator.is_visible(timeout=300):
                return locator
        except Exception:
            return None
        return None

    def _unique_visible_tree_search_context(self):
        marker = f"tree-root-{int(time.monotonic() * 1000)}"
        script = """(marker) => {
            const visible = (el) => {
              if (!el || !(el instanceof HTMLElement)) return false;
              const style = window.getComputedStyle(el);
              const rect = el.getBoundingClientRect();
              return style && style.visibility !== 'hidden' && style.display !== 'none'
                && rect.width > 0 && rect.height > 0
                && rect.bottom >= 0 && rect.right >= 0
                && rect.top <= window.innerHeight && rect.left <= window.innerWidth;
            };
            const treeSelector = [
              '.wui-tree',
              '.ant-tree',
              '.u-tree',
              '[role="tree"]'
            ].join(',');
            const roots = [];
            const hasVisibleTree = (el) => Array.from(el.querySelectorAll(treeSelector)).some(visible);
            const addRoot = (el) => {
              if (!el || !visible(el) || roots.includes(el)) return;
              roots.push(el);
            };
            const inputs = Array.from(document.querySelectorAll('input:not([type="hidden"])')).filter(visible);
            for (const input of inputs) {
              for (let node = input.parentElement, depth = 0; node && node !== document.body && depth < 8; node = node.parentElement, depth += 1) {
                if (visible(node) && hasVisibleTree(node)) {
                  addRoot(node);
                  break;
                }
              }
            }
            if (!roots.length) {
              for (const tree of Array.from(document.querySelectorAll(treeSelector)).filter(visible)) {
                let scope = tree;
                for (let node = tree.parentElement, depth = 0; node && node !== document.body && depth < 6; node = node.parentElement, depth += 1) {
                  if (!visible(node)) continue;
                  const hasSearch = Boolean(Array.from(node.querySelectorAll('input:not([type="hidden"])')).some(visible));
                  if (hasVisibleTree(node) && hasSearch) {
                    scope = node;
                    break;
                  }
                }
                addRoot(scope);
              }
            }
            const scoped = roots.filter((root) => !roots.some((other) => other !== root && root.contains(other)));
            roots.splice(0, roots.length, ...scoped);
            if (roots.length !== 1) return '';
            roots[0].setAttribute('data-ydf-browser-tree-search-root', marker);
            return `[data-ydf-browser-tree-search-root="${marker}"]`;
        }"""
        for context in self._all_search_contexts():
            try:
                selector = str(context.evaluate(script, marker) or "")
            except Exception:
                continue
            if not selector:
                continue
            try:
                locator = context.locator(selector).first
                if locator.is_visible(timeout=300):
                    return locator
            except Exception:
                continue
        return None

    def _tree_search_context_debug(self) -> list[dict[str, Any]]:
        script = """() => {
            const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
            const visible = (el) => {
              if (!el || !(el instanceof HTMLElement)) return false;
              const style = window.getComputedStyle(el);
              const rect = el.getBoundingClientRect();
              return style && style.visibility !== 'hidden' && style.display !== 'none'
                && rect.width > 0 && rect.height > 0
                && rect.bottom >= 0 && rect.right >= 0
                && rect.top <= window.innerHeight && rect.left <= window.innerWidth;
            };
            const describe = (el) => {
              const rect = el.getBoundingClientRect();
              return {
                tag: String(el.tagName || '').toLowerCase(),
                className: String(el.className || '').slice(0, 120),
                fieldid: el.getAttribute('fieldid') || el.getAttribute('data-fieldid') || '',
                placeholder: el.getAttribute('placeholder') || '',
                text: normalize(el.innerText || el.textContent || '').slice(0, 120),
                rect: {x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width), height: Math.round(rect.height)}
              };
            };
            const exactTreeSelector = ['.wui-tree', '.ant-tree', '.u-tree', '[role="tree"]'].join(',');
            const broadTreeSelector = [exactTreeSelector, '[class*="tree"]', '[class*="Tree"]'].join(',');
            const inputs = Array.from(document.querySelectorAll('input:not([type="hidden"])')).filter(visible);
            const exactTrees = Array.from(document.querySelectorAll(exactTreeSelector)).filter(visible);
            const broadTrees = Array.from(document.querySelectorAll(broadTreeSelector)).filter(visible);
            const roots = [];
            const hasVisibleTree = (el, selector) => Array.from(el.querySelectorAll(selector)).some(visible);
            const addRoot = (el) => {
              if (!el || !visible(el) || roots.includes(el)) return;
              roots.push(el);
            };
            for (const input of inputs) {
              for (let node = input.parentElement, depth = 0; node && node !== document.body && depth < 8; node = node.parentElement, depth += 1) {
                if (visible(node) && hasVisibleTree(node, broadTreeSelector)) {
                  addRoot(node);
                  break;
                }
              }
            }
            const scoped = roots.filter((root) => !roots.some((other) => other !== root && root.contains(other)));
            return {
              exact_tree_count: exactTrees.length,
              broad_tree_count: broadTrees.length,
              input_count: inputs.length,
              candidate_root_count: scoped.length,
              exact_trees: exactTrees.slice(0, 5).map(describe),
              broad_trees: broadTrees.slice(0, 8).map(describe),
              inputs: inputs.slice(0, 8).map(describe),
              candidate_roots: scoped.slice(0, 5).map(describe)
            };
        }"""
        diagnostics: list[dict[str, Any]] = []
        for index, context in enumerate(self._all_search_contexts()):
            try:
                data = context.evaluate(script)
            except Exception as exc:
                diagnostics.append({"context_index": index, "error": str(exc)[:200]})
                continue
            if isinstance(data, dict):
                data["context_index"] = index
                data["locator_probe"] = self._tree_locator_probe(context)
                diagnostics.append(data)
        return diagnostics

    def _tree_locator_probe(self, context) -> list[dict[str, Any]]:
        selectors = [
            ".wui-tree, .ant-tree, .u-tree, [role='tree']",
            "[class*='tree'], [class*='Tree']",
            "input[placeholder*='搜索'], input[placeholder*='查询'], input:not([type='hidden'])",
        ]
        probe: list[dict[str, Any]] = []
        for selector in selectors:
            locator = context.locator(selector)
            try:
                count = locator.count()
            except Exception as exc:
                probe.append({"selector": selector, "error": str(exc)[:200]})
                continue
            item: dict[str, Any] = {"selector": selector, "count": count, "visible_count": 0, "visible_samples": []}
            for index in range(min(count, 20)):
                candidate = locator.nth(index)
                try:
                    visible = candidate.is_visible(timeout=200)
                except Exception:
                    visible = False
                if not visible:
                    continue
                item["visible_count"] += 1
                if len(item["visible_samples"]) >= 5:
                    continue
                try:
                    item["visible_samples"].append(
                        candidate.evaluate(
                            """(el) => {
                                const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                                const rect = el.getBoundingClientRect();
                                return {
                                  tag: String(el.tagName || '').toLowerCase(),
                                  className: String(el.className || '').slice(0, 120),
                                  fieldid: el.getAttribute('fieldid') || el.getAttribute('data-fieldid') || '',
                                  placeholder: el.getAttribute('placeholder') || '',
                                  text: normalize(el.innerText || el.textContent || '').slice(0, 120),
                                  rect: {x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width), height: Math.round(rect.height)}
                                };
                            }"""
                        )
                    )
                except Exception as exc:
                    item["visible_samples"].append({"error": str(exc)[:200]})
            probe.append(item)
        return probe

    def _resolve_fill_locator(self, selector: str):
        locator = self._resolve_visible_locator(selector)
        return self._resolve_fill_locator_from_root(locator)

    def _resolve_fill_locator_from_root(self, locator):
        input_locator = locator.locator("input,textarea,[contenteditable='true']").first
        try:
            if input_locator.count() > 0:
                return input_locator
        except Exception:
            pass
        return locator

    def _resolve_foreground_form_field_root(self, bound_element: BoundElement):
        candidate = getattr(bound_element, "candidate", None)
        key = str(getattr(candidate, "key", "") or "").strip()
        label = str(getattr(candidate, "label", "") or getattr(candidate, "title", "") or "").strip()
        fieldid = str(getattr(candidate, "fieldid", "") or "").strip()
        data_field = str(getattr(candidate, "data_field", "") or "").strip()
        if not any((key, label, fieldid, data_field)):
            return None
        for selector in (
            f'[uikey="{key}"]' if key else "",
            f'[fieldid="{fieldid}"]' if fieldid else "",
            f'[data-fieldid="{fieldid}"]' if fieldid else "",
            f'[fieldid="{data_field}"]' if data_field else "",
            f'[data-field="{data_field}"]' if data_field else "",
        ):
            if not selector:
                continue
            locator = self._require_page().locator(selector)
            try:
                count = min(locator.count(), 20)
            except Exception:
                continue
            for index in range(count):
                item = locator.nth(index)
                try:
                    if not item.is_visible(timeout=300):
                        continue
                    if item.evaluate(
                        """(node) => {
                            const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                            const visible = (el) => {
                              const style = window.getComputedStyle(el);
                              const rect = el.getBoundingClientRect();
                              return style && style.visibility !== 'hidden' && style.display !== 'none'
                                && rect.width > 0 && rect.height > 0;
                            };
                            const isForegroundLayer = (el) => /modal|dialog|popup|drawer|yy-modal|wui-modal|ant-modal|u-modal/i.test(
                              String(el.className || '') + ' ' + String(el.getAttribute('role') || '')
                            );
                            for (let el = node; el && el.nodeType === 1; el = el.parentElement) {
                              const rect = el.getBoundingClientRect();
                              const text = normalize(el.innerText || el.textContent);
                              if (
                                visible(el)
                                && isForegroundLayer(el)
                                && text.includes('保存')
                                && text.includes('取消')
                                && rect.width >= 360
                                && rect.height >= 180
                              ) return true;
                            }
                            return false;
                        }"""
                    ):
                        return item
                except Exception:
                    continue
        marker = f"ydf-foreground-field-root-{int(time.time() * 1000)}"
        try:
            selector = self._require_page().evaluate(
                """({ label, fieldid, dataField, marker }) => {
                    const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                    const normalizeLabel = (value) => normalize(value)
                      .replace(/^[*＊\\s]+/, '')
                      .replace(/[：:]$/, '')
                      .trim();
                    const wantedLabel = normalizeLabel(label);
                    const visible = (el) => {
                      const style = window.getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style && style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width > 0 && rect.height > 0;
                    };
                    const hasControl = (el) => Boolean(el.querySelector(
                      'input:not([type="hidden"]), textarea, [contenteditable="true"], [role="textbox"], [role="combobox"], [role="switch"], button, [role="button"], [class*="suffix"], [class*="select"], [class*="refer"], [class*="ref"], [class*="switch"], [class*="Switch"]'
                    ));
                    const fieldLabelSelectors = [
                      'label',
                      '.ant-form-item-label',
                      '.wui-form-item-label',
                      '.u-form-item-label',
                      '.workflow-approve-ex-name',
                      '[class*="form-item-label"]',
                      '[class*="FormItemLabel"]',
                      '[class*="approve-ex-name"]'
                    ].join(',');
                    const fieldLabelCount = (el) => Array.from(el.querySelectorAll(fieldLabelSelectors))
                      .filter(visible)
                      .map((item) => normalizeLabel(item.innerText || item.textContent || item.getAttribute('title')))
                      .filter(Boolean)
                      .length;
                    const zScore = (el) => {
                      let score = 0;
                      for (let node = el; node && node.nodeType === 1; node = node.parentElement) {
                        const zIndex = Number.parseInt(window.getComputedStyle(node).zIndex, 10);
                        if (!Number.isNaN(zIndex)) score = Math.max(score, zIndex);
                      }
                      return score;
                    };
                    const isForegroundLayer = (el) => /modal|dialog|popup|drawer|yy-modal|wui-modal|ant-modal|u-modal/i.test(
                      String(el.className || '') + ' ' + String(el.getAttribute('role') || '')
                    );
                    const layerScore = (el) => {
                      let score = 0;
                      for (let node = el; node && node.nodeType === 1; node = node.parentElement) {
                        const rect = node.getBoundingClientRect();
                        const text = normalize(node.innerText || node.textContent);
                        if (isForegroundLayer(node)) score += 50000;
                        if (
                          isForegroundLayer(node)
                          && text.includes('保存')
                          && text.includes('取消')
                          && rect.width >= 360
                          && rect.height >= 180
                        ) {
                          score += 100000;
                          score += zScore(node);
                        }
                      }
                      return score;
                    };
                    const containsExactLabel = (el) => {
                      if (!wantedLabel) return false;
                      const labels = Array.from(el.querySelectorAll('label, span, div, [title], [class*="label"], [class*="Label"]'));
                      return labels.filter(visible).some((item) => {
                        const text = normalizeLabel(item.innerText || item.textContent || item.getAttribute('title'));
                        return text === wantedLabel;
                      });
                    };
                    const fieldSelectors = [
                      fieldid && `[fieldid="${CSS.escape(fieldid)}"]`,
                      fieldid && `[data-fieldid="${CSS.escape(fieldid)}"]`,
                      fieldid && `[name="${CSS.escape(fieldid)}"]`,
                      fieldid && `[id="${CSS.escape(fieldid)}"]`,
                      dataField && `[name="${CSS.escape(dataField)}"]`,
                      dataField && `[data-field="${CSS.escape(dataField)}"]`,
                      dataField && `[fieldid="${CSS.escape(dataField)}"]`,
                    ].filter(Boolean).join(',');
                    const roots = Array.from(document.querySelectorAll('div, section, form'))
                      .filter(visible)
                      .filter(hasControl)
                      .map((el) => ({ el, rect: el.getBoundingClientRect(), text: normalize(el.innerText || el.textContent) }))
                      .filter((item) => item.rect.width >= 160 && item.rect.width <= 900 && item.rect.height >= 24 && item.rect.height <= 180)
                      .filter((item) => {
                        if (wantedLabel && containsExactLabel(item.el)) return true;
                        if (fieldSelectors && item.el.querySelector(fieldSelectors)) return true;
                        return false;
                      })
                      .map((item) => ({ ...item, score: layerScore(item.el), area: item.rect.width * item.rect.height }))
                      .filter((item) => item.score > 0)
                      .sort((a, b) => b.score - a.score || a.area - b.area);
                    const target = roots[0] && roots[0].el;
                    if (!target) return '';
                    target.setAttribute('data-ydf-browser-foreground-field-root', marker);
                    return `[data-ydf-browser-foreground-field-root="${marker}"]`;
                }""",
                {"label": label, "fieldid": fieldid, "dataField": data_field, "marker": marker},
            )
        except Exception:
            return None
        if not selector:
            return None
        try:
            return self._resolve_visible_locator(str(selector))
        except Exception:
            return None

    def _resolve_form_field_root_by_label_position(self, bound_element: BoundElement):
        candidate = getattr(bound_element, "candidate", None)
        label = str(getattr(candidate, "label", "") or getattr(candidate, "title", "") or "").strip()
        if not label:
            return None
        marker = f"ydf-position-field-root-{int(time.time() * 1000)}"
        try:
            selector = self._require_page().evaluate(
                """({ label, marker }) => {
                    const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                    const normalizeLabel = (value) => normalize(value)
                      .replace(/^[*＊\\s]+/, '')
                      .replace(/[：:]$/, '')
                      .trim();
                    const wantedLabel = normalizeLabel(label);
                    const visible = (el) => {
                      const style = window.getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style && style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width > 0 && rect.height > 0;
                    };
                    const layerScore = (el) => {
                      let score = 0;
                      const isForegroundLayer = (node) => /modal|dialog|popup|drawer|yy-modal|wui-modal|ant-modal|u-modal/i.test(
                        String(node.className || '') + ' ' + String(node.getAttribute('role') || '')
                      );
                      for (let node = el; node && node.nodeType === 1; node = node.parentElement) {
                        const rect = node.getBoundingClientRect();
                        const text = normalize(node.innerText || node.textContent);
                        const zIndex = Number.parseInt(window.getComputedStyle(node).zIndex, 10);
                        const foreground = isForegroundLayer(node);
                        if (foreground && !Number.isNaN(zIndex)) score = Math.max(score, zIndex);
                        if (foreground) score += 50000;
                        if (
                          foreground
                          && text.includes('保存')
                          && text.includes('取消')
                          && rect.width >= 360
                          && rect.height >= 180
                        ) score += 100000;
                      }
                      return score;
                    };
                    const labelNodes = Array.from(document.querySelectorAll('label, span, div, [title], [class*="label"], [class*="Label"]'))
                      .filter(visible)
                      .filter((el) => normalizeLabel(el.innerText || el.textContent || el.getAttribute('title')) === wantedLabel)
                      .map((el) => ({ el, rect: el.getBoundingClientRect(), score: layerScore(el) }))
                      .sort((a, b) => b.score - a.score || b.rect.top - a.rect.top);
                    const labelNode = labelNodes[0] && labelNodes[0].el;
                    if (!labelNode) return '';
                    const labelRect = labelNode.getBoundingClientRect();
                    const controls = Array.from(document.querySelectorAll([
                      'input:not([type="hidden"])',
                      'textarea',
                      '[contenteditable="true"]',
                      '[role="textbox"]',
                      '[role="combobox"]',
                      'button',
                      '[role="button"]',
                      '[class*="suffix"]',
                      '[class*="select"]',
                      '[class*="refer"]',
                      '[class*="ref"]'
                    ].join(',')))
                      .filter(visible)
                      .map((control) => ({ control, rect: control.getBoundingClientRect() }))
                      .filter((item) => item.rect.left >= labelRect.right - 8)
                      .filter((item) => Math.abs((item.rect.top + item.rect.bottom) / 2 - (labelRect.top + labelRect.bottom) / 2) <= 42)
                      .sort((a, b) => {
                        const dyA = Math.abs((a.rect.top + a.rect.bottom) / 2 - (labelRect.top + labelRect.bottom) / 2);
                        const dyB = Math.abs((b.rect.top + b.rect.bottom) / 2 - (labelRect.top + labelRect.bottom) / 2);
                        return dyA - dyB || a.rect.left - b.rect.left;
                    });
                    const control = controls[0] && controls[0].control;
                    if (!control) return '';
                    const fieldLabelSelectors = [
                      'label',
                      '.ant-form-item-label',
                      '.wui-form-item-label',
                      '.u-form-item-label',
                      '.workflow-approve-ex-name',
                      '[class*="form-item-label"]',
                      '[class*="FormItemLabel"]',
                      '[class*="approve-ex-name"]'
                    ].join(',');
                    const fieldLabelCount = (root) => Array.from(root.querySelectorAll(fieldLabelSelectors))
                      .filter(visible)
                      .map((item) => normalizeLabel(item.innerText || item.textContent || item.getAttribute('title')))
                      .filter(Boolean)
                      .length;
                    let target = control;
                    for (let el = control.parentElement; el && el.nodeType === 1; el = el.parentElement) {
                      const rect = el.getBoundingClientRect();
                      if (fieldLabelCount(el) > 1) break;
                      if (
                        visible(el)
                        && rect.left <= labelRect.left + 5
                        && rect.right >= control.getBoundingClientRect().right - 5
                        && rect.top <= labelRect.top + 5
                        && rect.bottom >= labelRect.bottom - 5
                        && rect.width <= 1000
                        && rect.height <= 160
                      ) {
                        target = el;
                      }
                    }
                    target.setAttribute('data-ydf-browser-position-field-root', marker);
                    return `[data-ydf-browser-position-field-root="${marker}"]`;
                }""",
                {"label": label, "marker": marker},
            )
        except Exception:
            return None
        if not selector:
            return None
        try:
            return self._resolve_visible_locator(str(selector))
        except Exception:
            return None

    def _narrow_form_field_root(self, root, bound_element: BoundElement):
        candidate = getattr(bound_element, "candidate", None)
        label = str(getattr(candidate, "label", "") or getattr(candidate, "title", "") or "").strip()
        fieldid = str(getattr(candidate, "fieldid", "") or "").strip()
        data_field = str(getattr(candidate, "data_field", "") or "").strip()
        if not any((label, fieldid, data_field)):
            return root
        marker = f"ydf-field-root-{int(time.time() * 1000)}"
        try:
            selector = root.evaluate(
                """(root, args) => {
                    const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                    const normalizeLabel = (value) => normalize(value)
                      .replace(/^[*＊\\s]+/, '')
                      .replace(/[：:]$/, '')
                      .trim();
                    const labelMatches = (value, label) => normalizeLabel(value) === normalizeLabel(label);
                    const visible = (el) => {
                      const style = window.getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style && style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width > 0 && rect.height > 0;
                    };
                    const hasControl = (el) => Boolean(el.querySelector(
                      'input:not([type="hidden"]), textarea, [contenteditable="true"], [role="textbox"], [role="combobox"], [role="switch"], button, [role="button"], [class*="suffix"], [class*="select"], [class*="refer"], [class*="ref"], [class*="switch"], [class*="Switch"]'
                    ));
                    const zScore = (el) => {
                      let score = 0;
                      for (let node = el; node && node.nodeType === 1; node = node.parentElement) {
                        const zIndex = Number.parseInt(window.getComputedStyle(node).zIndex, 10);
                        if (!Number.isNaN(zIndex)) score = Math.max(score, zIndex);
                      }
                      return score;
                    };
                    const isForegroundLayer = (el) => /modal|dialog|popup|drawer|yy-modal|wui-modal|ant-modal|u-modal/i.test(
                      String(el.className || '') + ' ' + String(el.getAttribute('role') || '')
                    );
                    const layerScore = (el) => {
                      let score = zScore(el);
                      for (let node = el; node && node.nodeType === 1; node = node.parentElement) {
                        const rect = node.getBoundingClientRect();
                        const foreground = isForegroundLayer(node);
                        if (rect.width > 0 && rect.width <= 1200 && rect.height > 0 && rect.height <= 700) {
                          const text = normalize(node.innerText || node.textContent);
                          if (foreground && text.includes('保存') && text.includes('取消')) score += 100000;
                          if (foreground && text.includes('编码规则') && text.includes('配置参数说明')) score += 50000;
                        }
                        if (foreground) score += 50000;
                      }
                      return score;
                    };
                    const mark = (el) => {
                      el.setAttribute('data-ydf-browser-field-root', args.marker);
                      return `[data-ydf-browser-field-root="${args.marker}"]`;
                    };
                    let searchRoot = root;
                    const modalRoots = Array.from(document.querySelectorAll(
                      '.ant-modal, .wui-modal, .u-modal, [role="dialog"], [class*="modal"]'
                    )).filter(visible);
                    const modalRoot = modalRoots.reverse().find((modal) => {
                      const text = normalize(modal.innerText || modal.textContent);
                      return !args.label || text.includes(normalize(args.label));
                    });
                    if (modalRoot) searchRoot = modalRoot;
                    if (!modalRoot && args.label) {
                      const labelText = normalize(args.label);
                      const layerRoot = Array.from(document.querySelectorAll('div, section, form'))
                        .filter(visible)
                        .map((el) => ({ el, rect: el.getBoundingClientRect(), text: normalize(el.innerText || el.textContent) }))
                        .filter((item) => item.rect.width >= 360 && item.rect.width <= 1200 && item.rect.height >= 180 && item.rect.height <= 700)
                        .filter((item) => item.text.includes(labelText) && item.text.includes('保存') && item.text.includes('取消'))
                        .sort((a, b) => layerScore(b.el) - layerScore(a.el) || (a.rect.width * a.rect.height) - (b.rect.width * b.rect.height))[0];
                      if (layerRoot) searchRoot = layerRoot.el;
                    }
                    if (args.label && layerScore(searchRoot) <= layerScore(root)) {
                      const labelText = normalizeLabel(args.label);
                      const foregroundLabel = Array.from(document.querySelectorAll('label, span, div, [title], [class*="label"], [class*="Label"]'))
                        .filter(visible)
                        .filter((el) => labelMatches(el.innerText || el.textContent || el.getAttribute('title'), labelText))
                        .sort((a, b) => {
                          const ar = a.getBoundingClientRect();
                          const br = b.getBoundingClientRect();
                          return layerScore(b) - layerScore(a) || br.top - ar.top;
                        })[0];
                      if (foregroundLabel && layerScore(foregroundLabel) > layerScore(searchRoot)) {
                        for (let el = foregroundLabel; el && el.nodeType === 1; el = el.parentElement) {
                          const rect = el.getBoundingClientRect();
                          const text = normalize(el.innerText || el.textContent);
                          if (
                            visible(el)
                            && text.includes(labelText)
                            && text.includes('保存')
                            && text.includes('取消')
                            && rect.width >= 360
                            && rect.width <= 1400
                            && rect.height >= 180
                            && rect.height <= 900
                          ) {
                            searchRoot = el;
                            break;
                          }
                        }
                      }
                    }
                    const boundaryParent = searchRoot.parentElement;
                    const byField = Array.from(searchRoot.querySelectorAll(
                      `[fieldid="${CSS.escape(args.fieldid)}"], [data-fieldid="${CSS.escape(args.fieldid)}"], [name="${CSS.escape(args.dataField)}"], [data-field="${CSS.escape(args.dataField)}"]`
                    )).filter(visible).sort((a, b) => layerScore(b) - layerScore(a))[0];
                    if (byField) {
                      for (let el = byField; el && el !== boundaryParent; el = el.parentElement) {
                        if (visible(el) && hasControl(el)) {
                          const rect = el.getBoundingClientRect();
                          if (rect.height <= 140 && rect.width <= 900) return mark(el);
                        }
                        if (el === searchRoot) break;
                      }
                      return mark(byField);
                    }
                    const label = normalize(args.label);
                    if (!label) return '';
                    const labelNodes = Array.from(searchRoot.querySelectorAll('label, span, div, [title], [class*="label"], [class*="Label"]'))
                      .filter(visible)
                      .filter((el) => {
                        const text = normalize(el.innerText || el.textContent || el.getAttribute('title'));
                        return labelMatches(text, label);
                      })
                      .sort((a, b) => layerScore(b) - layerScore(a));
                    for (const labelNode of labelNodes) {
                      for (let el = labelNode.parentElement; el && el !== boundaryParent; el = el.parentElement) {
                        if (fieldLabelCount(el) > 1) break;
                        if (!visible(el) || !hasControl(el)) {
                          if (el === searchRoot) break;
                          continue;
                        }
                        const rect = el.getBoundingClientRect();
                        if (rect.height <= 140 && rect.width <= 900) return mark(el);
                        if (el === searchRoot) break;
                      }
                    }
                    const controls = Array.from(searchRoot.querySelectorAll(
                      'input:not([type="hidden"]), textarea, [contenteditable="true"], [role="textbox"], [role="combobox"], [role="switch"], [class*="switch"], [class*="Switch"]'
                    )).filter(visible);
                    for (const labelNode of labelNodes) {
                      const labelRect = labelNode.getBoundingClientRect();
                      const nearby = controls
                        .map((control) => ({ control, rect: control.getBoundingClientRect() }))
                        .filter((item) => item.rect.left >= labelRect.right - 5)
                        .map((item) => ({ ...item, score: Math.abs((item.rect.top + item.rect.bottom) / 2 - (labelRect.top + labelRect.bottom) / 2) + Math.max(0, item.rect.left - labelRect.right) / 20 }))
                        .sort((a, b) => a.score - b.score)[0];
                      if (!nearby || nearby.score > 80) continue;
                      for (let el = nearby.control.parentElement; el && el !== boundaryParent; el = el.parentElement) {
                        if (fieldLabelCount(el) > 1) break;
                        if (!visible(el) || !hasControl(el)) {
                          if (el === searchRoot) break;
                          continue;
                        }
                        const rect = el.getBoundingClientRect();
                        if (rect.height <= 140 && rect.width <= 900) return mark(el);
                        if (el === searchRoot) break;
                      }
                    }
                    return '';
                }""",
                {"label": label, "fieldid": fieldid, "dataField": data_field, "marker": marker},
            )
        except Exception:
            return root
        if not selector:
            return root
        try:
            return self._resolve_visible_locator(str(selector))
        except Exception:
            return root

    def _resolve_visible_locator(self, selector: str):
        fallback = None
        for context in self._all_search_contexts():
            locator = context.locator(selector)
            try:
                count = locator.count()
            except Exception:
                if fallback is None:
                    try:
                        fallback = locator.first
                    except Exception:
                        pass
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

    def _looks_like_choice_field(self, locator, bound_element: BoundElement) -> bool:
        runtime = bound_element.runtime
        candidate = getattr(bound_element, "candidate", None)
        component_name = str(getattr(candidate, "component_name", "") or "")
        normalized_component = component_name.lower().replace("-", "").replace("_", "")
        if "radio" in normalized_component:
            return False
        raw = getattr(candidate, "raw", {}) if candidate is not None else {}
        if normalized_component == "lcdenum" or _candidate_has_enum_type(raw):
            return True
        probe = f"{runtime.selector} {runtime.role or ''} {runtime.tag_name or ''} {runtime.name or ''} {component_name}"
        if "date" in probe.lower():
            return False
        if runtime.role in {"combobox", "listbox"} or runtime.tag_name == "select":
            return True
        if any(token in probe.lower() for token in ("select", "picker", "cascader", "dropdown", "tree")):
            return True
        if isinstance(raw, dict) and raw.get("runtime_only"):
            try:
                control = locator.evaluate(
                    """(node) => {
                      const selector = 'input:not([type="hidden"]), textarea, select, [contenteditable="true"], [role="textbox"], [role="combobox"], [role="listbox"]';
                      const element = node.matches?.(selector) ? node : node.querySelector(selector);
                      if (!element) return null;
                      return {
                        tag: String(element.tagName || '').toLowerCase(),
                        role: String(element.getAttribute('role') || '').toLowerCase(),
                        className: String(element.className || ''),
                        type: String(element.getAttribute('type') || '').toLowerCase(),
                        ariaHaspopup: String(element.getAttribute('aria-haspopup') || '').toLowerCase(),
                      };
                    }"""
                )
            except Exception:
                control = None
            if isinstance(control, dict):
                control_probe = " ".join(
                    str(control.get(key) or "")
                    for key in ("role", "className", "type", "ariaHaspopup")
                ).lower()
                if (
                    control.get("tag") in {"input", "textarea"}
                    and control.get("role") not in {"combobox", "listbox"}
                    and not any(token in control_probe for token in ("select", "picker", "cascader", "dropdown", "tree"))
                    and control.get("ariaHaspopup") not in {"true", "listbox", "menu", "dialog", "tree"}
                ):
                    return False
        try:
            class_name = locator.evaluate("(node) => node.className || ''")
        except Exception:
            return False
        return any(token in str(class_name).lower() for token in ("select", "picker", "cascader", "dropdown", "tree"))

    def _read_field_value_from_container(self, bound_element: BoundElement) -> str:
        candidate = getattr(bound_element, "candidate", None)
        fieldid = str(getattr(candidate, "fieldid", "") or "")
        label = str(getattr(candidate, "label", "") or "")
        value = self._read_field_value_from_candidate_identity(bound_element, label)
        if value:
            return value
        try:
            value = self._resolve_visible_locator(bound_element.runtime.selector).evaluate(
                _FIELD_VALUE_FROM_ROOT_SCRIPT,
                label,
            )
            if value:
                return str(value)
        except Exception:
            pass
        if not fieldid:
            return ""
        try:
            return self._require_page().evaluate(
                """({ fieldid, label }) => {
                    const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                    const root = Array.from(document.querySelectorAll(`[fieldid="${CSS.escape(fieldid)}"], [data-fieldid="${CSS.escape(fieldid)}"]`))
                      .find((el) => {
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
                      });
                    if (!root) return '';
                    const inputs = Array.from(root.querySelectorAll('input:not([type="checkbox"]), textarea, select'));
                    for (const input of inputs) {
                      const value = normalize(input.value || input.getAttribute('title') || '');
                      if (value && value !== label && value !== normalize(input.getAttribute('placeholder') || '')) return value;
                    }
                    const titled = Array.from(root.querySelectorAll('[title]'))
                      .map((el) => normalize(el.getAttribute('title')))
                      .find((value) => value && value !== label);
                    if (titled) return titled;
                    const labelNodes = Array.from(root.querySelectorAll('label, [class*="label"], [class*="Label"]'));
                    const labelTexts = new Set(labelNodes.map((el) => normalize(el.innerText || el.textContent)).filter(Boolean));
                    if (label) labelTexts.add(normalize(label));
                    const textNodes = Array.from(root.querySelectorAll('*'))
                      .filter((el) => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                      })
                      .map((el) => normalize(el.innerText || el.textContent))
                      .filter(Boolean)
                      .filter((text) => !labelTexts.has(text));
                    const longest = textNodes.sort((a, b) => a.length - b.length)[0];
                    if (longest) return longest;
                    let text = normalize(root.innerText || root.textContent);
                    for (const item of labelTexts) {
                      if (item) text = normalize(text.replace(item, ''));
                    }
                    return text;
                }""",
                {"fieldid": fieldid, "label": label},
            )
        except Exception:
            return ""

    def _read_field_value_from_candidate_identity(self, bound_element: BoundElement, label: str) -> str:
        candidate = getattr(bound_element, "candidate", None)
        identities = [
            str(getattr(candidate, "fieldid", "") or "").strip(),
            str(getattr(candidate, "key", "") or "").strip(),
            str(getattr(candidate, "data_field", "") or "").strip(),
        ]
        seen: set[str] = set()
        for identity in identities:
            if not identity or identity in seen:
                continue
            seen.add(identity)
            escaped = identity.replace("\\", "\\\\").replace('"', '\\"')
            selector = (
                f'[fieldid="{escaped}"], [data-fieldid="{escaped}"], '
                f'[data-field-id="{escaped}"], [uikey="{escaped}"], [name="{escaped}"], [id="{escaped}"]'
            )
            for context in self._all_search_contexts():
                try:
                    locator = context.locator(selector)
                    count = locator.count()
                except Exception:
                    continue
                for index in range(count):
                    root = locator.nth(index)
                    try:
                        if not root.is_visible(timeout=300):
                            continue
                        value = root.evaluate(_FIELD_VALUE_FROM_ROOT_SCRIPT, label)
                    except Exception:
                        continue
                    if value:
                        return str(value)
        return ""

    def _read_field_value_from_page_text(self, label: str) -> str:
        if not label:
            return ""
        try:
            return self._require_page().evaluate(
                """(label) => {
                    const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                    let lines = String(document.body.innerText || '').split(/\\n+/).map(normalize).filter(Boolean);
                    const detailIndex = Math.max(lines.lastIndexOf('项目详情'), lines.lastIndexOf('基本信息'));
                    if (detailIndex >= 0) lines = lines.slice(detailIndex + 1);
                    const endIndex = lines.findIndex((line) => line === '取消' || line === '业务助手');
                    if (endIndex >= 0) lines = lines.slice(0, endIndex);
                    for (let index = lines.length - 2; index >= 0; index -= 1) {
                      if (lines[index] === label || lines[index] === `${label}:` || lines[index] === `${label}：`) {
                        return lines[index + 1] || '';
                      }
                    }
                    for (const line of lines) {
                      for (const sep of [':', '：']) {
                        const prefix = `${label}${sep}`;
                        if (line.startsWith(prefix)) return normalize(line.slice(prefix.length));
                      }
                    }
                    return '';
                }""",
                label,
            )
        except Exception:
            return ""

    def _select_query_choice(
        self,
        root,
        fill_locator,
        value: Any,
        *,
        require_value_match: bool = False,
        root_already_active: bool = False,
        multi_select: bool = False,
    ) -> dict[str, Any] | None:
        if multi_select:
            return self._assign_multi_select_choice(
                root,
                fill_locator,
                value,
                root_already_active=root_already_active,
            )
        return self._select_single_query_choice(
            root,
            fill_locator,
            value,
            require_value_match=require_value_match,
            root_already_active=root_already_active,
        )

    def _select_single_query_choice(
        self,
        root,
        fill_locator,
        value: Any,
        *,
        require_value_match: bool = False,
        root_already_active: bool = False,
        require_unique_candidate: bool = False,
    ) -> dict[str, Any] | None:
        page = self._require_page()
        if not root_already_active:
            root.click(timeout=3000)
            page.wait_for_timeout(300)
        else:
            self._open_choice_field_without_scroll(root, fill_locator)
            page.wait_for_timeout(150)
            self._wait_for_query_choice_surface_ready(timeout_ms=2500)
        if self._popup_reference_module().wants_first_available(value):
            chosen = self._click_first_query_choice()
            if chosen:
                self._wait_for_query_choice_dropdown_to_settle()
                if self._query_choice_dropdown_visible():
                    self._force_dismiss_query_choice_dropdown(root)
                    self._wait_for_query_choice_dropdown_to_settle()
                if require_value_match:
                    actual = root.evaluate(_FIELD_VALUE_FROM_ROOT_SCRIPT, "")
                    if not self._choice_root_committed_value_matches(root, chosen):
                        raise RuntimeError(f"下拉选择后未回填: expected={chosen!r}, actual={actual!r}")
                    return {"actual": actual, "confirmed": True}
                return
            diagnostic = self._collect_choice_diagnostic_text()
            screenshot = self._save_diagnostic_screenshot("choice-first-available-missing")
            if screenshot:
                diagnostic = f"{diagnostic} | screenshot={screenshot}"
            raise RuntimeError(f"未找到第一条可用下拉候选: {diagnostic}")
        value = str(value)
        if self._query_choice_dropdown_visible() and not require_unique_candidate:
            if self._try_click_query_choice_with_wait(value, timeout_ms=800):
                if self._query_choice_selection_settled(root, value, require_value_match=require_value_match):
                    return
        self._fill_query_choice_filter(fill_locator, value, prevent_scroll=root_already_active)
        if require_unique_candidate:
            candidate_value = self._wait_for_unique_multi_select_candidate(root, value)
            result = root.evaluate(
                _MULTI_SELECT_SURFACE_SCRIPT,
                {
                    "action": "click-candidate",
                    "token": self._active_multi_select_surface_token,
                    "value": candidate_value,
                },
            )
            if isinstance(result, dict) and result.get("ok") is True:
                page.wait_for_timeout(300)
                return
            count = result.get("count") if isinstance(result, dict) else "未知"
            raise RuntimeError(f"当前字段候选项点击失败: {candidate_value}; count={count}")
        if self._try_click_query_choice_with_wait(value, timeout_ms=5000):
            if self._query_choice_selection_settled(root, value, require_value_match=require_value_match):
                return
        if self._try_click_query_choice_text_fallback(value):
            if self._query_choice_selection_settled(root, value, require_value_match=require_value_match):
                return
        self._open_existing_select_for_filter(root, fill_locator, value, prevent_scroll=root_already_active)
        if self._try_click_query_choice_with_wait(value, timeout_ms=5000):
            if self._query_choice_selection_settled(root, value, require_value_match=require_value_match):
                return
        if self._try_click_query_choice_text_fallback(value):
            if self._query_choice_selection_settled(root, value, require_value_match=require_value_match):
                return
        self._expand_query_choice_tree_until_visible(value)
        if self._try_click_query_choice_with_wait(value, timeout_ms=3000):
            if self._query_choice_selection_settled(root, value, require_value_match=require_value_match):
                return
        if self._try_click_query_choice_text_fallback(value):
            if self._query_choice_selection_settled(root, value, require_value_match=require_value_match):
                return
        if self._try_click_query_choice_with_wait(value):
            if self._query_choice_selection_settled(root, value, require_value_match=require_value_match):
                return
        if self._try_commit_query_choice_with_keyboard(root, fill_locator, value, require_value_match=require_value_match):
            return
        diagnostic = self._collect_choice_diagnostic_text()
        screenshot = self._save_diagnostic_screenshot("choice-missing")
        if screenshot:
            diagnostic = f"{diagnostic} | screenshot={screenshot}"
        raise RuntimeError(f"未找到查询条件可选值: {value}: {diagnostic}")

    def _assign_multi_select_choice(
        self,
        root,
        fill_locator,
        value: Any,
        *,
        root_already_active: bool = False,
    ) -> dict[str, list[str]]:
        expected = _normalize_multi_select_target_values(value)
        self._active_multi_select_surface_token = uuid.uuid4().hex
        try:
            self._prepare_multi_select_choice_surface(root, root_already_active=root_already_active)
            self._ensure_multi_select_choice_surface_open(
                root,
                fill_locator,
                root_already_active=root_already_active,
            )
        except Exception as exc:
            diagnostics = _multi_select_value_diagnostics(expected, [])
            raise MultiSelectAssignmentError(f"普通多选下拉候选面无法唯一关联: {exc}", diagnostics) from exc
        actual = self._read_multi_select_choice_values(root)
        diagnostics = _multi_select_value_diagnostics(expected, actual)
        if not diagnostics["missing_values"] and not diagnostics["unexpected_values"]:
            self._dismiss_multi_select_choice_surface(root)
            return {"expected_values": expected, "actual_values": actual}
        if actual:
            self._clear_multi_select_choice(root, fill_locator)
            self._ensure_multi_select_choice_surface_open(root, fill_locator, root_already_active=True)
            actual = self._read_multi_select_choice_values(root)
            diagnostics = _multi_select_value_diagnostics(expected, actual)
            if diagnostics["unexpected_values"]:
                self._dismiss_multi_select_choice_surface(root)
                raise MultiSelectAssignmentError("普通多选下拉无法移除已有选中项", diagnostics)
        for target in expected:
            try:
                self._select_single_query_choice(
                    root,
                    fill_locator,
                    target,
                    root_already_active=True,
                    require_unique_candidate=True,
                )
            except Exception as exc:
                self._ensure_multi_select_choice_surface_open(root, fill_locator)
                actual = self._read_multi_select_choice_values(root)
                diagnostics = _multi_select_value_diagnostics(expected, actual)
                self._dismiss_multi_select_choice_surface(root)
                raise MultiSelectAssignmentError(f"普通多选下拉目标选择失败: {exc}", diagnostics) from exc
            root_already_active = True
        self._ensure_multi_select_choice_surface_open(root, fill_locator)
        actual = self._read_multi_select_choice_values(root)
        diagnostics = _multi_select_value_diagnostics(expected, actual)
        self._dismiss_multi_select_choice_surface(root)
        if diagnostics["missing_values"] or diagnostics["unexpected_values"]:
            raise MultiSelectAssignmentError("普通多选下拉最终集合与目标集合不一致", diagnostics)
        return {"expected_values": expected, "actual_values": actual}

    def _prepare_multi_select_choice_surface(self, root, *, root_already_active: bool = False) -> None:
        root.evaluate(
            _MULTI_SELECT_SURFACE_SCRIPT,
            {
                "action": "prepare",
                "token": self._active_multi_select_surface_token,
                "allowExistingSingle": root_already_active,
            },
        )

    def _ensure_multi_select_choice_surface_open(
        self,
        root,
        fill_locator,
        *,
        root_already_active: bool = False,
    ) -> None:
        if self._multi_select_choice_surface_visible(root):
            return
        if root_already_active:
            self._open_choice_field_without_scroll(root, fill_locator)
        else:
            root.click(timeout=3000)
        self._wait_for_query_choice_surface_ready(timeout_ms=2500)
        result = root.evaluate(
            _MULTI_SELECT_SURFACE_SCRIPT,
            {"action": "attach", "token": self._active_multi_select_surface_token},
        )
        if not isinstance(result, dict) or result.get("ok") is not True:
            count = result.get("count") if isinstance(result, dict) else "未知"
            items = result.get("items") if isinstance(result, dict) else None
            raise RuntimeError(f"当前字段候选面不唯一: count={count}; surfaces={items}")

    def _multi_select_choice_surface_visible(self, root) -> bool:
        try:
            return bool(
                root.evaluate(
                    _MULTI_SELECT_SURFACE_SCRIPT,
                    {"action": "visible", "token": self._active_multi_select_surface_token},
                )
            )
        except Exception:
            return False

    def _dismiss_multi_select_choice_surface(self, root) -> None:
        if not self._multi_select_choice_surface_visible(root):
            return
        self._force_dismiss_query_choice_dropdown(root)
        self._wait_for_query_choice_dropdown_to_settle()

    def _read_multi_select_choice_values(self, root) -> list[str]:
        try:
            values = root.evaluate(
                """(node) => {
                    const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                    const selectors = [
                      '.w-select-selection-item', '.wui-select-selection-item',
                      '.ant-select-selection-item', '.u-select-selection-item',
                      '.w-select-selection__choice', '.wui-select-selection__choice',
                      '[class*="select-selection-item"]', '[class*="SelectSelectionItem"]',
                      '[class*="selection__choice"]', '[data-selection-item]'
                    ].join(',');
                    return Array.from(node.querySelectorAll(selectors)).map((item) => {
                      const clone = item.cloneNode(true);
                      clone.querySelectorAll('[class*="remove"], [class*="Remove"], [aria-label*="remove" i], [aria-label*="删除"]')
                        .forEach((child) => child.remove());
                      return normalize(item.getAttribute('title') || clone.textContent)
                        .replace(/[×xX]\\s*$/, '').trim();
                    }).filter(Boolean);
                }"""
            )
        except Exception:
            values = []
        selected = _unique_normalized_values(values if isinstance(values, list) else [])
        if selected:
            return selected
        return self._read_checked_multi_select_choice_values(root)

    def _read_checked_multi_select_choice_values(self, root) -> list[str]:
        try:
            values = root.evaluate(
                _MULTI_SELECT_SURFACE_SCRIPT,
                {"action": "read", "token": self._active_multi_select_surface_token},
            )
        except Exception:
            values = []
        return _unique_normalized_values(values if isinstance(values, list) else [])

    def _wait_for_unique_multi_select_candidate(self, root, value: str, timeout_ms: int = 5000) -> str:
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            try:
                result = root.evaluate(
                    _MULTI_SELECT_SURFACE_SCRIPT,
                    {"action": "candidates", "token": self._active_multi_select_surface_token},
                )
            except Exception:
                result = []
            candidates = result if isinstance(result, list) else []
            matches = [
                " ".join(str(candidate or "").split()).strip()
                for candidate in candidates
                if _multi_select_values_equivalent(value, candidate)
            ]
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                raise RuntimeError(f"普通多选下拉候选项身份歧义: {value}: {', '.join(matches)}")
            if time.monotonic() >= deadline:
                visible = _unique_normalized_values(candidates)
                raise RuntimeError(f"未找到当前字段多选候选项: {value}; candidates={visible[:20]}")
            self._require_page().wait_for_timeout(200)

    def _clear_multi_select_choice(self, root, fill_locator) -> None:
        page = self._require_page()
        try:
            root.hover(timeout=1000)
        except Exception:
            pass
        selectors = (
            ".w-select-clear, .wui-select-clear, .ant-select-clear, .u-select-clear, "
            ".w-select-selection__clear, .wui-select-selection__clear, "
            "[class*='select-clear'], [class*='SelectClear']"
        )
        try:
            clear = root.locator(selectors)
            for index in range(clear.count()):
                target = clear.nth(index)
                if target.is_visible(timeout=200):
                    target.click(timeout=1000)
                    page.wait_for_timeout(200)
                    if not self._read_multi_select_choice_values(root):
                        return
        except Exception:
            pass
        remove_selectors = (
            ".w-select-selection-item-remove, .wui-select-selection-item-remove, "
            ".ant-select-selection-item-remove, .u-select-selection-item-remove, "
            ".w-select-selection__choice__remove, .wui-select-selection__choice__remove, "
            "[class*='selection-item-remove'], [class*='selection__choice__remove']"
        )
        for _ in range(50):
            try:
                remove = root.locator(remove_selectors)
                visible = [remove.nth(index) for index in range(remove.count()) if remove.nth(index).is_visible(timeout=100)]
            except Exception:
                visible = []
            if not visible:
                break
            visible[0].click(timeout=1000)
            page.wait_for_timeout(120)
        try:
            root.evaluate(
                _MULTI_SELECT_SURFACE_SCRIPT,
                {"action": "clear", "token": self._active_multi_select_surface_token},
            )
            page.wait_for_timeout(200)
        except Exception:
            pass

    def _fill_query_choice_filter(self, fill_locator, value: str, *, prevent_scroll: bool = False) -> None:
        page = self._require_page()
        if not prevent_scroll:
            try:
                fill_locator.fill(value, timeout=1000)
                page.wait_for_timeout(500)
                return
            except Exception:
                pass
        self._set_query_choice_filter_value(fill_locator, value)

    def _open_choice_field_without_scroll(self, root, fill_locator) -> None:
        for locator in (fill_locator, root):
            try:
                locator.evaluate(
                    """(node) => {
                        const visible = (el) => {
                          const style = window.getComputedStyle(el);
                          const rect = el.getBoundingClientRect();
                          return style && style.visibility !== 'hidden' && style.display !== 'none'
                            && rect.width > 0 && rect.height > 0;
                        };
                        const selector = [
                          '.w-select-arrow',
                          '.wui-select-arrow',
                          '.ant-select-arrow',
                          '.u-select-arrow',
                          '[class*="select-arrow"]',
                          '[class*="SelectArrow"]',
                          '.w-select-selector',
                          '.wui-select-selector',
                          '.ant-select-selector',
                          '.u-select-selector',
                          'input:not([type="hidden"])',
                          '[role="combobox"]'
                        ].join(',');
                        const candidates = [
                          node,
                          ...Array.from(node.querySelectorAll ? node.querySelectorAll(selector) : [])
                        ].filter(visible);
                        const target = candidates.find((el) => /arrow/i.test(String(el.className || '')))
                          || candidates.find((el) => el.matches?.('input:not([type="hidden"]), [role="combobox"]'))
                          || candidates[0]
                          || node;
                        const rect = target.getBoundingClientRect();
                        const x = Math.max(rect.left + 1, Math.min(rect.left + rect.width / 2, rect.right - 1));
                        const y = Math.max(rect.top + 1, Math.min(rect.top + rect.height / 2, rect.bottom - 1));
                        try {
                          target.focus?.({ preventScroll: true });
                        } catch (_err) {
                          target.focus?.();
                        }
                        const init = { bubbles: true, cancelable: true, clientX: x, clientY: y, view: window };
                        for (const eventName of ['mouseover', 'mousemove', 'mousedown', 'mouseup', 'click']) {
                          target.dispatchEvent(new MouseEvent(eventName, init));
                        }
                    }"""
                )
                return
            except Exception:
                continue

    def _wait_for_query_choice_surface_ready(self, timeout_ms: int = 2500) -> bool:
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            for context in self._all_search_contexts():
                try:
                    if bool(
                        context.evaluate(
                            """() => {
                                const visible = (el) => {
                                  const style = window.getComputedStyle(el);
                                  const rect = el.getBoundingClientRect();
                                  return style && style.visibility !== 'hidden' && style.display !== 'none'
                                    && rect.width > 0 && rect.height > 0
                                    && !/hidden/i.test(String(el.className || ''));
                                };
                                const selector = '.w-select-dropdown, .wui-select-dropdown, .ant-select-dropdown, .u-select-dropdown, [role="listbox"], [class*="dropdown"], [class*="popup"]';
                                return Array.from(document.querySelectorAll(selector)).some((root) => {
                                  if (!visible(root)) return false;
                                  const text = String(root.innerText || root.textContent || '').replace(/\\s+/g, ' ').trim();
                                  return text && !/加载中|loading/i.test(text) && !root.querySelector(
                                    '.ant-spin-spinning, .wui-spin-spinning, .u-spin-spinning, [class*="loading"], [class*="Loading"]'
                                  );
                                });
                            }"""
                        )
                    ):
                        return True
                except Exception:
                    continue
            if time.monotonic() >= deadline:
                return False
            try:
                self._require_page().wait_for_timeout(120)
            except Exception:
                time.sleep(0.12)

    def _set_query_choice_filter_value(self, locator, value: str) -> None:
        page = self._require_page()
        try:
            locator.evaluate(
                """(node, value) => {
                    const editableSelector = [
                      'input:not([type="hidden"])',
                      'textarea',
                      '[contenteditable="true"]',
                      '[role="textbox"]',
                      '[role="combobox"]'
                    ].join(',');
                    const target = node.matches && node.matches(editableSelector)
                      ? node
                      : node.querySelector(editableSelector);
                    if (!target || target.disabled) return;
                    const visible = (el) => {
                      const style = window.getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style && style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width > 0 && rect.height > 0;
                    };
                    if (!visible(target)) return;
                    const tag = String(target.tagName || '').toUpperCase();
                    try {
                      target.focus?.({ preventScroll: true });
                    } catch (_err) {
                      target.focus?.();
                    }
                    if (target.isContentEditable || target.getAttribute('contenteditable') === 'true') {
                      target.textContent = value;
                    } else {
                      const proto = tag === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
                      const descriptor = Object.getOwnPropertyDescriptor(proto, 'value');
                      if (descriptor && descriptor.set) {
                        descriptor.set.call(target, value);
                      } else {
                        target.value = value;
                      }
                      target.defaultValue = value;
                      target.setAttribute('title', value);
                    }
                    for (const eventName of ['input', 'change', 'keyup']) {
                      const event = eventName === 'input' && typeof InputEvent !== 'undefined'
                        ? new InputEvent(eventName, { bubbles: true, inputType: 'insertText', data: value })
                        : new Event(eventName, { bubbles: true });
                      target.dispatchEvent(event);
                    }
                }""",
                value,
            )
        except Exception:
            pass
        page.wait_for_timeout(250)

    def _safe_active_element_debug(self) -> dict[str, Any]:
        try:
            return dict(
                self._require_page().evaluate(
                    r"""() => {
                        const node = document.activeElement;
                        if (!node) return {};
                        const rect = node.getBoundingClientRect();
                        const text = String(node.innerText || node.textContent || '').replace(/\s+/g, ' ').trim();
                        return {
                          tag: node.tagName,
                          class: String(node.className || ''),
                          id: node.id || '',
                          fieldid: node.getAttribute('fieldid') || '',
                          role: node.getAttribute('role') || '',
                          title: node.getAttribute('title') || '',
                          aria_label: node.getAttribute('aria-label') || '',
                          text: text.slice(0, 300),
                          rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
                          url: document.location.href,
                        };
                    }"""
                )
                or {}
            )
        except Exception as exc:
            return {"error": str(exc)[:500]}

    def _safe_locator_debug(self, locator) -> dict[str, Any]:
        try:
            return dict(
                locator.evaluate(
                    r"""(node) => {
                        const normalize = (value) => String(value || '').replace(/\s+/g, ' ').trim();
                        const rect = node.getBoundingClientRect();
                        const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
                        return {
                          tag: node.tagName,
                          class: String(node.className || ''),
                          id: node.id || '',
                          fieldid: node.getAttribute('fieldid') || '',
                          uikey: node.getAttribute('uikey') || '',
                          role: node.getAttribute('role') || '',
                          title: node.getAttribute('title') || '',
                          aria_label: node.getAttribute('aria-label') || '',
                          text: normalize(node.innerText || node.textContent).slice(0, 500),
                          rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
                          receives_pointer: Boolean(hit && (hit === node || node.contains(hit) || hit.contains(node))),
                          hit_tag: hit ? hit.tagName : '',
                          hit_class: hit ? String(hit.className || '') : '',
                          url: document.location.href,
                        };
                    }"""
                )
                or {}
            )
        except Exception as exc:
            return {"error": str(exc)[:500]}

    def _collapse_hovered_navigation_overlay(self) -> None:
        try:
            page = self._require_page()
            viewport = page.viewport_size or dict(GEOMETRY_FALLBACK_VIEWPORT)
            width = int(viewport.get("width") or GEOMETRY_FALLBACK_VIEWPORT["width"])
            height = int(viewport.get("height") or GEOMETRY_FALLBACK_VIEWPORT["height"])
            page.mouse.move(max(1, width - 12), max(80, min(height - 12, height // 2)))
            page.wait_for_timeout(180)
        except Exception:
            return

    def _open_existing_select_for_filter(self, root, fill_locator, value: str, *, prevent_scroll: bool = False):
        page = self._require_page()
        try:
            clear_icon = root.locator(".w-select-clear, .wui-select-clear, .ant-select-clear, [class*='select-clear']").first
            if clear_icon.count() > 0 and clear_icon.is_visible(timeout=300):
                clear_icon.click(timeout=1000)
                page.wait_for_timeout(300)
        except Exception:
            pass
        try:
            arrow = root.locator(".w-select-arrow, .wui-select-arrow, .ant-select-arrow, [class*='select-arrow']").first
            if arrow.count() > 0 and arrow.is_visible(timeout=300):
                arrow.click(timeout=1000)
                page.wait_for_timeout(300)
        except Exception:
            try:
                root.click(timeout=1000)
                page.wait_for_timeout(300)
            except Exception:
                pass
        self._fill_query_choice_filter(fill_locator, value, prevent_scroll=prevent_scroll)

    def _wait_for_query_choice_dropdown_to_settle(self) -> None:
        page = self._require_page()
        for _ in range(10):
            page.wait_for_timeout(150)
            if not self._query_choice_dropdown_visible():
                return

    def _query_choice_selection_settled(self, root, value: str, *, require_value_match: bool = False) -> bool:
        self._wait_for_query_choice_dropdown_to_settle()
        matched = self._choice_root_value_matches(root, value)
        if matched is not None:
            if matched or self._choice_root_visible_value_matches(root, value):
                self._blur_query_choice_root(root)
                self._wait_for_query_choice_dropdown_to_settle()
                if self._query_choice_dropdown_visible():
                    self._force_dismiss_query_choice_dropdown(root)
                    self._wait_for_query_choice_dropdown_to_settle()
                if require_value_match:
                    return self._choice_root_committed_value_matches(root, value)
                return True
            return False
        if self._choice_root_visible_value_matches(root, value):
            self._blur_query_choice_root(root)
            self._wait_for_query_choice_dropdown_to_settle()
            if self._query_choice_dropdown_visible():
                self._force_dismiss_query_choice_dropdown(root)
                self._wait_for_query_choice_dropdown_to_settle()
            if require_value_match:
                return self._choice_root_committed_value_matches(root, value)
            return True
        settled = not self._query_choice_dropdown_visible()
        if settled:
            if require_value_match:
                return False
            self._blur_query_choice_root(root)
        return settled

    def _choice_root_committed_value_matches(self, root, value: str) -> bool:
        try:
            return bool(
                root.evaluate(
                    """(node, value) => {
                        const normalize = (text) => String(text || '').replace(/\\s+/g, ' ').trim();
                        const wanted = normalize(value);
                        const matches = (text) => {
                          const normalized = normalize(text);
                          if (!normalized) return false;
                          return normalized === wanted || normalized.endsWith(` ${wanted}`) || normalized.includes(wanted);
                        };
                        const visible = (el) => {
                          const style = window.getComputedStyle(el);
                          const rect = el.getBoundingClientRect();
                          return style && style.visibility !== 'hidden' && style.display !== 'none'
                            && rect.width > 0 && rect.height > 0;
                        };
                        const dropdownSelector = [
                          '.w-select-dropdown',
                          '.wui-select-dropdown',
                          '.ant-select-dropdown',
                          '.u-select-dropdown',
                          '[role="listbox"]',
                          '[class*="dropdown"]',
                          '[class*="popup"]'
                        ].join(',');
                        const editorSelector = [
                          'input',
                          'textarea',
                          'select',
                          '[contenteditable="true"]',
                          '[role="textbox"]',
                          '[role="combobox"]'
                        ].join(',');
                        const values = [];
                        for (const item of Array.from(node.querySelectorAll(
                          '.wui-select-selection-item, .ant-select-selection-item, .u-select-selection-item, [class*="selection-item"], [class*="SelectionItem"], [class*="selected-value"], [class*="SelectedValue"]'
                        ))) {
                          if (visible(item) && !item.closest(dropdownSelector)) {
                            values.push(item.getAttribute('title'), item.innerText, item.textContent);
                          }
                        }
                        const textParts = [];
                        const walker = document.createTreeWalker(
                          node,
                          NodeFilter.SHOW_TEXT,
                          {
                            acceptNode: (textNode) => {
                              const parent = textNode.parentElement;
                              if (!parent || parent.closest(dropdownSelector) || parent.closest(editorSelector) || !visible(parent)) {
                                return NodeFilter.FILTER_REJECT;
                              }
                              return NodeFilter.FILTER_ACCEPT;
                            },
                          }
                        );
                        while (walker.nextNode()) textParts.push(walker.currentNode.nodeValue);
                        values.push(textParts.join(' '));
                        const inputs = node.matches('input, textarea, select')
                          ? [node]
                          : Array.from(node.querySelectorAll('input, textarea, select'));
                        for (const input of inputs) {
                          if (!visible(input) || input.closest(dropdownSelector)) continue;
                          if (document.activeElement === input) continue;
                          values.push(input.value, input.getAttribute('title'));
                        }
                        return values.some(matches);
                    }""",
                    value,
                )
            )
        except Exception:
            return False

    def _choice_root_visible_value_matches(self, root, value: str) -> bool:
        try:
            return bool(
                root.evaluate(
                    """(node, value) => {
                        const normalize = (text) => String(text || '').replace(/\\s+/g, ' ').trim();
                        const wanted = normalize(value);
                        const matches = (text) => {
                          const normalized = normalize(text);
                          if (!normalized) return false;
                          return normalized === wanted || normalized.endsWith(` ${wanted}`) || normalized.includes(wanted);
                        };
                        const dropdownSelector = [
                          '.w-select-dropdown',
                          '.wui-select-dropdown',
                          '.ant-select-dropdown',
                          '.u-select-dropdown',
                          '[role="listbox"]',
                          '[class*="dropdown"]',
                          '[class*="popup"]',
                        ].join(',');
                        const visible = (el) => {
                          const style = window.getComputedStyle(el);
                          const rect = el.getBoundingClientRect();
                          return style && style.visibility !== 'hidden' && style.display !== 'none'
                            && rect.width > 0 && rect.height > 0;
                        };
                        const outsideDropdown = (el) => !el.closest(dropdownSelector);
                        const values = [];
                        for (const input of Array.from(node.querySelectorAll('input, textarea, select'))) {
                          if (outsideDropdown(input) && visible(input)) {
                            values.push(input.value, input.getAttribute('title'));
                          }
                        }
                        for (const item of Array.from(node.querySelectorAll(
                          '.wui-select-selection-item, .ant-select-selection-item, .u-select-selection-item, [class*="selection-item"], [class*="SelectionItem"], [class*="selected-value"], [class*="SelectedValue"]'
                        ))) {
                          if (outsideDropdown(item) && visible(item)) {
                            values.push(item.getAttribute('title'), item.innerText, item.textContent);
                          }
                        }
                        values.push(node.getAttribute('title'));
                        const textParts = [];
                        const walker = document.createTreeWalker(
                          node,
                          NodeFilter.SHOW_TEXT,
                          {
                            acceptNode: (textNode) => {
                              const parent = textNode.parentElement;
                              if (!parent || parent.closest(dropdownSelector) || !visible(parent)) {
                                return NodeFilter.FILTER_REJECT;
                              }
                              return NodeFilter.FILTER_ACCEPT;
                            },
                          }
                        );
                        while (walker.nextNode()) textParts.push(walker.currentNode.nodeValue);
                        values.push(textParts.join(' '));
                        return values.some(matches);
                    }""",
                    value,
                )
            )
        except Exception:
            return False

    def _blur_query_choice_root(self, root) -> None:
        try:
            root.press("Tab", timeout=800)
            self._require_page().wait_for_timeout(150)
        except Exception:
            try:
                self._require_page().keyboard.press("Tab")
                self._require_page().wait_for_timeout(150)
            except Exception:
                pass
        try:
            root.evaluate(
                """(node) => {
                    const active = document.activeElement;
                    if (active && typeof active.blur === 'function') active.blur();
                    node.dispatchEvent(new FocusEvent('focusout', { bubbles: true }));
                    node.dispatchEvent(new Event('blur', { bubbles: true }));
                }"""
            )
            self._require_page().wait_for_timeout(150)
        except Exception:
            pass

    def _force_dismiss_query_choice_dropdown(self, root) -> None:
        try:
            root.evaluate(
                """(node) => {
                    const active = document.activeElement;
                    if (active && typeof active.blur === 'function') active.blur();
                    node.dispatchEvent(new FocusEvent('focusout', { bubbles: true }));
                    node.dispatchEvent(new Event('blur', { bubbles: true }));
                }"""
            )
            self._require_page().wait_for_timeout(150)
        except Exception:
            pass
        try:
            self._require_page().keyboard.press("Tab")
            self._require_page().wait_for_timeout(150)
        except Exception:
            pass

    def _choice_root_value_matches(self, root, value: str) -> bool | None:
        try:
            return bool(
                root.evaluate(
                    """(node, value) => {
                        const normalize = (text) => String(text || '').replace(/\\s+/g, ' ').trim();
                        const wanted = normalize(value);
                        const matches = (text) => {
                          const normalized = normalize(text);
                          if (!normalized) return false;
                          return normalized === wanted || normalized.endsWith(` ${wanted}`) || normalized.includes(wanted);
                        };
                        const values = [];
                        const outsideDropdown = (el) => !el.closest('.w-select-dropdown, .wui-select-dropdown, .ant-select-dropdown, .u-select-dropdown, [role="listbox"], [class*="dropdown"], [class*="popup"]');
                        for (const input of Array.from(node.querySelectorAll('input, textarea, select'))) {
                          if (!outsideDropdown(input)) continue;
                          values.push(input.value, input.getAttribute('title'));
                        }
                        for (const item of Array.from(node.querySelectorAll(
                          '.wui-select-selection-item, .ant-select-selection-item, .u-select-selection-item, [class*="selection-item"], [class*="SelectionItem"], [class*="selected-value"], [class*="SelectedValue"]'
                        ))) {
                          if (outsideDropdown(item)) values.push(item.getAttribute('title'), item.innerText, item.textContent);
                        }
                        values.push(node.getAttribute('title'));
                        return values.some(matches);
                    }""",
                    value,
                )
            )
        except Exception:
            return None

    def _try_commit_query_choice_with_keyboard(
        self,
        root,
        fill_locator,
        value: str,
        *,
        require_value_match: bool = False,
        root_already_active: bool = False,
    ) -> bool:
        page = self._require_page()
        if not root_already_active:
            try:
                root.click(timeout=1000)
                page.wait_for_timeout(200)
            except Exception:
                pass
        for key in ("ArrowDown", "Enter"):
            try:
                fill_locator.press(key, timeout=1000)
                page.wait_for_timeout(250)
            except Exception:
                try:
                    page.keyboard.press(key)
                    page.wait_for_timeout(250)
                except Exception:
                    return False
        self._wait_for_query_choice_dropdown_to_settle()
        if require_value_match:
            return self._choice_root_committed_value_matches(root, value)
        matched = self._choice_root_value_matches(root, value)
        return bool(matched)

    def _query_choice_dropdown_visible(self) -> bool:
        selector = ".w-select-dropdown, .wui-select-dropdown, .ant-select-dropdown, .u-select-dropdown, [role='listbox']"
        for context in self._all_search_contexts():
            try:
                locator = context.locator(selector)
                count = min(locator.count(), 20)
                for index in range(count):
                    if locator.nth(index).is_visible(timeout=100):
                        return True
            except Exception:
                pass
            try:
                if bool(
                    context.evaluate(
                        """(selector) => {
                            const visible = (el) => {
                              const style = window.getComputedStyle(el);
                              const rect = el.getBoundingClientRect();
                              return style && style.visibility !== 'hidden' && style.display !== 'none'
                                && rect.width > 0 && rect.height > 0
                                && !/hidden/i.test(String(el.className || ''));
                            };
                            return Array.from(document.querySelectorAll(selector)).some(visible);
                        }""",
                        selector,
                    )
                ):
                    return True
            except Exception:
                continue
        return False

    def _try_click_query_choice(self, value: str) -> bool:
        selectors = build_query_choice_selectors(value)
        for context in self._all_search_contexts():
            self._last_query_choice_precise_action = ""
            if self._try_click_precise_query_choice_tree_node(value, context=context):
                return True
            if getattr(self, "_last_query_choice_precise_action", "") in {"expanded", "blocked"}:
                continue
            if self._try_click_first(selectors, context=context):
                return True
        return False

    def _try_click_precise_query_choice_tree_node(self, value: str, context=None) -> bool:
        search_context = context or self._page
        marker = f"ydf-query-choice-tree-{int(time.time() * 1000)}"
        self._last_query_choice_precise_action = ""
        try:
            result = search_context.evaluate(
                """({ value, marker }) => {
                    const normalize = (text) => String(text || '').replace(/\\s+/g, ' ').trim();
                    const wanted = normalize(value);
                    if (!wanted) return { action: '', selector: '' };
                    const visible = (el) => {
                      if (!el || !el.ownerDocument || !el.isConnected) return false;
                      const view = el.ownerDocument.defaultView || window;
                      const style = view.getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style && style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width > 0 && rect.height > 0;
                    };
                    const textOf = (el) => normalize(el.getAttribute('title') || el.innerText || el.textContent);
                    const matchRank = (el) => {
                      const text = textOf(el);
                      if (!text) return -1;
                      if (text === wanted) return 0;
                      if (text.endsWith(` ${wanted}`)) return 1;
                      if (text.includes(wanted) && text.length <= wanted.length + 16) return 2;
                      return -1;
                    };
                    const wantedHasLeadingCode = /^\\d+/.test(wanted);
                    const codedLeafRank = (el) => {
                      const text = textOf(el);
                      if (wantedHasLeadingCode) return 1;
                      return /^\\d+\\s+/.test(text) && text.endsWith(` ${wanted}`) ? 0 : 1;
                    };
                    const dropdownSelector = [
                      '.w-select-dropdown',
                      '.wui-select-dropdown',
                      '.ant-select-dropdown',
                      '.u-select-dropdown',
                      '[role="listbox"]',
                      '[class*="dropdown"]',
                      '[class*="popup"]'
                    ].join(',');
                    const optionSelector = [
                      '.wui-select-tree-title',
                      '.wui-tree-title',
                      '.w-select-tree-title',
                      '.w-tree-title',
                      '.wui-select-tree-node-content-wrapper',
                      '.wui-tree-node-content-wrapper',
                      '.w-select-tree-node-content-wrapper',
                      '.w-tree-node-content-wrapper',
                      '[role="treeitem"]',
                      '[role="option"]',
                      '[class*="tree"][class*="title"]',
                      '[class*="Tree"][class*="Title"]',
                      '[class*="tree"][class*="content"]',
                      '[class*="Tree"][class*="Content"]',
                      '[class*="select"][class*="item"]',
                      '[class*="Select"][class*="Item"]',
                      '[class*="option"]',
                      '[class*="Option"]',
                      'li',
                      'span',
                      'div'
                    ].join(',');
                    const treeNodeFor = (el) => el.closest([
                      '[role="treeitem"]',
                      '.wui-select-tree-treenode',
                      '.wui-tree-treenode',
                      '.w-select-tree-treenode',
                      '.w-tree-treenode',
                      '[class*="tree"][class*="treenode"]',
                      '[class*="Tree"][class*="TreeNode"]',
                      'li'
                    ].join(','));
                    const switchersFor = (node) => {
                      const selector = [
                        '.wui-tree-switcher',
                        '.wui-select-tree-switcher',
                        '.w-tree-switcher',
                        '[class*="switcher"]',
                        '[class*="Switcher"]'
                      ].join(',');
                      return Array.from(node.querySelectorAll(selector)).filter((item) => {
                        if (!visible(item)) return false;
                        const owner = treeNodeFor(item);
                        return !owner || owner === node;
                      });
                    };
                    const nodeExpandedState = (node) => {
                      const expanded = node.getAttribute('aria-expanded');
                      if (expanded === 'true' || expanded === 'false') return expanded;
                      const child = node.querySelector('[aria-expanded="true"], [aria-expanded="false"]');
                      if (child && treeNodeFor(child) === node) return child.getAttribute('aria-expanded');
                      return '';
                    };
                    const hasSelectableLeafShape = (el) => {
                      const node = treeNodeFor(el);
                      if (!node) return true;
                      const switchers = switchersFor(node);
                      if (switchers.length && switchers.every((item) => /noop|leaf|none/i.test(String(item.className || '')))) {
                        return true;
                      }
                      if (nodeExpandedState(node)) return false;
                      const className = String(node.className || '');
                      if (/treenode-(open|close)|tree-node-(open|close)|switcher-(open|close)|switcher_open|switcher_close/i.test(className)) {
                        return false;
                      }
                      if (!switchers.length) return true;
                      return false;
                    };
                    const closedSwitcherFor = (el) => {
                      const node = treeNodeFor(el);
                      if (!node) return null;
                      const switchers = switchersFor(node);
                      return switchers.find((item) => {
                        const className = String(item.className || '');
                        const expanded = item.getAttribute('aria-expanded') || nodeExpandedState(node);
                        return expanded === 'false' || /close|collapsed/i.test(className);
                      }) || null;
                    };
                    const roots = Array.from(document.querySelectorAll(dropdownSelector)).filter(visible);
                    let candidates = [];
                    for (const root of roots) {
                      for (const el of Array.from(root.querySelectorAll(optionSelector))) {
                        if (!visible(el)) continue;
                        const rank = matchRank(el);
                        if (rank < 0) continue;
                        if (el.matches('input, textarea, button, select') || el.closest('input, textarea, button, select')) continue;
                        const rect = el.getBoundingClientRect();
                        const leafRank = hasSelectableLeafShape(el) ? 0 : 1;
                        const codeRank = codedLeafRank(el);
                        const roleRank = el.matches('.wui-select-tree-title, .wui-tree-title, .w-select-tree-title, .w-tree-title, [class*="tree"][class*="title"], [class*="Tree"][class*="Title"]') ? 0 : 1;
                        candidates.push({ el, leafRank, codeRank, roleRank, rank, area: rect.width * rect.height, top: rect.top, left: rect.left });
                      }
                    }
                    candidates.sort((a, b) => a.leafRank - b.leafRank || a.codeRank - b.codeRank || a.rank - b.rank || a.roleRank - b.roleRank || a.area - b.area || a.top - b.top || a.left - b.left);
                    const targetItem = candidates[0];
                    const target = targetItem && targetItem.el;
                    if (!target) return { action: '', selector: '' };
                    if (targetItem.leafRank > 0) {
                      const switcher = closedSwitcherFor(target);
                      if (switcher) {
                        switcher.setAttribute('data-ydf-browser-query-choice-tree-target', marker);
                        return { action: 'expanded', selector: `[data-ydf-browser-query-choice-tree-target="${marker}"]` };
                      }
                      return { action: 'blocked', selector: '' };
                    }
                    target.setAttribute('data-ydf-browser-query-choice-tree-target', marker);
                    return { action: 'clicked', selector: `[data-ydf-browser-query-choice-tree-target="${marker}"]` };
                }""",
                {"value": value, "marker": marker},
            )
        except Exception:
            return False
        if isinstance(result, dict):
            action = str(result.get("action") or "")
            selector = str(result.get("selector") or "")
        else:
            action = "clicked" if result else ""
            selector = str(result or "")
        self._last_query_choice_precise_action = action
        if not selector:
            return False
        try:
            target = search_context.locator(str(selector)).first
            if not self._click_query_choice_target_without_scroll(target):
                try:
                    target.click(timeout=2000)
                except Exception:
                    target.click(force=True, timeout=2000)
            self._require_page().wait_for_timeout(300)
            return action == "clicked"
        except Exception:
            return False

    def _click_query_choice_target_without_scroll(self, target) -> bool:
        try:
            page = self._require_page()
            box = target.bounding_box(timeout=2000)
            if box:
                width = float(box.get("width") or 0)
                height = float(box.get("height") or 0)
                if width > 0 and height > 0:
                    x = float(box.get("x") or 0) + min(max(width / 2, 1), max(width - 1, 1))
                    y = float(box.get("y") or 0) + min(max(height / 2, 1), max(height - 1, 1))
                    page.mouse.move(x, y)
                    page.mouse.down()
                    page.mouse.up()
                    return True
        except Exception:
            pass
        try:
            target.evaluate(
                """(node) => {
                    const visible = (el) => {
                      const style = window.getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style && style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width > 0 && rect.height > 0;
                    };
                    if (!visible(node)) return false;
                    const rect = node.getBoundingClientRect();
                    const x = Math.max(rect.left + 1, Math.min(rect.left + rect.width / 2, rect.right - 1));
                    const y = Math.max(rect.top + 1, Math.min(rect.top + rect.height / 2, rect.bottom - 1));
                    const clickTarget = document.elementFromPoint(x, y) || node;
                    const init = { bubbles: true, cancelable: true, clientX: x, clientY: y, view: window };
                    for (const eventName of ['mouseover', 'mousemove', 'mousedown', 'mouseup', 'click']) {
                      clickTarget.dispatchEvent(new MouseEvent(eventName, init));
                    }
                    return true;
                }"""
            )
            return True
        except Exception:
            return False

    def _try_click_query_choice_with_wait(self, value: str, timeout_ms: int = 1200) -> bool:
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            if self._try_click_query_choice(value):
                return True
            if time.monotonic() >= deadline:
                return False
            self._require_page().wait_for_timeout(250)

    def _try_click_query_choice_text_fallback(self, value: str) -> bool:
        for context in self._all_search_contexts():
            self._last_query_choice_precise_action = ""
            if self._try_click_precise_query_choice_tree_node(value, context=context):
                return True
            if getattr(self, "_last_query_choice_precise_action", "") in {"expanded", "blocked"}:
                continue
            try:
                clicked = bool(
                    context.evaluate(
                    """(value) => {
                        const normalize = (text) => (text || '').replace(/\\s+/g, ' ').trim();
                        const visible = (el) => {
                          const style = window.getComputedStyle(el);
                          const rect = el.getBoundingClientRect();
                          return style && style.visibility !== 'hidden' && style.display !== 'none'
                            && rect.width > 0 && rect.height > 0;
                        };
                        const roots = Array.from(document.querySelectorAll(
                          '.w-select-dropdown, .wui-select-dropdown, .ant-select-dropdown, .u-select-dropdown, [role="listbox"], [class*="popup"], [class*="dropdown"], [class*="refer"], [class*="ref"]'
                        )).filter(visible);
                        const matches = (text) => {
                          const normalized = normalize(text);
                          if (normalized === value) return true;
                          if (normalized.endsWith(` ${value}`)) return true;
                          return normalized.includes(value);
                        };
                        const optionSelector = [
                          '[role="option"]',
                          '[role="treeitem"]',
                          '.wui-select-item-option',
                          '.ant-select-item-option',
                          '.u-select-item-option',
                          '.wui-tree-node-content-wrapper',
                          '.wui-select-tree-node-content-wrapper',
                          '[class*="select"][class*="item"]',
                          '[class*="Select"][class*="Item"]',
                          '[class*="dropdown"][class*="item"]',
                          '[class*="Dropdown"][class*="Item"]',
                          '[class*="menu-item"]',
                          '[class*="menu"][class*="item"]',
                          'li'
                        ].join(',');
                        for (const root of roots) {
                          let candidates = Array.from(root.querySelectorAll(optionSelector)).filter(visible);
                          if (!candidates.length) {
                            candidates = Array.from(root.querySelectorAll('*')).filter(visible);
                          }
                          candidates.sort((a, b) => {
                            const ar = a.getBoundingClientRect();
                            const br = b.getBoundingClientRect();
                            return (ar.width * ar.height) - (br.width * br.height);
                          });
                          for (const candidate of candidates) {
                            if (matches(candidate.innerText || candidate.textContent)) {
                              const target = candidate.closest(
                                '[role="option"], .wui-select-item-option, .ant-select-item-option, .u-select-item-option, [class*="select"][class*="item"], [class*="Select"][class*="Item"], [class*="dropdown"][class*="item"], [class*="Dropdown"][class*="Item"], [role="treeitem"], .wui-tree-node-content-wrapper, .wui-select-tree-node-content-wrapper, li'
                              ) || candidate;
                              target.click();
                              return true;
                            }
                          }
                        }
                        return false;
                    }""",
                    value,
                    )
                )
                if clicked:
                    return True
            except Exception:
                continue
        return False

    def _click_first_query_choice(self) -> str:
        page = self._require_page()
        try:
            marker = f"first-choice-{int(time.time() * 1000)}"
            click_target_selector = page.evaluate(
                """(marker) => {
                    const normalize = (text) => String(text || '').replace(/\\s+/g, ' ').trim();
                    const visible = (el) => {
                      const style = window.getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style && style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width > 0 && rect.height > 0;
                    };
                    const disabled = (el) => {
                      const className = String(el.className || '');
                      return el.disabled || el.getAttribute('aria-disabled') === 'true' || /disabled/i.test(className);
                    };
                    const roots = Array.from(document.querySelectorAll(
                      '.w-select-dropdown, .wui-select-dropdown, .ant-select-dropdown, .u-select-dropdown, [role="listbox"], [class*="popup"], [class*="dropdown"]'
                    )).filter(visible);
                    const optionSelector = [
                      '[role="option"]',
                      '[role="treeitem"]',
                      '.wui-select-item-option',
                      '.ant-select-item-option',
                      '.u-select-item-option',
                      '.wui-tree-node-content-wrapper',
                      '.wui-select-tree-node-content-wrapper',
                      '[class*="select"][class*="item"]',
                      '[class*="Select"][class*="Item"]',
                      '[class*="dropdown"][class*="item"]',
                      '[class*="Dropdown"][class*="Item"]',
                      '[class*="menu-item"]',
                      '[class*="menu"][class*="item"]',
                      'li'
                    ].join(',');
                    const excluded = 'button, input, textarea, select, [role="button"]';
                    const candidates = [];
                    for (const root of roots) {
                      for (const candidate of Array.from(root.querySelectorAll(optionSelector))) {
                        if (!visible(candidate) || disabled(candidate) || candidate.matches(excluded) || candidate.closest(excluded)) continue;
                        const rect = candidate.getBoundingClientRect();
                        const text = normalize(candidate.innerText || candidate.textContent || candidate.getAttribute('title'));
                        if (!text) continue;
                        candidates.push({ target: candidate, top: rect.top, left: rect.left, area: rect.width * rect.height });
                      }
                    }
                    if (!candidates.length) {
                      for (const root of roots) {
                        candidates = candidates.concat(Array.from(root.querySelectorAll('*'))
                          .filter((candidate) => visible(candidate) && !disabled(candidate) && !candidate.matches(excluded) && !candidate.closest(excluded))
                          .filter((candidate) => !Array.from(candidate.children).some((child) => visible(child) && normalize(child.innerText || child.textContent)))
                          .map((target) => {
                            const rect = target.getBoundingClientRect();
                            return { target, top: rect.top, left: rect.left, area: rect.width * rect.height };
                          })
                          .filter((item) => normalize(item.target.innerText || item.target.textContent || item.target.getAttribute('title'))));
                      }
                    }
                    candidates.sort((a, b) => a.top - b.top || a.left - b.left || a.area - b.area);
                    const target = candidates[0] && candidates[0].target;
                    if (!target) return '';
                    target.setAttribute('data-ydf-browser-first-choice', marker);
                    return `[data-ydf-browser-first-choice="${marker}"]`;
                }""",
                marker,
            )
            if not click_target_selector:
                return ""
            target = page.locator(str(click_target_selector)).first
            chosen = " ".join(target.evaluate(
                "(node) => node.innerText || node.textContent || node.getAttribute('title') || ''"
            ).split())
            try:
                target.scroll_into_view_if_needed(timeout=1000)
            except Exception:
                pass
            try:
                target.click(timeout=2000)
            except Exception:
                target.click(force=True, timeout=2000)
            return chosen
        except Exception:
            return ""

    def _collect_choice_diagnostic_text(self) -> str:
        page = self._require_page()
        selectors = [
            ".w-select-dropdown",
            ".wui-select-dropdown",
            ".ant-select-dropdown",
            ".u-select-dropdown",
            '[class*="popup"]',
            '[class*="dropdown"]',
            '[class*="refer"]',
            '[class*="ref"]',
        ]
        snippets: list[str] = []
        for selector in selectors:
            locator = page.locator(selector)
            try:
                count = locator.count()
            except Exception:
                continue
            for index in range(min(count, 3)):
                item = locator.nth(index)
                try:
                    if not item.is_visible(timeout=200):
                        continue
                    text = " ".join((item.inner_text(timeout=500) or "").split())
                    if text:
                        snippets.append(f"{selector}[{index}]={text[:500]}")
                except Exception:
                    continue
        return " | ".join(snippets[:6]) or "无可见下拉/参照候选"

    def _expand_query_choice_tree_until_visible(self, value: str, max_rounds: int = 16) -> None:
        page = self._require_page()
        for _ in range(max_rounds):
            if self._is_any_visible(build_query_choice_selectors(value)):
                return
            expanded = False
            for selector in build_query_choice_tree_closed_switcher_selectors():
                locator = page.locator(selector)
                try:
                    count = locator.count()
                except Exception:
                    continue
                for index in range(count):
                    candidate = locator.nth(index)
                    try:
                        if not candidate.is_visible(timeout=300):
                            continue
                        candidate.click(timeout=2000)
                        page.wait_for_timeout(400)
                        expanded = True
                        break
                    except Exception:
                        continue
                if expanded:
                    break
            if not expanded:
                return

    def _resolve_visible_row_action(self, action_label: str) -> BoundElement:
        selector = self._find_first_visible_row_action_selector(build_row_action_selectors(action_label))
        if selector is None:
            raise RuntimeError(f"未找到可点击行级动作: {action_label}")
        return self._build_visible_action_bound_element(action_label, selector, reason="visible_row_action")

    def _resolve_visible_toolbar_action(
        self,
        action_label: str,
        fieldid: str | None = None,
        aliases: list[str] | None = None,
    ) -> BoundElement:
        labels = _ordered_toolbar_labels(action_label, aliases)
        selector = None
        if fieldid:
            selector = self._find_first_visible_fieldid_action_selector(
                fieldid,
                labels=labels,
                strict_label=True,
                exclude_table_scoped=True,
                allow_blocked=False,
            )
        for label in labels:
            if selector is not None:
                break
            selector = self._find_first_visible_exact_text_selector(
                build_toolbar_exact_text_selectors(),
                label,
                exclude_table_scoped=True,
            )
        if selector is None and fieldid:
            selector = self._find_first_visible_fieldid_action_selector(
                fieldid,
                exclude_table_scoped=True,
                allow_blocked=False,
            )
        for label in labels:
            if selector is not None:
                break
            selector = self._find_first_visible_selector(
                build_toolbar_action_selectors(label),
                exclude_table_scoped=True,
            )
        if selector is None and fieldid:
            # 遮挡身份仅用于最终诊断，不能抢占前景可点击的同名动作。
            selector = self._find_first_visible_fieldid_action_selector(
                fieldid, labels=labels, exclude_table_scoped=True,
            ) or self._find_first_visible_fieldid_action_selector(fieldid, exclude_table_scoped=True)
        if selector is None:
            raise RuntimeError(f"未找到可点击工具栏动作: {action_label}")
        return self._build_visible_action_bound_element(
            action_label,
            selector,
            reason="visible_toolbar_action",
            fieldid=fieldid,
        )

    def _resolve_visible_tab_action(self, action_label: str, fieldid: str | None = None) -> BoundElement:
        deadline = self._tab_retry_now() + _TAB_RETRY_TIMEOUT_S
        while True:
            selector = self._find_first_visible_selector(build_tab_action_selectors(action_label, fieldid=fieldid))
            if selector is None:
                selector = self._find_first_visible_exact_text_selector(build_tab_exact_text_selectors(), action_label)
            if selector is not None:
                return self._build_visible_action_bound_element(action_label, selector, reason="visible_tab_action")
            if self._tab_retry_now() >= deadline:
                raise RuntimeError(f"未找到可点击页签: {action_label}")
            self._tab_retry_sleep(_TAB_RETRY_INTERVAL_S)

    def _tab_retry_sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def _tab_retry_now(self) -> float:
        return time.monotonic()

    def _collect_tab_diagnostic(self, fieldid: str | None, action_label: str) -> str:
        page = self._require_page()
        parts: list[str] = []
        if fieldid:
            fieldid_selector = f'[fieldid="{fieldid}"]'
            try:
                fieldid_locator = page.locator(fieldid_selector)
                fieldid_count = fieldid_locator.count()
            except Exception:
                fieldid_count = -1
            if fieldid_count > 0:
                first_match = fieldid_locator.first
                try:
                    visible = first_match.is_visible(timeout=300)
                except Exception:
                    visible = False
                try:
                    box = first_match.bounding_box(timeout=300)
                except Exception:
                    box = None
                parts.append(f"fieldid候选 selector={fieldid_selector} count={fieldid_count} visible={visible} box={box}")
            else:
                parts.append(f"fieldid候选 selector={fieldid_selector} count={fieldid_count}")
        stepbar_selector = '[fieldid="stepBar"]'
        try:
            stepbar_locator = page.locator(stepbar_selector)
            stepbar_count = stepbar_locator.count()
        except Exception:
            stepbar_count = -1
        if stepbar_count > 0:
            try:
                children = stepbar_locator.first.locator(".wui-steps-item-wrap").count()
            except Exception:
                children = -1
            parts.append(f"stepBar容器 selector={stepbar_selector} count={stepbar_count} 子元素={children}")
        else:
            parts.append(f"stepBar容器 selector={stepbar_selector} count={stepbar_count}")
        text_selector = f'text="{action_label}"'
        try:
            text_count = page.locator(text_selector).count()
        except Exception:
            text_count = -1
        parts.append(f"文本匹配 selector={text_selector} count={text_count}")
        return " | ".join(parts)

    def _click_toolbar_bound_action(
        self,
        action_label: str,
        fieldid: str | None = None,
        aliases: list[str] | None = None,
    ) -> None:
        try:
            bound = self._resolve_visible_toolbar_action(action_label, fieldid=fieldid, aliases=aliases)
        except TypeError:
            if fieldid is not None or aliases:
                raise
            bound = self._resolve_visible_toolbar_action(action_label)
        if _is_download_action(action_label):
            self._click_and_save_download(bound)
            return
        self.click(bound)

    def _click_toolbar_dropdown_sub_action(
        self,
        label: str,
        sub_label: str,
        fieldid: str | None = None,
        aliases: list[str] | None = None,
    ) -> None:
        page = self._require_page()
        bound = self._resolve_visible_toolbar_action(label, fieldid=fieldid, aliases=aliases)
        trigger = self._resolve_visible_locator(bound.runtime.selector)
        selector = self._find_visible_toolbar_dropdown_item_selector(sub_label)
        if selector is None:
            try:
                trigger.hover(timeout=3000)
                page.wait_for_timeout(500)
            except Exception:
                pass
            selector = self._find_visible_toolbar_dropdown_item_selector(sub_label)
        if selector is None:
            if self._click_toolbar_dropdown_trigger_part(trigger):
                page.wait_for_timeout(500)
                selector = self._find_visible_toolbar_dropdown_item_selector(sub_label)
        if selector is None:
            try:
                trigger.click(timeout=3000)
                page.wait_for_timeout(500)
            except Exception:
                pass
            selector = self._find_visible_toolbar_dropdown_item_selector(sub_label)
        if selector is None:
            diagnostic = self._collect_page_diagnostic_text()
            screenshot = self._save_diagnostic_screenshot("toolbar-dropdown-sub-action-missing")
            if screenshot:
                diagnostic = f"{diagnostic} | screenshot={screenshot}"
            raise RuntimeError(f"未找到工具栏下拉子按钮: {label}>{sub_label}: {diagnostic}")
        item = self._resolve_visible_locator(selector)
        if _is_download_action(sub_label):
            self._click_locator_and_save_download(item)
        else:
            self._prepare_action_surface(item)
            item.click(timeout=3000)

    def _click_toolbar_dropdown_trigger_part(self, trigger) -> bool:
        selectors = [
            '[aria-haspopup="menu"]',
            '[aria-expanded]',
            '[class*="dropdown"]',
            '[class*="Dropdown"]',
            '[class*="down"]',
            '[class*="Down"]',
            '[class*="arrow"]',
            '[class*="Arrow"]',
            '[class*="xiangxia"]',
            ".anticon-down",
            ".wui-icon-down",
            ".uf-arrow-down",
            ".uf-triangle-down",
            ".icon-xiangxia",
        ]
        for selector in selectors:
            try:
                locator = trigger.locator(selector)
                count = locator.count()
            except Exception:
                continue
            for index in range(count):
                candidate = locator.nth(index)
                try:
                    if not candidate.is_visible(timeout=300):
                        continue
                    candidate.click(timeout=2000)
                    return True
                except Exception:
                    continue
        return False

    def _find_visible_toolbar_dropdown_item_selector(self, sub_label: str) -> str | None:
        return self._find_first_visible_exact_text_selector(build_toolbar_dropdown_item_selectors(), sub_label)

    def _click_and_save_download(self, bound_element: BoundElement) -> None:
        self._click_selector_and_save_download(bound_element.runtime.selector)

    def _click_selector_and_save_download(self, selector: str) -> None:
        page = self._require_page()
        locator = self._resolve_visible_locator(selector)
        self._click_locator_and_save_download(locator)

    def _click_locator_and_save_download(self, locator) -> None:
        page = self._require_page()
        try:
            with page.expect_download(timeout=15000) as download_info:
                locator.click(timeout=3000)
            download = download_info.value
        except Exception as exc:
            page.wait_for_timeout(1000)
            diagnostic = self._collect_page_diagnostic_text()
            screenshot = self._save_diagnostic_screenshot("download-missing")
            if screenshot:
                diagnostic = f"{diagnostic} | screenshot={screenshot}"
            raise RuntimeError(f"点击导出后未捕获到浏览器下载事件: {diagnostic}") from exc
        target = _unique_download_path(download.suggested_filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        download.save_as(str(target))
        self.downloaded_files.append(str(target))
        page.wait_for_timeout(600)

    def _open_import_sub_action(self, label: str, sub_action: str) -> None:
        page = self._require_page()
        bound = self._resolve_visible_toolbar_action(label)
        trigger = self._resolve_visible_locator(bound.runtime.selector)
        trigger.hover(timeout=3000)
        page.wait_for_timeout(500)
        action_labels = _import_sub_action_aliases(sub_action)
        selector = None
        for action_label in action_labels:
            selector = self._find_first_visible_exact_text_selector(build_import_dropdown_item_selectors(), action_label)
            if selector is not None:
                break
        if selector is None:
            trigger.click(timeout=3000)
            page.wait_for_timeout(500)
            for action_label in action_labels:
                selector = self._find_first_visible_exact_text_selector(build_import_dropdown_item_selectors(), action_label)
                if selector is not None:
                    break
        if selector is None:
            diagnostic = self._collect_page_diagnostic_text()
            screenshot = self._save_diagnostic_screenshot("import-sub-action-missing")
            if screenshot:
                diagnostic = f"{diagnostic} | screenshot={screenshot}"
            raise RuntimeError(f"未找到导入子按钮: {sub_action}: {diagnostic}")
        self._resolve_visible_locator(selector).click(timeout=3000)
        self._wait_ready()

    def _select_import_workbench_file(self, files: list[str]) -> None:
        page = self._require_page()
        selector = self._find_first_visible_selector(build_import_file_button_selectors())
        if selector is None:
            input_locator = page.locator('input[type="file"]').first
            try:
                input_locator.set_input_files(files, timeout=3000)
            except Exception as exc:
                diagnostic = self._collect_page_diagnostic_text()
                screenshot = self._save_diagnostic_screenshot("import-file-button-missing")
                if screenshot:
                    diagnostic = f"{diagnostic} | screenshot={screenshot}"
                raise RuntimeError(f"未找到导入工作台选择文件按钮: {diagnostic}") from exc
        else:
            locator = self._resolve_visible_locator(selector)
            try:
                with page.expect_file_chooser(timeout=10000) as chooser_info:
                    locator.click(timeout=3000)
                chooser_info.value.set_files(files)
            except Exception:
                page.locator('input[type="file"]').first.set_input_files(files, timeout=5000)
        for file in files:
            self._wait_for_visible_text(Path(file).name, timeout_ms=10000)

    def _submit_import_workbench(self) -> None:
        selector = self._find_first_visible_selector(build_import_workbench_submit_selectors())
        if selector is None:
            diagnostic = self._collect_page_diagnostic_text()
            screenshot = self._save_diagnostic_screenshot("import-submit-missing")
            if screenshot:
                diagnostic = f"{diagnostic} | screenshot={screenshot}"
            raise RuntimeError(f"未找到导入工作台导入按钮: {diagnostic}")
        self._resolve_visible_locator(selector).click(timeout=3000)
        self._wait_ready()

    def _resolve_direct_import_action(
        self,
        label: str,
        action_candidates: list[dict[str, Any]] | None = None,
        fieldid: str | None = None,
    ) -> BoundElement | None:
        for candidate in action_candidates or []:
            if not _is_direct_file_import_candidate(candidate):
                continue
            if not _import_candidate_matches(candidate, label, fieldid):
                continue
            try:
                return self._resolve_visible_toolbar_action(
                    label,
                    fieldid=fieldid or str(candidate.get("fieldid") or "") or None,
                    aliases=_direct_file_import_aliases(candidate),
                )
            except Exception as exc:
                raise RuntimeError(f"未找到直连导入按钮: {label}") from exc
        if fieldid:
            return None
        try:
            bound = self._resolve_visible_toolbar_action(label)
        except Exception:
            return None
        return bound if _is_direct_file_import_action(bound) else None

    def _resolve_import_action(
        self,
        label: str,
        fieldid: str | None,
        action_candidates: list[dict[str, Any]],
    ) -> BoundElement:
        candidate = next(
            (
                item
                for item in action_candidates
                if _import_candidate_matches(item, label, fieldid)
            ),
            None,
        )
        aliases = _direct_file_import_aliases(candidate) if candidate is not None else None
        return self._resolve_visible_toolbar_action(
            label,
            fieldid=fieldid or (str(candidate.get("fieldid") or "") if candidate else None),
            aliases=aliases,
        )

    def _select_direct_import_file(self, bound: BoundElement, files: list[str]) -> None:
        page = self._require_page()
        locator = self._resolve_visible_locator(bound.runtime.selector)
        try:
            with page.expect_file_chooser(timeout=10000) as chooser_info:
                locator.click(timeout=3000)
            chooser_info.value.set_files(files)
        except Exception as exc:
            diagnostic = self._collect_page_diagnostic_text()
            screenshot = self._save_diagnostic_screenshot("direct-import-filechooser-missing")
            if screenshot:
                diagnostic = f"{diagnostic} | screenshot={screenshot}"
            raise RuntimeError(f"直连导入按钮未打开文件选择器: {diagnostic}") from exc

    def _try_select_direct_import_file(self, bound: BoundElement, files: list[str]) -> bool:
        page = self._require_page()
        locator = self._resolve_visible_locator(bound.runtime.selector)
        try:
            with page.expect_file_chooser(timeout=3000) as chooser_info:
                locator.click(timeout=3000)
            chooser_info.value.set_files(files)
            return True
        except Exception:
            return False

    def _start_direct_import_network_tracking(self, files: list[str]) -> None:
        self._direct_import_network_events = {}
        self._direct_import_filenames = [Path(file).name for file in files]
        self._direct_import_network_seeded = False
        self._direct_import_last_activity = time.monotonic()

    def _stop_direct_import_network_tracking(self) -> None:
        self._direct_import_network_events = None
        self._direct_import_filenames = []
        self._direct_import_network_seeded = False
        self._direct_import_last_activity = 0.0

    def _wait_for_direct_import_network_result(
        self,
        files: list[str],
        *,
        timeout_ms: int = 15000,
        quiet_ms: int = 500,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            events = list((self._direct_import_network_events or {}).values())
            complete = bool(events) and all(
                item.get("failed") or int(item.get("status") or 0) > 0
                for item in events
            )
            quiet = (time.monotonic() - self._direct_import_last_activity) * 1000 >= quiet_ms
            if complete and quiet:
                return _direct_import_network_result(files, events)
            page = self._require_page()
            page.wait_for_timeout(min(100, max(1, timeout_ms)))
        events = list((self._direct_import_network_events or {}).values())
        network_requests = [_direct_import_network_event_payload(item) for item in events]
        diagnostic = f"network_requests={network_requests}"
        try:
            page_text = self._collect_page_diagnostic_text()
            if page_text:
                diagnostic = f"{diagnostic} | {page_text}"
        except Exception:
            pass
        screenshot = self._save_diagnostic_screenshot("direct-import-network-missing")
        if screenshot:
            diagnostic = f"{diagnostic} | screenshot={screenshot}"
        if not events:
            raise RuntimeError(f"未观察到相关后端上传或解析请求: {diagnostic}")
        raise RuntimeError(f"等待直连导入后端请求完成超时: {diagnostic}")

    def _wait_for_import_results(
        self,
        files: list[str],
        timeout_ms: int = 120000,
        notification_fallback: bool = False,
    ) -> list[dict[str, str]]:
        if notification_fallback:
            notification_results = self._notification_import_results(files)
            if notification_results:
                return notification_results
        page = self._require_page()
        deadline = time.monotonic() + timeout_ms / 1000
        results: list[dict[str, str]] = []
        while time.monotonic() < deadline:
            results = []
            for file in files:
                filename = Path(file).name
                status = self._read_import_file_status(filename, allow_single_result=len(files) == 1)
                if status:
                    item = {"file": filename, "status": status}
                    if status == "failure":
                        message = self._read_import_failure_reason(filename)
                        if not message:
                            diagnostic = self._collect_page_diagnostic_text()
                            screenshot = self._save_diagnostic_screenshot("import-failure-detail-missing")
                            if screenshot:
                                diagnostic = f"{diagnostic} | screenshot={screenshot}"
                            raise RuntimeError(f"未能提取导入失败详情: file={filename}: {diagnostic}")
                        item["message"] = message
                    else:
                        item["message"] = "导入完成"
                    results.append(item)
            if len(results) == len(files):
                return results
            if notification_fallback:
                notification_results = self._notification_import_results(files)
                if notification_results:
                    return notification_results
            page.wait_for_timeout(1000)
        diagnostic = self._collect_page_diagnostic_text()
        screenshot = self._save_diagnostic_screenshot("import-timeout")
        if screenshot:
            diagnostic = f"{diagnostic} | screenshot={screenshot}"
        raise RuntimeError(f"等待导入结果超时: {diagnostic}")

    def _notification_import_results(self, files: list[str]) -> list[dict[str, str]]:
        try:
            notifications = self.collect_notifications(timeout_ms=200)
        except Exception:
            return []
        for item in notifications:
            message = str(item.get("message") or "").strip()
            if not message:
                continue
            status = _notification_import_status(item)
            if not status:
                continue
            return [
                {"file": Path(file).name, "status": status, "message": message}
                for file in files
            ]
        return []

    def _read_import_file_status(self, filename: str, allow_single_result: bool = False) -> str:
        page = self._require_page()
        if allow_single_result:
            if _is_visible_text(page, "导入失败"):
                return "failure"
            if _is_visible_text(page, "导入完成") or _is_visible_text(page, "导入成功"):
                return "success"
            if self._has_visible_import_status_icon("failure"):
                return "failure"
            if self._has_visible_import_status_icon("success"):
                return "success"
        text = self._collect_import_status_text()
        if not text:
            return ""
        index = text.find(filename)
        if index < 0 and _normalize_import_filename(filename) not in _normalize_import_filename(text):
            if allow_single_result and _looks_like_single_import_progress(text):
                return _import_status_from_text(text)
            return ""
        snippet = text if index < 0 else text[index : index + 800]
        return _import_status_from_text(snippet)

    def _read_import_failure_reason(self, filename: str) -> str:
        opened = self._open_import_failure_detail(filename)
        try:
            text = self._wait_for_import_failure_detail_text(timeout_ms=10000 if opened else 2500)
        finally:
            self._close_import_failure_detail_dialog()
        return _extract_import_failure_message(text)

    def _wait_for_import_failure_detail_text(self, timeout_ms: int = 10000) -> str:
        page = self._require_page()
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            text = self._collect_top_dialog_text()
            message = _extract_import_failure_message(text)
            if message:
                return text
            page.wait_for_timeout(300)
        return ""

    def _collect_import_status_text(self) -> str:
        page = self._require_page()
        parts: list[str] = []
        contexts: list[Any] = [page]
        try:
            contexts.extend([frame for frame in page.frames if frame not in contexts])
        except Exception:
            pass
        for context in contexts:
            parts.extend(_collect_context_text_parts(context))
        seen: set[str] = set()
        compact_parts: list[str] = []
        for part in parts:
            text = " ".join(str(part or "").split())
            if text and text not in seen:
                seen.add(text)
                compact_parts.append(text)
        return "\n".join(compact_parts)

    def _open_import_failure_detail(self, filename: str) -> bool:
        page = self._require_page()
        row = page.locator(f'tr:has-text("{filename}"), [class*="item"]:has-text("{filename}")').first
        try:
            row.hover(timeout=3000)
        except Exception:
            pass
        trigger = None
        for selector in build_import_failure_menu_trigger_selectors(filename):
            locator = page.locator(selector)
            try:
                if locator.count() and locator.first.is_visible(timeout=300):
                    locator.first.hover(timeout=2000)
                    page.wait_for_timeout(300)
                    trigger = locator.first
                    if self._click_import_failure_view_if_visible(filename):
                        page.wait_for_timeout(500)
                        return True
                    try:
                        locator.first.click(timeout=2000)
                        page.wait_for_timeout(300)
                    except Exception:
                        pass
                    if self._click_import_failure_view_if_visible(filename):
                        page.wait_for_timeout(500)
                        return True
                    break
            except Exception:
                continue
        if self._open_import_failure_menu_by_position(filename):
            if self._click_import_failure_view_if_visible(filename):
                page.wait_for_timeout(500)
                return True
        if trigger is not None:
            try:
                trigger.hover(timeout=2000)
                page.wait_for_timeout(300)
            except Exception:
                pass
        if self._click_import_failure_view_if_visible(filename):
            page.wait_for_timeout(500)
            return True
        return False

    def _find_import_failure_view_selector(self, filename: str) -> str | None:
        selector = self._find_first_visible_exact_text_selector(build_import_dropdown_item_selectors(), "查看")
        if selector is not None:
            return selector
        quoted = json.dumps(filename, ensure_ascii=False)
        return self._find_first_visible_selector(
            [
                f"text={quoted} >> xpath=.. >> text=\"查看\"",
                '.ant-dropdown:visible text="查看"',
                '.ant-popover:visible text="查看"',
                '.wui-dropdown:visible text="查看"',
                '.wui-popover:visible text="查看"',
                '[class*="dropdown"]:visible text="查看"',
                '[class*="popover"]:visible text="查看"',
            ]
        )

    def _click_import_failure_view_if_visible(self, filename: str) -> bool:
        selector = self._find_import_failure_view_selector(filename)
        if selector is not None:
            self._resolve_visible_locator(selector).click(timeout=3000)
            return True
        page = self._require_page()
        try:
            locator = page.get_by_text("查看", exact=True)
            count = locator.count()
        except Exception:
            return False
        for index in range(count - 1, -1, -1):
            candidate = locator.nth(index)
            try:
                if not candidate.is_visible(timeout=300):
                    continue
                box = candidate.bounding_box(timeout=300)
                if box and (box.get("y", 0) < 70 or box.get("width", 0) > 160 or box.get("height", 0) > 80):
                    continue
                candidate.click(timeout=3000)
                return True
            except Exception:
                continue
        return False

    def _open_import_failure_menu_by_position(self, filename: str) -> bool:
        page = self._require_page()
        y_positions: list[float] = []
        for text in (filename, "导入失败"):
            try:
                locator = page.get_by_text(text, exact=False).last
                if locator.is_visible(timeout=300):
                    box = locator.bounding_box(timeout=300)
                    if box:
                        y_positions.append(box["y"] + box["height"] / 2)
            except Exception:
                continue
        viewport = page.viewport_size or {"width": 1280, "height": 720}
        if not y_positions:
            y_positions = [viewport["height"] / 2 - 90]
        root_box = None
        for selector in build_import_progress_dialog_selectors():
            locator = page.locator(selector).first
            try:
                if locator.is_visible(timeout=300):
                    root_box = locator.bounding_box(timeout=300)
                    if root_box and root_box.get("width", 0) <= 700 and root_box.get("height", 0) <= 600:
                        break
            except Exception:
                continue
        if root_box and (root_box.get("width", 0) > 700 or root_box.get("height", 0) > 600):
            root_box = None
        if root_box:
            x_positions = [root_box["x"] + root_box["width"] - offset for offset in (28, 36, 48)]
            min_y = root_box["y"]
            max_y = root_box["y"] + root_box["height"]
        else:
            x_positions = [viewport["width"] / 2 + offset for offset in (200, 210, 190)]
            min_y = 0
            max_y = viewport["height"]
        adjusted_y_positions: list[float] = []
        for y in y_positions:
            adjusted_y_positions.extend([y, y - 4, y + 4, y - 10, y + 10])
        for y in adjusted_y_positions:
            if y < min_y or y > max_y:
                continue
            for x in x_positions:
                try:
                    page.mouse.move(x, y)
                    page.wait_for_timeout(300)
                    if self._click_import_failure_view_if_visible(filename):
                        return True
                    page.mouse.click(x, y)
                    page.wait_for_timeout(300)
                    if self._click_import_failure_view_if_visible(filename):
                        return True
                    for view_y in (y + 50, y + 56, y + 62):
                        page.mouse.click(x, view_y)
                        page.wait_for_timeout(500)
                        message = _extract_import_failure_message(self._collect_top_dialog_text())
                        if message:
                            return True
                except Exception:
                    continue
        return False

    def _close_import_failure_detail_dialog(self) -> None:
        selector = self._find_first_visible_selector(build_dialog_button_selectors("关闭"))
        if selector:
            self._resolve_visible_locator(selector).click(timeout=3000)
            self._require_page().wait_for_timeout(300)

    def _close_import_progress_dialog(self) -> None:
        self._click_first_visible_if_any(build_import_progress_close_selectors())

    def _has_visible_import_status_icon(self, status: str) -> bool:
        selectors = build_import_status_icon_selectors(status)
        return any(self._collect_visible_selector_matches(selector) for selector in selectors)

    def _download_template_from_dialog(self, template: str | None) -> dict[str, Any]:
        page = self._require_page()
        page.wait_for_timeout(800)
        selector = self._resolve_template_download_selector(template)
        previous_count = len(self.downloaded_files)
        self._click_selector_and_save_download(selector)
        downloaded_files = self.downloaded_files[previous_count:]
        return {"template": template, "downloaded_files": downloaded_files}

    def _resolve_template_download_selector(self, template: str | None) -> str:
        if template:
            selector = self._find_first_visible_selector(build_template_download_link_selectors(template))
            if selector is None:
                diagnostic = self._collect_page_diagnostic_text()
                screenshot = self._save_diagnostic_screenshot("template-download-missing")
                if screenshot:
                    diagnostic = f"{diagnostic} | screenshot={screenshot}"
                raise RuntimeError(f"未找到模版下载链接: {template}: {diagnostic}")
            return selector
        selectors = build_template_download_link_selectors(None)
        for selector in selectors:
            matches = self._collect_visible_selector_matches(selector)
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                raise RuntimeError("模版下载链接匹配不唯一，请在 DSL 中指定 target.template")
        diagnostic = self._collect_page_diagnostic_text()
        screenshot = self._save_diagnostic_screenshot("template-download-missing")
        if screenshot:
            diagnostic = f"{diagnostic} | screenshot={screenshot}"
        raise RuntimeError(f"未找到模版下载链接: {diagnostic}")

    def _close_template_download_dialog(self) -> None:
        selector = self._find_first_visible_selector(build_dialog_button_selectors("取消"))
        if selector:
            self._resolve_visible_locator(selector).click(timeout=3000)
            self._require_page().wait_for_timeout(300)

    def _click_amount_unit_entry(self, action_candidates: list[dict[str, Any]] | None = None) -> None:
        candidates = [item for item in action_candidates or [] if _is_amount_unit_action_candidate(item)]
        for candidate in candidates:
            fieldid = str(candidate.get("fieldid") or "").strip() or None
            aliases = [
                str(candidate.get(key) or "").strip()
                for key in ("label", "title", "key")
                if str(candidate.get(key) or "").strip()
            ]
            try:
                self.click_toolbar_action("设置金额单位", fieldid=fieldid, aliases=aliases)
                return
            except Exception:
                continue
        self.click_toolbar_action("设置金额单位")

    def _resolve_amount_unit_dialog(self):
        page = self._require_page()
        page.wait_for_timeout(300)
        selectors = [*_dialog_root_selectors("设置金额单位"), *_dialog_root_selectors()]
        for selector in selectors:
            for context in self._all_search_contexts():
                locator = context.locator(selector)
                try:
                    count = locator.count()
                except Exception:
                    continue
                for index in range(count - 1, -1, -1):
                    candidate = locator.nth(index)
                    try:
                        if not candidate.is_visible(timeout=300):
                            continue
                        text = " ".join((candidate.inner_text(timeout=500) or "").split())
                        if "设置金额单位" in text or ("元" in text and "万元" in text):
                            return candidate
                    except Exception:
                        continue
        diagnostic = self._collect_page_diagnostic_text()
        screenshot = self._save_diagnostic_screenshot("amount-unit-dialog-missing")
        if screenshot:
            diagnostic = f"{diagnostic} | screenshot={screenshot}"
        raise RuntimeError(f"未找到金额单位弹窗: {diagnostic}")

    def _click_amount_unit_confirm(self, dialog) -> None:
        for label in ("确定", "确认"):
            for selector in (
                f'button:text-is("{label}")',
                f'[role="button"]:text-is("{label}")',
                f'button:has-text("{label}")',
                f'[role="button"]:has-text("{label}")',
            ):
                locator = dialog.locator(selector)
                try:
                    count = locator.count()
                except Exception:
                    continue
                for index in range(count):
                    button = locator.nth(index)
                    try:
                        if button.is_visible(timeout=300):
                            button.click(timeout=3000)
                            self._require_page().wait_for_timeout(300)
                            return
                    except Exception:
                        continue
        diagnostic = self._collect_top_dialog_text() or self._collect_page_diagnostic_text()
        screenshot = self._save_diagnostic_screenshot("amount-unit-confirm-missing")
        if screenshot:
            diagnostic = f"{diagnostic} | screenshot={screenshot}"
        raise RuntimeError(f"未找到金额单位弹窗确认按钮: {diagnostic}")

    def _collect_visible_selector_matches(self, selector: str) -> list[str]:
        matches: list[str] = []
        for context in self._all_search_contexts():
            locator = context.locator(selector)
            try:
                count = locator.count()
            except Exception:
                continue
            for index in range(count):
                candidate = locator.nth(index)
                try:
                    if candidate.is_visible(timeout=300) and self._is_reasonable_action_target(candidate):
                        matches.append(_selector_at_index(selector, index))
                except Exception:
                    continue
        return matches

    def _wait_for_visible_text(self, text: str, timeout_ms: int = 10000) -> None:
        page = self._require_page()
        deadline = time.monotonic() + timeout_ms / 1000
        selector = f"text={json.dumps(text, ensure_ascii=False)}"
        while time.monotonic() < deadline:
            try:
                if page.locator(selector).first.is_visible(timeout=300):
                    return
            except Exception:
                pass
            page.wait_for_timeout(300)

    def _collect_top_dialog_text(self) -> str:
        page = self._require_page()
        for selector in (".ant-modal:visible", ".wui-modal:visible", ".u-modal:visible", '[role="dialog"]:visible'):
            locator = page.locator(selector)
            try:
                count = locator.count()
            except Exception:
                continue
            for index in range(count - 1, -1, -1):
                try:
                    text = locator.nth(index).inner_text(timeout=1000).strip()
                except Exception:
                    continue
                if text:
                    return " ".join(text.split())
        return ""

    def _click_first_visible_if_any(self, selectors: list[str]) -> None:
        selector = self._find_first_visible_selector(selectors)
        if selector:
            self._resolve_visible_locator(selector).click(timeout=3000)
            self._require_page().wait_for_timeout(300)

    def _collect_page_diagnostic_text(self) -> str:
        page = self._require_page()
        snippets: list[str] = []
        dialog_text = self._collect_top_dialog_text()
        if dialog_text:
            snippets.append(dialog_text[:500])
        for selector in (
            ".ant-message-notice",
            ".ant-notification-notice",
            ".u-message-notice",
            ".wui-message-notice",
            ".ant-message",
            ".ant-notification",
            ".u-message",
            ".wui-message",
        ):
            try:
                text = page.locator(selector).first.inner_text(timeout=1000).strip()
            except Exception:
                continue
            if text:
                snippets.append(" ".join(text.split())[:500])
        snippets.extend(self._collect_toolbar_diagnostics("导出"))
        snippets.extend(self._collect_table_selection_diagnostics())
        return " | ".join(snippets[:6]) or "无页面提示"

    def _save_diagnostic_screenshot(self, name: str) -> str:
        if self.observation_session is not None:
            return ""
        page = self._require_page()
        target = _diag_dir() / f"ydf-browser-{name}-{int(time.time())}.png"
        try:
            page.screenshot(path=str(target), full_page=True, timeout=5000)
        except Exception:
            return ""
        self.diagnostic_files.append(str(target))
        return str(target)

    def capture_foreground_summary(self) -> dict[str, Any]:
        frames = []
        for frame in self._require_page().frames:
            try:
                counts = frame.evaluate(
                    """() => {
                        const visible = (node) => {
                          const style = window.getComputedStyle(node);
                          const rect = node.getBoundingClientRect();
                          return style.display !== 'none' && style.visibility !== 'hidden'
                            && rect.width > 0 && rect.height > 0;
                        };
                        const count = (selector) => Array.from(document.querySelectorAll(selector)).filter(visible).length;
                        return {
                          dialogs: count('[role="dialog"]'),
                          modals: count('.ant-modal-wrap, .wui-modal, .u-modal'),
                          drawers: count('.ant-drawer-content-wrapper, .w-drawer, .u-drawer')
                        };
                      }"""
                )
            except Exception:
                continue
            if isinstance(counts, dict) and any(int(value or 0) for value in counts.values()):
                frames.append({"url": redact_url(str(frame.url or "")), **counts})
        return {"visible": bool(frames), "frames": frames}

    def capture_safe_failure_screenshot(self) -> dict[str, Any]:
        if self._ai_failure_screenshot_attempted:
            return {"capture_unavailable_reason": "already_attempted"}
        self._ai_failure_screenshot_attempted = True
        if self.observation_session is None:
            return {"capture_unavailable_reason": "ai_observation_disabled"}
        try:
            masks = self._collect_sensitive_screenshot_masks()
        except Exception as exc:
            return {"capture_unavailable_reason": "redaction_unsupported", "detail": str(exc)}
        target, reference = self.observation_session.failure_artifact_target("failure-screenshot.png")
        try:
            self._require_page().screenshot(
                path=str(target),
                full_page=False,
                mask=masks,
                timeout=5000,
            )
        except Exception as exc:
            target.unlink(missing_ok=True)
            return {"capture_unavailable_reason": "capture_failed", "detail": str(exc)}
        self.observation_session.write(
            "diagnostic_file_created",
            {"kind": "failure_screenshot", "evidence_refs": [reference]},
        )
        return {
            "path": reference,
            "absolute_path": str(target),
            "masked_count": len(masks),
        }

    def _collect_sensitive_screenshot_masks(self) -> list[Any]:
        page = self._require_page()
        frames = list(getattr(page, "frames", []) or [])
        if not frames:
            frames = [page]
        masks: list[Any] = []
        for index, frame in enumerate(frames):
            if index > 0:
                try:
                    if not frame.frame_element().is_visible():
                        continue
                except Exception as exc:
                    raise RuntimeError(f"visible frame mask scan failed: {exc}") from exc
            try:
                controls = frame.locator("input, textarea, [contenteditable='true']")
                count = controls.count()
                for control_index in range(count):
                    control = controls.nth(control_index)
                    if not control.is_visible(timeout=200):
                        continue
                    attributes = {
                        name: str(control.get_attribute(name, timeout=200) or "")
                        for name in ("type", "autocomplete", "name", "id", "fieldid", "data-field")
                    }
                    autocomplete = attributes["autocomplete"].lower()
                    identities = [attributes[name] for name in ("name", "id", "fieldid", "data-field")]
                    if (
                        attributes["type"].lower() == "password"
                        or autocomplete in {"current-password", "new-password"}
                        or any(sensitive_field_rule(identity, auth_context=True) for identity in identities)
                    ):
                        masks.append(control)
            except Exception as exc:
                raise RuntimeError(f"visible frame mask scan failed: {exc}") from exc
        return masks

    def capture_safe_dom_summary(self) -> dict[str, Any]:
        if self._ai_failure_dom_attempted:
            return {"capture_unavailable_reason": "already_attempted"}
        self._ai_failure_dom_attempted = True
        return self._capture_dom_summary("dom-summary.json")

    def capture_step_dom_summary(self, step_index: int) -> dict[str, Any]:
        return self._capture_dom_summary(f"step-{step_index}-{uuid.uuid4().hex}-dom.json")

    def _capture_dom_summary(self, filename: str) -> dict[str, Any]:
        if self.observation_session is None:
            return {"capture_unavailable_reason": "ai_observation_disabled"}
        page = self._require_page()
        frames = list(getattr(page, "frames", []) or [page])
        raw_nodes: list[dict[str, Any]] = []
        unavailable_frames: list[dict[str, str]] = []
        sample_truncated = False
        for frame in frames:
            frame_url = redact_url(str(getattr(frame, "url", "") or ""))
            try:
                nodes = frame.evaluate(_DOM_SEMANTIC_SUMMARY_SCRIPT)
            except Exception as exc:
                unavailable_frames.append({"url": frame_url, "reason": str(exc)})
                continue
            if isinstance(nodes, list) and len(nodes) > 2000:
                sample_truncated = True
            for node in nodes[:2000] if isinstance(nodes, list) else []:
                if isinstance(node, dict):
                    raw_nodes.append({**node, "frame_url": frame_url})
        summary = sanitize_dom_semantic_summary(raw_nodes)
        try:
            candidates = self._popup_reference_module().discover(passive=True)
            if candidates:
                candidates = sanitize_evidence_payload(candidates)
                budget = 256 * 1024 - len(json.dumps(candidates, ensure_ascii=False).encode("utf-8")) - 1024
                summary = sanitize_dom_semantic_summary(raw_nodes, max_bytes=max(1024, budget))
                summary["reference_candidates"] = candidates
        except Exception as exc:
            summary["reference_candidates"] = {"capture_unavailable_reason": "candidate_capture_failed", "error_type": type(exc).__name__}

        summary["truncated"] = summary["truncated"] or sample_truncated
        if unavailable_frames:
            summary["unavailable_frames"] = unavailable_frames
        reference = self.observation_session.write_failure_json(filename, summary)
        self.observation_session.write(
            "diagnostic_file_created",
            {"kind": "dom_summary", "evidence_refs": [reference]},
        )
        return {
            "path": reference,
            "node_count": len(summary["nodes"]),
            "sample_truncated": bool(summary["truncated"]),
        }

    def _save_diagnostic_json(self, name: str, payload: dict[str, Any]) -> str:
        target = _diag_dir() / f"ydf-browser-{name}-{int(time.time())}.json"
        try:
            target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        except Exception:
            return ""
        self.diagnostic_files.append(str(target))
        return str(target)

    def _collect_toolbar_diagnostics(self, action_label: str) -> list[str]:
        page = self._require_page()
        details: list[str] = []
        for selector in build_toolbar_action_selectors(action_label):
            try:
                locator = page.locator(selector)
                count = locator.count()
            except Exception:
                continue
            visible_count = 0
            samples: list[str] = []
            for index in range(min(count, 5)):
                item = locator.nth(index)
                try:
                    if item.is_visible(timeout=200):
                        visible_count += 1
                        samples.append(" ".join((item.inner_text(timeout=300) or "").split())[:80])
                except Exception:
                    continue
            if count:
                details.append(f"导出候选 selector={selector} count={count} visible={visible_count} text={samples}")
        return details[:3]

    def _collect_table_selection_diagnostics(self) -> list[str]:
        page = self._require_page()
        checked = 0
        selected_rows = 0
        try:
            checked = page.locator('tbody tr input[type="checkbox"]:checked').count()
        except Exception:
            pass
        try:
            selected_rows = page.locator(
                'tbody tr[class*="selected"], tbody tr[class*="checked"], tbody tr[aria-selected="true"]'
            ).count()
        except Exception:
            pass
        return [f"表格选择诊断 checked_inputs={checked} selected_rows={selected_rows}"]

    def _reveal_toolbar_overflow(self, target_label: str | None = None) -> None:
        selectors = build_toolbar_more_selectors()
        page = self._require_page()
        touched = False
        for selector in selectors:
            for context in self._all_search_contexts():
                locator = context.locator(selector)
                try:
                    count = locator.count()
                except Exception:
                    continue
                for index in range(count):
                    candidate = locator.nth(index)
                    try:
                        if not candidate.is_visible(timeout=300) or not self._is_reasonable_action_target(candidate):
                            continue
                        candidate.hover(timeout=2000)
                        page.wait_for_timeout(500)
                        touched = True
                        if target_label is None or self._find_first_visible_selector(
                            build_toolbar_action_selectors(target_label),
                            exclude_table_scoped=True,
                        ):
                            return
                        candidate.click(timeout=2000)
                        page.wait_for_timeout(500)
                        if target_label is None or self._find_first_visible_selector(
                            build_toolbar_action_selectors(target_label),
                            exclude_table_scoped=True,
                        ):
                            return
                    except Exception:
                        continue
        if touched:
            return
        raise RuntimeError("未找到工具栏更多按钮")

    def _find_first_visible_selector(
        self,
        selectors: list[str],
        *,
        exclude_table_scoped: bool = False,
    ) -> str | None:
        for selector in selectors:
            for context in self._all_search_contexts():
                locator = context.locator(selector)
                try:
                    count = locator.count()
                except Exception:
                    continue
                for index in range(count):
                    try:
                        candidate = locator.nth(index)
                        if not candidate.is_visible(timeout=300):
                            continue
                        if exclude_table_scoped and self._is_table_scoped_action_target(candidate):
                            continue
                        if self._is_clickable_action_target(candidate):
                            return _selector_at_index(selector, index)
                    except Exception:
                        continue
        return None

    def _find_first_visible_exact_text_selector(
        self,
        selectors: list[str],
        text: str,
        *,
        exclude_table_scoped: bool = False,
    ) -> str | None:
        expected = _normalize_visible_text(text)
        if not expected:
            return None
        for selector in selectors:
            for context in self._all_search_contexts():
                locator = context.locator(selector)
                try:
                    count = locator.count()
                except Exception:
                    continue
                for index in range(count):
                    try:
                        candidate = locator.nth(index)
                        if not candidate.is_visible(timeout=300):
                            continue
                        actual = _normalize_visible_text(candidate.inner_text(timeout=300) or "")
                        if actual != expected:
                            continue
                        if exclude_table_scoped and self._is_table_scoped_action_target(candidate):
                            continue
                        if self._is_clickable_action_target(candidate):
                            return _selector_at_index(selector, index)
                    except Exception:
                        continue
        return None

    def _find_first_visible_row_action_selector(self, selectors: list[str]) -> str | None:
        for selector in selectors:
            for context in self._all_search_contexts():
                locator = context.locator(selector)
                try:
                    count = locator.count()
                except Exception:
                    continue
                for index in range(count):
                    try:
                        candidate = locator.nth(index)
                        if (
                            candidate.is_visible(timeout=300)
                            and self._is_clickable_action_target(candidate)
                            and self._is_table_scoped_action_target(candidate)
                        ):
                            return _selector_at_index(selector, index)
                    except Exception:
                        continue
        return None

    def _find_first_visible_fieldid_action_selector(
        self,
        fieldid: str,
        labels: list[str] | None = None,
        strict_label: bool = False,
        exclude_table_scoped: bool = False,
        allow_blocked: bool = True,
    ) -> str | None:
        expected_labels = {_normalize_visible_text(label) for label in labels or [] if _normalize_visible_text(label)}
        fallback_selector: str | None = None
        blocked_label_selector: str | None = None
        for selector in build_fieldid_action_selectors(fieldid):
            for context in self._all_search_contexts():
                locator = context.locator(selector)
                try:
                    count = locator.count()
                except Exception:
                    continue
                for index in range(count):
                    try:
                        candidate = locator.nth(index)
                        if not candidate.is_visible(timeout=300) or not self._is_reasonable_action_target(candidate):
                            continue
                        if exclude_table_scoped and self._is_table_scoped_action_target(candidate):
                            continue
                        indexed_selector = _selector_at_index(selector, index)
                        if not expected_labels:
                            receives_pointer = self._receives_pointer_events(candidate)
                            if receives_pointer:
                                return indexed_selector
                            if allow_blocked and fallback_selector is None:
                                fallback_selector = indexed_selector
                            continue
                        actual_labels = self._visible_action_text_aliases(candidate)
                        label_matches = bool(expected_labels.intersection(actual_labels))
                        if strict_label and not label_matches:
                            continue
                        receives_pointer = self._receives_pointer_events(candidate)
                        if label_matches:
                            if receives_pointer:
                                return indexed_selector
                            if allow_blocked:
                                blocked_label_selector = indexed_selector
                        elif receives_pointer and fallback_selector is None:
                            fallback_selector = indexed_selector
                    except Exception:
                        continue
        if blocked_label_selector is not None:
            return blocked_label_selector
        if strict_label:
            return None
        return fallback_selector

    def _visible_action_text_aliases(self, locator) -> set[str]:
        values: list[str] = []
        try:
            values.append(locator.inner_text(timeout=300) or "")
        except Exception:
            pass
        for attr in ("title", "aria-label"):
            try:
                values.append(locator.get_attribute(attr, timeout=300) or "")
            except Exception:
                continue
        return {_normalize_visible_text(value) for value in values if _normalize_visible_text(value)}

    def _is_clickable_action_target(self, locator) -> bool:
        return self._is_reasonable_action_target(locator) and self._receives_pointer_events(locator)

    def _is_reasonable_action_target(self, locator) -> bool:
        try:
            box = locator.bounding_box(timeout=300)
        except Exception:
            return True
        if not box:
            return True
        # 宽泛的 :has-text 选择器可能命中整块导航/页面容器；工具栏动作应该是小控件。
        if box.get("y", 0) < 70:
            return False
        return box.get("width", 0) <= 420 and box.get("height", 0) <= 120

    def _receives_pointer_events(self, locator) -> bool:
        clickability = self._inspect_action_clickability(locator)
        if clickability.get("unknown"):
            return True
        return bool(clickability.get("clickable", True))

    def _action_click_position(self, locator) -> dict[str, float] | None:
        clickability = self._inspect_action_clickability(locator)
        return self._click_position_from_clickability(clickability)

    def _inspect_action_clickability(self, locator) -> dict[str, Any]:
        try:
            locator.scroll_into_view_if_needed(timeout=500)
        except Exception:
            pass
        try:
            locator.evaluate(
                """(node) => {
                    try {
                        node.scrollIntoView({block: 'nearest', inline: 'center'});
                    } catch (_error) {
                        try { node.scrollIntoView(); } catch (_ignored) {}
                    }
                }"""
            )
        except Exception:
            pass
        try:
            result = locator.evaluate(
                """(node) => {
                    const rect = node.getBoundingClientRect();
                    if (!rect || rect.width <= 0 || rect.height <= 0) {
                        return {clickable: true, position: null, reason: 'empty-rect'};
                    }
                    const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
                    const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
                    const clamp = (value, min, max) => Math.min(Math.max(value, min), max);
                    const safeX = (value) => clamp(value, 0.5, Math.max(0.5, rect.width - 0.5));
                    const safeY = (value) => clamp(value, 0.5, Math.max(0.5, rect.height - 0.5));
                    const edgeX = Math.max(0.5, Math.min(2, rect.width / 8));
                    const edgeY = Math.max(0.5, Math.min(2, rect.height / 8));
                    const marginX = Math.max(1, Math.min(8, rect.width / 4));
                    const marginY = Math.max(1, Math.min(8, rect.height / 4));
                    const points = [
                        ['center', safeX(rect.width / 2), safeY(rect.height / 2)],
                        ['left-edge', safeX(edgeX), safeY(rect.height / 2)],
                        ['right-edge', safeX(rect.width - edgeX), safeY(rect.height / 2)],
                        ['top-edge', safeX(rect.width / 2), safeY(edgeY)],
                        ['bottom-edge', safeX(rect.width / 2), safeY(rect.height - edgeY)],
                        ['left-middle', safeX(marginX), safeY(rect.height / 2)],
                        ['right-middle', safeX(rect.width - marginX), safeY(rect.height / 2)],
                        ['top-middle', safeX(rect.width / 2), safeY(marginY)],
                        ['bottom-middle', safeX(rect.width / 2), safeY(rect.height - marginY)],
                        ['left-top', safeX(marginX), safeY(marginY)],
                        ['right-top', safeX(rect.width - marginX), safeY(marginY)],
                        ['left-bottom', safeX(marginX), safeY(rect.height - marginY)],
                        ['right-bottom', safeX(rect.width - marginX), safeY(rect.height - marginY)],
                    ];
                    const describe = (element) => {
                        if (!element) return 'no hit';
                        const parts = [String(element.tagName || '').toLowerCase()].filter(Boolean);
                        if (element.id) parts.push(`#${element.id}`);
                        const className = typeof element.className === 'string' ? element.className.trim() : '';
                        if (className) {
                            parts.push(`.${className.split(/\\s+/).slice(0, 4).join('.')}`);
                        }
                        if (element.getAttribute) {
                            const identity = element.getAttribute('fieldid')
                                || element.getAttribute('aria-label')
                                || element.getAttribute('title');
                            if (identity) parts.push(`[${identity}]`);
                        }
                        const text = String(element.innerText || element.textContent || '')
                            .replace(/\\s+/g, ' ')
                            .trim()
                            .slice(0, 80);
                        return `${parts.join('')}${text ? ` text="${text}"` : ''}`;
                    };
                    const blockers = [];
                    for (const [name, relativeX, relativeY] of points) {
                        const x = rect.left + relativeX;
                        const y = rect.top + relativeY;
                        if (x < 0 || y < 0 || x >= viewportWidth || y >= viewportHeight) {
                            blockers.push(`${name}: outside viewport`);
                            continue;
                        }
                        const hit = document.elementFromPoint(x, y);
                        if (hit && (hit === node || node.contains(hit))) {
                            return {
                                clickable: true,
                                position: {x: relativeX, y: relativeY},
                                point: name,
                            };
                        }
                        blockers.push(`${name}: ${describe(hit)}`);
                    }
                    return {
                        clickable: false,
                        blocked: true,
                        diagnostic: blockers.slice(0, 6).join(' | '),
                    };
                }"""
            )
        except Exception:
            return {"clickable": True, "unknown": True}
        if isinstance(result, bool):
            return {"clickable": result, "blocked": not result}
        if isinstance(result, dict):
            if "clickable" not in result:
                result = dict(result)
                result["clickable"] = True
                result["unknown"] = True
            return result
        return {"clickable": True, "unknown": True}

    def _click_position_from_clickability(self, clickability: dict[str, Any]) -> dict[str, float] | None:
        if not clickability.get("clickable"):
            return None
        position = clickability.get("position")
        if not isinstance(position, dict):
            return None
        try:
            x = float(position["x"])
            y = float(position["y"])
        except (KeyError, TypeError, ValueError):
            return None
        return {"x": x, "y": y}

    def _clickability_diagnostic(self, clickability: dict[str, Any]) -> str:
        diagnostic = clickability.get("diagnostic") or clickability.get("reason")
        if diagnostic:
            return str(diagnostic)
        return "无可接收 pointer event 的点击点"

    def _expand_viewport_for_action(self, clickability: dict[str, Any]) -> bool:
        diagnostic = self._clickability_diagnostic(clickability)
        if "outside viewport" not in diagnostic:
            return False
        try:
            page = self._require_page()
            viewport = getattr(page, "viewport_size", None) or dict(GEOMETRY_FALLBACK_VIEWPORT)
            width = int(viewport.get("width") or GEOMETRY_FALLBACK_VIEWPORT["width"])
            height = int(viewport.get("height") or GEOMETRY_FALLBACK_VIEWPORT["height"])
        except Exception:
            return False
        if width >= 1920:
            return False
        new_width = min(1920, max(width + 360, 1600))
        if new_width <= width:
            return False
        try:
            page.set_viewport_size({"width": new_width, "height": height})
            try:
                page.wait_for_timeout(200)
            except Exception:
                pass
            return True
        except Exception:
            return False

    def _is_table_scoped_action_target(self, locator) -> bool:
        try:
            return bool(
                locator.evaluate(
                    """(node) => Boolean(node.closest(
                        'table, .ant-table, .wui-table, .u-table, [role="table"], [role="grid"], [class*="table"]'
                    ))"""
                )
            )
        except Exception:
            return False

    def _build_visible_action_bound_element(
        self,
        action_label: str,
        selector: str,
        reason: str,
        fieldid: str | None = None,
    ) -> BoundElement:
        fieldid = fieldid or _guess_row_action_fieldid(action_label)
        return BoundElement(
            candidate=ElementCandidate(
                key=action_label,
                fieldid=fieldid,
                label=action_label,
                title=action_label,
                region_key=None,
                region_fieldid=None,
                element_type="action",
                component_name="Button",
            ),
            runtime=RuntimeElement(
                fieldid=fieldid or None,
                id=None,
                name=None,
                placeholder=None,
                text=action_label,
                role="button",
                tag_name="button",
                visible=True,
                selector=selector,
            ),
            confidence=1.0,
            reasons=[reason],
        )

    def _build_fieldid_action_bound_element(self, fieldid: str, selector: str) -> BoundElement:
        return BoundElement(
            candidate=ElementCandidate(
                key=fieldid,
                fieldid=fieldid,
                label=fieldid,
                title=fieldid,
                region_key=None,
                region_fieldid=None,
                element_type="action",
                component_name="Button",
            ),
            runtime=RuntimeElement(
                fieldid=fieldid,
                id=None,
                name=None,
                placeholder=None,
                text=fieldid,
                role="button",
                tag_name="button",
                visible=True,
                selector=selector,
            ),
            confidence=1.0,
            reasons=["visible_fieldid_action"],
        )

    def _scan_frame(self, frame, frame_index: int = 0) -> list[dict[str, Any]]:
        items = list(frame.evaluate(_DOM_SCAN_SCRIPT, frame_index))
        for item in items:
            identity_root_index = item.pop("_identity_root_index", None)
            if isinstance(identity_root_index, int) and identity_root_index >= 0:
                item["identity_root"] = f"{frame_index}:{identity_root_index}"
            item["frame_name"] = frame.name or ""
            item["frame_url"] = frame.url
        return items

    def _scan_notifications(self) -> list[dict[str, str]]:
        notifications: list[dict[str, str]] = []
        seen: set[str] = set()
        for frame in self._require_page().frames:
            try:
                items = list(frame.evaluate(_NOTIFICATION_SCAN_SCRIPT))
            except Exception:
                continue
            for item in items:
                message = " ".join(str(item.get("message") or "").split())
                if not message or message in seen:
                    continue
                seen.add(message)
                notifications.append(
                    {
                        "type": str(item.get("type") or "info"),
                        "message": message,
                    }
                )
        return notifications

    def _install_notification_observers(self, *, reset: bool = False, ignore_existing: bool = False) -> None:
        for frame in self._require_page().frames:
            try:
                frame.evaluate(_NOTIFICATION_OBSERVER_INSTALL_SCRIPT, {"reset": reset, "ignoreExisting": ignore_existing})
            except Exception:
                continue

    def _drain_buffered_notifications(self) -> list[dict[str, str]]:
        notifications: list[dict[str, str]] = []
        for frame in self._require_page().frames:
            try:
                items = list(frame.evaluate(_NOTIFICATION_OBSERVER_DRAIN_SCRIPT))
            except Exception:
                continue
            for item in items:
                message = " ".join(str(item.get("message") or "").split())
                if not message:
                    continue
                notifications.append(
                    {
                        "type": str(item.get("type") or "info"),
                        "message": message,
                    }
                )
        return notifications

    def _merge_notifications(self, *groups: list[dict[str, str]]) -> list[dict[str, str]]:
        merged: list[dict[str, str]] = []
        by_message: dict[str, int] = {}
        for group in groups:
            for item in group:
                message = " ".join(str(item.get("message") or "").split())
                if not message:
                    continue
                kind = str(item.get("type") or "info")
                existing_index = by_message.get(message)
                if existing_index is not None:
                    if merged[existing_index]["type"] == "info" and kind != "info":
                        merged[existing_index] = {"type": kind, "message": message}
                    continue
                by_message[message] = len(merged)
                merged.append({"type": kind, "message": message})
        return merged

    def _candidate_selectors(
        self,
        fieldid: str,
        label: str,
        runtime_fieldids: list[str] | None = None,
    ) -> list[str]:
        selectors = []
        for item in [*(runtime_fieldids or []), fieldid]:
            if not item:
                continue
            selectors.extend(
                [
                    f'[fieldid="{item}"]',
                    f'[data-fieldid="{item}"]',
                    f'#{item}',
                ]
            )
        if label:
            selectors.extend([f'text="{label}"', f'button:has-text("{label}")', f'label:has-text("{label}")'])
        return selectors

    def _launch_browser(self):
        launch_errors: list[Exception] = []
        options: dict[str, Any] = {"headless": self.headless}
        if self.window_size is not None:
            width, height = self.window_size
            if not self.headless:
                options["args"] = [f"--window-size={width},{height}"]
        for kwargs in (
            {"channel": "chrome", **options},
            dict(options),
        ):
            try:
                return self._playwright.chromium.launch(**kwargs)
            except Exception as exc:
                launch_errors.append(exc)
        raise RuntimeError(f"浏览器启动失败: {launch_errors[-1]}")

    def _require_page(self):
        if self._page is None:
            raise RuntimeError("浏览器运行时尚未启动")
        return self._page


@dataclass
class FixtureRuntime:
    menu_opening_work_surfaces = False

    runtime_elements: list[dict[str, Any]]
    field_values: dict[str, str] = field(default_factory=dict)
    clicked_targets: list[str] = field(default_factory=list)
    opened_menu: MenuTarget | None = None
    _action_completion_active: bool = field(default=False, init=False, repr=False)
    _action_completion_clicked_count: int = field(default=0, init=False, repr=False)
    _action_completion_clock: float = field(default=0.0, init=False, repr=False)

    def _acquire_action_completion(self) -> None:
        if self._action_completion_active:
            raise RuntimeError("已有动作正在等待完成")
        self._action_completion_active = True

    def _release_action_completion(self) -> None:
        self._action_completion_active = False

    def _prepare_action_completion(self, request: ActionCompletionRequest) -> None:
        self._action_completion_clicked_count = len(self.clicked_targets)

    def _observe_action_completion(
        self,
        request: ActionCompletionRequest,
        stage: str = "",
    ) -> ActionCompletionObservation:
        if stage not in {"", "dom"}:
            return ActionCompletionObservation()
        changed = len(self.clicked_targets) > self._action_completion_clicked_count
        return ActionCompletionObservation(dom_signal="fixture_state" if changed else "")

    def _action_completion_now(self) -> float:
        return self._action_completion_clock

    def _wait_action_completion_poll(self, timeout_ms: int) -> None:
        self._action_completion_clock += timeout_ms / 1000

    def open_menu(self, menu_target: MenuTarget) -> None:
        self.opened_menu = menu_target

    def capture_runtime_elements(self, manifest: PageManifest) -> list[dict[str, Any]]:
        return self.runtime_elements

    def capture_open_menu_work_surfaces(self, manifest: PageManifest) -> list[dict[str, Any]] | None:
        return None

    def wait_for_timeout(self, timeout_ms: int) -> None:
        return

    def is_region_visible(self, fieldid: str) -> bool:
        return any(
            item.get("fieldid") == fieldid and bool(item.get("visible", True))
            for item in self.runtime_elements
            if isinstance(item, dict)
        )

    def capture_page_state(self) -> dict[str, Any]:
        return {
            "url": "fixture://page",
            "title": "Fixture Page",
            "frames": [{"index": 0, "name": "", "url": "fixture://page"}],
            "frame_count": 1,
        }

    def inspect_menu_hosting(self, menu_target: MenuTarget) -> dict[str, str]:
        return {"mode": "unknown", "reason": "fixture runtime 无真实 frame 证据"}

    def ensure_menu_tab(self, menu_target: MenuTarget) -> None:
        if self.opened_menu is None or self.opened_menu.menu_name != menu_target.menu_name:
            raise RuntimeError(f"菜单页签校验失败: {menu_target.menu_name}")

    def prepare_binding(self, manifest: PageManifest) -> None:
        return

    def fill_field(self, bound_element: BoundElement, value: str) -> None:
        self.field_values[bound_element.candidate.fieldid] = str(value)

    def fill_query_field(self, bound_element: BoundElement, value: str) -> None:
        self.fill_field(bound_element, value)

    def fill_grid_row(self, bound_element: BoundElement, row_index: int, values: dict[str, Any]) -> None:
        self.field_values[f"{bound_element.candidate.fieldid}:{row_index}"] = json.dumps(values, ensure_ascii=False)

    def click(self, bound_element: BoundElement) -> None:
        self.clicked_targets.append(bound_element.candidate.label)

    def click_tree_node(self, label: str, tree_fieldid: str | None = None) -> None:
        suffix = f":{tree_fieldid}" if tree_fieldid else ""
        self.clicked_targets.append(f"tree{suffix}:{label}")

    def hover_row_by_text(self, text: str) -> None:
        self.clicked_targets.append(f"hover:{text}")

    def select_tree_context(self, label: str) -> None:
        self.click_tree_node(label)

    def focus_row_by_text(self, text: str) -> None:
        self.hover_row_by_text(text)

    def click_row_action(self, action_label: str) -> None:
        self.clicked_targets.append(action_label)

    def select_tree_node(self, label: str, tree_fieldid: str | None = None) -> None:
        self.click_tree_node(label, tree_fieldid=tree_fieldid)

    def click_toolbar_action(
        self,
        label: str,
        sub_label: str | None = None,
        fieldid: str | None = None,
        aliases: list[str] | None = None,
    ) -> None:
        self.clicked_targets.append(f"{label}>{sub_label}" if sub_label else label)

    def click_tab_action(self, label: str, fieldid: str | None = None) -> None:
        suffix = f":{fieldid}" if fieldid else ""
        self.clicked_targets.append(f"tab{suffix}:{label}")

    def click_query_action(self, label: str = "查询") -> None:
        self.clicked_targets.append(label)

    @table_scoped
    def focus_table_row(self, match: dict[str, Any], *, table_scope: ResolvedTableScope | None = None) -> None:
        self.hover_row_by_text(str(match.get("equals") or ""))

    @table_scoped
    def select_table_row(
        self,
        match: dict[str, Any],
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        table_scope: ResolvedTableScope | None = None,
    ) -> None:
        table, table_fieldid, table_columns = _resolved_table_scope_values(
            table_scope, table, table_fieldid, table_columns
        )
        suffix = f":{table}" if table else ""
        if table_fieldid:
            suffix = f"{suffix}[{table_fieldid}]"
        self.clicked_targets.append(f"select{suffix}:{match.get('equals') or ''}")

    @table_scoped
    def select_table_row_by_index(
        self,
        row_number: int,
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        table_scope: ResolvedTableScope | None = None,
    ) -> None:
        table, table_fieldid, table_columns = _resolved_table_scope_values(
            table_scope, table, table_fieldid, table_columns
        )
        suffix = f":{table}" if table else ""
        if table_fieldid:
            suffix = f"{suffix}[{table_fieldid}]"
        self.clicked_targets.append(f"select-row{suffix}:{row_number}")

    @table_scoped
    def select_table_rows_by_indices(
        self,
        row_numbers: list[int],
        table: str | None = None,
        table_fieldid: str | None = None,
        table_columns: list[str] | None = None,
        table_scope: ResolvedTableScope | None = None,
    ) -> None:
        table, table_fieldid, table_columns = _resolved_table_scope_values(
            table_scope, table, table_fieldid, table_columns
        )
        for row_number in row_numbers:
            if table or table_fieldid:
                self.select_table_row_by_index(
                    row_number,
                    table=table,
                    table_fieldid=table_fieldid,
                    table_columns=table_columns,
                )
            else:
                self.select_table_row_by_index(row_number)

    @table_scoped
    def collect_table_column_values(self, column: str, *, table_scope: ResolvedTableScope | None = None) -> list[str]:
        return []

    def collect_table_debug_text(self) -> str:
        return ""

    def read_field_value(self, bound_element: BoundElement) -> str:
        return self.field_values.get(bound_element.candidate.fieldid, "")

    def read_text(self, bound_element: BoundElement) -> str:
        return self.field_values.get(bound_element.candidate.fieldid, "")

    def collect_notifications(self) -> list[dict[str, str]]:
        return []

    def collect_open_menu_page_errors(self) -> list[dict[str, Any]]:
        return []

    def select_transfer_dialog(
        self,
        *,
        title: str | None = None,
        items: list[dict[str, Any]] | None = None,
        move: str = "to_right",
        confirm: bool = True,
    ) -> dict[str, Any]:
        return {"title": title, "selected": items or [], "move": move, "confirm": confirm}


class FixtureGateway:
    def __init__(self, template_payload: dict, menu_path: str | None = None) -> None:
        self.template_payload = template_payload
        self.menu_target = MenuTarget(
            menu_code="FIXTURE_MENU",
            menu_name=(menu_path.split(">>")[-1] if menu_path else "FixtureMenu"),
            path=[part.strip() for part in (menu_path or "FixtureMenu").split(">>") if part.strip()],
            service_code="fixture_service",
            page_code="fixture_page",
            biz_obj_code=((template_payload.get("data") or {}).get("bizObjCode") or "fixtureBizObj"),
        )

    def resolve_menu(self, menu_path: str) -> MenuTarget:
        self.menu_target.path = [part.strip() for part in menu_path.split(">>") if part.strip()]
        self.menu_target.menu_name = self.menu_target.path[-1]
        return self.menu_target

    def fetch_template(self, menu_target: MenuTarget) -> dict:
        return self.template_payload


def load_json_file(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _editable_table_column_identity_payload(column_candidate: Any | None) -> dict[str, Any]:
    if column_candidate is None:
        return {}
    payload: dict[str, Any] = {
        "columnFieldid": _candidate_text_attr(column_candidate, "fieldid"),
        "columnKey": _candidate_text_attr(column_candidate, "key"),
        "dataField": _candidate_text_attr(column_candidate, "data_field"),
        "tableFieldid": _candidate_text_attr(column_candidate, "region_fieldid"),
        "elementType": _candidate_text_attr(column_candidate, "element_type"),
        "componentName": _candidate_text_attr(column_candidate, "component_name"),
    }
    display_fields = _candidate_display_fields(column_candidate)
    if display_fields:
        payload["displayFields"] = display_fields
    column_groups = [str(item).strip() for item in getattr(column_candidate, "column_groups", []) or [] if str(item).strip()]
    if column_groups:
        payload["columnGroups"] = column_groups
    return {key: value for key, value in payload.items() if value}


def _bound_element_has_verified_form_identity(bound_element: Any) -> bool:
    path = getattr(bound_element, "contract_path", None)
    return bool(
        isinstance(path, dict)
        and path.get("applicability") == "verified"
        and "PRS-FORM-001" in (path.get("rule_ids") or [])
    )


def _iter_editable_table_values(values: Any):
    if isinstance(values, dict):
        for column, value in values.items():
            column_label = str(column)
            yield column_label, column_label, value
        return
    if isinstance(values, list):
        for item in values:
            if not isinstance(item, dict):
                raise ValueError(f"可编辑表格字段列表项必须是对象: {item!r}")
            column = str(item.get("column") or item.get("field") or "").strip()
            if not column:
                raise ValueError(f"可编辑表格字段列表项缺少 column: {item!r}")
            key = str(item.get("key") or column).strip() or column
            value = item.get("value", item.get("equals"))
            yield key, column, value
        return
    raise ValueError(f"可编辑表格字段必须是对象或列表: {values!r}")


def _candidate_display_fields(candidate: Any) -> list[str]:
    raw = getattr(candidate, "raw", None)
    props = raw.get("props") if isinstance(raw, dict) and isinstance(raw.get("props"), dict) else {}
    display_value = ""
    if isinstance(raw, dict):
        display_value = str(raw.get("displayvalue") or raw.get("displayValue") or "")
    if not display_value and isinstance(props, dict):
        display_value = str(props.get("displayvalue") or props.get("displayValue") or "")
    if not display_value:
        return []
    fields = [part for part in re.split(r"[^A-Za-z0-9_]+", display_value) if part]
    return list(dict.fromkeys(fields))


def _editable_table_column_candidate_diagnostics(column_candidate: Any | None) -> dict[str, Any]:
    if column_candidate is None:
        return {}
    diagnostics = {
        "fieldid": _candidate_text_attr(column_candidate, "fieldid"),
        "data_field": _candidate_text_attr(column_candidate, "data_field"),
        "table_fieldid": _candidate_text_attr(column_candidate, "region_fieldid"),
    }
    cleaned: dict[str, Any] = {key: value for key, value in diagnostics.items() if value}
    column_groups = [str(item).strip() for item in getattr(column_candidate, "column_groups", []) or [] if str(item).strip()]
    if column_groups:
        cleaned["column_groups"] = column_groups
    return cleaned


def _editable_table_cell_resolution_diagnostics(resolution: dict[str, Any]) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {}
    locator_source = resolution.get("locator_source") or resolution.get("source")
    if locator_source:
        diagnostics["locator_source"] = str(locator_source)
    actual_identity = resolution.get("actualIdentity")
    if isinstance(actual_identity, dict):
        actual_fieldid = actual_identity.get("fieldid") or actual_identity.get("columnFieldid")
        actual_data_field = actual_identity.get("data_field") or actual_identity.get("dataField")
        if actual_fieldid:
            diagnostics["actual_fieldid"] = str(actual_fieldid)
        if actual_data_field:
            diagnostics["actual_data_field"] = str(actual_data_field)
    for source_key, target_key in (
        ("actual_fieldid", "actual_fieldid"),
        ("actualFieldid", "actual_fieldid"),
        ("actual_data_field", "actual_data_field"),
        ("actualDataField", "actual_data_field"),
        ("context", "locator_context"),
    ):
        value = resolution.get(source_key)
        if value and target_key not in diagnostics:
            diagnostics[target_key] = str(value)
    column_groups = resolution.get("columnGroups") or resolution.get("column_groups")
    if isinstance(column_groups, list) and column_groups:
        diagnostics["column_groups"] = [str(item) for item in column_groups if str(item)]
    scope = _editable_table_scope_from_resolution(resolution)
    if scope:
        diagnostics["table_scope"] = scope
    return diagnostics


def _editable_table_scope_from_resolution(resolution: Any) -> dict[str, Any]:
    if not isinstance(resolution, dict):
        return {}
    raw_scope = resolution.get("tableScope") or resolution.get("table_scope")
    if not isinstance(raw_scope, dict):
        return {}

    def _scope_value(*keys: str) -> str:
        for key in keys:
            value = raw_scope.get(key)
            if value is not None and value != "":
                return str(value)
        return ""

    scope: dict[str, Any] = {}
    for source_keys, target_key in (
        (("table",), "table"),
        (("tableFieldid", "table_fieldid"), "table_fieldid"),
        (("rootSource", "root_source", "source"), "root_source"),
        (("rootClassName", "root_class_name"), "root_class_name"),
        (("rootText", "root_text"), "root_text"),
        (("rowText", "row_text"), "row_text"),
    ):
        value = _scope_value(*source_keys)
        if value:
            scope[target_key] = value[:800] if target_key in {"root_text", "row_text"} else value
    row_index = raw_scope.get("rowIndex", raw_scope.get("row_index"))
    if row_index is not None and row_index != "":
        try:
            scope["row_index"] = int(row_index)
        except (TypeError, ValueError):
            scope["row_index"] = str(row_index)
    root_score = raw_scope.get("rootScore", raw_scope.get("root_score"))
    if root_score is not None and root_score != "":
        try:
            scope["root_score"] = int(root_score)
        except (TypeError, ValueError):
            scope["root_score"] = str(root_score)
    return scope


def _editable_table_cell_identity_conflict_message(payload: dict[str, Any], result: dict[str, Any]) -> str:
    target_identity = result.get("targetIdentity") or {
        "columnFieldid": payload.get("columnFieldid"),
        "dataField": payload.get("dataField"),
        "tableFieldid": payload.get("tableFieldid"),
    }
    conflict = result.get("identityConflict")
    actual_identity = result.get("actualIdentity")
    if isinstance(conflict, dict):
        actual_identity = actual_identity or conflict.get("actualIdentity")
    return (
        "可编辑表格列身份冲突: "
        f"column={payload.get('column', '')}; "
        f"target={json.dumps(target_identity, ensure_ascii=False)}; "
        f"actual={json.dumps(actual_identity or {}, ensure_ascii=False)}; "
        f"locator_source={result.get('locator_source') or result.get('source') or ''}"
    )


def _candidate_text_attr(candidate: Any, name: str) -> str:
    value = getattr(candidate, name, "")
    if value is None:
        return ""
    return str(value).strip()


def _search_context_label(context) -> dict[str, str]:
    raw_name = getattr(context, "name", "")
    try:
        name = raw_name() if callable(raw_name) else raw_name
    except Exception:
        name = ""
    try:
        url = getattr(context, "url", "")
    except Exception:
        url = ""
    return {
        "type": context.__class__.__name__,
        "name": str(name or ""),
        "url": str(url or ""),
    }


def _editable_table_add_row_name_mismatch_message(
    label: str,
    table: str | None,
    debug_items: list[dict[str, Any]],
) -> str | None:
    table_name = str(table or "").strip()
    if not table_name or not debug_items:
        return None
    nearby_labels: list[str] = []
    mismatch_candidates = 0
    for item in debug_items:
        debug = item.get("debug") if isinstance(item, dict) else None
        if not isinstance(debug, dict):
            continue
        candidates = debug.get("candidates")
        if not isinstance(candidates, list):
            continue
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            if candidate.get("skipped") != "table-label-mismatch":
                continue
            mismatch_candidates += 1
            raw_labels = candidate.get("nearbyLabels")
            if isinstance(raw_labels, list):
                for raw_label in raw_labels:
                    text = str(raw_label or "").strip()
                    if text and text not in nearby_labels:
                        nearby_labels.append(text)
    if not mismatch_candidates:
        return None
    label_hint = "、".join(nearby_labels[:8]) if nearby_labels else "未采集到可见表格标题"
    return (
        f"可编辑表格名称未匹配: target.table={table_name}; "
        f"页面可见表格标题包括: {label_hint}; "
        f"未点击 {label}。请将 DSL target.table 改为页面实际标题。"
    )


def _editable_table_add_row_empty_message(
    label: str,
    table: str | None,
    debug_items: list[dict[str, Any]],
) -> str | None:
    for item in debug_items:
        debug = item.get("debug") if isinstance(item, dict) else None
        if not isinstance(debug, dict) or debug.get("failure") != "add-row-no-data-row":
            continue
        state = debug.get("rowState") if isinstance(debug.get("rowState"), dict) else {}
        row_texts = state.get("rowTexts") if isinstance(state, dict) else None
        row_hint = "、".join(str(text) for text in row_texts[:5]) if isinstance(row_texts, list) else ""
        fieldid = str(debug.get("tableFieldid") or "").strip()
        fieldid_part = f"table_fieldid={fieldid}; " if fieldid else ""
        validation = debug.get("validationRoot") if isinstance(debug.get("validationRoot"), dict) else {}
        root_text = str(validation.get("text") or "").strip() if isinstance(validation, dict) else ""
        root_part = f"validation_root={root_text[:160]}; " if root_text else ""
        table_part = f"table={table or ''}; " if table else ""
        return (
            "可编辑表格新增行未生效: "
            f"{table_part}{fieldid_part}{root_part}label={label}; rows={row_hint or '无可编辑数据行'}"
        )
    return None


def _editable_table_add_row_scope_message(
    label: str,
    table: str | None,
    debug_items: list[dict[str, Any]],
) -> str | None:
    for item in debug_items:
        debug = item.get("debug") if isinstance(item, dict) else None
        if not isinstance(debug, dict) or debug.get("failure") != "add-row-scope-stale":
            continue
        return (
            "可编辑表格作用域令牌失效: "
            f"table={table or ''}; table_fieldid={debug.get('tableFieldid') or ''}; "
            f"label={label}; 未点击新增。"
        )
    return None


def _editable_table_add_row_debug_clicked_candidate(debug_items: list[dict[str, Any]]) -> bool:
    for item in debug_items:
        debug = item.get("debug") if isinstance(item, dict) else None
        if isinstance(debug, dict) and debug.get("failure") == "add-row-no-data-row":
            return True
    return False


def _editable_table_add_row_should_retry(result: Any) -> bool:
    if not isinstance(result, dict) or result.get("row_state_changed") is not False:
        return False
    if result.get("row_state_reliable") is not True or result.get("foreground_opened"):
        return False
    before = result.get("row_state_before")
    if not isinstance(before, dict):
        return False
    try:
        return int(before.get("dataRowCount") or 0) > 0
    except (TypeError, ValueError):
        return False


def _editable_table_editor_selectors() -> list[str]:
    return [
        "input:not([type='hidden'])",
        "textarea",
        "[contenteditable='true']",
        '[role="textbox"]',
        '[role="combobox"]',
    ]


def _candidate_component_claims_modal_reference(candidate: Any | None) -> bool:
    component_name = str(getattr(candidate, "component_name", "") or "").lower().replace("-", "").replace("_", "")
    if bool(component_name) and any(
        token in component_name
        for token in (
            "modalselect",
            "refer",
            "reference",
            "ref",
        )
    ):
        return True
    return _candidate_raw_claims_reference(getattr(candidate, "raw", None))


def _candidate_raw_claims_reference(raw: Any) -> bool:
    if not isinstance(raw, dict):
        return False
    return bool(str(raw.get("refuri") or raw.get("refUri") or raw.get("refURI") or "").strip())


def _candidate_component_claims_table_reference(candidate: Any | None) -> bool:
    component_name = str(getattr(candidate, "component_name", "") or "").lower().replace("-", "").replace("_", "")
    return bool(component_name) and "tablemodalselect" in component_name


def _candidate_has_enum_type(raw: Any) -> bool:
    if not isinstance(raw, dict):
        return False
    for key in ("enumType", "enum_type", "enumtype"):
        value = raw.get(key)
        if value is not None and str(value).strip():
            return True
    props = raw.get("props")
    if isinstance(props, dict):
        for key in ("enumType", "enum_type", "enumtype"):
            value = props.get(key)
            if value is not None and str(value).strip():
                return True
    return False


def _candidate_claims_multi_select(candidate: Any | None) -> bool:
    raw = getattr(candidate, "raw", None)
    if not isinstance(raw, dict):
        return False
    props = raw.get("props") if isinstance(raw.get("props"), dict) else {}
    for source in (raw, props):
        for key in ("checkable", "multiple", "multiSelect", "multiselect"):
            value = source.get(key)
            if value is True or str(value or "").strip().lower() in {"1", "true", "yes", "multiple"}:
                return True
        if str(source.get("mode") or "").strip().lower() in {"multiple", "tags"}:
            return True
    return False


def _ensure_table_reference_target_uses_match(
    candidate: Any | None,
    value: Any,
    *,
    target_has_selection: bool,
) -> None:
    if not _candidate_component_claims_table_reference(candidate):
        return
    if target_has_selection:
        return
    label = str(getattr(candidate, "label", "") or getattr(candidate, "title", "") or "").strip()
    field = f"[{label}]" if label else ""
    example_field = label or "字段名"
    raise RuntimeError(
        f"表格参照字段{field}必须使用 match、row_number 或 first_available，不能使用标量值。"
        f"示例: {example_field}: {{filter: {{conditions: [{{field: 项目代码, equals: 目标代码}}]}}, "
        "match: {column: 项目代码, equals: 目标代码}}"
    )




def _display_step_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    return str(value)




























_EDITABLE_TABLE_NUMBER_PATTERN = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)")


def _editable_table_numeric_values_match(actual_value: str, expected_value: str) -> bool:
    actual_with_hint = _editable_table_decimal_value(actual_value, require_format_hint=True)
    expected_with_hint = _editable_table_decimal_value(expected_value, require_format_hint=True)
    if actual_with_hint is None and expected_with_hint is None:
        return False
    actual = _editable_table_decimal_value(actual_value)
    expected = _editable_table_decimal_value(expected_value)
    return actual is not None and expected is not None and actual == expected


def _plain_field_value_matches(actual_value: str, expected_value: str) -> bool:
    actual = _normalize_plain_field_value(actual_value)
    expected = _normalize_plain_field_value(expected_value)
    if actual == expected:
        return True
    return _editable_table_numeric_values_match(actual, expected)


def _parse_date_range_value(value: Any) -> tuple[str, str, str]:
    text = _normalize_plain_field_value(value)
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})", text)
    if not match:
        raise ValueError(f"日期范围格式应为 YYYY-MM-DD~YYYY-MM-DD: {value!r}")
    start, end = match.groups()
    for item in (start, end):
        try:
            date.fromisoformat(item)
        except ValueError as exc:
            raise ValueError(f"日期范围包含非法日期: {value!r}") from exc
    return start, end, f"{start}~{end}"


def _date_range_values_match(actual_value: str, expected_value: str) -> bool:
    try:
        actual = _parse_date_range_value(actual_value)[2]
        expected = _parse_date_range_value(expected_value)[2]
    except ValueError:
        return False
    return actual == expected


def _normalize_plain_field_value(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _editable_table_decimal_value(value: Any, require_format_hint: bool = False) -> Decimal | None:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return None
    has_format_hint = any(marker in text for marker in (",", "，", "."))
    if require_format_hint and not has_format_hint:
        return None
    normalized = text.replace(" ", "").replace(",", "").replace("，", "")
    if not _EDITABLE_TABLE_NUMBER_PATTERN.fullmatch(normalized):
        return None
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def _normalize_table_header_key(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return re.sub(r"^[\s*＊✱✳※]+", "", text).strip()


def _table_header_records(item: dict[str, Any]) -> list[tuple[str, str]]:
    records = [
        (str(header.get("text") or "").strip(), str(header.get("identity") or "").strip())
        for header in item.get("columnHeaders", [])
        if isinstance(header, dict)
        and str(header.get("text") or "").strip()
        and str(header.get("identity") or "").strip()
    ]
    if records:
        return records
    occurrences: dict[str, int] = {}
    result: list[tuple[str, str]] = []
    for value in item.get("columns", []):
        text = str(value).strip()
        key = _normalize_table_header_key(text)
        if not text or not key:
            continue
        occurrences[key] = occurrences.get(key, 0) + 1
        result.append((text, f"text:{key}:{occurrences[key]}"))
    return result


def _merge_header_records(groups: list[list[tuple[str, str]]]) -> list[tuple[str, str]]:
    merged: list[tuple[str, str]] = []
    seen: set[str] = set()
    for group in groups:
        for record in group:
            if record[1] in seen:
                continue
            seen.add(record[1])
            merged.append(record)
    return merged


def _merge_collected_header_records(
    observed: list[tuple[str, str]],
    collected: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    collected_keys = {_normalize_table_header_key(text) for text, _identity in collected}
    result = _merge_header_records(
        [[record for record in observed if _normalize_table_header_key(record[0]) in collected_keys]]
    )
    observed_keys = {_normalize_table_header_key(text) for text, _identity in result}
    collected = [
        record
        for record in collected
        if not (record[1].startswith("text:") and _normalize_table_header_key(record[0]) in observed_keys)
    ]
    return _merge_header_records([result, collected])


def _leading_code(value: str) -> str:
    text = str(value or "").strip()
    match = re.match(r"\d+", text)
    return match.group(0) if match else ""


def _normalize_multi_select_target_values(value: Any) -> list[str]:
    raw_values = value if isinstance(value, list) else [value]
    normalized = [" ".join(str(item or "").split()).strip() for item in raw_values]
    duplicates = sorted({item for item in normalized if normalized.count(item) > 1})
    if duplicates:
        raise ValueError(f"多选目标列表包含重复值: {', '.join(duplicates)}")
    return normalized


def _unique_normalized_values(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = " ".join(str(value or "").split()).strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _multi_select_identity_parts(value: Any) -> tuple[str, str]:
    normalized = " ".join(str(value or "").split()).strip()
    name = re.sub(r"^\d+(?:[\s_-]+|$)", "", normalized).strip()
    return normalized, name


def _multi_select_values_equivalent(left: Any, right: Any) -> bool:
    left_full, left_name = _multi_select_identity_parts(left)
    right_full, right_name = _multi_select_identity_parts(right)
    if not left_full or not right_full:
        return left_full == right_full
    if left_full == right_full:
        return True
    left_code = _leading_code(left_full)
    right_code = _leading_code(right_full)
    if left_code and right_code:
        return left_code == right_code
    return bool(left_code or right_code) and left_name == right_name and bool(left_name)


def _multi_select_value_diagnostics(expected: list[Any], actual: list[Any]) -> dict[str, list[str]]:
    expected_values = _unique_normalized_values(expected)
    actual_values = _unique_normalized_values(actual)
    unmatched_actual = list(actual_values)
    missing: list[str] = []
    for expected_value in expected_values:
        matches = [index for index, actual_value in enumerate(unmatched_actual) if _multi_select_values_equivalent(expected_value, actual_value)]
        if len(matches) == 1:
            unmatched_actual.pop(matches[0])
        else:
            missing.append(expected_value)
    return {
        "expected_values": expected_values,
        "actual_values": actual_values,
        "missing_values": missing,
        "unexpected_values": unmatched_actual,
    }


def _ambiguous_multi_select_candidate_values(value: Any, candidates: list[Any]) -> list[str]:
    matches = _unique_normalized_values(
        [candidate for candidate in candidates if _multi_select_values_equivalent(value, candidate)]
    )
    return matches if len(matches) > 1 else []


def _compact_attachment_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip().lower()


def _attachment_view_label(value: str) -> str:
    return {"card": "卡片视图", "table": "表格视图"}.get(value, value)


def _normalize_extension_list(raw: Any) -> set[str]:
    if raw is None:
        return set()
    if isinstance(raw, str):
        items = re.split(r"[,;，；\s]+", raw)
    elif isinstance(raw, (list, tuple, set)):
        items = [str(item) for item in raw]
    else:
        return set()
    extensions: set[str] = set()
    for item in items:
        value = str(item or "").strip().lower()
        if not value:
            continue
        if value == "*":
            extensions.add("*")
            continue
        if "/" in value:
            continue
        extensions.add(value.lstrip("."))
    return extensions


def _allowed_attachment_extensions(candidate: dict[str, Any]) -> set[str]:
    raw = candidate.get("raw") if isinstance(candidate, dict) else {}
    props = raw.get("props") if isinstance(raw, dict) else {}
    for source in (
        props.get("enableFileType") if isinstance(props, dict) else None,
        props.get("accept") if isinstance(props, dict) else None,
        raw.get("enableFileType") if isinstance(raw, dict) else None,
        raw.get("accept") if isinstance(raw, dict) else None,
        candidate.get("allowed_extensions") if isinstance(candidate, dict) else None,
    ):
        extensions = _normalize_extension_list(source)
        if extensions:
            return extensions
    return set()


def _normalize_attachment_candidates(
    candidates: list[dict[str, Any]],
    attachment_type: str,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        raw = candidate.get("raw") if isinstance(candidate.get("raw"), dict) else {}
        normalized.append(
            {
                "key": str(candidate.get("key") or ""),
                "fieldid": str(candidate.get("fieldid") or raw.get("divCode") or raw.get("key") or ""),
                "label": str(candidate.get("label") or raw.get("label") or raw.get("title") or attachment_type),
                "node_type": str(candidate.get("node_type") or raw.get("nodeType") or ""),
                "component_name": str(candidate.get("component_name") or raw.get("name") or ""),
                "allowed_extensions": sorted(_allowed_attachment_extensions(candidate)),
                "raw": raw,
            }
        )
    return normalized


def _first_matching_attachment_candidate(
    candidates: list[dict[str, Any]],
    attachment_type: str,
) -> dict[str, Any] | None:
    wanted = _compact_attachment_text(attachment_type)
    for candidate in candidates:
        aliases = {
            candidate.get("label"),
            candidate.get("fieldid"),
            candidate.get("key"),
        }
        if wanted in {_compact_attachment_text(item) for item in aliases if item}:
            return candidate
    return candidates[0] if len(candidates) == 1 else None


def build_service_url(base_url: str, service_code: str) -> str:
    return f"{base_url.rstrip('/')}/#/service/{service_code}"


def build_accessibility_selector(role: str, name: str) -> str:
    return f"axrole={role}::{name}"


def _fieldid_selector(fieldid: str) -> str:
    value = str(fieldid).replace("\\", "\\\\").replace('"', '\\"')
    return f'[fieldid="{value}"], [data-fieldid="{value}"], [data-field-id="{value}"]'


def build_tree_node_selectors(label: str) -> list[str]:
    return RENDER_ADAPTERS.selectors("tree.node", label)


def build_tree_closed_switcher_selectors() -> list[str]:
    return RENDER_ADAPTERS.selectors("tree.closed_switcher")


def build_row_hover_selectors(text: str) -> list[str]:
    return [
        f'tr:has-text("{text}")',
        f'[role="row"]:has-text("{text}")',
        f'.ant-table-row:has-text("{text}")',
        f'tbody tr:has-text("{text}")',
        f'div[role="row"]:has-text("{text}")',
    ]


def build_table_data_row_selectors() -> list[str]:
    return RENDER_ADAPTERS.selectors("table.data_row")


def _table_data_row_selectors(*, scoped: bool = False) -> list[str]:
    selectors = build_table_data_row_selectors()
    if not scoped:
        return selectors
    return [":scope > tr", *selectors, "tr"]


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def build_table_tree_expand_selectors() -> list[str]:
    return RENDER_ADAPTERS.selectors("table.tree_expand")


def build_row_selection_checkbox_selectors() -> list[str]:
    return RENDER_ADAPTERS.selectors("row.selection_checkbox")


def build_table_header_selection_checkbox_selectors() -> list[str]:
    return [
        'thead input[type="checkbox"]',
        'thead [role="checkbox"]',
        'thead label[class*="checkbox"]',
        'thead span[class*="checkbox"]',
        '[role="columnheader"] input[type="checkbox"]',
        '[role="columnheader"] [role="checkbox"]',
        '[role="columnheader"] label[class*="checkbox"]',
        '[role="columnheader"] span[class*="checkbox"]',
        '[class*="table-header"] input[type="checkbox"]',
        '[class*="table-header"] [role="checkbox"]',
        '[class*="table-header"] label[class*="checkbox"]',
        '[class*="table-header"] span[class*="checkbox"]',
        '[class*="TableHeader"] input[type="checkbox"]',
        '[class*="TableHeader"] [role="checkbox"]',
        '[class*="TableHeader"] label[class*="checkbox"]',
        '[class*="TableHeader"] span[class*="checkbox"]',
        'th input[type="checkbox"]',
        'th [role="checkbox"]',
        'th label[class*="checkbox"]',
        'th span[class*="checkbox"]',
    ]


def build_login_probe_selectors() -> dict[str, list[str]]:
    return {
        "username": [
            'input[placeholder="邮箱/账号/用户手机号"]',
            'input[placeholder*="账号"]',
        ],
        "password": [
            'input[placeholder="密码"]',
            'input[type="password"]',
        ],
        "submit": [
            'button:has-text("登录")',
            'text="登录"',
        ],
    }


def build_row_action_selectors(action_label: str) -> list[str]:
    return RENDER_ADAPTERS.selectors("row.action", action_label)


def build_toolbar_action_selectors(action_label: str) -> list[str]:
    return RENDER_ADAPTERS.selectors("toolbar.action", action_label)


def build_toolbar_exact_text_selectors() -> list[str]:
    return RENDER_ADAPTERS.selectors("toolbar.exact_text")


def build_toolbar_dropdown_item_selectors() -> list[str]:
    return RENDER_ADAPTERS.selectors("toolbar.dropdown_item")


def build_tab_action_selectors(action_label: str, fieldid: str | None = None) -> list[str]:
    return RENDER_ADAPTERS.selectors("tab.action", action_label, fieldid=fieldid)


def build_tab_exact_text_selectors() -> list[str]:
    return RENDER_ADAPTERS.selectors("tab.exact_text")


def build_editable_table_add_row_selectors(label: str = "新增") -> list[str]:
    return RENDER_ADAPTERS.selectors("editable_table.add_row", label)


def build_fieldid_action_selectors(fieldid: str) -> list[str]:
    return RENDER_ADAPTERS.selectors("fieldid.action", fieldid)











def build_transfer_dialog_dialog_selectors() -> list[str]:
    return RENDER_ADAPTERS.selectors("transfer_dialog.dialog")


def build_transfer_dialog_move_to_target_selectors() -> list[str]:
    return RENDER_ADAPTERS.selectors("transfer_dialog.move_to_target")


def build_transfer_dialog_confirm_selectors(label: str = "确定") -> list[str]:
    return RENDER_ADAPTERS.selectors("transfer_dialog.confirm", label)


def build_toolbar_more_selectors() -> list[str]:
    return RENDER_ADAPTERS.selectors("toolbar.more")


def build_dialog_button_selectors(label: str) -> list[str]:
    dialog_roots = [
        ".ant-modal:visible",
        ".ant-modal-confirm:visible",
        ".wui-modal:visible",
        ".wui-modal-confirm:visible",
        ".u-modal:visible",
        ".u-modal-confirm:visible",
        '[role="dialog"]:visible',
        '[class*="modal"]:visible',
    ]
    button_selectors = [
        f'button:text-is("{label}")',
        f'[role="button"]:text-is("{label}")',
        f'button:has-text("{label}")',
        f'[role="button"]:has-text("{label}")',
        f'text="{label}"',
    ]
    return [f"{root} {button}" for root in dialog_roots for button in button_selectors]


def build_import_dropdown_item_selectors() -> list[str]:
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


def build_import_file_button_selectors() -> list[str]:
    dialog_roots = _dialog_root_selectors()
    buttons = [
        'button:text-is("选择文件")',
        '[role="button"]:text-is("选择文件")',
        'button:has-text("选择文件")',
        '[role="button"]:has-text("选择文件")',
        'button:has-text("点击上传")',
        '[role="button"]:has-text("点击上传")',
        ".ant-upload button",
        ".wui-upload button",
        ".u-upload button",
    ]
    return [f"{root} {button}" for root in dialog_roots for button in buttons]


def build_import_workbench_submit_selectors() -> list[str]:
    dialog_roots = _dialog_root_selectors("导入工作台")
    buttons = [
        'button:text-is("导入")',
        '[role="button"]:text-is("导入")',
        'button:has-text("导入")',
        '[role="button"]:has-text("导入")',
        '.ant-modal-footer button:text-is("导入")',
        '.wui-modal-footer button:text-is("导入")',
        '.u-modal-footer button:text-is("导入")',
        '.ant-modal-footer button:has-text("导入")',
        '.wui-modal-footer button:has-text("导入")',
        '.u-modal-footer button:has-text("导入")',
    ]
    return [f"{root} {button}" for root in dialog_roots for button in buttons]


def build_import_failure_menu_trigger_selectors(filename: str) -> list[str]:
    quoted = json.dumps(filename, ensure_ascii=False)
    trigger_fragments = [
        '[class*="setting"]',
        '[class*="gear"]',
        '[class*="shezhi"]',
        '[class*="more"]',
        '[class*="ellipsis"]',
        '[class*="caozuo"]',
    ]
    row_roots = [
        f"tr:has-text({quoted})",
        f'[role="row"]:has-text({quoted})',
        f'[class*="item"]:has-text({quoted})',
        f'[class*="row"]:has-text({quoted})',
    ]
    selectors: list[str] = []
    for row in row_roots:
        for fragment in trigger_fragments:
            selectors.append(f"{row} button:has({fragment})")
            selectors.append(f"{row} {fragment}")
    for fragment in trigger_fragments:
        selectors.append(f"button:has({fragment})")
        selectors.append(fragment)
    return [
        *selectors,
    ]


def build_import_progress_close_selectors() -> list[str]:
    return [
        '.ant-modal:has-text("导入进度") .ant-modal-close',
        '.wui-modal:has-text("导入进度") .wui-modal-close',
        '.u-modal:has-text("导入进度") .u-modal-close',
        '[role="dialog"]:has-text("导入进度") [aria-label="Close"]',
        '[role="dialog"]:has-text("导入进度") button:has-text("×")',
        '.ant-modal:visible .ant-modal-close',
        '.wui-modal:visible .wui-modal-close',
        '.u-modal:visible .u-modal-close',
    ]


def build_import_progress_dialog_selectors() -> list[str]:
    return [
        '.ant-modal:has-text("正在操作")',
        '.wui-modal:has-text("正在操作")',
        '.u-modal:has-text("正在操作")',
        '[role="dialog"]:has-text("正在操作")',
        '[class*="modal"]:has-text("正在操作")',
        '.ant-modal:has-text("导入失败")',
        '.wui-modal:has-text("导入失败")',
        '.u-modal:has-text("导入失败")',
        '[role="dialog"]:has-text("导入失败")',
        '[class*="modal"]:has-text("导入失败")',
    ]


def build_import_status_icon_selectors(status: str) -> list[str]:
    if status == "failure":
        icon_fragments = ["exclamation", "error", "fail", "close-circle"]
    else:
        icon_fragments = ["check", "success", "complete"]
    dialog_roots = [
        '.ant-modal:has-text("正在操作")',
        '.wui-modal:has-text("正在操作")',
        '.u-modal:has-text("正在操作")',
        '[role="dialog"]:has-text("正在操作")',
        '[class*="modal"]:has-text("正在操作")',
        ".ant-modal:visible",
        ".wui-modal:visible",
        ".u-modal:visible",
        '[role="dialog"]:visible',
    ]
    icon_selectors = [f'[class*="{fragment}"]' for fragment in icon_fragments]
    return [f"{root} {icon}" for root in dialog_roots for icon in icon_selectors]


def build_template_download_link_selectors(template: str | None) -> list[str]:
    dialog_roots = _template_download_dialog_root_selectors()
    download_links = [
        'a:text-is("下载")',
        'button:text-is("下载")',
        'span:text-is("下载")',
        'div:text-is("下载")',
        '*:text-is("下载")',
        '[role="button"]:text-is("下载")',
        'a:has-text("下载")',
        'button:has-text("下载")',
        '[role="button"]:has-text("下载")',
    ]
    if not template:
        return [f"{root} {link}" for root in dialog_roots for link in download_links]
    quoted = json.dumps(template, ensure_ascii=False)
    row_roots = [
        f'tr:has-text({quoted})',
        f'[role="row"]:has-text({quoted})',
        f'[class*="row"]:has-text({quoted})',
        f'div:has-text({quoted})',
        f'li:has-text({quoted})',
    ]
    return [f"{root} {row} {link}" for root in dialog_roots for row in row_roots for link in download_links]


def _template_download_dialog_root_selectors() -> list[str]:
    selectors: list[str] = []
    for title in ["模版下载", "模板下载"]:
        selectors.extend(_dialog_root_selectors(title))
    return selectors


def _dialog_root_selectors(title: str | None = None) -> list[str]:
    roots = [
        ".ant-modal:visible",
        ".wui-modal:visible",
        ".u-modal:visible",
        '[role="dialog"]:visible',
        '[class*="modal"]:visible',
    ]
    if not title:
        return roots
    quoted = json.dumps(title, ensure_ascii=False)
    return [f"{root}:has-text({quoted})" for root in roots]


def build_query_expand_selectors() -> list[str]:
    return RENDER_ADAPTERS.selectors("query.expand")


def build_query_action_selectors(action_label: str = "查询", fieldids: list[str] | None = None) -> list[str]:
    return RENDER_ADAPTERS.selectors("query.action", action_label, fieldids=fieldids)


def build_query_reset_selectors(query_region_fieldid: str) -> list[str]:
    return RENDER_ADAPTERS.selectors("query.reset", query_region_fieldid)


def build_query_reset_identity_selectors() -> list[str]:
    return RENDER_ADAPTERS.selectors("query.reset_identity")


def build_query_reset_text_selectors() -> list[str]:
    return RENDER_ADAPTERS.selectors("query.reset_text")


def build_query_choice_selectors(value: str) -> list[str]:
    return RENDER_ADAPTERS.selectors("query.choice", value)


def build_query_choice_tree_closed_switcher_selectors() -> list[str]:
    return RENDER_ADAPTERS.selectors("query.choice_tree_closed_switcher")


def build_menu_open_urls(base_url: str, menu_target: MenuTarget | dict[str, Any]) -> list[str]:
    service_code = _get_menu_target_value(menu_target, "service_code")
    if service_code:
        return [build_service_url(base_url, service_code)]
    service_url = _get_menu_target_value(menu_target, "service_url")
    if service_url:
        return [build_hash_url(base_url, service_url)]
    raise ValueError("菜单缺少可打开的 service_code 或 service_url")


def should_open_menu_in_new_tab(current_url: str, target_url: str) -> bool:
    return current_url.rstrip("/") == target_url.split("#", 1)[0].rstrip("/") and "#" in target_url


def _runtime_business_host(base_url: str, page_url: str) -> str:
    parsed_page = urlparse(str(page_url or ""))
    if parsed_page.scheme in {"http", "https"} and parsed_page.netloc:
        return f"{parsed_page.scheme}://{parsed_page.netloc}"
    parsed_base = urlparse(str(base_url or ""))
    if parsed_base.scheme in {"http", "https"} and parsed_base.netloc:
        return f"{parsed_base.scheme}://{parsed_base.netloc}"
    raise RuntimeError(f"无法识别 BPR 业务域名: base_url={base_url!r}, page_url={page_url!r}")


def _extract_bpr_report_url(text: str) -> str:
    payload = _safe_json_text(text)
    for value in _walk_bpr_response_values(payload):
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("http"):
                return stripped
    match = re.search(r"https?://[^\s\"'<>]+/iuap-ymc-[^\s\"'<>]+", text or "")
    return match.group(0) if match else ""


def _walk_bpr_response_values(value: Any):
    if isinstance(value, dict):
        for key in ("message", "data", "url", "reportUrl", "report_url"):
            if key in value:
                yield value[key]
        for item in value.values():
            yield from _walk_bpr_response_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_bpr_response_values(item)
    else:
        yield value


def _safe_json_text(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return text


def _bpr_event_count(uba_data: list[dict[str, Any]]) -> int:
    total = 0
    for item in uba_data:
        content = item.get("content") if isinstance(item, dict) else None
        if isinstance(content, list):
            total += len(content)
    return total


def _first_non_empty(payload: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return ""


def build_hash_url(base_url: str, route: str) -> str:
    if route.startswith(("http://", "https://")):
        return route
    if route.startswith("#"):
        return f"{base_url.rstrip('/')}/{route}"
    return urljoin(base_url, route)


def _get_menu_target_value(menu_target: MenuTarget | dict[str, Any], key: str) -> Any:
    if isinstance(menu_target, dict):
        return menu_target.get(key)
    return getattr(menu_target, key, None)


def _guess_row_action_fieldid(action_label: str) -> str:
    return guess_row_action_fieldid(action_label)


def _guess_action_fieldid(action_label: str) -> str:
    return guess_action_fieldid(action_label)


def _is_download_action(action_label: str) -> bool:
    return action_label in {"导出", "导出excel"}


def _ordered_toolbar_labels(action_label: str, aliases: list[str] | None = None) -> list[str]:
    values = [action_label, *(aliases or [])]
    ordered: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in ordered:
            ordered.append(text)
    return ordered


def _looks_like_template_payload(payload: dict[str, Any]) -> bool:
    data = payload.get("data")
    if not isinstance(data, dict):
        return False
    uidata = data.get("uidata")
    return isinstance(uidata, list) and bool(uidata) and isinstance(uidata[0], dict)


def _normalize_dynamic_template_payload(payload: Any, *, source: str) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    if _looks_like_template_payload(payload):
        normalized = dict(payload)
    else:
        data = payload.get("data")
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


def _dynamic_template_payload_identity_candidates(payload: dict[str, Any]) -> list[str]:
    data = payload.get("data") if isinstance(payload, dict) else None
    uidata = data.get("uidata") if isinstance(data, dict) else None
    root = uidata[0] if isinstance(uidata, list) and uidata and isinstance(uidata[0], dict) else {}
    values = [
        str((data or {}).get("pageId") or "").strip(),
        str((data or {}).get("pageCode") or "").strip(),
        str(root.get("divCode") or "").strip(),
        str(root.get("key") or "").strip(),
    ]
    return list(dict.fromkeys(value for value in values if value))


def _dynamic_template_payload_first_table_identity(payload: dict[str, Any]) -> str:
    data = payload.get("data") if isinstance(payload, dict) else None
    uidata = data.get("uidata") if isinstance(data, dict) else None

    def walk(nodes: Any) -> str:
        if not isinstance(nodes, list):
            return ""
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if node.get("nodeType") == "table" or node.get("name") == "LCDTable":
                return str(node.get("fieldid") or node.get("divCode") or node.get("key") or "").strip()
            identity = walk(node.get("children"))
            if identity:
                return identity
        return ""

    return walk(uidata)


def _dynamic_template_payload_form_field_identities(payload: dict[str, Any]) -> list[str]:
    data = payload.get("data") if isinstance(payload, dict) else None
    uidata = data.get("uidata") if isinstance(data, dict) else None
    identities: list[str] = []
    manifest = None
    table_column_nodes: set[int] = set()
    if isinstance(uidata, list) and uidata and isinstance(uidata[0], dict):
        manifest = build_page_manifest(payload)
        # 表格列也可声明为 formItem；按原节点排除，保留同 fieldid 的独立表单字段。
        table_column_nodes = {id(column.raw) for column in manifest.table_columns}

    def walk(nodes: Any) -> None:
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if node.get("nodeType") == "formItem" and node.get("hide") != 1 and id(node) not in table_column_nodes:
                identity = str(node.get("fieldid") or node.get("divCode") or node.get("key") or "").strip()
                if identity and identity not in identities:
                    identities.append(identity)
            walk(node.get("children"))

    walk(uidata)
    if manifest is not None:
        for field in manifest.fields:
            if field.visible_by_config:
                identities.extend(identity for identity in field.runtime_fieldids if identity not in identities)
    return identities


def _dynamic_template_payload_form_field_labels(payload: dict[str, Any]) -> list[str]:
    data = payload.get("data") if isinstance(payload, dict) else None
    uidata = data.get("uidata") if isinstance(data, dict) else None
    labels: list[str] = []
    table_column_nodes: set[int] = set()
    if isinstance(uidata, list) and uidata and isinstance(uidata[0], dict):
        table_column_nodes = {id(column.raw) for column in build_page_manifest(payload).table_columns}

    def walk(nodes: Any) -> None:
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if node.get("nodeType") == "formItem" and node.get("hide") != 1 and id(node) not in table_column_nodes:
                label = str(node.get("label") or node.get("title") or "").strip()
                if label and label not in labels:
                    labels.append(label)
            walk(node.get("children"))

    walk(uidata)
    return labels


def _selector_at_index(selector: str, index: int) -> str:
    return selector if index == 0 else f"{selector} >> nth={index}"


def _normalize_visible_text(value: str) -> str:
    return "".join(str(value or "").split())


def _unique_download_path(filename: str) -> Path:
    downloads_dir = Path.home() / "Downloads"
    safe_name = filename or f"ydf-download-{int(time.time())}.xlsx"
    target = downloads_dir / safe_name
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    for index in range(1, 1000):
        candidate = downloads_dir / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
    return downloads_dir / f"{stem}-{int(time.time())}{suffix}"


def _request_attr(request: Any, name: str) -> str:
    value = getattr(request, name, "")
    if callable(value):
        try:
            value = value()
        except Exception:
            value = ""
    return str(value or "")


def _request_post_data_buffer(request: Any) -> bytes | str | None:
    value = getattr(request, "post_data_buffer", None)
    if callable(value):
        try:
            value = value()
        except Exception:
            value = None
    if value is not None:
        return value
    value = getattr(request, "post_data", None)
    if callable(value):
        try:
            value = value()
        except Exception:
            value = None
    return value


def _request_body_size(request: Any) -> tuple[int, bool, str]:
    sizes = getattr(request, "sizes", None)
    if callable(sizes):
        try:
            request_sizes = sizes()
        except asyncio.CancelledError:
            request_sizes = {}
        except Exception:
            request_sizes = {}
        if isinstance(request_sizes, dict) and "requestBodySize" in request_sizes:
            try:
                body_size = int(request_sizes["requestBodySize"])
            except (TypeError, ValueError):
                body_size = -1
            if body_size >= 0:
                return body_size, True, ""
    body = _request_post_data_buffer(request)
    if isinstance(body, bytes):
        return len(body), True, ""
    if isinstance(body, str):
        return len(body.encode("utf-8")), True, ""
    try:
        content_length = int(_request_headers(request).get("content-length", ""))
    except (TypeError, ValueError):
        content_length = -1
    if content_length >= 0:
        return content_length, True, ""
    if _request_attr(request, "method").upper() in {"GET", "HEAD"}:
        return 0, True, ""
    return 0, False, "request_body_size_unavailable"


def _forward_request_headers(headers: Any) -> dict[str, str]:
    if callable(headers):
        try:
            headers = headers()
        except Exception:
            headers = {}
    if not isinstance(headers, dict):
        return {}
    blocked = {
        "host",
        "content-length",
        "connection",
        "proxy-connection",
        "transfer-encoding",
        "upgrade",
        "http2-settings",
    }
    forwarded: dict[str, str] = {}
    for key, value in headers.items():
        name = str(key)
        if name.lower() in blocked:
            continue
        forwarded[name] = str(value)
    return forwarded


def _forward_response_headers(headers: Any) -> dict[str, str]:
    if callable(headers):
        try:
            headers = headers()
        except Exception:
            headers = {}
    if not isinstance(headers, dict):
        return {}
    blocked = {
        "set-cookie",
        "content-length",
        "content-encoding",
        "connection",
        "proxy-connection",
        "transfer-encoding",
        "upgrade",
    }
    forwarded: dict[str, str] = {}
    for key, value in headers.items():
        name = str(key)
        if name.lower() in blocked:
            continue
        forwarded[name] = str(value)
    return forwarded


def _route_fallback(route: Any) -> None:
    fallback = getattr(route, "fallback", None)
    if callable(fallback):
        fallback()
        return
    route.continue_()


def _is_browser_closed_error(exc: Exception) -> bool:
    return "target page, context or browser has been closed" in str(exc).lower()


def _browser_app_name(context: Any) -> str | None:
    try:
        executable_path = str(context.browser.browser_type.executable_path or "")
    except Exception:
        return None
    for part in Path(executable_path).parents:
        if part.suffix == ".app":
            return part.stem
    return None


def _manual_browser_window_count(app_name: str | None) -> int | None:
    if not app_name or sys.platform != "darwin":
        return None
    script = (
        'tell application "System Events"\n'
        f'if not (exists process "{app_name}") then return "0"\n'
        "end tell\n"
        f'tell application "{app_name}" to return count of windows'
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            check=False,
            capture_output=True,
            text=True,
            timeout=1,
        )
    except Exception:
        return None
    try:
        return int((result.stdout or "").strip())
    except ValueError:
        return None


def _content_length(response: Any) -> int:
    headers = getattr(response, "headers", {}) or {}
    if callable(headers):
        try:
            headers = headers()
        except Exception:
            headers = {}
    if not isinstance(headers, dict):
        return 0
    value = headers.get("content-length") or headers.get("Content-Length") or ""
    try:
        return max(0, int(str(value)))
    except (TypeError, ValueError):
        return 0


def _response_body_size(request: Any, response: Any) -> int:
    sizes = getattr(request, "sizes", None)
    if callable(sizes):
        try:
            request_sizes = sizes()
        except (Exception, asyncio.CancelledError):
            request_sizes = {}
        if isinstance(request_sizes, dict):
            try:
                body_size = int(request_sizes.get("responseBodySize") or 0)
            except (TypeError, ValueError):
                body_size = 0
            if body_size > 0:
                return body_size
    return _content_length(response)


def _request_response(request: Any) -> Any:
    response = getattr(request, "response", None)
    if not callable(response):
        return None
    try:
        return response()
    except Exception:
        return None


def _request_failure_text(request: Any) -> str:
    failure = getattr(request, "failure", None)
    if callable(failure):
        try:
            failure = failure()
        except Exception:
            failure = None
    if isinstance(failure, dict):
        return str(failure.get("errorText") or failure.get("error_text") or "")
    return str(failure or "")


def _response_duration_ms(response: Any) -> int:
    return _request_duration_ms(getattr(response, "request", None))


def _remaining_timeout_ms(deadline: float) -> int:
    return max(0, int((deadline - time.monotonic()) * 1000))


def _request_duration_ms(request: Any, started_at: float | None = None) -> int:
    timing = getattr(request, "timing", None)
    if callable(timing):
        try:
            timing = timing()
        except Exception:
            timing = None
    duration = _duration_from_timing(timing) if isinstance(timing, dict) else 0
    if duration:
        return duration
    if started_at is None:
        return 0
    return max(0, int(round((time.monotonic() - started_at) * 1000)))


def _duration_from_timing(timing: dict[str, Any]) -> int:
    start = _timing_value(timing, "startTime")
    end = max(
        _positive_timing_value(timing, "responseEnd"),
        _positive_timing_value(timing, "responseStart"),
        _positive_timing_value(timing, "requestEnd"),
        _positive_timing_value(timing, "connectEnd"),
        _positive_timing_value(timing, "secureConnectionStart"),
        _positive_timing_value(timing, "connectStart"),
        _positive_timing_value(timing, "domainLookupEnd"),
        _positive_timing_value(timing, "domainLookupStart"),
    )
    if end <= 0:
        return 0
    if start > 0 and end > start:
        return int(round(end - start))
    return int(round(end))


def _timing_value(timing: dict[str, Any], key: str) -> float:
    try:
        return float(timing.get(key) or 0)
    except (TypeError, ValueError):
        return 0.0


def _positive_timing_value(timing: dict[str, Any], key: str) -> float:
    value = _timing_value(timing, key)
    return value if value > 0 else 0.0


def _network_category(url: str, resource_type: str) -> str:
    resource = (resource_type or "").lower()
    if resource in {"script", "stylesheet", "image", "font", "media"}:
        return "static"
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".woff", ".woff2", ".ttf", ".ico"}:
        return "static"
    return "api"


def _performance_step_context_payload(context: dict[str, Any] | None) -> dict[str, Any]:
    if not context:
        return {"step_context": "unknown"}
    payload: dict[str, Any] = {"step_context": str(context.get("step_context") or "step")}
    for key in ("suite_code", "case_code", "step_index", "action"):
        value = context.get(key)
        if value not in (None, ""):
            payload[key] = value
    return payload


def _summarize_network_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    events = [
        {
            **event,
            "category": event.get("category")
            or _network_category(str(event.get("url") or ""), str(event.get("resource_type") or "")),
        }
        for event in events
    ]
    status_counts: dict[str, int] = {}
    encoded_body_size = 0
    request_body_size = 0
    failed_count = 0
    api_count = 0
    static_count = 0
    for event in events:
        if event.get("failed"):
            failed_count += 1
        else:
            status = int(event.get("status") or 0)
            if status:
                key = str(status)
                status_counts[key] = status_counts.get(key, 0) + 1
        encoded_body_size += int(event.get("encoded_body_size") or 0)
        request_body_size += int(event.get("request_body_size") or 0)
        if event.get("category") == "static":
            static_count += 1
        else:
            api_count += 1
    top_slow = sorted(events, key=lambda item: int(item.get("duration_ms") or 0), reverse=True)[:5]
    top_slow_api = sorted(
        [item for item in events if item.get("category") != "static"],
        key=lambda item: int(item.get("duration_ms") or 0),
        reverse=True,
    )[:5]
    top_slow_static = sorted(
        [item for item in events if item.get("category") == "static"],
        key=lambda item: int(item.get("duration_ms") or 0),
        reverse=True,
    )[:5]
    request_body_size_available = all(bool(event.get("request_body_size_available")) for event in events)
    request_body_size_unavailable_reason = ""
    if not request_body_size_available:
        request_body_size_unavailable_reason = next(
            (
                str(event.get("request_body_size_unavailable_reason"))
                for event in events
                if not event.get("request_body_size_available") and event.get("request_body_size_unavailable_reason")
            ),
            "request_body_size_unavailable",
        )
    return {
        "request_count": len(events),
        "failed_count": failed_count,
        "api_request_count": api_count,
        "static_resource_count": static_count,
        "status_counts": status_counts,
        "encoded_body_size": encoded_body_size,
        "request_body_size": request_body_size,
        "request_body_size_available": request_body_size_available,
        "request_body_size_unavailable_reason": request_body_size_unavailable_reason,
        "requests": [_network_event_payload(item) for item in events],
        "top_slow_requests": [_network_event_payload(item) for item in top_slow],
        "top_slow_api_requests": [_network_event_payload(item) for item in top_slow_api],
        "top_slow_static_resources": [_network_event_payload(item) for item in top_slow_static],
    }


def _network_event_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "url": str(item.get("url") or ""),
        "method": str(item.get("method") or ""),
        "resource_type": str(item.get("resource_type") or ""),
        "status": int(item.get("status") or 0),
        "duration_ms": int(item.get("duration_ms") or 0),
        "encoded_body_size": int(item.get("encoded_body_size") or 0),
        "request_body_size": int(item.get("request_body_size") or 0),
        "request_body_size_available": bool(item.get("request_body_size_available")),
        "request_body_size_unavailable_reason": str(item.get("request_body_size_unavailable_reason") or ""),
        "failed": bool(item.get("failed")),
        "error": str(item.get("error") or ""),
        "step_context": str(item.get("step_context") or "unknown"),
        "suite_code": str(item.get("suite_code") or ""),
        "case_code": str(item.get("case_code") or ""),
        "step_index": int(item.get("step_index") or 0),
        "action": str(item.get("action") or ""),
        "completed_step_context": str(item.get("completed_step_context") or "unknown"),
        "completed_step_index": int(item.get("completed_step_index") or 0),
        "completed_action": str(item.get("completed_action") or ""),
    }


def _resolve_import_file(path: str) -> Path:
    file_path = Path(path).expanduser()
    if not file_path.exists():
        raise RuntimeError(f"导入文件不存在: {file_path}")
    if not file_path.is_file():
        raise RuntimeError(f"导入路径不是文件: {file_path}")
    return file_path.resolve()


def _is_direct_file_import_action(bound: BoundElement) -> bool:
    candidate = bound.candidate
    return _is_direct_file_import_candidate(
        {
            "component_name": candidate.component_name,
            "raw": candidate.raw,
        }
    )


def _is_direct_file_import_candidate(candidate: dict[str, Any]) -> bool:
    raw = candidate.get("raw") if isinstance(candidate.get("raw"), dict) else {}
    props = raw.get("props") if isinstance(raw.get("props"), dict) else {}
    component_name = str(candidate.get("component_name") or raw.get("name") or "").lower()
    return component_name == "ydfileimportbutton" or bool(candidate.get("justFile") or raw.get("justFile") or props.get("justFile"))


def _import_candidate_matches(candidate: dict[str, Any], label: str, fieldid: str | None) -> bool:
    candidate_fieldid = str(candidate.get("fieldid") or "").strip()
    if fieldid:
        return candidate_fieldid == fieldid
    aliases = {
        str(candidate.get(key) or "").strip()
        for key in ("label", "title", "key", "fieldid")
    }
    aliases.update(str(item or "").strip() for item in candidate.get("action_keys") or [])
    return label in aliases


def _should_probe_direct_import(
    label: str,
    fieldid: str | None,
    action_candidates: list[dict[str, Any]],
) -> bool:
    candidate = next(
        (item for item in action_candidates if _import_candidate_matches(item, label, fieldid)),
        None,
    )
    if candidate is None:
        return bool(fieldid)
    raw = candidate.get("raw") if isinstance(candidate.get("raw"), dict) else {}
    component_name = str(candidate.get("component_name") or raw.get("name") or "").lower()
    return component_name != "ydfimportdropdownbutton"


def _request_headers(request: Any) -> dict[str, str]:
    headers = getattr(request, "headers", {}) or {}
    if callable(headers):
        try:
            headers = headers()
        except Exception:
            headers = {}
    if not isinstance(headers, dict):
        return {}
    return {str(key).lower(): str(value) for key, value in headers.items()}


def _response_headers(response: Any) -> dict[str, str]:
    headers = getattr(response, "headers", {}) or {}
    if callable(headers):
        try:
            headers = headers()
        except Exception:
            headers = {}
    if not isinstance(headers, dict):
        return {}
    return {str(key).lower(): str(value) for key, value in headers.items()}


def _is_direct_import_seed_request(request: Any, filenames: list[str]) -> bool:
    method = _request_attr(request, "method").upper()
    if method not in {"GET", "POST", "PUT", "PATCH"}:
        return False
    url = unquote(_request_attr(request, "url")).lower()
    content_type = _request_headers(request).get("content-type", "").lower()
    body = _request_post_data_buffer(request)
    if isinstance(body, bytes):
        body_text = body.decode("utf-8", errors="ignore").lower()
    else:
        body_text = str(body or "").lower()
    normalized_filenames = [str(name or "").lower() for name in filenames if name]
    has_filename = any(name in url or name in body_text for name in normalized_filenames)
    has_file_content_type = "multipart/form-data" in content_type or "application/octet-stream" in content_type
    has_import_url = any(token in url for token in ("/import", "import?", "upload", "/excel/"))
    return has_filename or has_file_content_type or has_import_url


def _direct_import_response_outcome(response: Any) -> tuple[str, str]:
    try:
        payload = response.json()
    except Exception:
        return "", ""
    if not isinstance(payload, dict):
        return "", ""
    message = str(
        payload.get("message")
        or payload.get("msg")
        or payload.get("errorMessage")
        or payload.get("error")
        or ""
    ).strip()
    lower_message = message.lower()
    if any(token in lower_message for token in ("失败", "错误", "不能为空", "error", "fail")):
        return "failure", message
    success = payload.get("success")
    if isinstance(success, bool):
        return ("success" if success else "failure"), message
    code = str(payload.get("code") or payload.get("status") or "").strip().lower()
    if code in {"0", "200", "success", "ok", "succeeded"}:
        return "success", message
    if code and code not in {"1", "true"}:
        return "failure", message or f"业务状态 {code}"
    if any(token in lower_message for token in ("成功", "完成", "success", "completed")):
        return "success", message
    return "", message


def _direct_import_network_result(files: list[str], events: list[dict[str, Any]]) -> dict[str, Any]:
    status = "submitted"
    message = "后端已接收导入文件"
    for event in events:
        http_status = int(event.get("status") or 0)
        if event.get("failed"):
            status = "failure"
            message = str(event.get("error") or "后端请求失败")
            break
        if http_status < 200 or http_status >= 300:
            status = "failure"
            message = f"HTTP {http_status}: {event.get('url') or ''}".strip()
            break
        if event.get("business_status") == "failure":
            status = "failure"
            message = str(event.get("message") or "导入处理失败")
            break
        if event.get("business_status") == "success":
            status = "success"
            message = str(event.get("message") or "导入成功")
    return {
        "import_results": [
            {"file": Path(file).name, "status": status, "message": message}
            for file in files
        ],
        "network_requests": [_direct_import_network_event_payload(item) for item in events],
    }


def _direct_import_network_event_payload(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "url": str(event.get("url") or ""),
        "method": str(event.get("method") or ""),
        "resource_type": str(event.get("resource_type") or ""),
        "status": int(event.get("status") or 0),
        "failed": bool(event.get("failed")),
        "error": str(event.get("error") or ""),
        "business_status": str(event.get("business_status") or ""),
        "message": str(event.get("message") or ""),
        "seed": bool(event.get("seed")),
    }


def _normalize_direct_import_status(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"success", "succeeded", "done", "complete", "completed"} or "成功" in text or "完成" in text:
        return "success"
    if text in {"failure", "failed", "error"} or "失败" in text:
        return "failure"
    return text


def _is_amount_unit_action_candidate(candidate: dict[str, Any]) -> bool:
    raw = candidate.get("raw") if isinstance(candidate.get("raw"), dict) else {}
    component_name = str(candidate.get("component_name") or raw.get("name") or "").lower()
    return component_name == "lcdsetamtunit"


def _direct_file_import_aliases(candidate: dict[str, Any]) -> list[str]:
    aliases: list[str] = []
    for key in ("label", "title", "key", "fieldid"):
        value = str(candidate.get(key) or "").strip()
        if value and value not in aliases:
            aliases.append(value)
    for value in candidate.get("action_keys") or []:
        text = str(value or "").strip()
        if text and text not in aliases:
            aliases.append(text)
    return aliases


def _import_sub_action_aliases(label: str) -> list[str]:
    aliases = [label]
    if label == "下载模版":
        aliases.append("下载模板")
    elif label == "下载模板":
        aliases.append("下载模版")
    return aliases


def _normalize_import_filename(value: str) -> str:
    ignored = {" ", "\n", "\r", "\t", "_", "-"}
    return "".join(ch for ch in str(value or "") if ch not in ignored).lower()


def _looks_like_single_import_progress(text: str) -> bool:
    compact = _compact_import_progress_text(text)
    return "正在操作1/1" in compact or "导入1/1" in compact


def _looks_like_import_progress_text(text: str) -> bool:
    compact = _compact_import_progress_text(text)
    return ("导入1/1" in compact) or ("正在操作" in compact and "导入" in compact) or (
        "导入" in compact and "移除" in compact and "查看" in compact
    )


def _collect_context_text_parts(context: Any) -> list[str]:
    modal_parts: list[str] = []
    for selector in (
        ".ant-modal:visible",
        ".wui-modal:visible",
        ".u-modal:visible",
        '[role="dialog"]:visible',
        '[class*="modal"]:visible',
    ):
        try:
            text = context.locator(selector).first.inner_text(timeout=1000).strip()
        except Exception:
            continue
        if text:
            modal_parts.append(text)
    if any(_import_status_from_text(text) for text in modal_parts):
        return modal_parts

    parts: list[str] = [*modal_parts]
    try:
        body_text = context.locator("body").first.inner_text(timeout=1000).strip()
    except Exception:
        body_text = ""
    if body_text:
        parts.append(body_text)
    try:
        shadow_text = context.evaluate(
            """() => {
                const parts = [];
                const visit = (node) => {
                    if (!node) return;
                    if (node.nodeType === Node.TEXT_NODE) {
                        const text = (node.textContent || '').trim();
                        if (text) parts.push(text);
                        return;
                    }
                    if (node.nodeType === Node.ELEMENT_NODE) {
                        const style = window.getComputedStyle(node);
                        if (style.display === 'none' || style.visibility === 'hidden') return;
                        if (node.shadowRoot) visit(node.shadowRoot);
                    }
                    if (node.childNodes) {
                        for (const child of node.childNodes) visit(child);
                    }
                };
                visit(document.body);
                return parts.join('\\n');
            }"""
        )
    except Exception:
        shadow_text = ""
    if shadow_text:
        parts.append(str(shadow_text))
    return parts


def _compact_import_progress_text(text: str) -> str:
    ignored = {" ", "\n", "\r", "\t", "(", ")", "（", "）"}
    return "".join(ch for ch in str(text or "") if ch not in ignored)


def _import_status_from_text(text: str) -> str:
    if "导入失败" in text or ("导入" in text and "失败" in text):
        return "failure"
    if "导入完成" in text or "导入成功" in text or ("导入" in text and "完成" in text):
        return "success"
    return ""


def _notification_import_status(item: dict[str, str]) -> str:
    message = str(item.get("message") or "")
    notification_type = str(item.get("type") or "").lower()
    if notification_type == "error" or "失败" in message or "错误" in message or "不能为空" in message:
        return "failure"
    if "导入完成" in message or "导入成功" in message or "成功" in message:
        return "success"
    return ""


def _extract_import_failure_message(text: str) -> str:
    compact = " ".join(str(text or "").split())
    if not compact:
        return ""
    if _looks_like_import_progress_text(compact):
        return ""
    for prefix in ("信息提示", "错误提示", "温馨提示", "失败原因", "错误原因", "提示", "信息", "错误"):
        if compact.startswith(prefix):
            compact = compact[len(prefix):].strip()
            break
    for suffix in ("关闭", "确定", "取消"):
        if compact.endswith(suffix):
            compact = compact[: -len(suffix)].strip()
            break
    marker_positions = [compact.find(marker) for marker in ("导入失败", "失败") if compact.find(marker) >= 0]
    if not marker_positions:
        return compact[:800]
    index = min(marker_positions)
    start = -1
    for marker in ("正在操作", "导入进度", "导入 (", "导入("):
        start = compact.rfind(marker, 0, index)
        if start >= 0:
            break
    if start < 0:
        start = max(0, index - 500)
    end = min(len(compact), index + 300)
    return compact[start:end]


def _runtime_notification_matches(
    item: dict[str, Any],
    *,
    expected_type: str = "",
    contains: str = "",
    equals: str = "",
    message: str = "",
) -> bool:
    actual_message = str(item.get("message") or "")
    return (
        (not expected_type or str(item.get("type") or "") == expected_type)
        and (not contains or contains in actual_message)
        and (not equals or actual_message == equals)
        and (not message or _runtime_notification_message_matches(actual_message, message))
    )


def _runtime_notification_message_matches(actual: str, expected: str) -> bool:
    if actual == expected:
        return True
    return _normalize_runtime_notification_message(actual) == _normalize_runtime_notification_message(expected)


def _normalize_runtime_notification_message(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip().rstrip("!！。.;；,，")


def _notification_expectation_text(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("expectedType", "contains", "equals", "message", "label"):
        value = str(payload.get(key) or "").strip()
        if value:
            parts.append(f"{key}={value}")
    return " ".join(parts) or "*"


def _notification_close_error_message(payload: dict[str, Any], result: dict[str, Any]) -> str:
    reason = str(result.get("reason") or "").strip()
    expectation = _notification_expectation_text(payload)
    diagnostic = str(result.get("diagnostic") or "").strip()
    actual = result.get("actual_notifications")
    matched = result.get("matched_notification")
    if reason == "not_found":
        message = f"未找到匹配页面提示: expected={expectation} actual={actual or []}"
    elif reason == "close_entry_missing":
        message = f"未找到页面提示关闭入口: expected={expectation} matched={matched or {}}"
    elif reason == "still_visible":
        message = f"页面提示关闭后仍可见: expected={expectation} matched={matched or {}}"
    else:
        message = f"页面提示关闭失败: expected={expectation} reason={reason or 'unknown'}"
    if diagnostic:
        message = f"{message}: {diagnostic}"
    return message


def _is_visible_text(page, text: str) -> bool:
    for candidate in (
        lambda: page.locator(f"text={json.dumps(text, ensure_ascii=False)}").first,
        lambda: page.get_by_text(text, exact=True).first,
        lambda: page.get_by_text(text, exact=False).first,
    ):
        try:
            if candidate().is_visible(timeout=300):
                return True
        except Exception:
            continue
    return False


def _extract_row_match_values(match: dict[str, Any]) -> list[str]:
    raw_conditions = match.get("conditions") or match.get("all")
    if raw_conditions is None:
        value = str(match.get("equals") or "").strip()
        return [value] if value else []
    if isinstance(raw_conditions, dict):
        raw_conditions = [raw_conditions]
    if not isinstance(raw_conditions, list):
        return []
    values = []
    for item in raw_conditions:
        if not isinstance(item, dict):
            continue
        value = str(item.get("equals") or "").strip()
        if value:
            values.append(value)
    return values


def _row_match_columns(match: dict[str, Any]) -> list[str]:
    raw_conditions = match.get("conditions") or match.get("all")
    if raw_conditions is None:
        column = str(match.get("column") or match.get("field") or "").strip()
        return [column] if column else []
    if isinstance(raw_conditions, dict):
        raw_conditions = [raw_conditions]
    if not isinstance(raw_conditions, list):
        return []
    columns: list[str] = []
    for item in raw_conditions:
        if not isinstance(item, dict):
            continue
        column = str(item.get("column") or item.get("field") or "").strip()
        if column and column not in columns:
            columns.append(column)
    return columns


def _format_column_match_for_error(column: str | None, values: list[str]) -> str:
    if column and len(values) == 1:
        return f"{column}={values[0]}"
    if column:
        return f"{column}: {values}"
    return str(values)


def _table_row_click_not_confirmed(debug: dict[str, Any] | None) -> bool:
    return bool(debug and debug.get("strategy") == "row_click" and debug.get("selected_after") is False)


def _table_row_debug_text(row) -> str:
    try:
        return " ".join((row.inner_text(timeout=300) or "").split())[:240]
    except Exception:
        return ""


def _first_row_match_column(match: dict[str, Any]) -> str | None:
    raw_conditions = match.get("conditions") or match.get("all")
    if raw_conditions is None:
        column = str(match.get("column") or match.get("field") or "").strip()
        return column or None
    if isinstance(raw_conditions, dict):
        raw_conditions = [raw_conditions]
    if not isinstance(raw_conditions, list):
        return None
    for item in raw_conditions:
        if not isinstance(item, dict):
            continue
        column = str(item.get("column") or item.get("field") or "").strip()
        if column:
            return column
    return None


_TRANSFER_DIALOG_SELECT_SCRIPT = """
async (args) => {
  const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
  const normalizeCompact = (value) => normalize(value).replace(/\\s+/g, '');
  const visible = (el) => {
    if (!el || el.nodeType !== 1) return false;
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style && style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
  };
  const textOf = (el) => normalize(el ? (el.innerText || el.textContent || '') : '');
  const all = (root, selector) => {
    try {
      return Array.from(root.querySelectorAll(selector));
    } catch (_error) {
      return [];
    }
  };
  const dialogs = [
    ...all(document, '.ant-modal, .wui-modal, .u-modal, .yy-modal, [role="dialog"], [class*="modal"], [class*="Modal"]'),
  ].filter(visible);
  const title = normalize(args.title || '');
  const dialog = dialogs
    .filter((item) => !title || textOf(item).includes(title))
    .map((item) => {
      const rect = item.getBoundingClientRect();
      return { item, area: rect.width * rect.height };
    })
    .sort((a, b) => b.area - a.area)[0]?.item;
  if (!dialog) {
    throw new Error(`未找到双列表选择窗口${title ? `: ${title}` : ''}`);
  }
  const dialogRect = dialog.getBoundingClientRect();
  const footer = all(dialog, '.ant-modal-footer, .wui-modal-footer, .u-modal-footer, [class*="footer"]').find(visible);
  const footerTop = footer ? footer.getBoundingClientRect().top : dialogRect.bottom;
  const listRoots = all(
    dialog,
    [
      '.ant-transfer-list',
      '.wui-transfer-list',
      '.u-transfer-list',
      '[class*="transfer-list"]',
      '[class*="TransferList"]',
      '.ant-table',
      '.wui-table',
      '.u-table',
      '[role="table"]',
      '[role="grid"]',
      'table',
    ].join(',')
  )
    .filter(visible)
    .filter((el) => {
      const rect = el.getBoundingClientRect();
      return rect.top < footerTop && rect.width >= 120 && rect.height >= 80;
    })
    .sort((a, b) => a.getBoundingClientRect().left - b.getBoundingClientRect().left);
  let sourceRoots = listRoots.filter((el) => {
    const rect = el.getBoundingClientRect();
    return rect.left < dialogRect.left + dialogRect.width * 0.6;
  });
  if (!sourceRoots.length) {
    sourceRoots = [dialog];
  }
  const columnIndex = (tableRoot, column) => {
    const wanted = normalizeCompact(column);
    if (!wanted) return -1;
    const headers = all(tableRoot, 'th, [role="columnheader"], .ant-table-cell, .wui-table-cell, .u-table-cell')
      .filter(visible)
      .filter((el) => {
        const tag = String(el.tagName || '').toLowerCase();
        return tag === 'th' || String(el.getAttribute('role') || '') === 'columnheader' || el.closest('thead');
      });
    return headers.findIndex((el) => normalizeCompact(textOf(el)) === wanted);
  };
  const cellText = (row, index) => {
    const cells = all(row, 'td, [role="gridcell"], .ant-table-cell, .wui-table-cell, .u-table-cell').filter(visible);
    if (index >= 0 && cells[index]) return textOf(cells[index]);
    return textOf(row);
  };
  const rowMatches = (row, match, tableRoot) => {
    const equals = normalize(match.equals ?? match.value ?? match.label ?? match.text ?? '');
    const contains = normalize(match.contains ?? '');
    const index = columnIndex(tableRoot, match.column);
    const haystack = cellText(row, index);
    if (equals && normalizeCompact(haystack) === normalizeCompact(equals)) return true;
    if (equals && haystack.includes(equals)) return true;
    if (contains && haystack.includes(contains)) return true;
    return false;
  };
  const findCandidate = (match) => {
    for (const root of sourceRoots) {
      const rows = all(root, 'tbody tr, [role="row"], .ant-table-row, .wui-table-row, .u-table-row, li, [class*="item"], [class*="Item"]')
        .filter(visible)
        .filter((el) => {
          const rect = el.getBoundingClientRect();
          return rect.top < footerTop && rect.left < dialogRect.left + dialogRect.width * 0.7;
        });
      const row = rows.find((item) => rowMatches(item, match, root));
      if (row) return row;
    }
    return null;
  };
  const clickSelectable = (row) => {
    const target = all(row, 'input[type="checkbox"], [role="checkbox"], .ant-checkbox, .wui-checkbox, .u-checkbox')
      .filter(visible)[0] || row;
    target.click();
  };
  const items = Array.isArray(args.items) ? args.items : [];
  const selected = [];
  for (const item of items) {
    const match = item && item.match ? item.match : item;
    const row = findCandidate(match || {});
    if (!row) {
      throw new Error(`未找到待选数据: ${JSON.stringify(match)}`);
    }
    clickSelectable(row);
    selected.push(match);
  }
  await new Promise((resolve) => setTimeout(resolve, 150));
  const buttonTextMatches = (button) => {
    const childText = all(button, '*').map((el) => [
      el.className,
      el.getAttribute('title'),
      el.getAttribute('aria-label'),
      textOf(el),
    ].join(' ')).join(' ');
    const text = [
      textOf(button),
      button.getAttribute('title'),
      button.getAttribute('aria-label'),
      button.className,
      childText,
    ].join(' ');
    const lower = text.toLowerCase();
    const move = String(args.move || 'to_right').toLowerCase();
    if (/(left|arrow-left|2arrow-left|左|移出)/i.test(text)) return false;
    const wantsAll = /(all|全部|double|双)/i.test(move);
    if (!wantsAll && /(2arrow-right|double-right|double|全选|全部)/i.test(text)) return false;
    return /(right|arrow-right)/i.test(text) || /(>|右|移入|添加|加入|选择)/.test(text);
  };
  const moveButton = all(dialog, 'button, [role="button"]')
    .filter(visible)
    .filter((button) => !button.disabled && buttonTextMatches(button))
    .sort((a, b) => {
      const ar = a.getBoundingClientRect();
      const br = b.getBoundingClientRect();
      const center = dialogRect.left + dialogRect.width / 2;
      return Math.abs((ar.left + ar.right) / 2 - center) - Math.abs((br.left + br.right) / 2 - center);
    })[0];
  if (items.length && !moveButton) {
    throw new Error('未找到双列表移入按钮');
  }
  if (items.length && moveButton) {
    moveButton.click();
    await new Promise((resolve) => setTimeout(resolve, 150));
  }
  let confirmed = false;
  if (args.confirm !== false) {
    const confirmButton = all(dialog, 'button, [role="button"]')
      .filter(visible)
      .filter((button) => /^(确定|确认)$/.test(textOf(button)))
      .sort((a, b) => b.getBoundingClientRect().top - a.getBoundingClientRect().top)[0];
    if (!confirmButton) {
      throw new Error('未找到双列表确认按钮');
    }
    confirmButton.click();
    confirmed = true;
  }
  return {
    selected,
    selected_count: selected.length,
    moved: selected.length,
    confirmed,
  };
}
"""




_DYNAMIC_TEMPLATE_WORK_SURFACE_SCRIPT = """
(identities) => {
  const wanted = new Set((identities || []).map((value) => String(value || '').trim()).filter(Boolean));
  const visible = (node) => {
    if (!node) return false;
    const style = window.getComputedStyle(node);
    const rect = node.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden'
      && style.pointerEvents !== 'none' && rect.width > 0 && rect.height > 0;
  };
  const receivesPointer = (node) => {
    if (!visible(node) || node.closest('[inert], [aria-hidden="true"]')) return false;
    if (node.matches('[disabled], [aria-disabled="true"], [readonly], [aria-readonly="true"]')) return false;
    const rect = node.getBoundingClientRect();
    const points = [
      [rect.left + rect.width / 2, rect.top + rect.height / 2],
      [rect.left + Math.min(8, rect.width / 2), rect.top + Math.min(8, rect.height / 2)]
    ];
    return points.some(([x, y]) => {
      const hit = document.elementFromPoint(x, y);
      return Boolean(hit && (hit === node || node.contains(hit) || hit.contains(node)));
    });
  };
  const roots = Array.from(document.querySelectorAll('[fieldid], [data-fieldid], [id]'))
    .filter((node) => wanted.has(String(
      node.getAttribute('fieldid') || node.getAttribute('data-fieldid') || node.id || ''
    ).trim()))
    .filter(visible);
  if (!roots.length) return { root: false, interactive: false, root_count: 0, interactive_count: 0 };
  const workSurfaceSelector = [
    '[role="dialog"]',
    '.ant-modal', '.wui-modal', '.u-modal', '.yy-modal',
    '.ant-drawer', '.wui-drawer', '.u-drawer', '.yy-drawer',
    '[class*="modal"]', '[class*="Modal"]',
    '[class*="drawer"]', '[class*="Drawer"]',
    '[class*="popup"]', '[class*="Popup"]'
  ].join(',');
  const workSurfaces = Array.from(new Set(roots.map((root) => root.closest(workSurfaceSelector) || document.body)));
  const interactiveCount = workSurfaces.filter((root) => {
    const controls = roots
      .filter((node) => (node.closest(workSurfaceSelector) || document.body) === root)
      .flatMap((node) => [node, ...node.querySelectorAll(
        'input, textarea, select, button, [role], [contenteditable="true"], [fieldid], [data-fieldid]'
      )]);
    return controls.some(receivesPointer);
  }).length;
  return {
    root: workSurfaces.length > 0,
    interactive: interactiveCount > 0,
    root_count: workSurfaces.length,
    interactive_count: interactiveCount,
  };
}
"""


_DYNAMIC_TEMPLATE_FIELD_LABEL_SCRIPT = """
(label) => {
  const normalize = (value) => String(value || '').replace(/\\s+/g, '').replace(/^[*＊]/, '');
  const wanted = normalize(label);
  const visible = (node) => {
    if (!node) return false;
    const style = window.getComputedStyle(node);
    const rect = node.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
  };
  const matches = Array.from(document.querySelectorAll([
    'label',
    '[role="heading"]',
    '.ant-form-item-label',
    '.wui-form-item-label',
    '.u-form-item-label',
    '.xui-form-label',
    '[class*="form-item-label"]',
    '[class*="formItemLabel"]',
    '[class$="-label"]',
    '[class$="_label"]'
  ].join(','))).filter(visible).filter((node) => normalize(node.innerText || node.textContent) === wanted);
  const interactive = matches.filter((node) => {
    let container = node;
    for (let depth = 0; depth < 8 && container; depth += 1, container = container.parentElement) {
      if (Array.from(container.querySelectorAll(
        'input, textarea, select, [contenteditable="true"], [role="textbox"]'
      )).some(visible)) return true;
    }
    return false;
  });
  return {
    root: interactive.length === 1,
    interactive: interactive.length === 1,
    root_count: interactive.length,
    interactive_count: interactive.length,
  };
}
"""


_DOM_SCAN_SCRIPT = """
(frameIndex) => {
  const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const isDialogRoot = (el) => el.matches('[role="dialog"], .ant-modal, .wui-modal, .u-modal, .w-modal, .yy-modal');
  const findLabelText = (el) => {
    const ariaLabelledBy = el.getAttribute('aria-labelledby');
    if (ariaLabelledBy) {
      const text = ariaLabelledBy
        .split(/\\s+/)
        .map((id) => document.getElementById(id))
        .filter(Boolean)
        .map((node) => normalize(node.innerText || node.textContent || ''))
        .filter(Boolean)
        .join(' ');
      if (text) return text;
    }
    if (el.id) {
      const label = document.querySelector(`label[for="${el.id.replace(/"/g, '\\"')}"]`);
      if (label) {
        const text = normalize(label.innerText || label.textContent || '');
        if (text) return text;
      }
    }
    const labelSelectors = [
      'label',
      '.ant-form-item-label',
      '.wui-form-item-label',
      '.u-form-item-label',
      '.workflow-approve-ex-name',
      '.label',
      '.xui-form-label',
      '.xui-table-cell',
      '[class*="form-item-label"]',
      '[class*="FormItemLabel"]',
      '[class*="approve-ex-name"]'
    ].join(',');
    const wrapper = el.closest('label, [class*="form"], [class*="item"], [class*="cell"], td, th, div');
    if (!wrapper) return '';
    let depth = 0;
    for (let node = wrapper; node && node !== document.body && depth < 8; node = node.parentElement, depth += 1) {
      if (isDialogRoot(node)) break;
      const rect = node.getBoundingClientRect();
      if (rect.height > 240 && /modal-body|drawer-body|popup/i.test(String(node.className || ''))) break;
      if (rect.width <= 0 || rect.height <= 0 || rect.height > 180) continue;
      const labels = Array.from(node.querySelectorAll(labelSelectors)).filter(isVisible);
      const leafLabels = labels.filter(label => !labels.some(other => label !== other && label.contains(other)));
      if (leafLabels.length !== 1) continue;
      const labelNode = leafLabels[0];
      if (labelNode === el || (el.contains(labelNode) && node !== el)) continue;
      const text = normalize(labelNode.innerText || labelNode.textContent || '');
      if (text) return text;
    }
    return '';
  };
  const nodes = Array.from(
    document.querySelectorAll(
      '[fieldid], [data-fieldid], [uikey], input, textarea, select, button, [role="button"], [role="switch"], [role="checkbox"], [role="combobox"], [role="textbox"], [role="listbox"], [contenteditable="true"], [aria-label], [title], .ant-form-item, .wui-form-item, .u-form-item, [class*="form-item"], [class*="FormItem"], [class*="formItem"], .ant-select, .wui-select, .w-select, .u-select, [class*="select-selector"], [class*="SelectSelector"], .ant-checkbox, .wui-checkbox, .u-checkbox, [class*="checkbox"], [class*="Checkbox"]'
    )
  );
  const uiKeyRoots = Array.from(document.querySelectorAll('[uikey]'));
  const results = [];
  const isVisible = (el) => {
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
  };
  const cleanText = (el) => normalize(el.innerText || el.textContent || '');
  // Inline reference widgets and their trigger buttons are not dialog surfaces.
  const isInDialog = (el) => Boolean(el.closest(
    '.ant-modal, .ant-modal-confirm, .wui-modal, .wui-modal-confirm, .w-modal, .w-modal-confirm, .u-modal, .u-modal-confirm, [role="dialog"], [class*="modal"]:not(.modal-btn), [class*="Modal"]:not([class*="ModalSelect"]), [class*="drawer"], [class*="Drawer"], [class*="popup"], [class*="Popup"]'
  ));
  const isInTable = (el) => Boolean(el.closest(
    'table, .ant-table, .wui-table, .u-table, [role="table"], [role="grid"], [class*="table"]'
  ));
  const isDisabled = (el) => {
    if (!el || !(el instanceof HTMLElement)) return false;
    const className = String(el.className || '');
    return Boolean(el.disabled)
      || el.getAttribute('disabled') !== null
      || el.getAttribute('aria-disabled') === 'true'
      || /(^|[-_\\s])disabled($|[-_\\s])/i.test(className);
  };
  const isReadonly = (el) => {
    if (!el || !(el instanceof HTMLElement)) return false;
    const className = String(el.className || '');
    return el.getAttribute('readonly') !== null
      || el.getAttribute('aria-readonly') === 'true'
      || /(^|[-_\\s])readonly($|[-_\\s])/i.test(className);
  };
  const canEditControl = (el) => {
    if (!isVisible(el) || isDisabled(el)) return false;
    const tag = String(el.tagName || '').toLowerCase();
    const role = String(el.getAttribute('role') || '').toLowerCase();
    if (tag === 'input') {
      const type = String(el.getAttribute('type') || '').toLowerCase();
      if (['hidden', 'radio'].includes(type)) return false;
      if (type === 'checkbox') return true;
      return !isReadonly(el);
    }
    if (tag === 'textarea') return !isReadonly(el);
    if (tag === 'select') return true;
    if (el.isContentEditable || el.getAttribute('contenteditable') === 'true') return !isReadonly(el);
    if (role === 'textbox') return !isReadonly(el);
    if (role === 'combobox' || role === 'switch' || role === 'checkbox' || role === 'button') return true;
    const className = String(el.className || '');
    return /suffix|select|refer|ref|switch|checkbox/i.test(className);
  };
  const editableSelector = [
    'input:not([type="hidden"]):not([type="radio"])',
    'textarea',
    'select',
    '[contenteditable="true"]',
    '[role="textbox"]',
    '[role="combobox"]',
    '[role="switch"]',
    '[role="checkbox"]',
    'button',
    '[role="button"]',
    '[class*="suffix"]',
    '[class*="select"]',
    '[class*="refer"]',
    '[class*="ref"]',
    '[class*="switch"]',
    '[class*="Switch"]',
    '[class*="checkbox"]',
    '[class*="Checkbox"]',
  ].join(',');
  const hasEditableControl = (root) => {
    if (!root || !(root instanceof HTMLElement) || isDisabled(root)) return false;
    if (canEditControl(root)) return true;
    return Array.from(root.querySelectorAll(editableSelector)).some(canEditControl);
  };
  const hasReadonlyControl = (root) => {
    if (!root || !(root instanceof HTMLElement)) return false;
    const controls = Array.from(root.querySelectorAll('input:not([type="hidden"]), textarea, [role="textbox"], [contenteditable="true"]'));
    if (['input', 'textarea'].includes(String(root.tagName || '').toLowerCase()) || root.getAttribute('role') === 'textbox' || root.isContentEditable) {
      controls.unshift(root);
    }
    return controls.some((item) => isVisible(item) && isReadonly(item));
  };
  const receivesPointer = (el) => {
    if (!el || !isVisible(el) || isDisabled(el) || el.closest('[inert], [aria-hidden="true"]')) return false;
    const style = window.getComputedStyle(el);
    if (style.pointerEvents === 'none') return false;
    const rect = el.getBoundingClientRect();
    const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
    const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
    const visibleRect = {
      left: Math.max(0, rect.left), right: Math.min(viewportWidth, rect.right),
      top: Math.max(0, rect.top), bottom: Math.min(viewportHeight, rect.bottom)
    };
    const reachableRect = { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom };
    const clippingParent = (node) => /^(absolute|fixed)$/.test(window.getComputedStyle(node).position)
      ? node.offsetParent : node.parentElement;
    for (let parent = clippingParent(el); parent; parent = clippingParent(parent)) {
      const parentStyle = window.getComputedStyle(parent);
      if (/^(inline|contents)$/.test(parentStyle.display)) continue;
      if (!/^(auto|scroll|hidden|clip)$/.test(parentStyle.overflowX)
          && !/^(auto|scroll|hidden|clip)$/.test(parentStyle.overflowY)) continue;
      const parentRect = parent.getBoundingClientRect();
      // shortcut: 裁剪边界按轴对齐缩放换算，需支持旋转或斜切时改用多边形相交。
      const scaleX = parent.offsetWidth ? parentRect.width / parent.offsetWidth : 1;
      const scaleY = parent.offsetHeight ? parentRect.height / parent.offsetHeight : 1;
      const contentLeft = parentRect.left + parent.clientLeft * scaleX;
      const contentTop = parentRect.top + parent.clientTop * scaleY;
      for (const [overflow, low, high, start, end, scrollable] of [
        [parentStyle.overflowX, 'left', 'right', contentLeft, contentLeft + parent.clientWidth * scaleX, parent.scrollWidth > parent.clientWidth],
        [parentStyle.overflowY, 'top', 'bottom', contentTop, contentTop + parent.clientHeight * scaleY, parent.scrollHeight > parent.clientHeight]
      ]) {
        if (!/^(auto|scroll|hidden|clip)$/.test(overflow)) continue;
        if (end <= start) return false;
        if (scrollable && /^(auto|scroll)$/.test(overflow)) {
          reachableRect[low] = start;
          reachableRect[high] = end;
        } else {
          reachableRect[low] = Math.max(reachableRect[low], start);
          reachableRect[high] = Math.min(reachableRect[high], end);
          if (reachableRect[high] <= reachableRect[low]) return false;
        }
        visibleRect[low] = Math.max(visibleRect[low], start);
        visibleRect[high] = Math.min(visibleRect[high], end);
      }
    }
    const { left, right, top, bottom } = visibleRect;
    if (right <= left || bottom <= top) return null;
    const points = [
      [left + (right - left) / 2, top + (bottom - top) / 2],
      [left + Math.min(8, (right - left) / 2), top + Math.min(8, (bottom - top) / 2)]
    ];
    return points.some(([x, y]) => {
      const hit = document.elementFromPoint(x, y);
      return Boolean(hit && (hit === el || el.contains(hit) || hit.contains(el)));
    });
  };
  const cssEscapeSafe = (value) => {
    if (window.CSS && typeof window.CSS.escape === 'function') return window.CSS.escape(value);
    return String(value).replace(/"/g, '\\\\"');
  };
  let runtimeScanId = 0;
  const buildSelector = (el, containerFieldId, dataFieldId, uiKey) => {
    let semanticSelector = '';
    let directIdentity = false;
    if (containerFieldId) {
      semanticSelector = `[fieldid="${cssEscapeSafe(containerFieldId)}"]`;
      directIdentity = el.getAttribute('fieldid') === containerFieldId;
    } else if (dataFieldId) {
      semanticSelector = `[data-fieldid="${cssEscapeSafe(dataFieldId)}"]`;
      directIdentity = el.getAttribute('data-fieldid') === dataFieldId;
    } else if (uiKey) {
      semanticSelector = `[uikey="${cssEscapeSafe(uiKey)}"]`;
      directIdentity = el.getAttribute('uikey') === uiKey;
    } else if (el.id) {
      semanticSelector = `#${cssEscapeSafe(el.id)}`;
      directIdentity = true;
    } else if (el.name) {
      semanticSelector = `${el.tagName.toLowerCase()}[name="${cssEscapeSafe(el.name)}"]`;
      directIdentity = true;
    }
    let marker = el.getAttribute('data-ydf-browser-runtime-id');
    if (!marker) {
      runtimeScanId += 1;
      marker = `scan-${frameIndex}-${Date.now()}-${runtimeScanId}`;
      el.setAttribute('data-ydf-browser-runtime-id', marker);
    }
    const markerSelector = `[data-ydf-browser-runtime-id="${cssEscapeSafe(marker)}"]`;
    return semanticSelector
      ? `${semanticSelector}${directIdentity ? '' : ' '}${markerSelector}`
      : markerSelector;
  };
  for (const el of nodes) {
    const fieldContainer = el.closest('[fieldid]');
    const dataFieldContainer = el.closest('[data-fieldid]');
    const uiKeyContainer = el.closest('[uikey]');
    const rawFieldId = el.getAttribute('fieldid') || fieldContainer?.getAttribute('fieldid') || null;
    const dataFieldId = el.getAttribute('data-fieldid') || dataFieldContainer?.getAttribute('data-fieldid') || null;
    const uiKey = el.getAttribute('uikey') || uiKeyContainer?.getAttribute('uikey') || null;
    const fieldRoot = fieldContainer || dataFieldContainer || uiKeyContainer || el;
    const editable = !isDialogRoot(el)
      && hasEditableControl(el.matches('[fieldid], [data-fieldid], [uikey]') ? fieldRoot : el);
    const disabled = !editable && (isDisabled(fieldRoot) || isDisabled(el));
    const readonly = !editable && hasReadonlyControl(fieldRoot);
    const preferUiKey = Boolean(uiKey && (!rawFieldId || rawFieldId.endsWith('_drag') || /^20\\d+/.test(rawFieldId)));
    const fieldid = preferUiKey ? uiKey : rawFieldId;
    const directControl = canEditControl(el)
      || el.matches('select, button, [role="button"], [role="combobox"], [role="listbox"]');
    const selector = buildSelector(
      el,
      preferUiKey ? null : rawFieldId,
      preferUiKey ? null : dataFieldId,
      preferUiKey && !directControl ? uiKey : null,
    );
    results.push({
      fieldid: fieldid || uiKey,
      id: el.id || null,
      name: el.getAttribute('name'),
      placeholder: el.getAttribute('placeholder'),
      text: cleanText(el),
      label_text: findLabelText(el),
      aria_label: el.getAttribute('aria-label'),
      title_attr: el.getAttribute('title'),
      value: typeof el.value === 'string' ? normalize(el.value) : '',
      role: el.getAttribute('role'),
      class_name: typeof el.className === 'string' ? el.className : '',
      tag_name: el.tagName.toLowerCase(),
      visible: isVisible(el),
      in_dialog: isInDialog(el),
      in_table: isInTable(el),
      disabled,
      readonly,
      editable,
      pointer_receivable: receivesPointer(el),
      _identity_root_index: uiKeyContainer ? uiKeyRoots.indexOf(uiKeyContainer) : null,
      is_identity_root: el === uiKeyContainer,
      selector,
    });
  }
  return results;
}
"""


_FIELD_VALUE_FROM_ROOT_SCRIPT = """
(root, label) => {
  const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
  const inputs = Array.from(root.querySelectorAll('input:not([type="checkbox"]), textarea, select'));
  for (const input of inputs) {
    const value = normalize(input.value || input.getAttribute('title') || '');
    if (value && value !== label && value !== normalize(input.getAttribute('placeholder') || '')) return value;
  }
  const ownValue = normalize(root.value || root.getAttribute?.('title') || '');
  if (ownValue && ownValue !== label) return ownValue;
  const titled = Array.from(root.querySelectorAll('[title]'))
    .map((el) => normalize(el.getAttribute('title')))
    .find((value) => value && value !== label);
  if (titled) return titled;
  const labelNodes = Array.from(root.querySelectorAll('label, [class*="label"], [class*="Label"]'));
  const labelTexts = new Set(labelNodes.map((el) => normalize(el.innerText || el.textContent)).filter(Boolean));
  if (label) labelTexts.add(normalize(label));
  const directText = normalize(root.innerText || root.textContent);
  for (const item of labelTexts) {
    if (item && directText === item) return '';
  }
  let text = directText;
  for (const item of labelTexts) {
    if (item) text = normalize(text.replace(item, ''));
  }
  return text;
}
"""


_NOTIFICATION_CLOSE_SCRIPT = """
(args) => {
  const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const normalizeMessage = (value) => normalize(value).replace(/[!！。.;；,，]+$/g, '').replace(/\\s+/g, '');
  const rootSelectors = [
    '.ant-message-notice',
    '.ant-notification-notice',
    '.ant-modal-confirm',
    '.u-message-notice',
    '.u-notification-notice',
    '.u-modal-confirm',
    '.wui-message-notice',
    '.wui-notification-notice',
    '.wui-modal-confirm',
    '[role="alert"]',
    '[class*="message"][class*="notice"]',
    '[class*="notification"][class*="notice"]'
  ];
  const closeSelectors = [
    '.ant-notification-notice-close',
    '.ant-notification-notice-close-icon',
    '.ant-notification-close',
    '.ant-notification-close-x',
    '.ant-message-notice-close-icon',
    '.ant-message-notice-close',
    '.u-notification-notice-close',
    '.u-notification-notice-close-icon',
    '.u-notification-close',
    '.u-notification-close-x',
    '.u-message-notice-close-icon',
    '.u-message-notice-close',
    '.wui-notification-notice-close',
    '.wui-notification-notice-close-icon',
    '.wui-notification-close',
    '.wui-notification-close-x',
    '.wui-message-notice-close-icon',
    '.wui-message-notice-close',
    '[class*="notification-notice-close"]',
    '[class*="message-notice-close"]',
    '[class*="notice-close"]',
    '[aria-label="close"]',
    '[aria-label="Close"]',
    '[aria-label="关闭"]',
    '[title="关闭"]',
    'button[class*="close"]',
    '[role="button"][class*="close"]',
    '[class*="close-icon"]',
    '[class*="closeIcon"]'
  ];
  const defaultButtonLabels = ['关闭', '确定', '确认', '我知道了', 'OK'];
  const isVisible = (el) => {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
  };
  const typeFromClass = (el) => {
    const className = String(el && el.className || '').toLowerCase();
    const text = normalize(el && (el.innerText || el.textContent) || '');
    if (className.includes('error') || className.includes('danger') || className.includes('close-circle')) return 'error';
    if (className.includes('warn') || className.includes('exclamation')) return 'warning';
    if (className.includes('success') || className.includes('check-circle')) return 'success';
    const icon = el && el.querySelector && el.querySelector('[class*="error"], [class*="danger"], [class*="close-circle"]');
    if (icon) return 'error';
    if (/未通过|失败/.test(text)) return 'error';
    return 'info';
  };
  const itemFromRoot = (root) => ({
    root,
    type: typeFromClass(root),
    message: normalize(root.innerText || root.textContent || '')
  });
  const allItems = () => {
    const items = [];
    const seen = new Set();
    for (const selector of rootSelectors) {
      for (const root of document.querySelectorAll(selector)) {
        if (!isVisible(root)) continue;
        const item = itemFromRoot(root);
        if (!item.message) continue;
        const key = `${item.type}\\u0000${item.message}`;
        if (seen.has(key)) continue;
        seen.add(key);
        items.push(item);
      }
    }
    return items;
  };
  const matches = (item) => {
    const expectedType = normalize(args.expectedType || '');
    const contains = normalize(args.contains || '');
    const equals = normalize(args.equals || '');
    const message = normalize(args.message || '');
    if (expectedType && item.type !== expectedType) return false;
    if (contains && !item.message.includes(contains)) return false;
    if (equals && item.message !== equals) return false;
    if (message && normalizeMessage(item.message) !== normalizeMessage(message)) return false;
    return true;
  };
  const publicItems = (items) => items.map((item) => ({ type: item.type, message: item.message }));
  const findButtonByLabel = (root, labels) => {
    const controls = Array.from(root.querySelectorAll('button, [role="button"], a'));
    for (const label of labels) {
      const expected = normalize(label);
      if (!expected) continue;
      for (const control of controls) {
        if (!isVisible(control)) continue;
        const text = normalize(control.innerText || control.textContent || control.getAttribute('aria-label') || control.getAttribute('title') || '');
        if (text === expected || text.includes(expected)) {
          return control;
        }
      }
    }
    return null;
  };
  const findCloseControl = (root, explicitLabel) => {
    if (explicitLabel) {
      const explicit = findButtonByLabel(root, [explicitLabel]);
      if (explicit) return { element: explicit, action: `confirm-button:${explicitLabel}` };
    }
    for (const selector of closeSelectors) {
      for (const candidate of root.querySelectorAll(selector)) {
        if (isVisible(candidate)) {
          const clickable = candidate.closest('button, [role="button"], a, [aria-label], [title]') || candidate;
          return { element: clickable, action: `close-icon:${selector}` };
        }
      }
    }
    const button = findButtonByLabel(root, defaultButtonLabels);
    if (button) {
      const label = normalize(button.innerText || button.textContent || button.getAttribute('aria-label') || button.getAttribute('title') || '');
      return { element: button, action: `confirm-button:${label}` };
    }
    return null;
  };
  const markCloseControl = (element) => {
    const marker = `notification-close-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    element.setAttribute('data-ydf-browser-notification-close-target', marker);
    return `[data-ydf-browser-notification-close-target="${marker}"]`;
  };
  const items = allItems();
  const matched = items.find(matches);
  if (!matched) {
    return {
      closed: false,
      reason: 'not_found',
      actual_notifications: publicItems(items),
      diagnostic: `selectors=${rootSelectors.join(',')}`
    };
  }
  const explicitLabel = normalize(args.label || '');
  const close = findCloseControl(matched.root, explicitLabel);
  if (!close) {
    return {
      closed: false,
      reason: 'close_entry_missing',
      matched_notification: { type: matched.type, message: matched.message },
      actual_notifications: publicItems(items),
      diagnostic: `closeSelectors=${closeSelectors.join(',')}; labels=${[explicitLabel, ...defaultButtonLabels].filter(Boolean).join(',')}`
    };
  }
  const closeSelector = markCloseControl(close.element);
  return {
    closed: true,
    closed_notification: { type: matched.type, message: matched.message },
    remaining_notifications: [],
    close_selector: closeSelector,
    close_action: close.action
  };
}
"""


_NOTIFICATION_SCAN_SCRIPT = """
() => {
  const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const selectors = [
    '.ant-message-notice',
    '.ant-notification-notice',
    '.ant-modal-confirm',
    '.u-message-notice',
    '.u-notification-notice',
    '.u-modal-confirm',
    '.wui-message-notice',
    '.wui-notification-notice',
    '.wui-modal-confirm',
    '[role="alert"]',
    '[class*="message"][class*="notice"]',
    '[class*="notification"][class*="notice"]'
  ];
  const typeFromClass = (className) => {
    const value = String(className || '').toLowerCase();
    if (value.includes('error') || value.includes('danger')) return 'error';
    if (value.includes('warn')) return 'warning';
    if (value.includes('success')) return 'success';
    return 'info';
  };
  const isVisible = (el) => {
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
  };
  const items = [];
  for (const selector of selectors) {
    for (const el of document.querySelectorAll(selector)) {
      if (!isVisible(el)) continue;
      const message = normalize(el.innerText || el.textContent || '');
      if (!message) continue;
      items.push({ type: typeFromClass(el.className), message });
    }
  }
  return items;
}
"""


_WORKFLOW_RESULT_SCAN_SCRIPT = """
() => {
  const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
  const visible = (node) => {
    if (!node) return false;
    const style = window.getComputedStyle(node);
    const rect = node.getBoundingClientRect();
    return style && style.display !== 'none' && style.visibility !== 'hidden'
      && rect.width > 0 && rect.height > 0;
  };
  const textOf = (node) => normalize(node.innerText || node.textContent || '');
  const semanticPattern = /提交请求已执行完毕|部分失败|批量[^\\n]{0,30}(?:完成|失败)|(?:成功|失败)\\s*\\d+\\s*条/;
  const parseCount = (text, patterns) => {
    for (const pattern of patterns) {
      const match = text.match(pattern);
      if (match) return Number(match[1]);
    }
    return null;
  };
  const actionSelector = 'button, [role="button"], a, span';
  const findAction = (root, labels) => {
    for (const node of root.querySelectorAll(actionSelector)) {
      if (!visible(node)) continue;
      const text = normalize(node.innerText || node.textContent || node.getAttribute('aria-label') || node.getAttribute('title') || '');
      if (!labels.includes(text)) continue;
      return node;
    }
    return null;
  };
  const markerSelector = (node, prefix) => {
    const marker = `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    node.setAttribute(`data-ydf-browser-${prefix}-target`, marker);
    return `[data-ydf-browser-${prefix}-target="${marker}"]`;
  };
  const candidates = [];
  for (const node of Array.from(document.querySelectorAll('body *'))) {
    if (!visible(node)) continue;
    const text = textOf(node);
    if (!text || text.length > 1600 || !semanticPattern.test(text)) continue;
    const total = parseCount(text, [
      /(?:总数|总计|总条数|合计|共计|共)\\s*[:：]?\\s*(\\d+)/,
    ]);
    const succeeded = parseCount(text, [
      /(?:成功数|成功条数|成功)\\s*[:：]?\\s*(\\d+)/,
    ]);
    const failed = parseCount(text, [
      /(?:失败数|失败条数|失败)\\s*[:：]?\\s*(\\d+)/,
    ]);
    const confirm = findAction(node, ['确认', '确定']);
    const details = findAction(node, ['查看详情', '详情']);
    if (!confirm && !details && total == null && succeeded == null && failed == null) continue;
    const semantics = {
      message: text,
      title: normalize(node.querySelector('h1, h2, h3, [role="heading"]')?.innerText || ''),
    };
    const className = String(node.className || '').toLowerCase();
    const score = (className.includes('error-content') ? 4 : 0)
      + (className.includes('result') ? 2 : 0)
      + (confirm ? 1 : 0)
      + (details ? 1 : 0);
    const complete = [total, succeeded, failed].every((value) => Number.isInteger(value))
      && Boolean(confirm || details);
    candidates.push({
      status: complete ? 'observed' : 'evidence_unavailable',
      selector: markerSelector(node, 'workflow-result'),
      semantics,
      text,
      counts: complete ? { total, succeeded, failed } : {},
      actions: {
        confirm: confirm ? markerSelector(confirm, 'workflow-result-action') : '',
        details: details ? markerSelector(details, 'workflow-result-action') : '',
      },
      reason: complete ? '' : '结果层统计或操作入口无法可靠解析',
      _score: score,
      _text_length: text.length,
    });
  }
  candidates.sort((left, right) => (right._score - left._score) || (right._text_length - left._text_length));
  return candidates.slice(0, 3).map(({ _score, _text_length, ...item }) => item);
}
"""


_WORKFLOW_RESULT_DETAILS_SCAN_SCRIPT = """
() => {
  const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
  const visible = (node) => {
    if (!node) return false;
    const style = window.getComputedStyle(node);
    const rect = node.getBoundingClientRect();
    return style && style.display !== 'none' && style.visibility !== 'hidden'
      && rect.width > 0 && rect.height > 0;
  };
  const roots = Array.from(document.querySelectorAll(
    '[role="dialog"], .ant-modal, .ant-modal-wrap, .wui-modal, .w-modal, .u-modal, [class*="modal"], [class*="Modal"]'
  )).filter(visible);
  const details = [];
  for (const root of roots) {
    const rows = Array.from(root.querySelectorAll(
      'tbody tr, [role="row"], .ant-table-row, .wui-table-row, .w-table-row, .u-table-row'
    )).filter(visible);
    const headers = Array.from(root.querySelectorAll('thead th, [role="columnheader"], .ant-table-thead th'))
      .map((node) => normalize(node.innerText || node.textContent || ''));
    for (const row of rows) {
      const cells = Array.from(row.querySelectorAll('td, [role="gridcell"], [role="cell"]'))
        .map((node) => normalize(node.innerText || node.textContent || ''));
      if (!cells.length) continue;
      const item = {};
      cells.forEach((value, index) => {
        const header = headers[index] || `column_${index + 1}`;
        if (/单据|编码|单号|业务号/.test(header)) item.document_code = value;
        else if (/原因|失败信息|错误原因|说明/.test(header)) item.error_reason = value;
        else if (/错误码|编码/.test(header)) item.error_code = value;
        else item[header] = value;
      });
      details.push(item);
    }
    if (!details.length) {
      const text = normalize(root.innerText || root.textContent || '');
      const code = text.match(/(?:单据编码|单据号|单号)\\s*[:：]?\\s*([^\\s，,;；]+)/);
      const reason = text.match(/(?:错误原因|失败原因|失败信息|原因)\\s*[:：]?\\s*([^，,;；]+)/);
      const errorCode = text.match(/错误码\\s*[:：]?\\s*([^\\s，,;；]+)/);
      if (code || reason || errorCode) {
        details.push({
          ...(code ? { document_code: code[1] } : {}),
          ...(reason ? { error_reason: reason[1] } : {}),
          ...(errorCode ? { error_code: errorCode[1] } : {}),
        });
      }
    }
  }
  return details.length ? [{ status: 'observed', details }] : [];
}
"""

_NOTIFICATION_OBSERVER_INSTALL_SCRIPT = """
(options) => {
  const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const selectors = [
    '.ant-message-notice',
    '.ant-notification-notice',
    '.ant-modal-confirm',
    '.u-message-notice',
    '.u-notification-notice',
    '.u-modal-confirm',
    '.wui-message-notice',
    '.wui-notification-notice',
    '.wui-modal-confirm',
    '[role="alert"]',
    '[class*="message"][class*="notice"]',
    '[class*="notification"][class*="notice"]'
  ];
  const selectorText = selectors.join(',');
  const typeFromClass = (className) => {
    const value = String(className || '').toLowerCase();
    if (value.includes('error') || value.includes('danger')) return 'error';
    if (value.includes('warn')) return 'warning';
    if (value.includes('success')) return 'success';
    return 'info';
  };
  const isVisible = (el) => {
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
  };
  const ensureState = () => {
    if (!window.__ydfNotificationCapture) {
      window.__ydfNotificationCapture = { items: [], seen: Object.create(null), observer: null };
    }
    return window.__ydfNotificationCapture;
  };
  const state = ensureState();
  if (options && options.reset) {
    state.items = [];
    state.seen = Object.create(null);
    state.existing = new WeakMap();
    if (options.ignoreExisting) {
      for (const el of document.querySelectorAll(selectorText)) {
        if (isVisible(el)) state.existing.set(el, [typeFromClass(el.className), normalize(el.innerText || el.textContent || '')].join('\\u0000'));
      }
    }
  }
  const push = (el) => {
    if (!el || !isVisible(el)) return;
    const message = normalize(el.innerText || el.textContent || '');
    if (!message) return;
    const type = typeFromClass(el.className);
    const key = `${type}\\u0000${message}`;
    if (state.existing?.get(el) === key) return;
    if (state.seen[key]) return;
    state.seen[key] = true;
    state.items.push({ type, message });
  };
  const elementFromNode = (node) => {
    if (!node) return null;
    if (node.nodeType === Node.ELEMENT_NODE || node.nodeType === Node.DOCUMENT_NODE) return node;
    return node.parentElement || null;
  };
  const scanRoot = (node) => {
    const root = elementFromNode(node);
    if (!root) return;
    if (root.nodeType === Node.ELEMENT_NODE && root.matches && root.matches(selectorText)) {
      push(root);
    }
    if (root.querySelectorAll) {
      for (const el of root.querySelectorAll(selectorText)) push(el);
    }
  };
  if (!state.observer) {
    state.observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        scanRoot(mutation.target);
        for (const node of mutation.addedNodes || []) scanRoot(node);
      }
    });
    const target = document.documentElement || document.body;
    if (target) {
      state.observer.observe(target, {
        subtree: true,
        childList: true,
        characterData: true,
        attributes: true,
        attributeFilter: ['class', 'style']
      });
    }
  }
  return true;
}
"""

_NOTIFICATION_OBSERVER_DRAIN_SCRIPT = """
() => {
  const state = window.__ydfNotificationCapture;
  if (!state || !Array.isArray(state.items)) return [];
  const items = state.items.slice();
  state.items = [];
  return items;
}
"""

_TREE_SHORTCUT_TARGET_SCRIPT = """
(root, args) => {
  const mode = String(args && args.node || '').trim();
  const marker = String(args && args.marker || 'ydf-tree-shortcut-target');
  const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
  const visible = (el) => {
    if (!el || !el.ownerDocument || !el.isConnected) return false;
    const view = el.ownerDocument.defaultView;
    const style = view.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return Boolean(style)
      && style.visibility !== 'hidden'
      && style.display !== 'none'
      && rect.width > 0
      && rect.height > 0
      && rect.bottom >= 0
      && rect.right >= 0
      && rect.top <= (view.innerHeight || el.ownerDocument.documentElement.clientHeight || 0)
      && rect.left <= (view.innerWidth || el.ownerDocument.documentElement.clientWidth || 0);
  };
  const rootEl = root && root.querySelectorAll ? root : document.body;
  if (!rootEl) return { action: 'none', label: '', selector: '', reason: 'missing-root' };
  for (const old of Array.from(rootEl.querySelectorAll('[data-ydf-browser-tree-shortcut-target]'))) {
    old.removeAttribute('data-ydf-browser-tree-shortcut-target');
  }
  const treeSelector = [
    '.wui-tree',
    '.wui-select-tree',
    '.ant-tree',
    '.u-tree',
    '[role="tree"]',
    '[role="tree-node"]'
  ].join(',');
  const nodeSelector = [
    '.wui-tree-treenode',
    '.wui-select-tree-treenode',
    '.ant-tree-treenode',
    '.u-tree-treenode',
    '[role="treeitem"]',
    'li'
  ].join(',');
  const contentSelector = [
    '.wui-tree-title',
    '.wui-select-tree-title',
    '.ant-tree-title',
    '.u-tree-title',
    '.wui-tree-node-content-wrapper',
    '.wui-select-tree-node-content-wrapper',
    '.ant-tree-node-content-wrapper',
    '.u-tree-node-content-wrapper',
    '[class*="tree"][class*="title"]',
    '[class*="Tree"][class*="Title"]',
    '[class*="tree-node-content"]',
    '[class*="node-content"]',
    '[title]'
  ].join(',');
  const switcherSelector = [
    '.wui-tree-switcher',
    '.wui-select-tree-switcher',
    '.ant-tree-switcher',
    '.u-tree-switcher',
    '[class*="switcher"]',
    '[class*="Switcher"]',
    '[class*="expand"]',
    '[class*="Expand"]'
  ].join(',');
  const controlSelector = [
    'input[type="checkbox"]',
    'input[type="radio"]',
    '[role="checkbox"]',
    '[role="radio"]',
    '.wui-checkbox-wrapper',
    '.ant-checkbox-wrapper',
    '.u-checkbox-wrapper',
    '.wui-radio-wrapper',
    '.ant-radio-wrapper',
    '.u-radio-wrapper',
    '[class*="checkbox-wrapper"]',
    '[class*="CheckboxWrapper"]',
    '[class*="radio-wrapper"]',
    '[class*="RadioWrapper"]',
    '.wui-checkbox',
    '.ant-checkbox',
    '.u-checkbox',
    '.wui-radio',
    '.ant-radio',
    '.u-radio',
    '[class*="checkbox"]',
    '[class*="Checkbox"]',
    '[class*="radio"]',
    '[class*="Radio"]'
  ].join(',');
  const treeNodeFor = (el) => el && el.closest ? el.closest(nodeSelector) : null;
  const isDisabled = (el) => {
    if (!el) return true;
    const className = String(el.className || '').toLowerCase();
    return el.disabled === true
      || el.getAttribute('disabled') != null
      || el.getAttribute('aria-disabled') === 'true'
      || /disabled/.test(className);
  };
  const isTreeSwitcher = (el) => {
    const className = String(el && el.className || '').toLowerCase();
    return /switcher|expand|collapse/.test(className) && !/checkbox|radio/.test(className);
  };
  const selected = (el) => {
    if (!el) return false;
    const tag = String(el.tagName || '').toLowerCase();
    const type = String(el.getAttribute('type') || '').toLowerCase();
    if (tag === 'input' && (type === 'checkbox' || type === 'radio') && el.checked === true) return true;
    const aria = String(el.getAttribute && el.getAttribute('aria-checked') || '').toLowerCase();
    if (['true', '1', 'checked'].includes(aria)) return true;
    const className = String(el.className || '').toLowerCase();
    return /(^|[-_\\s])(checked|selected|active)([-_\\s]|$)/.test(className);
  };
  const controlScore = (el) => {
    const tag = String(el.tagName || '').toLowerCase();
    const type = String(el.getAttribute('type') || '').toLowerCase();
    const role = String(el.getAttribute('role') || '').toLowerCase();
    const className = String(el.className || '').toLowerCase();
    if (tag === 'input' && (type === 'checkbox' || type === 'radio')) return 0;
    if (role === 'checkbox' || role === 'radio') return 1;
    if (/checkbox-wrapper|radio-wrapper/.test(className)) return 2;
    if (/checkbox|radio/.test(className)) return 3;
    return 9;
  };
  const nearestVisibleClickTarget = (control, input) => {
    const candidates = [
      control,
      control.closest && control.closest('.wui-checkbox-wrapper, .ant-checkbox-wrapper, .u-checkbox-wrapper, .wui-radio-wrapper, .ant-radio-wrapper, .u-radio-wrapper, [class*="checkbox-wrapper"], [class*="CheckboxWrapper"], [class*="radio-wrapper"], [class*="RadioWrapper"], label'),
      input && input.closest && input.closest('label'),
      input && input.parentElement,
      control.parentElement,
    ].filter(Boolean);
    return candidates.find(visible) || input || control;
  };
  const directParentNode = (node, tree) => {
    for (let parent = node.parentElement; parent && parent !== tree; parent = parent.parentElement) {
      if (parent.matches && parent.matches(nodeSelector)) return parent;
    }
    return null;
  };
  const directNodeElements = (node, selector) => Array.from(node.querySelectorAll(selector))
    .filter((el) => visible(el) && treeNodeFor(el) === node);
  const nodeLabel = (node) => {
    const candidates = directNodeElements(node, contentSelector)
      .filter((el) => !isTreeSwitcher(el))
      .sort((a, b) => {
        const aClass = String(a.className || '').toLowerCase();
        const bClass = String(b.className || '').toLowerCase();
        const aRank = /title/.test(aClass) ? 0 : /content/.test(aClass) ? 1 : 2;
        const bRank = /title/.test(bClass) ? 0 : /content/.test(bClass) ? 1 : 2;
        return aRank - bRank;
      });
    for (const el of candidates) {
      const text = normalize(el.getAttribute('title') || el.innerText || el.textContent);
      if (text) return text;
    }
    return normalize(node.getAttribute('title') || node.innerText || node.textContent);
  };
  const contentClickTarget = (node) => directNodeElements(node, contentSelector)
    .filter((el) => !isTreeSwitcher(el))
    .find(visible) || node;
  const collapsedSwitcher = (node) => {
    const nodeClass = String(node.className || '').toLowerCase();
    if (/treenode-leaf|tree-node-leaf|node-leaf|is-leaf/.test(nodeClass)) return null;
    const candidates = directNodeElements(node, switcherSelector)
      .filter((el) => {
        if (isDisabled(el) || !isTreeSwitcher(el)) return false;
        const className = String(el.className || '').toLowerCase();
        return !/noop|switcher-noop|switcher_noop|is-leaf/.test(className);
      });
    for (const el of candidates) {
      const className = String(el.className || '').toLowerCase();
      const aria = String(el.getAttribute('aria-expanded') || '').toLowerCase();
      if (aria === 'false' || /close|closed|collapsed|center_close/.test(className)) return el;
    }
    if (/treenode-open|node-open|expanded/.test(nodeClass)) return null;
    if (/treenode-close|node-close|collapsed/.test(nodeClass)) return candidates[0] || null;
    return null;
  };
  const selectNode = (node) => {
    const label = nodeLabel(node);
    if (!label) return { action: 'none', label: '', selector: '', reason: 'empty-label' };
    const controls = directNodeElements(node, controlSelector)
      .filter((el) => !isDisabled(el) && !isTreeSwitcher(el))
      .sort((a, b) => controlScore(a) - controlScore(b));
    for (const control of controls) {
      const input = control.matches('input[type="checkbox"], input[type="radio"]')
        ? control
        : control.querySelector('input[type="checkbox"], input[type="radio"]');
      if (selected(control) || selected(input)) {
        return { action: 'already_selected', label, selector: '' };
      }
      const target = nearestVisibleClickTarget(control, input);
      if (!target) continue;
      target.setAttribute('data-ydf-browser-tree-shortcut-target', marker);
      return { action: 'select', label, selector: `[data-ydf-browser-tree-shortcut-target="${marker}"]` };
    }
    const target = contentClickTarget(node);
    target.setAttribute('data-ydf-browser-tree-shortcut-target', marker);
    return { action: 'select', label, selector: `[data-ydf-browser-tree-shortcut-target="${marker}"]` };
  };
  const pushUnique = (items, item) => {
    if (item && visible(item) && !items.includes(item)) items.push(item);
  };
  const trees = [];
  if (rootEl.matches && rootEl.matches(treeSelector)) pushUnique(trees, rootEl);
  for (const tree of Array.from(rootEl.querySelectorAll(treeSelector))) pushUnique(trees, tree);
  const searchRoots = trees.length ? trees : [rootEl];
  const nodesFor = (tree) => Array.from(tree.querySelectorAll(nodeSelector))
    .filter((node) => visible(node) && !isDisabled(node));
  if (mode === 'root') {
    for (const tree of searchRoots) {
      const roots = nodesFor(tree).filter((node) => !directParentNode(node, tree));
      if (roots.length) return selectNode(roots[0]);
    }
    return { action: 'none', label: '', selector: '', reason: 'empty-tree' };
  }
  if (mode === 'first_leaf') {
    for (const tree of searchRoots) {
      const nodes = nodesFor(tree);
      for (const node of nodes) {
        const switcher = collapsedSwitcher(node);
        if (switcher) {
          const label = nodeLabel(node);
          switcher.setAttribute('data-ydf-browser-tree-shortcut-target', marker);
          return { action: 'expand', label, selector: `[data-ydf-browser-tree-shortcut-target="${marker}"]` };
        }
        const child = nodes.find((other) => other !== node && directParentNode(other, tree) === node);
        if (child) continue;
        return selectNode(node);
      }
    }
    return { action: 'none', label: '', selector: '', reason: 'empty-tree' };
  }
  return { action: 'none', label: '', selector: '', reason: `unsupported-node:${mode}` };
}
"""

_TABLE_ROOT_FUNCTIONS = """
  const commonAncestor = (a, b) => {
    if (!a || !b) return a || b;
    const ancestors = new Set();
    let current = a;
    while (current) {
      ancestors.add(current);
      current = current.parentElement;
    }
    current = b;
    while (current) {
      if (ancestors.has(current)) return current;
      current = current.parentElement;
    }
    return a;
  };
  const horizontallyOverlaps = (a, b, tolerance = 24) =>
    a.right >= b.left - tolerance && b.right >= a.left - tolerance;
  const splitTableClusterRoot = (root) => {
    const headerSelector = '.wui-table-header, .ant-table-header, .u-table-header, .el-table__header, [class*="table-header"], [class*="TableHeader"]';
    const bodySelector = '.wui-table-body, .ant-table-body, .u-table-body, .el-table__body, [class*="table-body"], [class*="TableBody"]';
    const header = root && root.matches && root.matches(headerSelector)
      ? root
      : (root && root.querySelector ? root.querySelector(headerSelector) : null) || (root && root.closest ? root.closest(headerSelector) : null);
    const body = root && root.matches && root.matches(bodySelector)
      ? root
      : (root && root.querySelector ? root.querySelector(bodySelector) : null);
    if (header && body) return commonAncestor(header, body);
    if (body || !header) return root;
    const anchor = header || root;
    if (!anchor || !anchor.getBoundingClientRect) return root;
    const anchorRect = anchor.getBoundingClientRect();
    const bodies = Array.from(document.querySelectorAll(bodySelector))
      .filter(visible)
      .map((item) => ({ item, rect: item.getBoundingClientRect() }))
      .filter(({ rect }) => horizontallyOverlaps(anchorRect, rect) && rect.bottom >= anchorRect.top - 12)
      .sort((a, b) => Math.abs(a.rect.top - anchorRect.bottom) - Math.abs(b.rect.top - anchorRect.bottom));
    if (!bodies.length) return root;
    const cluster = commonAncestor(anchor, bodies[0].item);
    if (cluster === document.body || cluster === document.documentElement) return root;
    const identity = node => {
      const owner = node && node.closest('[fieldid], [data-fieldid], [data-field-id], [data-table-fieldid], [data-table-field-id]');
      return owner && (owner.getAttribute('fieldid') || owner.getAttribute('data-fieldid')
        || owner.getAttribute('data-field-id') || owner.getAttribute('data-table-fieldid') || owner.getAttribute('data-table-field-id'));
    };
    const rootIdentity = identity(root);
    const bodyIdentity = identity(bodies[0].item);
    if (rootIdentity && bodyIdentity && rootIdentity !== bodyIdentity) return root;
    return cluster;
  };
"""


_TABLE_SCOPE_VISIBILITY_FUNCTIONS = """
  const tableScopeVisible = (node) => {
    if (!node) return false;
    const styleOf = el => el.ownerDocument.defaultView.getComputedStyle(el);
    const style = styleOf(node);
    const rect = node.getBoundingClientRect();
    if (style.display === 'none' || style.visibility === 'hidden'
        || Number(style.opacity || 1) <= 0 || rect.width <= 0 || rect.height <= 0) return false;
    const bounds = { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom };
    const clippingParent = el => /^(absolute|fixed)$/.test(styleOf(el).position)
      ? el.offsetParent : el.parentElement;
    for (let parent = clippingParent(node); parent; parent = clippingParent(parent)) {
      const parentStyle = styleOf(parent);
      if (Number(parentStyle.opacity || 1) <= 0) return false;
      if (/^(inline|contents)$/.test(parentStyle.display)) continue;
      const parentRect = parent.getBoundingClientRect();
      const scaleX = parent.offsetWidth ? parentRect.width / parent.offsetWidth : 1;
      const scaleY = parent.offsetHeight ? parentRect.height / parent.offsetHeight : 1;
      const left = parentRect.left + parent.clientLeft * scaleX;
      const top = parentRect.top + parent.clientTop * scaleY;
      for (const [overflow, low, high, start, end, scrollable] of [
        [parentStyle.overflowX, 'left', 'right', left, left + parent.clientWidth * scaleX, parent.scrollWidth > parent.clientWidth],
        [parentStyle.overflowY, 'top', 'bottom', top, top + parent.clientHeight * scaleY, parent.scrollHeight > parent.clientHeight]
      ]) {
        if (!/^(auto|scroll|hidden|clip)$/.test(overflow)) continue;
        if (end <= start) return false;
        // 可滚动到的表格仍可操作，不能将暂时离开滚动视口当作永久裁剪。
        if (scrollable && /^(auto|scroll)$/.test(overflow)) {
          bounds[low] = start;
          bounds[high] = end;
        } else {
          bounds[low] = Math.max(bounds[low], start);
          bounds[high] = Math.min(bounds[high], end);
          if (bounds[high] <= bounds[low]) return false;
        }
      }
    }
    return true;
  };
"""


_TABLE_SCOPE_FOREGROUND_EXISTS_SCRIPT = """
() => {
  __TABLE_SCOPE_VISIBILITY_FUNCTIONS__
  const selector = [
    '[role="dialog"]', '[aria-modal="true"]',
    '.ant-modal', '.wui-modal', '.u-modal', '.yy-modal',
    '.ant-drawer', '.wui-drawer', '.u-drawer', '.yy-drawer',
    '[class*="modal"]', '[class*="Modal"]', '[class*="drawer"]', '[class*="Drawer"]'
  ].join(',');
  return Array.from(document.querySelectorAll(selector)).some(tableScopeVisible);
}
""".replace("__TABLE_SCOPE_VISIBILITY_FUNCTIONS__", _TABLE_SCOPE_VISIBILITY_FUNCTIONS)


_TABLE_SCOPE_REGION_EVIDENCE_SCRIPT = """
({ fieldid, token }) => {
  const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
  __TABLE_SCOPE_VISIBILITY_FUNCTIONS__
  const visible = (node) => {
    if (!node) return false;
    const style = getComputedStyle(node);
    const rect = node.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden'
      && Number(style.opacity || 1) > 0 && rect.width > 0 && rect.height > 0;
  };
  const matches = Array.from(document.querySelectorAll('[fieldid], [data-fieldid]')).filter(
    (candidate) => candidate.getAttribute('fieldid') === fieldid
      || candidate.getAttribute('data-fieldid') === fieldid
  );
  __TABLE_ROOT_FUNCTIONS__
  const roots = [];
  const appendRoot = (root) => {
    root = splitTableClusterRoot(root);
    if (root && !roots.includes(root)) roots.push(root);
  };
  for (const node of matches) {
    appendRoot(node.closest(
      '[role="grid"], table, .ant-table, .wui-table, .u-table, .yy-table, [class*="table"], [class*="Table"]'
    ));
    for (let ancestor = node; ancestor && ancestor !== document.body; ancestor = ancestor.parentElement) {
      if (/table/i.test(String(ancestor.className || ''))) appendRoot(ancestor);
    }
    if (!roots.length) appendRoot(node);
  }
  if (!roots.length) return [];
  const layerSelector = [
    '[role="dialog"]', '[aria-modal="true"]',
    '.ant-modal', '.wui-modal', '.u-modal', '.yy-modal',
    '.ant-drawer', '.wui-drawer', '.u-drawer', '.yy-drawer',
    '[class*="modal"]', '[class*="Modal"]', '[class*="drawer"]', '[class*="Drawer"]'
  ].join(',');
  const layers = Array.from(document.querySelectorAll(layerSelector)).filter(tableScopeVisible);
  return roots.map((root, index) => {
    const rect = root.getBoundingClientRect();
    const inForeground = layers.some((layer) => layer.contains(root));
    const style = getComputedStyle(root);
    const interactive = tableScopeVisible(root)
      && style.pointerEvents !== 'none'
      && !root.closest('[inert], [aria-hidden="true"]')
      && !root.matches('[disabled], [aria-disabled="true"]');
    const headerIdentityAttributes = [
      'data-field', 'data-index', 'data-data-index', 'data-key',
      'data-column-key', 'data-col-key', 'fieldid', 'data-fieldid', 'name'
    ];
    const headerOwner = (header) => {
      for (let node = header; node && node !== root; node = node.parentElement) {
        const structuralOwner = node.matches('th, [role="columnheader"]');
        const cellBoundary = structuralOwner || /cell/i.test(String(node.className || ''));
        const stableIdentity = headerIdentityAttributes.some(
          (name) => normalize(node.getAttribute && node.getAttribute(name))
        );
        if (cellBoundary && (structuralOwner || stableIdentity)) return node;
      }
      return header;
    };
    const seenHeaders = new Set();
    const headerNodes = Array.from(new Set(Array.from(root.querySelectorAll(
      'th, [role="columnheader"], .ant-table-thead [class*="cell"], .wui-table-header [class*="cell"]'
    )).filter(visible).map(headerOwner))).filter(visible);
    const headerEvidence = headerNodes.map((header) => {
      const text = normalize(header.innerText || header.textContent);
      const attribute = headerIdentityAttributes.find((name) => normalize(header.getAttribute(name)));
      const rect = header.getBoundingClientRect();
      const identity = attribute
        ? `${attribute}:${normalize(header.getAttribute(attribute))}`
        : `geometry:${Math.round(rect.left)}:${Math.round(rect.top)}:${Math.round(rect.width)}:${Math.round(rect.height)}`;
      return { text, key: attribute ? identity : `${text}|${identity}` };
    }).filter((header) => {
      if (!header.text || seenHeaders.has(header.key)) return false;
      seenHeaders.add(header.key);
      return true;
    });
    const headers = headerEvidence.map((header) => header.text);
    const rows = Array.from(root.querySelectorAll(
      'tbody tr, .ant-table-tbody tr, .wui-table-tbody tr, .u-table-tbody tr, [role="row"]'
    )).filter(visible).filter((row) => row.querySelector('td, [role="gridcell"], [role="cell"]'));
    const rowTexts = rows.map((row) => normalize(row.innerText || row.textContent)).filter(Boolean).slice(0, 10);
    const rootToken = `${token}-${index}`;
    const existingTokens = String(root.getAttribute('data-ydf-table-scope-token') || '').split(' ').filter(Boolean);
    root.setAttribute(
      'data-ydf-table-scope-token',
      Array.from(new Set([...existingTokens, rootToken])).join(' ')
    );
    return {
      exists: true,
      visible: tableScopeVisible(root),
      interactive,
      inForeground,
      columns: headers,
      columnHeaders: headerEvidence.map((header) => ({ text: header.text, identity: header.key })),
      rowCount: rows.length,
      rowTexts,
      area: Math.max(0, rect.width * rect.height),
      token: rootToken
    };
  });
}
""".replace("__TABLE_ROOT_FUNCTIONS__", _TABLE_ROOT_FUNCTIONS).replace(
    "__TABLE_SCOPE_VISIBILITY_FUNCTIONS__", _TABLE_SCOPE_VISIBILITY_FUNCTIONS,
)


_TABLE_SCOPE_ROOT_FUNCTIONS = """
  __TABLE_SCOPE_VISIBILITY_FUNCTIONS__
  const tableScopeRoot = (token, interactive = true) => {
    if (!token) return null;
    const roots = Array.from(document.querySelectorAll('[data-ydf-table-scope-token]'))
      .filter(node => String(node.getAttribute('data-ydf-table-scope-token') || '').split(' ').includes(token));
    if (roots.length !== 1) return null;
    const node = roots[0];
    const style = getComputedStyle(node);
    if (!tableScopeVisible(node)) return null;
    if (!interactive) return node;
    if (style.pointerEvents === 'none'
      || node.closest('[inert], [aria-hidden="true"]') || node.matches('[disabled], [aria-disabled="true"]')) return null;
    try {
      for (let subject = node; subject; subject = subject.ownerDocument.defaultView.frameElement) {
        if (!tableScopeVisible(subject) || subject.closest('[inert], [aria-hidden="true"]')) return null;
        const layers = Array.from(subject.ownerDocument.querySelectorAll(
          '[role="dialog"], [aria-modal="true"], .ant-modal, .wui-modal, .u-modal, .yy-modal, .ant-drawer, .wui-drawer, .u-drawer, .yy-drawer'
        )).filter(tableScopeVisible);
        if (layers.length && !layers.some(layer => layer.contains(subject))) return null;
      }
    } catch (_) { return null; }
    return node;
  };
""".replace("__TABLE_SCOPE_VISIBILITY_FUNCTIONS__", _TABLE_SCOPE_VISIBILITY_FUNCTIONS)


_TABLE_SCOPE_TOKEN_VALID_SCRIPT = """
(token) => {
  __TABLE_SCOPE_ROOT_FUNCTIONS__
  return Boolean(tableScopeRoot(token));
}
""".replace("__TABLE_SCOPE_ROOT_FUNCTIONS__", _TABLE_SCOPE_ROOT_FUNCTIONS)


_WORKFLOW_PANEL_SCAN_SCRIPT = r"""
({label, token}) => {
  const normalize = value => String(value || '').replace(/\s+/g, ' ').trim();
  const visible = el => {
    if (!el?.isConnected) return false;
    const rect = el.getBoundingClientRect();
    const style = el.ownerDocument.defaultView.getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
  };
  const reachable = el => {
    if (!visible(el)) return false;
    const r = el.getBoundingClientRect();
    return [[.5,.5],[.2,.5],[.8,.5]].some(([x,y]) => {
      const hit = el.ownerDocument.elementFromPoint(r.left+r.width*x, r.top+r.height*y);
      return hit && el.contains(hit);
    });
  };
  try {
    for (let win=window; win.frameElement; win=win.parent) {
      if (!reachable(win.frameElement)) return [];
    }
  } catch (_) { return []; }
  return [...document.querySelectorAll('#workflow-approve-component')].filter(visible).map((root, i) => {
    root.setAttribute('data-ydf-browser-workflow-panel', `${token}-${i}`);
    const actions = [...root.querySelectorAll('.approve-btns-container button, .approve-btns-container [role="button"], .approve-btns-container label, .approve-btns-container [role="radio"]')]
      .filter(el => !el.matches('label') || el.querySelector('input[type="radio"]'))
      .filter(el => !el.parentElement?.closest('button, [role="button"], label, [role="radio"]'))
      .map((el, j) => {
        const control = el.matches('label') ? el.querySelector('input[type="radio"]') : el;
        el.setAttribute('data-ydf-browser-workflow-action', `${token}-${i}-${j}`);
        return {
          label: normalize(el.innerText || el.textContent),
          kind: control?.type === 'radio' || el.getAttribute('role') === 'radio' ? 'radio' : 'button',
          selector: `[data-ydf-browser-workflow-action="${token}-${i}-${j}"]`,
          visible: visible(el),
          disabled: Boolean(control?.matches(':disabled, [aria-disabled="true"]')
            || el.closest('[inert], [aria-disabled="true"], .is-disabled, .wui-radio-button-disabled')),
          pointer_receivable: reachable(el),
          checked: Boolean(control?.checked || el.getAttribute('aria-checked') === 'true'),
        };
      });
    const matches = actions.filter(action => action.label === normalize(label) && action.visible);
    const action = matches.length === 1 ? matches[0] : null;
    return {
      status: matches.length > 1 ? 'ambiguous_action' : !action ? 'action_missing'
        : action.disabled || !action.pointer_receivable ? 'action_blocked' : 'ready',
      selector: `[data-ydf-browser-workflow-panel="${token}-${i}"]`,
      actions, action,
    };
  });
}
"""

_ACTION_SURFACE_OBSERVER_SCRIPT = """
(node, context) => {
  const doc = node.ownerDocument;
  const visible = el => {
    if (!el?.isConnected) return false;
    const rect = el.getBoundingClientRect();
    const style = el.ownerDocument.defaultView.getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
  };
  const reachable = el => {
    if (!visible(el) || el.disabled || el.getAttribute('aria-disabled') === 'true') return false;
    const rect = el.getBoundingClientRect();
    return [[.5, .5], [.2, .5], [.8, .5], [.5, .2], [.5, .8]].some(([x, y]) => {
      const hit = el.ownerDocument.elementFromPoint(rect.left + rect.width * x, rect.top + rect.height * y);
      return hit && el.contains(hit);
    });
  };
  const source = context?.workflow_panel ? node.closest('#workflow-approve-component')
    : node.closest('.yy-ydf-modal-holder') || node.closest(
    '.ant-modal-wrap, .ant-modal, .wui-modal, .u-modal, .yy-drawer-wrapper, .ant-drawer-content-wrapper, [role="dialog"], [role="alertdialog"]'
  );
  const returnRoot = context?.workflow_panel ? doc.body : source?.parentElement;
  const confirmationSelector = '.ac-confirm, .ant-modal-confirm, .wui-modal-confirm, .u-modal-confirm, [role="alertdialog"]'
    + (context?.workflow_panel ? ', [role="dialog"]:has([fieldid="approve_component_confirm_ok"])' : '');
  const confirmations = () => Array.from(doc.querySelectorAll(confirmationSelector)).filter(visible);
  const existingConfirmations = new Set(confirmations());
  const normalize = value => String(value || '').replace(/\\s+/g, '').trim();
  const action = normalize(context?.sub_label || context?.action || node.innerText);
  const popupSelector = '.yy-ydf-modal-holder, .ant-modal, .wui-modal, .u-modal, .yy-drawer-wrapper, [role="dialog"]';
  const popups = () => Array.from(doc.querySelectorAll(popupSelector)).filter(visible);
  const existingPopups = new Set(popups());
  const popupContent = root => {
    const busySelector = '[aria-busy="true"], .ant-spin-spinning, .wui-spin-spinning, .w-spin-spinning, .wui-spin-backdrop';
    if ((root.matches(busySelector) && visible(root))
        || Array.from(root.querySelectorAll(busySelector)).some(visible)) return {blocked: true, ready: false};
    const frames = Array.from(root.querySelectorAll('iframe')).filter(visible);
    const children = frames.map(frame => {
      try {
        const body = frame.contentDocument?.body;
        return body && reachable(frame) ? popupContent(body) : {blocked: true, ready: false};
      } catch (_) { return {blocked: true, ready: false}; }
    });
    const rows = Array.from(root.querySelectorAll('tbody tr, [role="row"], .wui-table-row, .ant-table-row, .u-table-row'));
    const candidates = rows.length ? rows : Array.from(root.querySelectorAll('[role="option"], [role="treeitem"]'));
    const ready = candidates.some(candidate => {
      if (!visible(candidate) || candidate.closest('thead, tfoot, [aria-disabled="true"], [inert]')) return false;
      const text = normalize(candidate.innerText || candidate.textContent);
      if (!text || /暂无数据|点击上方查询条件搜索数据|^(小计|合计|汇总|总计)/.test(text)) return false;
      const controls = Array.from(candidate.querySelectorAll('input[type="checkbox"], input[type="radio"], [role="checkbox"], [role="radio"]'));
      if (controls.length && controls.every(control => control.disabled || control.getAttribute('aria-disabled') === 'true')) return false;
      return reachable(candidate) || Array.from(candidate.querySelectorAll('td, [role="gridcell"], [role="cell"]')).some(reachable);
    });
    return {blocked: children.some(child => child.blocked), ready: ready || children.some(child => child.ready)};
  };
  const canClose = source && visible(source) && !source.matches(confirmationSelector)
    && !source.closest(confirmationSelector) && !source.querySelector(confirmationSelector);
  return () => {
    // A child document must not declare an actionable dialog behind its iframe's overlay.
    try {
      for (let win = doc.defaultView; win.frameElement; win = win.parent) {
        if (!reachable(win.frameElement)) return '';
      }
    } catch (_) { return ''; }
    const opened = confirmations().filter(dialog => !existingConfirmations.has(dialog));
    if (opened.length) {
      const ready = opened.length === 1 && Array.from(opened[0].querySelectorAll('button, [role="button"]'))
        .some(button => {
          const text = String(button.innerText || button.textContent || '').replace(/\\s+/g, '').trim();
          return (/^(确定|确认|是|继续)$/.test(text)
            || button.matches('.ant-btn-primary, .wui-button-primary, .u-button-primary'))
            && reachable(button);
        });
      return ready ? 'confirmation_required' : 'confirmation_pending';
    }
    if (canClose && (!source.isConnected || !visible(source)) && returnRoot?.isConnected
        && Array.from(returnRoot.querySelectorAll('button, input, textarea, select, [role="button"]')).some(reachable)) {
      return 'foreground_closed';
    }
    const newPopups = popups().filter(root => !existingPopups.has(root) && action
      && Array.from(root.querySelectorAll('.yy-ydf-modal-header, [class*="title"], [role="heading"], h1, h2, h3'))
        .some(title => visible(title) && normalize(title.textContent) === action));
    const openedPopups = newPopups.filter(root => !newPopups.some(other => other !== root && other.contains(root)));
    if (openedPopups.length) {
      if (openedPopups.length !== 1) return 'popup_reference_pending';
      const popup = openedPopups[0];
      const confirm = Array.from(popup.querySelectorAll('button, [role="button"]'))
        .some(button => /^(确定|确认)$/.test(normalize(button.innerText || button.textContent)) && reachable(button));
      const content = popupContent(popup);
      return confirm && !content.blocked && content.ready ? 'popup_reference_ready' : 'popup_reference_pending';
    }
    return '';
  };
}
"""

_EDITABLE_TABLE_ADD_ROW_SCRIPT = """
async ({ label, table, tableFieldid, tableRegionFieldid, tableColumns, tableScopeToken }) => {
  window.__ydfEditableTableAddRowDebug = null;
  const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
  const normalizeText = normalize;
  const normalizeCompact = (value) => String(value || '').replace(/\\s+/g, '').trim();
  const actionLabel = normalize(label);
  const actionLabelKey = normalizeCompact(actionLabel);
  const tableKey = normalizeCompact(table);
  const targetTableFieldid = normalizeCompact(tableFieldid);
  const targetTableScopeToken = normalizeCompact(tableScopeToken);
  const tableAddButtonIdentities = [...new Set([targetTableFieldid, normalizeCompact(tableRegionFieldid)].filter(Boolean))]
    .map(value => `${value}_add_button`);
  const targetTableColumns = Array.isArray(tableColumns) ? tableColumns.map(normalizeCompact).filter(Boolean) : [];
  const visible = (el) => {
    if (!el || !(el instanceof HTMLElement)) return false;
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
  };
  const tableSelector = '.ant-table, .wui-table, .u-table, [role="grid"], [role="table"], table, .ydf-table-placeholder, .ydf-table-placeholder-add, .ydf-table-placeholder-add-button, [class*="editable-table"], [class*="EditableTable"], [class*="table-placeholder"], [class*="TablePlaceholder"]';
  const realTableSelector = '.ant-table, .wui-table, .u-table, [role="grid"], [role="table"], table';
  const rowSelector = 'tbody tr, .ant-table-tbody tr, .wui-table-tbody tr, .u-table-tbody tr, .ant-table-row, .wui-table-row, .u-table-row, [role="row"]';
  const tableLevelActionSelector = 'thead, tfoot, .ant-table-thead, .wui-table-thead, .u-table-thead, .ant-table-header, .wui-table-header, .u-table-header, .ant-table-footer, .wui-table-footer, .u-table-footer, .ydf-table-placeholder, .ydf-table-placeholder-add, .ydf-table-placeholder-add-button, [class*="table-header"], [class*="TableHeader"], [class*="table-footer"], [class*="TableFooter"], [class*="table-placeholder"], [class*="TablePlaceholder"], [class*="table-toolbar"], [class*="TableToolbar"]';
  const tableRoot = (el) => el.closest(tableSelector);
  const clickableRoot = (el) => el.closest('button, a, [role="button"], .ant-btn, .wui-button, .u-button, [class*="link"], [class*="Link"]') || el;
  __TABLE_ROOT_FUNCTIONS__
  const tableIdentityAttributeNames = ['fieldid', 'data-fieldid', 'data-field-id', 'data-table-fieldid', 'data-table-field-id', 'name', 'id'];
  const identityAttributeNames = ['fieldid', 'data-fieldid', 'data-field-id', 'data-field', 'data-index', 'data-data-index', 'data-key', 'data-column-key', 'data-col-key', 'name', 'id'];
  const identitySelectorForValue = (value) => identityAttributeNames.map((name) => `[${name}="${CSS.escape(value)}"]`).join(',');
  const tableIdentitySelectorForValue = (value) => tableIdentityAttributeNames.map((name) => `[${name}="${CSS.escape(value)}"]`).join(',');
  __TABLE_SCOPE_ROOT_FUNCTIONS__
  const resolvedTableScopeRoot = () => tableScopeRoot(targetTableScopeToken, false);
  const tableIdentityMatchesValue = (value) => {
    value = normalizeCompact(value);
    return Boolean(targetTableFieldid && (value === targetTableFieldid || value === `${targetTableFieldid}_table`));
  };
  const targetTableIdentitySelector = () => {
    if (!targetTableFieldid) return '';
    return [targetTableFieldid, `${targetTableFieldid}_table`]
      .map(tableIdentitySelectorForValue)
      .join(',');
  };
  const anchorIdentityRoot = (identityRoot, anchor) => {
    const clusterRoot = splitTableClusterRoot(identityRoot);
    if (!anchor || !clusterRoot) return clusterRoot;
    if (clusterRoot.contains(anchor) || anchor.contains(clusterRoot)) return clusterRoot;
    return null;
  };
  const rootHasOwnIdentity = (root) => {
    if (!targetTableFieldid || !root) return false;
    if (tableIdentityAttributeNames.some((name) => tableIdentityMatchesValue(root.getAttribute(name)))) return true;
    return false;
  };
  const rootMatchesIdentity = (root) => {
    return rootHasOwnIdentity(root);
  };
  const identityElementRoot = (identityEl) => {
    if (!identityEl) return null;
    return rootHasOwnIdentity(identityEl) ? identityEl : (
      tableRoot(identityEl) || identityEl.closest('[class*="table"], [class*="Table"]') || identityEl
    );
  };
  const closestIdentityTableRoot = (root, anchor = null) => {
    if (!targetTableFieldid || !root || !root.querySelector) return null;
    const selector = targetTableIdentitySelector();
    const identityEl = selector ? root.querySelector(selector) : null;
    if (!identityEl) return null;
    const identityRoot = identityElementRoot(identityEl);
    return anchorIdentityRoot(identityRoot, anchor);
  };
  let targetIdentityAmbiguous = false;
  const globalTargetIdentityRoot = (anchor = null) => {
    targetIdentityAmbiguous = false;
    const selector = targetTableIdentitySelector();
    if (!selector) return null;
    const anchoredRoots = [];
    const fallbackRoots = [];
    for (const identityEl of Array.from(document.querySelectorAll(selector))) {
      if (!visible(identityEl) && !identityEl.querySelector) continue;
      const identityRoot = identityElementRoot(identityEl);
      const anchored = anchorIdentityRoot(identityRoot, anchor);
      if (anchored && visible(anchored) && !anchoredRoots.includes(anchored)) {
        anchoredRoots.push(anchored);
      }
      if (!anchor || !anchor.isConnected) {
        const unanchored = anchorIdentityRoot(identityRoot, null);
        if (unanchored && visible(unanchored) && !fallbackRoots.includes(unanchored)) {
          fallbackRoots.push(unanchored);
        }
      }
    }
    if (anchoredRoots.length === 1) return anchoredRoots[0];
    if (anchoredRoots.length > 1) {
      targetIdentityAmbiguous = true;
      return null;
    }
    if (anchor && anchor.isConnected) return null;
    if (fallbackRoots.length > 1) {
      targetIdentityAmbiguous = true;
      return null;
    }
    return fallbackRoots.length === 1 ? fallbackRoots[0] : null;
  };
  const actionTextMatches = (value) => {
    const text = normalize(value);
    if (text === actionLabel) return true;
    const withoutIcon = normalize(text.replace(/^[\\s+＋]+/, ''));
    return withoutIcon === actionLabel || (actionLabelKey && normalizeCompact(withoutIcon) === actionLabelKey);
  };
  const tableTextMatches = (value) => {
    if (!table) return true;
    const text = normalizeText(value);
    return text.includes(table) || (tableKey && normalizeCompact(value).includes(tableKey));
  };
  const nearbyTableLabels = (root) => {
    if (!root) return [];
    const rootRect = root.getBoundingClientRect();
    const labels = Array.from(document.querySelectorAll('span, div, label, h1, h2, h3, h4'))
      .filter(visible)
      .map((el) => ({ el, rect: el.getBoundingClientRect(), text: normalizeText(el.innerText || el.textContent) }))
      .filter((item) => item.text && item.text !== actionLabel && item.text.length <= 80)
      .filter((item) => item.rect.bottom <= rootRect.top + 8 && rootRect.top - item.rect.bottom <= 320)
      .sort((a, b) => (rootRect.top - a.rect.bottom) - (rootRect.top - b.rect.bottom));
    const seen = new Set();
    const result = [];
    for (const item of labels) {
      if (seen.has(item.text)) continue;
      seen.add(item.text);
      result.push(item.text);
      if (result.length >= 6) break;
    }
    return result;
  };
  const columnIdentityScore = (root) => {
    if (!targetTableColumns.length || !root) return 0;
    const text = normalizeCompact(root.innerText || root.textContent);
    const matched = targetTableColumns.filter((column) => text.includes(column)).length;
    return matched ? Math.min(500, matched * 160) : 0;
  };
  const tableLabelScore = (root) => {
    if (!table) return 0;
    if (!root) return -1000;
    if (rootMatchesIdentity(root)) return 1400;
    let score = -1000;
    let distance = 0;
    for (let node = root; node && node !== document.body; node = node.parentElement) {
      if (rootMatchesIdentity(node)) {
        score = Math.max(score, 1400 - distance);
      }
      const tableRootCount = node.querySelectorAll ? node.querySelectorAll(tableSelector).length : 0;
      if (normalizeText(node.innerText || node.textContent).includes(table)) {
        score = Math.max(score, (tableRootCount > 1 ? 250 : 1000) - distance);
      }
      if (tableTextMatches(node.innerText || node.textContent)) {
        score = Math.max(score, (tableRootCount > 1 ? 250 : 1000) - distance);
      }
      distance += 1;
    }
    const rootRect = root.getBoundingClientRect();
    const labels = Array.from(document.querySelectorAll('span, div, label, h1, h2, h3, h4'))
      .filter(visible)
      .filter((el) => tableTextMatches(el.innerText || el.textContent));
    for (const labelEl of labels) {
      const rect = labelEl.getBoundingClientRect();
      if (rect.bottom <= rootRect.top + 8) {
        const verticalDistance = rootRect.top - rect.bottom;
        score = Math.max(score, 600 - Math.min(600, verticalDistance));
      }
    }
    score = Math.max(score, columnIdentityScore(root));
    return score;
  };
  const rowState = (root) => {
    if (!root) return { rowCount: 0, rowTexts: [], empty: false };
    const rows = Array.from(root.querySelectorAll(rowSelector))
      .filter(visible)
      .filter((row) => !row.closest('thead, .ant-table-thead, .wui-table-thead, .u-table-thead, .ant-table-header, .wui-table-header, .u-table-header, [class*="table-header"], [class*="TableHeader"]'));
    const rowTexts = rows.map((row) => normalizeText(row.innerText || row.textContent)).filter(Boolean).slice(0, 10);
    const emptyRowPattern = /暂无数据|暂时没有数据|点击上方查询条件搜索数据/;
    const summaryRowPattern = /^小计(?:\\s|$)|^合计(?:\\s|$)/;
    const dataRows = rowTexts.filter((text) => !emptyRowPattern.test(text) && !summaryRowPattern.test(text));
    return { rowCount: rows.length, rowTexts, dataRowCount: dataRows.length, empty: rows.length > 0 && dataRows.length === 0 };
  };
  const hasTargetTableScope = Boolean(targetTableFieldid || targetTableColumns.length);
  const placeholderRoot = (root) => Boolean(
    root && root.matches && root.matches('.ydf-table-placeholder, .ydf-table-placeholder-add, .ydf-table-placeholder-add-button, [class*="table-placeholder"], [class*="TablePlaceholder"]')
  );
  const targetValidationRootFor = (root) => {
    if (!root) return root;
    const resolvedScopeRoot = resolvedTableScopeRoot();
    if (resolvedScopeRoot) return resolvedScopeRoot;
    const globalIdentityRoot = globalTargetIdentityRoot(root);
    if (targetIdentityAmbiguous) return null;
    if (globalIdentityRoot && visible(globalIdentityRoot)) return globalIdentityRoot;
    for (let node = root; node && node !== document.body; node = node.parentElement) {
      if (!visible(node)) continue;
      if (rootMatchesIdentity(node)) return splitTableClusterRoot(node);
    }
    for (let node = root; node && node !== document.body; node = node.parentElement) {
      if (!visible(node)) continue;
      const identityRoot = closestIdentityTableRoot(node, root);
      if (identityRoot && visible(identityRoot)) return identityRoot;
    }
    for (let node = root; node && node !== document.body; node = node.parentElement) {
      if (!visible(node)) continue;
      if (columnIdentityScore(node) > 0) return splitTableClusterRoot(node);
    }
    return root;
  };
  const targetValidationRootResolutionFor = (root) => {
    if (!root) return { root, reliable: false, source: 'missing-root' };
    const resolvedScopeRoot = resolvedTableScopeRoot();
    if (resolvedScopeRoot) {
      return { root: resolvedScopeRoot, reliable: true, source: 'resolved-table-scope' };
    }
    if (targetTableScopeToken) {
      return { root: null, reliable: false, source: 'resolved-table-scope-stale' };
    }
    const globalIdentityRoot = globalTargetIdentityRoot(root);
    if (targetIdentityAmbiguous) {
      return { root, reliable: false, source: 'target-identity-ambiguous' };
    }
    if (globalIdentityRoot && visible(globalIdentityRoot)) {
      return { root: globalIdentityRoot, reliable: true, source: 'target-global-identity' };
    }
    for (let node = root; node && node !== document.body; node = node.parentElement) {
      if (!visible(node)) continue;
      if (rootMatchesIdentity(node)) {
        return { root: splitTableClusterRoot(node), reliable: true, source: 'target-identity' };
      }
    }
    for (let node = root; node && node !== document.body; node = node.parentElement) {
      if (!visible(node)) continue;
      const identityRoot = closestIdentityTableRoot(node, root);
      if (identityRoot && visible(identityRoot)) {
        return { root: identityRoot, reliable: true, source: 'target-descendant-identity' };
      }
    }
    for (let node = root; node && node !== document.body; node = node.parentElement) {
      if (!visible(node)) continue;
      if (columnIdentityScore(node) > 0) {
        const columnRoot = anchorIdentityRoot(node, root);
        if (columnRoot && visible(columnRoot)) {
          return { root: columnRoot, reliable: true, source: 'target-column-identity' };
        }
      }
    }
    return { root, reliable: false, source: placeholderRoot(root) ? 'placeholder-unresolved' : 'target-unresolved' };
  };
  const broadValidationRootFor = (root) => {
    let best = root;
    let bestScore = -1;
    for (let node = root; node && node !== document.body; node = node.parentElement) {
      if (!visible(node)) continue;
      const state = rowState(node);
      const score = state.rowCount + columnIdentityScore(node);
      if (score > bestScore) {
        best = node;
        bestScore = score;
      }
      if (state.dataRowCount > 0 && columnIdentityScore(node) > 0) break;
    }
    return best;
  };
  const validationRootFor = (root) => {
    return hasTargetTableScope ? targetValidationRootFor(root) : broadValidationRootFor(root);
  };
  const validationRootResolutionFor = (root) => {
    if (hasTargetTableScope) return targetValidationRootResolutionFor(root);
    return { root: broadValidationRootFor(root), reliable: Boolean(root), source: 'broad' };
  };
  const validationRootDiagnostic = (resolution) => {
    const root = resolution ? resolution.root : null;
    return root ? {
      text: normalizeText(root.innerText || root.textContent).slice(0, 240),
      className: String(root.className || '').slice(0, 160),
      source: resolution.source || '',
      reliable: Boolean(resolution.reliable)
    } : null;
  };
  const foregroundRoots = () => Array.from(document.querySelectorAll(
    '.yy-ydf-modal-holder, .yy-drawer-wrapper, .ant-modal, .wui-modal, .u-modal, [role="dialog"]'
  )).filter(visible);
  const foregroundBefore = new Set(foregroundRoots());
  let foregroundOpened = false;
  let latestValidationRootResolution = null;
  const waitForRowStateChange = async (previousResolution, previousState, anchor) => {
    let lastResolution = validationRootResolutionFor(anchor);
    let lastState = rowState(lastResolution.root);
    latestValidationRootResolution = lastResolution;
    for (let attempt = 0; attempt < 8; attempt += 1) {
      foregroundOpened = foregroundRoots().some(root => !foregroundBefore.has(root)
        && Array.from(root.querySelectorAll('input, textarea, select, button, [role="button"]'))
          .some(control => {
            if (!visible(control) || control.disabled || control.readOnly) return false;
            const rect = control.getBoundingClientRect();
            const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
            return hit && control.contains(hit);
          }));
      if (foregroundOpened) return lastState;
      await new Promise((resolve) => setTimeout(resolve, 250));
      const nextResolution = validationRootResolutionFor(anchor);
      const nextState = rowState(nextResolution.root);
      lastResolution = nextResolution;
      lastState = nextState;
      latestValidationRootResolution = nextResolution;
      const reliable = Boolean(previousResolution.reliable && nextResolution.reliable);
      if (reliable && (
        nextState.dataRowCount > previousState.dataRowCount ||
        nextState.rowCount > previousState.rowCount ||
        (previousState.empty && !nextState.empty && nextState.dataRowCount > 0)
      )) {
        return nextState;
      }
    }
    return lastState;
  };
  const fieldidAddButtonCandidates = tableAddButtonIdentities.length
    ? Array.from(document.querySelectorAll(tableAddButtonIdentities.map(identitySelectorForValue).join(',')))
      .filter(visible)
      .map((el) => clickableRoot(el))
      .filter(visible)
    : [];
  const candidateSources = new Map();
  for (const el of fieldidAddButtonCandidates) {
    candidateSources.set(el, 'table-fieldid-add-button');
  }
  const labelCandidates = Array.from(document.querySelectorAll('button, a, [role="button"], span, div'))
    .filter(visible)
    .map((el) => clickableRoot(el))
    .filter((el, index, arr) => arr.indexOf(el) === index)
    .filter(visible)
    .filter((el) => actionTextMatches(el.innerText || el.textContent));
  const candidates = [...fieldidAddButtonCandidates, ...labelCandidates]
    .filter((el, index, arr) => arr.indexOf(el) === index);
  const debug = { label, table, tableFieldid, tableColumns: targetTableColumns, candidates: [], scored: [] };
  if (targetTableScopeToken && !tableScopeRoot(targetTableScopeToken)) {
    debug.failure = 'add-row-scope-stale';
    window.__ydfEditableTableAddRowDebug = debug;
    return null;
  }
  const scored = [];
  for (const el of candidates) {
    if (targetTableScopeToken && !resolvedTableScopeRoot().contains(el)
      && !(fieldidAddButtonCandidates.length === 1 && fieldidAddButtonCandidates[0] === el)) continue;
    const rect = el.getBoundingClientRect();
    const rawText = normalize(el.innerText || el.textContent);
    const root = tableRoot(el);
    const rootClassName = root ? String(root.className || '') : '';
    const source = candidateSources.get(el) || 'label-text';
    const item = {
      text: rawText,
      source,
      tag: String(el.tagName || '').toLowerCase(),
      className: String(el.className || '').slice(0, 160),
      x: Math.round(rect.x),
      y: Math.round(rect.y),
      width: Math.round(rect.width),
      height: Math.round(rect.height),
      hasRoot: Boolean(root),
      rootClassName: rootClassName.slice(0, 160),
      rootText: root ? normalize(root.innerText || root.textContent).slice(0, 240) : '',
      nearbyLabels: root ? nearbyTableLabels(root) : []
    };
    debug.candidates.push(item);
    const rowScope = el.closest(rowSelector);
    const tableLevelAction = Boolean(el.closest(tableLevelActionSelector));
    const placeholderAction = Boolean(el.closest('.ydf-table-placeholder, .ydf-table-placeholder-add, .ydf-table-placeholder-add-button, [class*="table-placeholder"], [class*="TablePlaceholder"]'));
    const rootState = rowState(root);
    const tableBodyAction = Boolean(root && rootState.dataRowCount > 0 && !placeholderAction && normalizeText(root.innerText || root.textContent) !== rawText);
    const stickyTableBodyAction = Boolean(root && /wui-table-sticky|ant-table-sticky|el-table__fixed|table-sticky|TableSticky|table-fixed|TableFixed/.test(rootClassName) && !placeholderAction && normalizeText(root.innerText || root.textContent) !== rawText);
    const rowScopedAction = rowScope && !tableLevelAction;
    item.tableLevelAction = tableLevelAction;
    item.rowScopedAction = Boolean(rowScopedAction);
    item.tableBodyAction = Boolean(tableBodyAction && !tableLevelAction);
    item.stickyTableBodyAction = Boolean(stickyTableBodyAction);
    if (source !== 'table-fieldid-add-button' && (stickyTableBodyAction || rowScopedAction || (tableBodyAction && !tableLevelAction))) {
      item.skipped = 'row-scoped-action';
      continue;
    }
    if (rect.y < 70 || rect.width > 420 || rect.height > 120) {
      item.skipped = 'outside-action-size-or-top-nav';
      continue;
    }
    const labelScore = tableLabelScore(root);
    item.labelScore = labelScore;
    if (table && labelScore < 0 && !(targetTableScopeToken && source === 'table-fieldid-add-button')) {
      item.skipped = 'table-label-mismatch';
      continue;
    }
    let score = 0;
    if (source === 'table-fieldid-add-button') score += 5000;
    if (root) score += 100;
    score += labelScore;
    if (el.closest('tfoot, .ant-table-footer, .wui-table-footer, .u-table-footer, [class*="footer"], [class*="Footer"]')) score += 50;
    score += Math.min(40, Math.max(0, rect.y / 25));
    item.score = score;
    debug.scored.push(item);
    scored.push({ el, root, score, rect, item });
  }
  scored.sort((a, b) => b.score - a.score);
  const chosen = scored[0];
  if (!chosen) {
    window.__ydfEditableTableAddRowDebug = debug;
    return null;
  }
  const validationRootBefore = validationRootResolutionFor(chosen.root);
  if (validationRootBefore.source === 'resolved-table-scope-stale') {
    debug.failure = 'add-row-scope-stale';
    debug.validationRootBefore = validationRootDiagnostic(validationRootBefore);
    debug.chosenCandidate = chosen.item;
    window.__ydfEditableTableAddRowDebug = debug;
    return null;
  }
  const stateBefore = rowState(validationRootBefore.root);
  chosen.el.click();
  const state = await waitForRowStateChange(validationRootBefore, stateBefore, chosen.root);
  const validationRoot = latestValidationRootResolution || validationRootResolutionFor(chosen.root);
  const rowStateReliable = Boolean(validationRootBefore.reliable && validationRoot.reliable);
  const rowStateChanged = rowStateReliable && (state.dataRowCount > stateBefore.dataRowCount || state.rowCount > stateBefore.rowCount);
  if (state.empty || (hasTargetTableScope && state.dataRowCount === 0) || (table && targetTableColumns.length && state.rowCount === 0)) {
    debug.failure = 'add-row-no-data-row';
    debug.rowStateBefore = stateBefore;
    debug.rowState = state;
    debug.validationRootBefore = validationRootDiagnostic(validationRootBefore);
    debug.validationRoot = validationRootDiagnostic(validationRoot);
    window.__ydfEditableTableAddRowDebug = debug;
  }
  return {
    label,
    table: table || null,
    table_fieldid: tableFieldid || '',
    row_state_before: stateBefore,
    row_state: state,
    row_state_changed: rowStateChanged,
    row_state_reliable: rowStateReliable,
    foreground_opened: foregroundOpened,
    validation_root_source: validationRoot.source || '',
    validation_root_before_source: validationRootBefore.source || '',
    validation_root: validationRootDiagnostic(validationRoot),
    validation_root_before: validationRootDiagnostic(validationRootBefore),
    chosen_candidate: chosen.item || null,
    top_candidates: scored.slice(0, 5).map((entry) => entry.item).filter(Boolean),
    selector: '',
    x: Math.round(chosen.rect.x),
    y: Math.round(chosen.rect.y)
  };
}
""".replace("__TABLE_SCOPE_ROOT_FUNCTIONS__", _TABLE_SCOPE_ROOT_FUNCTIONS).replace("__TABLE_ROOT_FUNCTIONS__", _TABLE_ROOT_FUNCTIONS)

_EDITABLE_TABLE_CELL_SELECTOR_SCRIPT = """
({ column, rowNumber, table, columnFieldid, columnKey, dataField, tableFieldid, tableScopeToken, elementType, componentName, displayFields, columnGroups }) => {
  __TABLE_SCOPE_ROOT_FUNCTIONS__
  window.__ydfEditableTableCellDebug = null;
  const normalize = (value) => String(value || '').replace(/\\s+/g, '').trim();
  const normalizeHeader = (value) => normalize(String(value || '').replace(/^[\\s*＊✱✳※]+/, ''));
  const normalizeText = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
  const identityValue = (value) => String(value || '').trim();
  const tableSelector = '.ant-table, .wui-table, .u-table, [role="grid"], [role="table"], table';
  const headerSelector = 'th, [role="columnheader"], .ant-table-cell, .wui-table-cell, .u-table-cell';
  const rowSelector = 'tbody tr, .ant-table-tbody tr, .wui-table-tbody tr, .u-table-tbody tr, .ant-table-row, .wui-table-row, .u-table-row, [role="row"]';
  const cellSelector = 'td, [role="gridcell"], [role="cell"], .ant-table-cell, .wui-table-cell, .u-table-cell';
  const identityAttributeNames = [
    'fieldid',
    'data-fieldid',
    'data-field-id',
    'data-field',
    'data-index',
    'data-data-index',
    'data-key',
    'data-column-key',
    'data-col-key',
    'name',
    'id',
    'key'
  ];
  const strongIdentityAttributeNames = [
    'fieldid',
    'data-fieldid',
    'data-field-id',
    'data-field',
    'data-index',
    'data-data-index',
    'data-key',
    'data-column-key',
    'data-col-key',
    'name'
  ];
  const targetIdentity = {
    columnFieldid: identityValue(columnFieldid),
    columnKey: identityValue(columnKey),
    dataField: identityValue(dataField),
    tableFieldid: identityValue(tableFieldid),
    elementType: identityValue(elementType),
    componentName: identityValue(componentName),
    displayFields: Array.isArray(displayFields) ? displayFields.map(identityValue).filter(Boolean) : [],
    columnGroups: Array.isArray(columnGroups) ? columnGroups.map(identityValue).filter(Boolean) : []
  };
  const targetValues = [targetIdentity.columnFieldid, targetIdentity.columnKey, targetIdentity.dataField, ...targetIdentity.displayFields].filter(Boolean);
  const hasTargetIdentity = targetValues.length > 0;
  const platformCellFieldid = targetIdentity.columnFieldid && Number.isInteger(rowNumber) && rowNumber > 0
    ? `${targetIdentity.columnFieldid}_${rowNumber - 1}`
    : '';
  const platformCellFieldidPrefix = targetIdentity.columnFieldid
    ? `${targetIdentity.columnFieldid}_`
    : '';
  const visible = (el) => {
    if (!el || !(el instanceof HTMLElement)) return false;
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
  };
  const wanted = normalize(column);
  const debug = { column, rowNumber, table, wanted, targetIdentity, matchingHeaders: [], candidates: [] };
  const asciiUnitSuffixMatch = (text, wanted) => {
    if (!text || !wanted || !wanted.startsWith(text)) return false;
    const suffix = wanted.slice(text.length);
    return /^\\([^()（）]+\\)$/.test(suffix);
  };
  const headerMatchScore = (text) => {
    if (text === wanted) return 100;
    if (text.includes(wanted)) return 80;
    if (asciiUnitSuffixMatch(text, wanted)) return 40;
    return -1;
  };
  const columnGroupsMatch = (expected, actual) => {
    const left = Array.isArray(expected) ? expected.map(normalizeHeader).filter(Boolean) : [];
    const right = Array.isArray(actual) ? actual.map(normalizeHeader).filter(Boolean) : [];
    if (!left.length) return true;
    if (left.length !== right.length) return false;
    return left.every((value, index) => value === right[index]);
  };
  const isHeaderCell = (el) => {
    const tag = String(el.tagName || '').toLowerCase();
    return tag === 'th'
      || el.getAttribute('role') === 'columnheader'
      || Boolean(el.closest('thead, .ant-table-thead, .wui-table-thead, .u-table-thead, .ant-table-header, .wui-table-header, .u-table-header, [class*="table-header"], [class*="TableHeader"]'));
  };
  const tableRoot = (el) => {
    const direct = el.closest(tableSelector);
    if (direct) return direct;
    const headerRoot = el.closest('.ant-table-header, .wui-table-header, .u-table-header, [class*="table-header"], [class*="TableHeader"]');
    if (headerRoot && headerRoot.parentElement) return headerRoot.parentElement;
    return el.closest('[class*="table"], [class*="Table"]');
  };
  const directCells = (row, selector) => {
    const children = Array.from(row.children || []).filter((el) => visible(el) && el.matches && el.matches(selector));
    if (children.length) return children;
    return Array.from(row.querySelectorAll(selector)).filter(visible);
  };
  const identityValues = (el, names = identityAttributeNames) => {
    if (!el || !(el instanceof Element)) return [];
    const values = [];
    for (const name of names) {
      const value = identityValue(el.getAttribute(name));
      if (value) values.push(value);
    }
    return Array.from(new Set(values));
  };
  const ownOrDescendantIdentityValues = (el, names = identityAttributeNames) => {
    const values = identityValues(el, names);
    if (el && el.querySelectorAll) {
      for (const child of Array.from(el.querySelectorAll('*'))) {
        values.push(...identityValues(child, names));
      }
    }
    return Array.from(new Set(values));
  };
  const identityMatches = (el) => {
    if (!hasTargetIdentity) return false;
    return ownOrDescendantIdentityValues(el).some((value) =>
      targetValues.includes(value)
      || value === platformCellFieldid
      || (platformCellFieldidPrefix && value.startsWith(platformCellFieldidPrefix))
    );
  };
  const identityMatchScore = (el) => {
    if (!hasTargetIdentity) return -1;
    const values = ownOrDescendantIdentityValues(el);
    if (targetIdentity.columnFieldid && values.includes(targetIdentity.columnFieldid)) return 300;
    if (targetIdentity.dataField && values.includes(targetIdentity.dataField)) return 260;
    if (targetIdentity.columnKey && values.includes(targetIdentity.columnKey)) return 220;
    return -1;
  };
  const identityObject = (el) => {
    if (!el || !(el instanceof Element)) return {};
    const first = (...names) => {
      for (const name of names) {
        const value = identityValue(el.getAttribute(name));
        if (value) return value;
      }
      return '';
    };
    return {
      fieldid: first('fieldid', 'data-fieldid', 'data-field-id'),
      data_field: first('data-field', 'data-index', 'data-data-index'),
      key: first('data-key', 'data-column-key', 'data-col-key', 'key'),
      name: first('name'),
      id: first('id')
    };
  };
  const mergedActualIdentity = (cell, header) => {
    const cellIdentity = identityObject(cell);
    const headerIdentity = identityObject(header);
    return {
      fieldid: cellIdentity.fieldid || headerIdentity.fieldid || '',
      data_field: cellIdentity.data_field || headerIdentity.data_field || '',
      key: cellIdentity.key || headerIdentity.key || '',
      name: cellIdentity.name || headerIdentity.name || '',
      id: cellIdentity.id || headerIdentity.id || '',
      cell: cellIdentity,
      header: headerIdentity
    };
  };
  const identityConflict = (cell, header, actualIdentity) => {
    if (!hasTargetIdentity) return null;
    let actualValues = ownOrDescendantIdentityValues(cell, strongIdentityAttributeNames);
    if (!actualValues.length && header) {
      actualValues = ownOrDescendantIdentityValues(header, strongIdentityAttributeNames);
    }
    actualValues = actualValues.filter(Boolean);
    if (!actualValues.length) return null;
    if (actualValues.some((value) =>
      targetValues.includes(value)
      || value === platformCellFieldid
      || (platformCellFieldidPrefix && value.startsWith(platformCellFieldidPrefix))
    )) return null;
    return { targetIdentity, actualIdentity, actualValues };
  };
  const markResult = (cell, source, header = null, candidateDebug = null) => {
    const actualIdentity = mergedActualIdentity(cell, header);
    const conflict = identityConflict(cell, header, actualIdentity);
    const result = {
      selector: '',
      locator_source: source,
      source,
      targetIdentity,
      actualIdentity,
      actual_fieldid: actualIdentity.fieldid || '',
      actual_data_field: actualIdentity.data_field || ''
    };
    if (candidateDebug && candidateDebug.tableScope) {
      result.tableScope = candidateDebug.tableScope;
    }
    if (candidateDebug && Array.isArray(candidateDebug.columnGroups) && candidateDebug.columnGroups.length) {
      result.columnGroups = candidateDebug.columnGroups;
    }
    if (conflict) {
      result.identityConflict = conflict;
      return result;
    }
    const marker = `ydf-cell-${Date.now()}-${Math.floor(Math.random() * 100000)}`;
    document.querySelectorAll('[data-ydf-browser-cell-target]').forEach((el) => el.removeAttribute('data-ydf-browser-cell-target'));
    cell.setAttribute('data-ydf-browser-cell-target', marker);
    result.selector = `[data-ydf-browser-cell-target="${CSS.escape(marker)}"]`;
    if (candidateDebug) {
      candidateDebug.locatorSource = source;
      candidateDebug.actualIdentity = actualIdentity;
    }
    return result;
  };
  const identitySelectorForValue = (value) => {
    const escaped = CSS.escape(value);
    return identityAttributeNames.map((name) => `[${name}="${escaped}"]`).join(',');
  };
  const rootSortScore = (root, source = '') => {
    if (!root || !(root instanceof HTMLElement)) return -10000;
    const rect = root.getBoundingClientRect();
    const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 0;
    const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
    const intersectsViewport = rect.width > 0 && rect.height > 0
      && rect.right > 0 && rect.bottom > 0
      && rect.left < viewportWidth && rect.top < viewportHeight;
    let score = 0;
    if (source === 'target-table-fieldid') score += 1200;
    if (root.matches && root.matches(tableSelector)) score += 500;
    if (intersectsViewport) score += 300;
    const labelScore = tableLabelScore(root);
    if (labelScore > -1000) score += labelScore;
    const centerX = Math.max(rect.left + 1, Math.min(rect.left + rect.width / 2, viewportWidth - 1));
    const centerY = Math.max(rect.top + 1, Math.min(rect.top + rect.height / 2, viewportHeight - 1));
    const topElement = viewportWidth && viewportHeight ? document.elementFromPoint(centerX, centerY) : null;
    if (topElement && (topElement === root || root.contains(topElement))) score += 250;
    if (root.closest('.ant-modal, .wui-modal, .u-modal, .w-modal, .yy-modal, [role="dialog"], [class*="drawer"], [class*="Drawer"]')) score += 200;
    const area = Math.max(1, rect.width * rect.height);
    score -= Math.min(120, Math.floor(area / 50000));
    return score;
  };
  const tableScopeFor = (root, source, row = null, rowIndex = null, rootScore = null) => ({
    table,
    tableFieldid: targetIdentity.tableFieldid,
    rootSource: source || '',
    rootScore: rootScore === null ? rootSortScore(root, source) : rootScore,
    rootClassName: String(root && (root.className || root.tagName) || '').slice(0, 160),
    rootText: normalizeText(root ? root.innerText || root.textContent : '').slice(0, 300),
    rowIndex,
    rowText: row ? normalizeText(row.innerText || row.textContent).slice(0, 800) : ''
  });
  const targetTableRootCandidates = () => {
    const items = [];
    const appendRoot = (node, source) => {
      if (!node || !(node instanceof HTMLElement)) return;
      const roots = [];
      const direct = tableRoot(node) || node.closest('[class*="table"], [class*="Table"]') || node;
      if (direct) roots.push(direct);
      if (!direct || !direct.matches || !direct.matches(tableSelector)) {
        roots.push(...Array.from(node.querySelectorAll(tableSelector)).filter(visible));
      }
      for (const root of roots) {
        if (!root || !visible(root)) continue;
        if (items.some((item) => item.root === root)) continue;
        const score = rootSortScore(root, source);
        items.push({ root, source, score, tableScope: tableScopeFor(root, source, null, null, score) });
      }
    };
    if (tableScopeToken) {
      const tokenRoot = tableScopeRoot(tableScopeToken);
      appendRoot(tokenRoot, 'resolved-table-scope');
      return items;
    }
    if (targetIdentity.tableFieldid) {
      for (const node of Array.from(document.querySelectorAll(identitySelectorForValue(targetIdentity.tableFieldid)))) {
        appendRoot(node, 'target-table-fieldid');
      }
    }
    if (!items.length) {
      for (const root of Array.from(document.querySelectorAll(tableSelector)).filter(visible)) {
        if (!table || tableLabelScore(root) > -1000) appendRoot(root, 'table-label');
      }
    }
    if (!items.length) appendRoot(document.body, 'document-body');
    items.sort((a, b) => (b.score - a.score));
    return items;
  };
  const isSummaryRow = (row) => {
    const rowText = normalizeText(row.innerText || row.textContent);
    const compactRowText = normalize(rowText);
    const className = String(row.className || '');
    if (/(summary|footer|total|subtotal)/i.test(className)) return true;
    if (/^(小计|合计|汇总|总计)(\\s|$)/.test(rowText) || /^(小计|合计|汇总|总计)/.test(compactRowText)) return true;
    const cells = directCells(row, cellSelector);
    const firstCellText = normalizeText(cells[0] ? cells[0].innerText || cells[0].textContent : '');
    const firstCompactText = normalize(firstCellText);
    return /^(小计|合计|汇总|总计)(\\s|$)/.test(firstCellText) || /^(小计|合计|汇总|总计)$/.test(firstCompactText);
  };
  const tableLabelScore = (root) => {
    if (!table) return 0;
    let score = -1000;
    let distance = 0;
    for (let node = root; node && node !== document.body; node = node.parentElement) {
      if (normalizeText(node.innerText || node.textContent).includes(table)) {
        score = 1000 - distance;
        break;
      }
      distance += 1;
    }
    const rootRect = root.getBoundingClientRect();
    const labels = Array.from(document.querySelectorAll('span, div, label, h1, h2, h3, h4'))
      .filter(visible)
      .filter((el) => normalizeText(el.innerText || el.textContent).includes(table));
    for (const label of labels) {
      const rect = label.getBoundingClientRect();
      if (rect.bottom <= rootRect.top + 8) {
        const verticalDistance = rootRect.top - rect.bottom;
        score = Math.max(score, 600 - Math.min(600, verticalDistance));
      }
    }
    return score;
  };
  const cellForHeader = (cells, header, fallbackIndex) => {
    const headerKeys = [
      header.getAttribute('fieldid'),
      header.getAttribute('data-fieldid'),
      header.getAttribute('data-field-id'),
      header.getAttribute('data-index'),
      header.getAttribute('data-field'),
      header.getAttribute('data-data-index'),
      header.getAttribute('data-key'),
      header.getAttribute('data-column-key')
    ].filter(Boolean);
    for (const key of headerKeys) {
      const matched = cells.find((cell) =>
        cell.getAttribute('fieldid') === key
        || cell.getAttribute('data-fieldid') === key
        || cell.getAttribute('data-field-id') === key
        || cell.getAttribute('data-index') === key
        || cell.getAttribute('data-field') === key
        || cell.getAttribute('data-data-index') === key
        || cell.getAttribute('data-key') === key
        || cell.getAttribute('data-column-key') === key
        || ownOrDescendantIdentityValues(cell).includes(key)
      );
      if (matched) return matched;
    }

    const headerRect = header.getBoundingClientRect();
    const headerCenterX = headerRect.left + headerRect.width / 2;
    const positioned = cells
      .map((cell, index) => ({ cell, index, rect: cell.getBoundingClientRect() }))
      .filter((item) => item.rect.width > 0 && item.rect.height > 0);
    const byDistance = (a, b) => {
      const aCenter = a.rect.left + a.rect.width / 2;
      const bCenter = b.rect.left + b.rect.width / 2;
      return Math.abs(aCenter - headerCenterX) - Math.abs(bCenter - headerCenterX);
    };
    const containing = positioned.filter((item) =>
      item.rect.left - 2 <= headerCenterX && item.rect.right + 2 >= headerCenterX
    );
    if (containing.length) return containing.sort(byDistance)[0].cell;

    const overlapping = positioned.filter((item) => {
      const overlap = Math.min(item.rect.right, headerRect.right) - Math.max(item.rect.left, headerRect.left);
      return overlap > Math.min(item.rect.width, headerRect.width) * 0.45;
    });
    if (overlapping.length) return overlapping.sort(byDistance)[0].cell;

    return fallbackIndex >= 0 && fallbackIndex < cells.length ? cells[fallbackIndex] : null;
  };
  const headerGroupPath = (header, root, allHeaders) => {
    if (!header || !root) return [];
    const headerRect = header.getBoundingClientRect();
    const centerX = headerRect.left + headerRect.width / 2;
    return Array.from(allHeaders || [])
      .filter((candidate) => candidate !== header && root.contains(candidate) && visible(candidate))
      .map((candidate) => {
        const rect = candidate.getBoundingClientRect();
        const text = normalizeHeader(candidate.innerText || candidate.textContent || candidate.getAttribute('title'));
        return { candidate, rect, text };
      })
      .filter((item) => item.text)
      .filter((item) => item.rect.bottom <= headerRect.top + 4)
      .filter((item) => item.rect.left - 2 <= centerX && item.rect.right + 2 >= centerX)
      .sort((a, b) => (a.rect.top - b.rect.top) || (a.rect.left - b.rect.left))
      .map((item) => item.text);
  };
  const rowCandidatesForRoot = (root) => {
    let rows = Array.from(root.querySelectorAll(rowSelector))
        .filter(visible)
        .filter((row) => !row.closest('thead, .ant-table-thead, .wui-table-thead, .u-table-thead, .ant-table-header, .wui-table-header, .u-table-header, [class*="table-header"], [class*="TableHeader"]'))
        .filter((row) => row.querySelector('td, [role="gridcell"], [role="cell"], .ant-table-cell, .wui-table-cell, .u-table-cell'));
    return rows.filter((row) => !isSummaryRow(row));
  };
  const targetRoots = targetTableRootCandidates();
  if (tableScopeToken && !targetRoots.length) {
    debug.candidates.push({ matched: false, skipped: 'missing-scope-token' });
    window.__ydfEditableTableCellDebug = debug;
    return { selector: '', locator_source: '', targetIdentity };
  }
  if (hasTargetIdentity) {
    for (const item of targetRoots) {
      const root = item.root;
      if (item.source === 'document-body' && (table || targetIdentity.tableFieldid)) {
        debug.candidates.push({
          locatorSource: 'identity-cell',
          rootSource: item.source,
          matched: false,
          skipped: 'document-body-identity-scope-disabled',
          tableScope: item.tableScope
        });
        continue;
      }
      const rows = rowCandidatesForRoot(root);
      const rowIndex = rowNumber === -1 ? rows.length - 1 : rowNumber - 1;
      if (rowIndex < 0 || rowIndex >= rows.length) {
        debug.candidates.push({
          locatorSource: 'identity-cell',
          rootClassName: String(root.className || root.tagName || '').slice(0, 160),
          rootSource: item.source,
          rootScore: item.score,
          rowCount: rows.length,
          rowIndex,
          matched: false,
          skipped: 'missing-row-in-target-root',
          tableScope: item.tableScope
        });
        continue;
      }
      const cells = directCells(rows[rowIndex], cellSelector);
      const identityCell = cells.find(identityMatches);
      const tableScope = tableScopeFor(root, item.source, rows[rowIndex], rowIndex, item.score);
      debug.candidates.push({
        locatorSource: 'identity-cell',
        rootClassName: String(root.className || root.tagName || '').slice(0, 160),
        rootSource: item.source,
        rootScore: item.score,
        rowCount: rows.length,
        rowIndex,
        rowText: normalizeText(rows[rowIndex].innerText || rows[rowIndex].textContent).slice(0, 800),
        cellCount: cells.length,
        matched: Boolean(identityCell),
        tableScope
      });
      if (identityCell) return markResult(identityCell, 'identity-cell', null, { tableScope });
    }
  }
  const headerSearchRoots = targetRoots.map((item) => item.root).filter(Boolean);
  const headerElements = [];
  for (const root of headerSearchRoots.length ? headerSearchRoots : [document]) {
    for (const header of Array.from(root.querySelectorAll(headerSelector))) {
      if (!headerElements.includes(header)) headerElements.push(header);
    }
  }
  const headers = headerElements
    .filter(visible)
    .filter(isHeaderCell);
  const candidates = [];
  for (const header of headers) {
    const text = normalizeHeader(header.innerText || header.textContent || header.getAttribute('title'));
    const matchScore = headerMatchScore(text);
    const identityScore = identityMatchScore(header);
    if (identityScore < 0 && matchScore < 0) continue;
    debug.matchingHeaders.push({
      text,
      identityScore,
      matchScore,
      raw: normalizeText(header.innerText || header.textContent || header.getAttribute('title')),
      className: String(header.className || '').slice(0, 160),
      identityValues: ownOrDescendantIdentityValues(header).slice(0, 20)
    });
    const headerRow = header.closest('tr, .ant-table-row, .wui-table-row, .u-table-row, [role="row"]') || header.parentElement;
    const root = tableRoot(header);
    const candidateDebug = {
      text,
      identityScore,
      hasHeaderRow: Boolean(headerRow),
      hasRoot: Boolean(root),
      rootClassName: root ? String(root.className || '').slice(0, 160) : '',
      rootText: root ? normalizeText(root.innerText || root.textContent).slice(0, 240) : ''
    };
    if (!headerRow || !root || !visible(root)) {
      candidateDebug.skipped = 'missing-header-row-or-root';
      debug.candidates.push(candidateDebug);
      continue;
    }
    const siblings = directCells(headerRow, headerSelector);
    const columnIndex = siblings.findIndex((cell) => cell === header || cell.contains(header));
    candidateDebug.siblingTexts = siblings.map((cell) => normalizeText(cell.innerText || cell.textContent)).slice(0, 20);
    candidateDebug.columnIndex = columnIndex;
    if (columnIndex < 0) {
      candidateDebug.skipped = 'missing-column-index';
      debug.candidates.push(candidateDebug);
      continue;
    }
    const score = tableLabelScore(root);
    candidateDebug.score = score;
    candidateDebug.matchScore = matchScore;
    const columnGroups = headerGroupPath(header, root, headers);
    candidateDebug.columnGroups = columnGroups;
    if (!columnGroupsMatch(targetIdentity.columnGroups, columnGroups)) {
      candidateDebug.skipped = 'column-group-mismatch';
      debug.candidates.push(candidateDebug);
      continue;
    }
    debug.candidates.push(candidateDebug);
    candidates.push({ header, root, columnIndex, score, identityScore, matchScore, debug: candidateDebug });
  }
  candidates.sort((a, b) => (b.identityScore - a.identityScore) || (b.matchScore - a.matchScore) || (b.score - a.score));
  for (const candidate of candidates) {
    const rowRoots = [];
    for (let node = candidate.root; node && node !== document.body && rowRoots.length < 6; node = node.parentElement) {
      if (!rowRoots.includes(node) && visible(node)) rowRoots.push(node);
    }
    const headerRect = candidate.header.getBoundingClientRect();
    candidate.debug.rowRoots = rowRoots.map((root) => String(root.className || root.tagName || '').slice(0, 120));
    for (const rowRoot of rowRoots) {
      let rows = Array.from(rowRoot.querySelectorAll(rowSelector))
        .filter(visible)
        .filter((row) => !row.closest('thead, .ant-table-thead, .wui-table-thead, .u-table-thead, .ant-table-header, .wui-table-header, .u-table-header, [class*="table-header"], [class*="TableHeader"]'))
        .filter((row) => row.getBoundingClientRect().top >= headerRect.bottom - 4)
        .filter((row) => row.querySelector('td, [role="gridcell"], [role="cell"], .ant-table-cell, .wui-table-cell, .u-table-cell'));
      const rowCountBeforeSummaryFilter = rows.length;
      rows = rows.filter((row) => !isSummaryRow(row));
      candidate.debug.rowCount = rows.length;
      candidate.debug.summaryRowCount = rowCountBeforeSummaryFilter - rows.length;
      candidate.debug.rowTexts = rows.map((row) => normalizeText(row.innerText || row.textContent)).slice(0, 10);
      if (!rows.length) continue;
      const rowIndex = rowNumber === -1 ? rows.length - 1 : rowNumber - 1;
      candidate.debug.rowIndex = rowIndex;
      if (rowIndex < 0 || rowIndex >= rows.length) continue;
      const cells = directCells(rows[rowIndex], cellSelector);
      candidate.debug.tableScope = tableScopeFor(rowRoot, 'header-geometry', rows[rowIndex], rowIndex, candidate.score);
      candidate.debug.cellCount = cells.length;
      candidate.debug.cellTexts = cells.map((cell) => normalizeText(cell.innerText || cell.textContent)).slice(0, 20);
      let cell = null;
      let locatorSource = 'text-geometry';
      if (candidate.identityScore >= 0) {
        cell = cells.find(identityMatches) || cellForHeader(cells, candidate.header, candidate.columnIndex);
        locatorSource = cells.find(identityMatches) ? 'identity-cell' : 'identity-header-geometry';
      } else {
        cell = cellForHeader(cells, candidate.header, candidate.columnIndex);
        if (targetIdentity.columnGroups.length) locatorSource = 'column-group-geometry';
      }
      candidate.debug.selectedCellIndex = cells.indexOf(cell);
      if (!cell) {
        candidate.debug.skipped = 'missing-cell-for-header';
        continue;
      }
      return markResult(cell, locatorSource, candidate.header, candidate.debug);
    }
  }
  window.__ydfEditableTableCellDebug = debug;
  return { selector: '', locator_source: '', targetIdentity };
}
""".replace("__TABLE_SCOPE_ROOT_FUNCTIONS__", _TABLE_SCOPE_ROOT_FUNCTIONS)

_ATTACHMENT_VIEW_SCRIPT = """
(candidates) => {
  const visible = (el) => {
    if (!el || !(el instanceof HTMLElement)) return false;
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
  };
  const roots = [];
  for (const candidate of candidates || []) {
    if (!candidate || !candidate.fieldid) continue;
    const escaped = CSS.escape(String(candidate.fieldid));
    const root = document.querySelector(`[fieldid="${escaped}"], [data-fieldid="${escaped}"], [data-field-id="${escaped}"]`);
    if (root && visible(root) && (root.matches('.lcd-upload-next') || root.querySelector('.view-switch'))) roots.push(root);
  }
  for (const root of document.querySelectorAll('.lcd-upload-next')) {
    if (visible(root) && !roots.includes(root)) roots.push(root);
  }
  for (const root of roots) {
    const cardContent = root.querySelector('.card-content');
    const tableContent = root.querySelector('.table-content');
    const cardVisible = visible(cardContent);
    const tableVisible = visible(tableContent);
    if (cardVisible !== tableVisible) return cardVisible ? 'card' : 'table';
    const checked = root.querySelector('.view-switch .is-checked input[value], .view-switch input[value]:checked');
    const view = String((checked && checked.value) || root.getAttribute('viewtype') || '').toLowerCase();
    if (view === 'card' || view === 'table') return view;
  }
  return '';
}
"""

_ATTACHMENT_VIEW_SWITCH_SCRIPT = """
(payload) => {
  const visible = (el) => {
    if (!el || !(el instanceof HTMLElement)) return false;
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
  };
  const roots = [];
  for (const candidate of payload.candidates || []) {
    if (!candidate || !candidate.fieldid) continue;
    const escaped = CSS.escape(String(candidate.fieldid));
    const root = document.querySelector(`[fieldid="${escaped}"], [data-fieldid="${escaped}"], [data-field-id="${escaped}"]`);
    if (root && visible(root) && (root.matches('.lcd-upload-next') || root.querySelector('.view-switch'))) roots.push(root);
  }
  for (const root of document.querySelectorAll('.lcd-upload-next')) {
    if (visible(root) && !roots.includes(root)) roots.push(root);
  }
  for (const root of roots) {
    const input = root.querySelector(`.view-switch input[type="radio"][value="${CSS.escape(String(payload.target_view || ''))}"]`);
    const target = input && input.closest('label');
    if (!target || !visible(target)) continue;
    const marker = `ydf-attachment-view-${Date.now()}-${Math.floor(Math.random() * 100000)}`;
    document.querySelectorAll('[data-ydf-browser-attachment-view]').forEach((el) => el.removeAttribute('data-ydf-browser-attachment-view'));
    target.setAttribute('data-ydf-browser-attachment-view', marker);
    return `[data-ydf-browser-attachment-view="${CSS.escape(marker)}"]`;
  }
  return '';
}
"""

_ATTACHMENT_FILE_INPUT_SELECTOR_SCRIPT = """
(payload) => {
  const normalize = (value) => String(value || '').replace(/\\s+/g, '').trim();
  const visible = (el) => {
    if (!el || !(el instanceof HTMLElement)) return false;
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
  };
  const args = payload && typeof payload === 'object' ? payload : { attachment_type: payload };
  const candidates = Array.isArray(args.candidates) ? args.candidates : [];
  const wanted = normalize(args.attachment_type);
  const fieldidSelector = (fieldid) => {
    const escaped = CSS.escape(String(fieldid || ''));
    return `[fieldid="${escaped}"], [data-fieldid="${escaped}"], [data-field-id="${escaped}"]`;
  };
  const candidateMatches = (candidate) => {
    const aliases = [candidate.label, candidate.fieldid, candidate.key].map(normalize).filter(Boolean);
    return aliases.includes(wanted);
  };
  const candidateRoots = [];
  for (const candidate of candidates) {
    if (!candidate || !candidate.fieldid) continue;
    const root = document.querySelector(fieldidSelector(candidate.fieldid));
    if (root && visible(root)) {
      candidateRoots.push({ root, candidate, matched: candidateMatches(candidate) });
    }
  }
  candidateRoots.sort((a, b) => Number(b.matched) - Number(a.matched));
  const knownRoot =
    document.querySelector('[fieldid="pmBillAttachmentList"], [data-fieldid="pmBillAttachmentList"]')
    || document.querySelector('[fieldid="tab-pmBillAttachment"], [data-fieldid="tab-pmBillAttachment"]');
  if (knownRoot && visible(knownRoot)) {
    candidateRoots.push({ root: knownRoot, candidate: {}, matched: false });
  }
  candidateRoots.push({ root: document.body, candidate: {}, matched: false });

  const markInput = (input, root, candidate, source) => {
    const marker = `ydf-attachment-${Date.now()}-${Math.floor(Math.random() * 100000)}`;
    const rootMarker = `ydf-attachment-root-${Date.now()}-${Math.floor(Math.random() * 100000)}`;
    document.querySelectorAll('[data-ydf-browser-attachment-input]').forEach((el) => el.removeAttribute('data-ydf-browser-attachment-input'));
    document.querySelectorAll('[data-ydf-browser-attachment-root]').forEach((el) => el.removeAttribute('data-ydf-browser-attachment-root'));
    input.setAttribute('data-ydf-browser-attachment-input', marker);
    if (root instanceof HTMLElement) root.setAttribute('data-ydf-browser-attachment-root', rootMarker);
    const accept = input.getAttribute('accept') || '';
    const allowed = Array.isArray(candidate.allowed_extensions) && candidate.allowed_extensions.length
      ? candidate.allowed_extensions
      : accept.split(/[,;，；\\s]+/).filter(Boolean);
    return {
      input_selector: `[data-ydf-browser-attachment-input="${CSS.escape(marker)}"]`,
      root_selector: `[data-ydf-browser-attachment-root="${CSS.escape(rootMarker)}"]`,
      label: candidate.label || args.attachment_type || '',
      fieldid: candidate.fieldid || root.getAttribute('fieldid') || root.getAttribute('data-fieldid') || '',
      allowed_extensions: allowed,
      source,
    };
  };

  for (const item of candidateRoots) {
    const root = item.root;
    const candidate = item.candidate || {};
    const inputs = Array.from(root.querySelectorAll('input[type="file"]'));
    for (const input of inputs) {
      let node = input.parentElement;
      while (node && node !== root.parentElement) {
        const text = normalize(node.innerText || node.textContent);
        if (
          (item.matched || text.includes(wanted) || !wanted)
          && (text.includes('本地上传') || inputs.length === 1)
          && node.querySelectorAll('input[type="file"]').length === 1
        ) {
          return markInput(input, root, candidate, 'component-input');
        }
        node = node.parentElement;
      }
    }
  }

  for (const item of candidateRoots) {
    const root = item.root;
    const labelCandidates = Array.from(root.querySelectorAll('*'))
      .filter(visible)
      .map((el) => {
        const rect = el.getBoundingClientRect();
        return {
          el,
          rect,
          text: normalize(el.innerText || el.textContent),
          area: rect.width * rect.height,
        };
      })
      .filter((candidate) => candidate.text.startsWith(`*${wanted}(`) || candidate.text.startsWith(`${wanted}(`) || candidate.text === wanted)
      .sort((a, b) => a.area - b.area);
    const label = labelCandidates[0];
    if (!label) continue;
    const uploadWrappers = Array.from(root.querySelectorAll('.wui-upload, .ant-upload, .u-upload, [class*="upload"]'))
      .filter(visible)
      .filter((el) => el.querySelector('input[type="file"]') && normalize(el.innerText || el.textContent).includes('本地上传'))
      .map((el) => ({ el, rect: el.getBoundingClientRect() }))
      .sort((a, b) => {
        const ay = Math.abs((a.rect.y + a.rect.height / 2) - (label.rect.y + label.rect.height / 2));
        const by = Math.abs((b.rect.y + b.rect.height / 2) - (label.rect.y + label.rect.height / 2));
        return ay - by;
      });
    const wrapper = uploadWrappers[0];
    const input = wrapper && wrapper.el.querySelector('input[type="file"]');
    if (input) return markInput(input, root, item.candidate || {}, 'label-nearest-upload');
  }
  return null;
}
"""

_ATTACHMENT_TEXT_SCRIPT = """
(payload) => {
  const args = payload && typeof payload === 'object' ? payload : {};
  const root = (args.root_selector && document.querySelector(args.root_selector))
    || document.querySelector('[fieldid="pmBillAttachmentList"], [data-fieldid="pmBillAttachmentList"]')
    || document.querySelector('[fieldid="tab-pmBillAttachment"], [data-fieldid="tab-pmBillAttachment"]')
    || document.body;
  return String(root.innerText || root.textContent || '').replace(/\\s+/g, ' ').trim();
}
"""

_ATTACHMENT_STATE_SCRIPT = """
(payload) => {
  const args = payload && typeof payload === 'object' ? payload : {};
  const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
  const compact = (value) => normalize(value).replace(/\\s+/g, '');
  const visible = (el) => {
    if (!el || !(el instanceof HTMLElement)) return false;
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
  };
  const root = (args.root_selector && document.querySelector(args.root_selector))
    || document.querySelector('[fieldid="pmBillAttachmentList"], [data-fieldid="pmBillAttachmentList"]')
    || document.querySelector('[fieldid="tab-pmBillAttachment"], [data-fieldid="tab-pmBillAttachment"]')
    || document.body;
  const filename = compact(args.filename);
  const attachmentType = compact(args.attachment_type);
  const text = normalize(root.innerText || root.textContent || '');
  const compactText = compact(text);
  const progressWords = ['上传中', '正在上传', '上传进度', '处理中', '解析中', 'loading'];
  const hasProgressText = progressWords.some((word) => compactText.toLowerCase().includes(String(word).toLowerCase()));
  const progressElement = Array.from(root.querySelectorAll('[class*="progress"], [class*="loading"], [class*="spin"], [aria-busy="true"]'))
    .some(visible);
  const uploading = hasProgressText || progressElement;
  const rowSelectors = [
    'tr',
    '[role="row"]',
    'li',
    '.wui-table-row',
    '.ant-table-row',
    '.u-table-row',
    '.wui-upload-list-item',
    '.ant-upload-list-item',
    '[class*="upload-list"]',
    '[class*="uploadList"]',
    '[class*="file-list"]',
    '[class*="attachment"]',
    '[class*="attach"]',
  ];
  const rows = Array.from(root.querySelectorAll(rowSelectors.join(',')))
    .filter(visible)
    .filter((el) => {
      const rowText = compact(el.innerText || el.textContent || '');
      if (!filename || !rowText.includes(filename)) return false;
      if (el.querySelector('input[type="file"]')) return false;
      return !progressWords.some((word) => rowText.toLowerCase().includes(String(word).toLowerCase()));
    });
  if (rows.length && !uploading) {
    return {
      completed: true,
      signal: 'file-row',
      text,
      root_selector: args.root_selector || '',
      row_count: rows.length,
    };
  }
  if (attachmentType && !uploading && (compactText.includes(`${attachmentType}(1)`) || compactText.includes(`${attachmentType}（1）`))) {
    return {
      completed: true,
      signal: 'type-count',
      text,
      root_selector: args.root_selector || '',
      row_count: rows.length,
    };
  }
  return {
    completed: false,
    signal: uploading ? 'uploading' : '',
    text,
    root_selector: args.root_selector || '',
    row_count: rows.length,
  };
}
"""


_TABLE_ASSERTION_ROWS_SCRIPT = r"""
(rootOrPayload, maybePayload) => {
  const root = rootOrPayload instanceof HTMLElement ? rootOrPayload : document;
  const normalize = (value) => String(value || '').replace(/\s+/g, ' ').trim();
  const visible = (node) => {
    const style = window.getComputedStyle(node);
    const rect = node.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
  };
  const headers = Array.from(root.querySelectorAll(
    'thead th, [role="columnheader"], .ant-table-header th, .wui-table-header th, .u-table-header th'
  )).filter(visible).map((node) => normalize(
    node.getAttribute('title') || node.getAttribute('aria-label') || node.innerText || node.textContent
  ).replace(/^[\s*＊✱✳※]+/, '')).filter(Boolean);
  const uniqueHeaders = headers.filter((item, index) => headers.indexOf(item) === index);
  const summary = /^(小计|合计|汇总|总计)(\s|$)/;
  const rows = [];
  for (const row of Array.from(root.querySelectorAll(
    'tbody tr, [role="row"], .ant-table-row, .wui-table-row, .u-table-row, .el-table__row'
  )).filter(visible)) {
    if (row.closest('thead, .ant-table-header, .wui-table-header, .u-table-header, .el-table__header')) continue;
    const cells = Array.from(row.querySelectorAll(
      'td, [role="cell"], .ant-table-cell, .wui-table-cell, .u-table-cell, .el-table__body td'
    )).filter(visible);
    const values = cells.map((cell) => {
      const control = cell.matches('input, textarea, select') ? cell : cell.querySelector('input, textarea, select');
      return normalize(control ? control.value : (cell.innerText || cell.textContent));
    });
    const first = values.find(Boolean) || '';
    if (!first || summary.test(first)) continue;
    const item = {};
    for (let index = 0; index < Math.min(uniqueHeaders.length, values.length); index += 1) {
      if (uniqueHeaders[index]) item[uniqueHeaders[index]] = values[index];
    }
    if (Object.values(item).some(Boolean)) rows.push(item);
  }
  const identityColumns = uniqueHeaders.filter((header) => /(编码|代码|编号|主键|(^|\s)id($|\s))/i.test(header));
  const activePage = root.querySelector(
    '.ant-pagination-item-active, .wui-pagination-item-active, .u-pagination-item-active, [aria-current="page"]'
  );
  const emptyNode = Array.from(root.querySelectorAll(
    '.ant-empty-description, .wui-empty, .u-empty, [class*="empty"]'
  )).filter(visible).find((node) => /暂无数据|没有数据|无数据/.test(normalize(node.innerText || node.textContent)));
  return {
    rows,
    identity_columns: identityColumns,
    pagination: activePage ? { current_page: normalize(activePage.innerText || activePage.textContent) } : null,
    empty_state: emptyNode ? normalize(emptyNode.innerText || emptyNode.textContent) : (rows.length === 0 ? true : false)
  };
}
"""


_TABLE_COLUMN_VALUES_SCRIPT = """
(rootOrPayload, maybePayload) => {
  const rootArg = rootOrPayload instanceof HTMLElement ? rootOrPayload : null;
  const payloadOrColumnName = maybePayload || rootOrPayload;
  const payload = (payloadOrColumnName && typeof payloadOrColumnName === 'object')
    ? payloadOrColumnName
    : { column: payloadOrColumnName };
  const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const normalizeHeader = (value) => normalize(String(value || '').replace(/^[\\s*＊✱✳※]+/, ''));
  const unique = (items) => Array.from(new Set(items.filter(Boolean)));
  const visible = (el) => {
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
  };
  const columnName = normalize(payload.column || payloadOrColumnName);
  const tableFieldid = normalize(payload.tableFieldid || '');
  const dataField = normalize(payload.dataField || '');
  const all = (root, selector) => {
    try {
      return Array.from(root.querySelectorAll(selector));
    } catch (_error) {
      return [];
    }
  };
  const scope = rootArg || (payload.root && payload.root.querySelectorAll ? payload.root : document);
  const headerSelector = [
    'th',
    '[role="columnheader"]',
    '.wui-table-header th',
    '.wui-table-header [class*="cell"]',
    '.ant-table-header th',
    '.ant-table-header [class*="cell"]',
    '.u-table-header th',
    '.u-table-header [class*="cell"]',
    '.el-table__header th',
    '.el-table__header [class*="cell"]'
  ].join(',');
  const cellSelector = [
    '[role="cell"]',
    'td',
    '.ant-table-cell',
    '.wui-table-cell',
    '.u-table-cell',
    '.el-table__body td',
    '.el-table__body [class*="cell"]',
    '[class*="table-body"] [class*="cell"]',
    '[class*="TableBody"] [class*="cell"]'
  ].join(',');
  const isHeaderCell = (el) => {
    const tag = String(el.tagName || '').toLowerCase();
    const headerRoot = el.closest('.ant-table-header, .wui-table-header, .u-table-header, .el-table__header, thead, [class*="table-header"], [class*="TableHeader"]');
    return tag === 'th' || el.getAttribute('role') === 'columnheader' || Boolean(headerRoot);
  };
  const isSummaryRow = (row) => {
    const rowText = normalize(row.innerText || row.textContent);
    const compactRowText = rowText.replace(/\\s+/g, '');
    const className = String(row.className || '');
    if (/(summary|footer|total|subtotal|tfoot)/i.test(className)) return true;
    if (/^(小计|合计|汇总|总计)(\\s|$)/.test(rowText) || /^(小计|合计|汇总|总计)/.test(compactRowText)) return true;
    const cells = all(row, cellSelector).filter(visible);
    const firstCellText = normalize(cells[0] ? cells[0].innerText || cells[0].textContent : '');
    const firstCompactText = firstCellText.replace(/\\s+/g, '');
    return /^(小计|合计|汇总|总计)(\\s|$)/.test(firstCellText) || /^(小计|合计|汇总|总计)$/.test(firstCompactText);
  };
  const identityKeys = [
    'data-field',
    'data-index',
    'data-key',
    'data-column-key',
    'data-col-key',
    'fieldid',
    'data-fieldid',
    'key'
  ];
  const identityValues = (el) => {
    const values = new Set();
    if (!el || !el.getAttribute) return values;
    for (const key of identityKeys) {
      const value = normalize(el.getAttribute(key) || '');
      if (value) values.add(value);
    }
    if (dataField) values.add(dataField);
    return values;
  };
  const identityEquivalent = (a, b) => {
    const left = normalize(a);
    const right = normalize(b);
    if (!left || !right) return false;
    if (left === right) return true;
    if (left.endsWith(`_${right}`)) return true;
    if (right.endsWith(`_${left}`)) return true;
    return false;
  };
  const identityMatches = (cell, header) => {
    const headerValues = identityValues(header);
    const cellValues = identityValues(cell);
    for (const value of headerValues) {
      for (const cellValue of cellValues) {
        if (identityEquivalent(value, cellValue)) return true;
      }
    }
    return false;
  };
  const headerLabels = (el) => unique([
    normalizeHeader(el.innerText || ''),
    normalizeHeader(el.textContent || ''),
    normalizeHeader(el.getAttribute('title') || ''),
    normalizeHeader(el.getAttribute('aria-label') || ''),
  ]);
  const horizontalOverlap = (a, b, tolerance = 24) =>
    a.right >= b.left - tolerance && b.right >= a.left - tolerance;
  const relatedTableBodies = (table, scope) => {
    const roots = [];
    if (table && all(table, 'tbody tr, [role="row"], .ant-table-row, .wui-table-row, .u-table-row, .el-table__row').length) {
      roots.push(table);
    }
    const tableRect = table && table.getBoundingClientRect ? table.getBoundingClientRect() : null;
    const searchRoot = scope && scope.querySelectorAll ? scope : document;
    const bodySelector = [
      'tbody',
      '.ant-table-body',
      '.wui-table-body',
      '.u-table-body',
      '.el-table__body',
      '[class*="table-body"]',
      '[class*="TableBody"]'
    ].join(',');
    const bodyRoots = all(searchRoot, bodySelector)
      .filter(visible)
      .filter((body) => {
        if (!tableRect) return true;
        const rect = body.getBoundingClientRect();
        return horizontalOverlap(tableRect, rect) && rect.bottom >= tableRect.top - 16;
      })
      .sort((a, b) => {
        if (!tableRect) return 0;
        return Math.abs(a.getBoundingClientRect().top - tableRect.bottom)
          - Math.abs(b.getBoundingClientRect().top - tableRect.bottom);
      });
    for (const bodyRoot of bodyRoots) {
      if (!roots.includes(bodyRoot)) roots.push(bodyRoot);
    }
    return roots;
  };
  const dataRowsForTable = (table, scope) => {
    const rows = [];
    const seenRows = new Set();
    for (const bodyRoot of relatedTableBodies(table, scope)) {
      for (const row of all(bodyRoot, 'tbody tr, [role="row"], .ant-table-row, .wui-table-row, .u-table-row, .el-table__row')) {
        if (seenRows.has(row) || !visible(row)) continue;
        if (row.closest('thead, .ant-table-header, .wui-table-header, .u-table-header, .el-table__header')) continue;
        if (isSummaryRow(row)) continue;
        seenRows.add(row);
        rows.push(row);
      }
    }
    return rows;
  };
  const headerCells = all(scope, headerSelector)
    .filter(visible)
    .filter(isHeaderCell)
    .filter((el) => {
      return headerLabels(el).includes(columnName) || (dataField && identityValues(el).has(dataField));
    });
  const header = headerCells[0];
  if (!header) return [];
  const headerRect = header.getBoundingClientRect();
  const headerRow = header.closest('tr, [role="row"]');
  const headerSiblings = headerRow
    ? all(headerRow, headerSelector)
    : [];
  let index = headerSiblings.indexOf(header);
  if (index < 0 && header.cellIndex >= 0) index = header.cellIndex;
  const table = header.closest('table, .ant-table, .wui-table, .u-table, .el-table, [role="table"], [role="grid"]') || scope;
  const rows = dataRowsForTable(table, scope);
  const values = [];
  for (const row of rows) {
    const cells = all(row, cellSelector).filter(visible);
    const cell = cells.find((item) => identityMatches(item, header)) || (index >= 0 ? cells[index] : null);
    const text = cell ? normalize(cell.innerText || cell.textContent || '') : '';
    if (text) values.push(text);
  }
  if (values.length) return Array.from(new Set(values));

  const centerX = headerRect.left + headerRect.width / 2;
  const allCells = dataRowsForTable(table, scope).flatMap((row) => all(row, cellSelector).filter(visible));
  const aligned = [];
  for (const cell of allCells) {
    const rect = cell.getBoundingClientRect();
    if (rect.top <= headerRect.bottom + 2) continue;
    if (centerX < rect.left || centerX > rect.right) continue;
    const text = normalize(cell.innerText || cell.textContent || '');
    if (text) aligned.push(text);
  }
  return Array.from(new Set(aligned));
}
"""


_TABLE_CELL_LINK_CLICK_SCRIPT = """
(rootOrPayload, maybePayload) => {
  const rootArg = rootOrPayload instanceof HTMLElement ? rootOrPayload : null;
  const payload = maybePayload || rootOrPayload || {};
  const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
  const normalizeCompact = (value) => normalize(value).replace(/\\s+/g, '');
  const normalizeHeader = (value) => normalize(String(value || '').replace(/^[\\s*＊✱✳※]+/, ''));
  const visible = (el) => {
    if (!el || el.nodeType !== 1) return false;
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
  };
  const textOf = (el) => normalize(el ? (el.innerText || el.textContent || '') : '');
  const cssEscape = (value) => {
    if (window.CSS && typeof window.CSS.escape === 'function') return window.CSS.escape(value);
    return String(value).replace(/"/g, '\\"');
  };
  const all = (root, selector) => {
    try {
      return Array.from(root.querySelectorAll(selector));
    } catch (_error) {
      return [];
    }
  };
  const scope = rootArg || document;
  const column = normalize(payload.column || '');
  const linkText = normalize(payload.linkText || '');
  const match = payload.match || {};
  const rowNumber = Number(payload.rowNumber || 0);
  const tableColumns = Array.from(payload.tableColumns || []).map((item) => normalize(String(item))).filter(Boolean);
  if (!column) return { clicked: false, reason: 'missing-column' };

  const rawConditions = Array.isArray(match.conditions) ? match.conditions : [match];
  const conditions = rawConditions
    .filter((item) => item && typeof item === 'object')
    .map((item) => ({
      column: normalize(item.column || item.field || ''),
      equals: item.equals === undefined || item.equals === null ? '' : normalize(String(item.equals)),
      contains: item.contains === undefined || item.contains === null ? '' : normalize(String(item.contains))
    }))
    .filter((item) => item.column && (item.equals || item.contains));
  const requestedColumns = Array.from(new Set([
    column,
    ...conditions.map((item) => item.column),
    ...tableColumns,
  ].filter(Boolean)));
  const headerSelector = [
    'th',
    '[role="columnheader"]',
    '.wui-table-header th',
    '.wui-table-header [class*="cell"]',
    '.ant-table-header th',
    '.ant-table-header [class*="cell"]',
    '.u-table-header th',
    '.u-table-header [class*="cell"]',
    '.el-table__header th',
    '.el-table__header [class*="cell"]'
  ].join(',');
  const cellSelector = [
    '[role="cell"]',
    'td',
    '.ant-table-cell',
    '.wui-table-cell',
    '.u-table-cell',
    '.el-table__body td',
    '.el-table__body [class*="cell"]',
    '[class*="table-body"] [class*="cell"]',
    '[class*="TableBody"] [class*="cell"]'
  ].join(',');
  const headerCells = all(scope, headerSelector).filter(visible).filter((el) => {
    const tag = String(el.tagName || '').toLowerCase();
    return tag === 'th'
      || el.getAttribute('role') === 'columnheader'
      || Boolean(el.closest('.ant-table-header, .wui-table-header, .u-table-header, .el-table__header, thead, [class*="table-header"], [class*="TableHeader"]'));
  });
  const identityKeys = ['data-field', 'data-index', 'data-key', 'data-column-key', 'data-col-key', 'fieldid', 'data-fieldid', 'key'];
  const identityValues = (el) => {
    const values = new Set();
    if (!el || !el.getAttribute) return values;
    for (const key of identityKeys) {
      const value = normalize(el.getAttribute(key) || '');
      if (value) values.add(value);
    }
    return values;
  };
  const identityEquivalent = (a, b) => {
    const left = normalize(a);
    const right = normalize(b);
    return Boolean(left && right && (left === right || left.endsWith(`_${right}`) || right.endsWith(`_${left}`)));
  };
  const identityMatches = (cell, header) => {
    const headerValues = identityValues(header);
    const cellValues = identityValues(cell);
    for (const value of headerValues) {
      for (const cellValue of cellValues) {
        if (identityEquivalent(value, cellValue)) return true;
      }
    }
    return false;
  };
  const headerLabels = (el) => [
    normalizeHeader(el.innerText || ''),
    normalizeHeader(el.textContent || ''),
    normalizeHeader(el.getAttribute('title') || ''),
    normalizeHeader(el.getAttribute('aria-label') || ''),
  ].filter(Boolean);
  const headers = [];
  for (const header of headerCells) {
    const labels = headerLabels(header);
    const columnName = requestedColumns.find((item) => labels.includes(item));
    if (!columnName) continue;
    const headerRow = header.closest('tr, [role="row"]');
    const siblings = headerRow ? all(headerRow, headerSelector) : [];
    let index = siblings.indexOf(header);
    if (index < 0 && header.cellIndex >= 0) index = header.cellIndex;
    const dataIndex = header.getAttribute('data-index') || header.getAttribute('data-field') || '';
    if (index >= 0 || dataIndex || identityValues(header).size) headers.push({ columnName, index, dataIndex, header });
  }
  const targetHeader = headers.find((item) => item.columnName === column);
  if (!targetHeader) return { clicked: false, reason: 'column-not-found', column };
  const headerByColumn = (name) => headers.find((item) => item.columnName === name);
  const rowCell = (row, header) => {
    if (!header) return null;
    const cells = all(row, cellSelector).filter(visible);
    if (header.dataIndex) {
      const found = row.querySelector(`[data-index="${cssEscape(header.dataIndex)}"], [data-field="${cssEscape(header.dataIndex)}"]`);
      if (found && visible(found)) return found;
    }
    return cells.find((item) => identityMatches(item, header.header)) || (header.index >= 0 ? cells[header.index] : null);
  };
  const cellValue = (row, header) => {
    const cell = rowCell(row, header);
    return cell ? textOf(cell) : '';
  };
  const rows = all(scope, 'tbody tr, [role="row"], .ant-table-row, .wui-table-row, .u-table-row, .el-table__row')
    .filter(visible)
    .filter((row) => !row.closest('thead, .ant-table-header, .wui-table-header, .u-table-header, .el-table__header'))
    .filter((row) => all(row, cellSelector).some(visible));
  let row = null;
  if (rowNumber > 0) {
    row = rows[rowNumber - 1] || null;
  } else if (conditions.length) {
    row = rows.find((candidate) => conditions.every((condition) => {
      const value = cellValue(candidate, headerByColumn(condition.column));
      if (condition.equals) return normalizeCompact(value) === normalizeCompact(condition.equals) || normalize(value).includes(condition.equals);
      if (condition.contains) return normalize(value).includes(condition.contains);
      return false;
    })) || null;
  } else {
    const matchValues = Array.from(payload.matchValues || []).map((item) => normalize(String(item))).filter(Boolean);
    row = rows.find((candidate) => matchValues.every((value) => textOf(candidate).includes(value))) || null;
  }
  if (!row) return { clicked: false, reason: 'row-not-found', column };
  const cell = rowCell(row, targetHeader);
  if (!cell || !visible(cell)) return { clicked: false, reason: 'cell-not-found', column };
  const candidates = [
    ...all(cell, 'a, button, [role="link"], [role="button"], [onclick], [class*="link"], [class*="Link"]'),
    cell
  ].filter(visible);
  const clickable = candidates.filter((item) => {
    if (item === cell) {
      const role = normalize(item.getAttribute('role') || '').toLowerCase();
      const className = String(item.className || '');
      const cursor = window.getComputedStyle(item).cursor;
      return Boolean(item.onclick || role === 'link' || /link/i.test(className) || cursor === 'pointer');
    }
    return true;
  });
  const target = linkText
    ? clickable.find((item) => normalizeCompact(textOf(item)) === normalizeCompact(linkText) || textOf(item).includes(linkText))
    : (clickable.length === 1 ? clickable[0] : clickable.find((item) => item !== cell) || clickable[0]);
  if (!target) return { clicked: false, reason: linkText ? 'link-text-not-found' : 'cell-not-clickable', column };
  target.scrollIntoView({ block: 'center', inline: 'center' });
  target.click();
  return { clicked: true, column, clicked_text: textOf(target), link_text: linkText };
}
"""

_TABLE_ROW_VALUES_SCRIPT = """
(rootOrPayload, maybePayload) => {
  const rootArg = rootOrPayload instanceof HTMLElement ? rootOrPayload : null;
  const payload = maybePayload || rootOrPayload || {};
  const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const normalizeHeader = (value) => normalize(String(value || '').replace(/^[\\s*＊✱✳※]+/, ''));
  const unique = (items) => Array.from(new Set(items.filter(Boolean)));
  const visible = (el) => {
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
  };
  const matchValues = Array.from(payload.matchValues || []).map((item) => normalize(String(item))).filter(Boolean);
  const columns = Array.from(payload.columns || []).map((item) => normalize(String(item))).filter(Boolean);
  const tableColumns = Array.from(payload.tableColumns || []).map((item) => normalize(String(item))).filter(Boolean);
  const tableFieldid = normalize(payload.tableFieldid || '');
  const dataField = normalize(payload.dataField || '');
  if (!matchValues.length || !columns.length) return {};
  const cssEscape = (value) => {
    if (window.CSS && typeof window.CSS.escape === 'function') return window.CSS.escape(value);
    return String(value).replace(/"/g, '\\"');
  };
  const all = (root, selector) => {
    try {
      return Array.from(root.querySelectorAll(selector));
    } catch (_error) {
      return [];
    }
  };
  const scope = rootArg || (payload.root && payload.root.querySelectorAll ? payload.root : document);
  const match = payload.match || {};
  const rawConditions = Array.isArray(match.conditions) ? match.conditions : [match];
  const conditions = rawConditions
    .filter((item) => item && typeof item === 'object')
    .map((item) => ({
      column: normalize(item.column || item.field || ''),
      equals: item.equals === undefined || item.equals === null ? '' : normalize(String(item.equals)),
      contains: item.contains === undefined || item.contains === null ? '' : normalize(String(item.contains))
    }))
    .filter((item) => item.column && (item.equals || item.contains));
  const requestedColumns = Array.from(new Set([
    ...columns,
    ...conditions.map((item) => item.column),
    ...tableColumns,
  ].filter(Boolean)));
  const headerSelector = [
    'th',
    '[role="columnheader"]',
    '.wui-table-header th',
    '.wui-table-header [class*="cell"]',
    '.ant-table-header th',
    '.ant-table-header [class*="cell"]',
    '.u-table-header th',
    '.u-table-header [class*="cell"]',
    '.el-table__header th',
    '.el-table__header [class*="cell"]'
  ].join(',');
  const cellSelector = [
    '[role="cell"]',
    'td',
    '.ant-table-cell',
    '.wui-table-cell',
    '.u-table-cell',
    '.el-table__body td',
    '.el-table__body [class*="cell"]',
    '[class*="table-body"] [class*="cell"]',
    '[class*="TableBody"] [class*="cell"]'
  ].join(',');
  const isHeaderCell = (el) => {
    const tag = String(el.tagName || '').toLowerCase();
    const headerRoot = el.closest('.ant-table-header, .wui-table-header, .u-table-header, .el-table__header, thead, [class*="table-header"], [class*="TableHeader"]');
    return tag === 'th' || el.getAttribute('role') === 'columnheader' || Boolean(headerRoot);
  };
  const identityKeys = [
    'data-field',
    'data-index',
    'data-key',
    'data-column-key',
    'data-col-key',
    'fieldid',
    'data-fieldid',
    'key'
  ];
  const identityValues = (el) => {
    const values = new Set();
    if (!el || !el.getAttribute) return values;
    for (const key of identityKeys) {
      const value = normalize(el.getAttribute(key) || '');
      if (value) values.add(value);
    }
    if (dataField) values.add(dataField);
    return values;
  };
  const identityEquivalent = (a, b) => {
    const left = normalize(a);
    const right = normalize(b);
    if (!left || !right) return false;
    if (left === right) return true;
    if (left.endsWith(`_${right}`)) return true;
    if (right.endsWith(`_${left}`)) return true;
    return false;
  };
  const identityMatches = (cell, header) => {
    const headerValues = identityValues(header);
    const cellValues = identityValues(cell);
    for (const value of headerValues) {
      for (const cellValue of cellValues) {
        if (identityEquivalent(value, cellValue)) return true;
      }
    }
    return false;
  };
  const headerLabels = (el) => unique([
    normalizeHeader(el.innerText || ''),
    normalizeHeader(el.textContent || ''),
    normalizeHeader(el.getAttribute('title') || ''),
    normalizeHeader(el.getAttribute('aria-label') || ''),
  ]);
  const horizontalOverlap = (a, b, tolerance = 24) =>
    a.right >= b.left - tolerance && b.right >= a.left - tolerance;
  const relatedTableBodies = (table, scope) => {
    const roots = [];
    if (table && all(table, 'tbody tr, [role="row"], .ant-table-row, .wui-table-row, .u-table-row, .el-table__row').length) {
      roots.push(table);
    }
    const tableRect = table && table.getBoundingClientRect ? table.getBoundingClientRect() : null;
    const searchRoot = scope && scope.querySelectorAll ? scope : document;
    const bodySelector = [
      'tbody',
      '.ant-table-body',
      '.wui-table-body',
      '.u-table-body',
      '.el-table__body',
      '[class*="table-body"]',
      '[class*="TableBody"]'
    ].join(',');
    const bodyRoots = all(searchRoot, bodySelector)
      .filter(visible)
      .filter((body) => {
        if (!tableRect) return true;
        const rect = body.getBoundingClientRect();
        return horizontalOverlap(tableRect, rect) && rect.bottom >= tableRect.top - 16;
      })
      .sort((a, b) => {
        if (!tableRect) return 0;
        return Math.abs(a.getBoundingClientRect().top - tableRect.bottom)
          - Math.abs(b.getBoundingClientRect().top - tableRect.bottom);
      });
    for (const bodyRoot of bodyRoots) {
      if (!roots.includes(bodyRoot)) roots.push(bodyRoot);
    }
    return roots;
  };
  const dataRowsForHeaders = (headers, scope) => {
    const rows = [];
    const seenRows = new Set();
    const tables = headers
      .map((item) => item.header.closest('table, .ant-table, .wui-table, .u-table, .el-table, [role="table"], [role="grid"]') || scope)
      .filter(Boolean);
    for (const table of tables) {
      for (const bodyRoot of relatedTableBodies(table, scope)) {
        for (const row of all(bodyRoot, 'tbody tr, [role="row"], .ant-table-row, .wui-table-row, .u-table-row, .el-table__row')) {
          if (seenRows.has(row) || !visible(row)) continue;
          if (row.closest('thead, .ant-table-header, .wui-table-header, .u-table-header, .el-table__header')) continue;
          seenRows.add(row);
          rows.push(row);
        }
      }
    }
    return rows;
  };

  const headerCells = all(scope, headerSelector).filter(visible).filter(isHeaderCell);
  const headers = [];
  for (const header of headerCells) {
    const labels = headerLabels(header);
    const columnName = requestedColumns.find((column) => labels.includes(column));
    if (!columnName) continue;
    const headerRow = header.closest('tr, [role="row"]');
    const siblings = headerRow
      ? all(headerRow, headerSelector)
      : [];
    let index = siblings.indexOf(header);
    if (index < 0 && header.cellIndex >= 0) index = header.cellIndex;
    const dataIndex = header.getAttribute('data-index') || header.getAttribute('data-field') || '';
    if (index >= 0 || dataIndex || identityValues(header).size) headers.push({ columnName, index, dataIndex, header });
  }
  if (!headers.length) return {};
  const headerByColumn = (column) => headers.find((item) => item.columnName === column);

  const rowCellValue = (row, header) => {
    if (!header) return '';
    const cells = all(row, cellSelector).filter(visible);
    const cell = header.dataIndex
      ? row.querySelector(`[data-index="${cssEscape(header.dataIndex)}"], [data-field="${cssEscape(header.dataIndex)}"]`)
      : cells.find((item) => identityMatches(item, header.header)) || (header.index >= 0 ? cells[header.index] : null);
    if (!cell) return '';
    const control = cell.matches('input, textarea, select')
      ? cell
      : cell.querySelector('input, textarea, select');
    return normalize(control ? control.value : (cell.innerText || cell.textContent || ''));
  };
  const scopedRows = all(scope, 'tbody tr, [role="row"], .ant-table-row, .wui-table-row, .u-table-row, .el-table__row')
    .filter(visible)
    .filter((row) => !row.closest('thead, .ant-table-header, .wui-table-header, .u-table-header, .el-table__header'));
  const candidateRows = dataRowsForHeaders(headers, scope);
  if (!candidateRows.length) candidateRows.push(...scopedRows);
  const row = candidateRows.find((candidate) => {
    if (conditions.length) {
      return conditions.every((condition) => {
        const value = rowCellValue(candidate, headerByColumn(condition.column));
        if (condition.equals) return value === condition.equals || normalize(value).includes(condition.equals);
        if (condition.contains) return normalize(value).includes(condition.contains);
        return false;
      });
    }
    const text = normalize(candidate.innerText || candidate.textContent || '');
    return matchValues.every((value) => text.includes(value));
  });
  if (!row) return {};

  const result = {};
  if (payload.selectorMarker) {
    const marker = String(payload.selectorMarker);
    row.setAttribute('data-ydf-browser-table-row-match', marker);
    result.__selector = `[data-ydf-browser-table-row-match="${marker}"]`;
  }
  for (const header of headers) {
    if (!columns.includes(header.columnName)) continue;
    result[header.columnName] = rowCellValue(row, header);
  }
  return result;
}
"""

_TABLE_HEADERS_SCRIPT = """
(rootOrPayload, maybePayload) => {
  const rootArg = rootOrPayload instanceof HTMLElement ? rootOrPayload : null;
  const payload = rootArg ? (maybePayload || {}) : (rootOrPayload || {});
  const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const normalizeHeader = (value) => normalize(String(value || '').replace(/^[\\s*＊✱✳※]+/, ''));
  const visible = (el) => {
    if (!el || !el.getBoundingClientRect) return false;
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
  };
  const headerSelector = [
    'th',
    '[role="columnheader"]',
    '.wui-table-header th',
    '.wui-table-header [class*="cell"]',
    '.ant-table-header th',
    '.ant-table-header [class*="cell"]',
    '.u-table-header th',
    '.u-table-header [class*="cell"]',
    '.el-table__header th',
    '.el-table__header [class*="cell"]'
  ].join(',');
  const headerIdentityAttributes = [
    'data-field', 'data-index', 'data-data-index', 'data-key',
    'data-column-key', 'data-col-key', 'fieldid', 'data-fieldid', 'name'
  ];
  const headerOwner = (header) => {
    for (let node = header; node && node !== rootArg; node = node.parentElement) {
      const structuralOwner = node.matches('th, [role="columnheader"]');
      const cellBoundary = structuralOwner || /cell/i.test(String(node.className || ''));
      const stableIdentity = headerIdentityAttributes.some(
        (name) => normalize(node.getAttribute && node.getAttribute(name))
      );
      if (cellBoundary && (structuralOwner || stableIdentity)) return node;
    }
    return header;
  };
  const isHeaderCell = (el) => {
    const tag = String(el.tagName || '').toLowerCase();
    const headerRoot = el.closest('.ant-table-header, .wui-table-header, .u-table-header, .el-table__header, thead, [class*="table-header"], [class*="TableHeader"]');
    return tag === 'th' || el.getAttribute('role') === 'columnheader' || Boolean(headerRoot);
  };
  const rootRect = rootArg && rootArg.getBoundingClientRect ? rootArg.getBoundingClientRect() : null;
  const relatedToRoot = (el) => {
    if (!rootArg || rootArg === document || rootArg === document.body || rootArg === document.documentElement) return true;
    if (rootArg.contains(el)) return true;
    if (payload.table || payload.tableFieldid) return false;
    const headerRoot = el.closest('.ant-table-header, .wui-table-header, .u-table-header, .el-table__header, thead, [class*="table-header"], [class*="TableHeader"]');
    if (headerRoot && rootArg.contains(headerRoot)) return true;
    if (!rootRect) return false;
    const rect = el.getBoundingClientRect();
    const overlapsHorizontally = rect.right >= rootRect.left - 20 && rect.left <= rootRect.right + 20;
    const above = rect.bottom <= rootRect.top + 48 && rootRect.top - rect.bottom < 220;
    const nearTop = Math.abs(rect.top - rootRect.top) < 180 && overlapsHorizontally;
    return overlapsHorizontally && (above || nearTop);
  };
  const headerNodes = Array.from(new Set(Array.from(document.querySelectorAll(headerSelector))
    .filter(visible)
    .filter(isHeaderCell)
    .filter(relatedToRoot)
    .map(headerOwner)));
  const headers = headerNodes.map((node) => {
      const text = normalize(node.innerText || node.textContent || node.getAttribute('title') || '');
      const key = normalizeHeader(text);
      const attribute = headerIdentityAttributes.find((name) => normalize(node.getAttribute(name)));
      const identity = attribute ? `${attribute}:${normalize(node.getAttribute(attribute))}` : `text:${key}`;
      return { text, key, identity };
    })
    .filter((item) => item.text && item.key);
  const seen = new Set();
  const result = [];
  for (const item of headers) {
    const key = payload.includeIdentity ? item.identity : item.key;
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(payload.includeIdentity ? { text: item.text, identity: item.identity } : item.text);
  }
  return result;
}
"""

_SCROLL_TABLE_HEADERS_RIGHT_SCRIPT = """
(rootOrPayload, maybePayload) => {
  const rootArg = rootOrPayload instanceof HTMLElement ? rootOrPayload : null;
  const payload = rootArg ? (maybePayload || {}) : (rootOrPayload || {});
  const visible = (el) => {
    if (!el || !el.getBoundingClientRect) return false;
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
  };
  const scope = rootArg && rootArg.querySelectorAll ? rootArg : document;
  const candidates = [
    ...(rootArg && rootArg.scrollWidth > rootArg.clientWidth + 20 ? [rootArg] : []),
    ...Array.from(scope.querySelectorAll(
      '.ant-table-body, .wui-table-body, .u-table-body, .el-table__body-wrapper, [class*="table"][class*="body"], [class*="Table"][class*="body"], div'
    ))
  ]
    .filter(visible)
    .filter((el) => el.scrollWidth > el.clientWidth + 20)
    .filter((el) => payload.restoreScrollLeft || payload.rewindToLeft || el.scrollLeft + el.clientWidth < el.scrollWidth - 2)
    .sort((a, b) => (b.clientWidth * b.clientHeight) - (a.clientWidth * a.clientHeight));
  const target = candidates[0];
  if (!target) return false;
  if (payload.restoreScrollLeft) {
    const initialScrollLeft = Number(target.__ydfBrowserTableHeadersInitialScrollLeft);
    delete target.__ydfBrowserTableHeadersInitialScrollLeft;
    if (!Number.isFinite(initialScrollLeft)) return false;
    target.scrollLeft = initialScrollLeft;
    return true;
  }
  if (payload.rewindToLeft) {
    const before = target.scrollLeft;
    if (before <= 0) return false;
    if (payload.rememberScrollLeft && target.__ydfBrowserTableHeadersInitialScrollLeft === undefined) {
      target.__ydfBrowserTableHeadersInitialScrollLeft = before;
    }
    target.scrollLeft = 0;
    return target.scrollLeft < before;
  }
  const before = target.scrollLeft;
  if (payload.rememberScrollLeft && target.__ydfBrowserTableHeadersInitialScrollLeft === undefined) {
    target.__ydfBrowserTableHeadersInitialScrollLeft = before;
  }
  target.scrollLeft = Math.min(target.scrollWidth, before + Math.max(160, Math.floor(target.clientWidth * 0.8)));
  return target.scrollLeft > before;
}
"""


_TABLE_COLUMN_VISIBLE_SCRIPT = """
(columnName) => {
  const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const visible = (el) => {
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0
      && rect.right > 0 && rect.left < window.innerWidth;
  };
  const expected = normalize(String(columnName || '').replace(/^[*＊]+/, ''));
  if (!expected) return true;
  return Array.from(document.querySelectorAll('th, [role="columnheader"], .ant-table-cell, .wui-table-cell, .u-table-cell'))
    .filter(visible)
    .some((header) => {
      const text = normalize((header.innerText || header.textContent || '').replace(/^[*＊]+/, ''));
      return text === expected || text.split(' ')[0] === expected;
    });
}
"""


_SCROLL_TABLE_RIGHT_SCRIPT = """
() => {
  const candidates = Array.from(document.querySelectorAll(
    '.ant-table-body, .wui-table-body, .u-table-body, [class*="table"][class*="body"], [class*="Table"][class*="body"], div'
  ));
  for (const el of candidates) {
    const style = window.getComputedStyle(el);
    const canScroll = el.scrollWidth > el.clientWidth + 20 && style.display !== 'none' && style.visibility !== 'hidden';
    if (!canScroll) continue;
    const before = el.scrollLeft;
    el.scrollLeft = Math.min(el.scrollLeft + Math.max(240, el.clientWidth * 0.75), el.scrollWidth);
    if (el.scrollLeft > before) return true;
  }
  return false;
}
"""


_SCROLL_TABLE_LEFT_SCRIPT = """
(root) => {
  const scope = root instanceof HTMLElement ? root : document;
  const candidates = [
    ...(scope.matches && scope.matches('.ant-table-body, .wui-table-body, .u-table-body, .ant-table-header, .wui-table-header, .u-table-header') ? [scope] : []),
    ...Array.from(scope.querySelectorAll(
    '.ant-table-body, .wui-table-body, .u-table-body, .ant-table-header, .wui-table-header, .u-table-header, [class*="table"][class*="body"], [class*="Table"][class*="body"], [class*="table"][class*="header"], div'
    )),
  ];
  let moved = false;
  for (const el of candidates) {
    const style = window.getComputedStyle(el);
    const canScroll = el.scrollWidth > el.clientWidth + 20 && style.display !== 'none' && style.visibility !== 'hidden';
    if (!canScroll) continue;
    const before = el.scrollLeft;
    el.scrollLeft = 0;
    if (el.scrollLeft < before) moved = true;
  }
  return moved;
}
"""


_SCROLL_TABLE_DOWN_SCRIPT = """
(root) => {
  const scope = root instanceof HTMLElement ? root : document;
  const candidates = [
    ...(scope.matches && scope.matches('.ant-table-body, .wui-table-body, .u-table-body') ? [scope] : []),
    ...Array.from(scope.querySelectorAll(
    '.ant-table-body, .wui-table-body, .u-table-body, [class*="table"][class*="body"], [class*="Table"][class*="body"], div'
    )),
  ];
  for (const el of candidates) {
    const style = window.getComputedStyle(el);
    const canScroll = el.scrollHeight > el.clientHeight + 20 && style.display !== 'none' && style.visibility !== 'hidden';
    if (!canScroll) continue;
    const before = el.scrollTop;
    el.scrollTop = Math.min(el.scrollTop + Math.max(240, el.clientHeight * 0.75), el.scrollHeight);
    if (el.scrollTop > before) return true;
  }
  return false;
}
"""


_TABLE_FIELDID_ROOT_SELECTOR_SCRIPT = """
(payload) => {
  const fieldids = Array.isArray(payload && payload.fieldids)
    ? payload.fieldids.map((item) => String(item || '').trim()).filter(Boolean)
    : [];
  const marker = payload && payload.marker ? String(payload.marker) : `table-fieldid-selection-${Date.now()}`;
  const requireSelectableRows = payload && payload.requireSelectableRows !== false;
  const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const expectedColumns = Array.isArray(payload && payload.columns)
    ? payload.columns.map((item) => normalize(String(item || ''))).filter(Boolean)
    : [];
  const cssEscapeSafe = (value) => {
    if (window.CSS && typeof window.CSS.escape === 'function') return window.CSS.escape(value);
    return String(value).replace(/"/g, '\\\\"');
  };
  const visible = (el) => {
    if (!el || !el.getBoundingClientRect) return false;
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
  };
  const rowSelector = 'tbody tr, [role="row"], .ant-table-row, .wui-table-row, .u-table-row';
  const checkboxSelector = [
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
  ].join(',');
  const rowCount = (root) => root.querySelectorAll(rowSelector).length;
  const selectableRowCount = (root) => Array.from(root.querySelectorAll(rowSelector))
    .filter(visible)
    .filter((row) => row.querySelector(checkboxSelector))
    .length;
  const cellSelector = 'td, [role="gridcell"], [role="cell"], .ant-table-cell, .wui-table-cell, .u-table-cell, .el-table__cell';
  const businessRow = (row) => {
    if (!visible(row)) return false;
    if (row.closest('thead, tfoot, .ant-table-thead, .wui-table-thead, .u-table-thead, .ant-table-footer, .wui-table-footer, .u-table-footer')) return false;
    const className = String(row.className || '');
    if (/(summary|footer|total|subtotal)/i.test(className)) return false;
    const text = normalize(row.innerText || row.textContent);
    const compactText = text.replace(/\\s+/g, '');
    if (!text) return false;
    if (/暂无数据|点击上方查询条件搜索数据/.test(text)) return false;
    if (/^(小计|合计|汇总|总计)(\\s|$)/.test(text) || /^(小计|合计|汇总|总计)/.test(compactText)) return false;
    return Boolean(row.querySelector(cellSelector));
  };
  const rowReceivesPointer = (row) => {
    const cells = Array.from(row.querySelectorAll(cellSelector))
      .filter(visible)
      .filter((item) => !item.closest('thead, .ant-table-header, .wui-table-header, .u-table-header, .el-table__header'));
    for (const cell of cells) {
      const rect = cell.getBoundingClientRect();
      const points = [
        [rect.left + Math.min(Math.max(rect.width / 2, 8), 24), rect.top + rect.height / 2],
        [rect.left + rect.width / 2, rect.top + rect.height / 2],
      ];
      for (const [x, y] of points) {
        if (x < 0 || y < 0 || x > window.innerWidth || y > window.innerHeight) continue;
        const top = document.elementFromPoint(x, y);
        if (top && (cell === top || cell.contains(top) || top.contains(cell))) return true;
      }
    }
    return false;
  };
  const receivableRowCount = (root) => Array.from(root.querySelectorAll(rowSelector))
    .filter(businessRow)
    .filter(rowReceivesPointer)
    .length;
  const headerNames = (root) => Array.from(root.querySelectorAll(
      'th, [role="columnheader"], .ant-table-cell, .wui-table-cell, .u-table-cell, .el-table__cell, [data-field], [data-data-field]'
    ))
    .filter(visible)
    .map((item) => normalize(item.innerText || item.textContent || item.getAttribute('title') || item.getAttribute('aria-label') || ''))
    .filter(Boolean);
  const matchedColumnCount = (root) => {
    if (!expectedColumns.length) return 0;
    const headers = headerNames(root);
    return expectedColumns.filter((expected) => headers.some((header) => header === expected || header.includes(expected))).length;
  };
  __TABLE_ROOT_FUNCTIONS__
  const tableRoots = Array.from(document.querySelectorAll('.wui-table, .ant-table, .u-table, .el-table, [role="grid"], table, [class*="Table"], [class*="table"]'))
    .filter((root) => root.querySelector && root.querySelector(rowSelector));
  const nestedTableRootCount = (root) => tableRoots.filter((other) => other !== root && root.contains(other)).length;
  const selectors = fieldids.flatMap((fieldid) => [
    `[fieldid="${cssEscapeSafe(fieldid)}"]`,
    `[data-fieldid="${cssEscapeSafe(fieldid)}"]`,
    `[data-field-id="${cssEscapeSafe(fieldid)}"]`
  ]);
  const candidates = [];
  const seen = new Set();
  for (const [fieldidIndex, fieldid] of fieldids.entries()) {
    const fieldSelectors = [
      `[fieldid="${cssEscapeSafe(fieldid)}"]`,
      `[data-fieldid="${cssEscapeSafe(fieldid)}"]`,
      `[data-field-id="${cssEscapeSafe(fieldid)}"]`
    ];
    for (const selector of fieldSelectors) {
      for (const root of Array.from(document.querySelectorAll(selector))) {
        if (!visible(root) || seen.has(root)) continue;
        seen.add(root);
        const clusterRoot = splitTableClusterRoot(root);
        const rows = rowCount(clusterRoot);
        const selectableRows = selectableRowCount(clusterRoot);
        const receivableRows = receivableRowCount(clusterRoot);
        const columnsMatched = matchedColumnCount(clusterRoot);
        if (requireSelectableRows && selectableRows <= 0 && receivableRows <= 0 && columnsMatched <= 0) continue;
        const rect = clusterRoot.getBoundingClientRect();
        candidates.push({
          root,
          clusterRoot,
          fieldid,
          fieldidIndex,
          tag: String(clusterRoot.tagName || '').toLowerCase(),
          className: String(clusterRoot.className || '').slice(0, 160),
          rows,
          selectableRows,
          receivableRows,
          columnsMatched,
          nestedTables: nestedTableRootCount(clusterRoot),
          area: rect.width * rect.height,
          text: normalize(clusterRoot.innerText || clusterRoot.textContent || '').slice(0, 80),
        });
      }
    }
  }
  if (!candidates.length) return { selector: '', fieldids, source: 'fieldid', tables: selectors };
  candidates.sort((a, b) =>
    a.fieldidIndex - b.fieldidIndex
    || b.receivableRows - a.receivableRows
    || b.columnsMatched - a.columnsMatched
    || b.selectableRows - a.selectableRows
    || a.nestedTables - b.nestedTables
    || a.area - b.area
  );
  for (const root of candidates.map((item) => item.clusterRoot)) {
    root.removeAttribute('data-ydf-browser-table-selection-root');
  }
  const selected = candidates[0];
  selected.clusterRoot.setAttribute('data-ydf-browser-table-selection-root', marker);
  return {
    selector: `[data-ydf-browser-table-selection-root="${marker}"]`,
    fieldids,
    fieldid: selected.fieldid,
    source: selected.fieldid.endsWith('_drag') ? 'fieldid_drag' : 'fieldid',
    tag: selected.tag,
    className: selected.className,
    rows: selected.rows,
    selectableRows: selected.selectableRows,
    receivableRows: selected.receivableRows,
    columnsMatched: selected.columnsMatched,
    text: selected.text,
  };
}
""".replace("__TABLE_ROOT_FUNCTIONS__", _TABLE_ROOT_FUNCTIONS)


_TABLE_SELECTION_ROOT_SELECTOR_SCRIPT = """
(payload) => {
  const tableName = (payload && payload.table ? String(payload.table) : '').replace(/\\s+/g, ' ').trim();
  const columnNames = Array.isArray(payload && payload.columns)
    ? payload.columns.map((item) => String(item || '').replace(/\\s+/g, ' ').trim()).filter(Boolean)
    : [];
  const marker = payload && payload.marker ? String(payload.marker) : `table-selection-${Date.now()}`;
  const requireSelectableRows = payload && payload.requireSelectableRows !== false;
  const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const visible = (el) => {
    if (!el || !el.getBoundingClientRect) return false;
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
  };
  const unique = (items) => Array.from(new Set(items.filter(Boolean)));
  const tableRoots = unique([
    ...Array.from(document.querySelectorAll('.wui-table, .ant-table, .u-table, .el-table, [role="grid"], table')),
    ...Array.from(document.querySelectorAll('[class*="Table"], [class*="table"]'))
      .filter((el) => el.querySelector('tbody tr, [role="row"], .ant-table-row, .wui-table-row, .u-table-row')),
  ]).filter(visible);
  const labelNodes = Array.from(document.querySelectorAll('span, div, label, h1, h2, h3, h4, legend'))
    .filter(visible)
    .map((node) => ({ node, text: normalize(node.innerText || node.textContent || '') }))
    .filter((item) => item.text && item.text.includes(tableName));
  const rowSelector = 'tbody tr, [role="row"], .ant-table-row, .wui-table-row, .u-table-row';
  const checkboxSelector = [
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
  ].join(',');
  const rowCount = (root) => root.querySelectorAll(rowSelector).length;
  const selectableRowCount = (root) => Array.from(root.querySelectorAll(rowSelector))
    .filter(visible)
    .filter((row) => row.querySelector(checkboxSelector))
    .length;
  __TABLE_ROOT_FUNCTIONS__
  const nestedTableRootCount = (root) => tableRoots.filter((other) => other !== root && root.contains(other)).length;
  const headerSelector = [
    'th',
    '[role="columnheader"]',
    '.wui-table-header th',
    '.wui-table-header [class*="cell"]',
    '.ant-table-header th',
    '.ant-table-header [class*="cell"]',
    '.u-table-header th',
    '.u-table-header [class*="cell"]'
  ].join(',');
  const headerTextsNearRoot = (root) => {
    const rect = root.getBoundingClientRect();
    const headers = Array.from(document.querySelectorAll(headerSelector))
      .filter(visible)
      .map((node) => ({ node, rect: node.getBoundingClientRect(), text: normalize(node.innerText || node.textContent || '') }))
      .filter((item) => item.text);
    return headers
      .filter((item) => {
        if (root.contains(item.node)) return true;
        const overlapsHorizontally = item.rect.right >= rect.left - 20 && item.rect.left <= rect.right + 20;
        const above = item.rect.bottom <= rect.top + 36 && rect.top - item.rect.bottom < 180;
        return overlapsHorizontally && above;
      })
      .sort((a, b) => Math.abs(rect.top - a.rect.bottom) - Math.abs(rect.top - b.rect.bottom))
      .map((item) => item.text);
  };
  const columnScoreRoot = (root) => {
    if (!columnNames.length) return 0;
    const headers = headerTextsNearRoot(root);
    if (!headers.length) return 0;
    let score = 0;
    let matched = 0;
    for (const expected of columnNames) {
      if (headers.includes(expected)) {
        score += 180;
        matched += 1;
        continue;
      }
      if (expected.length >= 2 && headers.some((header) => header.includes(expected) || expected.includes(header))) {
        score += 45;
        matched += 1;
      }
    }
    if (!matched) return 0;
    return score + Math.min(120, matched * 20);
  };
  const scoreRoot = (root) => {
    const rect = root.getBoundingClientRect();
    const rootText = normalize(root.innerText || root.textContent || '');
    let score = 0;
    if (rootText === tableName) score += 120;
    else if (rootText.includes(tableName)) score += 45;
    for (const item of labelNodes) {
      const label = item.node;
      const labelRect = label.getBoundingClientRect();
      const overlapsHorizontally = labelRect.right >= rect.left - 20 && labelRect.left <= rect.right + 20;
      const inside = root.contains(label);
      const wrapsRoot = label.contains(root);
      const above = labelRect.bottom <= rect.top + 12 && rect.top - labelRect.bottom < 220 && overlapsHorizontally;
      if (inside || wrapsRoot || above) {
        score += item.text === tableName ? 140 : 100;
      }
      if (above) score += Math.max(0, 80 - Math.abs(rect.top - labelRect.bottom));
    }
    const columnScore = columnScoreRoot(root);
    if (columnScore > 0) score += 100 + columnScore;
    if (root.matches('.wui-table, .ant-table, .u-table, .el-table, table, [role="grid"]')) score += 10;
    if (rowCount(root) > 0) score += 10;
    score -= Math.min(420, nestedTableRootCount(root) * 120);
    return score;
  };
  const candidates = tableRoots
    .map((root) => {
      const clusterRoot = splitTableClusterRoot(root);
      return {
        root,
        clusterRoot,
        tag: String(clusterRoot.tagName || '').toLowerCase(),
        className: String(clusterRoot.className || '').slice(0, 160),
        score: scoreRoot(root),
        rows: rowCount(clusterRoot),
        selectableRows: selectableRowCount(clusterRoot),
        text: normalize(clusterRoot.innerText || clusterRoot.textContent || '').slice(0, 80),
      };
    })
    .filter((item) => item.score > 0 && (!requireSelectableRows || item.selectableRows > 0))
    .sort((a, b) => b.score - a.score || b.selectableRows - a.selectableRows || b.rows - a.rows);
  const debugTables = tableRoots
    .map((root) => normalize(root.innerText || root.textContent || '').slice(0, 40))
    .filter(Boolean)
    .slice(0, 12);
  if (!candidates.length) return { selector: '', tables: debugTables };
  for (const root of candidates.map((item) => item.clusterRoot)) root.removeAttribute('data-ydf-browser-table-selection-root');
  const selected = candidates[0];
  selected.clusterRoot.setAttribute('data-ydf-browser-table-selection-root', marker);
  return {
    selector: `[data-ydf-browser-table-selection-root="${marker}"]`,
    tables: debugTables,
    tag: selected.tag,
    className: selected.className,
    score: selected.score,
    rows: selected.rows,
    selectableRows: selected.selectableRows,
    text: selected.text,
  };
}
""".replace("__TABLE_ROOT_FUNCTIONS__", _TABLE_ROOT_FUNCTIONS)


_CHECKBOX_SELECTION_STATE_SCRIPT = """
(node) => {
  const normalize = (value) => String(value || '').toLowerCase();
  const classText = normalize([
    node && node.className,
    node && node.parentElement && node.parentElement.className,
    node && node.closest && node.closest('label, [class*="checkbox"], [class*="Checkbox"]') && node.closest('label, [class*="checkbox"], [class*="Checkbox"]').className,
  ].join(' '));
  const input = node && node.matches && node.matches('input[type="checkbox"]')
    ? node
    : (node && node.querySelector && node.querySelector('input[type="checkbox"]'));
  if (input) {
    if (input.indeterminate === true) return 'mixed';
    if (input.checked === true) return 'checked';
  }
  const aria = normalize(node && node.getAttribute && node.getAttribute('aria-checked'));
  if (aria === 'mixed') return 'mixed';
  if (aria === 'true') return 'checked';
  if (/(indeterminate|mixed|half|partial)/.test(classText)) return 'mixed';
  if (/(^|\\s|_|-)(checked|is-checked)($|\\s|_|-)/.test(classText)) return 'checked';
  if (/(ant-checkbox-checked|wui-checkbox-checked|u-checkbox-checked|el-checkbox-checked)/.test(classText)) return 'checked';
  return 'unchecked';
}
"""


_ROW_CHECKBOX_SELECTION_STATE_SCRIPT = """
(node) => {
  const normalize = (value) => String(value || '').toLowerCase();
  const selectedClass = (el) => {
    const classText = normalize([
      el && el.className,
      el && el.parentElement && el.parentElement.className,
      el && el.closest && el.closest('label, [class*="checkbox"], [class*="Checkbox"]') && el.closest('label, [class*="checkbox"], [class*="Checkbox"]').className,
    ].join(' '));
    if (/(indeterminate|mixed|half|partial)/.test(classText)) return 'mixed';
    if (/(^|\\s|_|-)(checked|is-checked)($|\\s|_|-)/.test(classText)) return 'checked';
    if (/(ant-checkbox-checked|wui-checkbox-checked|u-checkbox-checked|el-checkbox-checked)/.test(classText)) return 'checked';
    return '';
  };
  const stateOf = (candidate) => {
    const input = candidate && candidate.matches && candidate.matches('input[type="checkbox"]')
      ? candidate
      : (candidate && candidate.querySelector && candidate.querySelector('input[type="checkbox"]'));
    if (input) {
      if (input.indeterminate === true) return 'mixed';
      if (input.checked === true) return 'checked';
    }
    const aria = normalize(candidate && candidate.getAttribute && candidate.getAttribute('aria-checked'));
    if (aria === 'mixed') return 'mixed';
    if (aria === 'true') return 'checked';
    return selectedClass(candidate);
  };
  const row = node && (node.closest && node.closest('tr, [role="row"], .wui-table-row, .ant-table-row, .u-table-row, .el-table__row')) || node;
  const candidates = row && row.querySelectorAll
    ? Array.from(row.querySelectorAll('input[type="checkbox"], [role="checkbox"], label[class*="checkbox"], span[class*="checkbox"], div[class*="checkbox"]'))
    : [];
  for (const candidate of candidates) {
    const state = stateOf(candidate);
    if (state === 'checked' || state === 'mixed') return state;
  }
  return 'unchecked';
}
"""


_TABLE_DEBUG_SCRIPT = """
() => {
  const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const visible = (el) => {
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style && style.visibility !== 'hidden' && style.display !== 'none' && rect.width > 0 && rect.height > 0;
  };
  const headers = Array.from(document.querySelectorAll('th, [role="columnheader"], .ant-table-cell, .wui-table-cell, .u-table-cell'))
    .filter(visible)
    .map((el) => normalize(el.innerText || el.textContent || ''))
    .filter(Boolean)
    .slice(0, 80);
  const rows = Array.from(document.querySelectorAll('tbody tr, [role="row"], .ant-table-row, .wui-table-row, .u-table-row'))
    .filter(visible)
    .map((el) => normalize(el.innerText || el.textContent || ''))
    .filter(Boolean)
    .slice(0, 20);
  const scrollables = Array.from(document.querySelectorAll('div'))
    .filter((el) => el.scrollWidth > el.clientWidth + 20)
    .map((el) => ({ className: String(el.className || '').slice(0, 120), left: el.scrollLeft, width: el.clientWidth, scrollWidth: el.scrollWidth }))
    .slice(0, 20);
  return { headers, rows, scrollables };
}
"""
