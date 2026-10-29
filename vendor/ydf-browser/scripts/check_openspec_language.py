#!/usr/bin/env python3
"""Check OpenSpec artifacts for compatible Chinese prose."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import NamedTuple


_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_INLINE_CODE_RE = re.compile(r"`[^`]*`")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->")
_ENGLISH_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")

_ALLOWED_EXACT_LINES = {
    "## Why",
    "## What Changes",
    "## Capabilities",
    "### New Capabilities",
    "### Modified Capabilities",
    "## Impact",
    "## Context",
    "## Goals / Non-Goals",
    "**Goals:**",
    "**Non-Goals:**",
    "## Decisions",
    "## Risks / Trade-offs",
    "## Migration Plan",
    "## Open Questions",
    "## ADDED Requirements",
    "## MODIFIED Requirements",
    "## REMOVED Requirements",
    "## RENAMED Requirements",
    "## Purpose",
    "## Requirements",
}

_PREFIXES_TO_STRIP = (
    r"^#{3}\s+Requirement:\s*",
    r"^#{4}\s+Scenario:\s*",
    r"^-\s+\*\*(?:WHEN|THEN|AND)\*\*\s*",
    r"^-\s+\[[ xX]\]\s+\d+(?:\.\d+)*\s*",
    r"^-\s+",
    r"^\d+\.\s+",
)


class Issue(NamedTuple):
    relative_path: str
    line_number: int
    message: str
    line: str


def _artifact_paths(change_root: Path) -> list[Path]:
    paths = [
        change_root / "proposal.md",
        change_root / "design.md",
        change_root / "tasks.md",
    ]
    specs_dir = change_root / "specs"
    if specs_dir.exists():
        paths.extend(sorted(specs_dir.glob("**/*.md")))
    return [path for path in paths if path.exists()]


def _strip_machine_syntax(line: str) -> str:
    text = _HTML_COMMENT_RE.sub("", line).strip()
    if text in _ALLOWED_EXACT_LINES:
        return ""
    text = _INLINE_CODE_RE.sub("", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = text.replace("**", "").replace("__", "").strip()
    for pattern in _PREFIXES_TO_STRIP:
        text = re.sub(pattern, "", text).strip()
    text = text.lstrip("#").strip()
    return text


def _is_english_human_prose(text: str) -> bool:
    if not text or _CJK_RE.search(text):
        return False
    words = _ENGLISH_WORD_RE.findall(text)
    if len(words) < 4:
        return False
    letters = sum(len(word) for word in words)
    return letters >= 18


def check_file(path: Path, relative_path: str) -> list[Issue]:
    issues: list[Issue] = []
    in_fence = False
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        human_text = _strip_machine_syntax(raw_line)
        if _is_english_human_prose(human_text):
            issues.append(
                Issue(
                    relative_path=relative_path,
                    line_number=line_number,
                    message="疑似英文正文，应使用简体中文表达",
                    line=raw_line.strip(),
                )
            )
    return issues


def check_change(project_root: str | Path, change: str) -> list[Issue]:
    root = Path(project_root)
    change_root = root / "openspec" / "changes" / change
    if not change_root.exists():
        return [
            Issue(
                relative_path=str(change_root.relative_to(root) if change_root.is_absolute() else change_root),
                line_number=0,
                message=f"未找到 OpenSpec change: {change}",
                line="",
            )
        ]
    issues: list[Issue] = []
    for path in _artifact_paths(change_root):
        relative_path = path.relative_to(change_root).as_posix()
        issues.extend(check_file(path, relative_path))
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check OpenSpec artifacts use compatible Chinese prose.")
    parser.add_argument("--change", required=True, help="OpenSpec change name under openspec/changes/")
    parser.add_argument("--root", default=".", help="Project root. Defaults to current directory.")
    args = parser.parse_args(argv)

    issues = check_change(Path(args.root).resolve(), args.change)
    if not issues:
        print(f"OpenSpec language check passed: {args.change}")
        return 0
    print(f"OpenSpec language check failed: {args.change}", file=sys.stderr)
    for issue in issues:
        location = issue.relative_path
        if issue.line_number:
            location = f"{location}:{issue.line_number}"
        print(f"{location}: {issue.message}", file=sys.stderr)
        if issue.line:
            print(f"  {issue.line}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
