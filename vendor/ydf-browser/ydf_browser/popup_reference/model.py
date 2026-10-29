from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable, Literal, Mapping


ReferenceSourceKind = Literal["form", "query", "editable_table"]
PopupReferenceCompletion = Literal[
    "confirmed",
    "auto_closed_backfilled",
    "caller_verification_required",
]


class PopupReferenceStage(StrEnum):
    RECOGNIZE_ORIGIN = "recognize_origin"
    RESOLVE_OWNER = "resolve_owner"
    OPEN_SURFACE = "open_surface"
    RESOLVE_SURFACE = "resolve_surface"
    APPLY_CONTEXT = "apply_context"
    FILTER_CANDIDATES = "filter_candidates"
    SELECT_CANDIDATE = "select_candidate"
    VERIFY_SELECTION = "verify_selection"
    CONFIRM = "confirm"
    VERIFY_COMPLETION = "verify_completion"
    WRITE_EVIDENCE = "write_evidence"


@dataclass(frozen=True, slots=True)
class ReferenceOwnerIdentity:
    """Stable identity used to re-resolve a reference owner at execution time."""

    selector: str
    fieldid: str = ""
    label: str = ""
    contract_verified: bool = False
    fallback_selector: str = ""

    @classmethod
    def from_locator(
        cls,
        locator: Any,
        *,
        fieldid: str = "",
        label: str = "",
        contract_verified: bool = False,
        fallback_selector: str = "",
    ) -> ReferenceOwnerIdentity:
        selector = fallback_selector
        try:
            attributes = locator.evaluate(
                """(node) => ({
                    id: node.getAttribute('id') || '',
                    fieldid: node.getAttribute('fieldid') || '',
                    dataFieldid: node.getAttribute('data-fieldid') || '',
                    uikey: node.getAttribute('uikey') || '',
                })"""
            )
            if isinstance(attributes, dict):
                for attribute, key in (
                    ("id", "id"),
                    ("fieldid", "fieldid"),
                    ("data-fieldid", "dataFieldid"),
                    ("uikey", "uikey"),
                ):
                    value = str(attributes.get(key) or "").strip()
                    if value:
                        selector = f"[{attribute}={json.dumps(value, ensure_ascii=False)}]"
                        break
            if selector:
                position = locator.evaluate(
                    """(node, selector) => {
                        const matches = Array.from(document.querySelectorAll(selector));
                        return {index: matches.indexOf(node), count: matches.length};
                    }""",
                    selector,
                )
                if isinstance(position, dict):
                    match_count = int(position.get("count") or 0)
                    match_index = int(position.get("index", -1))
                    if match_count > 1 and match_index >= 0:
                        selector = f":nth-match({selector}, {match_index + 1})"
        except Exception:
            if not fallback_selector:
                raise RuntimeError(f"无法固定弹出参照来源字段身份: {fieldid or label}")
            selector = fallback_selector
        if not selector:
            raise RuntimeError(f"无法固定弹出参照来源字段身份: {fieldid or label}")
        return cls(
            selector=selector,
            fieldid=fieldid,
            label=label,
            contract_verified=contract_verified,
            fallback_selector=(fallback_selector if fallback_selector != selector else ""),
        )


@dataclass(frozen=True, slots=True)
class BoundReferenceSource:
    kind: ReferenceSourceKind
    identity: ReferenceOwnerIdentity


@dataclass(frozen=True, slots=True)
class OpenReferenceSource:
    kind: Literal["open_surface"] = "open_surface"


@dataclass(frozen=True, slots=True)
class PopupReferenceRequest:
    source: BoundReferenceSource | OpenReferenceSource
    target: object
    deadline: float | None = None
    cancelled: Callable[[], bool] | None = None
    title: str | None = None
    confirm: bool = True

    @classmethod
    def from_bound_target(
        cls,
        *,
        source_kind: ReferenceSourceKind,
        identity: ReferenceOwnerIdentity,
        target: object,
        deadline: float | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> PopupReferenceRequest:
        return cls(
            source=BoundReferenceSource(kind=source_kind, identity=identity),
            target=target,
            deadline=deadline,
            cancelled=cancelled,
        )

    @classmethod
    def from_open_surface(
        cls,
        *,
        target: object,
        title: str | None = None,
        confirm: bool = True,
        deadline: float | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> PopupReferenceRequest:
        return cls(
            source=OpenReferenceSource(),
            target=target,
            deadline=deadline,
            cancelled=cancelled,
            title=title,
            confirm=confirm,
        )


@dataclass(frozen=True, slots=True)
class PopupReferenceResult:
    selected: tuple[Mapping[str, object], ...]
    confirmed: bool
    confirm_label: str | None = None
    close_action: str | None = None
    root_backfilled: bool | None = None
    dialog_hidden: bool | None = None
    completion: PopupReferenceCompletion = "confirmed"
    popup_tab_context: tuple[Mapping[str, object], ...] | None = None
    popup_tree_context: tuple[Mapping[str, object], ...] | None = None
    contract_path: Mapping[str, object] | None = None
    diagnostic_refs: tuple[str, ...] = ()
    details: Mapping[str, object] = field(default_factory=dict)

    def to_runtime_dict(self) -> dict[str, Any]:
        if self.details.get("_suppress_report"):
            return {}
        result: dict[str, Any] = {
            "selected": [dict(item) for item in self.selected],
            "confirmed": self.confirmed,
        }
        for key, value in (
            ("confirm_label", self.confirm_label),
            ("close_action", self.close_action),
            ("root_backfilled", self.root_backfilled),
            ("dialog_hidden", self.dialog_hidden),
        ):
            if value is not None:
                result[key] = value
        if self.popup_tab_context:
            result["popup_tab_context"] = [dict(item) for item in self.popup_tab_context]
        if self.popup_tree_context:
            result["popup_tree_context"] = [dict(item) for item in self.popup_tree_context]
        if self.contract_path is not None:
            result["contract_path"] = dict(self.contract_path)
        if self.diagnostic_refs:
            result["diagnostic_refs"] = list(self.diagnostic_refs)
        result.update(
            {key: value for key, value in self.details.items() if not str(key).startswith("_")}
        )
        return result


class PopupReferenceError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        stage: PopupReferenceStage,
        reason: str,
        evidence: Mapping[str, object] | None = None,
        diagnostic_refs: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.reason = reason
        self.evidence = dict(evidence or {})
        self.diagnostic_refs = tuple(diagnostic_refs)
