#!/usr/bin/env bash
set -euo pipefail

# Build the Meeting Processor macOS .app + .dmg.
#
# The Python payload (the meeting_processor package + built SPA, requirements,
# and default config) is NOT bundled via Tauri's `resources` mechanism: its
# glob either flattens the directory tree or forces every `cargo build` to
# pre-stage files. Instead we let Tauri build a lean .app, then inject the
# payload straight into `Contents/Resources/` (preserving structure) and sign.
# The DMG is built with `hdiutil` (no fragile AppleScript/Finder dependency).
#
#   1. build the React SPA into the Python package
#   2. tauri build (.app only)
#   3. inject meeting_processor/ + requirements.txt + config.default.yaml into Resources
#   4. ad-hoc codesign the whole bundle (covers the injected files)
#   5. package a .dmg with hdiutil

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESKTOP="$ROOT/desktop"
BUNDLE="$DESKTOP/src-tauri/target/release/bundle"
APP="$BUNDLE/macos/Meeting Processor.app"
RES="$APP/Contents/Resources"
DMG="$BUNDLE/dmg/Meeting Processor_1.0.0_aarch64.dmg"

echo "==> 1/5 Building SPA"
( cd "$ROOT/frontend" && { [ -d node_modules ] || npm install; } && npm run build )

echo "==> 2/5 tauri build (.app)"
( cd "$DESKTOP/src-tauri" && npx --yes @tauri-apps/cli@^2 build --bundles app )

echo "==> 3/5 Injecting Python payload into Resources"
rsync -a --delete \
  --exclude '__pycache__' --exclude '*.pyc' \
  "$ROOT/meeting_processor/" "$RES/meeting_processor/"
cp "$ROOT/requirements.txt" "$RES/requirements.txt"
cp "$DESKTOP/src-tauri/resources/config.default.yaml" "$RES/config.default.yaml"

echo "==> 4/5 Ad-hoc codesign"
codesign --force --deep --sign - "$APP"

echo "==> 5/5 Packaging .dmg (hdiutil)"
mkdir -p "$(dirname "$DMG")"
STAGING="$(mktemp -d)"
cp -R "$APP" "$STAGING/"
ln -s /Applications "$STAGING/Applications"
rm -f "$DMG"
hdiutil create -volname "Meeting Processor" -srcfolder "$STAGING" -ov -format UDZO "$DMG" >/dev/null
rm -rf "$STAGING"

echo "Done."
echo "App: $APP"
echo "DMG: $DMG"
