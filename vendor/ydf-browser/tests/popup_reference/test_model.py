from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

import ydf_browser.popup_reference as popup_reference_module
from ydf_browser.popup_reference import (
    BoundReferenceSource,
    OpenReferenceSource,
    PopupReferenceError,
    PopupReferenceRequest,
    PopupReferenceResult,
    PopupReferenceStage,
    ReferenceOwnerIdentity,
)


def test_package_exports_only_the_public_interface() -> None:
    assert set(popup_reference_module.__all__) == {
        "BoundReferenceSource",
        "OpenReferenceSource",
        "PopupReference",
        "PopupReferenceError",
        "PopupReferenceRequest",
        "PopupReferenceResult",
        "PopupReferenceStage",
        "ReferenceOwnerIdentity",
    }


def test_bound_request_keeps_stable_owner_identity() -> None:
    identity = ReferenceOwnerIdentity(
        selector='[fieldid="bank_input"]',
        fieldid="bank",
        label="开户银行",
    )

    request = PopupReferenceRequest.from_bound_target(
        source_kind="form",
        identity=identity,
        target={"match": {"column": "银行名称", "equals": "中信银行"}},
        deadline=42.0,
    )

    assert request == PopupReferenceRequest(
        source=BoundReferenceSource(kind="form", identity=identity),
        target={"match": {"column": "银行名称", "equals": "中信银行"}},
        deadline=42.0,
        cancelled=None,
        title=None,
        confirm=True,
    )
    with pytest.raises(FrozenInstanceError):
        request.deadline = 43.0  # type: ignore[misc]


def test_locator_identity_keeps_semantic_fallback_for_rerender() -> None:
    class Locator:
        def evaluate(self, _script: str, *args: object) -> object:
            if args:
                return {"index": 1, "count": 2}
            return {"id": "", "fieldid": "bank", "dataFieldid": "", "uikey": ""}

    identity = ReferenceOwnerIdentity.from_locator(
        Locator(),
        fieldid="bank",
        fallback_selector='[fieldid="bank_input"]',
    )

    assert identity.selector == ':nth-match([fieldid="bank"], 2)'
    assert identity.fallback_selector == '[fieldid="bank_input"]'


def test_open_surface_request_has_no_owner_identity() -> None:
    request = PopupReferenceRequest.from_open_surface(
        target={"first_available": True},
        title="选择银行",
        confirm=False,
    )

    assert request.source == OpenReferenceSource()
    assert request.title == "选择银行"
    assert request.confirm is False


def test_result_maps_to_existing_runtime_report_shape() -> None:
    result = PopupReferenceResult(
        selected=({"match": {"column": "银行名称", "equals": "中信银行"}},),
        confirmed=True,
        confirm_label="确定",
        close_action="confirm",
        root_backfilled=True,
        dialog_hidden=True,
        completion="confirmed",
        popup_tab_context=({"label": "银行"},),
        popup_tree_context=None,
        contract_path={
            "contract_version": "1.0.1",
            "applicability": "verified",
            "rule_ids": ["PRS-POPUP-001", "PRS-POPUP-002"],
            "fallback_reason": None,
        },
        diagnostic_refs=("/tmp/popup.json",),
    )

    assert result.to_runtime_dict() == {
        "selected": [{"match": {"column": "银行名称", "equals": "中信银行"}}],
        "confirmed": True,
        "confirm_label": "确定",
        "close_action": "confirm",
        "root_backfilled": True,
        "dialog_hidden": True,
        "popup_tab_context": [{"label": "银行"}],
        "contract_path": {
            "contract_version": "1.0.1",
            "applicability": "verified",
            "rule_ids": ["PRS-POPUP-001", "PRS-POPUP-002"],
            "fallback_reason": None,
        },
        "diagnostic_refs": ["/tmp/popup.json"],
    }


def test_structured_error_preserves_compatible_text() -> None:
    error = PopupReferenceError(
        "未打开弹出参照选择框",
        stage=PopupReferenceStage.RESOLVE_SURFACE,
        reason="surface_unavailable",
        evidence={"fieldid": "bank"},
        diagnostic_refs=("/tmp/popup.png",),
    )

    assert str(error) == "未打开弹出参照选择框"
    assert error.stage is PopupReferenceStage.RESOLVE_SURFACE
    assert error.reason == "surface_unavailable"
    assert error.evidence == {"fieldid": "bank"}
    assert error.diagnostic_refs == ("/tmp/popup.png",)
