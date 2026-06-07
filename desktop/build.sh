#!/usr/bin/env bash
set -euo pipefail

# Build the Meeting Processor macOS .app + .dmg.
#   1. build the React SPA into the Python package
#   2. stage the read-only payload (Python source + SPA + requirements + config)
#   3. tauri build
#   4. ad-hoc codesign (stable identity; not notarized)

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESKTOP="$ROOT/desktop"
RES="$DESKTOP/src-tauri/resources"

echo "==> 1/4 Building SPA"
( cd "$ROOT/frontend" && { [ -d node_modules ] || npm install; } && npm run build )

echo "==> 2/4 Staging resources"
rm -rf "$RES/meeting_processor"
rsync -a --delete \
  --exclude '__pycache__' --exclude '*.pyc' \
  "$ROOT/meeting_processor/" "$RES/meeting_processor/"
cp "$ROOT/requirements.txt" "$RES/requirements.txt"
[ -f "$RES/config.default.yaml" ] || cp "$ROOT/config.yaml" "$RES/config.default.yaml"

echo "==> 3/4 tauri build"
( cd "$DESKTOP/src-tauri" && npx --yes @tauri-apps/cli@^2 build )

APP="$DESKTOP/src-tauri/target/release/bundle/macos/Meeting Processor.app"
echo "==> 4/4 Ad-hoc codesign"
codesign --force --deep --sign - "$APP" || echo "codesign skipped"

echo "Done. App at: $APP"
echo "DMG at: $DESKTOP/src-tauri/target/release/bundle/dmg/"
