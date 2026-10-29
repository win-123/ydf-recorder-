from __future__ import annotations

import json
import time
from typing import Any

from .model import PopupReferenceError
from .selection import (
    _popup_reference_root_value_is_empty_state,
    _popup_reference_root_value_matches_targets,
    _popup_reference_targets_are_plain_first_available,
    _remaining_timeout_ms,
    build_popup_reference_confirm_selectors,
)

POPUP_REFERENCE_CONFIRM_LABELS = ("确定", "确认", "保存")

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


class CompletionStage:
    def _wait_for_popup_reference_root_backfill(
        self,
        root,
        before_value: str,
        selection_targets: list[dict[str, Any]] | None = None,
        timeout_ms: int = 3500,
    ) -> bool:
        if not self._popup_reference_root_backfill_check_required(root):
            return True
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            remaining_ms = _remaining_timeout_ms(deadline)
            if remaining_ms <= 0:
                return False
            after_value = self._read_popup_reference_root_value(root, timeout_ms=min(1000, remaining_ms))
            if self._popup_reference_root_value_backfilled(after_value, before_value, selection_targets):
                return True
            remaining_ms = _remaining_timeout_ms(deadline)
            if remaining_ms <= 0:
                return False
            poll_ms = min(200, remaining_ms)
            try:
                self._wait_for_timeout(poll_ms)
            except PopupReferenceError:
                raise
            except Exception:
                return False

    def _read_popup_reference_root_value(self, root, timeout_ms: int = 1000) -> str:
        if timeout_ms <= 0:
            return ""
        try:
            value = root.evaluate(_FIELD_VALUE_FROM_ROOT_SCRIPT, "", timeout=max(1, timeout_ms))
            return str(value or "").strip()
        except Exception:
            return ""

    def _popup_reference_root_backfilled(
        self,
        root,
        before_value: str,
        selection_targets: list[dict[str, Any]] | None = None,
    ) -> bool:
        after_value = self._read_popup_reference_root_value(root)
        return self._popup_reference_root_value_backfilled(after_value, before_value, selection_targets)

    def _popup_reference_root_value_backfilled(
        self,
        after_value: str,
        before_value: str,
        selection_targets: list[dict[str, Any]] | None = None,
    ) -> bool:
        if not after_value:
            return False
        if _popup_reference_root_value_is_empty_state(after_value):
            return False
        if after_value != str(before_value or "").strip():
            return True
        if _popup_reference_targets_are_plain_first_available(selection_targets or []):
            return True
        return _popup_reference_root_value_matches_targets(after_value, selection_targets or [])

    def _popup_reference_root_backfill_check_required(self, root) -> bool:
        return callable(getattr(root, "evaluate", None))

    def _click_popup_reference_confirm(self, dialog) -> None:
        for label in POPUP_REFERENCE_CONFIRM_LABELS:
            for selector in build_popup_reference_confirm_selectors(label):
                locator = dialog.locator(selector)
                try:
                    count = locator.count()
                except Exception:
                    continue
                for index in range(count):
                    candidate = locator.nth(index)
                    try:
                        if not candidate.is_visible(timeout=300):
                            continue
                        self._last_popup_reference_confirm_debug = json.dumps(
                            {"selector": selector, "index": index},
                            ensure_ascii=False,
                        )
                        self._last_popup_reference_confirm_label = label
                        candidate.click(timeout=2000)
                        if not self._popup_reference_dialog_still_visible(dialog):
                            return
                        try:
                            candidate.click(timeout=1000, force=True)
                        except Exception:
                            pass
                        if not self._popup_reference_dialog_still_visible(dialog):
                            return
                        try:
                            candidate.evaluate(
                                """(node) => {
                                    node.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                                    node.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                                    node.click();
                                }"""
                            )
                        except Exception:
                            pass
                        return
                    except Exception:
                        continue
        try:
            marker = f"confirm-{int(time.time() * 1000)}"
            result = dialog.evaluate(
                """(root, args) => {
                        const normalize = (text) => String(text || '').replace(/\\s+/g, '').trim();
                        const wanted = new Set(args.labels.map(normalize));
                        const visible = (el) => {
                          const style = window.getComputedStyle(el);
                          const rect = el.getBoundingClientRect();
                          return style && style.visibility !== 'hidden' && style.display !== 'none'
                            && rect.width > 0 && rect.height > 0;
                        };
                        const footerSelector = [
                          '.ant-modal-footer',
                          '.wui-modal-footer',
                          '.yy-modal-footer',
                          '.u-modal-footer',
                          '[class*="modal-footer"]',
                          '[class*="ModalFooter"]',
                          '[class*="footer"]',
                          '[class*="Footer"]'
                        ].join(',');
                        const clickableSelector = [
                          'button',
                          '[role="button"]',
                          'a',
                          '.wui-button',
                          '.ant-btn',
                          '.u-button',
                          '.w-button',
                          '[class*="button"]',
                          '[class*="Button"]'
                        ].join(',');
                        const candidates = Array.from(root.querySelectorAll([
                          clickableSelector,
                          'span',
                          'div'
                        ].join(',')))
                          .filter(visible)
                          .map((candidate, index) => {
                            const clickable = candidate.closest(clickableSelector) || candidate;
                            const className = String(clickable.className || candidate.className || '');
                            if (clickable.disabled || clickable.getAttribute('aria-disabled') === 'true' || /disabled/i.test(className)) return null;
                            const text = normalize(candidate.innerText || candidate.textContent || candidate.getAttribute('title'));
                            if (!wanted.has(text)) return null;
                            const footer = clickable.closest(footerSelector) || candidate.closest(footerSelector);
                            const primary = /primary|danger|confirm|ok/i.test(className);
                            const rect = clickable.getBoundingClientRect();
                            if (rect.width > 280 || rect.height > 90) return null;
                            return { candidate: clickable, index, text, footer: Boolean(footer), primary };
                          }
                          )
                          .filter(Boolean)
                          .sort((a, b) => {
                            const ar = a.candidate.getBoundingClientRect();
                            const br = b.candidate.getBoundingClientRect();
                            return Number(b.footer) - Number(a.footer)
                              || Number(b.primary) - Number(a.primary)
                              || br.top - ar.top
                              || a.index - b.index;
                          });
                        const target = candidates[0];
                        if (!target) return null;
                        target.candidate.setAttribute('data-ydf-browser-popup-reference-confirm', args.marker);
                        return {
                          selector: `[data-ydf-browser-popup-reference-confirm="${args.marker}"]`,
                          text: target.text,
                          cls: String(target.candidate.className || '').slice(0, 160),
                          footer: target.footer,
                          primary: target.primary,
                          index: target.index,
                        };
                    }""",
                {"labels": list(POPUP_REFERENCE_CONFIRM_LABELS), "marker": marker},
            )
            if result and result.get("selector"):
                self._last_popup_reference_confirm_debug = json.dumps(result, ensure_ascii=False)[:800]
                self._last_popup_reference_confirm_label = str(result.get("text") or "").strip()
                candidate = dialog.locator(str(result["selector"])).first
                try:
                    candidate.click(timeout=2000)
                except Exception:
                    candidate.click(timeout=1000, force=True)
                return
        except Exception:
            pass
        page = self._require_page()
        for frame in getattr(page, "frames", []):
            if frame is page.main_frame:
                continue
            try:
                if not self._popup_reference_dialog_contains_origin(dialog, frame.frame_element()):
                    continue
                self._click_popup_reference_confirm(frame.locator("body").first)
                return
            except Exception:
                continue
        diagnostic = self._collect_popup_reference_diagnostic_text(dialog)
        if "无可见下拉/参照候选" in diagnostic:
            self._last_popup_reference_close_action = "choice-surface-gone"
            return
        screenshot = self._save_diagnostic_screenshot("popup-reference-confirm-missing")
        if screenshot:
            diagnostic = f"{diagnostic} | screenshot={screenshot}"
        raise RuntimeError(f"未找到弹出参照确认按钮: {diagnostic}")

    def _click_popup_reference_confirm_with_label(self, dialog, label: str) -> None:
        for selector in build_popup_reference_confirm_selectors(label):
            locator = dialog.locator(selector)
            try:
                count = locator.count()
            except Exception:
                continue
            for index in range(count):
                candidate = locator.nth(index)
                try:
                    if not candidate.is_visible(timeout=300):
                        continue
                    self._last_popup_reference_confirm_label = label
                    candidate.click(timeout=2000)
                    return
                except Exception:
                    continue
        if self._click_popup_reference_confirm_structurally(dialog, (label,)):
            return
        diagnostic = self._collect_popup_reference_diagnostic_text(dialog)
        screenshot = self._save_diagnostic_screenshot("popup-reference-confirm-missing")
        if screenshot:
            diagnostic = f"{diagnostic} | screenshot={screenshot}"
        raise RuntimeError(f"未找到弹出参照确认按钮: {label}: {diagnostic}")

    def _click_popup_reference_confirm_structurally(
        self,
        dialog,
        labels: tuple[str, ...],
    ) -> bool:
        marker = f"confirm-{int(time.time() * 1000)}"
        script = """(root, args) => {
                const normalize = (text) => String(text || '').replace(/\\s+/g, '').trim();
                const wanted = new Set(args.labels.map(normalize));
                const visible = (el) => {
                  if (!el || !(el instanceof HTMLElement)) return false;
                  const style = window.getComputedStyle(el);
                  const rect = el.getBoundingClientRect();
                  return style && style.visibility !== 'hidden' && style.display !== 'none'
                    && rect.width > 0 && rect.height > 0;
                };
                const footerSelector = [
                  '.ant-modal-footer',
                  '.wui-modal-footer',
                  '.yy-modal-footer',
                  '.u-modal-footer',
                  '[class*="modal-footer"]',
                  '[class*="ModalFooter"]',
                  '[class*="footer"]',
                  '[class*="Footer"]'
                ].join(',');
                const clickableSelector = [
                  'button',
                  '[role="button"]',
                  'a',
                  '.wui-button',
                  '.ant-btn',
                  '.u-button',
                  '.w-button',
                  '[class*="button"]',
                  '[class*="Button"]'
                ].join(',');
                const candidates = Array.from(root.querySelectorAll([
                  clickableSelector,
                  'span',
                  'div'
                ].join(',')))
                  .filter(visible)
                  .map((candidate, index) => {
                    const clickable = candidate.closest(clickableSelector) || candidate;
                    const className = String(clickable.className || candidate.className || '');
                    if (clickable.disabled || clickable.getAttribute('aria-disabled') === 'true' || /disabled/i.test(className)) return null;
                    const text = normalize(candidate.innerText || candidate.textContent || candidate.getAttribute('title') || candidate.getAttribute('aria-label'));
                    if (!wanted.has(text)) return null;
                    const footer = clickable.closest(footerSelector) || candidate.closest(footerSelector);
                    const primary = /primary|danger|confirm|ok/i.test(className);
                    const rect = clickable.getBoundingClientRect();
                    if (rect.width > 280 || rect.height > 90) return null;
                    return { candidate: clickable, index, text, footer: Boolean(footer), primary };
                  })
                  .filter(Boolean)
                  .sort((a, b) => {
                    const ar = a.candidate.getBoundingClientRect();
                    const br = b.candidate.getBoundingClientRect();
                    return Number(b.footer) - Number(a.footer)
                      || Number(b.primary) - Number(a.primary)
                      || br.top - ar.top
                      || a.index - b.index;
                  });
                const target = candidates[0];
                if (!target) return null;
                target.candidate.setAttribute('data-ydf-browser-popup-reference-confirm', args.marker);
                return {
                  selector: `[data-ydf-browser-popup-reference-confirm="${args.marker}"]`,
                  text: target.text,
                  cls: String(target.candidate.className || '').slice(0, 160),
                  footer: target.footer,
                  primary: target.primary,
                  index: target.index,
                };
            }"""

        def click_from(context) -> bool:
            try:
                try:
                    result = context.evaluate(
                        script,
                        {"labels": list(labels), "marker": marker},
                        timeout=1200,
                    )
                except TypeError:
                    result = context.evaluate(script, {"labels": list(labels), "marker": marker})
                if not isinstance(result, dict) or not result.get("selector"):
                    return False
                self._last_popup_reference_confirm_debug = json.dumps(result, ensure_ascii=False)[:800]
                self._last_popup_reference_confirm_label = str(result.get("text") or "").strip()
                candidate = context.locator(str(result["selector"])).first
                try:
                    candidate.click(timeout=2000)
                except Exception:
                    candidate.click(timeout=1000, force=True)
                return True
            except Exception:
                return False

        if click_from(dialog):
            return True
        try:
            page = self._require_page()
        except Exception:
            return False
        for frame in getattr(page, "frames", []):
            if frame is getattr(page, "main_frame", None):
                continue
            try:
                if not self._popup_reference_dialog_contains_origin(dialog, frame.frame_element()):
                    continue
                if click_from(frame.locator("body").first):
                    return True
            except Exception:
                continue
        return False

    def _popup_reference_dialog_hidden_now(self, dialog) -> bool:
        try:
            if not bool(dialog.is_visible(timeout=200)):
                return not self._has_visible_popup_reference_surface_in_search_contexts()
        except AttributeError:
            return False
        except Exception:
            return not self._has_visible_popup_reference_surface_in_search_contexts()
        try:
            dialog_has_surface = bool(
                dialog.evaluate(
                    """(root) => {
                        const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
                        const visible = (el) => {
                          const style = window.getComputedStyle(el);
                          const rect = el.getBoundingClientRect();
                          return style && style.visibility !== 'hidden' && style.display !== 'none'
                            && rect.width > 0 && rect.height > 0;
                        };
                        const overlaySelector = [
                          '.ant-modal',
                          '.wui-modal',
                          '.w-modal',
                          '.yy-modal',
                          '.u-modal',
                          '[role="dialog"]',
                          '[class*="modal"]',
                          '[class*="Modal"]',
                          '[class*="popup"]',
                          '[class*="Popup"]',
                          '[class*="popover"]',
                          '[class*="Popover"]',
                          '[class*="dropdown"]',
                          '[class*="Dropdown"]'
                        ].join(',');
                        const rootText = [
                          root.className,
                          root.getAttribute?.('role'),
                          root.getAttribute?.('aria-modal')
                        ].join(' ');
                        const rootLooksLikeOverlay = root !== document.body
                          && root !== document.documentElement
                          && (/dialog|modal|popup|popover|dropdown/i.test(rootText)
                            || root.matches?.(overlaySelector));
                        const overlayRoots = [
                          ...(rootLooksLikeOverlay ? [root] : []),
                          ...Array.from(root.querySelectorAll(overlaySelector)).filter(visible)
                        ].filter((item, index, all) => item && all.indexOf(item) === index);
                        const buttonSelector = 'button, [role="button"], .wui-button, .ant-btn, .u-button, .w-button';
                        const choiceSelector = [
                          'iframe',
                          'table',
                          '[role="grid"]',
                          '[role="tree"]',
                          '[role="treeitem"]',
                          '[role="option"]',
                          '[role="listbox"]',
                          '.wui-tree',
                          '.ant-tree',
                          '.u-tree',
                          '.wui-table',
                          '.ant-table',
                          '.u-table',
                          '.w-select-dropdown',
                          '.wui-select-dropdown',
                          '.ant-select-dropdown',
                          '.u-select-dropdown',
                          '[class*="list"]',
                          '[class*="List"]'
                        ].join(',');
                        const hasConfirmButton = (scope) => Array.from(scope.querySelectorAll(buttonSelector))
                          .filter(visible)
                          .map((button) => normalize(button.innerText || button.textContent || button.getAttribute('title') || button.getAttribute('aria-label')))
                          .some((item) => item === '确定' || item === '确认' || item === '保存');
                        const hasCancelButton = (scope) => Array.from(scope.querySelectorAll(buttonSelector))
                          .filter(visible)
                          .map((button) => normalize(button.innerText || button.textContent || button.getAttribute('title') || button.getAttribute('aria-label')))
                          .some((item) => item === '取消');
                        const hasChoiceSurface = (scope) => Array.from(scope.querySelectorAll(choiceSelector))
                          .some((item) => visible(item));
                        return (hasChoiceSurface(root) && hasConfirmButton(root) && hasCancelButton(root))
                          || overlayRoots.some((scope) => hasChoiceSurface(scope) && hasConfirmButton(scope));
                    }""",
                    timeout=500,
                )
            )
            if dialog_has_surface:
                return False
        except AttributeError:
            return False
        except Exception:
            return not self._has_visible_popup_reference_surface_in_search_contexts()
        dialog_frame_contexts = self._popup_reference_dialog_frame_contexts(dialog)
        if dialog_frame_contexts:
            return not self._has_visible_popup_reference_surface_in_search_contexts(
                contexts=dialog_frame_contexts,
                require_reference_identity=False,
            )
        if self._has_visible_popup_reference_surface_in_search_contexts():
            return False
        return True

    def _popup_reference_dialog_frame_contexts(self, dialog) -> list[Any]:
        try:
            iframe_locator = dialog.locator("iframe")
            iframe_count = min(max(int(iframe_locator.count()), 0), 20)
        except Exception:
            return []
        has_visible_iframe = False
        for index in range(iframe_count):
            try:
                if iframe_locator.nth(index).is_visible(timeout=200):
                    has_visible_iframe = True
                    break
            except Exception:
                continue
        if not has_visible_iframe:
            return []
        try:
            page = self._require_page()
        except Exception:
            return []
        main_frame = getattr(page, "main_frame", None)
        contexts: list[Any] = []
        for frame in getattr(page, "frames", []):
            if frame is main_frame:
                continue
            try:
                frame_element = frame.frame_element()
                try:
                    if not frame_element.is_visible():
                        continue
                except Exception:
                    pass
                if self._popup_reference_dialog_contains_origin(dialog, frame_element):
                    contexts.append(frame)
            except Exception:
                continue
        return contexts

    def _has_visible_popup_reference_surface_in_search_contexts(
        self,
        contexts: list[Any] | None = None,
        *,
        require_reference_identity: bool = True,
    ) -> bool:
        reference_identity = "referenceEvidence" if require_reference_identity else "true"
        script = """() => {
            const normalize = (value) => String(value || '').replace(/\\s+/g, ' ').trim();
            const visible = (el) => {
              if (!el || !(el instanceof HTMLElement)) return false;
              const style = window.getComputedStyle(el);
              const rect = el.getBoundingClientRect();
              return style && style.visibility !== 'hidden' && style.display !== 'none'
                && rect.width > 0 && rect.height > 0;
            };
            const buttonSelector = 'button, [role="button"], .wui-button, .ant-btn, .u-button, .w-button';
            const choiceSelector = [
              'table',
              '[role="grid"]',
              '[role="tree"]',
              '[role="treeitem"]',
              '[role="option"]',
              '[role="listbox"]',
              '.wui-tree',
              '.ant-tree',
              '.u-tree',
              '.wui-table',
              '.ant-table',
              '.u-table',
              '.w-select-dropdown',
              '.wui-select-dropdown',
              '.ant-select-dropdown',
              '.u-select-dropdown',
              '[class*="list"]',
              '[class*="List"]'
            ].join(',');
            const hasButtonText = (scope, labels) => Array.from(scope.querySelectorAll(buttonSelector))
              .filter(visible)
              .map((button) => normalize(button.innerText || button.textContent || button.getAttribute('title') || button.getAttribute('aria-label')))
              .some((item) => labels.includes(item));
            const hasConfirmButton = (scope) => hasButtonText(scope, ['确定', '确认', '保存']);
            const hasCancelButton = (scope) => hasButtonText(scope, ['取消']);
            const hasChoiceSurface = (scope) => Array.from(scope.querySelectorAll(choiceSelector))
              .some((item) => visible(item));
            const href = String(window.location && window.location.href || '');
            const isReferenceFrame = /PM_SELECT_MANAGER|_fromNodeCode=|select|reference|refer/i.test(href);
            const roots = Array.from(document.querySelectorAll('body, main, div, section, form'))
              .filter(visible)
              .map((el) => ({ el, rect: el.getBoundingClientRect(), text: normalize(el.innerText || el.textContent) }))
              .filter((item) => item.rect.width >= 260 && item.rect.height >= 160)
              .filter((item) => {
                const text = item.text;
                const hasReferenceTitle = /项目负责人|参照|选择|人员/.test(text);
                const referenceEvidence = isReferenceFrame || hasReferenceTitle;
                const structureEvidence = hasChoiceSurface(item.el)
                  && hasConfirmButton(item.el)
                  && hasCancelButton(item.el);
                return structureEvidence && __REFERENCE_IDENTITY__;
              })
              .sort((a, b) => (a.rect.width * a.rect.height) - (b.rect.width * b.rect.height));
            return roots.length > 0;
        }""".replace("__REFERENCE_IDENTITY__", reference_identity)
        try:
            search_contexts = self._all_search_contexts() if contexts is None else list(contexts)
        except Exception:
            return False
        for context in search_contexts:
            try:
                try:
                    result = context.evaluate(script, timeout=500)
                except TypeError:
                    result = context.evaluate(script)
                if bool(result):
                    return True
            except Exception:
                continue
        return False

    def _activate_popup_reference_selected_item(self, dialog) -> bool:
        selected_selectors = [
            ".wui-tree-node-selected",
            ".wui-tree-treenode-selected .wui-tree-node-content-wrapper",
            ".ant-tree-node-selected",
            ".ant-tree-treenode-selected .ant-tree-node-content-wrapper",
            ".u-tree-node-selected",
            '[aria-selected="true"]',
            '[class*="selected"]',
            '[class*="active"]',
        ]
        for selector in selected_selectors:
            try:
                locator = dialog.locator(selector)
                count = min(locator.count(), 20)
            except Exception:
                continue
            for index in range(count):
                candidate = locator.nth(index)
                try:
                    if not candidate.is_visible(timeout=200):
                        continue
                    try:
                        candidate.dblclick(timeout=1000)
                    except Exception:
                        candidate.click(timeout=1000)
                    return True
                except Exception:
                    continue
        try:
            return bool(
                dialog.evaluate(
                    """(root) => {
                        const visible = (el) => {
                          const style = window.getComputedStyle(el);
                          const rect = el.getBoundingClientRect();
                          return style && style.visibility !== 'hidden' && style.display !== 'none'
                            && rect.width > 0 && rect.height > 0;
                        };
                        const excluded = 'button, input, textarea, select, .yy-modal-footer *, .ant-modal-footer *, .wui-modal-footer *, .u-modal-footer *';
                        const candidates = Array.from(root.querySelectorAll('[aria-selected="true"], [class*="selected"], [class*="active"]'))
                          .filter((el) => visible(el) && !el.matches(excluded) && !el.closest(excluded))
                          .sort((a, b) => {
                            const ar = a.getBoundingClientRect();
                            const br = b.getBoundingClientRect();
                            return (ar.width * ar.height) - (br.width * br.height);
                          });
                        const target = candidates[0];
                        if (!target) return false;
                        target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                        target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                        target.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
                        target.click();
                        return true;
                    }"""
                )
            )
        except Exception:
            return False

    def _popup_reference_dialog_still_visible(self, dialog) -> bool:
        try:
            self._wait_for_timeout(120)
        except PopupReferenceError:
            raise
        except Exception:
            pass
        try:
            return bool(dialog.is_visible(timeout=200))
        except Exception:
            return False

    def _wait_for_popup_reference_dialog_to_close(self, dialog, timeout_ms: int = 2500) -> bool:
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            self._check_cancelled()
            try:
                if not dialog.is_visible(timeout=300):
                    return True
            except Exception:
                return False
            self._check_selection_rejection()
            if self._popup_reference_dialog_replaced(dialog):
                return True
            if time.monotonic() >= deadline:
                return False
            self._wait_for_timeout(min(100, max(1, int((deadline - time.monotonic()) * 1000))))

    def _popup_reference_dialog_replaced(self, dialog) -> bool:
        try:
            return bool(dialog.evaluate("""(root) => {
                const visible = (node) => {
                  const rect = node.getBoundingClientRect();
                  const style = getComputedStyle(node);
                  return rect.width > 0 && rect.height > 0
                    && style.display !== 'none' && style.visibility !== 'hidden';
                };
                const buttons = 'button, [role="button"], .wui-button, .ant-btn, .u-button, .w-button';
                const text = (node) => String(node.innerText || node.textContent || '').trim();
                const confirms = Array.from(root.querySelectorAll(buttons))
                  .filter(node => visible(node) && ['确定', '确认', '保存'].includes(text(node)));
                return confirms.length > 0 && confirms.every(button => {
                  const rect = button.getBoundingClientRect();
                  const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
                  if (!hit || root.contains(hit)) return false;
                  for (let node = hit; node && node !== document.body; node = node.parentElement) {
                    if (node.contains(root)) return false;
                    const controls = Array.from(node.querySelectorAll(buttons)).filter(visible);
                    const hasConfirm = controls.some(item => ['确定', '确认', '保存'].includes(text(item)));
                    const hasCancel = controls.some(item => text(item) === '取消');
                    const choices = node.querySelectorAll('table, [role="grid"], [role="tree"], [role="option"], [role="treeitem"], iframe');
                    if (hasConfirm && hasCancel && Array.from(choices).some(visible)) return true;
                  }
                  return false;
                });
            }""", timeout=500))
        except Exception:
            return False

    def _close_popup_reference_dialog_if_visible(self, dialog) -> bool:
        try:
            if not dialog.is_visible(timeout=300):
                return True
        except Exception:
            return False
        for selector in (
            ".ant-modal-close",
            ".wui-modal-close",
            ".u-modal-close",
            '[aria-label="Close"]',
            'button:has-text("×")',
        ):
            try:
                locator = dialog.locator(selector)
                count = min(locator.count(), 5)
            except Exception:
                continue
            for index in range(count):
                candidate = locator.nth(index)
                try:
                    if candidate.is_visible(timeout=300):
                        candidate.click(timeout=1000)
                        return self._wait_for_popup_reference_dialog_to_close(dialog, timeout_ms=1500)
                except Exception:
                    continue
        return False
