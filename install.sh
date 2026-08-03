#!/bin/sh
set -eu

RELEASE_VERSION="1.0.0"
SOURCE_COMMIT="4106f432d6073ef9ad12dce04a961a708ee0432d"
SOURCE_URL="https://github.com/harrynguyen/unified-brain/archive/4106f432d6073ef9ad12dce04a961a708ee0432d.tar.gz"
ARTIFACT_URL="https://github.com/harrynguyen/unified-brain/releases/download/v1.0.0/unified_brain_kg-1.0.0-py3-none-any.whl"
CHECKSUM_URL="https://github.com/harrynguyen/unified-brain/releases/download/v1.0.0/SHA256SUMS"
EXPECTED_KG_VERSION="kg 1.0.0"

TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/kg-install-XXXXXX")
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT HUP INT TERM

printf '%s\n' "Installing kg $RELEASE_VERSION from commit $SOURCE_COMMIT"
printf '%s\n' 'The installer mutates no harness files.'
printf '%s\n' 'After install, ensure ~/.local/bin is on PATH.'

curl -fsSL "$SOURCE_URL" -o "$TMP_DIR/source.tar.gz"
curl -fsSL "$ARTIFACT_URL" -o "$TMP_DIR/artifact.whl"
curl -fsSL "$CHECKSUM_URL" -o "$TMP_DIR/SHA256SUMS"
(
    cd "$TMP_DIR"
    shasum -a 256 -c SHA256SUMS
)

uv tool install --from "$TMP_DIR/source.tar.gz"
KG_BIN=$(command -v kg || true)
if [ -z "$KG_BIN" ] && [ -x "$HOME/.local/bin/kg" ]; then KG_BIN="$HOME/.local/bin/kg"; fi
[ -n "$KG_BIN" ] || { printf '%s\n' 'kg executable not found after install' >&2; exit 1; }
ACTUAL_VERSION=$($KG_BIN --version)
[ "$ACTUAL_VERSION" = "$EXPECTED_KG_VERSION" ] || {
    printf '%s\n' "version mismatch: $ACTUAL_VERSION" >&2
    printf '%s\n' 'Upgrade guidance: verify the pinned release metadata.' >&2
    printf '%s\n' 'Rollback guidance: uv tool uninstall unified-brain-kg.' >&2
    exit 1
}
printf '%s\n' "Installed $ACTUAL_VERSION at $KG_BIN"
printf '%s\n' 'PATH guidance: export PATH="$HOME/.local/bin:$PATH"'
