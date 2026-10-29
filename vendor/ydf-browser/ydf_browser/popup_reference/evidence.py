from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from ..observation import redact_url
from .model import PopupReferenceError
from .selection import build_popup_reference_trigger_selectors

def _network_event_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "url": redact_url(str(item.get("url") or "")),
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


class EvidenceStage:
    _last_popup_reference_open_debug: dict[str, Any] | None

    def _save_diagnostic_screenshot(self, name: str) -> str:
        if self.observation_session is not None:
            return ""
        target = Path("/tmp") / f"ydf-browser-{name}-{int(time.time())}.png"
        try:
            self._require_page().screenshot(path=str(target), full_page=True, timeout=5000)
        except Exception:
            return ""
        reference = str(target)
        self.diagnostic_files.append(reference)
        self._request_diagnostic_refs.append(reference)
        return reference

    def _save_diagnostic_json(self, name: str, payload: dict[str, Any]) -> str:
        target = Path("/tmp") / f"ydf-browser-{name}-{int(time.time())}.json"
        try:
            target.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception:
            return ""
        reference = str(target)
        self.diagnostic_files.append(reference)
        self._request_diagnostic_refs.append(reference)
        return reference

    def _popup_reference_diag_enabled(self) -> bool:
        return str(os.environ.get("YDF_BROWSER_POPUP_DIAG") or "").strip().lower() in {"1", "true", "yes", "on"}

    def _collect_popup_reference_open_debug(self, root, *, phase: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "phase": phase,
            "enabled": True,
            "network_start_index": len(self._network_events),
            "dialog_counts_before": self._safe_visible_popup_reference_dialog_counts(),
            "active_element_before": self._safe_active_element_debug(),
            "root": self._safe_popup_reference_root_debug(root),
            "console_recent": list(self._console_events[-10:]),
            "page_errors_recent": list(self._page_errors[-10:]),
        }
        return payload

    def _record_popup_reference_clicked_target(
        self,
        locator,
        *,
        source: str,
        selector: str = "",
        index: int | None = None,
    ) -> None:
        if not self._popup_reference_diag_enabled():
            return
        debug = self._last_popup_reference_open_debug or {"enabled": True, "network_start_index": len(self._network_events)}
        target = self._safe_locator_debug(locator)
        target.update({"source": source})
        if selector:
            target["selector"] = selector
        if index is not None:
            target["index"] = index
        debug["clicked_target"] = target
        self._last_popup_reference_open_debug = debug

    def _record_popup_reference_click_error(self, error: Exception) -> None:
        if not self._popup_reference_diag_enabled():
            return
        debug = self._last_popup_reference_open_debug or {"enabled": True, "network_start_index": len(self._network_events)}
        debug["click_error"] = str(error)[:1000]
        self._last_popup_reference_open_debug = debug

    def _record_popup_reference_after_click(self) -> None:
        if not self._popup_reference_diag_enabled():
            return
        page = self._require_page()
        debug = self._last_popup_reference_open_debug or {"enabled": True, "network_start_index": len(self._network_events)}
        debug["active_element_after_500ms"] = self._safe_active_element_debug()
        debug["dialog_counts_after_500ms"] = self._safe_visible_popup_reference_dialog_counts()
        try:
            self._wait_for_timeout(1500)
        except PopupReferenceError:
            raise
        except Exception:
            pass
        debug["active_element_after_2000ms"] = self._safe_active_element_debug()
        debug["dialog_counts_after_2000ms"] = self._safe_visible_popup_reference_dialog_counts()
        self._last_popup_reference_open_debug = debug

    def _safe_visible_popup_reference_dialog_counts(self) -> dict[str, Any]:
        try:
            return dict(self._visible_popup_reference_dialog_counts())
        except Exception as exc:
            return {"error": str(exc)[:500]}

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

    def _safe_popup_reference_root_debug(self, root) -> dict[str, Any]:
        try:
            return dict(
                root.evaluate(
                    r"""(node, args) => {
                        const normalize = (value) => String(value || '').replace(/\s+/g, ' ').trim();
                        const rectPayload = (el) => {
                          const rect = el.getBoundingClientRect();
                          return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
                        };
                        const visible = (el) => {
                          const style = window.getComputedStyle(el);
                          const rect = el.getBoundingClientRect();
                          return style && style.visibility !== 'hidden' && style.display !== 'none'
                            && rect.width > 0 && rect.height > 0;
                        };
                        const receivesPointer = (el) => {
                          const rect = el.getBoundingClientRect();
                          const x = rect.left + rect.width / 2;
                          const y = rect.top + rect.height / 2;
                          const hit = document.elementFromPoint(x, y);
                          return Boolean(hit && (hit === el || el.contains(hit) || hit.contains(el)));
                        };
                        const skip = /(clear|close|remove|delete|calendar|date)/i;
                        const marker = /(refer|reference|ref|参照|选择|search|sousuo|fangdajing|canzhao|arrow)/i;
                        const explicitPopupClass = /(?:^|\s)(?:modal-btn|icon-only|ydf-select-btn)(?:\s|$)/i;
                        const triggerRank = (el) => {
                          const tag = String(el.tagName || '').toLowerCase();
                          const cls = String(el.className || '').toLowerCase();
                          const fieldid = String(el.getAttribute('fieldid') || '').toLowerCase();
                          const role = String(el.getAttribute('role') || '').toLowerCase();
                          const text = [
                            cls,
                            fieldid,
                            role,
                            el.getAttribute('title'),
                            el.getAttribute('aria-label'),
                            el.innerText,
                            el.textContent,
                          ].join(' ').toLowerCase();
                          let score = 0;
                          if (tag === 'button' || role === 'button') score += 1000;
                          if (/modal-btn|wui-button|icon-only/.test(cls)) score += 600;
                          if (/_btn(?:_|$)|_btn_icon$/.test(fieldid)) score += 500;
                          if (/refer|reference|ref|参照|选择|sousuo|fangdajing|canzhao|icon/.test(text)) score += 200;
                          if (/select-selection-search|show-search|combobox/.test(cls) || tag === 'input') score -= 700;
                          return score;
                        };
                        const candidateInfo = (el, selector) => {
                          const textParts = [
                            el.className,
                            el.getAttribute('title'),
                            el.getAttribute('aria-label'),
                            el.innerText,
                            el.textContent,
                            el.getAttribute('role'),
                            el.getAttribute('aria-haspopup'),
                          ].join(' ');
                          const style = window.getComputedStyle(el);
                          return {
                            selector,
                            tag: el.tagName,
                            class: String(el.className || ''),
                            id: el.id || '',
                            fieldid: el.getAttribute('fieldid') || '',
                            role: el.getAttribute('role') || '',
                            title: el.getAttribute('title') || '',
                            aria_label: el.getAttribute('aria-label') || '',
                            text: normalize(el.innerText || el.textContent).slice(0, 300),
                            visible: visible(el),
                            disabled: Boolean(el.disabled || el.getAttribute('aria-disabled') === 'true'),
                            marker_match: !skip.test(textParts) && (
                              marker.test(textParts)
                              || explicitPopupClass.test(String(el.className || ''))
                              || /dialog|tree|menu/.test(String(el.getAttribute('aria-haspopup') || '').toLowerCase())
                              || /input-suffix|select-arrow|icon-(sousuo|search|fangdajing|canzhao)/i.test(String(el.className || ''))
                            ),
                            skip_match: skip.test(textParts),
                            trigger_rank: triggerRank(el),
                            receives_pointer: receivesPointer(el),
                            rect: rectPayload(el),
                          };
                        };
                        const all = [];
                        for (const selector of args.selectors) {
                          for (const el of Array.from(node.querySelectorAll(selector))) {
                            if (!all.some((item) => item.el === el)) {
                              all.push({ el, selector });
                            }
                          }
                        }
                        const candidates = all
                          .map((item) => candidateInfo(item.el, item.selector))
                          .filter((item) => item.visible)
                          .sort((a, b) => b.trigger_rank - a.trigger_rank
                            || (b.rect.x + b.rect.width) - (a.rect.x + a.rect.width)
                            || (a.rect.width * a.rect.height) - (b.rect.width * b.rect.height))
                          .slice(0, 20);
                        return {
                          tag: node.tagName,
                          class: String(node.className || ''),
                          id: node.id || '',
                          fieldid: node.getAttribute('fieldid') || '',
                          uikey: node.getAttribute('uikey') || '',
                          role: node.getAttribute('role') || '',
                          title: node.getAttribute('title') || '',
                          text: normalize(node.innerText || node.textContent).slice(0, 500),
                          html: String(node.outerHTML || '').slice(0, 2000),
                          rect: rectPayload(node),
                          url: document.location.href,
                          trigger_candidates: candidates,
                        };
                    }""",
                    {"selectors": build_popup_reference_trigger_selectors()},
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

    def _popup_reference_open_debug_payload(
        self,
        *,
        reason: str,
        diagnostic: str = "",
        screenshot: str = "",
    ) -> dict[str, Any]:
        debug = dict(self._last_popup_reference_open_debug or {})
        start = int(debug.get("network_start_index") or 0)
        network_events = self._network_events[start:] if start >= 0 else []
        debug.update(
            {
                "reason": reason,
                "diagnostic": diagnostic,
                "screenshot": screenshot,
                "dialog_counts_at_failure": self._safe_visible_popup_reference_dialog_counts(),
                "active_element_at_failure": self._safe_active_element_debug(),
                "console_recent": list(self._console_events[-20:]),
                "page_errors_recent": list(self._page_errors[-20:]),
                "network_delta": [_network_event_payload(item) for item in network_events[-50:]],
            }
        )
        return debug

    def _collect_popup_reference_table_match_debug(self, dialog, match: dict[str, Any]) -> str:
        try:
            result = dialog.evaluate(
                """(root, match) => {
                    const normalize = (text) => String(text || '').replace(/\\s+/g, ' ').trim();
                    const visible = (el) => {
                      const style = window.getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style && style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width > 0 && rect.height > 0;
                    };
                    const textOf = (el) => normalize(el?.getAttribute?.('title') || el?.innerText || el?.textContent || '');
                    const rowSelector = [
                      'tbody tr',
                      '.wui-table-tbody .wui-table-row',
                      '.wui-table-body .wui-table-row',
                      '.ant-table-tbody .ant-table-row',
                      '.u-table-tbody .u-table-row',
                      '[role="grid"] [role="row"]',
                      '[class*="table-body"] [class*="table-row"]',
                      '[class*="TableBody"] [class*="TableRow"]'
                    ].join(',');
                    const broadRowSelector = [
                      'tbody tr',
                      'tr',
                      '.w-table-row',
                      '.wui-table-row',
                      '.ant-table-row',
                      '.u-table-row',
                      '[role="row"]',
                      '[class*="table"] [class*="row"]',
                      '[class*="Table"] [class*="Row"]'
                    ].join(',');
                    const cellSelector = [
                      'td',
                      '[role="gridcell"]',
                      '[role="cell"]',
                      '.w-table-cell',
                      '.wui-table-cell',
                      '.ant-table-cell',
                      '.u-table-cell'
                    ].join(',');
                    const headerSelector = [
                      'thead th',
                      '[role="columnheader"]',
                      '.w-table-thead th',
                      '.w-table-header .w-table-cell',
                      '.wui-table-thead th',
                      '.ant-table-thead th',
                      '.u-table-thead th',
                      '[class*="table"] [class*="header"] [class*="cell"]',
                      '[class*="Table"] [class*="Header"] [class*="Cell"]'
                    ].join(',');
                    const pickerSelector = [
                      'input[type="radio"]',
                      'input[type="checkbox"]',
                      '[role="radio"]',
                      '[role="checkbox"]',
                      '.wui-radio',
                      '.wui-checkbox',
                      '.ant-radio',
                      '.ant-checkbox',
                      '.u-radio',
                      '.u-checkbox',
                      '[class*="radio"]',
                      '[class*="Radio"]',
                      '[class*="checkbox"]',
                      '[class*="Checkbox"]'
                    ].join(',');
                    const compactNode = (node) => ({
                      tag: node.tagName,
                      cls: String(node.className || '').slice(0, 120),
                      text: textOf(node).slice(0, 300),
                    });
                    const strictRows = Array.from(root.querySelectorAll(rowSelector))
                      .filter((el, index, all) => all.indexOf(el) === index)
                      .filter((el) => visible(el) && !el.closest('thead'));
                    const broadRows = Array.from(root.querySelectorAll(broadRowSelector))
                      .filter((el, index, all) => all.indexOf(el) === index)
                      .filter((el) => visible(el) && !el.closest('thead'));
                    const headers = Array.from(root.querySelectorAll(headerSelector)).filter(visible).map(textOf).slice(0, 30);
                    const wantedValue = match.equals || match.value || match.text || match.label || match.contains || '';
                    const rows = broadRows
                      .filter((row) => textOf(row).includes(String(wantedValue)))
                      .slice(0, 5)
                      .map((row) => ({
                        ...compactNode(row),
                        strict: strictRows.includes(row),
                        cells: Array.from(row.querySelectorAll(cellSelector)).filter(visible).map(textOf).slice(0, 20),
                        pickers: Array.from(row.querySelectorAll(pickerSelector)).slice(0, 8).map((item) => ({
                          ...compactNode(item),
                          visible: visible(item),
                          checked: item.checked === true,
                          ariaChecked: item.getAttribute('aria-checked'),
                          ariaSelected: item.getAttribute('aria-selected'),
                        })),
                      }));
                    return {
                      wantedColumn: match.column || match.field || '',
                      wantedValue,
                      headerCount: headers.length,
                      headers,
                      strictRowCount: strictRows.length,
                      broadRowCount: broadRows.length,
                      rows,
                    };
                }""",
                match,
            )
            return json.dumps(result, ensure_ascii=False)[:2000]
        except Exception:
            return ""

    def _collect_popup_reference_selection_debug(self, dialog) -> str:
        try:
            script = """(root) => {
                    const normalize = (text) => String(text || '').replace(/\\s+/g, ' ').trim();
                    const visible = (el) => {
                      const style = window.getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style && style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width > 0 && rect.height > 0;
                    };
                    const rows = Array.from(root.querySelectorAll('tbody tr, .wui-table-row, .ant-table-row, .u-table-row, [role="row"]'))
                      .filter((row, index, all) => all.indexOf(row) === index)
                      .filter((row) => visible(row) && !row.closest('thead'))
                      .slice(0, 5)
                      .map((row) => ({
                        text: normalize(row.innerText || row.textContent).slice(0, 300),
                        cls: String(row.className || '').slice(0, 120),
                        checked: row.querySelectorAll('input:checked, [aria-checked="true"], [aria-selected="true"], [class*="checked"], [class*="selected"]').length,
                        inputs: Array.from(row.querySelectorAll('input[type="radio"], input[type="checkbox"]')).map((input) => ({
                          checked: input.checked === true,
                          cls: String(input.className || '').slice(0, 80),
                          ariaChecked: input.getAttribute('aria-checked'),
                        })),
                      }));
                    return {
                      checkedCount: root.querySelectorAll('input:checked, [aria-checked="true"], [aria-selected="true"]').length,
                      selectedClassCount: root.querySelectorAll('[class*="checked"], [class*="selected"]').length,
                      selectedText: normalize(root.innerText || root.textContent).match(/已选择\\s*\\d+\\s*条/)?.[0] || '',
                      rows,
                    };
                }"""
            try:
                result = dialog.evaluate(script, timeout=1500)
            except TypeError:
                result = dialog.evaluate(script)
            return json.dumps(result, ensure_ascii=False)[:1600]
        except Exception:
            return ""

    def _collect_popup_reference_diagnostic_text(self, dialog) -> str:
        try:
            text = " ".join((dialog.inner_text(timeout=1000) or "").split())
            if text:
                return text[:800]
        except Exception:
            pass
        return self._collect_choice_diagnostic_text()
