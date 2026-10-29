from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import tomllib
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "package_release.py"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("package_release", SCRIPT_PATH)
package_release = importlib.util.module_from_spec(spec)
assert spec is not None
assert spec.loader is not None
spec.loader.exec_module(package_release)


def write_file(path: Path, content: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_playwright_dependency_is_pinned_to_verified_runtime_version() -> None:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as stream:
        dependencies = tomllib.load(stream)["project"]["dependencies"]

    assert "playwright==1.61.0" in dependencies


def test_collect_release_files_includes_user_assets_and_excludes_sources(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    included_files = [
        "README.md",
        "VERSION",
        "bin/ydf-browser",
        "bin/ydf-browser.cmd",
        "config/env.example.yaml",
        "docs/release/tester-guide.md",
        "docs/release/ai-dev-guide.md",
        "docs/release/request-forwarding.md",
        "docs/release/changelog.md",
        "examples/project_suggest_tabs.yaml",
        "schemas/dsl.schema.json",
        "scripts/install.sh",
        "scripts/install.ps1",
        "scripts/install-runtime.sh",
        "scripts/install-runtime.ps1",
        "scripts/install-skill.sh",
        "scripts/install-skill.ps1",
        "skills/gov-ydfdev-browser/SKILL.md",
        "skills/gov-ydfdev-browser/references/dsl-reference.md",
        "wheels/ydf_browser-1.0.0-py3-none-any.whl",
    ]
    excluded_files = [
        "ydf_browser/cli.py",
        "tests/test_cli.py",
        "skills/ydf-browser-dsl/SKILL.md",
        "config/env.yaml",
        ".ydf-browser/session.json",
        "reports/latest/report.json",
        "tmp/debug.yaml",
    ]
    for file_name in included_files + excluded_files:
        write_file(root / file_name)

    collected = {path.as_posix() for path in package_release.collect_release_files(root)}

    assert set(included_files) <= collected
    assert not set(excluded_files) & collected


def test_build_release_manifest_contains_platform_package_metadata(tmp_path: Path) -> None:
    archive = tmp_path / "ydf-browser-release.zip"
    archive.write_bytes(b"release")

    manifest = package_release.build_release_manifest(
        version="0.1.25",
        platform="macos",
        package_url="https://061981.xyz/ydf-browser/ydf-browser-0.1.25-macos.zip",
        archive_path=archive,
        min_python="3.11",
        min_skill_version="0.1.24",
    )

    assert manifest["channel"] == "stable"
    assert manifest["platforms"]["macos"]["url"].startswith("https://061981.xyz/ydf-browser/")
    assert len(manifest["platforms"]["macos"]["sha256"]) == 64


def test_create_release_archive_uses_platform_version_and_release_root(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    write_file(root / "README.md")
    write_file(root / "VERSION", "1.2.3\n")
    write_file(root / "bin/ydf-browser")
    write_file(root / "bin/ydf-browser.cmd")
    write_file(root / "config/env.example.yaml")
    write_file(root / "docs/release/tester-guide.md")
    write_file(root / "docs/release/ai-dev-guide.md")
    write_file(root / "docs/release/request-forwarding.md")
    write_file(root / "docs/release/changelog.md")
    write_file(root / "examples/project_suggest_tabs.yaml")
    write_file(root / "schemas/dsl.schema.json")
    write_file(root / "scripts/install.sh")
    (root / "scripts/install.sh").chmod(0o755)
    write_file(root / "scripts/install.ps1")
    write_file(root / "scripts/install-runtime.sh")
    write_file(root / "scripts/install-runtime.ps1")
    write_file(root / "scripts/install-skill.sh")
    write_file(root / "scripts/install-skill.ps1")
    write_file(root / "skills/gov-ydfdev-browser/SKILL.md")
    write_file(root / "wheels/ydf_browser-1.2.3-py3-none-any.whl")
    write_file(root / "ydf_browser/cli.py")
    output_dir = tmp_path / "out"

    archive_path = package_release.create_release_archive(
        project_root=root,
        output_dir=output_dir,
        platform="all",
        timestamp=datetime(2026, 5, 25, 9, 10, 11),
    )

    assert archive_path == output_dir / "ydf-browser-release-1.2.3-all-20260525-091011.zip"
    with ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        bootstrap_mode = archive.getinfo(
            "ydf-browser-release-1.2.3-all-20260525-091011/scripts/install.sh"
        ).external_attr >> 16

    prefix = "ydf-browser-release-1.2.3-all-20260525-091011"
    assert f"{prefix}/README.md" in names
    assert f"{prefix}/bin/ydf-browser" in names
    assert f"{prefix}/scripts/install.sh" in names
    assert f"{prefix}/scripts/install.ps1" in names
    assert bootstrap_mode & 0o111
    assert f"{prefix}/skills/gov-ydfdev-browser/SKILL.md" in names
    assert f"{prefix}/wheels/ydf_browser-1.2.3-py3-none-any.whl" in names
    assert f"{prefix}/ydf_browser/cli.py" not in names


def test_main_builds_wheel_before_default_release_archive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "repo"
    write_file(root / "VERSION", "1.2.3\n")
    output_dir = tmp_path / "out"
    events: list[str] = []
    monkeypatch.setattr(package_release, "check_platform_rendering_contract", lambda _root: None)

    def fake_build_wheel(project_root: Path) -> None:
        events.append("build")
        write_file(Path(project_root) / "wheels" / "ydf_browser-1.2.3-py3-none-any.whl")

    def fake_collect_release_files(project_root: Path) -> list[Path]:
        events.append("collect")
        assert Path(project_root) == root
        return [Path("wheels/ydf_browser-1.2.3-py3-none-any.whl")]

    def fake_create_release_archive(project_root: Path, output_dir: Path, platform: str) -> Path:
        events.append("archive")
        assert Path(project_root) == root
        assert Path(output_dir) == tmp_path / "out"
        assert platform == "all"
        return output_dir / "release.zip"

    monkeypatch.setattr(package_release, "build_wheel", fake_build_wheel)
    monkeypatch.setattr(package_release, "collect_release_files", fake_collect_release_files)
    monkeypatch.setattr(package_release, "create_release_archive", fake_create_release_archive)

    result = package_release.main(["--project-root", str(root), "--output-dir", str(output_dir)])

    assert result == 0
    assert events == ["build", "collect", "archive"]


def test_main_runs_platform_contract_gate_before_build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "repo"
    write_file(root / "VERSION", "1.2.3\n")
    events: list[str] = []

    def fake_contract_gate(project_root: Path) -> None:
        events.append("gate")
        assert Path(project_root) == root

    def fake_build_wheel(project_root: Path) -> None:
        events.append("build")
        write_file(Path(project_root) / "wheels/ydf_browser-1.2.3-py3-none-any.whl")

    def fake_collect_release_files(project_root: Path) -> list[Path]:
        events.append("collect")
        return [Path("wheels/ydf_browser-1.2.3-py3-none-any.whl")]

    def fake_create_release_archive(project_root: Path, output_dir: Path, platform: str) -> Path:
        events.append("archive")
        return output_dir / "release.zip"

    monkeypatch.setattr(package_release, "check_platform_rendering_contract", fake_contract_gate)
    monkeypatch.setattr(package_release, "build_wheel", fake_build_wheel)
    monkeypatch.setattr(package_release, "collect_release_files", fake_collect_release_files)
    monkeypatch.setattr(package_release, "create_release_archive", fake_create_release_archive)

    assert package_release.main(["--project-root", str(root)]) == 0
    assert events == ["gate", "build", "collect", "archive"]


def test_platform_contract_gate_rejects_missing_contract_inputs(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="平台渲染契约门禁输入缺失"):
        package_release.check_platform_rendering_contract(tmp_path / "repo")


def test_main_build_wheel_flag_uses_default_release_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "repo"
    write_file(root / "VERSION", "1.2.3\n")
    output_dir = tmp_path / "out"
    events: list[str] = []
    monkeypatch.setattr(package_release, "check_platform_rendering_contract", lambda _root: None)

    def fake_build_wheel(project_root: Path) -> None:
        events.append("build")
        write_file(Path(project_root) / "wheels" / "ydf_browser-1.2.3-py3-none-any.whl")

    def fake_collect_release_files(project_root: Path) -> list[Path]:
        events.append("collect")
        return [Path("wheels/ydf_browser-1.2.3-py3-none-any.whl")]

    def fake_create_release_archive(project_root: Path, output_dir: Path, platform: str) -> Path:
        events.append("archive")
        return output_dir / "release.zip"

    monkeypatch.setattr(package_release, "build_wheel", fake_build_wheel)
    monkeypatch.setattr(package_release, "collect_release_files", fake_collect_release_files)
    monkeypatch.setattr(package_release, "create_release_archive", fake_create_release_archive)

    result = package_release.main(
        ["--project-root", str(root), "--output-dir", str(output_dir), "--build-wheel"]
    )

    assert result == 0
    assert events == ["build", "collect", "archive"]


def test_main_dry_run_does_not_build_wheel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "repo"
    write_file(root / "VERSION", "1.2.3\n")
    events: list[str] = []

    def fake_build_wheel(project_root: Path) -> None:
        events.append("build")

    def fake_collect_release_files(project_root: Path) -> list[Path]:
        events.append("collect")
        return []

    def fake_create_release_archive(project_root: Path, output_dir: Path, platform: str) -> Path:
        events.append("archive")
        return output_dir / "release.zip"

    monkeypatch.setattr(package_release, "build_wheel", fake_build_wheel)
    monkeypatch.setattr(package_release, "collect_release_files", fake_collect_release_files)
    monkeypatch.setattr(package_release, "create_release_archive", fake_create_release_archive)

    result = package_release.main(["--project-root", str(root), "--dry-run"])

    assert result == 0
    assert events == ["collect"]


def test_main_verbose_dry_run_lists_bootstrap_installers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "repo"
    write_file(root / "VERSION", "1.2.3\n")
    write_file(root / "scripts" / "install.sh")
    write_file(root / "scripts" / "install.ps1")

    result = package_release.main(["--project-root", str(root), "--dry-run", "--verbose"])

    assert result == 0
    output = capsys.readouterr().out
    assert "scripts/install.sh" in output
    assert "scripts/install.ps1" in output


def test_main_stops_release_archive_when_default_wheel_build_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    write_file(root / "VERSION", "1.2.3\n")
    events: list[str] = []
    monkeypatch.setattr(package_release, "check_platform_rendering_contract", lambda _root: None)

    def fake_build_wheel(project_root: Path) -> None:
        events.append("build")
        raise RuntimeError("build failed")

    def fake_collect_release_files(project_root: Path) -> list[Path]:
        events.append("collect")
        return [Path("wheels/ydf_browser-1.2.3-py3-none-any.whl")]

    def fake_create_release_archive(project_root: Path, output_dir: Path, platform: str) -> Path:
        events.append("archive")
        return output_dir / "release.zip"

    monkeypatch.setattr(package_release, "build_wheel", fake_build_wheel)
    monkeypatch.setattr(package_release, "collect_release_files", fake_collect_release_files)
    monkeypatch.setattr(package_release, "create_release_archive", fake_create_release_archive)

    with pytest.raises(RuntimeError, match="build failed"):
        package_release.main(["--project-root", str(root)])

    assert events == ["build"]


def test_posix_launcher_resolves_symlinked_path_to_release_root(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("POSIX launcher is not used on Windows")
    release_root = tmp_path / "release"
    launcher_path = release_root / "bin" / "ydf-browser"
    runtime_python = release_root / "runtime" / ".venv" / "bin" / "python"
    stale_runtime_script = release_root / "runtime" / ".venv" / "bin" / "ydf-browser"
    launcher_path.parent.mkdir(parents=True)
    runtime_python.parent.mkdir(parents=True)
    shutil.copy2(PROJECT_ROOT / "bin" / "ydf-browser", launcher_path)
    runtime_python.write_text(
        "#!/usr/bin/env sh\n"
        "echo runtime-python-ok\n"
        "echo args:$*\n",
        encoding="utf-8",
    )
    stale_runtime_script.write_text(
        "#!/private/tmp/deleted-staging/runtime/.venv/bin/python\n",
        encoding="utf-8",
    )
    launcher_path.chmod(0o755)
    runtime_python.chmod(0o755)
    stale_runtime_script.chmod(0o755)
    symlink_path = tmp_path / ".local" / "bin" / "ydf-browser"
    symlink_path.parent.mkdir(parents=True)
    symlink_path.symlink_to(launcher_path)

    result = subprocess.run(
        [str(symlink_path), "doctor"],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "YDF_BROWSER_AUTO_UPDATE": "0"},
    )

    assert result.returncode == 0
    assert result.stdout.splitlines() == ["runtime-python-ok", "args:-m ydf_browser.cli doctor"]


def test_runtime_installers_recreate_or_force_reinstall_existing_runtime() -> None:
    posix_script = (PROJECT_ROOT / "scripts" / "install-runtime.sh").read_text(encoding="utf-8")
    windows_script = (PROJECT_ROOT / "scripts" / "install-runtime.ps1").read_text(encoding="utf-8")

    assert 'rm -rf "$VENV_DIR"' in posix_script
    assert "--force-reinstall" in posix_script
    assert "Remove-Item $VenvDir -Force -Recurse" in windows_script
    assert "--force-reinstall" in windows_script


def test_runtime_installers_require_python_311_or_newer_before_creating_venv() -> None:
    posix_script = (PROJECT_ROOT / "scripts" / "install-runtime.sh").read_text(encoding="utf-8")
    windows_script = (PROJECT_ROOT / "scripts" / "install-runtime.ps1").read_text(encoding="utf-8")

    assert "python3.14" in posix_script
    assert "sys.version_info >= (3, 11)" in posix_script
    assert "Python 3.11+ is required" in posix_script
    assert "python3.14" in windows_script
    assert "sys.version_info >= (3, 11)" in windows_script
    assert "Python 3.11+ is required" in windows_script
    assert "current.txt" in windows_script
    assert "ItemType SymbolicLink" not in windows_script


def test_windows_installers_register_command_dir_in_user_and_current_process_path() -> None:
    runtime_script = (PROJECT_ROOT / "scripts" / "install-runtime.ps1").read_text(encoding="utf-8")
    bootstrap_script = (PROJECT_ROOT / "scripts" / "install.ps1").read_text(encoding="ascii")

    assert "DoNotExpandEnvironmentNames" in runtime_script
    assert 'GetValueKind("Path")' in runtime_script
    assert 'SetValue("Path", $UpdatedUserPath, $UserPathKind)' in runtime_script
    assert "Add-UniquePathEntry" in runtime_script
    assert "$env:Path = Add-UniquePathEntry $env:Path $BinDir" in runtime_script
    assert "$env:Path = Add-UniquePathEntry $env:Path $BinDir" in bootstrap_script


def test_installed_launchers_start_detached_background_update() -> None:
    posix_launcher = (PROJECT_ROOT / "bin" / "ydf-browser").read_text(encoding="utf-8")
    windows_launcher = (PROJECT_ROOT / "bin" / "ydf-browser.cmd").read_text(encoding="utf-8")

    assert "ydf_browser.updater" in posix_launcher
    assert "YDF_BROWSER_AUTO_UPDATE" in posix_launcher
    assert '"${1:-}" != "update"' in posix_launcher
    assert "runtime/.venv/bin/python" in posix_launcher
    assert "-m ydf_browser.cli" in posix_launcher
    assert "ydf_browser.updater" in windows_launcher
    assert "YDF_BROWSER_AUTO_UPDATE" in windows_launcher
    assert '"%~1"=="update"' in windows_launcher
    assert "runtime\\.venv\\Scripts\\python.exe" in windows_launcher
    assert "-m ydf_browser.cli" in windows_launcher


def _copy_posix_skill_installer_package(tmp_path: Path) -> tuple[Path, Path]:
    package = tmp_path / "package"
    installer = package / "scripts" / "install-skill.sh"
    installer.parent.mkdir(parents=True)
    shutil.copy2(PROJECT_ROOT / "scripts" / "install-skill.sh", installer)
    installer.chmod(0o755)
    write_file(package / "VERSION", "0.1.25\n")
    skill_source = package / "skills" / "gov-ydfdev-browser"
    write_file(skill_source / "SKILL.md", "new\n")
    write_file(skill_source / "references" / "guide.md", "guide\n")
    return installer, skill_source


def _run_posix_skill_installer(
    installer: Path,
    target: str,
    *,
    agents_home: Path,
    claude_home: Path,
    codex_home: Path,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(installer), target],
        env={
            **os.environ,
            "AGENTS_HOME": str(agents_home),
            "CLAUDE_HOME": str(claude_home),
            "CODEX_HOME": str(codex_home),
            **(extra_env or {}),
        },
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("target", ["agents", "codex", "claude", "all"])
def test_posix_skill_installer_uses_one_canonical_copy_and_never_writes_codex(
    tmp_path: Path,
    target: str,
) -> None:
    if os.name == "nt":
        pytest.skip("POSIX installer is not used on Windows")
    installer, _skill_source = _copy_posix_skill_installer_package(tmp_path)
    agents_home = tmp_path / "agents"
    claude_home = tmp_path / "claude"
    codex_home = tmp_path / "codex"
    codex_skill = codex_home / "skills" / "gov-ydfdev-browser"
    write_file(codex_skill / "SKILL.md", "keep-codex\n")

    result = _run_posix_skill_installer(
        installer,
        target,
        agents_home=agents_home,
        claude_home=claude_home,
        codex_home=codex_home,
    )

    assert result.returncode == 0, result.stderr
    canonical = agents_home / "skills" / "gov-ydfdev-browser"
    assert (canonical / "SKILL.md").read_text(encoding="utf-8") == "new\n"
    assert (canonical / "VERSION").read_text(encoding="utf-8").strip() == "0.1.25"
    assert (codex_skill / "SKILL.md").read_text(encoding="utf-8") == "keep-codex\n"
    claude_skill = claude_home / "skills" / "gov-ydfdev-browser"
    if target in {"claude", "all"}:
        assert claude_skill.is_symlink()
        assert claude_skill.resolve() == canonical.resolve()
    else:
        assert not claude_skill.exists()


@pytest.mark.parametrize("missing", ["SKILL.md", "VERSION"])
def test_posix_skill_installer_rejects_incomplete_source_before_any_change(
    tmp_path: Path,
    missing: str,
) -> None:
    if os.name == "nt":
        pytest.skip("POSIX installer is not used on Windows")
    installer, skill_source = _copy_posix_skill_installer_package(tmp_path)
    missing_path = skill_source / missing if missing == "SKILL.md" else installer.parents[1] / missing
    missing_path.unlink()
    agents_home = tmp_path / "agents"
    canonical = agents_home / "skills" / "gov-ydfdev-browser"
    write_file(canonical / "SKILL.md", "keep-canonical\n")
    claude_home = tmp_path / "claude"

    result = _run_posix_skill_installer(
        installer,
        "all",
        agents_home=agents_home,
        claude_home=claude_home,
        codex_home=tmp_path / "codex",
    )

    assert result.returncode != 0
    assert (canonical / "SKILL.md").read_text(encoding="utf-8") == "keep-canonical\n"
    assert not (claude_home / "skills" / "gov-ydfdev-browser").exists()


def test_posix_skill_installer_does_not_copy_when_link_creation_fails(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("POSIX installer is not used on Windows")
    installer, _skill_source = _copy_posix_skill_installer_package(tmp_path)
    fake_bin = tmp_path / "fake-bin"
    fake_ln = fake_bin / "ln"
    write_file(fake_ln, "#!/usr/bin/env sh\nexit 9\n")
    fake_ln.chmod(0o755)
    agents_home = tmp_path / "agents"
    claude_home = tmp_path / "claude"

    result = _run_posix_skill_installer(
        installer,
        "all",
        agents_home=agents_home,
        claude_home=claude_home,
        codex_home=tmp_path / "codex",
        extra_env={"PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"},
    )

    assert result.returncode != 0
    assert (agents_home / "skills" / "gov-ydfdev-browser" / "SKILL.md").is_file()
    assert not (claude_home / "skills" / "gov-ydfdev-browser").exists()


def test_posix_skill_installer_replaces_a_read_only_canonical_skill(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("POSIX installer is not used on Windows")
    installer, _skill_source = _copy_posix_skill_installer_package(tmp_path)
    agents_home = tmp_path / "agents"
    canonical = agents_home / "skills" / "gov-ydfdev-browser"
    write_file(canonical / "SKILL.md", "old\n")
    write_file(canonical / "removed.md", "stale\n")
    (canonical / "SKILL.md").chmod(0o444)
    canonical.chmod(0o555)

    result = _run_posix_skill_installer(
        installer,
        "codex",
        agents_home=agents_home,
        claude_home=tmp_path / "claude",
        codex_home=tmp_path / "codex",
    )
    if canonical.exists():
        canonical.chmod(0o755)
        for path in canonical.rglob("*"):
            path.chmod(0o755 if path.is_dir() else 0o644)

    assert result.returncode == 0, result.stderr
    assert (canonical / "SKILL.md").read_text(encoding="utf-8") == "new\n"
    assert not (canonical / "removed.md").exists()


def test_posix_skill_installer_repairs_wrong_claude_link_and_is_idempotent(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("POSIX installer is not used on Windows")
    installer, _skill_source = _copy_posix_skill_installer_package(tmp_path)
    agents_home = tmp_path / "agents"
    claude_home = tmp_path / "claude"
    claude_skill = claude_home / "skills" / "gov-ydfdev-browser"
    wrong_target = tmp_path / "wrong-skill"
    write_file(wrong_target / "SKILL.md", "wrong\n")
    claude_skill.parent.mkdir(parents=True)
    claude_skill.symlink_to(wrong_target, target_is_directory=True)

    first = _run_posix_skill_installer(
        installer,
        "all",
        agents_home=agents_home,
        claude_home=claude_home,
        codex_home=tmp_path / "codex",
    )
    second = _run_posix_skill_installer(
        installer,
        "all",
        agents_home=agents_home,
        claude_home=claude_home,
        codex_home=tmp_path / "codex",
    )

    canonical = agents_home / "skills" / "gov-ydfdev-browser"
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert claude_skill.is_symlink()
    assert claude_skill.resolve() == canonical.resolve()


@pytest.mark.parametrize("conflict_kind", ["directory", "file"])
def test_posix_skill_installer_rejects_real_claude_target_before_any_change(
    tmp_path: Path,
    conflict_kind: str,
) -> None:
    if os.name == "nt":
        pytest.skip("POSIX installer is not used on Windows")
    installer, _skill_source = _copy_posix_skill_installer_package(tmp_path)
    agents_home = tmp_path / "agents"
    canonical = agents_home / "skills" / "gov-ydfdev-browser"
    write_file(canonical / "SKILL.md", "keep-canonical\n")
    claude_home = tmp_path / "claude"
    claude_skill = claude_home / "skills" / "gov-ydfdev-browser"
    if conflict_kind == "directory":
        write_file(claude_skill / "SKILL.md", "keep-claude\n")
    else:
        write_file(claude_skill, "keep-file\n")

    result = _run_posix_skill_installer(
        installer,
        "all",
        agents_home=agents_home,
        claude_home=claude_home,
        codex_home=tmp_path / "codex",
    )

    assert result.returncode != 0
    assert (canonical / "SKILL.md").read_text(encoding="utf-8") == "keep-canonical\n"
    if conflict_kind == "directory":
        assert (claude_skill / "SKILL.md").read_text(encoding="utf-8") == "keep-claude\n"
    else:
        assert claude_skill.read_text(encoding="utf-8") == "keep-file\n"
