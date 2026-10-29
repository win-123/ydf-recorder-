from __future__ import annotations

import os
import shutil
from pathlib import Path
from urllib.parse import urlparse


PROFILE_MODE_PERSISTENT = "persistent"
PROFILE_MODE_EPHEMERAL = "ephemeral"
COOKIE_RESET_VISIBLE_TO_BASE_URL = "visible_to_base_url"
COOKIE_RESET_NOT_APPLICABLE = "not_applicable"


def resolve_profile_path() -> Path:
    override = os.environ.get("YDF_BROWSER_PROFILE_DIR")
    if override:
        return Path(override).expanduser()
    home = Path(os.environ.get("YDF_BROWSER_HOME", "~/.ydf-browser")).expanduser()
    return home / "browser-profile" / "default"


def profile_payload(mode: str, path: Path | None = None, *, reuse_session: bool = False) -> dict[str, str | None]:
    if mode == PROFILE_MODE_PERSISTENT:
        return {
            "mode": PROFILE_MODE_PERSISTENT,
            "path": str(path or resolve_profile_path()),
            "cookies_reset": "restore_authenticated_session" if reuse_session else COOKIE_RESET_VISIBLE_TO_BASE_URL,
        }
    return {
        "mode": PROFILE_MODE_EPHEMERAL,
        "path": None,
        "cookies_reset": COOKIE_RESET_NOT_APPLICABLE,
    }


def clear_profile(path: Path | None = None) -> Path:
    profile_path = path or resolve_profile_path()
    if _profile_locked(profile_path):
        raise RuntimeError(f"持久化浏览器 profile 正在使用，请先结束正在使用该 profile 的运行: {profile_path}")
    if profile_path.exists():
        shutil.rmtree(profile_path)
    return profile_path


def cookie_visible_to_url(cookie: dict, url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    request_path = parsed.path or "/"
    domain = str(cookie.get("domain") or "").strip().lower()
    path = str(cookie.get("path") or "/") or "/"
    if not host or not domain:
        return False
    normalized_domain = domain.lstrip(".")
    domain_matches = host == normalized_domain or (domain.startswith(".") and host.endswith(f".{normalized_domain}"))
    if not domain_matches:
        return False
    if path == "/":
        return True
    return request_path == path or request_path.startswith(path.rstrip("/") + "/")


def _profile_locked(profile_path: Path) -> bool:
    return any((profile_path / name).exists() for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"))
