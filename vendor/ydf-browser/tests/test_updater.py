from __future__ import annotations

import io
import json
import os
import subprocess
import zipfile
from pathlib import Path

import pytest
import ydf_browser.updater as updater

from ydf_browser.updater import (
    DEFAULT_TRUSTED_HOSTS,
    DEFAULT_UPDATE_MANIFEST_URL,
    ReleaseManifest,
    UpdateManager,
    is_newer_version,
    is_trusted_url,
    run_background_update,
    should_check,
)


def _manifest(**overrides: object) -> dict:
    payload: dict[str, object] = {
        "schema_version": 1,
        "channel": "stable",
        "version": "0.1.25",
        "min_python": "3.11",
        "min_skill_version": "0.1.24",
        "platforms": {
            "macos": {
                "url": "https://061981.xyz/ydf-browser/ydf-browser-0.1.25.zip",
                "sha256": "a" * 64,
            }
        },
    }
    payload.update(overrides)
    return payload


def test_release_manifest_validates_and_selects_current_platform() -> None:
    manifest = ReleaseManifest.from_dict(_manifest())

    package = manifest.package_for("Darwin", "arm64")

    assert manifest.version == "0.1.25"
    assert package["url"].startswith("https://061981.xyz/ydf-browser/")
    assert package["sha256"] == "a" * 64


def test_default_update_source_uses_public_release_directory() -> None:
    assert DEFAULT_UPDATE_MANIFEST_URL == "https://061981.xyz/ydf-browser/release-manifest.json"
    assert DEFAULT_TRUSTED_HOSTS == frozenset({"061981.xyz"})


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://061981.xyz/ydf-browser/manifest.json", True),
        ("http://061981.xyz/ydf-browser/manifest.json", False),
        ("https://evil.example/releases/manifest.json", False),
    ],
)
def test_update_urls_require_https_and_trusted_host(url: str, expected: bool) -> None:
    assert is_trusted_url(url, DEFAULT_TRUSTED_HOSTS) is expected


def test_manifest_rejects_invalid_sha256() -> None:
    with pytest.raises(ValueError, match="sha256"):
        ReleaseManifest.from_dict(_manifest(platforms={"macos": {"url": "https://061981.xyz/ydf-browser/a", "sha256": "bad"}}))


def test_version_comparison_is_stable_semver_comparison() -> None:
    assert is_newer_version("0.1.25", "0.1.24") is True
    assert is_newer_version("0.1.24", "0.1.24") is False
    assert is_newer_version("0.1.23", "0.1.24") is False


def test_should_check_uses_24_hour_cooldown(tmp_path: Path) -> None:
    state = tmp_path / "update-state.json"
    state.write_text(json.dumps({"last_checked_at": "2026-08-13T00:00:00+00:00"}), encoding="utf-8")

    assert should_check(state, now="2026-08-13T23:59:59+00:00") is False
    assert should_check(state, now="2026-08-14T00:00:00+00:00") is True


class _Response(io.BytesIO):
    def __init__(self, payload: bytes, url: str) -> None:
        super().__init__(payload)
        self.url = url

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def geturl(self) -> str:
        return self.url


def test_update_manager_records_available_version_without_install(tmp_path: Path) -> None:
    payload = json.dumps(_manifest()).encode("utf-8")
    home = tmp_path / "home"
    current = home / "releases" / "0.1.24"
    current.mkdir(parents=True)
    (current / "VERSION").write_text("0.1.24\n", encoding="utf-8")
    (home / "current").symlink_to(current, target_is_directory=True)
    manager = UpdateManager(
        home,
        manifest_url="https://061981.xyz/ydf-browser/manifest.json",
        opener=lambda _request, timeout: _Response(payload, "https://061981.xyz/ydf-browser/manifest.json"),
    )

    result = manager.check()

    assert result["result"] == "available"
    assert result["available_version"] == "0.1.25"
    assert json.loads((home / "update-state.json").read_text(encoding="utf-8"))["result"] == "available"


def test_update_manager_failure_records_attempt_and_phase(tmp_path: Path) -> None:
    manager = UpdateManager(
        tmp_path / "home",
        manifest_url="https://061981.xyz/ydf-browser/manifest.json",
        opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("network down")),
    )

    result = manager.check(force=True)

    assert len(result["attempt_id"]) == 32
    assert result["phase"] == "manifest"
    assert result["reason"] == "OSError: network down"
    assert json.loads((tmp_path / "home" / "update-state.json").read_text())["attempt_id"] == result[
        "attempt_id"
    ]


def test_update_subprocess_failure_includes_phase_exit_code_and_bounded_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = UpdateManager(tmp_path / "home")
    stderr = "prefix-" + "x" * 2500
    monkeypatch.setattr(
        updater.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(["python", "-m", "pip"], 7, "", stderr),
    )

    with pytest.raises(RuntimeError) as captured:
        manager._run(["python", "-m", "pip"], cwd=tmp_path, phase="install_wheel")

    message = str(captured.value)
    assert message.startswith("install_wheel failed: exit_code=7; stderr=")
    assert len(message.rsplit("stderr=", 1)[1]) == 2000
    assert "CalledProcessError" not in message


def test_update_requests_identify_the_client(tmp_path: Path) -> None:
    payload = json.dumps(_manifest()).encode("utf-8")
    headers: dict[str, str | None] = {}

    def opener(request, timeout):
        headers["user_agent"] = request.get_header("User-agent")
        return _Response(payload, "https://061981.xyz/ydf-browser/manifest.json")

    manager = UpdateManager(
        tmp_path / "home",
        manifest_url="https://061981.xyz/ydf-browser/manifest.json",
        opener=opener,
    )

    manager._fetch_manifest()

    assert headers["user_agent"] == f"ydf-browser-updater/{updater.__version__}"


def test_update_manager_skips_duplicate_background_check_during_cooldown(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "update-state.json").write_text(
        json.dumps({"last_checked_at": "2999-01-01T00:00:00+00:00"}), encoding="utf-8"
    )
    manager = UpdateManager(home, opener=lambda *_args, **_kwargs: pytest.fail("must not fetch"))

    assert manager.check()["result"] == "cooldown"


def test_run_background_update_respects_disable_switch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YDF_BROWSER_AUTO_UPDATE", "0")
    manager = UpdateManager(tmp_path / "home")
    monkeypatch.setattr("ydf_browser.updater.UpdateManager", lambda *_args, **_kwargs: manager)

    run_background_update(tmp_path / "home")

    assert not (tmp_path / "home" / "update-state.json").exists()


def test_default_https_context_does_not_inherit_ssl_keylog_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SSLKEYLOGFILE", "/not-used/sslkeylogfile.txt")
    observed: dict[str, object] = {}

    def fake_urlopen(_request: object, *, timeout: int, context: object):
        observed["timeout"] = timeout
        observed["keylog_filename"] = getattr(context, "keylog_filename", "missing")
        return object()

    monkeypatch.setattr(updater.urllib.request, "urlopen", fake_urlopen)
    manager = updater.UpdateManager(tmp_path / "home", opener=fake_urlopen)

    manager._open(updater.urllib.request.Request("https://061981.xyz/ydf-browser/manifest.json"), timeout=10)

    assert observed == {"timeout": 10, "keylog_filename": None}


def _write_release_archive(path: Path, version: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        root = f"ydf-browser-release-{version}-all"
        archive.writestr(f"{root}/VERSION", f"{version}\n")
        archive.writestr(f"{root}/wheels/ydf_browser-{version}-py3-none-any.whl", "wheel")


def test_install_switches_current_and_preserves_previous(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    old = home / "releases" / "0.1.24"
    old.mkdir(parents=True)
    (old / "VERSION").write_text("0.1.24\n", encoding="utf-8")
    (home / "current").symlink_to(old, target_is_directory=True)
    archive = tmp_path / "release.zip"
    _write_release_archive(archive, "0.1.25")
    manager = UpdateManager(home)
    monkeypatch.setattr(manager, "_download", lambda *_args: archive)
    monkeypatch.setattr(manager, "_prepare_runtime", lambda _staging: None)

    result = manager._install(ReleaseManifest.from_dict(_manifest()))

    assert result["result"] == "installed"
    assert (home / "current" / "VERSION").read_text(encoding="utf-8").strip() == "0.1.25"
    assert (home / "previous" / "VERSION").read_text(encoding="utf-8").strip() == "0.1.24"


def test_failed_install_does_not_change_current(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    old = home / "releases" / "0.1.24"
    old.mkdir(parents=True)
    (old / "VERSION").write_text("0.1.24\n", encoding="utf-8")
    (home / "current").symlink_to(old, target_is_directory=True)
    archive = tmp_path / "release.zip"
    _write_release_archive(archive, "0.1.25")
    manager = UpdateManager(home)
    monkeypatch.setattr(manager, "_download", lambda *_args: archive)
    monkeypatch.setattr(manager, "_prepare_runtime", lambda _staging: (_ for _ in ()).throw(RuntimeError("health")))

    with pytest.raises(RuntimeError, match="health"):
        manager._install(ReleaseManifest.from_dict(_manifest()))

    assert (home / "current" / "VERSION").read_text(encoding="utf-8").strip() == "0.1.24"


def test_download_rejects_digest_mismatch_and_untrusted_redirect(tmp_path: Path) -> None:
    manager = UpdateManager(tmp_path / "home")
    response = _Response(b"package", "https://061981.xyz/ydf-browser/package.zip")
    manager.opener = lambda _request, timeout: response

    with pytest.raises(ValueError, match="SHA-256"):
        manager._download("https://061981.xyz/ydf-browser/package.zip", "b" * 64)

    response = _Response(b"package", "https://evil.example/releases/package.zip")
    with pytest.raises(ValueError, match="重定向"):
        manager._download("https://061981.xyz/ydf-browser/package.zip", "c" * 64)


def test_extract_archive_rejects_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("../escape.txt", "no")

    with pytest.raises(ValueError, match="越界"):
        UpdateManager(tmp_path / "home")._extract_archive(archive, tmp_path / "stage")


def test_extract_archive_restores_unix_executable_mode_without_widening_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(updater, "_IS_WINDOWS", False)
    archive = tmp_path / "permissions.zip"
    root = "ydf-browser-release-0.1.27"
    with zipfile.ZipFile(archive, "w") as package:
        for name, content, mode in (
            (f"{root}/VERSION", "0.1.27\n", 0o644),
            (f"{root}/bin/ydf-browser", "#!/bin/sh\n", 0o755),
            (f"{root}/wheels/ydf_browser-0.1.27-py3-none-any.whl", "wheel", 0o644),
        ):
            member = zipfile.ZipInfo(name)
            member.external_attr = mode << 16
            package.writestr(member, content)

    stage = tmp_path / "stage"
    UpdateManager(tmp_path / "home")._extract_archive(archive, stage)

    entrypoint = stage / "bin" / "ydf-browser"
    wheel = stage / "wheels" / "ydf_browser-0.1.27-py3-none-any.whl"
    assert os.access(entrypoint, os.X_OK)
    assert not os.access(wheel, os.X_OK)


def test_update_lock_allows_only_one_process_lock(tmp_path: Path) -> None:
    from ydf_browser.updater import update_lock

    with update_lock(tmp_path / "home") as first:
        with update_lock(tmp_path / "home") as second:
            assert first is True
            assert second is False


def test_rollback_swaps_current_and_previous(tmp_path: Path) -> None:
    home = tmp_path / "home"
    current = home / "releases" / "0.1.25"
    previous = home / "releases" / "0.1.24"
    current.mkdir(parents=True)
    previous.mkdir(parents=True)
    (current / "VERSION").write_text("0.1.25\n", encoding="utf-8")
    (previous / "VERSION").write_text("0.1.24\n", encoding="utf-8")
    (home / "current").symlink_to(current, target_is_directory=True)
    (home / "previous").symlink_to(previous, target_is_directory=True)

    result = UpdateManager(home).rollback()

    assert result["result"] == "rolled_back"
    assert (home / "current" / "VERSION").read_text(encoding="utf-8").strip() == "0.1.24"
    assert (home / "previous" / "VERSION").read_text(encoding="utf-8").strip() == "0.1.25"


def test_windows_pointer_switch_does_not_require_directory_symlinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    old = home / "releases" / "0.1.24"
    new = home / "releases" / "0.1.25"
    old.mkdir(parents=True)
    new.mkdir(parents=True)
    (home / "current.txt").parent.mkdir(parents=True, exist_ok=True)
    (home / "current.txt").write_text(str(old) + "\n", encoding="utf-8")
    monkeypatch.setattr(updater, "_IS_WINDOWS", True)

    updater.UpdateManager(home)._switch_current(new)

    assert Path((home / "current.txt").read_text(encoding="utf-8").strip()) == new
    assert Path((home / "previous.txt").read_text(encoding="utf-8").strip()) == old
    assert not (home / "current").is_symlink()


def test_windows_pointer_switch_migrates_existing_current_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    old = home / "releases" / "0.1.24"
    new = home / "releases" / "0.1.25"
    old.mkdir(parents=True)
    new.mkdir(parents=True)
    (home / "current").symlink_to(old, target_is_directory=True)
    monkeypatch.setattr(updater, "_IS_WINDOWS", True)

    updater.UpdateManager(home)._switch_current(new)

    launcher = home / "current" / "bin" / "ydf-browser.cmd"
    assert not (home / "current").is_symlink()
    assert "current.txt" in launcher.read_text(encoding="ascii")
