from __future__ import annotations

import re

from .models import BindingResult, BoundElement, ElementCandidate, PageManifest, RuntimeElement
from .platform_rendering_contract import build_contract_path


def bind_manifest(manifest: PageManifest, runtime_elements: list[dict]) -> BindingResult:
    runtime = [_coerce_runtime_element(item) for item in runtime_elements]
    result = BindingResult(manifest=manifest)
    query_field_ids = {id(candidate) for candidate in manifest.query_fields}
    for candidate in [*manifest.fields, *manifest.query_fields]:
        bound = _bind_candidate(candidate, runtime)
        if bound is None:
            result.missing_fields.append(candidate.label or candidate.fieldid)
            if (
                candidate.element_type == "formItem"
                and id(candidate) not in query_field_ids
                and _has_exact_identity_conflict(candidate, runtime)
            ):
                path = build_contract_path("incompatible", [_contract_rule_for_candidate(candidate)])
                for alias in candidate.aliases():
                    result.incompatible_fields[alias] = path
        else:
            result.bound_fields.append(bound)
    for candidate in manifest.actions:
        bound = _bind_candidate(candidate, runtime)
        if bound is None:
            result.missing_actions.append(candidate.label or candidate.fieldid)
        else:
            result.bound_actions.append(bound)
    for candidate in manifest.tabs:
        bound = _bind_candidate(candidate, runtime)
        if bound is None:
            result.missing_tabs.append(candidate.label or candidate.fieldid)
        else:
            result.bound_tabs.append(bound)
    return result


def bind_runtime_form_field(name: str, runtime_elements: list[dict]) -> BoundElement | None:
    runtime = [_coerce_runtime_element(item) for item in runtime_elements]
    scored: list[tuple[tuple[int, int, int, float], float, RuntimeElement, list[str]]] = []
    for item in runtime:
        if not _runtime_form_field_is_eligible(item):
            continue
        score, reasons = _score_runtime_form_field(name, item)
        if score <= 0:
            continue
        scored.append((_runtime_form_field_priority(item, score), score, item, reasons))
    if not scored:
        return None
    _priority, score, item, reasons = min(scored, key=lambda candidate: candidate[0])
    label = str(name)
    runtime_key = f"runtime:{label}"
    return BoundElement(
        candidate=ElementCandidate(
            key=runtime_key,
            fieldid=runtime_key,
            label=label,
            title=label,
            region_key=None,
            region_fieldid=None,
            element_type="formItem",
            component_name=_runtime_component_name(item),
            data_field=item.name or item.id,
            raw={"runtime_only": True},
        ),
        runtime=item,
        confidence=score,
        reasons=reasons,
        contract_path=build_contract_path("unverified", ["PRS-FORM-001"], "exact_identity_unavailable"),
    )


def bind_runtime_readable_form_field(
    candidates: list[ElementCandidate],
    runtime_elements: list[dict],
) -> BoundElement | None:
    runtime = [_coerce_runtime_element(item) for item in runtime_elements]
    foreground_exists = any(item.visible and item.in_dialog for item in runtime)
    for candidate in candidates:
        exact = [
            item
            for item in runtime
            if item.fieldid in _verified_runtime_fieldids(candidate) and item.visible
        ]
        if foreground_exists:
            exact = [item for item in exact if item.in_dialog]
        roots = {item.identity_root for item in exact}
        if len(exact) > 1 and len(roots) == 1 and None not in roots:
            owners = [item for item in exact if item.is_identity_root]
            controls = [item for item in runtime if item.visible and item.identity_root in roots
                        and _runtime_is_direct_control(candidate, item)]
            if len(owners) == 1 and not controls:
                exact = owners
        if len(exact) == 1:
            return BoundElement(
                candidate=candidate,
                runtime=exact[0],
                confidence=1.0,
                reasons=["platform_identity", "read_only_assertion"],
                contract_path=build_contract_path(
                    "unverified", ["PRS-FORM-001"], "component_variant_unverified"
                ),
            )
    return None


def _coerce_runtime_element(item: dict) -> RuntimeElement:
    return RuntimeElement(
        fieldid=item.get("fieldid"),
        id=item.get("id"),
        name=item.get("name"),
        placeholder=item.get("placeholder"),
        text=item.get("text"),
        role=item.get("role"),
        tag_name=item.get("tag_name"),
        visible=bool(item.get("visible", True)),
        selector=item.get("selector") or "",
        label_text=item.get("label_text"),
        aria_label=item.get("aria_label"),
        title_attr=item.get("title_attr"),
        value=item.get("value"),
        in_dialog=bool(item.get("in_dialog", False)),
        in_table=bool(item.get("in_table", False)),
        disabled=bool(item.get("disabled", False)),
        readonly=bool(item.get("readonly", False)),
        editable=item.get("editable") if item.get("editable") is None else bool(item.get("editable")),
        pointer_receivable=(
            item.get("pointer_receivable")
            if item.get("pointer_receivable") is None
            else bool(item.get("pointer_receivable"))
        ),
        identity_root=item.get("identity_root"),
        is_identity_root=bool(item.get("is_identity_root", False)),
        class_name=item.get("class_name"),
    )


def _runtime_form_field_is_eligible(runtime: RuntimeElement) -> bool:
    if not runtime.visible or runtime.in_table or runtime.disabled or runtime.readonly:
        return False
    if _runtime_checkbox_is_table_or_tree(runtime):
        return False
    if runtime.editable is False:
        return False
    role = str(runtime.role or "").lower()
    tag_name = str(runtime.tag_name or "").lower()
    if runtime.editable is True:
        return True
    return tag_name in {"input", "textarea", "select"} or role in {"textbox", "combobox", "listbox", "switch"}


def _score_runtime_form_field(name: str, runtime: RuntimeElement) -> tuple[float, list[str]]:
    expected = _normalize_label(name)
    if not expected:
        return 0.0, []
    score = 0.0
    reasons: list[str] = []
    for attr, exact_score, normalized_score in (
        ("label_text", 0.95, 0.93),
        ("aria_label", 0.9, 0.88),
        ("placeholder", 0.86, 0.84),
        ("text", 0.8, 0.78),
        ("title_attr", 0.78, 0.76),
        ("value", 0.68, 0.66),
    ):
        value = getattr(runtime, attr)
        if not value:
            continue
        if str(value) == str(name):
            score = max(score, exact_score)
            reasons.append(attr)
            continue
        if _normalize_label(value) == expected:
            score = max(score, normalized_score)
            reasons.append(f"{attr}:normalized")
    return score, reasons


def _runtime_form_field_priority(runtime: RuntimeElement, score: float) -> tuple[int, int, int, float]:
    dialog_rank = 0 if runtime.visible and runtime.in_dialog else 1
    editable_rank = 0 if runtime.editable is True else 1
    control_rank = 0 if (
        str(runtime.role or "").lower() in {"textbox", "combobox", "listbox", "switch"}
        or str(runtime.tag_name or "").lower() in {"input", "textarea", "select"}
        or _runtime_component_name(runtime) == "RuntimeSelect"
    ) else 1
    return (control_rank, dialog_rank, editable_rank, -score)


def _runtime_component_name(runtime: RuntimeElement) -> str:
    role = str(runtime.role or "").lower()
    tag_name = str(runtime.tag_name or "").lower()
    if role == "switch":
        return "RuntimeSwitch"
    if role in {"combobox", "listbox"} or tag_name == "select" or set(
        str(runtime.class_name or "").split()
    ) & {"ant-select", "wui-select", "w-select", "u-select"}:
        return "RuntimeSelect"
    if tag_name == "textarea":
        return "RuntimeTextarea"
    return "RuntimeInput"


def _bind_candidate(candidate: ElementCandidate, runtime_elements: list[RuntimeElement]) -> BoundElement | None:
    verified_ids = _verified_runtime_fieldids(candidate)
    exact_matches = [item for item in runtime_elements if item.fieldid in verified_ids]
    if exact_matches:
        if any(item.visible and item.in_dialog for item in runtime_elements) and not any(
            item.visible and item.in_dialog for item in exact_matches
        ):
            return None
        eligible = [item for item in exact_matches if _platform_identity_is_eligible(candidate, item)]
        eligible = _collapse_same_root_exact_matches(candidate, eligible, runtime_elements)
        if len(eligible) != 1:
            return None
        if candidate.element_type == "formItem" and eligible[0].pointer_receivable is not True:
            return BoundElement(
                candidate=candidate,
                runtime=eligible[0],
                confidence=0.99,
                reasons=["platform_identity", "pointer_receivability_unknown"],
                contract_path=build_contract_path(
                    "unverified", ["PRS-FORM-001"], "component_variant_unverified"
                ),
            )
        return BoundElement(
            candidate=candidate,
            runtime=eligible[0],
            confidence=1.0,
            reasons=["platform_identity"],
            contract_path=build_contract_path("verified", [_contract_rule_for_candidate(candidate)]),
        )
    scored: list[tuple[float, RuntimeElement, list[str]]] = []
    for runtime in runtime_elements:
        if not runtime.visible:
            continue
        score, reasons = _score_candidate(candidate, runtime)
        if score <= 0:
            continue
        scored.append((score, runtime, reasons))
    if not scored:
        return None
    if candidate.element_type == "formItem":
        score, runtime, reasons = min(scored, key=lambda item: _form_candidate_priority(item[1], item[0]))
    else:
        score, runtime, reasons = max(scored, key=lambda item: item[0])
    contract_path = None
    if candidate.element_type == "formItem":
        contract_path = build_contract_path("unverified", ["PRS-FORM-001"], "exact_identity_unavailable")
    return BoundElement(
        candidate=candidate,
        runtime=runtime,
        confidence=score,
        reasons=reasons,
        contract_path=contract_path,
    )


def _has_exact_identity_conflict(candidate: ElementCandidate, runtime_elements: list[RuntimeElement]) -> bool:
    exact_matches = [item for item in runtime_elements if item.fieldid in _verified_runtime_fieldids(candidate)]
    if not exact_matches:
        return False
    if any(item.visible and item.in_dialog for item in runtime_elements) and not any(
        item.visible and item.in_dialog for item in exact_matches
    ):
        return True
    eligible = [item for item in exact_matches if _platform_identity_is_eligible(candidate, item)]
    return len(_collapse_same_root_exact_matches(candidate, eligible, runtime_elements)) != 1


def _collapse_same_root_exact_matches(
    candidate: ElementCandidate,
    matches: list[RuntimeElement],
    runtime_elements: list[RuntimeElement],
) -> list[RuntimeElement]:
    if not matches:
        return matches
    fieldids = {str(item.fieldid or "").strip() for item in matches}
    if len(fieldids) != 1 or not next(iter(fieldids)):
        return matches
    controls = [item for item in matches if _runtime_is_direct_control(candidate, item)]
    identity_roots = {item.identity_root for item in matches}
    if len(identity_roots) > 1:
        return matches
    identity_root = next(iter(identity_roots)) if len(identity_roots) == 1 else None
    if len(controls) > 1 and not identity_root:
        return controls
    if identity_root:
        foreground_exists = any(item.visible and item.in_dialog for item in runtime_elements)
        descendant_controls = [
            item
            for item in runtime_elements
            if item.identity_root == identity_root
            and item.fieldid in candidate.runtime_fieldids
            and item.fieldid not in fieldids
            and _runtime_is_direct_control(candidate, item)
            and _platform_identity_is_eligible(candidate, item)
            and (not foreground_exists or item.in_dialog)
        ]
        controls.extend(descendant_controls)
        if not controls and str(candidate.component_name or "").lower() == "ydfselect":
            visible_controls = [
                item for item in runtime_elements
                if item.identity_root == identity_root and item.visible and _runtime_is_direct_control(candidate, item)
            ]
            if (
                len(visible_controls) == 1
                and visible_controls[0].tag_name == "input"
                and visible_controls[0].role == "combobox"
                and visible_controls[0].readonly
                and not visible_controls[0].disabled
            ):
                # A closed select's readonly search input still permits choice clicks on its root.
                return [item for item in matches if item.is_identity_root]
        if not controls and str(candidate.component_name or "").lower() == "ydfdatepicker":
            return [
                item
                for item in matches
                if "ydf-date-picker" in str(item.class_name or "").split()
                and item.visible
                and item.pointer_receivable is True
            ]
    non_button_controls = [item for item in controls if str(item.tag_name or "").lower() != "button"]
    if len(non_button_controls) == 1:
        return non_button_controls
    if len(controls) == 1:
        return controls
    if controls:
        return controls
    containers = [item for item in matches if not _runtime_is_direct_control(candidate, item)]
    return containers if len(containers) == 1 else matches


def _runtime_is_direct_control(candidate: ElementCandidate, runtime: RuntimeElement) -> bool:
    tag_name = str(runtime.tag_name or "").lower()
    return tag_name in {"input", "textarea", "select"} or str(runtime.role or "").lower() in {
        "textbox",
        "combobox",
        "listbox",
        "switch",
        "checkbox",
    } or (tag_name == "button" and str(candidate.component_name or "").lower() == "ydfswitch") or (
        tag_name == "button"
        and str(candidate.component_name or "").lower().replace("-", "").replace("_", "")
        in {"ydftablemodalselect", "ydftreemodalselect"}
    )


def _verified_runtime_fieldids(candidate: ElementCandidate) -> list[str]:
    if candidate.verified_runtime_fieldids:
        return list(candidate.verified_runtime_fieldids)
    if candidate.element_type == "formItem" and (not candidate.raw or candidate.raw.get("divCode")):
        return [candidate.fieldid] if candidate.fieldid else []
    return []


def _platform_identity_is_eligible(candidate: ElementCandidate, runtime: RuntimeElement) -> bool:
    if (
        str(runtime.tag_name or "").lower() == "button"
        and str(candidate.component_name or "").lower().replace("-", "").replace("_", "")
        in {"ydftablemodalselect", "ydftreemodalselect"}
    ):
        return bool(runtime.visible and not runtime.disabled and runtime.pointer_receivable is True)
    if not runtime.visible or runtime.disabled or runtime.readonly or runtime.editable is False:
        return False
    if runtime.pointer_receivable is False:
        return False
    if candidate.element_type == "formItem":
        return _runtime_form_field_is_eligible(runtime)
    return True


def _contract_rule_for_candidate(candidate: ElementCandidate) -> str:
    if candidate.element_type == "table_column":
        return "PRS-TABLE-001"
    return "PRS-FORM-001"


def _form_candidate_priority(runtime: RuntimeElement, score: float) -> tuple[int, float, int, int]:
    editable_rank = _runtime_editable_rank(runtime)
    dialog_rank = 0 if runtime.in_dialog and editable_rank == 0 else 1
    table_rank = 1 if runtime.in_table else 0
    return (dialog_rank, -score, editable_rank, table_rank)


def _runtime_editable_rank(runtime: RuntimeElement) -> int:
    if runtime.disabled or runtime.readonly or runtime.editable is False:
        return 1
    if runtime.editable is True:
        return 0
    role = str(runtime.role or "").lower()
    tag_name = str(runtime.tag_name or "").lower()
    return 0 if role in {"textbox", "combobox", "listbox", "switch"} or tag_name in {"input", "textarea", "select"} else 1


def _score_candidate(candidate: ElementCandidate, runtime: RuntimeElement) -> tuple[float, list[str]]:
    if _runtime_checkbox_is_table_or_tree(runtime) and _is_checkbox_form_candidate(candidate):
        return 0.0, []
    if _is_background_table_runtime_for_form_candidate(candidate, runtime):
        return 0.0, []
    score = 0.0
    reasons: list[str] = []
    candidate_label = _normalize_label(candidate.label)
    runtime_text = _normalize_label(runtime.text)
    runtime_placeholder = _normalize_label(runtime.placeholder)
    runtime_label_text = _normalize_label(runtime.label_text)
    runtime_aria_label = _normalize_label(runtime.aria_label)
    runtime_title = _normalize_label(runtime.title_attr)
    runtime_value = _normalize_label(runtime.value)
    if candidate.fieldid and candidate.fieldid == runtime.fieldid:
        score = 1.0
        reasons.append("fieldid")
    if runtime.fieldid and runtime.fieldid in set(candidate.runtime_fieldids or []):
        score = max(score, 0.99)
        reasons.append("runtime_fieldid")
    if candidate.key and candidate.key == runtime.fieldid:
        score = max(score, 0.98)
        reasons.append("template_key")
    if candidate.label and runtime.text and candidate.label == runtime.text:
        score = max(score, 0.9)
        reasons.append("label")
    if candidate_label and runtime_text and candidate_label == runtime_text:
        score = max(score, 0.88)
        reasons.append("label:normalized")
    if candidate.data_field and runtime.id and candidate.data_field == runtime.id:
        score = max(score, 0.75)
        reasons.append("data_field")
    if candidate.data_field and runtime.name and candidate.data_field == runtime.name:
        score = max(score, 0.82)
        reasons.append("data_field:name")
    if candidate.fieldid and runtime.id and candidate.fieldid == runtime.id:
        score = max(score, 0.85)
        reasons.append("id")
    if candidate.label and runtime.placeholder and candidate.label == runtime.placeholder:
        score = max(score, 0.8)
        reasons.append("placeholder")
    if candidate_label and runtime_placeholder and candidate_label == runtime_placeholder:
        score = max(score, 0.79)
        reasons.append("placeholder:normalized")
    if candidate.label and runtime.label_text and candidate.label == runtime.label_text:
        score = max(score, 0.82)
        reasons.append("label_text")
    if candidate_label and runtime_label_text and candidate_label == runtime_label_text:
        score = max(score, 0.81)
        reasons.append("label_text:normalized")
    if candidate.label and runtime.aria_label and candidate.label == runtime.aria_label:
        score = max(score, 0.82)
        reasons.append("aria_label")
    if candidate_label and runtime_aria_label and candidate_label == runtime_aria_label:
        score = max(score, 0.81)
        reasons.append("aria_label:normalized")
    if candidate.label and runtime.title_attr and candidate.label == runtime.title_attr:
        score = max(score, 0.8)
        reasons.append("title_attr")
    if candidate_label and runtime_title and candidate_label == runtime_title:
        score = max(score, 0.79)
        reasons.append("title_attr:normalized")
    if candidate.label and runtime.value and candidate.label == runtime.value:
        score = max(score, 0.7)
        reasons.append("value")
    if candidate_label and runtime_value and candidate_label == runtime_value:
        score = max(score, 0.69)
        reasons.append("value:normalized")
    if candidate.label and runtime.text and _is_loose_label_match(candidate.label, runtime.text):
        score = max(score, 0.7)
        reasons.append("label:contains")
    if _label_text_only_match_conflicts(candidate, runtime, reasons):
        return 0.0, []
    return score, reasons


def _label_text_only_match_conflicts(candidate: ElementCandidate, runtime: RuntimeElement, reasons: list[str]) -> bool:
    if candidate.element_type != "formItem":
        return False
    if not reasons or any(not reason.startswith("label_text") for reason in reasons):
        return False
    expected = _normalize_label(candidate.label)
    if not expected:
        return False
    for value in (runtime.text, runtime.name):
        actual = _normalize_label(value)
        if actual and actual != expected:
            return True
    return False


def _is_background_table_runtime_for_form_candidate(candidate: ElementCandidate, runtime: RuntimeElement) -> bool:
    if candidate.element_type != "formItem" or not runtime.in_table:
        return False
    if _is_checkbox_form_candidate(candidate) and _is_runtime_checkbox(runtime):
        return True
    if candidate.fieldid and candidate.fieldid == runtime.fieldid:
        return False
    if candidate.key and candidate.key == runtime.fieldid:
        return False
    if candidate.data_field and candidate.data_field in {runtime.id, runtime.name}:
        return False
    return True


def _is_checkbox_form_candidate(candidate: ElementCandidate) -> bool:
    if candidate.element_type != "formItem":
        return False
    component_name = str(candidate.component_name or "").lower().replace("-", "").replace("_", "")
    return "checkbox" in component_name


def _is_runtime_checkbox(runtime: RuntimeElement) -> bool:
    role = str(runtime.role or "").lower()
    tag_name = str(runtime.tag_name or "").lower()
    selector = str(runtime.selector or "").lower()
    if role == "checkbox":
        return True
    return tag_name == "input" and "checkbox" in selector


def _runtime_checkbox_is_table_or_tree(runtime: RuntimeElement) -> bool:
    if not _is_runtime_checkbox(runtime):
        return False
    selector = str(runtime.selector or "").lower()
    return bool(runtime.in_table) or "tree" in selector


def _is_loose_label_match(expected: str, actual: str) -> bool:
    if not expected or not actual or expected == actual:
        return False
    if expected not in actual:
        return False
    remainder = actual.replace(expected, "")
    return not any(char.isalnum() or "\u4e00" <= char <= "\u9fff" for char in remainder)


def _normalize_label(value: str | None) -> str:
    if not value:
        return ""
    normalized = re.sub(r"[（(].*?[）)]", "", value)
    normalized = re.sub(r"\s+", "", normalized).strip()
    return normalized.lstrip("*＊").rstrip(":：")
