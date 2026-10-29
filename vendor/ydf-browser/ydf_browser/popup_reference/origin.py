from __future__ import annotations

import json
import re
import time
from types import SimpleNamespace
from typing import Any

from ..models import BoundElement
from .model import PopupReferenceError
from .selection import (
    _candidate_has_enum_type,
    _candidate_raw_claims_reference,
    build_popup_reference_trigger_selectors,
)

class OriginStage:
    def _looks_like_popup_reference_field(self, locator, bound_element: BoundElement) -> bool:
        runtime = getattr(bound_element, "runtime", None)
        candidate = getattr(bound_element, "candidate", None)
        component_name = str(getattr(candidate, "component_name", "") or getattr(runtime, "name", "") or "")
        normalized_component = component_name.lower().replace("-", "").replace("_", "")
        if "radio" in normalized_component:
            return False
        raw = getattr(candidate, "raw", {}) if candidate is not None else {}
        if normalized_component and any(token in normalized_component for token in ("refer", "reference", "ref", "modalselect")):
            return True
        if _candidate_raw_claims_reference(raw):
            return True
        if normalized_component == "ydftextarea":
            return False
        if normalized_component == "lcdenum" or _candidate_has_enum_type(raw):
            return False
        runtime_fieldid = str(getattr(runtime, "fieldid", "") or "").strip()
        if isinstance(raw, dict) and raw.get("runtime_only") and re.search(r"(?:^|_)input(?:_search)?_input$", runtime_fieldid):
            return True
        if normalized_component and "select" in normalized_component:
            return False
        if normalized_component in {"ydfinput", "ydfinputnumber"}:
            return self._root_has_popup_reference_trigger(locator)
        raw_text = ""
        if isinstance(raw, (dict, list)):
            try:
                raw_text = json.dumps(raw, ensure_ascii=False).lower()
            except Exception:
                raw_text = str(raw).lower()
        else:
            raw_text = str(raw).lower()
        label = str(getattr(candidate, "label", "") or getattr(candidate, "title", "") or "")
        probe = f"{component_name} {label} {raw_text}".lower()
        if "date" in probe:
            return False
        if any(token in probe for token in ("refer", "reference", "refcode", "ref_code", "refmodel", "ref_model", "modal_select", "modalselect", "参照")):
            return True
        return self._root_has_popup_reference_trigger(locator)

    def _root_has_popup_reference_trigger(self, locator) -> bool:
        try:
            return bool(
                locator.evaluate(
                    """(node, selectors) => {
                        const visible = (el) => {
                          const style = window.getComputedStyle(el);
                          const rect = el.getBoundingClientRect();
                          return style && style.visibility !== 'hidden' && style.display !== 'none'
                            && rect.width > 0 && rect.height > 0;
                        };
                        const skip = /(clear|close|remove|delete|calendar|date)/i;
                        const marker = /(refer|reference|ref|参照|选择|search|sousuo|fangdajing|canzhao|arrow)/i;
                        const cell = node.closest([
                          'td',
                          '[role="gridcell"]',
                          '[role="cell"]',
                          '.w-table-cell',
                          '.wui-table-cell',
                          '.ant-table-cell',
                          '.u-table-cell'
                        ].join(','));
                        const owner = cell
                          || node.closest([
                            '[uikey]',
                            '[class*="form-item"]',
                            '[class*="FormItem"]',
                            '[fieldid]',
                            '[data-fieldid]'
                          ].join(','))
                          || node;
                        const sourceIdentity = String(
                          node.getAttribute('fieldid') || node.getAttribute('data-fieldid') || ''
                        ).trim();
                        const identitySegments = (value) => String(value || '').trim().split('_').filter(Boolean);
                        const sameIdentityFamily = (value) => {
                          const sourceSegments = identitySegments(sourceIdentity).filter((segment) => !/^(input|btn)$/.test(segment));
                          const candidateSegments = identitySegments(value).filter((segment) => !/^(input|btn)$/.test(segment));
                          if (!sourceSegments.length || !candidateSegments.length) return false;
                          const samePrefix = (shorter, longer) => shorter.every((segment, index) => segment === longer[index]);
                          return samePrefix(sourceSegments, candidateSegments) || samePrefix(candidateSegments, sourceSegments);
                        };
                        const explicitIdentityValues = (el) => [
                          el.getAttribute('fieldid'),
                          el.getAttribute('data-fieldid'),
                        ].map((value) => String(value || '').trim()).filter(Boolean);
                        const hasSameIdentity = (el) => {
                          const explicitIdentities = explicitIdentityValues(el);
                          if (explicitIdentities.some((identity) => !sameIdentityFamily(identity))) return false;
                          return [
                          el.getAttribute('fieldid'),
                          el.getAttribute('data-fieldid'),
                          el.getAttribute('data-name'),
                          el.getAttribute('name'),
                          el.getAttribute('id'),
                          el.getAttribute('uikey'),
                          ].some((value) => sameIdentityFamily(value));
                        };
                        const isPopupTrigger = (el) => {
                          if (!visible(el)) return false;
                          const text = [
                            el.className,
                            el.getAttribute('title'),
                            el.getAttribute('aria-label'),
                            el.innerText,
                            el.textContent,
                            el.getAttribute('role'),
                            el.getAttribute('aria-haspopup'),
                          ].join(' ');
                          return !skip.test(text) && (
                            marker.test(text)
                            || /(?:^|\\s)(?:modal-btn|icon-only|ydf-select-btn)(?:\\s|$)/i.test(String(el.className || ''))
                            || /dialog|tree|menu/.test(String(el.getAttribute('aria-haspopup') || '').toLowerCase())
                            || /input-suffix|select-arrow|icon-(sousuo|search|fangdajing|canzhao)/i.test(String(el.className || ''))
                          );
                        };
                        const collectCandidates = (root) => selectors.flatMap((selector) => [
                          ...(root.matches?.(selector) ? [root] : []),
                          ...Array.from(root.querySelectorAll(selector))
                        ]).filter((el, index, all) => all.indexOf(el) === index);
                        let scopedOwner = owner;
                        let recoveredIdentityOwner = false;
                        if (!cell && sourceIdentity && owner === node) {
                          const ownerCandidates = [
                            node.parentElement,
                            node.parentElement?.closest('[uikey], [fieldid], [data-fieldid], [class*="form-item"], [class*="FormItem"]'),
                          ].filter((candidate, index, all) => candidate && all.indexOf(candidate) === index);
                          const identityOwner = ownerCandidates.find((candidate) => {
                            const ancestorIdentityElements = [
                              ...(candidate.matches?.('[fieldid], [data-fieldid]') ? [candidate] : []),
                              ...Array.from(candidate.querySelectorAll('[fieldid], [data-fieldid]')),
                            ];
                            const ancestorCandidates = collectCandidates(candidate);
                            const sameFieldTrigger = ancestorCandidates.some((el) => hasSameIdentity(el) && isPopupTrigger(el));
                            const competingFieldIdentity = ancestorIdentityElements.some((el) => {
                              const explicitIdentities = explicitIdentityValues(el);
                              if (!explicitIdentities.some((identity) => !sameIdentityFamily(identity))) return false;
                              return true;
                            });
                            return sameFieldTrigger && !competingFieldIdentity;
                          });
                          if (identityOwner) {
                            scopedOwner = identityOwner;
                            recoveredIdentityOwner = true;
                          }
                        }
                        const candidates = collectCandidates(scopedOwner)
                          .filter((el) => !recoveredIdentityOwner || hasSameIdentity(el));
                        return candidates.some(isPopupTrigger);
                    }""",
                    build_popup_reference_trigger_selectors(),
                )
            )
        except Exception:
            return False

    def _editable_table_cell_looks_like_popup_reference(
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
            return self._looks_like_popup_reference_field(cell, bound)
        return self._root_has_popup_reference_trigger(cell)

    def _open_popup_reference_dialog(self, root) -> None:
        page = self._require_page()
        if self._popup_reference_diag_enabled():
            self._last_popup_reference_open_debug = self._collect_popup_reference_open_debug(root, phase="before")
        try:
            root.hover(timeout=1000)
        except Exception:
            pass
        ranked_trigger_scan = lambda marker: root.evaluate(
                """(node, args) => {
                        const visible = (el) => {
                          const style = window.getComputedStyle(el);
                          const rect = el.getBoundingClientRect();
                          return style && style.visibility !== 'hidden' && style.display !== 'none'
                            && rect.width > 0 && rect.height > 0;
                        };
                        const skip = /(clear|close|remove|delete|calendar|date)/i;
                        const marker = /(refer|reference|ref|参照|选择|search|sousuo|fangdajing|canzhao|arrow)/i;
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
                        const cell = node.closest([
                          'td',
                          '[role="gridcell"]',
                          '[role="cell"]',
                          '.w-table-cell',
                          '.wui-table-cell',
                          '.ant-table-cell',
                          '.u-table-cell'
                        ].join(','));
                        const owner = cell
                          || node.closest([
                            '[uikey]',
                            '[class*="form-item"]',
                            '[class*="FormItem"]',
                            '[fieldid]',
                            '[data-fieldid]'
                          ].join(','))
                          || node;
                        const sourceIdentity = String(
                          node.getAttribute('fieldid') || node.getAttribute('data-fieldid') || ''
                        ).trim();
                        const identitySegments = (value) => String(value || '').trim().split('_').filter(Boolean);
                        const sameIdentityFamily = (value) => {
                          const sourceSegments = identitySegments(sourceIdentity).filter((segment) => !/^(input|btn)$/.test(segment));
                          const candidateSegments = identitySegments(value).filter((segment) => !/^(input|btn)$/.test(segment));
                          if (!sourceSegments.length || !candidateSegments.length) return false;
                          const samePrefix = (shorter, longer) => shorter.every((segment, index) => segment === longer[index]);
                          return samePrefix(sourceSegments, candidateSegments) || samePrefix(candidateSegments, sourceSegments);
                        };
                        const explicitIdentityValues = (el) => [
                          el.getAttribute('fieldid'),
                          el.getAttribute('data-fieldid'),
                        ].map((value) => String(value || '').trim()).filter(Boolean);
                        const hasSameIdentity = (el) => {
                          const explicitIdentities = explicitIdentityValues(el);
                          if (explicitIdentities.some((identity) => !sameIdentityFamily(identity))) return false;
                          return [
                          el.getAttribute('fieldid'),
                          el.getAttribute('data-fieldid'),
                          el.getAttribute('data-name'),
                          el.getAttribute('name'),
                          el.getAttribute('id'),
                          el.getAttribute('uikey'),
                          ].some((value) => sameIdentityFamily(value));
                        };
                        const isPopupTrigger = (el) => {
                          if (!visible(el)) return false;
                          const text = [
                            el.className,
                            el.getAttribute('title'),
                            el.getAttribute('aria-label'),
                            el.innerText,
                            el.textContent,
                            el.getAttribute('role'),
                            el.getAttribute('aria-haspopup'),
                          ].join(' ');
                          return !skip.test(text) && (
                            marker.test(text)
                            || /(?:^|\\s)(?:modal-btn|icon-only|ydf-select-btn)(?:\\s|$)/i.test(String(el.className || ''))
                            || /dialog|tree|menu/.test(String(el.getAttribute('aria-haspopup') || '').toLowerCase())
                            || /input-suffix|select-arrow|icon-(sousuo|search|fangdajing|canzhao)/i.test(String(el.className || ''))
                          );
                        };
                        const collectCandidates = (root) => args.selectors.flatMap((selector) => [
                          ...(root.matches?.(selector) ? [root] : []),
                          ...Array.from(root.querySelectorAll(selector)),
                        ]).filter((el, index, all) => all.indexOf(el) === index);
                        let scopedOwner = owner;
                        let recoveredIdentityOwner = false;
                        if (!cell && sourceIdentity && owner === node) {
                          const ownerCandidates = [
                            node.parentElement,
                            node.parentElement?.closest('[uikey], [fieldid], [data-fieldid], [class*="form-item"], [class*="FormItem"]'),
                          ].filter((candidate, index, all) => candidate && all.indexOf(candidate) === index);
                          const identityOwner = ownerCandidates.find((candidate) => {
                            const ancestorIdentityElements = [
                              ...(candidate.matches?.('[fieldid], [data-fieldid]') ? [candidate] : []),
                              ...Array.from(candidate.querySelectorAll('[fieldid], [data-fieldid]')),
                            ];
                            const ancestorCandidates = collectCandidates(candidate);
                            const sameFieldTrigger = ancestorCandidates.some((el) => hasSameIdentity(el) && isPopupTrigger(el));
                            const competingFieldIdentity = ancestorIdentityElements.some((el) => {
                              const explicitIdentities = explicitIdentityValues(el);
                              if (!explicitIdentities.some((identity) => !sameIdentityFamily(identity))) return false;
                              return true;
                            });
                            return sameFieldTrigger && !competingFieldIdentity;
                          });
                          if (identityOwner) {
                            scopedOwner = identityOwner;
                            recoveredIdentityOwner = true;
                          }
                        }
                        const candidates = collectCandidates(scopedOwner)
                          .filter((el) => !recoveredIdentityOwner || hasSameIdentity(el))
                          .filter(isPopupTrigger);
                        candidates.sort((a, b) => {
                          const ar = a.getBoundingClientRect();
                          const br = b.getBoundingClientRect();
                          return triggerRank(b) - triggerRank(a)
                            || br.right - ar.right
                            || (ar.width * ar.height) - (br.width * br.height);
                        });
                        const target = candidates[0];
                        if (!target) return '';
                        target.setAttribute('data-ydf-browser-popup-reference-trigger', args.marker);
                        return `[data-ydf-browser-popup-reference-trigger="${args.marker}"]`;
                    }""",
                    {"selectors": build_popup_reference_trigger_selectors(), "marker": marker},
            )
        ranked_trigger_scan_completed = False
        ranked_trigger_scan_failed = False
        ranked_trigger_scan_empty = False
        try:
            for attempt in range(2):
                marker = f"trigger-{int(time.time() * 1000)}"
                try:
                    click_target_selector = ranked_trigger_scan(marker)
                except Exception:
                    ranked_trigger_scan_failed = True
                    break
                ranked_trigger_scan_completed = True
                if not click_target_selector:
                    ranked_trigger_scan_empty = True
                    break
                try:
                    target = self._resolve_visible_locator(str(click_target_selector))
                    self._record_popup_reference_clicked_target(target, source="ranked-trigger")
                    try:
                        target.click(timeout=2000)
                    except Exception:
                        try:
                            target.click(force=True, timeout=2000)
                        except Exception as exc:
                            self._record_popup_reference_click_error(exc)
                            raise
                except Exception:
                    if attempt == 1:
                        raise
                    continue
                try:
                    self._wait_for_timeout(500)
                    self._record_popup_reference_after_click()
                except PopupReferenceError:
                    raise
                except Exception:
                    pass
                return
        except PopupReferenceError:
            raise
        except Exception:
            pass
        if ranked_trigger_scan_completed and not ranked_trigger_scan_failed and ranked_trigger_scan_empty:
            return
        fallback_selectors = (
            build_popup_reference_trigger_selectors()
            if ranked_trigger_scan_failed or not ranked_trigger_scan_completed or not ranked_trigger_scan_empty
            else []
        )
        for selector in fallback_selectors:
            trigger = root.locator(selector)
            try:
                count = trigger.count()
            except Exception:
                continue
            for index in range(count):
                candidate = trigger.nth(index)
                try:
                    if not candidate.is_visible(timeout=300):
                        continue
                    self._record_popup_reference_clicked_target(
                        candidate,
                        source="selector-fallback",
                        selector=selector,
                        index=index,
                    )
                    candidate.click(timeout=1500)
                except Exception as exc:
                    self._record_popup_reference_click_error(exc)
                    continue
                try:
                    self._wait_for_timeout(500)
                    self._record_popup_reference_after_click()
                except PopupReferenceError:
                    raise
                except Exception:
                    pass
                return
        try:
            self._record_popup_reference_clicked_target(root, source="root-fallback")
            root.click(timeout=1500)
            self._wait_for_timeout(500)
            self._record_popup_reference_after_click()
        except PopupReferenceError:
            raise
        except Exception as exc:
            self._record_popup_reference_click_error(exc)
            if self._popup_reference_diag_enabled():
                screenshot = self._save_diagnostic_screenshot("popup-reference-open-trigger-failed")
                self._save_diagnostic_json(
                    "popup-reference-open-trigger-debug",
                    self._popup_reference_open_debug_payload(
                        reason="trigger-click-failed",
                        diagnostic=str(exc),
                        screenshot=screenshot,
                    ),
                )
            raise RuntimeError("无法打开弹出参照选择框") from exc
