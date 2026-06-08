# Linux AppImage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the Meeting Processor desktop app as a fully self-contained Linux AppImage (bundled relocatable Python 3.11 + CPU-only torch/whisper + static ffmpeg), built by a local script and a GitHub Actions workflow.

**Architecture:** The existing `desktop/` Tauri crate gains a `platform.rs` module (Approach B) that isolates every OS difference behind a few functions. On Linux everything is bundled, so `check_prerequisites` short-circuits to all-OK and the existing JS flow goes straight to starting the bundled server; no detection/install/bootstrap. The hard work is the build script that assembles an AppDir and folds it into an AppImage with `linuxdeploy`.

**Tech Stack:** Rust (Tauri v2), `cfg(target_os)`; python-build-standalone (relocatable CPython 3.11); CPU-only PyTorch wheels; johnvansickle static ffmpeg; linuxdeploy + appimage plugin; GitHub Actions (ubuntu-22.04).

**Reference spec:** `docs/superpowers/specs/2026-06-08-linux-appimage-design.md`

**IMPORTANT — where things run:** Tasks 1–2 (Rust) build and unit-test on macOS (and any OS) via `cargo test`. Tasks 3–5 (build script, CI, docs) are authored and **syntax-checked** here but only fully execute on Linux/CI — their real validation is triggering the GitHub Actions workflow. Do not attempt to run `build-linux.sh` on macOS.

---

## File Structure

**New:**
- `desktop/src-tauri/src/platform.rs` — OS-difference isolation (pure path builders + cfg-gated dispatch) + unit tests.
- `desktop/linux/meeting-processor.desktop` — AppImage menu entry.
- `desktop/build-linux.sh` — assemble AppDir → AppImage.
- `.github/workflows/linux-appimage.yml` — CI build on ubuntu-22.04.

**Modified:**
- `desktop/src-tauri/src/lib.rs` — declare `mod platform;`.
- `desktop/src-tauri/src/paths.rs` — `shell_path()` gated to macOS (it becomes the macOS arm of `platform::extra_path()`).
- `desktop/src-tauri/src/setup.rs` — `check_prerequisites` short-circuits on Linux; PATH via `platform::extra_path()`.
- `desktop/src-tauri/src/server.rs` — Python/package/PATH via `platform::*`.
- `desktop/README.md` — Linux build + smoke instructions.

---

## Phase 1 — `platform.rs` module

### Task 1.1: Create `platform.rs` with pure path builders + tests

**Files:**
- Create: `desktop/src-tauri/src/platform.rs`
- Modify: `desktop/src-tauri/src/lib.rs`

- [ ] **Step 1: Write `platform.rs`** (pure builders are compiled on all OSes and unit-tested; the cfg-gated dispatch selects per-OS)

```rust
//! Isolates OS differences: where the Python interpreter, ffmpeg, and the
//! `meeting_processor` package live, and whether first-run bootstrap is needed.
//!
//! macOS bootstraps a venv from system Python on first run; Linux ships a
//! fully self-contained AppImage (relocatable Python + ML deps + ffmpeg all
//! bundled), so it needs no bootstrap and starts the server immediately.
use std::path::{Path, PathBuf};
use tauri::AppHandle;

// ---- Pure path builders (compiled on every platform → unit-tested here) ----

/// macOS: the venv python created during bootstrap, under the data dir.
pub fn macos_python(data_dir: &Path) -> PathBuf {
    data_dir.join(".venv").join("bin").join("python")
}

/// Linux: the relocatable python3.11 bundled in the AppImage.
pub fn linux_python(appdir: &Path) -> PathBuf {
    appdir.join("usr").join("python").join("bin").join("python3.11")
}

/// Linux: directory placed on PYTHONPATH (contains `meeting_processor/`).
pub fn linux_package_dir(appdir: &Path) -> PathBuf {
    appdir.join("usr").join("lib")
}

/// Linux: directory containing the bundled `ffmpeg`.
pub fn linux_bin_dir(appdir: &Path) -> PathBuf {
    appdir.join("usr").join("bin")
}

// ---- cfg-gated public interface ----

/// Does this OS need the first-run detect/install/bootstrap flow?
#[cfg(target_os = "macos")]
pub fn needs_bootstrap() -> bool {
    true
}
#[cfg(not(target_os = "macos"))]
pub fn needs_bootstrap() -> bool {
    false
}

/// The AppImage mount point. Falls back to "." when run outside an AppImage
/// (e.g. a bare `cargo run` during Linux development).
#[cfg(not(target_os = "macos"))]
fn appdir() -> PathBuf {
    std::env::var("APPDIR")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("."))
}

/// Absolute path to the Python interpreter that runs the server.
#[cfg(target_os = "macos")]
pub fn python(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(macos_python(&crate::paths::data_dir(app)?))
}
#[cfg(not(target_os = "macos"))]
pub fn python(_app: &AppHandle) -> Result<PathBuf, String> {
    Ok(linux_python(&appdir()))
}

/// Directory to put on PYTHONPATH so `import meeting_processor` resolves.
#[cfg(target_os = "macos")]
pub fn package_dir(app: &AppHandle) -> Result<PathBuf, String> {
    crate::paths::resource_dir(app)
}
#[cfg(not(target_os = "macos"))]
pub fn package_dir(_app: &AppHandle) -> Result<PathBuf, String> {
    Ok(linux_package_dir(&appdir()))
}

/// PATH for spawned processes, with the platform's tool dirs prepended.
#[cfg(target_os = "macos")]
pub fn extra_path() -> String {
    crate::paths::shell_path()
}
#[cfg(not(target_os = "macos"))]
pub fn extra_path() -> String {
    let bin = linux_bin_dir(&appdir());
    match std::env::var("PATH") {
        Ok(p) if !p.is_empty() => format!("{}:{}", bin.display(), p),
        _ => bin.display().to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::Path;

    #[test]
    fn macos_python_is_under_data_venv() {
        let p = macos_python(Path::new("/data"));
        assert_eq!(p, Path::new("/data/.venv/bin/python"));
    }

    #[test]
    fn linux_python_is_under_appdir() {
        let p = linux_python(Path::new("/mnt/app"));
        assert_eq!(p, Path::new("/mnt/app/usr/python/bin/python3.11"));
    }

    #[test]
    fn linux_package_dir_is_usr_lib() {
        assert_eq!(linux_package_dir(Path::new("/mnt/app")), Path::new("/mnt/app/usr/lib"));
    }

    #[test]
    fn linux_bin_dir_is_usr_bin() {
        assert_eq!(linux_bin_dir(Path::new("/mnt/app")), Path::new("/mnt/app/usr/bin"));
    }
}
```

- [ ] **Step 2: Declare the module in `lib.rs`** — add `pub mod platform;` to the module list. The list becomes:

```rust
pub mod paths;
pub mod platform;
pub mod port;
pub mod prereq;
pub mod server;
pub mod setup;
pub mod state;
```

(keep the existing `use server::ServerProcess;` / `use tauri::{Manager, WindowEvent};` and the `run()` fn below it unchanged.)

- [ ] **Step 3: Build + run the new tests** (timeout 600000)

Run: `cd desktop/src-tauri && cargo test platform::tests`
Expected: 4 tests PASS.

- [ ] **Step 4: Full test run** — `cargo test`
Expected: 18 tests pass (14 existing + 4 new).

- [ ] **Step 5: Commit**

```bash
git add desktop/src-tauri/src/platform.rs desktop/src-tauri/src/lib.rs
git commit -m "feat(desktop): platform module isolating macOS/Linux differences

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 1.2: Wire `platform::*` into setup.rs / server.rs / paths.rs (macOS behavior unchanged)

**Files:**
- Modify: `desktop/src-tauri/src/setup.rs`
- Modify: `desktop/src-tauri/src/server.rs`
- Modify: `desktop/src-tauri/src/paths.rs`

- [ ] **Step 1: `paths.rs` — gate `shell_path()` to macOS.** It is now only used by the macOS arm of `platform::extra_path()`. Change its signature line from:

```rust
pub fn shell_path() -> String {
```
to:
```rust
#[cfg(target_os = "macos")]
pub fn shell_path() -> String {
```
(leave the body unchanged.)

- [ ] **Step 2: `setup.rs` — import platform and short-circuit `check_prerequisites` on non-macOS.** At the top of the file, after `use crate::paths;`, add:

```rust
use crate::platform;
```

Then change `check_prerequisites` so its first lines are:

```rust
#[tauri::command]
pub async fn check_prerequisites(app: AppHandle) -> Result<Prerequisites, String> {
    // Non-macOS (Linux AppImage) ships everything bundled — nothing to detect.
    if !platform::needs_bootstrap() {
        return Ok(Prerequisites {
            brew: Status::Ok,
            python311: Status::Ok,
            ffmpeg: Status::Ok,
            venv: Status::Ok,
        });
    }

    let (brew_out, _) = capture(brew_path(), &["--version"]).await;
    // …rest of the existing macOS detection unchanged…
```

- [ ] **Step 3: `setup.rs` — route the PATH through `platform::extra_path()`.** In `capture`, change `.env("PATH", paths::shell_path())` to `.env("PATH", platform::extra_path())`. In `run_streamed`, change `.env("PATH", paths::shell_path())` to `.env("PATH", platform::extra_path())`. (Two occurrences total.)

- [ ] **Step 4: `server.rs` — use the platform interface.** Add `use crate::platform;` near the top (alongside `use crate::paths;`). Then in `start_server`, replace the three resolution lines:

Replace:
```rust
    let resources = paths::resource_dir(&app)?;
    let python = paths::venv_python(&app)?;
```
with:
```rust
    let resources = platform::package_dir(&app)?;
    let python = platform::python(&app)?;
```

And replace the PATH env line:
```rust
        .env("PATH", paths::shell_path())
```
with:
```rust
        .env("PATH", platform::extra_path())
```

(Everything else in `start_server` — `MEETING_DATA_DIR`, PYTHONPATH from `resources`, cwd, log capture, health-poll, kill — stays the same. On macOS `platform::python`/`package_dir`/`extra_path` return exactly what the old code did, so behavior is identical.)

- [ ] **Step 5: Build + test** (timeout 600000)

Run: `cd desktop/src-tauri && cargo build && cargo test`
Expected: zero errors; 18 tests pass. Note: `paths::venv_python` is still used by `check_prerequisites` (the macOS venv-existence check), so it is NOT dead code — no `#[allow(dead_code)]` needed.

- [ ] **Step 6: Re-verify macOS app still builds end-to-end** (the macOS path must be unaffected)

Run: `./desktop/build.sh 2>&1 | tail -5`
Expected: ends with `App:` and `DMG:` lines (the macOS `.app`/`.dmg` still build). This confirms the refactor didn't break macOS.

- [ ] **Step 7: Commit**

```bash
git add desktop/src-tauri/src/setup.rs desktop/src-tauri/src/server.rs desktop/src-tauri/src/paths.rs
git commit -m "refactor(desktop): route OS-specific paths through platform module

macOS behavior is identical (platform::* returns the same values); Linux now
resolves the bundled python/ffmpeg/package and skips the bootstrap flow.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase 2 — Linux build script

### Task 2.1: `.desktop` entry

**Files:**
- Create: `desktop/linux/meeting-processor.desktop`

- [ ] **Step 1: Create the desktop entry**

```ini
[Desktop Entry]
Type=Application
Name=Meeting Processor
Exec=meeting-processor
Icon=meeting-processor
Categories=Utility;
Terminal=false
```

- [ ] **Step 2: Commit**

```bash
git add desktop/linux/meeting-processor.desktop
git commit -m "feat(desktop): Linux .desktop entry for AppImage

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 2.2: `build-linux.sh`

**Files:**
- Create: `desktop/build-linux.sh`

- [ ] **Step 1: Write the script**

```bash
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
```

- [ ] **Step 2: Make it executable + syntax-check** (cannot run on macOS)

Run: `chmod +x desktop/build-linux.sh && bash -n desktop/build-linux.sh && echo SYNTAX_OK`
Expected: `SYNTAX_OK`.

- [ ] **Step 3: Verify the referenced binary name matches the crate.** The Tauri binary name is the package name from `desktop/src-tauri/Cargo.toml` (`meeting-processor-desktop`), so the release artifact is `target/release/meeting-processor-desktop`. Confirm the `cp` in step 5 uses that exact name.

Run: `grep '^name' desktop/src-tauri/Cargo.toml | head -1`
Expected: `name = "meeting-processor-desktop"` — matches the `cp .../target/release/meeting-processor-desktop` line.

- [ ] **Step 4: Commit**

```bash
git add desktop/build-linux.sh
git commit -m "build(desktop): Linux AppImage assembly script (self-contained)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase 3 — CI workflow

### Task 3.1: GitHub Actions workflow

**Files:**
- Create: `.github/workflows/linux-appimage.yml`

- [ ] **Step 1: Write the workflow**

```yaml
name: Linux AppImage

on:
  workflow_dispatch: {}
  push:
    tags:
      - "v*"

jobs:
  build:
    runs-on: ubuntu-22.04
    steps:
      - uses: actions/checkout@v4

      - name: Install system dependencies
        run: |
          sudo apt-get update
          sudo apt-get install -y \
            libwebkit2gtk-4.1-dev \
            libgtk-3-dev \
            libayatana-appindicator3-dev \
            librsvg2-dev \
            fuse \
            rsync

      - uses: actions/setup-node@v4
        with:
          node-version: "20"

      - name: Install Rust
        uses: dtolnay/rust-toolchain@stable

      - name: Build AppImage
        run: ./desktop/build-linux.sh

      - name: Smoke-test the bundled Python
        run: |
          ./desktop/build/linux/AppDir/usr/python/bin/python3.11 \
            -c "import torch, whisper, fastapi; print('bundled deps OK', torch.__version__)"

      - name: Upload AppImage artifact
        uses: actions/upload-artifact@v4
        with:
          name: meeting-processor-linux-appimage
          path: desktop/build/linux/Meeting_Processor-x86_64.AppImage

      - name: Attach to release (tags only)
        if: startsWith(github.ref, 'refs/tags/')
        uses: softprops/action-gh-release@v2
        with:
          files: desktop/build/linux/Meeting_Processor-x86_64.AppImage
```

- [ ] **Step 2: Validate the YAML parses**

Run: `python3 -c "import yaml,sys; yaml.safe_load(open('.github/workflows/linux-appimage.yml')); print('YAML_OK')"` (or use `.venv/bin/python`)
Expected: `YAML_OK`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/linux-appimage.yml
git commit -m "ci(desktop): GitHub Actions workflow to build the Linux AppImage

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase 4 — Docs

### Task 4.1: README — Linux section

**Files:**
- Modify: `desktop/README.md`

- [ ] **Step 1: Append a Linux section** to `desktop/README.md` (after the existing macOS content):

````markdown

## Linux (AppImage)

Fully self-contained: the AppImage bundles a relocatable Python 3.11, CPU-only
torch + whisper, a static ffmpeg, and the app. Friends download one file, no
install or first-run download.

### Build

Must build on Linux (ubuntu-22.04 baseline). Locally:

```bash
./desktop/build-linux.sh
# → desktop/build/linux/Meeting_Processor-x86_64.AppImage
```

Or trigger the **Linux AppImage** GitHub Actions workflow (manual run, or push a
`v*` tag to attach it to a release).

### Run

```bash
chmod +x Meeting_Processor-x86_64.AppImage
./Meeting_Processor-x86_64.AppImage
```

Data lives in `~/.local/share/com.meetingprocessor.desktop/`.

### Manual smoke checklist (on a real Linux box)

- [ ] Launch the AppImage → the SPA loads at `/ui` with no setup screen.
- [ ] Process one recording end-to-end → exercises the bundled ffmpeg + CPU torch.
- [ ] Confirm `vault/` and logs appear under `~/.local/share/com.meetingprocessor.desktop/`.
- [ ] Quit → `pgrep -fl "meeting_processor web"` shows nothing (server killed).
````

- [ ] **Step 2: Commit**

```bash
git add desktop/README.md
git commit -m "docs(desktop): Linux AppImage build + smoke instructions

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 4.2: Trigger the real CI build (validation)

**Files:** none (validation via CI).

- [ ] **Step 1:** Push the branch and run the workflow. The branch must be on GitHub first:

```bash
git push -u origin "$(git branch --show-current)"
```

- [ ] **Step 2:** Trigger the workflow manually (Actions tab → "Linux AppImage" → Run workflow), or via CLI:

```bash
gh workflow run "Linux AppImage" --ref "$(git branch --show-current)"
```

- [ ] **Step 3:** Watch it and confirm green — especially the "Smoke-test the bundled Python" step printing `bundled deps OK`. Download the artifact.

Run: `gh run watch "$(gh run list --workflow="Linux AppImage" --limit 1 --json databaseId --jq '.[0].databaseId')"`
Expected: the run completes successfully; the AppImage artifact is uploaded.

- [ ] **Step 4 (manual, on a Linux box):** Walk the README smoke checklist. If anything fails, fix the relevant script/module and re-run the workflow.

---

## Self-Review Notes

- **Spec coverage:** platform.rs interface (Task 1.1) + wiring (1.2); AppImage layout + build (2.2); .desktop (2.1); CI on ubuntu-22.04 with smoke (3.1); README + manual smoke (4.1); real-build validation (4.2). CPU-only torch pin is in build-linux.sh step 4. Relocatable Python rationale is documented in platform.rs and build-linux.sh. python-under-usr/python (to keep linuxdeploy away) is in build-linux.sh step 7 comment.
- **macOS untouched:** `platform::*` returns the same values the old code used; Task 1.2 step 6 re-runs `build.sh` to confirm.
- **Binary name consistency:** crate `[lib] name` is `meeting_processor_desktop_lib`, but the *binary/package* name is `meeting-processor-desktop` → release artifact `target/release/meeting-processor-desktop` (Task 2.2 step 3 verifies).
- **Known follow-ups (out of scope per spec):** `.deb`/`.rpm`, ARM Linux, auto-update.
