from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = PROJECT_ROOT / "scripts" / "install.sh"
POWERSHELL_INSTALL_SCRIPT = PROJECT_ROOT / "scripts" / "install.ps1"
PACKAGE_URL = "https://061981.xyz/ydf-browser/test-package.zip"


def _write_package(path: Path, *, version: str = "9.8.7", traversal: bool = False) -> None:
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        prefix = "ydf-browser-release-9.8.7-all"
        archive.writestr(f"{prefix}/VERSION", f"{version}\n")
        archive.writestr(f"{prefix}/wheels/ydf_browser-{version}-py3-none-any.whl", b"wheel")
        launcher = ZipInfo(f"{prefix}/bin/ydf-browser")
        launcher.create_system = 3
        launcher.external_attr = 0o100755 << 16
        archive.writestr(launcher, "#!/usr/bin/env sh\nexit 0\n")
        installer = ZipInfo(f"{prefix}/scripts/install-runtime.sh")
        installer.create_system = 3
        installer.external_attr = 0o100755 << 16
        archive.writestr(
            installer,
            "#!/usr/bin/env sh\n"
            "set -eu\n"
            "package_root=$(CDPATH= cd -- \"$(dirname -- \"$0\")/..\" && pwd)\n"
            "[ -x \"$package_root/bin/ydf-browser\" ] || { echo 'launcher is not executable' >&2; exit 7; }\n"
            "printf 'installed\\n' > \"$BOOTSTRAP_MARKER\"\n",
        )
        if traversal:
            archive.writestr("../escaped.txt", "must not be written")


def _write_fake_commands(path: Path) -> None:
    path.mkdir()
    (path / "python3.11").symlink_to(sys.executable)
    (path / "uname").write_text(
        "#!/usr/bin/env sh\n"
        "case \"${1:-}\" in\n"
        "  -s) echo Darwin ;;\n"
        "  -m) echo arm64 ;;\n"
        "  *) echo Darwin ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    (path / "curl").write_text(
        "#!/usr/bin/env sh\n"
        "set -eu\n"
        "[ \"${1:-}\" = \"-q\" ] || { echo 'curl must disable .curlrc' >&2; exit 8; }\n"
        "output=\n"
        "url=\n"
        "while [ \"$#\" -gt 0 ]; do\n"
        "  case \"$1\" in\n"
        "    -o) output=$2; shift 2 ;;\n"
        "    *) url=$1; shift ;;\n"
        "  esac\n"
        "done\n"
        "case \"$url\" in\n"
        "  */release-manifest.json) source=$FAKE_MANIFEST ;;\n"
        "  */test-package.zip) source=$FAKE_PACKAGE ;;\n"
        "  *) echo \"unexpected URL: $url\" >&2; exit 9 ;;\n"
        "esac\n"
        "/bin/cp \"$source\" \"$output\"\n"
        "printf '%s' \"$url\"\n",
        encoding="utf-8",
    )
    for command in (path / "uname", path / "curl"):
        command.chmod(0o755)


def _run_installer(
    tmp_path: Path,
    *,
    package_version: str = "9.8.7",
    sha256: str | None = None,
    traversal: bool = False,
) -> subprocess.CompletedProcess[str]:
    package = tmp_path / "package.zip"
    _write_package(package, version=package_version, traversal=traversal)
    manifest = tmp_path / "release-manifest.json"
    digest = sha256 or hashlib.sha256(package.read_bytes()).hexdigest()
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "channel": "stable",
                "version": "9.8.7",
                "min_python": "3.11",
                "min_skill_version": "9.8.0",
                "platforms": {
                    "macos-arm64": {"url": PACKAGE_URL, "sha256": digest},
                    "all": {
                        "url": "https://061981.xyz/ydf-browser/fallback.zip",
                        "sha256": "0" * 64,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    _write_fake_commands(fake_bin)
    marker = tmp_path / "installed.txt"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "FAKE_MANIFEST": str(manifest),
        "FAKE_PACKAGE": str(package),
        "BOOTSTRAP_MARKER": str(marker),
        "YDF_BROWSER_HOME": str(tmp_path / "home"),
        "YDF_BROWSER_BIN_DIR": str(tmp_path / "user-bin"),
    }
    return subprocess.run(
        ["/bin/sh", str(INSTALL_SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.mark.skipif(os.name == "nt", reason="POSIX bootstrap is not used on Windows")
def test_posix_bootstrap_verifies_and_delegates_platform_package(tmp_path: Path) -> None:
    result = _run_installer(tmp_path)

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "installed.txt").read_text(encoding="utf-8") == "installed\n"
    assert "ydf-browser install-skill" in result.stdout


@pytest.mark.skipif(os.name == "nt", reason="POSIX bootstrap is not used on Windows")
def test_posix_bootstrap_rejects_sha256_mismatch_before_install(tmp_path: Path) -> None:
    result = _run_installer(tmp_path, sha256="f" * 64)

    assert result.returncode != 0
    assert "SHA-256" in result.stderr
    assert not (tmp_path / "installed.txt").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX bootstrap is not used on Windows")
def test_posix_bootstrap_rejects_zip_traversal_before_install(tmp_path: Path) -> None:
    result = _run_installer(tmp_path, traversal=True)

    assert result.returncode != 0
    assert "越界路径" in result.stderr
    assert not (tmp_path / "installed.txt").exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX bootstrap is not used on Windows")
def test_posix_bootstrap_rejects_package_version_mismatch(tmp_path: Path) -> None:
    result = _run_installer(tmp_path, package_version="9.8.6")

    assert result.returncode != 0
    assert "VERSION" in result.stderr
    assert not (tmp_path / "installed.txt").exists()


def test_powershell_bootstrap_fails_closed_without_effective_redirect_uri() -> None:
    source = POWERSHELL_INSTALL_SCRIPT.read_text(encoding="ascii")

    assert 'throw "Could not determine the final response URL."' in source
    assert "return $Fallback" not in source
    assert "$PackageVersion -ne $ReleaseVersion.ToString()" in source
