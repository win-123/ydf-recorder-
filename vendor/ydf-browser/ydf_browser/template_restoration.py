from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from .binder import bind_manifest
from .models import BindingResult, BoundElement, PageManifest
from .platform_rendering_contract import build_contract_path
from .template_parser import build_page_manifest


class RuntimeTemplateAdapter:
    """Browser facts and existing binding interactions, without restoration policy."""

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime

    def peek_template(self) -> dict[str, Any] | None:
        pop = getattr(self._runtime, "pop_dynamic_template_payload", None)
        if pop is None:
            return None
        peek = getattr(self._runtime, "peek_dynamic_template_payload", None)
        return peek() if peek is not None else pop()

    def matches_action(self, payload: dict[str, Any]) -> bool:
        matches = getattr(self._runtime, "_dynamic_template_payload_matches_action", None)
        return matches is None or matches(payload)

    def can_apply_as_fallback(self, payload: dict[str, Any]) -> bool:
        fallback = getattr(self._runtime, "dynamic_template_payload_can_apply_as_fallback", None)
        return fallback is not None and fallback(payload)

    def work_surface_ready(self, payload: dict[str, Any]) -> bool:
        ready = getattr(self._runtime, "_dynamic_template_payload_work_surface_ready", None)
        return ready is None or ready(payload)

    def consume_template(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        if getattr(self._runtime, "peek_dynamic_template_payload", None) is None:
            return payload
        pop_if_current = getattr(self._runtime, "pop_dynamic_template_payload_if_current", None)
        return pop_if_current(payload) if pop_if_current is not None else self._runtime.pop_dynamic_template_payload()

    def visible_page_identity(self, fieldids: list[str]) -> str | None:
        resolve = getattr(self._runtime, "resolve_visible_page_identity", None)
        return resolve(fieldids) if resolve is not None else None

    def prepare_binding(self, manifest: PageManifest) -> None:
        self._runtime.prepare_binding(manifest)

    def capture_runtime_elements(self, manifest: PageManifest) -> list[dict[str, Any]]:
        return self._runtime.capture_runtime_elements(manifest)

    def capture_page_state(self) -> dict[str, Any] | None:
        capture = getattr(self._runtime, "capture_page_state", None)
        if capture is None:
            return None
        try:
            return capture()
        except Exception:
            return None


@dataclass
class TemplateActionResult:
    value: Any
    changes: dict[str, Any]


class TemplateRestoration:
    """Own the current template context; callers execute actions, not restore stages."""

    def __init__(
        self,
        adapter: Any,
        *,
        on_action_notifications: Callable[[list[dict[str, str]]], None] | None = None,
    ) -> None:
        self._adapter = adapter
        self._on_action_notifications = on_action_notifications
        self._last_step_action: str | None = None
        self._last_dom_transition_restore: dict[str, Any] | None = None
        self.initialize()

    @property
    def manifest(self) -> PageManifest | None:
        return self._manifest

    @property
    def binding(self) -> BindingResult | None:
        return self._binding

    @property
    def page_state(self) -> dict[str, Any] | None:
        return self._page_state

    @property
    def active_tab_region_fieldid(self) -> str | None:
        return self._active_tab_region_fieldid

    @property
    def has_parent(self) -> bool:
        return bool(self._history)

    def record_step(self, action: str) -> None:
        """Remember successful dispatches, including steps that cannot switch templates."""
        self._last_step_action = action

    def prepare_step(self) -> dict[str, Any] | None:
        """Apply a ready preceding response before target resolution or candidate clearing."""
        return self._apply_pending_template(self._last_step_action or "toolbar.click", before_action=True)

    def refresh_binding(self, *, source: str = "field") -> None:
        if self._manifest is None:
            return
        if source not in {"tab.click", "query.expand", "row.hover"}:
            self._adapter.prepare_binding(self._manifest)
        elements = self._adapter.capture_runtime_elements(self._manifest)
        if source != "row.hover":
            self._page_state = self._adapter.capture_page_state()
        self._binding = bind_manifest(self._manifest, elements)

    def include_field(self, bound: BoundElement) -> None:
        if self._binding is not None:
            self._binding.bound_fields.append(bound)

    def initialize(
        self,
        manifest: PageManifest | None = None,
        binding: BindingResult | None = None,
        page_state: dict[str, Any] | None = None,
        *,
        manifest_history: Iterable[PageManifest] = (),
    ) -> None:
        self._manifest = manifest
        self._binding = binding
        self._page_state = page_state
        self._history: list[tuple[PageManifest, str | None]] = []
        self._source: str | None = None
        self._active_tab_region_fieldid: str | None = None
        self._seen_manifests = list(manifest_history)

    def execute(
        self,
        action: str,
        callback: Callable[[], Any],
        *,
        restore_previous: bool = False,
        target: dict[str, Any] | None = None,
    ) -> TemplateActionResult:
        """Execute once and return action data plus template-change facts.

        The callback owns clicks, completion waits and validation; selected fields
        must already have confirmed reference completion. ``target`` preserves a
        requested action identity not present in its result (fieldid plus label).
        ``table.scope`` wraps the existing pre-target table availability check.
        Exceptions keep any context already applied, without retries or rollback.
        """
        changes: dict[str, Any] = {}
        if action == "table.scope":
            self._restore_previous_table_template_if_available()
            return TemplateActionResult(callback(), changes)
        if action == "form.fill":
            before = self._apply_pending_template(action)
            if before:
                changes["dynamic_template"] = before
        value = callback()
        notifications = value.get("notifications") or []
        if value.get("completion_signal") == "confirmation_required":
            if action == "action.click" and self._on_action_notifications is not None:
                self._on_action_notifications(notifications)
            return TemplateActionResult(value, changes)
        identity = target if target is not None else value
        fieldid = str(identity.get("fieldid") or "")
        action_label = str(identity.get("label") or "")
        if target is not None:
            fieldid, action_label = fieldid.strip(), action_label.strip()
        label = action_label or fieldid
        dynamic = None
        if action in {"toolbar.click", "dialog.click", "action.click", "form.fill", "editable_table.add_row",
                      "table_row_action.click", "table.click_cell_link", "popup_reference.select", "workflow_panel.click"}:
            dynamic = self._apply_pending_template(action)
            if dynamic:
                changes["dynamic_template"] = dynamic
        # Generic actions publish notifications after applying a payload but before
        # DOM restoration, so a rebinding failure retains the original diagnostics.
        if action == "action.click" and self._on_action_notifications is not None:
            self._on_action_notifications(notifications)
        automatic = False
        restore = False
        if action == "toolbar.click" and not dynamic:
            automatic = (
                label in {"确定", "确认"} and self._should_auto_restore_previous_template_after_dialog_confirm(notifications)
                or self._should_auto_restore_previous_template_after_save(label, notifications)
                or self._should_auto_restore_previous_template_after_cancel(label, notifications)
                or self._should_auto_restore_previous_template_after_confirm(label, notifications)
            )
            restore = automatic or restore_previous
        elif action == "dialog.click" and not dynamic:
            if restore_previous:
                restore = True
            else:
                automatic = (
                    self._should_auto_restore_previous_template_after_save(label, notifications)
                    or self._should_auto_restore_previous_template_after_dialog_confirm(notifications)
                )
                restore = automatic
        elif action == "popup_reference.select" and not dynamic:
            if self._source in {"editable_table.add_row", "popup_reference.select"}:
                if value.get("confirmed") is True and not _has_error_notification(notifications):
                    restored = self._restore_closed_reference_chain()
                    if restored:
                        changes.update(restored_template=restored, auto_restored_template=True)
            else:
                restore = automatic = self._should_auto_restore_previous_template_after_popup_reference_select()
        elif action == "form.fill" and any(field.get("selected") for field in value.get("fields", [])):
            status = self._form_popup_reference_restore_status(allow_form_fill=dynamic is not None)
            changes["popup_reference_restore"] = status
            restore = automatic = bool(status.get("should_restore"))
        elif action in {"action.click", "tab.click"} and not dynamic:
            if action == "tab.click" and value.get("fieldid"):
                self._active_tab_region_fieldid = _tab_content_fieldid(value["fieldid"])
            restored = self._try_restore_previous_template_after_dom_transition(
                source=action, label=label, notifications=notifications,
            )
            evidence = self._last_dom_transition_restore
            if evidence and (action == "action.click" or evidence.get("checked")):
                changes["dom_transition"] = evidence
            if restored:
                changes.update(restored_template=restored, restore_reason="dom_transition")
                if action == "tab.click":
                    changes["auto_restored_template"] = True
                elif _is_return_action(fieldid, action_label):
                    changes["return_action_hint"] = True
            if action == "tab.click":
                if not restored:
                    self.refresh_binding(source="tab.click")
                if restored or self._manifest is not None:
                    changes["bound_field_count"] = len(self._binding.bound_fields) if self._binding else 0
        elif action in {"table_row_action.click", "table.click_cell_link"} and not dynamic:
            switched = self._apply_seen_manifest_if_dom_switched()
            if switched:
                changes["dom_switched_template"] = switched
        if restore:
            restored = self._restore_previous()
            if restored:
                changes["restored_template"] = restored
                if automatic:
                    changes["auto_restored_template"] = True
        return TemplateActionResult(value, changes)

    def _restore_closed_reference_chain(self) -> dict[str, Any] | None:
        for index in range(len(self._history) - 1, -1, -1):
            previous, source = self._history[index]
            try:
                elements = self._adapter.capture_runtime_elements(previous)
            except Exception:
                return None
            if source in {"editable_table.add_row", "popup_reference.select"}:
                candidates = [*previous.table_columns, *previous.fields, *previous.query_fields, *previous.trees]
                fieldids = {candidate.fieldid for candidate in candidates if candidate.fieldid}
                # Shared column labels and footer buttons do not prove a previous reference is still active.
                if not any(item.get("visible", True) and item.get("pointer_receivable") is not False
                           and item.get("fieldid") in fieldids for item in elements):
                    continue
            if _manifest_visible_unshared_action_identity_matches(
                self._manifest, previous, elements, {"保存", "提交", "取消", "确定", "确认"},
            ):
                return None
            if _manifest_visibility_score(previous, elements) > _manifest_visibility_score(self._manifest, elements):
                self._history = self._history[:index + 1]
                return self._restore_previous()
            if source not in {"editable_table.add_row", "popup_reference.select"}:
                return None
        return None

    def _restore_previous(self) -> dict[str, Any] | None:
        if not self._history:
            return None
        self._manifest, self._source = self._history.pop()
        self._active_tab_region_fieldid = None
        self._adapter.prepare_binding(self._manifest)
        elements = self._adapter.capture_runtime_elements(self._manifest)
        self._page_state = self._adapter.capture_page_state()
        self._binding = bind_manifest(self._manifest, elements)
        return {"page": self._manifest.page.fieldid, "bound_action_count": len(self._binding.bound_actions)}

    def _apply_pending_template(self, source: str, *, before_action: bool = False) -> dict[str, Any] | None:
        payload = self._adapter.peek_template()
        if not payload:
            return None
        fallback_contract_path = None
        if not self._adapter.matches_action(payload):
            if not self._adapter.can_apply_as_fallback(payload):
                return None
            fallback_contract_path = build_contract_path(
                "unverified", ["PRS-COMPLETE-002"], "exact_identity_unavailable"
            )
            if source == "toolbar.click" and not before_action:
                # Defer targetless toolbar evidence until the next component's work surface is ready.
                return None
        if not self._adapter.work_surface_ready(payload):
            return None
        payload = self._adapter.consume_template(payload)
        if not payload:
            return None
        if self._manifest is not None:
            self._history.append((self._manifest, self._source))
        self._manifest = build_page_manifest(payload)
        self._active_tab_region_fieldid = None
        self._source = source
        self._seen_manifests = [item for item in self._seen_manifests if item.page.fieldid != self._manifest.page.fieldid]
        self._seen_manifests.append(self._manifest)
        self._adapter.prepare_binding(self._manifest)
        elements = self._adapter.capture_runtime_elements(self._manifest)
        self._page_state = self._adapter.capture_page_state()
        self._binding = bind_manifest(self._manifest, elements)
        result = {"page": self._manifest.page.fieldid, "bound_action_count": len(self._binding.bound_actions)}
        if fallback_contract_path is not None:
            result["contract_path"] = fallback_contract_path
        return result

    def _should_auto_restore_previous_template_after_save(
        self,
        label: str,
        notifications: list[dict[str, str]],
    ) -> bool:
        if label not in {"保存", "提交"} or not self._history:
            return False
        if _has_error_notification(notifications):
            return False
        if self._manifest is None:
            return False
        previous_manifest = self._history[-1][0]
        try:
            runtime_elements = self._adapter.capture_runtime_elements(previous_manifest)
        except Exception:
            return False
        if _manifest_visible_unshared_action_identity_matches(
            self._manifest,
            previous_manifest,
            runtime_elements,
            _STABLE_EDIT_ACTION_ALIASES - {"取消"},
        ):
            return False
        previous_score = _manifest_visibility_score(previous_manifest, runtime_elements)
        current_score = _manifest_visibility_score(self._manifest, runtime_elements)
        if previous_score <= 0:
            return False
        if previous_score > current_score:
            return True
        return any(region.region_type == "main_table" for region in previous_manifest.regions)

    def _current_manifest_has_main_table(self) -> bool:
        return bool(
            self._manifest
            and any(region.region_type == "main_table" for region in self._manifest.regions)
        )

    def _restore_previous_table_template_if_available(self) -> dict[str, Any] | None:
        if self._current_manifest_has_main_table() or not self._history:
            return None
        previous_manifest = self._history[-1][0]
        if not any(region.region_type == "main_table" for region in previous_manifest.regions):
            return None
        try:
            runtime_elements = self._adapter.capture_runtime_elements(previous_manifest)
        except Exception:
            return None
        if _manifest_visibility_score(previous_manifest, runtime_elements) <= 0:
            return None
        return self._restore_previous()

    def _should_auto_restore_previous_template_after_cancel(
        self,
        label: str,
        notifications: list[dict[str, str]],
    ) -> bool:
        if label != "取消" or not self._history:
            return False
        if _has_error_notification(notifications):
            return False
        if self._manifest is None:
            return False
        previous_manifest = self._history[-1][0]
        try:
            runtime_elements = self._adapter.capture_runtime_elements(previous_manifest)
        except Exception:
            return False
        if _manifest_has_visible_action_alias(self._manifest, runtime_elements, {"取消"}):
            return False
        previous_score = _manifest_visibility_score(previous_manifest, runtime_elements)
        if previous_score <= 0:
            return False
        current_score = _manifest_visibility_score(self._manifest, runtime_elements)
        return previous_score >= current_score

    def _should_auto_restore_previous_template_after_confirm(
        self,
        label: str,
        notifications: list[dict[str, str]],
    ) -> bool:
        if label not in {"确定", "确认"} or not self._history:
            return False
        if _has_error_notification(notifications):
            return False
        if self._manifest is None:
            return False
        previous_manifest = self._history[-1][0]
        if not any(region.region_type == "main_table" for region in previous_manifest.regions):
            return False
        try:
            current_runtime_elements = self._adapter.capture_runtime_elements(self._manifest)
        except Exception:
            return False
        if _manifest_has_visible_action_alias(self._manifest, current_runtime_elements, {"取消"}):
            return False
        if self._source in {"toolbar.click", "action.click"} and _manifest_has_visible_editable_form_field_identity(
            self._manifest, current_runtime_elements, include_dialog=True,
        ):
            return False
        try:
            runtime_elements = self._adapter.capture_runtime_elements(previous_manifest)
        except Exception:
            return False
        previous_score = _manifest_visibility_score(previous_manifest, runtime_elements)
        if previous_score <= 0:
            return False
        current_score = _manifest_visibility_score(self._manifest, current_runtime_elements)
        return previous_score > current_score

    def _should_auto_restore_previous_template_after_popup_reference_select(self) -> bool:
        if not self._history or self._manifest is None:
            return False
        if self._source not in {"toolbar.click", "action.click", "table_row_action.click"}:
            return False
        if self._source == "table_row_action.click" and self._last_step_action != "table_row_action.click":
            return False
        stable_form_actions = {"保存", "提交", "取消"}
        previous_manifest = self._history[-1][0]
        try:
            runtime_elements = self._adapter.capture_runtime_elements(previous_manifest)
        except Exception:
            return False
        if _manifest_visible_unshared_action_identity_matches(
            self._manifest,
            previous_manifest,
            runtime_elements,
            stable_form_actions,
        ):
            return False
        if _manifest_has_visible_action_alias(previous_manifest, runtime_elements, stable_form_actions):
            return True
        previous_score = _manifest_visibility_score(previous_manifest, runtime_elements)
        if previous_score <= 0:
            return False
        current_score = _manifest_visibility_score(self._manifest, runtime_elements)
        return previous_score > current_score

    def _form_popup_reference_restore_status(self, *, allow_form_fill: bool = False) -> dict[str, Any]:
        if not self._history or self._manifest is None:
            return {"should_restore": False, "reason": "missing_page_stack_or_current_manifest"}
        if self._source not in {"toolbar.click", "action.click", "dialog.click"} and not (
            allow_form_fill and self._source == "form.fill"
        ):
            return {
                "should_restore": False,
                "reason": "unsupported_template_context",
                "template_context": self._source,
            }
        previous_manifest = self._history[-1][0]
        try:
            runtime_elements = self._adapter.capture_runtime_elements(previous_manifest)
        except Exception as exc:
            return {"should_restore": False, "reason": "capture_runtime_elements_failed", "error": str(exc)}
        stable_form_actions = {"保存", "提交", "取消", "确定", "确认"}
        if allow_form_fill:
            current_stable_actions = _manifest_visible_unshared_action_identity_matches(
                self._manifest,
                previous_manifest,
                runtime_elements,
                stable_form_actions,
            )
        else:
            current_stable_actions = _manifest_visible_action_identity_matches(
                self._manifest,
                runtime_elements,
                stable_form_actions,
            )
        if current_stable_actions:
            return {
                "should_restore": False,
                "reason": "current_template_stable_action_visible",
                "current_page": self._manifest.page.fieldid,
                "previous_page": previous_manifest.page.fieldid,
                "current_stable_actions": current_stable_actions,
            }
        previous_score = _manifest_visibility_score(previous_manifest, runtime_elements)
        if previous_score <= 0:
            return {
                "should_restore": False,
                "reason": "previous_template_not_visible",
                "current_page": self._manifest.page.fieldid,
                "previous_page": previous_manifest.page.fieldid,
                "previous_score": previous_score,
            }
        current_score = _manifest_visibility_score(self._manifest, runtime_elements)
        if allow_form_fill:
            should_restore = previous_score > current_score
            reason = "previous_score_gt_current_score" if should_restore else "previous_score_not_gt_current_score"
        else:
            should_restore = previous_score >= current_score
            reason = "previous_score_gte_current_score" if should_restore else "current_score_higher"
        return {
            "should_restore": should_restore,
            "reason": reason,
            "current_page": self._manifest.page.fieldid,
            "previous_page": previous_manifest.page.fieldid,
            "previous_score": previous_score,
            "current_score": current_score,
        }

    def _should_auto_restore_previous_template_after_dialog_confirm(
        self,
        notifications: list[dict[str, str]],
    ) -> bool:
        if self._source not in {
            "editable_table.add_row",
            "table_row_action.click",
            "toolbar.click",
            "action.click",
            "form.fill",
        }:
            return False
        if not self._history:
            return False
        if _has_error_notification(notifications):
            return False
        previous_manifest = self._history[-1][0]
        if not any(region.region_type == "main_table" for region in previous_manifest.regions):
            return False
        persistent_form_actions = _STABLE_EDIT_ACTION_ALIASES - {"取消"}
        try:
            current_runtime_elements = self._adapter.capture_runtime_elements(self._manifest)
        except Exception:
            current_runtime_elements = []
        if current_runtime_elements and _manifest_has_visible_action_identity(
            self._manifest,
            current_runtime_elements,
            persistent_form_actions,
        ):
            return False
        if current_runtime_elements and _manifest_has_visible_editable_form_field_identity(
            self._manifest,
            current_runtime_elements,
        ):
            return False
        if (
            self._source in {"toolbar.click", "action.click"}
            and current_runtime_elements
            and _manifest_has_visible_editable_form_field_identity(
                self._manifest,
                current_runtime_elements,
                include_dialog=True,
            )
        ):
            return False
        try:
            runtime_elements = self._adapter.capture_runtime_elements(previous_manifest)
        except Exception:
            return False
        previous_score = _manifest_visibility_score(previous_manifest, runtime_elements)
        if previous_score > 0 and _manifest_has_visible_action_identity(
            previous_manifest,
            runtime_elements,
            persistent_form_actions,
        ):
            return True
        if self._source in {"toolbar.click", "form.fill"}:
            current_score = _manifest_visibility_score(self._manifest, current_runtime_elements)
            return previous_score > current_score
        return previous_score > 0

    def _try_restore_previous_template_after_dom_transition(
        self,
        *,
        source: str,
        label: str,
        notifications: list[dict[str, str]],
    ) -> dict[str, Any] | None:
        self._last_dom_transition_restore = None
        if not self._should_restore_previous_template_after_dom_transition(source, label, notifications):
            return None
        return self._restore_previous()

    def _should_restore_previous_template_after_dom_transition(
        self,
        source: str,
        label: str,
        notifications: list[dict[str, str]],
    ) -> bool:
        if source not in {"action.click", "tab.click"} or not self._history:
            self._last_dom_transition_restore = {"checked": False, "reason": "not_applicable"}
            return False
        if _has_error_notification(notifications):
            self._last_dom_transition_restore = {"checked": True, "reason": "error_notification"}
            return False
        if self._manifest is None:
            self._last_dom_transition_restore = {"checked": False, "reason": "missing_current_manifest"}
            return False
        previous_manifest = self._history[-1][0]
        try:
            runtime_elements = self._adapter.capture_runtime_elements(previous_manifest)
        except Exception:
            self._last_dom_transition_restore = {"checked": True, "reason": "capture_failed"}
            return False
        previous_score = _manifest_visibility_score(previous_manifest, runtime_elements)
        current_score = _manifest_visibility_score(self._manifest, runtime_elements)
        evidence: dict[str, Any] = {
            "checked": True,
            "source": source,
            "label": label,
            "previous_page": previous_manifest.page.fieldid,
            "current_page": self._manifest.page.fieldid,
            "previous_score": previous_score,
            "current_score": current_score,
            "return_action_hint": _is_return_action(label, label),
        }
        stable_current_action_visible = _manifest_has_visible_action_identity(
            self._manifest,
            runtime_elements,
            _STABLE_EDIT_ACTION_ALIASES,
        )
        if source == "tab.click" and (
            stable_current_action_visible
            or _manifest_has_visible_editable_form_field_identity(self._manifest, runtime_elements)
        ):
            evidence["reason"] = "current_work_surface_visible"
            self._last_dom_transition_restore = evidence
            return False
        if stable_current_action_visible and previous_score <= current_score:
            evidence["reason"] = "current_stable_action_visible"
            self._last_dom_transition_restore = evidence
            return False
        if previous_score <= 0:
            evidence["reason"] = "previous_not_visible"
            self._last_dom_transition_restore = evidence
            return False
        if previous_score <= current_score:
            evidence["reason"] = "previous_not_stronger"
            self._last_dom_transition_restore = evidence
            return False
        evidence["reason"] = "restore"
        self._last_dom_transition_restore = evidence
        return True

    def _apply_seen_manifest_if_dom_switched(self) -> dict[str, Any] | None:
        if self._manifest is None or not self._seen_manifests:
            return None
        resolve_page_identity = getattr(self._adapter, "visible_page_identity", None)
        if resolve_page_identity is None:
            return None
        current_page = getattr(self._manifest.page, "fieldid", "")
        page_fieldids = [
            current_page,
            *(
                getattr(getattr(manifest, "page", None), "fieldid", "")
                for manifest in self._seen_manifests
            ),
        ]
        try:
            visible_page = resolve_page_identity([fieldid for fieldid in page_fieldids if fieldid])
        except Exception:
            return None
        for manifest in reversed(self._seen_manifests):
            page = getattr(manifest, "page", None)
            if page is not None and getattr(page, "fieldid", "") == current_page:
                continue
            if page is None or getattr(page, "fieldid", "") != visible_page:
                continue
            try:
                runtime_elements = self._adapter.capture_runtime_elements(manifest)
            except Exception:
                continue
            candidate_binding = bind_manifest(manifest, runtime_elements)
            current_binding = bind_manifest(self._manifest, runtime_elements)
            candidate_score = _manifest_visibility_score(manifest, runtime_elements)
            current_score = _manifest_visibility_score(self._manifest, runtime_elements)
            candidate_field_count = len(candidate_binding.bound_fields)
            current_field_count = len(current_binding.bound_fields)
            if candidate_score <= 0:
                continue
            if candidate_score < current_score:
                continue
            if candidate_score == current_score and candidate_field_count <= current_field_count:
                continue
            if self._manifest is not None:
                self._history.append((self._manifest, self._source))
            self._manifest = manifest
            self._source = "dom_switched"
            self._adapter.prepare_binding(self._manifest)
            self._page_state = self._adapter.capture_page_state()
            self._binding = candidate_binding
            return {
                "page": self._manifest.page.fieldid,
                "bound_action_count": len(self._binding.bound_actions),
                "bound_field_count": len(self._binding.bound_fields),
            }
        return None


_RETURN_ACTION_FIELDIDS = {"pageHeader_return", "ymbtl_backup"}
_RETURN_ACTION_LABELS = {"返回", "返回列表"}
_STABLE_EDIT_ACTION_ALIASES = {"取消", "保存", "提交", "保存并提交", "暂存"}


def _has_error_notification(notifications: list[dict[str, str]]) -> bool:
    return any(
        item.get("type") == "error" or "未通过" in str(item.get("message") or "") or "失败" in str(item.get("message") or "")
        for item in notifications
    )


def _manifest_visibility_score(manifest, runtime_elements: list[dict[str, Any]]) -> int:
    binding = bind_manifest(manifest, runtime_elements)
    score = len(binding.bound_fields) + len(binding.bound_actions)
    runtime_fieldids = {str(item.get("fieldid") or "") for item in runtime_elements if item.get("visible", True)}
    runtime_texts = {
        str(item.get(key) or "")
        for item in runtime_elements
        if item.get("visible", True)
        for key in ("text", "label_text", "placeholder", "aria_label", "title_attr", "value")
    }
    for candidate in [*manifest.table_columns, *manifest.trees]:
        if candidate.fieldid and candidate.fieldid in runtime_fieldids:
            score += 1
        elif candidate.label and candidate.label in runtime_texts:
            score += 1
    return score


def _manifest_has_visible_action_alias(
    manifest,
    runtime_elements: list[dict[str, Any]],
    aliases: set[str],
) -> bool:
    binding = bind_manifest(manifest, runtime_elements)
    for bound in binding.bound_actions:
        if aliases.intersection(bound.candidate.aliases()):
            return True
    return False


def _manifest_has_visible_action_identity(
    manifest,
    runtime_elements: list[dict[str, Any]],
    aliases: set[str],
) -> bool:
    return bool(_manifest_visible_action_identity_matches(manifest, runtime_elements, aliases))


def _manifest_has_visible_editable_form_field_identity(
    manifest, runtime_elements: list[dict[str, Any]], *, include_dialog: bool = False,
) -> bool:
    binding = bind_manifest(manifest, runtime_elements)
    region_types = {region.key: region.region_type for region in manifest.regions}
    region_types.update({region.fieldid: region.region_type for region in manifest.regions})
    for bound in binding.bound_fields:
        if not {
            "fieldid",
            "runtime_fieldid",
            "template_key",
            "data_field",
            "data_field:name",
            "id",
            "platform_identity",
        }.intersection(
            bound.reasons
        ):
            continue
        region_type = region_types.get(bound.candidate.region_key or "") or region_types.get(
            bound.candidate.region_fieldid or ""
        )
        if region_type in {"main_table", "query_box"}:
            continue
        if getattr(bound.runtime, "in_table", False):
            continue
        if getattr(bound.runtime, "in_dialog", False) and not include_dialog:
            continue
        if getattr(bound.runtime, "disabled", False) or getattr(bound.runtime, "readonly", False):
            continue
        return True
    return False


def _manifest_visible_action_identity_matches(
    manifest,
    runtime_elements: list[dict[str, Any]],
    aliases: set[str],
) -> list[dict[str, Any]]:
    def is_action_like(item: dict[str, Any]) -> bool:
        text_values = {
            str(item.get(key) or "").strip()
            for key in ("text", "label_text", "aria_label", "title_attr", "value")
        }
        text_values.discard("")
        if aliases.intersection(text_values):
            return True
        role = str(item.get("role") or "").strip().lower()
        if role in {"button", "menuitem", "option", "link"}:
            return True
        tag_name = str(item.get("tag_name") or "").strip().lower()
        return tag_name in {"button", "a"}

    matches: list[dict[str, Any]] = []
    for action in manifest.actions:
        if not aliases.intersection(action.aliases()):
            continue
        action_ids = {
            str(value)
            for value in (
                action.fieldid,
                action.key,
                action.data_field or "",
                action.rightflag or "",
                *action.action_keys,
            )
            if value
        }
        if not action_ids:
            continue
        for item in runtime_elements:
            if not item.get("visible", True) or not is_action_like(item):
                continue
            runtime_ids = {str(item.get(key) or "") for key in ("fieldid", "id", "name")}
            runtime_ids.discard("")
            if not runtime_ids.intersection(action_ids):
                continue
            text_values = {
                str(item.get(key) or "").strip()
                for key in ("text", "label_text", "aria_label", "title_attr", "value")
            }
            text_values.discard("")
            if aliases.intersection(text_values):
                matches.append(
                    {
                        "label": action.label,
                        "fieldid": action.fieldid,
                        "matched_ids": sorted(runtime_ids.intersection(action_ids)),
                        "matched_text": sorted(aliases.intersection(text_values)),
                    }
                )
                break
    return matches


def _manifest_visible_unshared_action_identity_matches(
    manifest,
    previous_manifest,
    runtime_elements: list[dict[str, Any]],
    aliases: set[str],
) -> list[dict[str, Any]]:
    previous_ids = {
        str(action.fieldid)
        for action in previous_manifest.actions
        if aliases.intersection(action.aliases())
        if action.fieldid
    }
    return [
        match
        for match in _manifest_visible_action_identity_matches(manifest, runtime_elements, aliases)
        if not set(match.get("matched_ids") or []).intersection(previous_ids)
    ]


def _is_return_action(fieldid: str, label: str) -> bool:
    return fieldid in _RETURN_ACTION_FIELDIDS or label in _RETURN_ACTION_LABELS


def _tab_content_fieldid(fieldid: str) -> str:
    value = str(fieldid or "").strip()
    if value.endswith("_tab"):
        return value[:-4]
    return value
