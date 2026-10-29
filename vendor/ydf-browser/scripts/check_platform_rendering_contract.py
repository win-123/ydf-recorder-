#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path
from typing import Any


_CONTRACT_VERSION = re.compile(r"contract_version:\s*([^\x60\s]+)")
_VERIFIED_AGAINST = re.compile(r"verified_against:\s*([^\x60\s]+)")
_RULE_ID = re.compile(r"rule_id:\s*([A-Z0-9-]+)")
_SOURCE_ANCHOR = re.compile(r"source_anchor:\s*([^\x60\s]+)")


def _default_spec(project_root: Path) -> Path | None:
    candidates = [
        project_root / "openspec/specs/platform-rendering-semantics/spec.md",
        project_root / "openspec/changes/consume-platform-rendering-contract-v1/specs/platform-rendering-semantics/spec.md",
        *sorted((project_root / "openspec/changes").glob("*/specs/platform-rendering-semantics/spec.md")),
    ]
    return next((path for path in candidates if path.is_file()), None)


def _spec_facts(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    versions = _CONTRACT_VERSION.findall(text)
    baselines = _VERIFIED_AGAINST.findall(text)
    rules: list[str] = []
    anchors: dict[str, list[str]] = {}
    current_rule: str | None = None
    for line in text.splitlines():
        rule_match = _RULE_ID.search(line)
        if rule_match:
            current_rule = rule_match.group(1)
            rules.append(current_rule)
            anchors.setdefault(current_rule, [])
        anchor_match = _SOURCE_ANCHOR.search(line)
        if anchor_match and current_rule is not None:
            anchors[current_rule].append(anchor_match.group(1))
    return {
        "text": text,
        "version": versions[0] if len(versions) == 1 else None,
        "version_count": len(versions),
        "baseline": baselines[0] if len(baselines) == 1 else None,
        "baseline_count": len(baselines),
        "rules": rules,
        "anchors": anchors,
    }


def _consumer_facts(path: Path) -> dict[str, Any]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    values: dict[str, list[Any]] = {}
    for node in ast.walk(tree):
        target: str | None = None
        value_node: ast.AST | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target, value_node = node.targets[0].id, node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            target, value_node = node.target.id, node.value
        if target not in {"PLATFORM_RENDERING_CONTRACT_VERSION", "VERIFIED_AGAINST", "CONSUMED_RULE_IDS"}:
            continue
        try:
            value = ast.literal_eval(value_node)
        except (ValueError, TypeError):
            value = None
        values.setdefault(target, []).append(value)
    return values


def _without_version_declaration(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not _CONTRACT_VERSION.search(line))


def check_contract(spec_path: Path, consumer_path: Path, previous_spec_path: Path | None = None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    notices: list[str] = []
    spec = _spec_facts(spec_path)
    consumer = _consumer_facts(consumer_path)

    if spec["version_count"] != 1 or spec["version"] is None:
        errors.append("spec contract_version must be declared exactly once")
    if spec["baseline_count"] != 1 or spec["baseline"] is None:
        errors.append("spec verified_against must be declared exactly once")
    if len(spec["rules"]) != len(set(spec["rules"])):
        errors.append("spec contains duplicate rule IDs")
    missing_anchors = [rule for rule in dict.fromkeys(spec["rules"]) if not spec["anchors"].get(rule)]
    if missing_anchors:
        errors.append(f"source_anchor missing for rule IDs: {', '.join(missing_anchors)}")

    for name in ("PLATFORM_RENDERING_CONTRACT_VERSION", "VERIFIED_AGAINST", "CONSUMED_RULE_IDS"):
        assignments = consumer.get(name, [])
        if len(assignments) != 1:
            errors.append(f"consumer must declare {name} exactly once")
    version = consumer.get("PLATFORM_RENDERING_CONTRACT_VERSION", [None])
    baseline = consumer.get("VERIFIED_AGAINST", [None])
    rules = consumer.get("CONSUMED_RULE_IDS", [None])
    if spec["version"] is not None and len(version) == 1 and version[0] != spec["version"]:
        errors.append("consumer contract version does not match spec version")
    if spec["baseline"] is not None and len(baseline) == 1 and baseline[0] != spec["baseline"]:
        errors.append("consumer verified_against does not match spec baseline")
    consumed = rules[0] if len(rules) == 1 else None
    if not isinstance(consumed, (tuple, list)):
        errors.append("consumer CONSUMED_RULE_IDS must be a tuple or list")
    else:
        if len(consumed) != len(set(consumed)):
            errors.append("consumer CONSUMED_RULE_IDS contains duplicate rule IDs")
        unknown = [rule for rule in consumed if rule not in spec["rules"]]
        if unknown:
            errors.append(f"consumer contains undefined rule IDs: {', '.join(dict.fromkeys(unknown))}")

    if previous_spec_path is not None:
        previous = _spec_facts(previous_spec_path)
        if spec["version"] == previous["version"] and _without_version_declaration(spec["text"]) != _without_version_declaration(previous["text"]):
            errors.append("spec body changed without a contract version change")
        for rule in sorted(set(spec["rules"]) & set(previous["rules"])):
            old = previous["anchors"].get(rule, [])
            new = spec["anchors"].get(rule, [])
            if old != new:
                notices.append(f"source anchor review required for {rule}: {old} -> {new}")
    return errors, notices


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check platform rendering contract projection drift.")
    parser.add_argument("--spec", type=Path, default=None)
    parser.add_argument("--consumer", type=Path, default=None)
    parser.add_argument("--previous-spec", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    project_root = Path(__file__).resolve().parents[1]
    spec_path = args.spec or _default_spec(project_root)
    consumer_path = args.consumer or project_root / "ydf_browser/platform_rendering_contract.py"
    if spec_path is None:
        print("platform rendering contract spec not found", file=sys.stderr)
        return 2
    errors, notices = check_contract(spec_path.resolve(), consumer_path.resolve(), args.previous_spec.resolve() if args.previous_spec else None)
    for notice in notices:
        print(notice)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(f"platform rendering contract OK: {spec_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
