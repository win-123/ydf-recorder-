#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zipfile import ZIP_DEFLATED, ZipFile


ARCHIVE_PREFIX = "ydf-browser-release"
TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S"
SUPPORTED_PLATFORMS = {"macos", "windows", "linux", "all"}

INCLUDE_PATHS = (
    "README.md",
    "VERSION",
    "bin",
    "config/env.example.yaml",
    "docs/release",
    "examples",
    "schemas",
    "scripts/install.sh",
    "scripts/install.ps1",
    "scripts/install-runtime.sh",
    "scripts/install-runtime.ps1",
    "scripts/install-skill.sh",
    "scripts/install-skill.ps1",
    "skills/gov-ydfdev-browser",
    "wheels",
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
    "ydf_browser",
    "tests",
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


def read_version(project_root: Path | str) -> str:
    root = Path(project_root).resolve()
    version_file = root / "VERSION"
    if version_file.exists():
        version = version_file.read_text(encoding="utf-8").strip()
        if version:
            return version
    pyproject = root / "pyproject.toml"
    for line in pyproject.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("version"):
            return line.split("=", 1)[1].strip().strip('"')
    raise ValueError("无法读取发布版本号")


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


def collect_release_files(project_root: Path | str) -> list[Path]:
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


def create_release_archive(
    project_root: Path | str,
    output_dir: Path | str | None = None,
    platform: str = "all",
    timestamp: datetime | None = None,
) -> Path:
    if platform not in SUPPORTED_PLATFORMS:
        raise ValueError(f"不支持的发布平台: {platform}")
    root = Path(project_root).resolve()
    version = read_version(root)
    archive_timestamp = _archive_timestamp(timestamp)
    archive_stem = f"{ARCHIVE_PREFIX}-{version}-{platform}-{archive_timestamp}"
    target_dir = Path(output_dir).resolve() if output_dir is not None else root / "dist"
    target_dir.mkdir(parents=True, exist_ok=True)
    archive_path = target_dir / f"{archive_stem}.zip"

    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        for relative_path in collect_release_files(root):
            archive.write(root / relative_path, Path(archive_stem) / relative_path)

    return archive_path


def build_release_manifest(
    *,
    version: str,
    platform: str,
    package_url: str,
    archive_path: Path | str,
    min_python: str = "3.11",
    min_skill_version: str | None = None,
    existing: dict[str, object] | None = None,
) -> dict[str, object]:
    parsed = urlparse(package_url)
    if parsed.scheme != "https" or parsed.hostname != "061981.xyz":
        raise ValueError("发布包 URL 必须是受信 061981.xyz HTTPS 地址")
    if platform not in SUPPORTED_PLATFORMS:
        raise ValueError(f"不支持的发布平台: {platform}")
    if not Path(archive_path).is_file():
        raise FileNotFoundError(f"发布包不存在: {archive_path}")
    payload = dict(existing or {})
    payload.update(
        {
            "schema_version": 1,
            "channel": "stable",
            "version": version,
            "min_python": min_python,
            "min_skill_version": min_skill_version or version,
        }
    )
    platforms = dict(payload.get("platforms") or {})
    platforms[platform] = {
        "url": package_url,
        "sha256": hashlib.sha256(Path(archive_path).read_bytes()).hexdigest(),
    }
    payload["platforms"] = platforms
    return payload


def write_release_manifest(path: Path | str, manifest: dict[str, object]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_wheel(project_root: Path | str) -> None:
    root = Path(project_root).resolve()
    wheel_dir = root / "wheels"
    wheel_dir.mkdir(parents=True, exist_ok=True)
    for old_wheel in wheel_dir.glob("ydf_browser-*.whl"):
        old_wheel.unlink()
    command = [sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "--wheel-dir", str(wheel_dir)]
    result = subprocess.run(command, cwd=root, check=False)
    if result.returncode != 0:
        raise RuntimeError("构建 wheel 失败")


def check_platform_rendering_contract(project_root: Path | str) -> None:
    root = Path(project_root).resolve()
    spec_path = root / "openspec/specs/platform-rendering-semantics/spec.md"
    if not spec_path.is_file():
        spec_path = root / (
            "openspec/changes/consume-platform-rendering-contract-v1/"
            "specs/platform-rendering-semantics/spec.md"
        )
    consumer_path = root / "ydf_browser/platform_rendering_contract.py"
    checker_path = root / "scripts/check_platform_rendering_contract.py"
    missing = [
        str(path.relative_to(root))
        for path in (spec_path, consumer_path, checker_path)
        if not path.is_file()
    ]
    if missing:
        raise RuntimeError(f"平台渲染契约门禁输入缺失: {', '.join(missing)}")
    result = subprocess.run(
        [sys.executable, str(checker_path), "--spec", str(spec_path), "--consumer", str(consumer_path)],
        cwd=root,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("平台渲染契约一致性检查失败")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Package a user-facing ydf-browser release zip.")
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
    parser.add_argument("--platform", choices=sorted(SUPPORTED_PLATFORMS), default="all")
    parser.add_argument("--manifest-file", type=Path, help="写入或合并稳定发布清单的 JSON 文件")
    parser.add_argument("--manifest-url", help="本次发布包在受信发布源上的 HTTPS 地址")
    parser.add_argument("--manifest-min-python", default="3.11", help="发布清单声明的最低 Python 版本")
    parser.add_argument("--manifest-min-skill-version", help="发布清单声明的最低 skill 版本")
    parser.add_argument(
        "--build-wheel",
        action="store_true",
        help="Accepted for compatibility; non-dry-run packages build the ydf-browser wheel by default.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print packaged files without creating a zip.")
    parser.add_argument("--verbose", action="store_true", help="Print every packaged file.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    project_root = args.project_root.resolve()
    output_dir = args.output_dir.resolve() if args.output_dir is not None else project_root / "dist"
    if not args.dry_run:
        check_platform_rendering_contract(project_root)
        build_wheel(project_root)
    source_files = collect_release_files(project_root)
    version = read_version(project_root)

    if args.dry_run:
        print(f"project_root: {project_root}")
        print(f"output_dir: {output_dir}")
        print(f"version: {version}")
        print(f"platform: {args.platform}")
        print(f"files: {len(source_files)}")
        if args.verbose:
            for source_file in source_files:
                print(source_file.as_posix())
        return 0

    if not any(path.as_posix().startswith("wheels/ydf_browser-") for path in source_files):
        raise FileNotFoundError("缺少 wheels/ydf_browser-*.whl，wheel 构建未生成发布包所需文件")
    archive_path = create_release_archive(project_root=project_root, output_dir=output_dir, platform=args.platform)
    if args.manifest_file is not None:
        if not args.manifest_url:
            raise ValueError("--manifest-file 必须同时指定 --manifest-url")
        existing: dict[str, object] | None = None
        if args.manifest_file.exists():
            existing_payload = json.loads(args.manifest_file.read_text(encoding="utf-8"))
            if not isinstance(existing_payload, dict):
                raise ValueError("已有发布清单必须是 JSON 对象")
            existing = existing_payload
        write_release_manifest(
            args.manifest_file,
            build_release_manifest(
                version=version,
                platform=args.platform,
                package_url=args.manifest_url,
                archive_path=archive_path,
                min_python=args.manifest_min_python,
                min_skill_version=args.manifest_min_skill_version,
                existing=existing,
            ),
        )
    print(f"created: {archive_path}")
    print(f"version: {version}")
    print(f"platform: {args.platform}")
    print(f"files: {len(source_files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
