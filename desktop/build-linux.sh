#!/usr/bin/env bash
set -euo pipefail

# Build the Meeting Processor Linux AppImage (x86_64), fully self-contained:
# a relocatable Python 3.11 with CPU-only torch + whisper, a static ffmpeg, the
# meeting_processor package + built SPA, and the Tauri binary — all packed by
# linuxdeploy (which also bundles WebKitGTK for the binary).
#
# RUN ON LINUX ONLY (ubuntu-22.04 baseline for broad glibc compatibility).
# Requires: bash, curl, tar, rsync, sha256sum, rustup/cargo, node/npm, and the
# system WebKitGTK dev libs (the CI workflow installs these).
#
# Supply chain: every external binary is pinned and SHA-256-verified before use,
# and Python deps are installed with --require-hashes from a committed lockfile
# (generate it once with desktop/lock-linux-deps.sh; the build fails closed if
# it is missing or a hash mismatches).

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESKTOP="$ROOT/desktop"
WORK="$DESKTOP/build/linux"
APPDIR="$WORK/AppDir"
LOCK="$DESKTOP/requirements-linux.lock"

# --- Pinned, SHA-256-verified external artifacts ----------------------------
# Refresh a hash here only after manually vetting the new upstream binary.
PY_URL="https://github.com/indygreg/python-build-standalone/releases/download/20240814/cpython-3.11.9+20240814-x86_64-unknown-linux-gnu-install_only.tar.gz"
PY_SHA="9a332ba354f3b4e8a96a15db6b2805a7a31dcc1b6b9c1b7b93e5246949fbb50f"
# Static ffmpeg from BtbN/FFmpeg-Builds (GitHub-hosted, reproducible CI builds).
FFMPEG_URL="https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-n7.1-latest-linux64-gpl-7.1.tar.xz"
FFMPEG_SHA="d86cd6d95b497ac3bbaa643b5e2202ff08b6a527415c19fabee05e12628eccfb"
LD_URL="https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-x86_64.AppImage"
LD_SHA="514d4ffe2a2f757369b41863a4f63fbbb222c429652803ebc081cb16ba21ac25"
LDP_URL="https://github.com/linuxdeploy/linuxdeploy-plugin-appimage/releases/download/continuous/linuxdeploy-plugin-appimage-x86_64.AppImage"
LDP_SHA="e0129b8070e0c7b37151027e46e9fa44fe97ea29e3692705a2c5cff3771d3121"

# Download $1 to $2 and verify it matches sha256 $3 (fail closed on mismatch).
fetch_verified() {
  local url="$1" out="$2" sha="$3"
  curl -fsSL -o "$out" "$url"
  echo "${sha}  ${out}" | sha256sum -c -
}

if [ ! -f "$LOCK" ]; then
  echo "ERROR: $LOCK is missing." >&2
  echo "Generate it on Linux with: desktop/lock-linux-deps.sh  (then commit it)." >&2
  echo "It is required so Python deps install with --require-hashes." >&2
  exit 1
fi

echo "==> 1/7 Building SPA"
( cd "$ROOT/frontend" && { [ -d node_modules ] || npm install; } && npm run build )

echo "==> 2/7 Building Tauri binary (release)"
( cd "$DESKTOP/src-tauri" && cargo build --release )

echo "==> 3/7 Resetting AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/lib" "$WORK/tools"

echo "==> 4/7 Bundling relocatable Python 3.11 + hash-pinned deps"
fetch_verified "$PY_URL" "$WORK/tools/python.tar.gz" "$PY_SHA"
tar -xzf "$WORK/tools/python.tar.gz" -C "$APPDIR/usr"   # extracts to $APPDIR/usr/python
PY="$APPDIR/usr/python/bin/python3.11"
# Install everything from the committed, hashed lockfile. The CPU torch wheel
# lives on the pytorch index; the rest on PyPI. --require-hashes verifies each.
"$PY" -m pip install \
  --require-hashes \
  --index-url https://download.pytorch.org/whl/cpu \
  --extra-index-url https://pypi.org/simple \
  -r "$LOCK"

echo "==> 5/7 Bundling static ffmpeg + payload"
fetch_verified "$FFMPEG_URL" "$WORK/tools/ffmpeg.tar.xz" "$FFMPEG_SHA"
tar -xJf "$WORK/tools/ffmpeg.tar.xz" -C "$WORK/tools"
ffmpeg_bin=( "$WORK"/tools/ffmpeg-*-linux64-gpl-*/bin/ffmpeg )
[[ ${#ffmpeg_bin[@]} -eq 1 && -f "${ffmpeg_bin[0]}" ]] \
  || { echo "ERROR: unexpected ffmpeg layout: ${ffmpeg_bin[*]}"; exit 1; }
cp "${ffmpeg_bin[0]}" "$APPDIR/usr/bin/ffmpeg"
rsync -a --delete --exclude '__pycache__' --exclude '*.pyc' \
  "$ROOT/meeting_processor/" "$APPDIR/usr/lib/meeting_processor/"
cp "$DESKTOP/src-tauri/resources/config.default.yaml" "$APPDIR/usr/lib/config.default.yaml"
cp "$DESKTOP/src-tauri/target/release/meeting-processor-desktop" "$APPDIR/usr/bin/meeting-processor"
cp "$DESKTOP/linux/meeting-processor.desktop" "$APPDIR/meeting-processor.desktop"
cp "$DESKTOP/src-tauri/icons/icon.png" "$APPDIR/meeting-processor.png"

echo "==> 6/7 Fetching linuxdeploy (verified)"
fetch_verified "$LD_URL" "$WORK/tools/linuxdeploy-x86_64.AppImage" "$LD_SHA"
fetch_verified "$LDP_URL" "$WORK/tools/linuxdeploy-plugin-appimage-x86_64.AppImage" "$LDP_SHA"
chmod +x "$WORK/tools/linuxdeploy-x86_64.AppImage" "$WORK/tools/linuxdeploy-plugin-appimage-x86_64.AppImage"

echo "==> 7/7 Packaging AppImage"
# Python lives under usr/python (NOT usr/bin), so linuxdeploy only deploys deps
# for the Tauri binary (WebKitGTK etc.) and leaves the bundled interpreter alone.
# APPIMAGE_EXTRACT_AND_RUN lets the linuxdeploy AppImages run without FUSE
# (GitHub Actions containers lack it).
export APPIMAGE_EXTRACT_AND_RUN=1
cd "$WORK"
OUTPUT="Meeting_Processor-x86_64.AppImage" \
"$WORK/tools/linuxdeploy-x86_64.AppImage" \
  --appdir "$APPDIR" \
  --executable "$APPDIR/usr/bin/meeting-processor" \
  --desktop-file "$APPDIR/meeting-processor.desktop" \
  --icon-file "$APPDIR/meeting-processor.png" \
  --output appimage

echo "Done. AppImage at: $WORK/Meeting_Processor-x86_64.AppImage"
