from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import ssl
import subprocess
import sys
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator
from zipfile import ZipFile

from . import __version__


DEFAULT_UPDATE_MANIFEST_URL = (
    "https://061981.xyz/ydf-browser/release-manifest.json"
)
DEFAULT_TRUSTED_HOSTS = frozenset({"061981.xyz"})
UPDATE_CHECK_INTERVAL = timedelta(hours=24)
UPDATE_STATE_FILE = "update-state.json"
UPDATE_LOCK_FILE = "update.lock"
_VERSION_PATTERN = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_PYTHON_PATTERN = re.compile(r"^(\d+)\.(\d+)$")
_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
_IS_WINDOWS = os.name == "nt"


def _version_tuple(value: str) -> tuple[int, int, int]:
    match = _VERSION_PATTERN.fullmatch(str(value).strip())
    if match is None:
        raise ValueError(f"版本号必须是 x.y.z: {value}")
    return tuple(int(part) for part in match.groups())


def _python_tuple(value: str) -> tuple[int, int]:
    match = _PYTHON_PATTERN.fullmatch(str(value).strip())
    if match is None:
        raise ValueError(f"Python 版本必须是 x.y: {value}")
    return tuple(int(part) for part in match.groups())


def is_newer_version(candidate: str, current: str) -> bool:
    return _version_tuple(candidate) > _version_tuple(current)


def is_trusted_url(url: str, trusted_hosts: set[str] | frozenset[str]) -> bool:
    parsed = urllib.parse.urlparse(url)
    return parsed.scheme == "https" and parsed.hostname in trusted_hosts and not parsed.username and not parsed.password


def _platform_key(system: str, machine: str) -> list[str]:
    system_key = {"Darwin": "macos", "Windows": "windows", "Linux": "linux"}.get(system, system.lower())
    machine_key = {"AMD64": "x86_64", "x86_64": "x86_64", "aarch64": "arm64", "arm64": "arm64"}.get(
        machine, machine.lower()
    )
    return [f"{system_key}-{machine_key}", system_key, "all"]


@dataclass(frozen=True, slots=True)
class ReleaseManifest:
    schema_version: int
    channel: str
    version: str
    min_python: str
    min_skill_version: str
    platforms: dict[str, dict[str, str]]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ReleaseManifest":
        if not isinstance(payload, dict):
            raise ValueError("发布清单必须是对象")
        if payload.get("schema_version") != 1:
            raise ValueError("不支持的发布清单 schema_version")
        if payload.get("channel") != "stable":
            raise ValueError("发布清单 channel 必须是 stable")
        version = str(payload.get("version") or "")
        _version_tuple(version)
        min_python = str(payload.get("min_python") or "")
        if not re.fullmatch(r"\d+\.\d+", min_python):
            raise ValueError("发布清单 min_python 无效")
        min_skill_version = str(payload.get("min_skill_version") or "")
        _version_tuple(min_skill_version)
        raw_platforms = payload.get("platforms")
        if not isinstance(raw_platforms, dict) or not raw_platforms:
            raise ValueError("发布清单 platforms 不能为空")
        platforms: dict[str, dict[str, str]] = {}
        for name, raw_package in raw_platforms.items():
            if not isinstance(raw_package, dict):
                raise ValueError(f"发布包必须是对象: {name}")
            url = str(raw_package.get("url") or "")
            sha256 = str(raw_package.get("sha256") or "")
            if not is_trusted_url(url, DEFAULT_TRUSTED_HOSTS):
                raise ValueError(f"发布包 URL 不受信或不是 HTTPS: {name}")
            if not _SHA256_PATTERN.fullmatch(sha256):
                raise ValueError(f"发布包 sha256 无效: {name}")
            platforms[str(name)] = {"url": url, "sha256": sha256.lower()}
        return cls(1, "stable", version, min_python, min_skill_version, platforms)

    def package_for(self, system: str | None = None, machine: str | None = None) -> dict[str, str]:
        candidates = _platform_key(system or platform.system(), machine or platform.machine())
        for candidate in candidates:
            if candidate in self.platforms:
                return self.platforms[candidate]
        raise ValueError(f"发布清单没有当前平台的发布包: {', '.join(candidates)}")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_update_state(home: Path) -> dict[str, Any]:
    path = home / UPDATE_STATE_FILE
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_update_state(home: Path, payload: dict[str, Any]) -> None:
    home.mkdir(parents=True, exist_ok=True)
    target = home / UPDATE_STATE_FILE
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, target)


def should_check(state_path: Path, now: str | None = None) -> bool:
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        last_checked = _parse_timestamp(str(state["last_checked_at"]))
    except (FileNotFoundError, OSError, KeyError, TypeError, ValueError):
        return True
    current = _parse_timestamp(now) if now is not None else datetime.now(timezone.utc)
    return current - last_checked >= UPDATE_CHECK_INTERVAL


def default_home() -> Path:
    return Path(os.environ.get("YDF_BROWSER_HOME", "~/.ydf-browser")).expanduser()


def skill_compatibility(min_version: str | None) -> dict[str, Any]:
    if not min_version:
        return {"ok": True, "status": "not_required"}
    required = _version_tuple(min_version)
    roots = {Path(os.environ.get("AGENTS_HOME", "~/.agents")).expanduser()}
    versions: dict[str, str] = {}
    for root in roots:
        version_file = root / "skills" / "gov-ydfdev-browser" / "VERSION"
        try:
            value = version_file.read_text(encoding="utf-8").strip()
            _version_tuple(value)
        except (FileNotFoundError, OSError, ValueError):
            continue
        versions[str(root)] = value
    if not versions:
        return {"ok": True, "status": "unknown", "min_skill_version": min_version, "versions": {}}
    incompatible = {root: value for root, value in versions.items() if _version_tuple(value) < required}
    return {
        "ok": not incompatible,
        "status": "incompatible" if incompatible else "compatible",
        "min_skill_version": min_version,
        "versions": versions,
        "incompatible": incompatible,
    }


def _resolve_link(link: Path) -> Path | None:
    if not link.exists() and not link.is_symlink():
        return None
    return link.resolve()


def _current_release(home: Path) -> Path | None:
    return _resolve_pointer(home, "current")


def _resolve_pointer(home: Path, name: str) -> Path | None:
    if _IS_WINDOWS:
        pointer = home / f"{name}.txt"
        try:
            return Path(pointer.read_text(encoding="utf-8").strip()).expanduser().resolve()
        except (FileNotFoundError, OSError, ValueError):
            pass
    return _resolve_link(home / name)


def _current_version(home: Path) -> str:
    release = _current_release(home)
    if release is not None:
        version_file = release / "VERSION"
        if version_file.exists():
            return version_file.read_text(encoding="utf-8").strip()
    from . import __version__

    return __version__


class _UpdateLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle: Any = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+")
        try:
            if _IS_WINDOWS:
                import msvcrt

                self.handle.seek(0, os.SEEK_END)
                if self.handle.tell() == 0:
                    self.handle.write("0")
                    self.handle.flush()
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, IOError):
            self.handle.close()
            self.handle = None
            return False
        return True

    def release(self) -> None:
        if self.handle is None:
            return
        try:
            if _IS_WINDOWS:
                import msvcrt

                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None


@contextmanager
def update_lock(home: Path) -> Iterator[bool]:
    lock = _UpdateLock(home / UPDATE_LOCK_FILE)
    acquired = lock.acquire()
    try:
        yield acquired
    finally:
        if acquired:
            lock.release()


class UpdateManager:
    def __init__(
        self,
        home: Path | None = None,
        *,
        manifest_url: str = DEFAULT_UPDATE_MANIFEST_URL,
        opener: Any = urllib.request.urlopen,
        python_executable: str | None = None,
    ) -> None:
        self.home = (home or default_home()).expanduser()
        self.manifest_url = manifest_url
        self.opener = opener
        self.python_executable = python_executable or sys.executable
        self._phase = "idle"

    def check(self, *, install: bool = False, force: bool = False) -> dict[str, Any]:
        current_version = _current_version(self.home)
        state = load_update_state(self.home)
        if not force and not should_check(self.home / UPDATE_STATE_FILE):
            return {"result": "cooldown", "current_version": current_version}
        with update_lock(self.home) as acquired:
            if not acquired:
                return {"result": "locked", "current_version": current_version}
            status: dict[str, Any] = {
                "attempt_id": uuid.uuid4().hex,
                "current_version": current_version,
                "last_checked_at": _now_iso(),
                "result": "failed",
            }
            try:
                self._phase = "manifest"
                manifest = self._fetch_manifest()
                status["available_version"] = manifest.version
                status["min_skill_version"] = manifest.min_skill_version
                if not is_newer_version(manifest.version, current_version):
                    status["result"] = "no_update"
                elif install:
                    status.update(self._install(manifest))
                else:
                    status["result"] = "available"
                self._phase = "complete"
            except Exception as exc:
                status["result"] = "failed"
                status["reason"] = f"{exc.__class__.__name__}: {exc}"
            status["phase"] = self._phase
            save_update_state(self.home, {**state, **status})
            return status

    def rollback(self) -> dict[str, Any]:
        with update_lock(self.home) as acquired:
            if not acquired:
                return {"result": "locked"}
            previous = _resolve_pointer(self.home, "previous")
            if previous is None or not previous.exists():
                return {"result": "failed", "reason": "没有可回滚版本"}
            self._switch_current(previous)
            status = {"result": "rolled_back", "current_version": _current_version(self.home)}
            save_update_state(self.home, {**load_update_state(self.home), **status, "rollback_at": _now_iso()})
            return status

    def _fetch_manifest(self) -> ReleaseManifest:
        if not is_trusted_url(self.manifest_url, DEFAULT_TRUSTED_HOSTS):
            raise ValueError("更新清单 URL 不受信或不是 HTTPS")
        request = urllib.request.Request(
            self.manifest_url,
            headers={"Accept": "application/json", "User-Agent": f"ydf-browser-updater/{__version__}"},
        )
        with self._open(request, timeout=10) as response:
            final_url = getattr(response, "geturl", lambda: self.manifest_url)()
            if not is_trusted_url(final_url, DEFAULT_TRUSTED_HOSTS):
                raise ValueError("更新清单重定向到不受信 URL")
            payload = json.loads(response.read().decode("utf-8"))
        return ReleaseManifest.from_dict(payload)

    def _open(self, request: urllib.request.Request, *, timeout: int) -> Any:
        if self.opener is urllib.request.urlopen:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = True
            context.verify_mode = ssl.CERT_REQUIRED
            context.load_default_certs()
            return self.opener(request, timeout=timeout, context=context)
        return self.opener(request, timeout=timeout)

    def _install(self, manifest: ReleaseManifest) -> dict[str, Any]:
        package = manifest.package_for()
        if _python_tuple(manifest.min_python) > (sys.version_info.major, sys.version_info.minor):
            raise RuntimeError(f"需要 Python {manifest.min_python}，当前为 {sys.version_info.major}.{sys.version_info.minor}")
        staging = self.home / "releases" / f"{manifest.version}.staging-{uuid.uuid4().hex}"
        archive: Path | None = None
        try:
            self._phase = "download_verify"
            archive = self._download(package["url"], package["sha256"])
            self._phase = "extract"
            self._extract_archive(archive, staging)
            self._prepare_runtime(staging)
            release = self.home / "releases" / manifest.version
            if release.exists():
                shutil.rmtree(release)
            staging.rename(release)
            self._phase = "switch_current"
            self._switch_current(release)
            self._phase = "cleanup_releases"
            self._cleanup_releases()
            return {"result": "installed", "current_version": manifest.version, "installed_version": manifest.version}
        finally:
            if staging.exists():
                shutil.rmtree(staging)
            if archive is not None and archive.parent == self.home / ".update-tmp":
                archive.unlink(missing_ok=True)

    def _download(self, url: str, sha256: str) -> Path:
        if not is_trusted_url(url, DEFAULT_TRUSTED_HOSTS):
            raise ValueError("发布包 URL 不受信或不是 HTTPS")
        temporary_dir = self.home / ".update-tmp"
        temporary_dir.mkdir(parents=True, exist_ok=True)
        target = temporary_dir / f"download-{uuid.uuid4().hex}.zip"
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/zip", "User-Agent": f"ydf-browser-updater/{__version__}"},
        )
        with self._open(request, timeout=30) as response, target.open("wb") as output:
            final_url = getattr(response, "geturl", lambda: url)()
            if not is_trusted_url(final_url, DEFAULT_TRUSTED_HOSTS):
                raise ValueError("发布包重定向到不受信 URL")
            digest = hashlib.sha256()
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                output.write(chunk)
        if digest.hexdigest() != sha256:
            target.unlink(missing_ok=True)
            raise ValueError("发布包 SHA-256 校验失败")
        return target

    def _extract_archive(self, archive: Path, staging: Path) -> None:
        staging.mkdir(parents=True, exist_ok=False)
        with ZipFile(archive) as package:
            root = staging.resolve()
            for member in package.infolist():
                destination = (staging / member.filename).resolve()
                if destination != root and root not in destination.parents:
                    raise ValueError("发布包包含越界路径")
                package.extract(member, staging)
                if not _IS_WINDOWS and member.create_system == 3 and destination.is_file():
                    archive_mode = (member.external_attr >> 16) & 0o777
                    executable_bits = archive_mode & 0o111
                    if executable_bits:
                        current_mode = destination.stat().st_mode & 0o777
                        os.chmod(destination, current_mode | executable_bits)
        entries = list(staging.iterdir())
        if len(entries) == 1 and entries[0].is_dir() and not (staging / "VERSION").exists():
            wrapper = entries[0]
            for child in wrapper.iterdir():
                child.rename(staging / child.name)
            wrapper.rmdir()
        if not (staging / "VERSION").is_file() or not list((staging / "wheels").glob("ydf_browser-*.whl")):
            raise ValueError("发布包缺少 VERSION 或 ydf-browser wheel")

    def _prepare_runtime(self, staging: Path) -> None:
        venv_dir = staging / "runtime" / ".venv"
        venv_dir.parent.mkdir(parents=True, exist_ok=True)
        self._run(
            [self.python_executable, "-m", "venv", str(venv_dir)],
            cwd=staging,
            phase="create_venv",
        )
        venv_python = venv_dir / ("Scripts/python.exe" if _IS_WINDOWS else "bin/python")
        wheel = next((staging / "wheels").glob("ydf_browser-*.whl"))
        self._run(
            [str(venv_python), "-m", "pip", "install", "--force-reinstall", "--find-links", str(staging / "wheels"), str(wheel)],
            cwd=staging,
            phase="install_wheel",
        )
        self._run(
            [str(venv_python), "-m", "playwright", "install", "chromium"],
            cwd=staging,
            phase="install_playwright",
        )
        self._phase = "health_check"
        health = subprocess.run(
            [str(venv_python), "-m", "ydf_browser.cli", "doctor", "--skip-config"],
            cwd=staging,
            check=False,
            capture_output=True,
            text=True,
        )
        if health.returncode != 0:
            detail = ((health.stderr or "").strip() or (health.stdout or "").strip())[-2000:]
            raise RuntimeError(f"health_check failed: exit_code={health.returncode}; stderr={detail}")

    def _run(self, command: list[str], *, cwd: Path, phase: str) -> None:
        self._phase = phase
        completed = subprocess.run(
            command,
            cwd=cwd,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or "").strip()[-2000:]
            raise RuntimeError(f"{phase} failed: exit_code={completed.returncode}; stderr={detail}")

    def _switch_current(self, release: Path) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        if _IS_WINDOWS:
            old_current = _current_release(self.home)
            self._ensure_windows_current_wrapper()
            if old_current is not None and old_current != release:
                self._write_pointer("previous", old_current)
            self._write_pointer("current", release)
            return
        current = self.home / "current"
        previous = self.home / "previous"
        old_current = _current_release(self.home)
        if old_current is not None and old_current != release:
            self._replace_link(previous, old_current)
        self._replace_link(current, release)

    @staticmethod
    def _replace_link(link: Path, target: Path) -> None:
        temporary = link.with_name(f".{link.name}.{uuid.uuid4().hex}.tmp")
        temporary.symlink_to(target, target_is_directory=True)
        os.replace(temporary, link)

    def _write_pointer(self, name: str, target: Path) -> None:
        pointer = self.home / f"{name}.txt"
        temporary = pointer.with_name(f".{pointer.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(str(target.resolve()) + "\n", encoding="utf-8")
        os.replace(temporary, pointer)

    def _ensure_windows_current_wrapper(self) -> None:
        current_dir = self.home / "current"
        if current_dir.is_symlink():
            current_dir.unlink()
        launcher = current_dir / "bin" / "ydf-browser.cmd"
        launcher.parent.mkdir(parents=True, exist_ok=True)
        launcher.write_text(
            "@echo off\r\n"
            "setlocal\r\n"
            "set /p RELEASE_ROOT=<\"%~dp0..\\..\\current.txt\"\r\n"
            "call \"%RELEASE_ROOT%\\bin\\ydf-browser.cmd\" %*\r\n"
            "exit /b %ERRORLEVEL%\r\n",
            encoding="ascii",
        )

    def _cleanup_releases(self) -> None:
        current = _current_release(self.home)
        previous = _resolve_pointer(self.home, "previous")
        releases = self.home / "releases"
        if not releases.exists():
            return
        for child in releases.iterdir():
            if child in {current, previous} or ".staging-" in child.name:
                continue
            if child.is_dir():
                shutil.rmtree(child)


def run_background_update(home: Path | None = None) -> None:
    if os.environ.get("YDF_BROWSER_AUTO_UPDATE", "1") == "0":
        return
    UpdateManager(home).check(install=True)


if __name__ == "__main__":
    if "--background" not in sys.argv[1:]:
        raise SystemExit("仅支持安装入口使用 --background 启动后台更新")
    run_background_update()
