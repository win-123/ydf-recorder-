from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "package_source.py"
spec = importlib.util.spec_from_file_location("package_source", SCRIPT_PATH)
package_source = importlib.util.module_from_spec(spec)
assert spec is not None
assert spec.loader is not None
spec.loader.exec_module(package_source)


def write_file(path: Path, content: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_collect_source_files_includes_runtime_validation_sources_only(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    included_files = [
        "README.md",
        "AGENTS.md",
        "pyproject.toml",
        ".gitignore",
        "ydf_browser/cli.py",
        "tests/test_cli.py",
        "examples/workflow.yaml",
        "examples/fixtures/import.xlsx",
        "skills/gov-ydfdev-browser/SKILL.md",
        "config/env.example.yaml",
        "scripts/package_source.py",
    ]
    excluded_files = [
        "config/env.yaml",
        "config/env.local.yaml",
        "tmp/scratch.yaml",
        "reports/latest/report.json",
        "dist/old.zip",
        ".venv/bin/python",
        ".git/HEAD",
        ".pytest_cache/CACHEDIR.TAG",
        "ydf_browser/__pycache__/cli.cpython-311.pyc",
    ]
    for file_name in included_files + excluded_files:
        write_file(root / file_name)

    collected = {path.as_posix() for path in package_source.collect_source_files(root)}

    assert set(included_files) <= collected
    assert not set(excluded_files) & collected


def test_create_source_archive_uses_timestamped_name_and_source_root(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    write_file(root / "README.md")
    write_file(root / "pyproject.toml")
    write_file(root / "ydf_browser/cli.py")
    write_file(root / "config/env.example.yaml")
    write_file(root / "config/env.yaml")
    output_dir = tmp_path / "out"

    archive_path = package_source.create_source_archive(
        project_root=root,
        output_dir=output_dir,
        timestamp=datetime(2026, 5, 8, 9, 10, 11),
    )

    assert archive_path == output_dir / "ydf-browser-source-20260508-091011.zip"
    with ZipFile(archive_path) as archive:
        names = set(archive.namelist())

    assert "ydf-browser-source-20260508-091011/README.md" in names
    assert "ydf-browser-source-20260508-091011/ydf_browser/cli.py" in names
    assert "ydf-browser-source-20260508-091011/config/env.example.yaml" in names
    assert "ydf-browser-source-20260508-091011/config/env.yaml" not in names
