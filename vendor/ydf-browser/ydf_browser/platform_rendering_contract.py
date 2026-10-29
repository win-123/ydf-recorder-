from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


PLATFORM_RENDERING_CONTRACT_VERSION = "1.0.1"
VERIFIED_AGAINST = "ams-pvdf/develop-v5-2609@b2547887e"
CONSUMED_RULE_IDS = (
    "PRS-FORM-001",
    "PRS-TABLE-001",
    "PRS-TABLE-002",
    "PRS-POPUP-001",
    "PRS-POPUP-002",
    "PRS-COMPLETE-001",
    "PRS-COMPLETE-002",
    "PRS-COMPLETE-003",
    "PRS-COMPLETE-004",
    "PRS-FALLBACK-001",
)
APPLICABILITIES = frozenset({"verified", "unverified", "incompatible"})
FALLBACK_REASONS = frozenset(
    {
        "platform_baseline_unavailable",
        "exact_identity_unavailable",
        "component_variant_unverified",
        "surface_variant_unverified",
        "strong_completion_signal_unavailable",
    }
)


def build_contract_path(
    applicability: str,
    rule_ids: Iterable[str],
    fallback_reason: str | None = None,
) -> dict[str, Any]:
    rules = list(rule_ids)
    if len(rules) != len(set(rules)):
        raise ValueError("rule_ids must not contain duplicates")
    path = {
        "contract_version": PLATFORM_RENDERING_CONTRACT_VERSION,
        "applicability": applicability,
        "rule_ids": rules,
        "fallback_reason": fallback_reason,
    }
    return validate_contract_path(path)


def validate_contract_path(path: Mapping[str, Any]) -> dict[str, Any]:
    if set(path) != {"contract_version", "applicability", "rule_ids", "fallback_reason"}:
        raise ValueError("contract_path must contain only contract_version, applicability, rule_ids and fallback_reason")
    if path["contract_version"] != PLATFORM_RENDERING_CONTRACT_VERSION:
        raise ValueError("contract_version does not match platform rendering contract")
    applicability = path["applicability"]
    if applicability not in APPLICABILITIES:
        raise ValueError("applicability must be verified, unverified or incompatible")
    rule_ids = path["rule_ids"]
    if not isinstance(rule_ids, list) or not rule_ids or any(rule not in CONSUMED_RULE_IDS for rule in rule_ids):
        raise ValueError("rule_ids must contain known platform rendering rules")
    if len(rule_ids) != len(set(rule_ids)):
        raise ValueError("rule_ids must not contain duplicates")
    reason = path["fallback_reason"]
    if applicability == "unverified":
        if reason not in FALLBACK_REASONS:
            raise ValueError("fallback_reason is required for unverified contract paths")
    elif reason is not None:
        raise ValueError("fallback_reason is only allowed for unverified contract paths")
    return {
        "contract_version": path["contract_version"],
        "applicability": applicability,
        "rule_ids": list(rule_ids),
        "fallback_reason": reason,
    }


def merge_contract_paths(paths: Iterable[Mapping[str, Any]]) -> dict[str, Any] | None:
    validated = [validate_contract_path(path) for path in paths]
    if not validated:
        return None
    applicability = max(
        (path["applicability"] for path in validated),
        key={"verified": 0, "unverified": 1, "incompatible": 2}.get,
    )
    rule_ids = [
        rule_id
        for rule_id in CONSUMED_RULE_IDS
        if any(rule_id in path["rule_ids"] for path in validated)
    ]
    reason = next(
        (path["fallback_reason"] for path in validated if path["applicability"] == "unverified"),
        None,
    )
    return build_contract_path(applicability, rule_ids, reason if applicability == "unverified" else None)
