from __future__ import annotations

import json
import os
import re
import sys
import time
from types import SimpleNamespace
from typing import Any

from ..adapters import default_render_adapter_registry
from ..models import BoundElement
from .model import PopupReferenceError

GEOMETRY_FALLBACK_VIEWPORT = {"width": 1440, "height": 900}
RENDER_ADAPTERS = default_render_adapter_registry()

def _bound_element_has_verified_form_identity(bound_element: Any) -> bool:
    path = getattr(bound_element, "contract_path", None)
    return bool(
        isinstance(path, dict)
        and path.get("applicability") == "verified"
        and "PRS-FORM-001" in (path.get("rule_ids") or [])
    )

def _candidate_raw_claims_reference(raw: Any) -> bool:
    if not isinstance(raw, dict):
        return False
    return bool(str(raw.get("refuri") or raw.get("refUri") or raw.get("refURI") or "").strip())

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

def _editable_table_value_has_structured_popup_reference_target(value: Any) -> bool:
    if isinstance(value, list):
        return True
    if not isinstance(value, dict):
        return False
    structured_keys = {
        "tree",
        "trees",
        "tab",
        "tabs",
        "match",
        "matches",
        "row_number",
        "row_numbers",
        "row_index",
        "first_available",
        "select_first_available",
        "selections",
        "selection",
        "values",
        "items",
        "targets",
    }
    return any(key in value for key in structured_keys)

def _normalize_popup_reference_target(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        return {"values": list(value)}
    if isinstance(value, dict):
        target = dict(value)
        if target.get("value") is not None and target.get("equals") is None:
            target["equals"] = target.get("value")
        if "match" in target and isinstance(target["match"], dict):
            target["match"] = dict(target["match"])
        elif target.get("column") and target.get("equals") is not None:
            target["match"] = {"column": target.get("column"), "equals": target.get("equals")}
        return target
    return {"equals": str(value)}

def _popup_reference_selection_targets(target: dict[str, Any]) -> list[dict[str, Any]]:
    def inherit_context(selection: dict[str, Any]) -> dict[str, Any]:
        result = dict(selection)
        for key in ("tab", "tabs"):
            if key in target and key not in result:
                result[key] = target[key]
        return result

    for key in ("selections", "selection"):
        raw = target.get(key)
        if isinstance(raw, dict):
            return [inherit_context(_normalize_popup_reference_target(raw))]
        if isinstance(raw, list):
            result = [inherit_context(_normalize_popup_reference_target(item)) for item in raw]
            return result or [target]
    for key in ("values", "items", "targets"):
        raw = target.get(key)
        if isinstance(raw, list):
            result = [inherit_context(_normalize_popup_reference_target(item)) for item in raw]
            return result or [target]
    raw_matches = target.get("matches")
    if isinstance(raw_matches, list):
        result: list[dict[str, Any]] = []
        for item in raw_matches:
            if isinstance(item, dict):
                result.append(inherit_context({"match": dict(item)}))
        return result or [target]
    return [target]

def _popup_reference_tab_targets(target: dict[str, Any]) -> list[Any]:
    result: list[Any] = []
    if "tab" in target:
        result.append(target.get("tab"))
    raw_tabs = target.get("tabs")
    if isinstance(raw_tabs, list):
        result.extend(raw_tabs)
    elif raw_tabs is not None:
        result.append(raw_tabs)
    return result

def _popup_reference_tab_target_label(target: Any) -> str:
    if _is_scalar_reference_value(target):
        return str(target).strip()
    if not isinstance(target, dict):
        return ""
    for key in ("label", "value", "name"):
        value = target.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""

def _popup_reference_tree_targets(target: dict[str, Any]) -> list[Any]:
    result: list[Any] = []
    if "tree" in target:
        result.append(target.get("tree"))
    raw_trees = target.get("trees")
    if isinstance(raw_trees, list):
        result.extend(raw_trees)
    elif raw_trees is not None:
        result.append(raw_trees)
    return result

def _popup_reference_tree_target_label(target: Any) -> str:
    if _is_scalar_reference_value(target):
        return str(target).strip()
    if not isinstance(target, dict):
        return ""
    for key in ("label", "value", "equals", "text", "node", "name"):
        value = target.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""

def _popup_reference_tree_search_terms(value: str) -> list[str]:
    normalized = " ".join(str(value or "").split())
    if not normalized:
        return []
    terms = [normalized]
    parts = [part.strip() for part in re.split(r"\s+", normalized) if part.strip()]
    if len(parts) > 1:
        terms.extend([parts[0], parts[-1]])
    seen: set[str] = set()
    result: list[str] = []
    for term in terms:
        if term and term not in seen:
            seen.add(term)
            result.append(term)
    return result

def _popup_reference_filter_text(target: dict[str, Any]) -> str:
    if _wants_first_available(target):
        for key in ("filter", "keyword", "query", "search", "input", "text", "label", "value", "equals"):
            value = target.get(key)
            if _is_scalar_reference_value(value) and str(value).strip():
                return str(value).strip()
        return ""
    for key in ("filter", "keyword", "query", "search", "input", "text", "label", "value", "equals"):
        value = target.get(key)
        if _is_scalar_reference_value(value) and str(value).strip():
            return str(value).strip()
    match = _popup_reference_target_match(target)
    if match:
        for key in ("equals", "value", "text", "label"):
            value = match.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
    return str(target).strip()

def _popup_reference_explicit_filter_text(target: dict[str, Any]) -> str:
    if "filter" not in target:
        return ""
    raw_filter = target.get("filter")
    if _is_scalar_reference_value(raw_filter) and str(raw_filter).strip():
        return str(raw_filter).strip()
    if isinstance(raw_filter, dict):
        for key in ("keyword", "query", "search", "input", "text", "label", "value", "equals"):
            value = raw_filter.get(key)
            if _is_scalar_reference_value(value) and str(value).strip():
                return str(value).strip()
    return ""

def _popup_reference_implicit_value_filter_text(target: dict[str, Any]) -> str:
    if _wants_first_available(target) or _popup_reference_target_match(target):
        return ""
    for key in ("equals", "value", "text"):
        value = target.get(key)
        if _is_scalar_reference_value(value) and str(value).strip():
            return str(value).strip()
    return ""

def _popup_reference_filter_conditions(target: dict[str, Any]) -> tuple[list[dict[str, str]], bool]:
    raw_filter = target.get("filter")
    if isinstance(raw_filter, dict):
        conditions = raw_filter.get("conditions") or raw_filter.get("matches") or raw_filter.get("all")
        if conditions is not None:
            return _normalize_popup_reference_filter_conditions(conditions), True
        field = raw_filter.get("field") or raw_filter.get("column")
        equals = raw_filter.get("equals")
        if field and equals is not None:
            return [{"field": str(field), "equals": str(equals)}], True
    match = _popup_reference_target_match(target)
    if match:
        column = match.get("column") or match.get("field")
        if column and _is_scalar_reference_value(raw_filter) and str(raw_filter).strip():
            return [{"field": str(column), "equals": str(raw_filter).strip()}], False
    return [], False

def _popup_reference_has_explicit_filter(target: dict[str, Any]) -> bool:
    if "filter" not in target:
        return False
    raw_filter = target.get("filter")
    if isinstance(raw_filter, dict):
        return bool(raw_filter)
    return _is_scalar_reference_value(raw_filter) and bool(str(raw_filter).strip())

def _normalize_popup_reference_filter_conditions(raw_conditions: Any) -> list[dict[str, str]]:
    if isinstance(raw_conditions, dict):
        raw_conditions = [raw_conditions]
    if not isinstance(raw_conditions, list):
        return []
    result: list[dict[str, str]] = []
    for item in raw_conditions:
        if not isinstance(item, dict):
            continue
        field = item.get("field") or item.get("column")
        equals = item.get("equals")
        if field is None or equals is None:
            continue
        result.append({"field": str(field), "equals": str(equals)})
    return result

def _is_scalar_reference_value(value: Any) -> bool:
    return value is not None and not isinstance(value, (dict, list, tuple, set))

def _popup_reference_root_value_matches_targets(actual_value: Any, targets: list[dict[str, Any]]) -> bool:
    actual = _normalize_reference_match_text(actual_value)
    if not actual:
        return False
    expected_values: list[str] = []
    for target in targets:
        if not isinstance(target, dict):
            continue
        expected = _popup_reference_target_value(target)
        if expected:
            expected_values.append(expected)
    if not expected_values:
        return False
    return all(_popup_reference_text_matches(actual, expected) for expected in expected_values)

def _popup_reference_targets_are_plain_first_available(targets: list[dict[str, Any]]) -> bool:
    if not targets:
        return False
    for target in targets:
        if not _wants_first_available(target):
            return False
        if _popup_reference_target_value(target) or _popup_reference_target_match(target):
            return False
        if _popup_reference_row_numbers(target) or _popup_reference_tree_targets(target) or _popup_reference_tab_targets(target):
            return False
    return True

def _popup_reference_candidate_text_is_empty_state(value: Any) -> bool:
    text = _normalize_reference_match_text(value)
    if not text:
        return False
    markers = ("暂无数据哦", "暂无数据", "暂时没有数据哦", "暂时没有数据", "点击上方查询条件搜索数据")
    if not any(marker in text for marker in markers):
        return False
    rest = text
    for marker in markers:
        rest = rest.replace(marker, "")
    rest = re.sub(r"[\s~～!！。.,，:：|｜_\-—]+", "", rest)
    return not rest

def _popup_reference_root_value_is_empty_state(value: Any) -> bool:
    text = _normalize_reference_match_text(value)
    return text == "请选择" or _popup_reference_candidate_text_is_empty_state(text)

def _popup_reference_text_matches(actual_value: Any, expected_value: Any) -> bool:
    actual = _normalize_reference_match_text(actual_value)
    expected = _normalize_reference_match_text(expected_value)
    if not actual or not expected:
        return False
    return (
        actual == expected
        or actual.endswith(f" {expected}")
        or expected.endswith(f" {actual}")
        or actual in expected
        or expected in actual
    )

def _normalize_reference_match_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()

def _popup_reference_match_value(match: dict[str, Any]) -> tuple[str, str]:
    for key in ("equals", "value", "text", "label"):
        value = match.get(key)
        if value is not None and str(value).strip():
            return str(value).strip(), "equals"
    value = match.get("contains")
    if value is not None and str(value).strip():
        return str(value).strip(), "contains"
    return "", "equals"

def _popup_reference_target_value(target: dict[str, Any]) -> str:
    for key in ("equals", "value", "text", "label"):
        value = target.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    match = _popup_reference_target_match(target)
    if match:
        for key in ("equals", "value", "text", "label"):
            value = match.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
    return ""

def _popup_reference_target_match(target: dict[str, Any]) -> dict[str, Any] | None:
    raw = target.get("match")
    if isinstance(raw, dict):
        return dict(raw)
    if target.get("column") and target.get("equals") is not None:
        return {"column": target.get("column"), "equals": target.get("equals")}
    return None

def _popup_reference_target_table(target: dict[str, Any]) -> str:
    return str(target.get("table") or target.get("table_name") or "").strip()

def _popup_reference_row_numbers(target: dict[str, Any]) -> list[int]:
    raw = target.get("row_numbers", None)
    if raw is None:
        raw = target.get("rows", None)
    if raw is None and target.get("row_number", None) is not None:
        raw = [target["row_number"]]
    if raw is None and target.get("row_index", None) is not None:
        raw = [target["row_index"]]
    if raw is None:
        return []
    if not isinstance(raw, list):
        raw = [raw]
    row_numbers = [int(item) for item in raw]
    if any(item < 1 for item in row_numbers):
        raise ValueError(f"弹出参照行号从 1 开始: {row_numbers}")
    return row_numbers

def _wants_first_available(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return bool(value.get("first_available") or value.get("select_first_available"))

def _leading_code(value: str) -> str:
    text = str(value or "").strip()
    match = re.match(r"\d+", text)
    return match.group(0) if match else ""

def _remaining_timeout_ms(deadline: float) -> int:
    return max(0, int((deadline - time.monotonic()) * 1000))

def build_popup_reference_dialog_selectors() -> list[str]:
    return RENDER_ADAPTERS.selectors("popup_reference.dialog")

def build_popup_reference_trigger_selectors() -> list[str]:
    return RENDER_ADAPTERS.selectors("popup_reference.trigger")

def build_popup_reference_filter_selectors() -> list[str]:
    return RENDER_ADAPTERS.selectors("popup_reference.filter")

def build_popup_reference_filter_submit_selectors() -> list[str]:
    return RENDER_ADAPTERS.selectors("popup_reference.filter_submit")

def build_popup_reference_tree_node_selectors(value: str) -> list[str]:
    return RENDER_ADAPTERS.selectors("popup_reference.tree_node", value)

def build_popup_reference_tree_closed_switcher_selectors() -> list[str]:
    return RENDER_ADAPTERS.selectors("popup_reference.tree_closed_switcher")

def build_popup_reference_option_selectors(value: str) -> list[str]:
    return RENDER_ADAPTERS.selectors("popup_reference.option", value)

def build_popup_reference_table_row_selectors(value: str) -> list[str]:
    return RENDER_ADAPTERS.selectors("popup_reference.table_row", value)

def build_popup_reference_confirm_selectors(label: str = "确定") -> list[str]:
    return RENDER_ADAPTERS.selectors("popup_reference.confirm", label)


class SelectionStage:
    _last_popup_reference_first_candidate: dict[str, Any] | None
    _last_popup_reference_first_candidate_error: str
    _last_popup_reference_first_candidate_saw_table: bool

    def _apply_popup_reference_tree_context(self, dialog, target: dict[str, Any]) -> list[dict[str, Any]]:
        tree_targets = _popup_reference_tree_targets(target)
        if not tree_targets:
            return []
        applied: list[dict[str, Any]] = []
        for tree_target in tree_targets:
            label = _popup_reference_tree_target_label(tree_target)
            if not label:
                continue
            if label in {"root", "first_leaf"}:
                clicked = self._click_popup_reference_tree_shortcut(dialog, label)
            else:
                debug_enabled = bool(os.environ.get("YDF_BROWSER_DEBUG_POPUP_REFERENCE"))
                if debug_enabled:
                    print(f"[ydf-browser] popup-reference-tree-context label={label} stage=click-initial", file=sys.stderr, flush=True)
                clicked = self._click_popup_reference_tree_node(dialog, label)
                if not clicked and self._search_popup_reference_tree_node(dialog, label):
                    if debug_enabled:
                        print(f"[ydf-browser] popup-reference-tree-context label={label} stage=click-after-search", file=sys.stderr, flush=True)
                    clicked = self._click_popup_reference_tree_node(dialog, label)
                if not clicked:
                    if debug_enabled:
                        print(f"[ydf-browser] popup-reference-tree-context label={label} stage=expand", file=sys.stderr, flush=True)
                    self._expand_popup_reference_tree_until_visible(dialog, label)
                    clicked = self._click_popup_reference_tree_node(dialog, label)
                if debug_enabled:
                    print(f"[ydf-browser] popup-reference-tree-context label={label} stage=done clicked={clicked}", file=sys.stderr, flush=True)
            if not clicked:
                diagnostic = self._collect_popup_reference_diagnostic_text(dialog)
                screenshot = self._save_diagnostic_screenshot("popup-reference-tree-node-missing")
                if screenshot:
                    diagnostic = f"{diagnostic} | screenshot={screenshot}"
                raise RuntimeError(f"未找到弹出参照树节点: {label}: {diagnostic}")
            applied_item = {"label": label}
            if isinstance(tree_target, dict):
                name = str(tree_target.get("name") or "").strip()
                if name and name != label:
                    applied_item["name"] = name
            applied.append(applied_item)
            try:
                self._wait_for_timeout(800)
            except PopupReferenceError:
                raise
            except Exception:
                pass
        return applied

    def _apply_popup_reference_tab_context(self, dialog, target: dict[str, Any]) -> list[dict[str, Any]]:
        tab_targets = _popup_reference_tab_targets(target)
        if not tab_targets:
            return []
        normalized_targets = []
        for tab_target in tab_targets:
            label = _popup_reference_tab_target_label(tab_target)
            if label:
                normalized_targets.append({"label": label})
        if not normalized_targets:
            return []
        try:
            result = dialog.evaluate(
                """(root, payload) => {
                    const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                    const compact = (value) => normalize(value).replace(/\\s+/g, '');
                    const visible = (el) => {
                      if (!el || !(el instanceof HTMLElement)) return false;
                      const style = window.getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style && style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width > 0 && rect.height > 0;
                    };
                    const isActive = (el) => {
                      const cls = [el.className, el.parentElement?.className].join(' ');
                      return el.getAttribute('aria-selected') === 'true'
                        || el.getAttribute('aria-current') === 'true'
                        || /(^|\\s)(active|selected|current|checked)(\\s|$)/i.test(cls)
                        || /w-tabs-tab-active|ant-tabs-tab-active|u-tabs-tab-active|wui-tabs-tab-active/i.test(cls);
                    };
                    const tabSelector = [
                      '[role="tab"]',
                      '.w-tabs-tab',
                      '.wui-tabs-tab',
                      '.ant-tabs-tab',
                      '.u-tabs-tab',
                      '[class*="tabs-tab"]',
                      '[class*="TabsTab"]',
                      '[class*="tab-item"]',
                      '[class*="TabItem"]',
                      '[class*="tabs_item"]',
                      '[class*="TabsItem"]'
                    ].join(',');
                    const seen = new Set();
                    const toCandidate = (el) => {
                      const text = normalize(
                        el.innerText
                        || el.textContent
                        || el.getAttribute('title')
                        || el.getAttribute('aria-label')
                      );
                      const title = normalize(el.getAttribute('title'));
                      const aria = normalize(el.getAttribute('aria-label'));
                      const rect = el.getBoundingClientRect();
                      return { el, text, title, aria, rect, active: isActive(el) };
                    };
                    const tabLikeCandidates = Array.from(root.querySelectorAll(tabSelector))
                      .filter((el) => {
                        if (seen.has(el)) return false;
                        seen.add(el);
                        return visible(el);
                      })
                      .map(toCandidate)
                      .filter((item) => {
                        if (!item.text && !item.title && !item.aria) return false;
                        const text = item.text || item.title || item.aria;
                        if (text.length > 60) return false;
                        if (item.el.closest('table, thead, tbody, tr, td, [role="grid"], [role="row"], [role="gridcell"]')) return false;
                        return true;
                      });
                    const plainTextCandidates = Array.from(root.querySelectorAll('span, div, a, button, li'))
                      .filter((el) => {
                        if (seen.has(el)) return false;
                        if (!visible(el)) return false;
                        if (el.closest('table, thead, tbody, tr, td, [role="grid"], [role="row"], [role="gridcell"]')) return false;
                        if (el.closest('input, textarea, select')) return false;
                        const text = normalize(el.innerText || el.textContent || el.getAttribute('title') || el.getAttribute('aria-label'));
                        if (!text || text.length > 30) return false;
                        const childText = Array.from(el.children || [])
                          .map((child) => normalize(child.innerText || child.textContent))
                          .filter(Boolean)
                          .join(' ');
                        if (childText && normalize(childText) !== text) return false;
                        seen.add(el);
                        el.setAttribute('data-ydf-browser-popup-reference-tab-text', 'true');
                        return true;
                      })
                      .map(toCandidate);
                    const candidates = [...tabLikeCandidates, ...plainTextCandidates]
                      .sort((a, b) => a.rect.top - b.rect.top || a.rect.left - b.rect.left);
                    const candidateLabels = candidates
                      .map((item) => item.text || item.title || item.aria)
                      .filter(Boolean);
                    const applied = [];
                    const missing = [];
                    for (const target of payload.targets || []) {
                      const label = normalize(target.label);
                      const wanted = compact(label);
                      const match = candidates.find((item) => {
                        const values = [item.text, item.title, item.aria].map(compact).filter(Boolean);
                        return values.some((value) => value === wanted);
                      });
                      if (!match) {
                        missing.push(label);
                        continue;
                      }
                      const marker = `popup-tab-${Date.now()}-${applied.length}-${Math.floor(Math.random() * 100000)}`;
                      match.el.setAttribute('data-ydf-browser-popup-reference-tab', marker);
                      applied.push({
                        label,
                        selector: `[data-ydf-browser-popup-reference-tab="${marker}"]`,
                        active: Boolean(match.active),
                      });
                    }
                    return {
                      applied,
                      missing,
                      candidates: Array.from(new Set(candidateLabels)).slice(0, 20),
                      diagnostic: normalize(root.innerText || root.textContent).slice(0, 1200),
                    };
                }""",
                {"targets": normalized_targets},
            )
        except Exception as exc:
            raise RuntimeError(f"无法解析弹出参照页签: {exc}") from exc
        missing = [str(item).strip() for item in list((result or {}).get("missing") or []) if str(item).strip()]
        if missing:
            candidates = [str(item).strip() for item in list((result or {}).get("candidates") or []) if str(item).strip()]
            diagnostic = str((result or {}).get("diagnostic") or "").strip()
            if not diagnostic:
                diagnostic = self._collect_popup_reference_diagnostic_text(dialog)
            if candidates:
                diagnostic = f"候选页签: {'、'.join(candidates)}; {diagnostic}"
            screenshot = self._save_diagnostic_screenshot("popup-reference-tab-missing")
            if screenshot:
                diagnostic = f"{diagnostic} | screenshot={screenshot}"
            raise RuntimeError(f"未找到弹出参照页签: {'、'.join(missing)}: {diagnostic}")
        applied: list[dict[str, Any]] = []
        for item in list((result or {}).get("applied") or []):
            label = str(item.get("label") or "").strip()
            selector = str(item.get("selector") or "").strip()
            if not label or not selector:
                continue
            applied_item: dict[str, Any] = {"label": label}
            if bool(item.get("active")):
                applied_item["active"] = True
                applied.append(applied_item)
                continue
            tab = dialog.locator(selector).first
            try:
                tab.click(timeout=2000)
            except Exception:
                tab.click(force=True, timeout=2000)
            applied.append(applied_item)
            try:
                self._wait_for_timeout(800)
            except PopupReferenceError:
                raise
            except Exception:
                pass
        return applied

    def _click_popup_reference_tree_shortcut(self, dialog, shortcut: str) -> bool:
        try:
            marker = f"popup-tree-shortcut-{int(time.time() * 1000)}"
            selector = dialog.evaluate(
                """(root, args) => {
                    const shortcut = String(args.shortcut || '').trim();
                    const marker = args.marker;
                    const visible = (el) => {
                      if (!el || !(el instanceof HTMLElement)) return false;
                      const style = window.getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style.display !== 'none' && style.visibility !== 'hidden'
                        && rect.width > 0 && rect.height > 0;
                    };
                    const disabled = (el) => {
                      const cls = String(el.className || '');
                      return el.disabled || el.getAttribute('aria-disabled') === 'true' || /disabled/i.test(cls);
                    };
                    const selector = [
                      '[role="treeitem"]',
                      '.wui-tree-treenode',
                      '.wui-select-tree-treenode',
                      '.ant-tree-treenode',
                      '.u-tree-treenode',
                      '.wui-tree-node-content-wrapper',
                      '.wui-select-tree-node-content-wrapper',
                      '.ant-tree-node-content-wrapper'
                    ].join(',');
                    const nodes = Array.from(root.querySelectorAll(selector))
                      .filter((el, index, all) => all.indexOf(el) === index)
                      .filter((el) => visible(el) && !disabled(el))
                      .map((el) => {
                        const target = el.matches('[role="treeitem"], .wui-tree-treenode, .wui-select-tree-treenode, .ant-tree-treenode, .u-tree-treenode')
                          ? (el.querySelector('.wui-tree-node-content-wrapper, .wui-select-tree-node-content-wrapper, .ant-tree-node-content-wrapper, [class*="title"], [class*="Title"]') || el)
                          : el;
                        const rect = target.getBoundingClientRect();
                        const text = String(el.innerText || el.textContent || el.getAttribute('title') || '').trim();
                        const cls = String(el.className || '');
                        const expanded = el.getAttribute('aria-expanded') === 'true' || /open|expanded/i.test(cls);
                        const collapsed = el.getAttribute('aria-expanded') === 'false' || /close|collapsed/i.test(cls);
                        return { el: target, text, rect, expanded, collapsed };
                      })
                      .filter((item) => item.text && visible(item.el))
                      .sort((a, b) => a.rect.top - b.rect.top || a.rect.left - b.rect.left);
                    const target = shortcut === 'first_leaf'
                      ? (nodes.find((item) => !item.collapsed && !item.expanded) || nodes[0])
                      : nodes[0];
                    if (!target) return '';
                    target.el.setAttribute('data-ydf-browser-popup-tree-shortcut', marker);
                    return `[data-ydf-browser-popup-tree-shortcut="${marker}"]`;
                }""",
                {"shortcut": shortcut, "marker": marker},
            )
            if not selector:
                return False
            target = dialog.locator(str(selector)).first
            try:
                target.click(timeout=2000)
            except Exception:
                target.click(force=True, timeout=2000)
            return True
        except Exception:
            return False

    def _apply_current_popup_reference_filter(self, dialog, target: dict[str, Any]) -> None:
        if "filter" not in target:
            filter_text = _popup_reference_implicit_value_filter_text(target)
            if filter_text:
                self._fill_popup_reference_filter(dialog, filter_text)
                self._wait_for_timeout(800)
            return
        filter_conditions, filter_conditions_explicit = _popup_reference_filter_conditions(target)
        filter_text = _popup_reference_explicit_filter_text(target)
        if filter_conditions:
            try:
                self._fill_popup_reference_filter_fields(dialog, filter_conditions)
                self._submit_popup_reference_filter(dialog)
                self._wait_for_timeout(800)
                return
            except PopupReferenceError:
                raise
            except RuntimeError:
                if filter_conditions_explicit:
                    raise
                if not filter_text:
                    return
        if filter_text:
            self._fill_popup_reference_filter(dialog, filter_text)
            self._wait_for_timeout(800)

    def _click_popup_reference_target(
        self,
        dialog,
        target: dict[str, Any],
        *,
        shell_dialog=None,
    ) -> bool:
        if _wants_first_available(target):
            return self._click_first_popup_reference_candidate(dialog, shell_dialog=shell_dialog)
        unique_text = _popup_reference_implicit_value_filter_text(target)
        if unique_text:
            if self._click_first_popup_reference_candidate(dialog, require_unique=True, unique_text=unique_text):
                return True
            if getattr(self, "_last_popup_reference_first_candidate_attempted", False):
                return False
        match = _popup_reference_target_match(target)
        if match and self._click_popup_reference_table_row(dialog, match):
            return True
        if match:
            return False
        value = _popup_reference_target_value(target)
        if not value:
            return False
        if self._click_popup_reference_tree_node(dialog, value):
            return True
        if not match and self._click_popup_reference_table_row(dialog, {"equals": value}):
            return True
        if self._click_popup_reference_list_option(dialog, value):
            return True
        self._expand_popup_reference_tree_until_visible(dialog, value)
        if self._click_popup_reference_tree_node(dialog, value):
            return True
        if not match and self._click_popup_reference_table_row(dialog, {"equals": value}):
            return True
        return self._click_popup_reference_list_option(dialog, value)

    def _click_first_popup_reference_candidate(
        self,
        dialog,
        *,
        require_unique: bool = False,
        unique_text: str = "",
        shell_dialog=None,
    ) -> bool:
        if require_unique or self._page_provider() is None:
            return self._try_click_first_popup_reference_candidate(
                dialog,
                require_unique=require_unique,
                unique_text=unique_text,
            )
        deadline = time.monotonic() + 8
        current = dialog
        shell = shell_dialog or dialog
        require_right_table = False
        while True:
            remaining_ms = _remaining_timeout_ms(deadline)
            if remaining_ms <= 0:
                return False
            current = self._wait_for_popup_reference_choice_root_ready(
                shell,
                current,
                timeout_ms=remaining_ms,
                require_candidate=True,
            )
            if self._try_click_first_popup_reference_candidate(
                current,
                require_right_table=require_right_table,
            ):
                return True
            require_right_table = (
                require_right_table or self._last_popup_reference_first_candidate_saw_table
            )
            remaining_ms = _remaining_timeout_ms(deadline)
            if remaining_ms <= 0:
                return False
            try:
                self._wait_for_timeout(min(200, remaining_ms))
            except PopupReferenceError:
                raise
            except Exception:
                return False
            current = self._resolve_current_popup_reference_choice_root(shell) or current

    def _try_click_first_popup_reference_candidate(
        self,
        dialog,
        *,
        require_unique: bool = False,
        unique_text: str = "",
        require_right_table: bool = False,
    ) -> bool:
        try:
            self._last_popup_reference_first_candidate_attempted = False
            self._last_popup_reference_first_candidate_saw_table = False
            debug_enabled = bool(os.environ.get("YDF_BROWSER_DEBUG_POPUP_REFERENCE"))
            if debug_enabled:
                print("[ydf-browser] popup-reference-first-candidate stage=evaluate", file=sys.stderr, flush=True)
            marker = f"first-reference-{int(time.time() * 1000)}"
            click_target_selector = dialog.evaluate(
                """(root, marker) => {
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
                    const emptyStateText = (text) => {
                      const normalized = normalize(text);
                      if (!normalized) return false;
                      const markers = ['暂无数据哦', '暂无数据', '暂时没有数据哦', '暂时没有数据', '点击上方查询条件搜索数据'];
                      if (!markers.some((marker) => normalized.includes(marker))) return false;
                      const rest = markers.reduce((value, marker) => value.split(marker).join(''), normalized)
                        .replace(/[\\s~～!！。.,，:：|｜_\\-—]+/g, '');
                      return !rest;
                    };
                    const tableRowSelector = [
                      'tbody tr',
                      '.w-table-tbody .w-table-row',
                      '.w-table-body .w-table-row',
                      '.wui-table-tbody .wui-table-row',
                      '.wui-table-body .wui-table-row',
                      '.ant-table-tbody .ant-table-row',
                      '.u-table-tbody .u-table-row',
                      '[role="grid"] [role="row"]',
                      '[class*="table-body"] [class*="table-row"]',
                      '[class*="TableBody"] [class*="TableRow"]'
                    ].join(',');
                    const looseTableRowSelector = [
                      'tbody tr',
                      '.w-table-row',
                      '.wui-table-row',
                      '.ant-table-row',
                      '.u-table-row',
                      '[role="grid"] [role="row"]',
                      '[class*="table-row"]',
                      '[class*="TableRow"]',
                      '[class*="table-body"] [class*="table-row"]',
                      '[class*="TableBody"] [class*="TableRow"]'
                    ].join(',');
                    const tableCellSelector = [
                      'td',
                      '[role="gridcell"]',
                      '[role="cell"]',
                      '.w-table-cell',
                      '.wui-table-cell',
                      '.ant-table-cell',
                      '.u-table-cell',
                      '[class*="table-cell"]',
                      '[class*="TableCell"]'
                    ].join(',');
                    const treeNodeSelector = [
                      '[role="treeitem"]',
                      '.wui-tree-treenode',
                      '.wui-select-tree-treenode',
                      '.ant-tree-treenode',
                      '.u-tree-treenode',
                      '.wui-tree-node-content-wrapper',
                      '.wui-select-tree-node-content-wrapper',
                      '.ant-tree-node-content-wrapper'
                    ].join(',');
                    const listOptionSelector = [
                      '[role="option"]',
                      '.wui-select-item-option',
                      '.ant-select-item-option',
                      '.u-select-item-option',
                      '.wui-list-item',
                      '.ant-list-item',
                      '.u-list-item'
                    ].join(',');
                    const candidateKindFor = (el) => {
                      if (
                        el.matches(tableRowSelector)
                        || (el.matches(looseTableRowSelector) && Array.from(el.querySelectorAll(tableCellSelector)).some(visible))
                      ) {
                        return 'table-row';
                      }
                      if (el.matches(listOptionSelector)) return 'list-option';
                      if (el.matches(treeNodeSelector) || el.closest(treeNodeSelector)) return 'tree-node';
                      return 'generic';
                    };
                    const candidateRankFor = (kind) => {
                      if (kind === 'table-row') return 0;
                      if (kind === 'list-option') return 1;
                      if (kind === 'tree-node') return 2;
                      return 3;
                    };
                    const selectionControlFor = (node) => {
                      const controlSelector = [
                        'input[type="radio"]',
                        'input[type="checkbox"]',
                        '[role="radio"]',
                        '[role="checkbox"]',
                        '.w-radio',
                        '.w-checkbox',
                        '.wui-radio',
                        '.wui-checkbox',
                        '.ant-radio',
                        '.ant-checkbox',
                        '.u-radio',
                        '.u-checkbox',
                        '.w-radio-wrapper',
                        '.w-checkbox-wrapper',
                        '.wui-radio-wrapper',
                        '.wui-checkbox-wrapper',
                        '.ant-radio-wrapper',
                        '.ant-checkbox-wrapper',
                        '.u-radio-wrapper',
                        '.u-checkbox-wrapper',
                        '[class*="radio"]',
                        '[class*="Radio"]',
                        '[class*="checkbox"]',
                        '[class*="Checkbox"]'
                      ].join(',');
                      const wrapperSelector = [
                        'label',
                        '.wui-tree-checkbox',
                        '.wui-select-tree-checkbox',
                        '.ant-tree-checkbox',
                        '.u-tree-checkbox',
                        '.wui-tree-radio',
                        '.wui-select-tree-radio',
                        '.ant-tree-radio',
                        '.u-tree-radio',
                        '.w-radio-wrapper',
                        '.w-checkbox-wrapper',
                        '.wui-radio-wrapper',
                        '.wui-checkbox-wrapper',
                        '.ant-radio-wrapper',
                        '.ant-checkbox-wrapper',
                        '.u-radio-wrapper',
                        '.u-checkbox-wrapper',
                        '[class*="radio-wrapper"]',
                        '[class*="RadioWrapper"]',
                        '[class*="checkbox-wrapper"]',
                        '[class*="CheckboxWrapper"]'
                      ].join(',');
                      const rankFor = (target) => {
                        const tag = String(target.tagName || '').toLowerCase();
                        const role = String(target.getAttribute('role') || '').toLowerCase();
                        const type = String(target.getAttribute('type') || '').toLowerCase();
                        const className = String(target.className || '').toLowerCase();
                        if (tag === 'label') return 0;
                        if (/tree-(checkbox|radio)|select-tree-(checkbox|radio)|radio-wrapper|checkbox-wrapper/.test(className)) return 1;
                        if (role === 'radio' || role === 'checkbox') return 2;
                        if (/radio|checkbox/.test(className) && !/group/.test(className)) return 3;
                        if (tag === 'input' && (type === 'radio' || type === 'checkbox')) return 8;
                        return 8;
                      };
                      return Array.from(node.querySelectorAll(controlSelector))
                        .filter((item, index, all) => all.indexOf(item) === index)
                        .filter((item) => !disabled(item))
                        .map((item) => {
                          const wrapper = item.closest(wrapperSelector);
                          const target = wrapper && node.contains(wrapper) && visible(wrapper) ? wrapper : item;
                          return { target, rank: rankFor(target) };
                        })
                        .filter((item, index, all) => all.findIndex((other) => other.target === item.target) === index)
                        .filter((item) => visible(item.target))
                        .sort((a, b) => {
                          const ar = a.target.getBoundingClientRect();
                          const br = b.target.getBoundingClientRect();
                          return a.rank - b.rank || ar.left - br.left || (ar.width * ar.height) - (br.width * br.height);
                        })[0]?.target || null;
                    };
                    const candidateContainerFor = (node) => {
                      const containerSelector = [
                        'tr',
                        '[role="row"]',
                        '.w-table-row',
                        '.wui-table-row',
                        '.ant-table-row',
                        '.u-table-row',
                        '[class*="table-row"]',
                        '[class*="TableRow"]',
                        '.wui-tree-treenode',
                        '.wui-select-tree-treenode',
                        '.ant-tree-treenode',
                        '.u-tree-treenode',
                        '[role="treeitem"]',
                        '[role="option"]',
                        '.wui-list-item',
                        '.ant-list-item',
                        '.u-list-item',
                        '[class*="list-item"]',
                        '[class*="ListItem"]',
                        'li'
                      ].join(',');
                      const direct = node.closest(containerSelector);
                      if (direct && root.contains(direct) && visible(direct)) return direct;
                      let current = node.parentElement;
                      for (let depth = 0; current && root.contains(current) && depth < 5; depth += 1, current = current.parentElement) {
                        if (!visible(current)) continue;
                        if (selectionControlFor(current) && normalize(current.innerText || current.textContent || current.getAttribute('title'))) {
                          return current;
                        }
                      }
                      return node;
                    };
                    const tableCellTargetFor = (node) => {
                      const cells = Array.from(node.querySelectorAll(tableCellSelector))
                        .filter(visible)
                        .sort((a, b) => {
                          const ar = a.getBoundingClientRect();
                          const br = b.getBoundingClientRect();
                          return ar.left - br.left || ar.top - br.top;
                        });
                      return cells[0] || null;
                    };
                    const derivedTableCandidates = () => {
                      const tableRootSelector = [
                        'table',
                        '[role="grid"]',
                        '.w-table',
                        '.wui-table',
                        '.ant-table',
                        '.u-table',
                        '[class*="table"]',
                        '[class*="Table"]'
                      ].join(',');
                      const tableRoots = Array.from(root.querySelectorAll(tableRootSelector))
                        .filter((el, index, all) => all.indexOf(el) === index)
                        .filter(visible);
                      const groups = [];
                      for (const tableRoot of tableRoots) {
                        const cells = Array.from(tableRoot.querySelectorAll(tableCellSelector))
                          .filter((cell, index, all) => all.indexOf(cell) === index)
                          .filter((cell) => visible(cell) && !cell.closest('thead'))
                          .filter((cell) => {
                            const role = String(cell.getAttribute('role') || '').toLowerCase();
                            const cls = String(cell.className || '').toLowerCase();
                            return role !== 'columnheader' && !/header|thead/.test(cls);
                          })
                          .map((cell) => {
                            const rect = cell.getBoundingClientRect();
                            return { cell, rect };
                          })
                          .sort((a, b) => a.rect.top - b.rect.top || a.rect.left - b.rect.left);
                        for (const item of cells) {
                          let group = groups.find((existing) => Math.abs(existing.top - item.rect.top) <= 3);
                          if (!group) {
                            group = { top: item.rect.top, cells: [] };
                            groups.push(group);
                          }
                          group.cells.push(item.cell);
                        }
                      }
                      return groups
                        .map((group) => {
                          const cells = group.cells
                            .filter(visible)
                            .sort((a, b) => a.getBoundingClientRect().left - b.getBoundingClientRect().left);
                          const text = normalize(cells.map((cell) => cell.innerText || cell.textContent || cell.getAttribute('title')).join(' '));
                          if (cells.length < 2 || !text) return null;
                          const row = cells[0].closest(looseTableRowSelector) || cells[0];
                          const selectionTarget = selectionControlFor(row);
                          const target = selectionTarget || cells[0];
                          const rect = target.getBoundingClientRect();
                          return {
                            target,
                            kind: 'table-row',
                            source: 'right-table',
                            rank: 0,
                            requiresSelection: true,
                            requiresControl: Boolean(selectionTarget),
                            text,
                            top: rect.top,
                            left: rect.left,
                            area: rect.width * rect.height
                          };
                        })
                        .filter(Boolean);
                    };
                    const excluded = [
                      'button',
                      'input',
                      'textarea',
                      'select',
                      'thead *',
                      '[role="columnheader"]',
                      '.wui-pagination',
                      '.ant-pagination',
                      '.u-pagination',
                      '[class*="pagination"]',
                      '[class*="Pagination"]',
                      '[class*="pager"]',
                      '[class*="Pager"]',
                      'tfoot',
                      '.yy-modal-footer *',
                      '.ant-modal-footer *',
                      '.w-modal-footer *',
                      '.wui-modal-footer *',
                      '.u-modal-footer *',
                      '[class*="footer"]',
                      '[class*="Footer"]'
                    ].join(',');
                    const selectors = [
                      'tbody tr',
                      '[role="row"]',
                      '.w-table-row',
                      '.wui-table-row',
                      '.ant-table-row',
                      '.u-table-row',
                      '[role="treeitem"]',
                      '.wui-tree-treenode',
                      '.wui-select-tree-treenode',
                      '.ant-tree-treenode',
                      '.u-tree-treenode',
                      '.wui-tree-node-content-wrapper',
                      '.wui-select-tree-node-content-wrapper',
                      '.ant-tree-node-content-wrapper',
                      '[role="option"]',
                      '.wui-select-item-option',
                      '.ant-select-item-option',
                      '.u-select-item-option',
                      '.wui-list-item',
                      '.ant-list-item',
                      '.u-list-item',
                      '[class*="table-row"]',
                      '[class*="TableRow"]',
                      'li'
                    ].join(',');
                    const candidates = [
                      ...derivedTableCandidates(),
                      ...Array.from(root.querySelectorAll(selectors))
                      .filter((el, index, all) => all.indexOf(el) === index)
                      .filter((el) => visible(el) && !disabled(el) && !el.matches(excluded) && !el.closest(excluded))
                      .map((el) => {
                        const container = candidateContainerFor(el);
                        const kind = candidateKindFor(container) === 'generic' ? candidateKindFor(el) : candidateKindFor(container);
                        const selectionTarget = selectionControlFor(container);
                        const target = selectionTarget || (kind === 'table-row' ? tableCellTargetFor(container) : null) || el;
                        const rect = target.getBoundingClientRect();
                        const source = kind === 'table-row'
                          ? 'right-table'
                          : (kind === 'tree-node' ? 'tree' : (kind === 'list-option' ? 'list' : 'generic'));
                        return {
                          target,
                          kind,
                          source,
                          rank: candidateRankFor(kind),
                          requiresSelection: kind === 'table-row' || Boolean(selectionTarget),
                          requiresControl: Boolean(selectionTarget),
                          text: normalize(container.innerText || container.textContent || container.getAttribute('title') || el.innerText || el.textContent || el.getAttribute('title')),
                          top: rect.top,
                          left: rect.left,
                          area: rect.width * rect.height
                        };
                      })
                    ]
                      .filter((item) => item.area > 0 && item.text)
                      .filter((item) => !emptyStateText(item.text))
                      .filter((item, index, all) => all.findIndex((other) => other.target === item.target) === index)
                      .sort((a, b) => a.rank - b.rank || a.top - b.top || a.left - b.left || a.area - b.area);
                    const candidateSelectors = candidates.slice(0, 30).map((candidate, index) => {
                      const markerValue = `${marker}-${index}`;
                      candidate.target.setAttribute('data-ydf-browser-first-reference', markerValue);
                      return {
                        selector: `[data-ydf-browser-first-reference="${markerValue}"]`,
                        kind: candidate.kind,
                        source: candidate.source,
                        text: candidate.text,
                        requiresSelection: candidate.requiresSelection,
                        requiresControl: candidate.requiresControl
                      };
                    });
                    return candidateSelectors;
                }""",
                marker,
            )
            if not click_target_selector:
                if debug_enabled:
                    print("[ydf-browser] popup-reference-first-candidate stage=missing", file=sys.stderr, flush=True)
                if require_unique:
                    self._last_popup_reference_first_candidate_error = json.dumps(
                        {
                            "candidate_count": 0,
                            "hint": "请使用更完整的值，或显式使用 first_available、row_number、列表或 selections",
                        },
                        ensure_ascii=False,
                    )
                return False
            raw_candidates = [click_target_selector] if isinstance(click_target_selector, str) else list(click_target_selector)
            candidates: list[dict[str, Any]] = []
            for item in raw_candidates:
                if isinstance(item, dict):
                    selector = str(item.get("selector") or "").strip()
                    if selector:
                        candidates.append(
                            {
                                "selector": selector,
                                "requires_selection": bool(item.get("requiresSelection")),
                                "requires_control": bool(item.get("requiresControl")),
                                "candidate_kind": str(item.get("kind") or item.get("candidate_kind") or "").strip() or "generic",
                                "candidate_source": str(item.get("source") or item.get("candidate_source") or "").strip() or "generic",
                                "candidate_text": str(item.get("text") or item.get("candidate_text") or "").strip(),
                            }
                        )
                elif item:
                    candidates.append(
                        {
                            "selector": str(item),
                            "requires_selection": False,
                            "requires_control": False,
                            "candidate_kind": "generic",
                            "candidate_source": "generic",
                            "candidate_text": "",
                        }
                    )
            candidates = [
                candidate for candidate in candidates
                if not _popup_reference_candidate_text_is_empty_state(candidate.get("candidate_text"))
            ]
            if debug_enabled:
                print(f"[ydf-browser] popup-reference-first-candidate stage=candidates count={len(candidates)}", file=sys.stderr, flush=True)
            table_candidates = [
                candidate for candidate in candidates
                if candidate.get("candidate_kind") == "table-row" or candidate.get("candidate_source") == "right-table"
            ]
            self._last_popup_reference_first_candidate_saw_table = bool(table_candidates)
            if require_right_table and not table_candidates:
                return False
            candidates_to_try = table_candidates or candidates
            if require_unique:
                deduplicated: list[dict[str, Any]] = []
                seen: set[tuple[str, str, str]] = set()
                normalized_unique_text = " ".join(str(unique_text or "").split())
                for candidate in candidates_to_try:
                    text = " ".join(str(candidate.get("candidate_text") or "").split())
                    identity = (
                        str(candidate.get("candidate_kind") or "generic"),
                        str(candidate.get("candidate_source") or "generic"),
                        text or str(candidate.get("selector") or ""),
                    )
                    if identity in seen:
                        continue
                    seen.add(identity)
                    deduplicated.append(candidate)
                if normalized_unique_text:
                    exact_candidate = next(
                        (
                            candidate for candidate in deduplicated
                            if " ".join(str(candidate.get("candidate_text") or "").split()) == normalized_unique_text
                        ),
                        None,
                    )
                    if exact_candidate is not None:
                        deduplicated = [exact_candidate]
                    else:
                        matching_candidates = [
                            candidate
                            for candidate in deduplicated
                            if _popup_reference_text_matches(candidate.get("candidate_text"), normalized_unique_text)
                        ]
                        if len(matching_candidates) == 1:
                            deduplicated = matching_candidates
                candidates_to_try = deduplicated
                if len(candidates_to_try) > 1:
                    preview = [str(item.get("candidate_text") or "") for item in candidates_to_try[:5]]
                    raise RuntimeError(
                        f"弹出参照标量值匹配到 {len(candidates_to_try)} 条候选，无法唯一确定目标: {preview}。"
                        "请使用更完整的值，或显式使用 first_available、row_number、列表或 selections。"
                    )
            for candidate in candidates_to_try:
                selector = str(candidate.get("selector") or "")
                requires_selection = bool(candidate.get("requires_selection"))
                requires_control = bool(candidate.get("requires_control"))
                if (
                    require_unique
                    and requires_selection
                    and (
                        candidate.get("candidate_kind") == "tree-node"
                        or candidate.get("candidate_source") == "tree"
                    )
                    and candidate.get("candidate_text")
                ):
                    self._last_popup_reference_first_candidate_attempted = True
                    if self._click_popup_reference_tree_node(
                        dialog,
                        str(candidate["candidate_text"]),
                        require_control=True,
                    ):
                        self._last_popup_reference_first_candidate = {
                            "candidate_kind": "tree-node",
                            "candidate_source": candidate.get("candidate_source") or "tree",
                            "candidate_text": candidate.get("candidate_text") or "",
                            "candidate_requires_selection": requires_selection,
                            "candidate_selected": True,
                        }
                        return True
                if debug_enabled:
                    print(f"[ydf-browser] popup-reference-first-candidate stage=click selector={selector} requires_selection={requires_selection}", file=sys.stderr, flush=True)
                target = dialog.locator(selector).first
                try:
                    target.scroll_into_view_if_needed(timeout=1000)
                except Exception:
                    pass
                if require_unique and not requires_selection:
                    self._last_popup_reference_first_candidate_attempted = True
                    try:
                        target.click(timeout=2000)
                    except Exception:
                        if self._popup_reference_dialog_still_visible(dialog):
                            try:
                                target.click(force=True, timeout=500)
                            except Exception:
                                continue
                    self._last_popup_reference_first_candidate = {
                        "candidate_kind": candidate.get("candidate_kind") or "generic",
                        "candidate_source": candidate.get("candidate_source") or "generic",
                        "candidate_text": candidate.get("candidate_text") or "",
                        "candidate_requires_selection": False,
                        "candidate_selected": True,
                    }
                    return True
                try:
                    self._last_popup_reference_first_candidate_attempted = True
                    target.click(timeout=2000)
                except Exception:
                    try:
                        self._last_popup_reference_first_candidate_attempted = True
                        target.click(force=True, timeout=2000)
                    except Exception:
                        continue
                if requires_control:
                    self._stabilize_popup_reference_selection(target, require_control=True)
                    candidate_selected = self._popup_reference_candidate_has_selection_state(
                        target,
                        require_control=True,
                    )
                else:
                    self._stabilize_popup_reference_selection(target)
                    candidate_selected = self._popup_reference_candidate_has_selection_state(target)
                if (requires_selection or self._popup_reference_candidate_requires_selection_state(target)) and not candidate_selected:
                    continue
                self._last_popup_reference_first_candidate = {
                    "candidate_kind": candidate.get("candidate_kind") or "generic",
                    "candidate_source": candidate.get("candidate_source") or "generic",
                    "candidate_text": candidate.get("candidate_text") or "",
                    "candidate_requires_selection": requires_selection,
                    "candidate_selected": candidate_selected,
                }
                if debug_enabled:
                    print("[ydf-browser] popup-reference-first-candidate stage=selected", file=sys.stderr, flush=True)
                return True
            if debug_enabled:
                print("[ydf-browser] popup-reference-first-candidate stage=not-selected", file=sys.stderr, flush=True)
            if table_candidates:
                diagnostic = {
                    "candidate_count": len(candidates),
                    "table_candidate_count": len(table_candidates),
                    "attempted": [
                        {
                            "candidate_kind": item.get("candidate_kind"),
                            "candidate_source": item.get("candidate_source"),
                            "candidate_text": item.get("candidate_text"),
                            "candidate_requires_selection": item.get("requires_selection"),
                        }
                        for item in table_candidates[:5]
                    ],
                }
                message = json.dumps(diagnostic, ensure_ascii=False)
                if not require_unique:
                    screenshot = self._save_diagnostic_screenshot("popup-reference-first-available-table-unselected")
                    if screenshot:
                        message = f"{message} | screenshot={screenshot}"
                self._last_popup_reference_first_candidate_error = message
            return False
        except RuntimeError:
            raise
        except Exception:
            return False

    def _click_popup_reference_table_row_by_index(self, dialog, row_number: int) -> bool:
        if row_number < 1:
            raise ValueError(f"弹出参照行号从 1 开始: {row_number}")
        try:
            marker = f"popup-row-index-{int(time.time() * 1000)}"
            click_target_selector = dialog.evaluate(
                """(root, args) => {
                    const rowNumber = args.rowNumber;
                    const marker = args.marker;
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
                    const rowSelector = [
                      'tbody tr',
                      '.w-table-tbody .w-table-row',
                      '.w-table-body .w-table-row',
                      '.wui-table-tbody .wui-table-row',
                      '.wui-table-body .wui-table-row',
                      '.ant-table-tbody .ant-table-row',
                      '.u-table-tbody .u-table-row',
                      '[role="grid"] [role="row"]',
                      '[class*="table-body"] [class*="table-row"]',
                      '[class*="TableBody"] [class*="TableRow"]'
                    ].join(',');
                    const cellSelector = [
                      'td',
                      '[role="gridcell"]',
                      '[role="cell"]',
                      '.wui-table-cell',
                      '.ant-table-cell',
                      '.u-table-cell'
                    ].join(',');
                    const rows = Array.from(root.querySelectorAll(rowSelector))
                      .filter((el, index, all) => all.indexOf(el) === index)
                      .filter((el) => visible(el) && !el.closest('thead'))
                      .filter((el) => Array.from(el.querySelectorAll(cellSelector)).some(visible));
                    const row = rows[rowNumber - 1];
                    if (!row) return '';
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
                    const pickers = Array.from(row.querySelectorAll(pickerSelector))
                      .filter((item, index, all) => all.indexOf(item) === index)
                      .filter((item) => visible(item) && !disabled(item))
                      .sort((a, b) => a.getBoundingClientRect().left - b.getBoundingClientRect().left);
                    const target = pickers[0] || row;
                    target.setAttribute('data-ydf-browser-popup-reference-row-index', marker);
                    return `[data-ydf-browser-popup-reference-row-index="${marker}"]`;
                }""",
                {"rowNumber": row_number, "marker": marker},
            )
            if not click_target_selector:
                return False
            target = dialog.locator(str(click_target_selector)).first
            try:
                target.scroll_into_view_if_needed(timeout=1000)
            except Exception:
                pass
            self._collapse_hovered_navigation_overlay()
            if not self._popup_reference_target_receives_pointer(target):
                return False
            try:
                target.click(timeout=2000)
            except Exception:
                if not self._popup_reference_target_receives_pointer(target):
                    return False
                target.click(force=True, timeout=2000)
            self._stabilize_popup_reference_selection(target)
            if self._popup_reference_candidate_requires_selection_state(target) and not self._popup_reference_candidate_has_selection_state(target):
                return False
            return True
        except Exception:
            return False

    def _fill_popup_reference_filter_fields(self, dialog, conditions: list[dict[str, str]]) -> bool:
        normalized_conditions = [
            {"field": str(item.get("field") or item.get("column") or "").strip(), "equals": str(item.get("equals") or "").strip()}
            for item in conditions
            if str(item.get("field") or item.get("column") or "").strip() and item.get("equals") is not None
        ]
        if not normalized_conditions:
            return False
        try:
            result = dialog.evaluate(
                """(root, conditions) => {
                    const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                    const compact = (value) => normalize(value).replace(/\\s+/g, '');
                    const labelKey = (value) => compact(value).replace(/^[*＊✱✳※]+/, '').replace(/[：:]+$/, '');
                    const fuzzyLabelMatches = (actualValue, wantedValue) => {
                      const actual = compact(actualValue);
                      const wanted = compact(wantedValue);
                      if (!actual || !wanted) return false;
                      if (actual === wanted || actual.includes(wanted)) return true;
                      if (wanted.length < 6 || actual.length < wanted.length || actual.length - wanted.length > 2) return false;
                      if (actual[0] !== wanted[0] || actual[actual.length - 1] !== wanted[wanted.length - 1]) return false;
                      let start = 0;
                      for (const char of wanted) {
                        const index = actual.indexOf(char, start);
                        if (index < 0) return false;
                        start = index + char.length;
                      }
                      return true;
                    };
                    const visible = (el) => {
                      const style = window.getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style && style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width > 0 && rect.height > 0;
                    };
                    const formRootFor = (el) => el.closest([
                      '.wui-form-item',
                      '.ant-form-item',
                      '.u-form-item',
                      '[class*="form-item"]',
                      '[class*="FormItem"]',
                      '[class*="query"]',
                      '[class*="Query"]',
                      'td',
                      'div'
                    ].join(','));
                    const choiceRootSelector = [
                      '.wui-select',
                      '.ant-select',
                      '.u-select',
                      '[role="combobox"]',
                      '[class*="tree-select"]',
                      '[class*="TreeSelect"]',
                      '[class*="select"]',
                      '[class*="Select"]',
                      '[class*="picker"]',
                      '[class*="Picker"]',
                      '[class*="cascader"]',
                      '[class*="Cascader"]',
                      '[class*="dropdown"]',
                      '[class*="Dropdown"]'
                    ].join(',');
                    const isPopupReferenceShell = (node) => {
                      if (!node) return false;
                      const probe = [node.className, node.getAttribute?.('class'), node.getAttribute?.('role')]
                        .join(' ')
                        .toLowerCase();
                      if (/table[-_ ]?select|tableselect|modal|dialog|popup|reference|refer/.test(probe)) return true;
                      if (node === root) return true;
                      return Boolean(node.querySelector?.([
                        'table',
                        '[role="grid"]',
                        '.wui-table',
                        '.ant-table',
                        '.u-table',
                        '[class*="table"]',
                        '[class*="Table"]'
                      ].join(',')));
                    };
                    const choiceRootFor = (input, owner) => {
                      const fieldRoot = input.closest(choiceRootSelector);
                      if (fieldRoot && root.contains(fieldRoot) && !isPopupReferenceShell(fieldRoot)) return fieldRoot;
                      return owner || input;
                    };
                    const looksLikeChoiceField = (input, owner) => {
                      const fieldRoot = choiceRootFor(input, owner);
                      const probe = [
                        input.getAttribute('role'),
                        input.getAttribute('aria-haspopup'),
                        input.className,
                        owner?.className,
                        fieldRoot?.className,
                      ].join(' ').toLowerCase();
                      if (/combobox|select|picker|cascader|dropdown|tree/.test(probe)) return true;
                      return Boolean((owner || input).querySelector([
                        '[role="combobox"]',
                        '.w-select-selection',
                        '.w-select-arrow',
                        '.wui-select-selector',
                        '.ant-select-selector',
                        '.u-select-selector',
                        '.wui-select-arrow',
                        '.ant-select-arrow',
                        '.u-select-arrow',
                        '[class*="select-arrow"]',
                        '[class*="SelectArrow"]'
                      ].join(',')));
                    };
                    const markChoiceRoot = (node, index) => {
                      const marker = `filter-choice-${Date.now()}-${index}-${Math.floor(Math.random() * 100000)}`;
                      node.setAttribute('data-ydf-browser-popup-reference-filter-field', marker);
                      return `[data-ydf-browser-popup-reference-filter-field="${marker}"]`;
                    };
                    const markTextInput = (node, index) => {
                      const marker = `filter-input-${Date.now()}-${index}-${Math.floor(Math.random() * 100000)}`;
                      node.setAttribute('data-ydf-browser-popup-reference-filter-input', marker);
                      return `[data-ydf-browser-popup-reference-filter-input="${marker}"]`;
                    };
                    const nearbyLabelTextFor = (input) => {
                      const inputRect = input.getBoundingClientRect();
                      const inputCenterY = inputRect.top + inputRect.height / 2;
                      const textNodeLabels = [];
                      try {
                        const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
                        let node = walker.nextNode();
                        while (node) {
                          const text = normalize(node.textContent || '');
                          const parent = node.parentElement;
                          if (text && text.length <= 40 && parent && visible(parent) && !parent.closest('script, style')) {
                            const range = document.createRange();
                            range.selectNodeContents(node);
                            for (const rect of Array.from(range.getClientRects())) {
                              if (rect.width > 0 && rect.height > 0) {
                                textNodeLabels.push({
                                  rect,
                                  text,
                                  centerY: rect.top + rect.height / 2
                                });
                              }
                            }
                            range.detach();
                          }
                          node = walker.nextNode();
                        }
                      } catch (error) {
                        // Ignore text node range failures; element labels below still work.
                      }
                      const labelSelector = [
                        'label',
                        '.wui-form-item-label',
                        '.ant-form-item-label',
                        '.u-form-item-label',
                        '[class*="label"]',
                        '[class*="Label"]',
                        'span',
                        'div'
                      ].join(',');
                      const elementLabels = Array.from(root.querySelectorAll(labelSelector))
                        .filter(visible)
                        .filter((el) => el !== input && !el.contains(input) && !input.contains(el))
                        .map((el) => {
                          const rect = el.getBoundingClientRect();
                          return {
                            rect,
                            text: normalize(el.innerText || el.textContent),
                            centerY: rect.top + rect.height / 2
                          };
                        })
                        .filter((item) => item.text && item.text.length <= 40);
                      const labels = [...elementLabels, ...textNodeLabels]
                        .filter((item) => item.rect.right <= inputRect.left + 16)
                        .filter((item) => item.rect.left >= inputRect.left - 420)
                        .filter((item) => Math.abs(item.centerY - inputCenterY) <= Math.max(24, inputRect.height, item.rect.height))
                        .sort((a, b) => Math.abs(a.rect.right - inputRect.left) - Math.abs(b.rect.right - inputRect.left));
                      return labels[0]?.text || '';
                    };
                    const labelTextFor = (input, nearbyLabelText = '') => {
                      const parts = [
                        input.getAttribute('placeholder'),
                        input.getAttribute('title'),
                        input.getAttribute('aria-label'),
                        input.getAttribute('name'),
                      ];
                      const id = input.getAttribute('id');
                      if (id) {
                        const label = root.querySelector(`label[for="${CSS.escape(id)}"]`);
                        if (label) parts.push(label.innerText || label.textContent);
                      }
                      const owner = formRootFor(input);
                      if (owner) {
                        const labelNodes = Array.from(owner.querySelectorAll([
                          'label',
                          '.wui-form-item-label',
                          '.ant-form-item-label',
                          '.u-form-item-label',
                          '[class*="label"]',
                          '[class*="Label"]'
                        ].join(','))).filter(visible);
                        parts.push(...labelNodes.map((item) => item.innerText || item.textContent));
                        parts.push(owner.innerText || owner.textContent);
                      }
                      parts.push(nearbyLabelText || nearbyLabelTextFor(input));
                      return normalize(parts.filter(Boolean).join(' '));
                    };
                    const candidates = Array.from(root.querySelectorAll([
                      'input:not([type="hidden"]):not([type="radio"]):not([type="checkbox"])',
                      'textarea',
                      '[contenteditable="true"]',
                      '[role="textbox"]'
                    ].join(',')))
                      .filter(visible)
                      .filter((input) => input.getAttribute('readonly') !== 'readonly' && input.getAttribute('aria-readonly') !== 'true')
                      .map((input, index) => {
                        const rect = input.getBoundingClientRect();
                        const nearbyLabelText = nearbyLabelTextFor(input);
                        return { input, index, nearbyLabelText, labelText: labelTextFor(input, nearbyLabelText), area: rect.width * rect.height };
                      })
                      .filter((item) => item.area > 0);
                    const used = new Set();
                    const missing = [];
                    const filled = [];
                    const choiceFields = [];
                    const textFields = [];
                    for (const condition of conditions) {
                      const field = normalize(condition.field);
                      const wanted = compact(field);
                      const scored = candidates
                        .filter((item) => !used.has(item.index))
                        .map((item) => {
                          const labelText = compact(item.labelText);
                          const nearbyLabel = compact(item.nearbyLabelText);
                          const labelTextKey = labelKey(item.labelText);
                          const nearbyLabelKey = labelKey(item.nearbyLabelText);
                          const placeholder = compact(item.input.getAttribute('placeholder'));
                          const title = compact(item.input.getAttribute('title'));
                          const aria = compact(item.input.getAttribute('aria-label'));
                          const nearbyLabelConflicts = nearbyLabelKey && nearbyLabelKey !== wanted;
                          let score = -1;
                          if (nearbyLabelKey === wanted) score = 1200;
                          else if (nearbyLabelConflicts) score = -1;
                          else if (labelTextKey === wanted) score = 1000;
                          else if (labelText.includes(wanted)) score = 800;
                          else if (placeholder === wanted || title === wanted || aria === wanted) score = 700;
                          else if (placeholder.includes(wanted) || title.includes(wanted) || aria.includes(wanted)) score = 600;
                          else if (fuzzyLabelMatches(labelText, wanted)) score = 500;
                          else if (
                            fuzzyLabelMatches(placeholder, wanted)
                            || fuzzyLabelMatches(title, wanted)
                            || fuzzyLabelMatches(aria, wanted)
                          ) score = 450;
                          return { ...item, score };
                        })
                        .filter((item) => item.score >= 0)
                        .sort((a, b) => b.score - a.score || a.index - b.index);
                      const target = scored[0];
                      if (!target) {
                        missing.push(field);
                        continue;
                      }
                      const owner = formRootFor(target.input);
                      const equals = String(condition.equals);
                      if (looksLikeChoiceField(target.input, owner)) {
                        const choiceRoot = choiceRootFor(target.input, owner);
                        choiceFields.push({ field, equals, rootSelector: markChoiceRoot(choiceRoot, target.index) });
                      } else {
                        textFields.push({ field, equals, inputSelector: markTextInput(target.input, target.index) });
                      }
                      used.add(target.index);
                      filled.push({ field, equals });
                    }
                    return { filled, missing, choiceFields, textFields };
                }""",
                normalized_conditions,
            )
        except Exception as exc:
            raise RuntimeError(f"无法填写弹出参照查询字段: {exc}") from exc
        missing = list((result or {}).get("missing") or [])
        if missing:
            diagnostic = self._collect_popup_reference_diagnostic_text(dialog)
            if self._popup_reference_has_generic_filter_input(dialog):
                first_value = next(
                    (
                        str(item.get("equals") or "").strip()
                        for item in normalized_conditions
                        if str(item.get("equals") or "").strip()
                    ),
                    "",
                )
                if first_value:
                    diagnostic = f"{diagnostic} | 当前参照只发现通用搜索框，请改用标量 filter: {first_value}"
                else:
                    diagnostic = f"{diagnostic} | 当前参照只发现通用搜索框，请改用标量 filter"
            screenshot = self._save_diagnostic_screenshot("popup-reference-filter-field-missing")
            if screenshot:
                diagnostic = f"{diagnostic} | screenshot={screenshot}"
            raise RuntimeError(f"未找到弹出参照查询字段: {', '.join(missing)}: {diagnostic}")
        for text_field in list((result or {}).get("textFields") or []):
            selector = str(text_field.get("inputSelector") or "").strip()
            equals = str(text_field.get("equals") or "").strip()
            if not selector:
                continue
            input_locator = dialog.locator(selector).first
            try:
                input_locator.fill(equals, timeout=2000)
            except Exception:
                try:
                    input_locator.evaluate(
                        """(node, value) => {
                            const descriptor = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
                            if (descriptor && descriptor.set && node instanceof HTMLInputElement) {
                              descriptor.set.call(node, value);
                            } else {
                              node.value = value;
                              node.textContent = value;
                            }
                            for (const eventName of ['input', 'change', 'keyup']) {
                              const event = eventName === 'input' && typeof InputEvent !== 'undefined'
                                ? new InputEvent(eventName, { bubbles: true, inputType: 'insertText', data: value })
                                : new Event(eventName, { bubbles: true });
                              node.dispatchEvent(event);
                            }
                        }""",
                        equals,
                    )
                except Exception:
                    pass
        for choice in list((result or {}).get("choiceFields") or []):
            selector = str(choice.get("rootSelector") or "").strip()
            equals = str(choice.get("equals") or "").strip()
            if not selector or not equals:
                continue
            root = dialog.locator(selector).first
            fill_locator = self._resolve_fill_locator_from_root(root)
            try:
                self._select_query_choice(root, fill_locator, equals)
            except RuntimeError:
                if self._popup_reference_filter_choice_has_prefix_value(root, equals):
                    continue
                raise
        return bool((result or {}).get("filled"))

    def _popup_reference_has_generic_filter_input(self, dialog) -> bool:
        try:
            return bool(
                dialog.evaluate(
                    """(root) => {
                        const visible = (el) => {
                          if (!el || !(el instanceof HTMLElement)) return false;
                          const style = window.getComputedStyle(el);
                          const rect = el.getBoundingClientRect();
                          return style && style.visibility !== 'hidden' && style.display !== 'none'
                            && rect.width > 0 && rect.height > 0;
                        };
                        return Array.from(root.querySelectorAll('input:not([type="hidden"]), textarea, [role="textbox"]'))
                          .some((input) => {
                            if (!visible(input)) return false;
                            const text = [
                              input.getAttribute('placeholder'),
                              input.getAttribute('aria-label'),
                              input.getAttribute('title')
                            ].join(' ');
                            return /输入关键字|关键字|搜索|查询|请输入/.test(text);
                          });
                    }"""
                )
            )
        except Exception:
            return False

    def _popup_reference_filter_choice_has_prefix_value(self, root, value: str) -> bool:
        target_code = _leading_code(value)
        if len(target_code) < 4:
            return False
        try:
            text = str(
                root.evaluate(
                    """(node) => {
                        const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                        const dropdownSelector = [
                          '.w-select-dropdown',
                          '.wui-select-dropdown',
                          '.ant-select-dropdown',
                          '.u-select-dropdown',
                          '[role="listbox"]',
                          '[class*="dropdown"]',
                          '[class*="popup"]'
                        ].join(',');
                        const values = [];
                        const outsideDropdown = (el) => !el.closest(dropdownSelector);
                        for (const input of Array.from(node.querySelectorAll('input, textarea, select'))) {
                          if (outsideDropdown(input)) values.push(input.value, input.getAttribute('title'));
                        }
                        for (const item of Array.from(node.querySelectorAll(
                          '.wui-select-selection-item, .ant-select-selection-item, .u-select-selection-item, [class*="selection-item"], [class*="SelectionItem"], [class*="selected-value"], [class*="SelectedValue"]'
                        ))) {
                          if (outsideDropdown(item)) values.push(item.getAttribute('title'), item.innerText, item.textContent);
                        }
                        values.push(node.getAttribute('title'), node.innerText, node.textContent);
                        return normalize(values.filter(Boolean).join(' '));
                    }"""
                )
            )
        except Exception:
            return False
        for code in re.findall(r"\d+", text):
            if len(code) >= 3 and len(code) < len(target_code) and target_code.startswith(code):
                return True
        return False

    def _fill_popup_reference_filter(self, dialog, value: str) -> None:
        filter_input = self._first_visible_child_locator(dialog, build_popup_reference_filter_selectors())
        if filter_input is None:
            diagnostic = self._collect_popup_reference_diagnostic_text(dialog)
            screenshot = self._save_diagnostic_screenshot("popup-reference-filter-missing")
            if screenshot:
                diagnostic = f"{diagnostic} | screenshot={screenshot}"
            raise RuntimeError(f"未找到弹出参照过滤框: {diagnostic}")
        try:
            filter_input.click(timeout=1500)
            filter_input.press("Meta+A", timeout=800)
            filter_input.press("Control+A", timeout=800)
            filter_input.fill(value, timeout=2000)
        except Exception:
            filter_input.fill(value, timeout=2000)
        try:
            filter_input.evaluate(
                """(node, value) => {
                    const descriptor = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
                    if (descriptor && descriptor.set && node instanceof HTMLInputElement) {
                      descriptor.set.call(node, value);
                    } else {
                      node.value = value;
                      node.textContent = value;
                    }
                    for (const eventName of ['input', 'change', 'keyup']) {
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

    def _submit_popup_reference_filter(self, dialog) -> None:
        page = self._require_page()
        for selector in build_popup_reference_filter_submit_selectors():
            try:
                locator = dialog.locator(selector)
                count = locator.count()
            except Exception:
                continue
            for index in range(count):
                candidate = locator.nth(index)
                try:
                    if not candidate.is_visible(timeout=300):
                        continue
                    candidate.click(timeout=1500)
                    self._wait_for_timeout(800)
                    return
                except PopupReferenceError:
                    raise
                except Exception:
                    continue
        try:
            active = dialog.locator(
                'input:not([type="hidden"]):focus, textarea:focus, [contenteditable="true"]:focus, [role="textbox"]:focus'
            ).first
            if active.count() and active.is_visible(timeout=300):
                active.press("Enter", timeout=800)
                self._wait_for_timeout(800)
                return
        except PopupReferenceError:
            raise
        except Exception:
            pass
        try:
            filter_input = self._first_visible_child_locator(dialog, build_popup_reference_filter_selectors())
            if filter_input is None:
                return
            box = filter_input.bounding_box(timeout=300)
            if not box:
                return
            page.mouse.click(box["x"] + box["width"] - 16, box["y"] + box["height"] / 2)
            self._wait_for_timeout(800)
        except PopupReferenceError:
            raise
        except Exception:
            return

    def _click_popup_reference_tree_node(
        self,
        dialog,
        value: str,
        *,
        require_control: bool = False,
    ) -> bool:
        try:
            marker = f"node-{int(time.time() * 1000)}"
            script = """(root, args) => {
                    const value = args.value;
                    const marker = args.marker;
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
                    const exactText = (el) => normalize(el.getAttribute('title') || el.innerText || el.textContent) === value;
                    const contentSelector = [
                      '.wui-tree-node-content-wrapper',
                      '.wui-select-tree-node-content-wrapper',
                      '.ant-tree-node-content-wrapper',
                      '.u-tree-node-content-wrapper',
                      '[class*="tree-node-content"]',
                      '[class*="node-content"]'
                    ].join(',');
                    const nodeSelector = [
                      '.wui-tree-treenode',
                      '.wui-select-tree-treenode',
                      '.ant-tree-treenode',
                      '.u-tree-treenode',
                      '[role="treeitem"]',
                      'li'
                    ].join(',');
                    const selectionControlFor = (node) => {
                      const controlSelector = [
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
                      const wrapperSelector = [
                        'label',
                        '.wui-tree-checkbox',
                        '.wui-select-tree-checkbox',
                        '.ant-tree-checkbox',
                        '.u-tree-checkbox',
                        '.wui-tree-radio',
                        '.wui-select-tree-radio',
                        '.ant-tree-radio',
                        '.u-tree-radio',
                        '.wui-radio-wrapper',
                        '.wui-checkbox-wrapper',
                        '.ant-radio-wrapper',
                        '.ant-checkbox-wrapper',
                        '.u-radio-wrapper',
                        '.u-checkbox-wrapper',
                        '[class*="radio-wrapper"]',
                        '[class*="RadioWrapper"]',
                        '[class*="checkbox-wrapper"]',
                        '[class*="CheckboxWrapper"]'
                      ].join(',');
                      const rankFor = (target) => {
                        const tag = String(target.tagName || '').toLowerCase();
                        const role = String(target.getAttribute('role') || '').toLowerCase();
                        const type = String(target.getAttribute('type') || '').toLowerCase();
                        const className = String(target.className || '').toLowerCase();
                        if (tag === 'input' && (type === 'radio' || type === 'checkbox')) return 0;
                        if (tag === 'label') return 1;
                        if (role === 'radio' || role === 'checkbox') return 2;
                        if (/radio|checkbox/.test(className) && !/group/.test(className)) return 3;
                        return 8;
                      };
                      return Array.from(node.querySelectorAll(controlSelector))
                        .filter((item, index, all) => all.indexOf(item) === index)
                        .filter((item) => !disabled(item))
                        .map((item) => {
                          const wrapper = item.closest(wrapperSelector);
                          const target = wrapper && node.contains(wrapper) && visible(wrapper) ? wrapper : item;
                          return { target, rank: rankFor(target) };
                        })
                        .filter((item, index, all) => all.findIndex((other) => other.target === item.target) === index)
                        .sort((a, b) => {
                          const ar = a.target.getBoundingClientRect();
                          const br = b.target.getBoundingClientRect();
                          return a.rank - b.rank || ar.left - br.left || (ar.width * ar.height) - (br.width * br.height);
                        })[0]?.target || null;
                    };
                    const treeRoots = Array.from(root.querySelectorAll([
                      '.wui-tree',
                      '.wui-select-tree',
                      '.ant-tree',
                      '.u-tree',
                      '[role="tree"]',
                      '[role="tree-node"]'
                    ].join(','))).filter(visible);
                    if (!treeRoots.length) return '';
                    const searchRoots = treeRoots;
                    const candidates = searchRoots.flatMap((tree) => Array.from(tree.querySelectorAll([
                      '[role="treeitem"]',
                      '[title]',
                      '.wui-tree-title',
                      '.wui-tree-node-content-wrapper',
                      '.wui-tree-treenode',
                      '.wui-select-tree-title',
                      '.wui-select-tree-node-content-wrapper',
                      '.ant-tree-title',
                      '.ant-tree-node-content-wrapper',
                      '.ant-tree-treenode',
                      '.u-tree-node-content-wrapper',
                      '[class*="tree"] [class*="title"]',
                      '[class*="tree"] [class*="node"]'
                    ].join(','))))
                      .filter((el, index, all) => all.indexOf(el) === index)
                      .filter((el) => visible(el) && el.tagName !== 'INPUT' && el.tagName !== 'TEXTAREA' && exactText(el))
                      .map((el) => {
                        const content = el.closest(contentSelector);
                        const node = el.closest(nodeSelector);
                        const nodeContent = node
                          ? Array.from(node.querySelectorAll(contentSelector)).find((item) => visible(item) && exactText(item))
                          : null;
                        const baseTarget = content || nodeContent || node || el;
                        const selectionTarget = node ? selectionControlFor(node) : null;
                        const target = selectionTarget || baseTarget;
                        const rect = target.getBoundingClientRect();
                        const className = String(target.className || '');
                        let score = rect.width * rect.height;
                        if (/content-wrapper|node-content/i.test(className)) score -= 1000000;
                        if (/treenode|treeitem/i.test(className)) score -= 100000;
                        return { target, score };
                      })
                      .sort((a, b) => a.score - b.score);
                    const target = candidates[0] && candidates[0].target;
                    if (!target) return '';
                    target.setAttribute('data-ydf-browser-popup-reference-node', marker);
                    return `[data-ydf-browser-popup-reference-node="${marker}"]`;
                }"""
            args = {"value": value, "marker": marker}
            try:
                click_target_selector = dialog.evaluate(script, args, timeout=1800)
            except TypeError:
                click_target_selector = dialog.evaluate(script, args)
            if not click_target_selector:
                return False
            target = dialog.locator(str(click_target_selector)).first
            try:
                target.scroll_into_view_if_needed(timeout=1000)
            except Exception:
                pass
            try:
                target.click(timeout=2000)
            except Exception:
                target.click(force=True, timeout=2000)
            if require_control:
                self._stabilize_popup_reference_selection(target, require_control=True)
                if not self._popup_reference_candidate_has_selection_state(target, require_control=True):
                    return False
            else:
                self._stabilize_popup_reference_selection(target)
            return True
        except Exception:
            return self._click_popup_reference_text_fallback(dialog, value)

    def _search_popup_reference_tree_node(self, dialog, value: str) -> bool:
        search_terms = _popup_reference_tree_search_terms(value)
        if not search_terms:
            return False
        original_value = ""
        input_selector = ""
        debug_enabled = bool(os.environ.get("YDF_BROWSER_DEBUG_POPUP_REFERENCE"))
        for term in search_terms:
            if debug_enabled:
                print(f"[ydf-browser] popup-reference-tree-search term={term} stage=mark-input", file=sys.stderr, flush=True)
            input_selector = self._mark_popup_reference_tree_search_input(dialog)
            if not input_selector:
                if debug_enabled:
                    print("[ydf-browser] popup-reference-tree-search stage=input-missing", file=sys.stderr, flush=True)
                return False
            search_input = dialog.locator(input_selector).first
            if term == search_terms[0]:
                try:
                    original_value = search_input.input_value(timeout=500)
                except Exception:
                    pass
            try:
                search_input.fill(term, timeout=1500)
            except Exception:
                try:
                    search_input.click(timeout=1000)
                    search_input.press("Meta+A", timeout=500)
                    search_input.press("Control+A", timeout=500)
                    search_input.type(term, timeout=1500)
                except Exception:
                    if debug_enabled:
                        print(f"[ydf-browser] popup-reference-tree-search term={term} stage=fill-failed", file=sys.stderr, flush=True)
                    continue
            pressed_or_clicked = False
            if debug_enabled:
                print(f"[ydf-browser] popup-reference-tree-search term={term} stage=filled", file=sys.stderr, flush=True)
            try:
                search_input.press("Enter", timeout=1000)
                pressed_or_clicked = True
            except Exception:
                pass
            if debug_enabled:
                print(f"[ydf-browser] popup-reference-tree-search term={term} stage=pressed-enter value={pressed_or_clicked}", file=sys.stderr, flush=True)
            trigger_selector = self._mark_popup_reference_tree_search_trigger(dialog, input_selector)
            if trigger_selector:
                trigger = dialog.locator(trigger_selector).first
                try:
                    trigger.click(timeout=1200)
                    pressed_or_clicked = True
                except Exception:
                    try:
                        trigger.click(force=True, timeout=1200)
                        pressed_or_clicked = True
                    except Exception:
                        pass
            if debug_enabled:
                print(f"[ydf-browser] popup-reference-tree-search term={term} stage=trigger value={bool(trigger_selector)}", file=sys.stderr, flush=True)
            try:
                self._wait_for_timeout(900 if pressed_or_clicked else 500)
            except PopupReferenceError:
                raise
            except Exception:
                time.sleep(0.5)
            if debug_enabled:
                print(f"[ydf-browser] popup-reference-tree-search term={term} stage=visible-check", file=sys.stderr, flush=True)
            if self._popup_reference_tree_node_visible(dialog, value):
                if debug_enabled:
                    print(f"[ydf-browser] popup-reference-tree-search term={term} stage=visible", file=sys.stderr, flush=True)
                return True
            if debug_enabled:
                print(f"[ydf-browser] popup-reference-tree-search term={term} stage=not-visible", file=sys.stderr, flush=True)
        try:
            search_input = dialog.locator(input_selector).first
            search_input.fill(original_value, timeout=1500)
            search_input.press("Enter", timeout=1000)
            trigger_selector = self._mark_popup_reference_tree_search_trigger(dialog, input_selector)
            if trigger_selector:
                dialog.locator(trigger_selector).first.click(timeout=1200)
            self._wait_for_timeout(500)
        except PopupReferenceError:
            raise
        except Exception:
            pass
        return False

    def _mark_popup_reference_tree_search_input(self, dialog) -> str:
        try:
            marker = f"popup-tree-search-{int(time.time() * 1000)}"
            script = """(root, marker) => {
                    const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                    const visible = (el) => {
                      if (!el || !(el instanceof HTMLElement)) return false;
                      const style = window.getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style && style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width > 0 && rect.height > 0;
                    };
                    const rootRect = root.getBoundingClientRect();
                    const tableSelector = [
                      'table',
                      '[role="grid"]',
                      '.wui-table',
                      '.w-table',
                      '.ant-table',
                      '.u-table',
                      '[class*="table"]',
                      '[class*="Table"]'
                    ].join(',');
                    const tableLefts = Array.from(root.querySelectorAll(tableSelector))
                      .filter(visible)
                      .map((el) => el.getBoundingClientRect().left)
                      .filter((left) => left > rootRect.left + 80)
                      .sort((a, b) => a - b);
                    const boundary = tableLefts[0] || (rootRect.left + Math.min(rootRect.width * 0.42, 430));
                    const inputSelector = 'input:not([type="hidden"]), textarea, [contenteditable="true"], [role="textbox"]';
                    const footerSelector = [
                      '.ant-modal-footer',
                      '.wui-modal-footer',
                      '.yy-modal-footer',
                      '.u-modal-footer',
                      '[class*="pagination"]',
                      '[class*="Pagination"]',
                      '[class*="footer"]',
                      '[class*="Footer"]'
                    ].join(',');
                    const candidates = Array.from(root.querySelectorAll(inputSelector))
                      .filter(visible)
                      .filter((el) => !el.closest(footerSelector))
                      .map((el, index) => {
                        const rect = el.getBoundingClientRect();
                        const text = normalize([
                          el.getAttribute('placeholder'),
                          el.getAttribute('aria-label'),
                          el.getAttribute('title'),
                          el.className,
                          el.parentElement && el.parentElement.className
                        ].join(' '));
                        const keyword = /关键字|搜索|查询|请输入|search|keyword/i.test(text);
                        return { el, index, rect, text, keyword };
                      })
                      .filter((item) => item.rect.left < boundary - 8)
                      .filter((item) => item.keyword || item.rect.width >= 120)
                      .sort((a, b) => {
                        return Number(b.keyword) - Number(a.keyword)
                          || a.rect.top - b.rect.top
                          || a.rect.left - b.rect.left
                          || a.index - b.index;
                      });
                    const target = candidates[0] && candidates[0].el;
                    if (!target) return '';
                    target.setAttribute('data-ydf-browser-popup-tree-search', marker);
                    return `[data-ydf-browser-popup-tree-search="${marker}"]`;
                }"""
            try:
                selector = dialog.evaluate(script, marker, timeout=1500)
            except TypeError:
                selector = dialog.evaluate(script, marker)
            return str(selector or "").strip()
        except Exception:
            return ""

    def _mark_popup_reference_tree_search_trigger(self, dialog, input_selector: str) -> str:
        try:
            marker = f"popup-tree-search-trigger-{int(time.time() * 1000)}"
            script = """(root, args) => {
                    const input = root.querySelector(args.inputSelector);
                    if (!input) return '';
                    const visible = (el) => {
                      if (!el || !(el instanceof HTMLElement)) return false;
                      const style = window.getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style && style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width > 0 && rect.height > 0;
                    };
                    const inputRect = input.getBoundingClientRect();
                    const clickableSelector = [
                      'button',
                      '[role="button"]',
                      'a',
                      '.wui-input-search-button',
                      '.ant-input-search-button',
                      '.u-input-search-button',
                      '.wui-input-suffix',
                      '.ant-input-suffix',
                      '.u-input-suffix',
                      'span',
                      'i',
                      '[class*="icon"]',
                      '[class*="Icon"]'
                    ].join(',');
                    const searchText = /(search|sousuo|fangdajing|magnif|查询|搜索)/i;
                    const roots = [
                      input.parentElement,
                      input.parentElement && input.parentElement.parentElement,
                      input.closest('[class*="input"]'),
                      input.closest('[class*="Input"]')
                    ].filter(Boolean);
                    const candidates = roots
                      .flatMap((parent) => Array.from(parent.querySelectorAll(clickableSelector)))
                      .filter((el, index, all) => all.indexOf(el) === index)
                      .filter(visible)
                      .map((el, index) => {
                        const rect = el.getBoundingClientRect();
                        const text = [
                          el.className,
                          el.getAttribute('title'),
                          el.getAttribute('aria-label'),
                          el.innerText,
                          el.textContent
                        ].join(' ');
                        return { el, rect, index, text };
                      })
                      .filter((item) => searchText.test(item.text))
                      .filter((item) => item.rect.left >= inputRect.left - 8 && item.rect.left <= inputRect.right + 80)
                      .sort((a, b) => a.rect.left - b.rect.left || a.index - b.index);
                    const target = candidates[0] && candidates[0].el;
                    if (!target) return '';
                    target.setAttribute('data-ydf-browser-popup-tree-search-trigger', args.marker);
                    return `[data-ydf-browser-popup-tree-search-trigger="${args.marker}"]`;
                }"""
            args = {"inputSelector": input_selector, "marker": marker}
            try:
                selector = dialog.evaluate(script, args, timeout=1200)
            except TypeError:
                selector = dialog.evaluate(script, args)
            return str(selector or "").strip()
        except Exception:
            return ""

    def _click_popup_reference_text_fallback(self, dialog, value: str) -> bool:
        try:
            marker = f"node-{int(time.time() * 1000)}"
            script = """(root, args) => {
                    const value = args.value;
                    const marker = args.marker;
                    const normalize = (text) => String(text || '').replace(/\\s+/g, ' ').trim();
                    const visible = (el) => {
                      const style = window.getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style && style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width > 0 && rect.height > 0;
                    };
                    const treeRoots = Array.from(root.querySelectorAll([
                      '.wui-tree',
                      '.wui-select-tree',
                      '.ant-tree',
                      '.u-tree',
                      '[role="tree"]',
                      '[role="tree-node"]'
                    ].join(','))).filter(visible);
                    if (!treeRoots.length) return false;
                    const searchRoots = treeRoots;
                    const candidates = searchRoots.flatMap((tree) => Array.from(tree.querySelectorAll([
                      '[role="treeitem"]',
                      '[title]',
                      '.wui-tree-title',
                      '.wui-tree-node-content-wrapper',
                      '.wui-tree-treenode',
                      '.wui-select-tree-title',
                      '.wui-select-tree-node-content-wrapper',
                      '.ant-tree-title',
                      '.ant-tree-node-content-wrapper',
                      '.ant-tree-treenode',
                      '.u-tree-node-content-wrapper',
                      '[class*="tree"] [class*="title"]',
                      '[class*="tree"] [class*="node"]'
                    ].join(',')))).filter((el, index, all) => all.indexOf(el) === index)
                      .filter((el) => visible(el) && el.tagName !== 'INPUT' && el.tagName !== 'TEXTAREA')
                      .slice(0, 1500);
                    candidates.sort((a, b) => {
                      const ar = a.getBoundingClientRect();
                      const br = b.getBoundingClientRect();
                      return (ar.width * ar.height) - (br.width * br.height);
                    });
                    for (const candidate of candidates) {
                      const text = normalize(candidate.getAttribute('title') || candidate.innerText || candidate.textContent);
                      if (text === value) {
                        const target = candidate.closest(
                          '.wui-tree-node-content-wrapper, .wui-select-tree-node-content-wrapper, .ant-tree-node-content-wrapper, .u-tree-node-content-wrapper, [class*="tree-node-content"], [class*="node-content"], [role="treeitem"]'
                        ) || candidate;
                        target.setAttribute('data-ydf-browser-popup-reference-node', marker);
                        return `[data-ydf-browser-popup-reference-node="${marker}"]`;
                      }
                    }
                    return '';
                }"""
            args = {"value": value, "marker": marker}
            try:
                click_target_selector = dialog.evaluate(script, args, timeout=1800)
            except TypeError:
                click_target_selector = dialog.evaluate(script, args)
            if not click_target_selector:
                return False
            dialog.locator(str(click_target_selector)).first.click(timeout=2000)
            return True
        except Exception:
            return False

    def _click_popup_reference_table_row(self, dialog, match: dict[str, Any]) -> bool:
        wanted, match_mode = _popup_reference_match_value(match)
        if not wanted:
            return False
        column = str(match.get("column") or match.get("field") or "").strip()
        try:
            marker = f"row-{int(time.time() * 1000)}"
            click_target_selector = dialog.evaluate(
                """(root, args) => {
                    const wanted = args.wanted;
                    const column = args.column;
                    const matchMode = args.matchMode || 'equals';
                    const marker = args.marker;
                    const normalize = (text) => String(text || '').replace(/\\s+/g, ' ').trim();
                    const compact = (text) => normalize(text).replace(/\\s+/g, '');
                    const fuzzyLabelMatches = (actualValue, wantedValue) => {
                      const actual = compact(actualValue);
                      const wanted = compact(wantedValue);
                      if (!actual || !wanted) return false;
                      if (actual === wanted || actual.includes(wanted)) return true;
                      if (wanted.length < 6 || actual.length < wanted.length || actual.length - wanted.length > 2) return false;
                      if (actual[0] !== wanted[0] || actual[actual.length - 1] !== wanted[wanted.length - 1]) return false;
                      let start = 0;
                      for (const char of wanted) {
                        const index = actual.indexOf(char, start);
                        if (index < 0) return false;
                        start = index + char.length;
                      }
                      return true;
                    };
                    const valueMatches = (actualValue) => {
                      const actual = normalize(actualValue);
                      if (!actual || !wanted) return false;
                      if (matchMode === 'contains') return actual.includes(wanted);
                      return actual === wanted || actual.includes(wanted);
                    };
                    const visible = (el) => {
                      const style = window.getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style && style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width > 0 && rect.height > 0;
                    };
                    const textOf = (el) => normalize(el?.getAttribute?.('title') || el?.innerText || el?.textContent || '');
                    const rowSelector = [
                      'tbody tr',
                      '.w-table-tbody .w-table-row',
                      '.w-table-body .w-table-row',
                      '.wui-table-tbody .wui-table-row',
                      '.wui-table-body .wui-table-row',
                      '.ant-table-tbody .ant-table-row',
                      '.u-table-tbody .u-table-row',
                      '[role="grid"] [role="row"]',
                      '[class*="table-body"] [class*="table-row"]',
                      '[class*="TableBody"] [class*="TableRow"]'
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
                    const rowRoots = Array.from(root.querySelectorAll(rowSelector))
                      .filter((el, index, all) => all.indexOf(el) === index)
                      .filter((el) => visible(el) && !el.closest('thead'))
                      .filter((el) => Array.from(el.querySelectorAll(cellSelector)).some(visible));
                    const columnInfoFor = (row) => {
                      if (!column) return { index: -1, headerCount: 0 };
                      const table = row.closest('table, [role="grid"], .w-table, .wui-table, .ant-table, .u-table, [class*="table"], [class*="Table"]') || root;
                      let headers = Array.from(table.querySelectorAll(headerSelector)).filter(visible);
                      if (!headers.length) {
                        headers = Array.from(root.querySelectorAll(headerSelector)).filter(visible);
                      }
                      const headerTexts = headers.map(textOf);
                      const normalizedColumn = normalize(column);
                      return {
                        index: headerTexts.findIndex(
                          (header) => header === normalizedColumn || header.includes(normalizedColumn) || fuzzyLabelMatches(header, normalizedColumn)
                        ),
                        headerCount: headerTexts.length,
                      };
                    };
                    const rowMatches = (row) => {
                      const cells = Array.from(row.querySelectorAll(cellSelector)).filter(visible);
                      const info = columnInfoFor(row);
                      if (column && info.index < 0) return false;
                      const offset = column && info.headerCount > 0 && cells.length > info.headerCount
                        ? cells.length - info.headerCount
                        : 0;
                      const cell = cells[info.index + offset] || cells[info.index];
                      if (column && !cell) return false;
                      if (info.index >= 0 && cell) {
                        const cellText = textOf(cell);
                        return valueMatches(cellText);
                      }
                      return valueMatches(textOf(row));
                    };
                    const clickableSelectionTarget = (item, row) => {
                      const wrapperSelector = [
                        'label',
                        '.wui-tree-checkbox',
                        '.wui-select-tree-checkbox',
                        '.ant-tree-checkbox',
                        '.u-tree-checkbox',
                        '.wui-tree-radio',
                        '.wui-select-tree-radio',
                        '.ant-tree-radio',
                        '.u-tree-radio',
                        '.wui-radio-wrapper',
                        '.wui-checkbox-wrapper',
                        '.ant-radio-wrapper',
                        '.ant-checkbox-wrapper',
                        '.u-radio-wrapper',
                        '.u-checkbox-wrapper',
                        '[class*="radio-wrapper"]',
                        '[class*="RadioWrapper"]',
                        '[class*="checkbox-wrapper"]',
                        '[class*="CheckboxWrapper"]'
                      ].join(',');
                      const direct = item.closest(wrapperSelector);
                      const rankFor = (target) => {
                        const tag = String(target.tagName || '').toLowerCase();
                        const className = String(target.className || '').toLowerCase();
                        const role = String(target.getAttribute('role') || '').toLowerCase();
                        const type = String(target.getAttribute('type') || '').toLowerCase();
                        if (tag === 'input' && (type === 'radio' || type === 'checkbox')) return 0;
                        if (tag === 'label') return 1;
                        if (role === 'radio' || role === 'checkbox') return 2;
                        if (/radio|checkbox/.test(className) && !/group/.test(className)) return 3;
                        if (/radio|checkbox/.test(className)) return 8;
                        return 10;
                      };
                      const itemTag = String(item.tagName || '').toLowerCase();
                      const itemType = String(item.getAttribute('type') || '').toLowerCase();
                      if (itemTag === 'input' && (itemType === 'radio' || itemType === 'checkbox') && visible(item)) {
                        return { target: item, rank: 0 };
                      }
                      if (direct && row.contains(direct) && visible(direct)) return { target: direct, rank: rankFor(direct) };
                      let current = item;
                      while (current && current !== row) {
                        if (visible(current)) return { target: current, rank: rankFor(current) };
                        current = current.parentElement;
                      }
                      return visible(row) ? { target: row, rank: 20 } : null;
                    };
                    let matchingRows = rowRoots.filter(rowMatches);
                    if (!matchingRows.length && column) {
                      matchingRows = rowRoots.filter((row) => textOf(row).includes(wanted));
                    }
                    const candidates = matchingRows
                      .map((row) => {
                        const selector = [
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
                        const picker = Array.from(row.querySelectorAll(selector))
                          .filter((item, index, all) => all.indexOf(item) === index)
                          .filter((item) => {
                            const className = String(item.className || '');
                            return !/disabled/i.test(className) && item.getAttribute('aria-disabled') !== 'true';
                          })
                          .map((item) => clickableSelectionTarget(item, row))
                          .filter(Boolean)
                          .filter((item, index, all) => all.findIndex((other) => other.target === item.target) === index)
                          .filter((item) => visible(item.target))
                          .sort((a, b) => {
                            const ar = a.target.getBoundingClientRect();
                            const br = b.target.getBoundingClientRect();
                            return a.rank - b.rank || ar.left - br.left || (ar.width * ar.height) - (br.width * br.height);
                          })[0]?.target;
                        const target = picker || row;
                        const rect = target.getBoundingClientRect();
                        return { target, score: rect.width * rect.height };
                      })
                      .sort((a, b) => a.score - b.score);
                    const target = candidates[0] && candidates[0].target;
                    if (!target) return '';
                    target.setAttribute('data-ydf-browser-popup-reference-row', marker);
                    return `[data-ydf-browser-popup-reference-row="${marker}"]`;
                }""",
                {"wanted": wanted, "matchMode": match_mode, "column": column, "marker": marker},
            )
            if click_target_selector:
                target = dialog.locator(str(click_target_selector)).first
                try:
                    target.scroll_into_view_if_needed(timeout=1000)
                except Exception:
                    pass
                try:
                    target.click(timeout=2000)
                except Exception:
                    try:
                        target.click(force=True, timeout=2000)
                    except Exception:
                        clicked = bool(
                            dialog.evaluate(
                                """(root, selector) => {
                                    const target = root.querySelector(selector);
                                    if (!target) return false;
                                    target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                                    target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                                    target.click();
                                    return true;
                                }""",
                                str(click_target_selector),
                            )
                        )
                        if not clicked:
                            raise
                requires_selection = self._popup_reference_candidate_requires_selection_state(target)
                if requires_selection:
                    self._stabilize_popup_reference_selection(target, require_control=True)
                else:
                    self._stabilize_popup_reference_selection(target)
                if requires_selection and not self._popup_reference_candidate_has_selection_state(
                    target,
                    require_control=True,
                ):
                    return False
                return True
        except Exception:
            pass
        if column:
            return False
        for selector in build_popup_reference_table_row_selectors(wanted):
            try:
                locator = dialog.locator(selector)
                count = min(locator.count(), 20)
            except Exception:
                continue
            for index in range(count):
                candidate = locator.nth(index)
                try:
                    if not candidate.is_visible(timeout=300):
                        continue
                    candidate.click(timeout=2000)
                    requires_selection = self._popup_reference_candidate_requires_selection_state(candidate)
                    if requires_selection:
                        self._stabilize_popup_reference_selection(candidate, require_control=True)
                    else:
                        self._stabilize_popup_reference_selection(candidate)
                    if requires_selection and not self._popup_reference_candidate_has_selection_state(
                        candidate,
                        require_control=True,
                    ):
                        continue
                    return True
                except Exception:
                    continue
        return False

    def _ensure_popup_reference_selected_control_checked(self, dialog) -> None:
        try:
            script = """(root) => {
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
                    const rowSelector = [
                      'tr',
                      '[role="row"]',
                      '.w-table-row',
                      '.wui-table-row',
                      '.ant-table-row',
                      '.u-table-row',
                      '[class*="table-row"]',
                      '[class*="TableRow"]',
                      '.wui-tree-treenode',
                      '.wui-select-tree-treenode',
                      '.ant-tree-treenode',
                      '.u-tree-treenode',
                      '[role="treeitem"]',
                      '[role="option"]',
                      '.wui-list-item',
                      '.ant-list-item',
                      '.u-list-item',
                      'li'
                    ].join(',');
                    const selectedRow = Array.from(root.querySelectorAll([
                      'tr',
                      '[role="row"]',
                      '.w-table-row',
                      '.wui-table-row',
                      '.ant-table-row',
                      '.u-table-row',
                      '[class*="table-row"]',
                      '[class*="TableRow"]',
                      '.wui-tree-treenode',
                      '.wui-select-tree-treenode',
                      '.ant-tree-treenode',
                      '.u-tree-treenode',
                      '[role="treeitem"]',
                      '[role="option"]',
                      '.wui-list-item',
                      '.ant-list-item',
                      '.u-list-item',
                      'li'
                    ].join(','))).find((row) => {
                      const className = String(row.className || '').toLowerCase();
                      const rowSelectionSelected = /(?:^|[\\s_-])(selected|checked)(?:$|[\\s_-])/.test(className)
                        || row.getAttribute('aria-selected') === 'true'
                        || row.getAttribute('aria-checked') === 'true';
                      return rowSelectionSelected
                        || row.querySelector('[aria-selected="true"], [aria-checked="true"], [class*="selected"], [class*="checked"]');
                    });
                    if (!selectedRow) return false;
                    const selectionRoot = selectedRow.closest(rowSelector) || selectedRow;
                    const controlSelector = [
                      'input[type="radio"]',
                      'input[type="checkbox"]',
                      '[role="radio"]',
                      '[role="checkbox"]',
                      '.wui-tree-checkbox',
                      '.wui-select-tree-checkbox',
                      '.ant-tree-checkbox',
                      '.u-tree-checkbox',
                      '.wui-tree-radio',
                      '.wui-select-tree-radio',
                      '.ant-tree-radio',
                      '.u-tree-radio',
                      '.w-radio',
                      '.w-checkbox',
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
                    const wrapperSelector = [
                      'label',
                      '.wui-tree-checkbox',
                      '.wui-select-tree-checkbox',
                      '.ant-tree-checkbox',
                      '.u-tree-checkbox',
                      '.wui-tree-radio',
                      '.wui-select-tree-radio',
                      '.ant-tree-radio',
                      '.u-tree-radio',
                      '.w-radio-wrapper',
                      '.w-checkbox-wrapper',
                      '.wui-radio-wrapper',
                      '.wui-checkbox-wrapper',
                      '.ant-radio-wrapper',
                      '.ant-checkbox-wrapper',
                      '.u-radio-wrapper',
                      '.u-checkbox-wrapper',
                      '[class*="radio-wrapper"]',
                      '[class*="RadioWrapper"]',
                      '[class*="checkbox-wrapper"]',
                      '[class*="CheckboxWrapper"]'
                    ].join(',');
                    const controls = Array.from(selectionRoot.querySelectorAll(controlSelector))
                      .filter((item, index, all) => all.indexOf(item) === index)
                      .filter((item) => !disabled(item));
                    if (!controls.length) return false;
                    const controlChecked = (item) => {
                      const input = item.matches('input[type="radio"], input[type="checkbox"]')
                        ? item
                        : item.querySelector('input[type="radio"], input[type="checkbox"]');
                      const className = String(item.className || '').toLowerCase();
                      return input?.checked === true
                        || item.getAttribute('aria-checked') === 'true'
                        || /checked/.test(className);
                    };
                    if (controls.some(controlChecked)) return true;
                    const rankFor = (target) => {
                      const tag = String(target.tagName || '').toLowerCase();
                      const role = String(target.getAttribute('role') || '').toLowerCase();
                      const type = String(target.getAttribute('type') || '').toLowerCase();
                      const className = String(target.className || '').toLowerCase();
                      if (tag === 'label') return 0;
                      if (/tree-(checkbox|radio)|select-tree-(checkbox|radio)/.test(className)) return 1;
                      if (role === 'radio' || role === 'checkbox') return 2;
                      if (/radio|checkbox/.test(className) && !/group/.test(className)) return 3;
                      if (tag === 'input' && (type === 'radio' || type === 'checkbox')) return 8;
                      return 10;
                    };
                    const candidates = controls
                      .map((item) => {
                        const wrapper = item.closest(wrapperSelector);
                        const target = wrapper && selectionRoot.contains(wrapper) && visible(wrapper) ? wrapper : item;
                        return { target, rank: rankFor(target) };
                      })
                      .filter((item, index, all) => all.findIndex((other) => other.target === item.target) === index)
                      .filter((item) => visible(item.target))
                      .sort((a, b) => {
                        const ar = a.target.getBoundingClientRect();
                        const br = b.target.getBoundingClientRect();
                        return a.rank - b.rank || ar.left - br.left || (ar.width * ar.height) - (br.width * br.height);
                      });
                    const target = candidates[0]?.target;
                    if (!target) return false;
                    target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                    target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                    target.click();
                    const input = target.matches('input[type="radio"], input[type="checkbox"]')
                      ? target
                      : target.querySelector('input[type="radio"], input[type="checkbox"]')
                        || selectionRoot.querySelector('input[type="radio"], input[type="checkbox"]');
                    return controls.some(controlChecked) || input?.checked === true;
                }"""
            try:
                dialog.evaluate(script, timeout=1500)
            except TypeError:
                dialog.evaluate(script)
            self._wait_for_timeout(120)
        except PopupReferenceError:
            raise
        except Exception:
            return

    def _popup_reference_target_receives_pointer(self, target) -> bool:
        try:
            return bool(
                target.evaluate(
                    """(node) => {
                        const rect = node.getBoundingClientRect();
                        if (!rect || rect.width <= 0 || rect.height <= 0) return false;
                        const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 0;
                        const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
                        const x = rect.left + rect.width / 2;
                        const y = rect.top + rect.height / 2;
                        if (x < 0 || y < 0 || x >= viewportWidth || y >= viewportHeight) return false;
                        const hit = document.elementFromPoint(x, y);
                        return Boolean(hit && (hit === node || node.contains(hit) || hit.contains(node)));
                    }"""
                )
            )
        except Exception:
            return True

    def _popup_reference_candidate_requires_selection_state(self, candidate) -> bool:
        try:
            return bool(
                candidate.evaluate(
                    """(node) => {
                        const row = node.closest('tr, [role="row"], .w-table-row, .wui-table-row, .ant-table-row, .u-table-row, [class*="table-row"], [class*="TableRow"], .wui-tree-treenode, .wui-select-tree-treenode, .ant-tree-treenode, .u-tree-treenode, [role="treeitem"], li, [role="option"], .wui-list-item, .ant-list-item, .u-list-item') || node;
                        const controlSelector = [
                          'input[type="radio"]',
                          'input[type="checkbox"]',
                          '[role="radio"]',
                          '[role="checkbox"]',
                          '.w-radio',
                          '.w-checkbox',
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
                        const visible = (el) => {
                          const style = window.getComputedStyle(el);
                          const rect = el.getBoundingClientRect();
                          return style && style.visibility !== 'hidden' && style.display !== 'none'
                            && rect.width > 0 && rect.height > 0;
                        };
                        return Array.from(row.querySelectorAll(controlSelector)).some(visible);
                    }""",
                    timeout=500,
                )
            )
        except Exception:
            return False

    def _stabilize_popup_reference_selection(self, candidate, *, require_control: bool = False) -> None:
        def selected() -> bool:
            if require_control:
                return self._popup_reference_candidate_has_selection_state(candidate, require_control=True)
            return self._popup_reference_candidate_has_selection_state(candidate)

        try:
            self._wait_for_timeout(120)
        except PopupReferenceError:
            raise
        except Exception:
            pass
        if selected():
            return
        try:
            candidate.click(timeout=800, force=True)
            self._wait_for_timeout(120)
        except PopupReferenceError:
            raise
        except Exception:
            pass
        if selected():
            return
        try:
            candidate.evaluate(
                """(node) => {
                    const row = node.closest('tr, [role="row"], .w-table-row, .wui-table-row, .ant-table-row, .u-table-row, [class*="table-row"], [class*="TableRow"], .wui-tree-treenode, .wui-select-tree-treenode, .ant-tree-treenode, .u-tree-treenode, [role="treeitem"], [role="option"], .wui-list-item, .ant-list-item, .u-list-item, li');
                    if (!row || row === node) return;
                    row.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                    row.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                    row.click();
                }""",
                timeout=500,
            )
            self._wait_for_timeout(120)
        except PopupReferenceError:
            raise
        except Exception:
            pass
        if selected():
            return
        try:
            candidate.evaluate(
                """(node) => {
                    const row = node.closest('tr, [role="row"], .w-table-row, .wui-table-row, .ant-table-row, .u-table-row, [class*="table-row"], [class*="TableRow"], .wui-tree-treenode, .wui-select-tree-treenode, .ant-tree-treenode, .u-tree-treenode, [role="treeitem"], [role="option"], .wui-list-item, .ant-list-item, .u-list-item, li') || node;
                    const controlSelector = [
                      'input[type="radio"]',
                      'input[type="checkbox"]',
                      '[role="radio"]',
                      '[role="checkbox"]',
                      '.w-radio',
                      '.w-checkbox',
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
                    const visible = (el) => {
                      const style = window.getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style && style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width > 0 && rect.height > 0;
                    };
                    const control = Array.from(row.querySelectorAll(controlSelector)).find(visible);
                    if (!control) return false;
                    control.click();
                    const input = control.matches('input[type="radio"], input[type="checkbox"]')
                      ? control
                      : control.querySelector('input[type="radio"], input[type="checkbox"]')
                        || row.querySelector('input[type="radio"], input[type="checkbox"]');
                    for (const eventName of ['input', 'change', 'click']) {
                      (input || control).dispatchEvent(new Event(eventName, { bubbles: true }));
                    }
                    return true;
                }""",
                timeout=500,
            )
            self._wait_for_timeout(160)
        except PopupReferenceError:
            raise
        except Exception:
            pass
        if selected():
            return
        try:
            candidate.dblclick(timeout=1000)
            self._wait_for_timeout(200)
        except PopupReferenceError:
            raise
        except Exception:
            return

    def _popup_reference_candidate_has_selection_state(self, candidate, *, require_control: bool = False) -> bool:
        try:
            require_control_js = "true" if require_control else "false"
            return bool(
                candidate.evaluate(
                    """(node) => {
                        const requireControl = """ + require_control_js + """;
                        const selected = (el) => {
                          if (!el) return false;
                          const className = String(el.className || '').toLowerCase();
                          return el.checked === true
                            || el.getAttribute('aria-selected') === 'true'
                            || el.getAttribute('aria-checked') === 'true'
                            || /selected|active|current|checked/.test(className);
                        };
                        const rowSelectionSelected = (el) => {
                          if (!el) return false;
                          const className = String(el.className || '').toLowerCase();
                          return el.checked === true
                            || el.getAttribute('aria-selected') === 'true'
                            || el.getAttribute('aria-checked') === 'true'
                            || /(?:^|[\\s_-])(selected|checked)(?:$|[\\s_-])/.test(className);
                        };
                        const controlSelected = (el) => {
                          if (!el) return false;
                          const className = String(el.className || '').toLowerCase();
                          const wrapper = el.closest && el.closest('label, .wui-tree-checkbox, .wui-select-tree-checkbox, .ant-tree-checkbox, .u-tree-checkbox, .wui-tree-radio, .wui-select-tree-radio, .ant-tree-radio, .u-tree-radio, .w-radio-wrapper, .w-checkbox-wrapper, .wui-radio-wrapper, .wui-checkbox-wrapper, .ant-radio-wrapper, .ant-checkbox-wrapper, .u-radio-wrapper, .u-checkbox-wrapper, [class*="radio-wrapper"], [class*="RadioWrapper"], [class*="checkbox-wrapper"], [class*="CheckboxWrapper"]');
                          const wrapperClass = String(wrapper?.className || '').toLowerCase();
                          const input = el.matches && el.matches('input[type="radio"], input[type="checkbox"]')
                            ? el
                            : el.querySelector && el.querySelector('input[type="radio"], input[type="checkbox"]');
                          return input?.checked === true
                            || el.getAttribute('aria-checked') === 'true'
                            || wrapper?.getAttribute?.('aria-checked') === 'true'
                            || /checked/.test(className)
                            || /checked/.test(wrapperClass);
                        };
                        const row = node.closest('tr, [role="row"], .w-table-row, .wui-table-row, .ant-table-row, .u-table-row, [class*="table-row"], [class*="TableRow"], .wui-tree-treenode, .wui-select-tree-treenode, .ant-tree-treenode, .u-tree-treenode, [role="treeitem"], li, [role="option"], .wui-list-item, .ant-list-item, .u-list-item') || node;
                        const rowIsSelected = rowSelectionSelected(node) || rowSelectionSelected(row);
                        const selectableControls = Array.from(row.querySelectorAll([
                          'input[type="radio"]',
                          'input[type="checkbox"]',
                          '[role="radio"]',
                          '[role="checkbox"]',
                          '.w-radio',
                          '.w-checkbox',
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
                        ].join(','))).filter((el, index, all) => all.indexOf(el) === index);
                        if (selectableControls.length) {
                          return selectableControls.some(controlSelected) || (!requireControl && rowIsSelected);
                        }
                        if (requireControl) return false;
                        if (rowIsSelected) return true;
                        if (selected(node) || selected(row)) return true;
                        return Boolean(row.querySelector('input:checked, [aria-selected="true"], [aria-checked="true"], [class*="selected"], [class*="active"], [class*="current"], [class*="checked"]'));
                    }""",
                    timeout=500,
                )
            )
        except Exception:
            return False

    def _click_popup_reference_list_option(self, dialog, value: str) -> bool:
        try:
            marker = f"option-{int(time.time() * 1000)}"
            click_target_selector = dialog.evaluate(
                """(root, args) => {
                    const value = args.value;
                    const marker = args.marker;
                    const normalize = (text) => String(text || '').replace(/\\s+/g, ' ').trim();
                    const visible = (el) => {
                      const style = window.getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style && style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width > 0 && rect.height > 0;
                    };
                    const textOf = (el) => normalize(el.getAttribute('title') || el.innerText || el.textContent || '');
                    const optionSelector = [
                      '[role="option"]',
                      '.wui-select-item-option',
                      '.ant-select-item-option',
                      '.u-select-item-option',
                      '.wui-list-item',
                      '.ant-list-item',
                      '.u-list-item',
                      '[class*="list"] [class*="item"]',
                      '[class*="List"] [class*="Item"]',
                      '[class*="menu"] [class*="item"]',
                      'li',
                      '[title]'
                    ].join(',');
                    const excluded = 'button, input, textarea, select, [role="button"], .ant-modal-footer *, .wui-modal-footer *, .u-modal-footer *, thead *, tr, [role="row"]';
                    const candidates = Array.from(root.querySelectorAll(optionSelector))
                      .filter((el, index, all) => all.indexOf(el) === index)
                      .filter((el) => visible(el) && !el.matches(excluded) && !el.closest(excluded))
                      .map((el) => {
                        const text = textOf(el);
                        const target = el.closest('[role="option"], .wui-select-item-option, .ant-select-item-option, .u-select-item-option, .wui-list-item, .ant-list-item, .u-list-item, [class*="list"] [class*="item"], [class*="List"] [class*="Item"], [class*="menu"] [class*="item"], li') || el;
                        const rect = target.getBoundingClientRect();
                        const exact = text === value ? 0 : 1;
                        return { target, text, exact, score: exact * 100000000 + rect.width * rect.height };
                      })
                      .filter((item) => item.text === value || item.text.includes(value))
                      .sort((a, b) => a.score - b.score);
                    const target = candidates[0] && candidates[0].target;
                    if (!target) return '';
                    target.setAttribute('data-ydf-browser-popup-reference-option', marker);
                    return `[data-ydf-browser-popup-reference-option="${marker}"]`;
                }""",
                {"value": value, "marker": marker},
            )
            if click_target_selector:
                target = dialog.locator(str(click_target_selector)).first
                try:
                    target.scroll_into_view_if_needed(timeout=1000)
                except Exception:
                    pass
                try:
                    target.click(timeout=2000)
                except Exception:
                    target.click(force=True, timeout=2000)
                self._stabilize_popup_reference_selection(target)
                return True
        except Exception:
            pass
        for selector in build_popup_reference_option_selectors(value):
            try:
                locator = dialog.locator(selector)
                count = min(locator.count(), 20)
            except Exception:
                continue
            for index in range(count):
                candidate = locator.nth(index)
                try:
                    if not candidate.is_visible(timeout=300):
                        continue
                    candidate.click(timeout=2000)
                    self._stabilize_popup_reference_selection(candidate)
                    return True
                except Exception:
                    continue
        return False

    def _popup_reference_tree_node_visible(self, dialog, value: str) -> bool:
        try:
            script = """(root, value) => {
                        const normalize = (text) => String(text || '').replace(/\\s+/g, ' ').trim();
                        const visible = (el) => {
                          const style = window.getComputedStyle(el);
                          const rect = el.getBoundingClientRect();
                          return style && style.visibility !== 'hidden' && style.display !== 'none'
                            && rect.width > 0 && rect.height > 0;
                        };
                        const treeRoots = Array.from(root.querySelectorAll([
                          '.wui-tree',
                          '.wui-select-tree',
                          '.ant-tree',
                          '.u-tree',
                          '[role="tree"]',
                          '[role="tree-node"]'
                        ].join(','))).filter(visible);
                        const searchRoots = treeRoots.length ? treeRoots : [root];
                        const candidates = searchRoots.flatMap((tree) => Array.from(tree.querySelectorAll([
                          '[role="treeitem"]',
                          '[title]',
                          '.wui-tree-title',
                          '.wui-tree-node-content-wrapper',
                          '.wui-tree-treenode',
                          '.wui-select-tree-title',
                          '.wui-select-tree-node-content-wrapper',
                          '.ant-tree-title',
                          '.ant-tree-node-content-wrapper',
                          '.ant-tree-treenode',
                          '.u-tree-node-content-wrapper',
                          '[class*="tree"] [class*="title"]',
                          '[class*="tree"] [class*="node"]'
                        ].join(',')))).filter((el, index, all) => all.indexOf(el) === index)
                          .filter((el) => visible(el) && el.tagName !== 'INPUT' && el.tagName !== 'TEXTAREA')
                          .slice(0, 1500);
                        candidates.sort((a, b) => {
                          const ar = a.getBoundingClientRect();
                          const br = b.getBoundingClientRect();
                          return (ar.width * ar.height) - (br.width * br.height);
                        });
                        for (const candidate of candidates) {
                          const text = normalize(candidate.getAttribute('title') || candidate.innerText || candidate.textContent);
                          if (text === value) {
                            return true;
                          }
                        }
                        return false;
                    }"""
            try:
                return bool(dialog.evaluate(script, value, timeout=1500))
            except TypeError:
                return bool(dialog.evaluate(script, value))
        except Exception:
            return False

    def _expand_popup_reference_tree_until_visible(self, dialog, value: str, max_rounds: int = 12) -> None:
        page = self._require_page()
        attempted: set[str] = set()
        for _ in range(max_rounds):
            if self._popup_reference_tree_node_visible(dialog, value):
                return
            expanded = False
            for selector in build_popup_reference_tree_closed_switcher_selectors():
                locator = dialog.locator(selector)
                try:
                    count = min(locator.count(), 50)
                except Exception:
                    continue
                for index in range(count):
                    self._check_cancelled()
                    candidate = locator.nth(index)
                    try:
                        if not candidate.is_visible(timeout=300):
                            continue
                        identity = candidate.evaluate("""el => {
                            const node = el.closest('[role="treeitem"], li, .wui-tree-treenode, .wui-select-tree-treenode, .ant-tree-treenode, .u-tree-treenode');
                            if (/noop|is-leaf|disabled|center_open|switcher[_-]open/i.test(String(el.className || ''))
                                || el.getAttribute('aria-disabled') === 'true' || el.disabled
                                || node?.getAttribute('aria-disabled') === 'true'
                                || node?.getAttribute('aria-expanded') === 'true'
                                || /treenode-open|node-open|node-leaf|is-leaf|disabled/i.test(String(node?.className || ''))) return '';
                            const key = 'data-ydf-browser-popup-tree-expander';
                            if (!el.hasAttribute(key)) el.setAttribute(key, `${Date.now()}-${Math.random()}`);
                            return el.getAttribute(key);
                        }""", timeout=500)
                        if not identity or identity in attempted:
                            continue
                        attempted.add(identity)
                        candidate.click(timeout=1500)
                        self._wait_for_timeout(300)
                        expanded = True
                        break
                    except PopupReferenceError:
                        raise
                    except Exception:
                        continue
                if expanded:
                    break
            if not expanded:
                return

    def _collapse_hovered_navigation_overlay(self) -> None:
        try:
            page = self._require_page()
            viewport = page.viewport_size or dict(GEOMETRY_FALLBACK_VIEWPORT)
            width = int(viewport.get("width") or GEOMETRY_FALLBACK_VIEWPORT["width"])
            height = int(viewport.get("height") or GEOMETRY_FALLBACK_VIEWPORT["height"])
            page.mouse.move(max(1, width - 12), max(80, min(height - 12, height // 2)))
            self._wait_for_timeout(180)
        except PopupReferenceError:
            raise
        except Exception:
            return
