from __future__ import annotations

import time
import uuid
from typing import Any

from .model import PopupReferenceError
from .selection import (
    _popup_reference_target_table,
    build_popup_reference_dialog_selectors,
)

_MARK_VISIBLE_POPUP_REFERENCE_DIALOGS_SCRIPT = r"""
({ marker, selectors }) => {
  const visible = (node) => {
    if (!node) return false;
    const style = window.getComputedStyle(node);
    const rect = node.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden'
      && rect.width > 0 && rect.height > 0;
  };
  const choiceSelector = [
    'table', '[role="grid"]', '[role="row"]', '[role="tree"]', '[role="treeitem"]',
    '[role="option"]', '[role="listbox"]', '.wui-tree', '.ant-tree', '.u-tree',
    '.wui-table', '.ant-table', '.u-table', '.wui-select-dropdown',
    '.ant-select-dropdown', '.u-select-dropdown', '[class*="table-row"]', '[class*="TableRow"]'
  ].join(',');
  const normalize = (value) => String(value || '').replace(/\s+/g, ' ').trim();
  const hasChoiceSurface = (node) => Array.from(node.querySelectorAll(choiceSelector)).some(visible);
  const hasConfirm = (node) => /确定|确认|保存/.test(normalize(node.innerText || node.textContent));
  const candidates = new Set();
  for (const selector of selectors || []) {
    const css = String(selector || '').replace(/:visible$/, '');
    try {
      document.querySelectorAll(css).forEach((node) => candidates.add(node));
    } catch (_) {
      continue;
    }
  }
  for (const node of candidates) {
    const rect = node.getBoundingClientRect();
    if (visible(node) && rect.width >= 260 && rect.height >= 160 && hasConfirm(node) && hasChoiceSurface(node)) {
      node.setAttribute('data-ydf-browser-popup-reference-existing', marker);
    }
  }
}
"""

_CLEAR_POPUP_REFERENCE_DIALOG_MARKER_SCRIPT = """
(marker) => {
  document.querySelectorAll('[data-ydf-browser-popup-reference-existing]').forEach((node) => {
    if (node.getAttribute('data-ydf-browser-popup-reference-existing') === marker) {
      node.removeAttribute('data-ydf-browser-popup-reference-existing');
    }
  });
}
"""


class SurfaceStage:
    def _visible_popup_reference_dialog_count(self) -> int:
        counts = self._visible_popup_reference_dialog_counts()
        return max(counts.values(), default=0)

    def _mark_visible_popup_reference_dialogs(self) -> str:
        marker = f"popup-reference-existing-{uuid.uuid4().hex}"
        selectors = build_popup_reference_dialog_selectors()
        for context in self._all_search_contexts():
            try:
                context.evaluate(
                    _MARK_VISIBLE_POPUP_REFERENCE_DIALOGS_SCRIPT,
                    {"marker": marker, "selectors": selectors},
                )
            except Exception:
                continue
        return marker

    def _clear_popup_reference_dialog_marker(self, marker: str) -> None:
        for context in self._all_search_contexts():
            try:
                context.evaluate(_CLEAR_POPUP_REFERENCE_DIALOG_MARKER_SCRIPT, marker)
            except Exception:
                continue

    def _visible_popup_reference_dialog_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for selector in build_popup_reference_dialog_selectors():
            current = 0
            for context in self._all_search_contexts():
                try:
                    locator = context.locator(selector)
                    count = locator.count()
                except Exception:
                    continue
                for index in range(count):
                    try:
                        candidate = locator.nth(index)
                        if candidate.is_visible(timeout=100) and self._looks_like_popup_reference_dialog_root(candidate):
                            current += 1
                    except Exception:
                        continue
            counts[selector] = current
        return counts

    def _resolve_current_popup_reference_shell(self, title: str | None = None):
        title_text = str(title or "").strip()
        for context in self._all_search_contexts():
            for selector in build_popup_reference_dialog_selectors():
                try:
                    locator = context.locator(selector)
                    count = locator.count()
                except Exception:
                    continue
                candidates = []
                for index in range(count):
                    candidate = locator.nth(index)
                    try:
                        if not candidate.is_visible(timeout=200):
                            continue
                        info = candidate.evaluate(
                            """(node, title) => {
                                const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                                const rect = node.getBoundingClientRect();
                                const text = normalize(node.innerText || node.textContent);
                                const hasConfirm = text.includes('确定') || text.includes('确认') || text.includes('保存');
                                const hasCancel = text.includes('取消');
                                const titleMatches = !title || text.includes(title);
                                return {
                                  text,
                                  area: rect.width * rect.height,
                                  hasConfirm,
                                  hasCancel,
                                  titleMatches,
                                };
                            }""",
                            title_text,
                        )
                    except Exception:
                        continue
                    if not info or not info.get("hasConfirm") or not info.get("hasCancel") or not info.get("titleMatches"):
                        continue
                    candidates.append((float(info.get("area") or 0), context, candidate))
                if candidates:
                    _area, matched_context, matched_candidate = sorted(candidates, key=lambda item: item[0])[0]
                    return self._mark_popup_reference_dialog_candidate(matched_context, matched_candidate)
        return self._resolve_popup_reference_dialog()

    def _popup_reference_choice_root_script(self, *, scoped: bool) -> str:
        signature = "(root) =>" if scoped else "() =>"
        roots_expression = (
            "root.querySelectorAll('body, main, div, section, form')"
            if scoped
            else "document.querySelectorAll('body, main, div, section, form')"
        )
        return (
            r"""
            __SIGNATURE__ {
                const normalize = (value) => String(value || '').replace(/\s+/g, ' ').trim();
                const visible = (el) => {
                  const style = window.getComputedStyle(el);
                  const rect = el.getBoundingClientRect();
                  return style && style.visibility !== 'hidden' && style.display !== 'none'
                    && rect.width > 0 && rect.height > 0;
                };
                const queryInputSelector = 'input:not([type="hidden"]):not([type="radio"]):not([type="checkbox"]), textarea, [contenteditable="true"], [role="textbox"]';
                const isPaginationInput = (input) => {
                  const owner = input.closest([
                    '.wui-pagination',
                    '.ant-pagination',
                    '.u-pagination',
                    '[class*="pagination"]',
                    '[class*="Pagination"]',
                    '[class*="pager"]',
                    '[class*="Pager"]',
                    'tfoot',
                    '[class*="footer"]',
                    '[class*="Footer"]'
                  ].join(','));
                  const textRoot = owner || input.parentElement || input;
                  const text = normalize(textRoot.innerText || textRoot.textContent);
                  return Boolean(owner) || /跳至|共\s*\d+\s*条|条\s*\/?\s*页|每页/.test(text);
                };
                const hasInput = (el) => Array.from(el.querySelectorAll(queryInputSelector))
                  .some((input) => visible(input) && !isPaginationInput(input));
                const hasTable = (el) => Boolean(el.querySelector('table, [role="grid"], .wui-table, .ant-table, .u-table, [class*="table"], [class*="Table"]'));
                const hasTreeOrList = (el) => Boolean(el.querySelector('[role="tree"], [role="treeitem"], [role="option"], .wui-tree, .ant-tree, .u-tree, [class*="list"], [class*="List"]'));
                const hasChoiceSurface = (el) => hasTable(el) || hasTreeOrList(el);
                const roots = Array.from(__ROOTS__)
                  .filter(visible)
                  .map((el) => {
                    const input = hasInput(el);
                    const choice = hasChoiceSurface(el);
                    const choiceRank = input && choice ? 0 : choice ? 1 : 2;
                    return { el, rect: el.getBoundingClientRect(), text: normalize(el.innerText || el.textContent), input, choice, choiceRank };
                  })
                  .filter((item) => item.rect.width >= 240 && item.rect.height >= 160)
                  .filter((item) => item.choice || item.input)
                  .filter((item) => !/业务助|填报说明/.test(item.text))
                  .sort((a, b) => a.choiceRank - b.choiceRank || (a.rect.width * a.rect.height) - (b.rect.width * b.rect.height));
                const target = roots[0] && roots[0].el;
                if (!target) return '';
                const marker = `ydf-popup-choice-${Date.now()}-${Math.floor(Math.random() * 100000)}`;
                target.setAttribute('data-ydf-browser-popup-reference-choice-root', marker);
                return `[data-ydf-browser-popup-reference-choice-root="${marker}"]`;
            }
            """
            .replace("__SIGNATURE__", signature)
            .replace("__ROOTS__", roots_expression)
        )

    def _resolve_popup_reference_choice_root_from_scope(self, scope):
        try:
            selector = scope.evaluate(self._popup_reference_choice_root_script(scoped=True))
        except Exception:
            return None
        if not selector:
            return None
        try:
            return scope.locator(str(selector)).first
        except Exception:
            return None

    def _resolve_current_popup_reference_choice_root(self, shell_dialog, title: str | None = None):
        scoped_choice_root = self._resolve_popup_reference_choice_root_from_scope(shell_dialog)
        if scoped_choice_root is not None:
            return scoped_choice_root
        script = self._popup_reference_choice_root_script(scoped=False)
        contexts = self._all_search_contexts()
        try:
            has_embedded_frame = bool(
                shell_dialog.evaluate(
                    """(root) => Array.from(root.querySelectorAll('iframe')).some((frame) => {
                        const style = window.getComputedStyle(frame);
                        const rect = frame.getBoundingClientRect();
                        return style && style.visibility !== 'hidden' && style.display !== 'none'
                          && rect.width > 0 && rect.height > 0;
                    })"""
                )
            )
        except Exception:
            has_embedded_frame = False
        if has_embedded_frame:
            page = self._require_page()
            contexts = [context for context in contexts if context is not page and context is not page.main_frame]
        for context in reversed(contexts):
            try:
                selector = context.evaluate(script)
            except Exception:
                continue
            if not selector:
                continue
            try:
                return context.locator(str(selector)).first
            except Exception:
                continue
        return None

    def _wait_for_popup_reference_choice_root_ready(
        self,
        shell_dialog,
        choice_root,
        timeout_ms: int = 8000,
        *,
        require_candidate: bool = False,
    ):
        current = choice_root or shell_dialog
        if self._popup_reference_choice_root_ready(current, require_candidate=require_candidate):
            return current
        page = self._require_page()
        attempts = max(1, int(timeout_ms / 300))
        for _ in range(attempts):
            try:
                self._wait_for_timeout(300)
            except PopupReferenceError:
                raise
            except Exception:
                pass
            refreshed = self._resolve_current_popup_reference_choice_root(shell_dialog) or current
            current = refreshed
            if self._popup_reference_choice_root_ready(current, require_candidate=require_candidate):
                return current
        return current

    def _popup_reference_choice_root_ready(self, choice_root, *, require_candidate: bool = False) -> bool:
        try:
            info = choice_root.evaluate(
                r"""(root) => {
                    const normalize = (value) => String(value || '').replace(/\s+/g, ' ').trim();
                    const visible = (el) => {
                      if (!el || !(el instanceof HTMLElement)) return false;
                      const style = window.getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style.display !== 'none' && style.visibility !== 'hidden'
                        && rect.width > 0 && rect.height > 0;
                    };
                    const queryInputSelector = 'input:not([type="hidden"]):not([type="radio"]):not([type="checkbox"]), textarea, [contenteditable="true"], [role="textbox"]';
                    const isPaginationInput = (input) => {
                      const owner = input.closest([
                        '.wui-pagination',
                        '.ant-pagination',
                        '.u-pagination',
                        '[class*="pagination"]',
                        '[class*="Pagination"]',
                        '[class*="pager"]',
                        '[class*="Pager"]',
                        'tfoot',
                        '[class*="footer"]',
                        '[class*="Footer"]'
                      ].join(','));
                      const textRoot = owner || input.parentElement || input;
                      const text = normalize(textRoot.innerText || textRoot.textContent);
                      return Boolean(owner) || /跳至|共\s*\d+\s*条|条\s*\/?\s*页|每页/.test(text);
                    };
                    const inputs = Array.from(root.querySelectorAll(queryInputSelector))
                      .filter((input) => visible(input) && !isPaginationInput(input));
                    const rowSelector = [
                      'tbody tr',
                      '.wui-table-tbody .wui-table-row',
                      '.wui-table-body .wui-table-row',
                      '.ant-table-tbody .ant-table-row',
                      '.u-table-tbody .u-table-row',
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
                    const cellSelector = [
                      'td',
                      '[role="gridcell"]',
                      '[role="cell"]',
                      '.wui-table-cell',
                      '.ant-table-cell',
                      '.u-table-cell'
                    ].join(',');
                    const rows = Array.from(root.querySelectorAll(rowSelector))
                      .filter((row, index, all) => all.indexOf(row) === index)
                      .filter((row) => visible(row) && !row.closest('thead'))
                      .filter((row) => Array.from(row.querySelectorAll(cellSelector)).some(visible));
                    const choices = Array.from(root.querySelectorAll([
                      '[role="tree"]',
                      '[role="treeitem"]',
                      '[role="option"]',
                      '.wui-tree',
                      '.wui-select-tree',
                      '.ant-tree',
                      '.u-tree',
                      '[class*="list"] [class*="item"]',
                      '[class*="List"] [class*="Item"]',
                      'li'
                    ].join(',')))
                      .filter(visible)
                      .filter((choice) => !choice.closest([
                        '.wui-pagination',
                        '.ant-pagination',
                        '.u-pagination',
                        '[class*="pagination"]',
                        '[class*="Pagination"]',
                        '[class*="pager"]',
                        '[class*="Pager"]',
                        'tfoot',
                        '[class*="footer"]',
                        '[class*="Footer"]'
                      ].join(',')));
                    const text = normalize(root.innerText || root.textContent);
                    const loading = /加载中|暂时没有数据|暂无数据|loading/i.test(text);
                    return {
                      ready: inputs.length > 0 || rows.length > 0 || choices.length > 0,
                      candidate_ready: rows.length > 0 || choices.length > 0,
                      loading,
                    };
                }"""
            )
        except AttributeError:
            return True
        except Exception:
            return False
        if isinstance(info, dict) and "ready" in info:
            return bool(info.get("candidate_ready") if require_candidate else info.get("ready"))
        return True

    def _resolve_popup_reference_selection_root(self, shell_dialog, choice_root, target: dict[str, Any]):
        table = _popup_reference_target_table(target)
        if not table:
            return choice_root
        for scope in (shell_dialog, choice_root):
            table_root = self._resolve_popup_reference_table_root(scope, table)
            if table_root is not None:
                return table_root
        diagnostic = self._collect_popup_reference_diagnostic_text(shell_dialog)
        raise RuntimeError(
            "未找到弹出参照表格: "
            f"target.table={table}; "
            "请确认 DSL target.selections[].table 写的是参照弹窗里的可见表格标题；"
            f"弹窗内容={diagnostic}"
        )

    def _resolve_popup_reference_table_root(self, scope, table: str):
        table_text = str(table or "").strip()
        if not table_text:
            return None
        marker = f"ydf-popup-table-{int(time.time() * 1000)}"
        try:
            selector = scope.evaluate(
                r"""(root, args) => {
                    const table = String(args.table || '').trim();
                    const marker = args.marker;
                    const normalize = (value) => String(value || '').replace(/\s+/g, ' ').trim();
                    const compact = (value) => normalize(value).replace(/\s+/g, '');
                    const wanted = compact(table);
                    const visible = (el) => {
                      if (!el || !(el instanceof HTMLElement)) return false;
                      const style = window.getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style.display !== 'none' && style.visibility !== 'hidden'
                        && rect.width > 0 && rect.height > 0;
                    };
                    const tableSelector = [
                      '.wui-table',
                      '.ant-table',
                      '.u-table',
                      '[role="grid"]',
                      '[role="table"]',
                      'table',
                      '[class*="Table"]',
                      '[class*="table"]'
                    ].join(',');
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
                    const rowLike = (el) => {
                      if (!el || !el.matches) return false;
                      const className = String(el.className || '').toLowerCase();
                      return el.matches(rowSelector)
                        || /(?:^|[\\s_-])table-row(?:$|[\\s_-])/.test(className)
                        || /(?:^|[\\s_-])table-cell(?:$|[\\s_-])/.test(className)
                        || /(?:^|[\\s_-])(wui|ant|u)-table-(row|cell)(?:$|[\\s_-])/.test(className);
                    };
                    const labelSelector = 'span, div, label, h1, h2, h3, h4, [role="tab"], [class*="tab"], [class*="Tab"]';
                    const containsWanted = (value) => {
                      const text = normalize(value);
                      return Boolean(text && (text.includes(table) || (wanted && compact(text).includes(wanted))));
                    };
                    const rowCount = (el) => Array.from(el.querySelectorAll(rowSelector)).filter(visible).length;
                    const tableRoots = Array.from(root.querySelectorAll(tableSelector))
                      .filter((el, index, all) => all.indexOf(el) === index)
                      .filter((el) => !rowLike(el))
                      .filter(visible)
                      .filter((el) => rowCount(el) > 0 || el.querySelector('thead, [role="columnheader"], th'));
                    const scoreTable = (el) => {
                      const rect = el.getBoundingClientRect();
                      let score = -1000;
                      let distance = 0;
                      for (let node = el; node && node !== root.parentElement; node = node.parentElement) {
                        if (containsWanted(node.getAttribute && (node.getAttribute('fieldid') || node.getAttribute('uikey') || ''))) {
                          score = Math.max(score, 1200 - distance);
                        }
                        const nodeText = normalize(node.innerText || node.textContent);
                        const nestedTables = node.querySelectorAll ? node.querySelectorAll(tableSelector).length : 0;
                        if (containsWanted(nodeText)) {
                          score = Math.max(score, (nestedTables > 1 ? 260 : 1000) - distance);
                        }
                        distance += 1;
                        if (node === root) break;
                      }
                      const labels = Array.from(root.querySelectorAll(labelSelector))
                        .filter(visible)
                        .map((label) => ({ label, rect: label.getBoundingClientRect(), text: normalize(label.innerText || label.textContent) }))
                        .filter((item) => item.text && containsWanted(item.text));
                      for (const item of labels) {
                        if (item.rect.bottom <= rect.top + 8) {
                          const verticalDistance = Math.max(0, rect.top - item.rect.bottom);
                          score = Math.max(score, 650 - Math.min(650, verticalDistance));
                        } else if (item.rect.top >= rect.top - 8 && item.rect.bottom <= rect.bottom + 8) {
                          score = Math.max(score, 400);
                        }
                      }
                      return score;
                    };
                    const scored = tableRoots
                      .map((el) => ({ el, score: scoreTable(el), rect: el.getBoundingClientRect(), rows: rowCount(el) }))
                      .filter((item) => item.score >= 0)
                      .sort((a, b) => b.score - a.score || a.rect.top - b.rect.top || b.rows - a.rows);
                    const chosen = scored[0] && scored[0].el;
                    if (!chosen) return '';
                    chosen.setAttribute('data-ydf-browser-popup-reference-table-root', marker);
                    return `[data-ydf-browser-popup-reference-table-root="${marker}"]`;
                }""",
                {"table": table_text, "marker": marker},
            )
        except Exception:
            return None
        if not selector:
            return None
        try:
            return scope.locator(str(selector)).first
        except Exception:
            return None

    def _resolve_popup_reference_dialog(
        self,
        exclude_count: int = 0,
        exclude_counts: dict[str, int] | None = None,
        exclude_marker: str | None = None,
    ):
        page = self._require_page()
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            for selector in build_popup_reference_dialog_selectors():
                visible_candidates = []
                for context in self._all_search_contexts():
                    try:
                        locator = context.locator(selector)
                        count = locator.count()
                    except Exception:
                        continue
                    for index in range(count):
                        candidate = locator.nth(index)
                        try:
                            if (
                                candidate.is_visible(timeout=300)
                                and self._looks_like_popup_reference_dialog_root(candidate)
                                and not self._popup_reference_dialog_has_marker(candidate, exclude_marker)
                            ):
                                visible_candidates.append((context, candidate))
                        except Exception:
                            continue
                selector_exclude_count = exclude_counts.get(selector, exclude_count) if exclude_counts else exclude_count
                if len(visible_candidates) > selector_exclude_count:
                    context, candidate = visible_candidates[-1]
                    return self._mark_popup_reference_dialog_candidate(context, candidate)
            # An ordinary form field needs a dialog created by this click.  If
            # selector-based identity cannot prove that, failing is safer than
            # selecting an unrelated pre-existing choice surface by structure.
            fallback = None if exclude_marker else self._resolve_popup_reference_dialog_by_structure()
            if fallback is not None:
                return fallback
            self._wait_for_timeout(250)
        diagnostic = self._collect_choice_diagnostic_text()
        screenshot = self._save_diagnostic_screenshot("popup-reference-dialog-missing")
        if screenshot:
            diagnostic = f"{diagnostic} | screenshot={screenshot}"
        if self._popup_reference_diag_enabled():
            self._save_diagnostic_json(
                "popup-reference-open-debug",
                self._popup_reference_open_debug_payload(
                    reason="dialog-missing",
                    diagnostic=diagnostic,
                    screenshot=screenshot,
                ),
            )
        raise RuntimeError(f"未打开弹出参照选择框: {diagnostic}")

    def _popup_reference_dialog_has_marker(self, dialog, marker: str | None) -> bool:
        if not marker:
            return False
        try:
            return str(dialog.get_attribute("data-ydf-browser-popup-reference-existing") or "") == marker
        except Exception:
            return False

    def _wait_for_popup_reference_dialog_outside_origin(
        self,
        origin_root,
        *,
        exclude_counts: dict[str, int] | None = None,
        timeout_ms: int = 4000,
    ):
        page = self._require_page()
        deadline = time.monotonic() + max(0.5, timeout_ms / 1000)
        last_dialog = None
        while time.monotonic() < deadline:
            try:
                candidate = self._resolve_popup_reference_dialog(exclude_counts=exclude_counts)
            except RuntimeError:
                candidate = None
            if candidate is not None:
                last_dialog = candidate
                if not self._popup_reference_dialog_contains_origin(candidate, origin_root):
                    return candidate
            self._wait_for_timeout(250)
        diagnostic = (
            self._collect_popup_reference_diagnostic_text(last_dialog)
            if last_dialog is not None
            else self._collect_choice_diagnostic_text()
        )
        screenshot = self._save_diagnostic_screenshot("popup-reference-current-dialog-missing")
        if screenshot:
            diagnostic = f"{diagnostic} | screenshot={screenshot}"
        raise RuntimeError(f"未打开当前字段弹出参照候选层: {diagnostic}")

    def _popup_reference_dialog_contains_origin(self, dialog, origin_root) -> bool:
        if origin_root is None:
            return False
        if dialog is origin_root:
            return True
        marker = f"ydf-popup-reference-origin-{int(time.time() * 1000)}"
        attr = "data-ydf-browser-popup-reference-origin"
        try:
            origin_root.evaluate(
                """(node, payload) => {
                    if (node && node.setAttribute) {
                        node.setAttribute(payload.attr, payload.marker);
                    }
                }""",
                {"attr": attr, "marker": marker},
            )
            return bool(
                dialog.evaluate(
                    """(node, payload) => {
                        if (!node || !node.querySelector) return false;
                        if (node.getAttribute && node.getAttribute(payload.attr) === payload.marker) return true;
                        return Boolean(node.querySelector(`[${payload.attr}="${payload.marker}"]`));
                    }""",
                    {"attr": attr, "marker": marker},
                )
            )
        except Exception:
            return False
        finally:
            try:
                origin_root.evaluate(
                    """(node, attr) => {
                        if (node && node.removeAttribute) {
                            node.removeAttribute(attr);
                        }
                    }""",
                    attr,
                )
            except Exception:
                pass

    def _mark_popup_reference_dialog_candidate(self, context, candidate):
        marker = f"dialog-{int(time.time() * 1000)}"
        try:
            selector = candidate.evaluate(
                """(node, marker) => {
                    node.setAttribute('data-ydf-browser-popup-reference-dialog', marker);
                    return `[data-ydf-browser-popup-reference-dialog="${marker}"]`;
                }""",
                marker,
            )
            return context.locator(str(selector)).first
        except Exception:
            return candidate

    def _looks_like_popup_reference_dialog_root(self, candidate) -> bool:
        try:
            summary = self._popup_reference_choice_surface_summary(candidate)
            if summary and not bool(summary.get("has_choice_surface")):
                return False
            return bool(
                candidate.evaluate(
                    """(node) => {
                        const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                        const visible = (el) => {
                          const style = window.getComputedStyle(el);
                          const rect = el.getBoundingClientRect();
                          return style && style.visibility !== 'hidden' && style.display !== 'none'
                            && rect.width > 0 && rect.height > 0;
                        };
                        const rect = node.getBoundingClientRect();
                        if (rect.width < 260 || rect.height < 160) return false;
                        const text = normalize(node.innerText || node.textContent);
                        const hasChoiceSurface = Boolean(node.querySelector(
                          'iframe, table, [role="grid"], [role="row"], [role="tree"], [role="treeitem"], [role="option"], [role="listbox"], .wui-tree, .ant-tree, .u-tree, .wui-table, .ant-table, .u-table, .wui-select-dropdown, .ant-select-dropdown, .u-select-dropdown, [class*="table-row"], [class*="TableRow"]'
                        ));
                        if (!hasChoiceSurface) return false;
                        if (Array.from(node.querySelectorAll('iframe')).some(visible)) return true;
                        const hasConfirm = text.includes('确定') || text.includes('确认') || text.includes('保存');
                        const hasCancel = text.includes('取消');
                        return hasConfirm && (hasCancel || text.includes('确定') || text.includes('确认'));
                    }"""
                )
            )
        except Exception:
            return True

    def _popup_reference_choice_surface_summary(self, candidate) -> dict[str, Any]:
        try:
            result = candidate.evaluate(
                """(node) => {
                    const popupReferenceChoiceSurfaceSummary = true;
                    const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                    const visible = (el) => {
                      if (!el || !(el instanceof HTMLElement)) return false;
                      const style = window.getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style && style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width > 0 && rect.height > 0;
                    };
                    const candidateSelector = [
                      'tbody tr',
                      '[role="grid"] [role="row"]',
                      '[role="row"]:not([aria-rowindex="1"])',
                      '[role="tree"]',
                      '[role="treeitem"]',
                      '[role="option"]',
                      '[role="listbox"] [role="option"]',
                      '.w-table-row',
                      '.wui-table-row',
                      '.ant-table-row',
                      '.u-table-row',
                      '.wui-tree',
                      '.ant-tree',
                      '.u-tree',
                      '.wui-select-dropdown [role="option"]',
                      '.ant-select-dropdown [role="option"]',
                      '.u-select-dropdown [role="option"]',
                      '[class*="table-row"]',
                      '[class*="TableRow"]'
                    ].join(',');
                    const excluded = [
                      'thead',
                      'tfoot',
                      '.wui-pagination',
                      '.ant-pagination',
                      '.u-pagination',
                      '[class*="pagination"]',
                      '[class*="Pagination"]',
                      '[class*="upload"]',
                      '[class*="Upload"]',
                      '[class*="attachment"]',
                      '[class*="Attachment"]'
                    ].join(',');
                    const candidates = Array.from(node.querySelectorAll(candidateSelector))
                      .filter((el, index, all) => all.indexOf(el) === index)
                      .filter((el) => visible(el) && !el.closest(excluded))
                      .filter((el) => {
                        const text = normalize(el.innerText || el.textContent || el.getAttribute('title'));
                        const cls = String(el.className || '').toLowerCase();
                        const role = String(el.getAttribute('role') || '').toLowerCase();
                        if (!text && role !== 'grid' && role !== 'tree' && role !== 'listbox') return false;
                        if (/form-item|formitem|upload|attachment|pagination|footer|header/.test(cls)) return false;
                        return true;
                      });
                    return {
                      has_choice_surface: candidates.length > 0 || Array.from(node.querySelectorAll('iframe')).some(visible),
                      candidate_count: candidates.length,
                      text: normalize(node.innerText || node.textContent).slice(0, 500),
                    };
                }"""
            )
            return dict(result or {})
        except Exception:
            return {}

    def _resolve_popup_reference_dialog_by_structure(self):
        marker = f"ydf-popup-reference-root-{int(time.time() * 1000)}"
        for context in self._all_search_contexts():
            try:
                selector = context.evaluate(
                """(marker) => {
                    const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                    const visible = (el) => {
                      const style = window.getComputedStyle(el);
                      const rect = el.getBoundingClientRect();
                      return style && style.visibility !== 'hidden' && style.display !== 'none'
                        && rect.width > 0 && rect.height > 0;
                    };
                    const hasKeywordInput = (el) => Array.from(el.querySelectorAll('input:not([type="hidden"])'))
                      .some((input) => visible(input) && /关键字|请输入|搜索|查询/.test(input.getAttribute('placeholder') || ''));
                    const hasTable = (el) => Boolean(el.querySelector('table, [role="grid"], .w-table, .wui-table, .ant-table, .u-table, [class*="table"], [class*="Table"]'));
                    const hasChoiceSurface = (el) => Boolean(el.querySelector([
                      'tbody tr',
                      '[role="grid"] [role="row"]',
                      '[role="tree"]',
                      '[role="treeitem"]',
                      '[role="option"]',
                      '[role="listbox"] [role="option"]',
                      '.w-table-row',
                      '.wui-table-row',
                      '.ant-table-row',
                      '.u-table-row',
                      '.wui-tree',
                      '.ant-tree',
                      '.u-tree',
                      '[class*="table-row"]',
                      '[class*="TableRow"]'
                    ].join(',')));
                    const maxRootWidth = Math.max(
                      document.documentElement?.clientWidth || 0,
                      window.innerWidth || 0,
                      1200
                    ) + 24;
                    const roots = Array.from(document.querySelectorAll('body, main, div, section, form'))
                      .filter(visible)
                      .map((el) => ({ el, rect: el.getBoundingClientRect(), text: normalize(el.innerText || el.textContent) }))
                      .filter((item) => item.rect.width >= 260 && item.rect.width <= maxRootWidth && item.rect.height >= 180 && item.rect.height <= 720)
                      .filter((item) => {
                        const hasConfirm = item.text.includes('确定') || item.text.includes('确认') || item.text.includes('保存');
                        return hasChoiceSurface(item.el) && (hasKeywordInput(item.el) || hasTable(item.el)) && hasConfirm && item.text.includes('取消');
                      })
                      .sort((a, b) => (a.rect.width * a.rect.height) - (b.rect.width * b.rect.height));
                    const target = roots[0] && roots[0].el;
                    if (!target) return '';
                    target.setAttribute('data-ydf-browser-popup-reference-root', marker);
                    return `[data-ydf-browser-popup-reference-root="${marker}"]`;
                }""",
                marker,
                )
            except Exception:
                continue
            if not selector:
                continue
            try:
                return context.locator(str(selector)).first
            except Exception:
                continue
        return None

    def _popup_reference_dialog_has_title(self, dialog, title: str) -> bool:
        if not str(title or "").strip():
            return True
        try:
            text = self._collect_popup_reference_diagnostic_text(dialog)
        except Exception:
            return True
        return str(title).strip() in text
