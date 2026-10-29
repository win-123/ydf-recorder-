#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ARCHIVE_PREFIX = "ydf-browser-source"
TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"

INCLUDE_PATHS = (
    "VERSION",
    "README.md",
    "AGENTS.md",
    "pyproject.toml",
    ".gitignore",
    "bin",
    "ydf_browser",
    "tests",
    "examples",
    "skills",
    "docs",
    "schemas",
    "config/env.example.yaml",
    "scripts",
)

EXCLUDED_DIR_NAMES = {
    ".git",
    ".pytest_cache",
    ".venv",
    ".ydf-browser",
    "__pycache__",
    "build",
    "dist",
    "reports",
    "tmp",
}

EXCLUDED_RELATIVE_FILES = {
    "config/env.yaml",
    "config/env.local.yaml",
}

EXCLUDED_FILE_NAMES = {
    ".DS_Store",
}

EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo",
}


def _archive_timestamp(timestamp: datetime | None = None) -> str:
    return (timestamp or datetime.now()).strftime(TIMESTAMP_FORMAT)


def _is_excluded_relative_path(relative_path: Path) -> bool:
    relative_name = relative_path.as_posix()
    if relative_name in EXCLUDED_RELATIVE_FILES:
        return True
    if relative_path.name in EXCLUDED_FILE_NAMES:
        return True
    if relative_path.suffix in EXCLUDED_SUFFIXES:
        return True
    return any(part in EXCLUDED_DIR_NAMES or part.endswith(".egg-info") for part in relative_path.parts)


def collect_source_files(project_root: Path | str) -> list[Path]:
    root = Path(project_root).resolve()
    collected: set[Path] = set()

    for include_name in INCLUDE_PATHS:
        include_path = root / include_name
        if not include_path.exists():
            continue

        if include_path.is_file():
            candidates = [include_path]
        else:
            candidates = [path for path in include_path.rglob("*") if path.is_file()]

        for candidate in candidates:
            if candidate.is_symlink():
                continue
            relative_path = candidate.relative_to(root)
            if _is_excluded_relative_path(relative_path):
                continue
            collected.add(relative_path)

    return sorted(collected, key=lambda path: path.as_posix())


def create_source_archive(
    project_root: Path | str,
    output_dir: Path | str | None = None,
    timestamp: datetime | None = None,
) -> Path:
    root = Path(project_root).resolve()
    archive_timestamp = _archive_timestamp(timestamp)
    archive_stem = f"{ARCHIVE_PREFIX}-{archive_timestamp}"
    target_dir = Path(output_dir).resolve() if output_dir is not None else root / "dist"
    target_dir.mkdir(parents=True, exist_ok=True)
    archive_path = target_dir / f"{archive_stem}.zip"

    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        for relative_path in collect_source_files(root):
            archive.write(root / relative_path, Path(archive_stem) / relative_path)

    return archive_path


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Package the necessary ydf-browser source files.")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Project root to package. Defaults to the repository root.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for the generated zip. Defaults to <project-root>/dist.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the files that would be packaged without creating a zip.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print every packaged file.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    project_root = args.project_root.resolve()
    output_dir = args.output_dir.resolve() if args.output_dir is not None else project_root / "dist"
    source_files = collect_source_files(project_root)

    if args.dry_run:
        print(f"project_root: {project_root}")
        print(f"output_dir: {output_dir}")
        print(f"files: {len(source_files)}")
        if args.verbose:
            for source_file in source_files:
                print(source_file.as_posix())
        return 0

    archive_path = create_source_archive(project_root=project_root, output_dir=output_dir)
    print(f"created: {archive_path}")
    print(f"files: {len(source_files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
