#!/usr/bin/env bash
set -euo pipefail

# Build the Meeting Processor Linux AppImage (x86_64), fully self-contained:
# a relocatable Python 3.11 with CPU-only torch + whisper, a static ffmpeg, the
# meeting_processor package + built SPA, and the Tauri binary — all packed by
# linuxdeploy (which also bundles WebKitGTK for the binary).
#
# RUN ON LINUX ONLY (ubuntu-22.04 baseline for broad glibc compatibility).
# Requires: bash, curl, tar, rsync, rustup/cargo, node/npm, and the system
# WebKitGTK dev libs (the CI workflow installs these).

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESKTOP="$ROOT/desktop"
WORK="$DESKTOP/build/linux"
APPDIR="$WORK/AppDir"

# Pinned, relocatable CPython 3.11 (install_only = ready-to-use, no build step).
PY_URL="https://github.com/indygreg/python-build-standalone/releases/download/20240814/cpython-3.11.9+20240814-x86_64-unknown-linux-gnu-install_only.tar.gz"
# Static ffmpeg (no dynamic deps).
FFMPEG_URL="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
# Bundler tools.
LD_URL="https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-x86_64.AppImage"
LDP_URL="https://github.com/linuxdeploy/linuxdeploy-plugin-appimage/releases/download/continuous/linuxdeploy-plugin-appimage-x86_64.AppImage"

echo "==> 1/7 Building SPA"
( cd "$ROOT/frontend" && { [ -d node_modules ] || npm install; } && npm run build )

echo "==> 2/7 Building Tauri binary (release)"
( cd "$DESKTOP/src-tauri" && cargo build --release )

echo "==> 3/7 Resetting AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/lib" "$WORK/tools"

echo "==> 4/7 Bundling relocatable Python 3.11 + CPU deps"
curl -fsSL "$PY_URL" | tar -xz -C "$APPDIR/usr"   # extracts to $APPDIR/usr/python
PY="$APPDIR/usr/python/bin/python3.11"
"$PY" -m pip install --upgrade pip
# CPU-only torch FIRST so the heavy CUDA wheel is never pulled; then the rest
# (requirements.txt's torch constraint is already satisfied).
"$PY" -m pip install torch --index-url https://download.pytorch.org/whl/cpu
"$PY" -m pip install -r "$ROOT/requirements.txt"

echo "==> 5/7 Bundling static ffmpeg + payload"
curl -fsSL "$FFMPEG_URL" | tar -xJ -C "$WORK/tools"
cp "$WORK"/tools/ffmpeg-*-amd64-static/ffmpeg "$APPDIR/usr/bin/ffmpeg"
rsync -a --delete --exclude '__pycache__' --exclude '*.pyc' \
  "$ROOT/meeting_processor/" "$APPDIR/usr/lib/meeting_processor/"
cp "$DESKTOP/src-tauri/resources/config.default.yaml" "$APPDIR/usr/lib/config.default.yaml"
cp "$DESKTOP/src-tauri/target/release/meeting-processor-desktop" "$APPDIR/usr/bin/meeting-processor"
cp "$DESKTOP/linux/meeting-processor.desktop" "$APPDIR/meeting-processor.desktop"
cp "$DESKTOP/src-tauri/icons/icon.png" "$APPDIR/meeting-processor.png"

echo "==> 6/7 Fetching linuxdeploy"
for url in "$LD_URL" "$LDP_URL"; do
  f="$WORK/tools/$(basename "$url")"
  [ -f "$f" ] || curl -fsSL -o "$f" "$url"
  chmod +x "$f"
done

echo "==> 7/7 Packaging AppImage"
# Python lives under usr/python (NOT usr/bin), so linuxdeploy only deploys deps
# for the Tauri binary (WebKitGTK etc.) and leaves the bundled interpreter alone.
cd "$WORK"
OUTPUT="Meeting_Processor-x86_64.AppImage" \
"$WORK/tools/linuxdeploy-x86_64.AppImage" \
  --appdir "$APPDIR" \
  --executable "$APPDIR/usr/bin/meeting-processor" \
  --desktop-file "$APPDIR/meeting-processor.desktop" \
  --icon-file "$APPDIR/meeting-processor.png" \
  --output appimage

echo "Done. AppImage at: $WORK/Meeting_Processor-x86_64.AppImage"
