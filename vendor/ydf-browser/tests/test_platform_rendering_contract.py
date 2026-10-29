from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from ydf_browser.platform_rendering_contract import (
    CONSUMED_RULE_IDS,
    PLATFORM_RENDERING_CONTRACT_VERSION,
    VERIFIED_AGAINST,
    build_contract_path,
    merge_contract_paths,
    validate_contract_path,
)


CHECK_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_platform_rendering_contract.py"


def test_contract_projection_is_independent_and_declares_unique_rules() -> None:
    assert PLATFORM_RENDERING_CONTRACT_VERSION == "1.0.1"
    assert VERIFIED_AGAINST == "ams-pvdf/develop-v5-2609@b2547887e"
    assert len(CONSUMED_RULE_IDS) == len(set(CONSUMED_RULE_IDS))
    assert "PRS-FORM-001" in CONSUMED_RULE_IDS
    assert "PRS-COMPLETE-004" in CONSUMED_RULE_IDS


@pytest.mark.parametrize("applicability", ["verified", "unverified", "incompatible"])
def test_build_contract_path_accepts_three_states(applicability: str) -> None:
    reason = "exact_identity_unavailable" if applicability == "unverified" else None

    path = build_contract_path(applicability, ["PRS-FORM-001"], reason)

    assert path == {
        "contract_version": "1.0.1",
        "applicability": applicability,
        "rule_ids": ["PRS-FORM-001"],
        "fallback_reason": reason,
    }
    assert validate_contract_path(path) == path


def test_contract_path_rejects_invalid_state_reason_and_shape() -> None:
    with pytest.raises(ValueError, match="applicability"):
        build_contract_path("maybe", ["PRS-FORM-001"])
    with pytest.raises(ValueError, match="fallback_reason"):
        build_contract_path("verified", ["PRS-FORM-001"], "exact_identity_unavailable")
    with pytest.raises(ValueError, match="rule"):
        build_contract_path("verified", ["PRS-FORM-001", "PRS-FORM-001"])
    with pytest.raises(ValueError, match="contract_version"):
        validate_contract_path({"applicability": "verified", "rule_ids": []})


def test_merge_contract_paths_deduplicates_rules_in_projection_order_and_prioritizes_state() -> None:
    merged = merge_contract_paths(
        [
            build_contract_path("verified", ["PRS-TABLE-002", "PRS-FORM-001"]),
            build_contract_path("unverified", ["PRS-FORM-001"], "surface_variant_unverified"),
            build_contract_path("incompatible", ["PRS-TABLE-001"]),
        ]
    )

    assert merged == {
        "contract_version": "1.0.1",
        "applicability": "incompatible",
        "rule_ids": ["PRS-FORM-001", "PRS-TABLE-001", "PRS-TABLE-002"],
        "fallback_reason": None,
    }


def test_merge_unverified_paths_keeps_first_stable_fallback_reason() -> None:
    merged = merge_contract_paths(
        [
            build_contract_path("unverified", ["PRS-FORM-001"], "exact_identity_unavailable"),
            build_contract_path("unverified", ["PRS-TABLE-001"], "surface_variant_unverified"),
        ]
    )

    assert merged["applicability"] == "unverified"
    assert merged["fallback_reason"] == "exact_identity_unavailable"


def _write_contract_fixtures(tmp_path: Path, *, version: str = "1.0.0", baseline: str = "base@1") -> tuple[Path, Path]:
    spec = tmp_path / "spec.md"
    spec.write_text(
        f"""- `contract_version: {version}`\n- `verified_against: {baseline}`\n\n### Requirement: Form\n- `rule_id: PRS-FORM-001`\n- `source_anchor: src/Form.jsx#Form`\n\n### Requirement: Table\n- `rule_id: PRS-TABLE-001`\n- `source_anchor: src/Table.jsx#Table`\n""",
        encoding="utf-8",
    )
    consumer = tmp_path / "consumer.py"
    consumer.write_text(
        f"""PLATFORM_RENDERING_CONTRACT_VERSION = {version!r}\nVERIFIED_AGAINST = {baseline!r}\nCONSUMED_RULE_IDS = ('PRS-FORM-001', 'PRS-TABLE-001')\n""",
        encoding="utf-8",
    )
    return spec, consumer


def _run_contract_check(spec: Path, consumer: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECK_SCRIPT), "--spec", str(spec), "--consumer", str(consumer), *extra],
        check=False,
        capture_output=True,
        text=True,
    )


def test_static_contract_check_accepts_matching_spec_and_consumer(tmp_path: Path) -> None:
    spec, consumer = _write_contract_fixtures(tmp_path)

    result = _run_contract_check(spec, consumer)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "consumer_change,expected",
    [
        ("CONSUMED_RULE_IDS = ('PRS-FORM-001', 'PRS-FORM-001')", "duplicate"),
        ("PLATFORM_RENDERING_CONTRACT_VERSION = '2.0.0'", "version"),
        ("VERIFIED_AGAINST = 'base@2'", "verified_against"),
    ],
)
def test_static_contract_check_rejects_projection_drift(
    tmp_path: Path, consumer_change: str, expected: str
) -> None:
    spec, consumer = _write_contract_fixtures(tmp_path)
    original = consumer.read_text(encoding="utf-8")
    target = consumer_change.split(" = ", 1)[0]
    consumer.write_text(
        original.replace(next(line for line in original.splitlines() if line.startswith(target)), consumer_change),
        encoding="utf-8",
    )

    result = _run_contract_check(spec, consumer)

    assert result.returncode != 0
    assert expected in result.stderr


def test_static_contract_check_rejects_missing_source_anchor(tmp_path: Path) -> None:
    spec, consumer = _write_contract_fixtures(tmp_path)
    spec.write_text(spec.read_text(encoding="utf-8").replace("- `source_anchor: src/Table.jsx#Table`\n", ""), encoding="utf-8")

    result = _run_contract_check(spec, consumer)

    assert result.returncode != 0
    assert "PRS-TABLE-001" in result.stderr
    assert "source_anchor" in result.stderr


def test_static_contract_check_rejects_unchanged_version_when_previous_body_changed(tmp_path: Path) -> None:
    spec, consumer = _write_contract_fixtures(tmp_path)
    previous = tmp_path / "previous.md"
    previous.write_text(spec.read_text(encoding="utf-8"), encoding="utf-8")
    spec.write_text(spec.read_text(encoding="utf-8") + "\n正文发生变化\n", encoding="utf-8")

    result = _run_contract_check(spec, consumer, "--previous-spec", str(previous))

    assert result.returncode != 0
    assert "version" in result.stderr
    assert "body" in result.stderr


def test_static_contract_check_lists_source_anchor_review_when_anchor_changes(tmp_path: Path) -> None:
    spec, consumer = _write_contract_fixtures(tmp_path, version="1.0.1")
    previous = tmp_path / "previous.md"
    previous.write_text(spec.read_text(encoding="utf-8").replace("1.0.1", "1.0.0"), encoding="utf-8")
    spec.write_text(spec.read_text(encoding="utf-8").replace("src/Table.jsx#Table", "src/TableV2.jsx#Table"), encoding="utf-8")

    result = _run_contract_check(spec, consumer, "--previous-spec", str(previous))

    assert result.returncode == 0, result.stderr
    assert "PRS-TABLE-001" in result.stdout
    assert "source anchor" in result.stdout
