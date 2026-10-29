#!/usr/bin/env sh
set -eu

TARGET="${1:-all}"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PACKAGE_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
SKILL_SOURCE="$PACKAGE_ROOT/skills/gov-ydfdev-browser"
VERSION_FILE="$PACKAGE_ROOT/VERSION"
AGENTS_ROOT="${AGENTS_HOME:-$HOME/.agents}/skills"
CANONICAL="$AGENTS_ROOT/gov-ydfdev-browser"
CLAUDE_DEST="${CLAUDE_HOME:-$HOME/.claude}/skills/gov-ydfdev-browser"
NEEDS_CLAUDE=0

case "$TARGET" in
  agents|codex) ;;
  claude|all) NEEDS_CLAUDE=1 ;;
  *)
    echo "Usage: $0 [codex|claude|agents|all]" >&2
    exit 2
    ;;
esac

if [ ! -f "$SKILL_SOURCE/SKILL.md" ] || [ ! -s "$VERSION_FILE" ]; then
  echo "Incomplete gov-ydfdev-browser skill source in $PACKAGE_ROOT" >&2
  exit 1
fi
SKILL_VERSION=$(tr -d '\r\n' < "$VERSION_FILE")
if [ -z "$SKILL_VERSION" ]; then
  echo "Empty VERSION in $PACKAGE_ROOT" >&2
  exit 1
fi
if [ "$NEEDS_CLAUDE" -eq 1 ] && [ ! -L "$CLAUDE_DEST" ] && [ -e "$CLAUDE_DEST" ]; then
  echo "Refusing to replace non-link Claude Code skill target: $CLAUDE_DEST" >&2
  exit 1
fi

mkdir -p "$AGENTS_ROOT"
STAGE=$(mktemp -d "$AGENTS_ROOT/.gov-ydfdev-browser.XXXXXX")
trap 'rm -rf "$STAGE"' EXIT HUP INT TERM
cp -R "$SKILL_SOURCE/." "$STAGE"
printf '%s\n' "$SKILL_VERSION" > "$STAGE/VERSION"
if [ -d "$CANONICAL" ] && [ ! -L "$CANONICAL" ]; then
  chmod -R u+w "$CANONICAL"
fi
rm -rf "$CANONICAL"
mv "$STAGE" "$CANONICAL"
trap - EXIT HUP INT TERM
echo "Installed gov-ydfdev-browser skill to $CANONICAL"

if [ "$NEEDS_CLAUDE" -eq 1 ]; then
  if [ -L "$CLAUDE_DEST" ] && [ "$(readlink "$CLAUDE_DEST")" = "$CANONICAL" ]; then
    :
  else
    mkdir -p "$(dirname "$CLAUDE_DEST")"
    rm -f "$CLAUDE_DEST"
    ln -s "$CANONICAL" "$CLAUDE_DEST"
  fi
  echo "Linked Claude Code skill at $CLAUDE_DEST"
fi

echo "Restart your agent tool to pick up new skills."
