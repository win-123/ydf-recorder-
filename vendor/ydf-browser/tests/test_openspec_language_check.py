from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_checker():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "check_openspec_language.py"
    spec = importlib.util.spec_from_file_location("check_openspec_language", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_change(root: Path, change: str, files: dict[str, str]) -> Path:
    change_root = root / "openspec" / "changes" / change
    for relative_path, content in files.items():
        path = change_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return change_root


def test_language_check_reports_english_human_prose(tmp_path: Path) -> None:
    checker = _load_checker()
    _write_change(
        tmp_path,
        "english-prose",
        {
            "proposal.md": """## Why

This change adds a mandatory language gate for generated OpenSpec artifacts.
""",
        },
    )

    issues = checker.check_change(tmp_path, "english-prose")

    assert issues
    assert issues[0].relative_path == "proposal.md"
    assert issues[0].line_number == 3
    assert "英文正文" in issues[0].message


def test_language_check_accepts_compatible_chinese_with_openspec_markers(tmp_path: Path) -> None:
    checker = _load_checker()
    _write_change(
        tmp_path,
        "compatible-chinese",
        {
            "specs/openspec-artifact-language/spec.md": """## ADDED Requirements

### Requirement: OpenSpec 文档生成后必须执行语言检查
系统 SHALL 在生成或更新 OpenSpec 文档后执行语言检查门禁。

#### Scenario: 最终回复前检查新生成的文档
- **WHEN** agent 创建 `proposal.md`
- **THEN** agent MUST 运行 `openspec validate <change> --strict`
- **AND** agent MUST 运行 `./scripts/check_openspec_language.py --change <change>`
""",
        },
    )

    issues = checker.check_change(tmp_path, "compatible-chinese")

    assert issues == []


def test_language_check_allows_code_blocks_paths_and_identifiers(tmp_path: Path) -> None:
    checker = _load_checker()
    _write_change(
        tmp_path,
        "technical-markers",
        {
            "tasks.md": """## 1. 语言检查脚本

- [ ] 1.1 新增 `scripts/check_openspec_language.py`，支持 `--change <change>`。
- [ ] 1.2 运行 `pytest tests/test_openspec_language_check.py`。

```bash
openspec validate enforce-openspec-language-check --strict
./scripts/check_openspec_language.py --change enforce-openspec-language-check
```
""",
        },
    )

    issues = checker.check_change(tmp_path, "technical-markers")

    assert issues == []
