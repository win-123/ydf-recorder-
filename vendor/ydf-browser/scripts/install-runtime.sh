#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PACKAGE_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
VERSION=$(tr -d '\r\n' < "$PACKAGE_ROOT/VERSION")
INSTALL_ROOT="${YDF_BROWSER_HOME:-$HOME/.ydf-browser}"
RELEASE_DIR="$INSTALL_ROOT/releases/$VERSION"
CURRENT_LINK="$INSTALL_ROOT/current"
VENV_DIR="$RELEASE_DIR/runtime/.venv"

mkdir -p "$RELEASE_DIR"
if [ "$PACKAGE_ROOT" != "$RELEASE_DIR" ]; then
  (cd "$PACKAGE_ROOT" && tar cf - .) | (cd "$RELEASE_DIR" && tar xf -)
fi

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

if [ -d "$VENV_DIR" ]; then
  rm -rf "$VENV_DIR"
fi
"$PYTHON_BIN" -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m pip install --upgrade pip

WHEEL=$(find "$RELEASE_DIR/wheels" -maxdepth 1 -name 'ydf_browser-*.whl' -print 2>/dev/null | head -n 1 || true)
if [ -z "$WHEEL" ]; then
  echo "Missing ydf-browser wheel under $RELEASE_DIR/wheels." >&2
  echo "Build the release package with scripts/package_release.py --build-wheel." >&2
  exit 1
fi

"$VENV_DIR/bin/python" -m pip install --force-reinstall --find-links "$RELEASE_DIR/wheels" "$WHEEL"
"$VENV_DIR/bin/python" -m playwright install chromium

mkdir -p "$INSTALL_ROOT"
ln -sfn "$RELEASE_DIR" "$CURRENT_LINK"

CONFIG_DIR="$INSTALL_ROOT/config"
mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG_DIR/env.yaml" ]; then
  cp "$RELEASE_DIR/config/env.example.yaml" "$CONFIG_DIR/env.yaml"
fi

BIN_DIR="${YDF_BROWSER_BIN_DIR:-$HOME/.local/bin}"
mkdir -p "$BIN_DIR"
ln -sfn "$CURRENT_LINK/bin/ydf-browser" "$BIN_DIR/ydf-browser"

echo "Installed ydf-browser $VERSION at $RELEASE_DIR"
echo "Config file: $CONFIG_DIR/env.yaml"
echo "Command linked at $BIN_DIR/ydf-browser"
echo "Ensure $BIN_DIR is in PATH, then run: ydf-browser doctor"
