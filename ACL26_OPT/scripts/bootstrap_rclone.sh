#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${1:-$HOME/bin}"
RCLONE_URL="${RCLONE_URL:-https://downloads.rclone.org/rclone-current-linux-amd64.zip}"
EXAMPLE_CONF_SOURCE="${EXAMPLE_CONF_SOURCE:-$(cd "$(dirname "$0")/.." && pwd)/config/rclone.volctos.example.conf}"
WRITE_EXAMPLE_CONF="${WRITE_EXAMPLE_CONF:-0}"

if command -v rclone >/dev/null 2>&1; then
  echo "rclone already installed at $(command -v rclone)"
else
  tmpdir="$(mktemp -d)"
  trap 'rm -rf "$tmpdir"' EXIT
  curl -fsSL -o "$tmpdir/rclone.zip" "$RCLONE_URL"
  unzip -q "$tmpdir/rclone.zip" -d "$tmpdir"
  mkdir -p "$INSTALL_DIR"
  cp "$tmpdir"/rclone-*-linux-amd64/rclone "$INSTALL_DIR/rclone"
  chmod 755 "$INSTALL_DIR/rclone"
  echo "installed rclone to $INSTALL_DIR/rclone"
fi

mkdir -p "$HOME/.config/rclone"
if [ "$WRITE_EXAMPLE_CONF" = "1" ] && [ ! -f "$HOME/.config/rclone/rclone.conf" ]; then
  cp "$EXAMPLE_CONF_SOURCE" "$HOME/.config/rclone/rclone.conf"
  chmod 600 "$HOME/.config/rclone/rclone.conf"
  echo "wrote example rclone config to $HOME/.config/rclone/rclone.conf"
  echo "replace placeholder keys before using TOS staging"
fi

echo "rclone version:"
"${INSTALL_DIR}/rclone" version 2>/dev/null || rclone version
