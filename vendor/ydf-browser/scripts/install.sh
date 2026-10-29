#!/usr/bin/env sh
set -eu

MANIFEST_URL="https://061981.xyz/ydf-browser/release-manifest.json"
TRUSTED_HOST="061981.xyz"

find_python_311() {
  for candidate in \
    python3.14 python3.13 python3.12 python3.11 python3 python \
    /opt/homebrew/bin/python3.14 /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11 /opt/homebrew/bin/python3 \
    /usr/local/bin/python3.14 /usr/local/bin/python3.13 /usr/local/bin/python3.12 /usr/local/bin/python3.11 /usr/local/bin/python3
  do
    if command -v "$candidate" >/dev/null 2>&1; then
      python_path=$(command -v "$candidate")
    elif [ -x "$candidate" ]; then
      python_path=$candidate
    else
      continue
    fi
    if "$python_path" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
    then
      printf '%s\n' "$python_path"
      return 0
    fi
  done
  return 1
}

PYTHON_BIN=$(find_python_311 || true)
if [ -z "$PYTHON_BIN" ]; then
  echo "Python 3.11+ is required but was not found in PATH." >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required but was not found in PATH." >&2
  exit 1
fi

TEMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/ydf-browser-install.XXXXXX")
trap 'rm -rf "$TEMP_ROOT"' EXIT HUP INT TERM
MANIFEST_FILE="$TEMP_ROOT/release-manifest.json"
MANIFEST_EFFECTIVE_URL="$TEMP_ROOT/manifest-url.txt"
SELECTION_FILE="$TEMP_ROOT/selection.txt"
ARCHIVE_FILE="$TEMP_ROOT/release.zip"
PACKAGE_EFFECTIVE_URL="$TEMP_ROOT/package-url.txt"
EXTRACT_ROOT="$TEMP_ROOT/package"
PACKAGE_ROOT_FILE="$TEMP_ROOT/package-root.txt"

download() {
  curl -q -fsSL \
    --proto '=https' \
    --proto-redir '=https' \
    --tlsv1.2 \
    -A 'ydf-browser-installer/1' \
    -o "$2" \
    -w '%{url_effective}' \
    "$1" > "$3"
}

download "$MANIFEST_URL" "$MANIFEST_FILE" "$MANIFEST_EFFECTIVE_URL"

"$PYTHON_BIN" - "$MANIFEST_FILE" "$MANIFEST_EFFECTIVE_URL" "$SELECTION_FILE" "$(uname -s)" "$(uname -m)" "$TRUSTED_HOST" <<'PY'
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse


def trusted(url: str, host: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname == host and parsed.username is None and parsed.password is None


def version(value: object, name: str) -> str:
    text = str(value or "")
    if not re.fullmatch(r"\d+(?:\.\d+)+", text):
        raise ValueError(f"发布清单 {name} 无效")
    return text


try:
    manifest_path, effective_path, selection_path, system, machine, trusted_host = sys.argv[1:]
    effective_url = Path(effective_path).read_text(encoding="utf-8").strip()
    if not trusted(effective_url, trusted_host):
        raise ValueError("发布清单重定向到不受信 URL")
    payload = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("发布清单必须是对象")
    if payload.get("schema_version") != 1:
        raise ValueError("不支持的发布清单 schema_version")
    if payload.get("channel") != "stable":
        raise ValueError("发布清单 channel 必须是 stable")
    release_version = version(payload.get("version"), "version")
    min_python = version(payload.get("min_python"), "min_python")
    version(payload.get("min_skill_version"), "min_skill_version")
    required_python = tuple(int(part) for part in min_python.split("."))
    current_python = sys.version_info[: len(required_python)]
    if current_python < required_python:
        raise ValueError(
            f"需要 Python {min_python}，当前为 {sys.version_info.major}.{sys.version_info.minor}"
        )
    platforms = payload.get("platforms")
    if not isinstance(platforms, dict) or not platforms:
        raise ValueError("发布清单 platforms 不能为空")
    normalized_system = {"Darwin": "macos", "Linux": "linux"}.get(system)
    if normalized_system is None:
        raise ValueError(f"POSIX 引导安装器不支持当前系统: {system}")
    normalized_machine = {
        "AMD64": "x86_64",
        "x86_64": "x86_64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }.get(machine, machine.lower())
    packages = {}
    for name, item in platforms.items():
        if not isinstance(item, dict):
            raise ValueError(f"发布包必须是对象: {name}")
        url = str(item.get("url") or "")
        sha256 = str(item.get("sha256") or "").lower()
        if not trusted(url, trusted_host):
            raise ValueError(f"发布包 URL 不受信或不是 HTTPS: {name}")
        if not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise ValueError(f"发布包 sha256 无效: {name}")
        packages[str(name)] = (url, sha256)
    selected = None
    for candidate in (f"{normalized_system}-{normalized_machine}", normalized_system, "all"):
        if candidate in packages:
            selected = packages[candidate]
            break
    if selected is None:
        raise ValueError("发布清单没有当前平台的发布包")
    Path(selection_path).write_text(
        f"{selected[0]}\n{selected[1]}\n{release_version}\n",
        encoding="utf-8",
    )
except Exception as exc:
    print(f"安装失败: {exc}", file=sys.stderr)
    raise SystemExit(1)
PY

PACKAGE_URL=$(sed -n '1p' "$SELECTION_FILE")
PACKAGE_SHA256=$(sed -n '2p' "$SELECTION_FILE")
RELEASE_VERSION=$(sed -n '3p' "$SELECTION_FILE")
download "$PACKAGE_URL" "$ARCHIVE_FILE" "$PACKAGE_EFFECTIVE_URL"

"$PYTHON_BIN" - "$ARCHIVE_FILE" "$PACKAGE_EFFECTIVE_URL" "$PACKAGE_SHA256" "$EXTRACT_ROOT" "$PACKAGE_ROOT_FILE" "$TRUSTED_HOST" "$RELEASE_VERSION" <<'PY'
import hashlib
import stat
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
from zipfile import ZipFile


def trusted(url: str, host: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname == host and parsed.username is None and parsed.password is None


try:
    archive_path, effective_path, expected_sha256, extract_path, result_path, trusted_host, expected_version = sys.argv[1:]
    effective_url = Path(effective_path).read_text(encoding="utf-8").strip()
    if not trusted(effective_url, trusted_host):
        raise ValueError("发布包重定向到不受信 URL")
    digest = hashlib.sha256()
    with Path(archive_path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected_sha256:
        raise ValueError("发布包 SHA-256 校验失败")
    root = Path(extract_path)
    root.mkdir()
    with ZipFile(archive_path) as package:
        for member in package.infolist():
            relative = PurePosixPath(member.filename.replace("\\", "/"))
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("发布包包含越界路径")
            mode = (member.external_attr >> 16) & 0o170000
            if stat.S_ISLNK(mode):
                raise ValueError("发布包包含不受支持的符号链接")
            destination = (root / Path(*relative.parts)).resolve()
            if destination != root.resolve() and root.resolve() not in destination.parents:
                raise ValueError("发布包包含越界路径")
        package.extractall(root)
        for member in package.infolist():
            destination = root / Path(*PurePosixPath(member.filename.replace("\\", "/")).parts)
            executable_bits = ((member.external_attr >> 16) & 0o777) & 0o111
            if member.create_system == 3 and executable_bits and destination.is_file():
                destination.chmod(destination.stat().st_mode | executable_bits)
    entries = list(root.iterdir())
    package_root = entries[0] if len(entries) == 1 and entries[0].is_dir() and not (root / "VERSION").exists() else root
    if not (package_root / "VERSION").is_file():
        raise ValueError("发布包缺少 VERSION")
    package_version = (package_root / "VERSION").read_text(encoding="utf-8").strip()
    if package_version != expected_version:
        raise ValueError(f"发布包 VERSION 与发布清单不一致: {package_version} != {expected_version}")
    if not list((package_root / "wheels").glob("ydf_browser-*.whl")):
        raise ValueError("发布包缺少 ydf-browser wheel")
    if not (package_root / "scripts" / "install-runtime.sh").is_file():
        raise ValueError("发布包缺少 POSIX runtime 安装器")
    Path(result_path).write_text(str(package_root), encoding="utf-8")
except Exception as exc:
    print(f"安装失败: {exc}", file=sys.stderr)
    raise SystemExit(1)
PY

PACKAGE_ROOT=$(cat "$PACKAGE_ROOT_FILE")
sh "$PACKAGE_ROOT/scripts/install-runtime.sh"

echo "Optional skill installation:"
echo "  ydf-browser install-skill"
echo "Installed stable ydf-browser runtime $RELEASE_VERSION."
