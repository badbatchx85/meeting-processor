#!/usr/bin/env bash
set -euo pipefail

# Generate the hash-pinned lockfile used by the Linux AppImage build.
#
# RUN ON LINUX with Python 3.11 (the CPU-only torch wheels are Linux-specific,
# so the hashes must be resolved on Linux). Commit the resulting
# desktop/requirements-linux.lock; build-linux.sh installs from it with
# --require-hashes and fails closed if it is missing or a hash mismatches.
#
# Re-run this whenever requirements.txt changes, then commit the new lock.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESKTOP="$ROOT/desktop"
LOCK="$DESKTOP/requirements-linux.lock"

command -v python3.11 >/dev/null 2>&1 \
  || { echo "ERROR: python3.11 not found on PATH (run on Linux with 3.11)."; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
python3.11 -m venv "$TMP/venv"
"$TMP/venv/bin/pip" install --quiet pip-tools

# Resolve against the CPU torch index + PyPI, emitting a hash for every wheel.
"$TMP/venv/bin/pip-compile" \
  --quiet \
  --generate-hashes \
  --index-url https://download.pytorch.org/whl/cpu \
  --extra-index-url https://pypi.org/simple \
  --output-file "$LOCK" \
  "$ROOT/requirements.txt"

echo "Wrote $LOCK"
echo "Commit it: git add desktop/requirements-linux.lock && git commit"
