# Linux AppImage — Design

**Date:** 2026-06-08
**Status:** Approved (pending written-spec review)
**Topic:** Add a Linux AppImage build of the Meeting Processor desktop app, alongside the existing macOS `.app`.

## Goal

Ship the Meeting Processor desktop app as a single, fully self-contained Linux
**AppImage**: a friend downloads one file, `chmod +x`, double-clicks, and it
runs — no installs, no first-run download, no internet needed.

## Decisions (from brainstorming)

| Question | Decision |
|----------|----------|
| Package format | **AppImage** (portable, distro-agnostic) |
| Prerequisites | **Fully self-contained** — bundle Python 3.11 + static ffmpeg inside the AppImage |
| ML dependencies | **Bake everything in** — pre-installed torch (CPU) + whisper; zero first-run, fully offline |
| Build environment | **Both** — a local `build-linux.sh` and a GitHub Actions workflow that calls it |
| Code structure | **Approach B** — isolate all OS differences in one `platform.rs` module |

## Architecture

The existing `desktop/` Tauri crate gains Linux support. Because everything is
bundled, the Linux runtime is *simpler* than macOS: there is no prerequisite
detection, no install step, and no venv bootstrap. The shell starts the bundled
server immediately.

### `platform.rs` (Approach B)

One module quarantines every OS difference; `setup.rs`/`server.rs` call through it.

```
platform::needs_bootstrap() -> bool      // macOS: true   | Linux: false
platform::python() -> PathBuf            // macOS: <data>/.venv/bin/python
                                          // Linux: $APPDIR/usr/python/bin/python3.11
platform::package_dir() -> PathBuf       // macOS: resource_dir()
                                          // Linux: $APPDIR/usr/lib
platform::extra_path() -> Option<String> // dirs to prepend to PATH
                                          // macOS: Homebrew bins | Linux: $APPDIR/usr/bin
```

`$APPDIR` is the env var the AppImage runtime sets to its mount point.

### Behavioral changes (all localized)

- **`check_prerequisites`** — on Linux returns every field `ok` immediately
  (Python, ffmpeg, and the "venv" are bundled), so the existing setup-page JS
  flows straight to `launchServer()`. No detection / install / bootstrap UI.
  macOS path unchanged.
- **`bootstrap_venv` / `install_prerequisite`** — never invoked on Linux (the JS
  skips them when nothing is missing). They remain macOS-only.
- **`start_server`** — uses `platform::python()`, sets `PATH` from
  `platform::extra_path()` (bundled ffmpeg) and `PYTHONPATH` from
  `platform::package_dir()`. `MEETING_DATA_DIR`, health-poll, and kill-on-exit
  are already cross-platform.
- **Data dir** — `app_data_dir()` already resolves per-OS
  (`~/.local/share/com.meetingprocessor.desktop/` on Linux via XDG). No change.

## Build & packaging

### AppDir layout

```
AppDir/
  AppRun                      # sets APPDIR, execs the Tauri binary
  meeting-processor.desktop   # menu metadata
  meeting-processor.png       # icon (reuse the generated one)
  usr/
    bin/
      meeting-processor       # the Tauri binary (cargo build --release)
      ffmpeg                  # static ffmpeg (e.g. johnvansickle static build)
    python/                   # python-build-standalone 3.11 (relocatable)
      bin/python3.11
      lib/python3.11/site-packages/  # torch (CPU) + whisper + fastapi + … installed here
    lib/
      meeting_processor/      # the package + built SPA (web/spa)
      config.default.yaml
```

### `desktop/build-linux.sh` steps

1. `npm run build` → SPA into `meeting_processor/web/spa`.
2. `cargo build --release` (Linux) → the `meeting-processor` binary.
3. Fetch **python-build-standalone** 3.11 (x86_64 gnu) → `AppDir/usr/python`.
   It is relocatable, so it works from the AppImage's random mount path — this
   is *why* we bundle a pre-built interpreter rather than a venv, whose
   hardcoded shebangs/`pyvenv.cfg` paths would break after relocation.
4. `pip install` into that Python's site-packages, pinned to **CPU-only torch**
   (`--index-url https://download.pytorch.org/whl/cpu`). The default Linux torch
   wheel pulls ~2 GB of CUDA libs that are unneeded here; CPU-only keeps it to a
   few hundred MB and is correct for these machines.
5. Drop in a **static ffmpeg** binary, `meeting_processor/` (+ SPA),
   `config.default.yaml`, `AppRun`, the `.desktop` file, and the icon.
6. Run **`linuxdeploy` + `linuxdeploy-plugin-appimage`** (bundles WebKitGTK libs)
   → `Meeting Processor-x86_64.AppImage`.

**Realistic size:** with CPU-only torch, ~1.2–1.5 GB.

### Runtime wiring

`AppRun` execs the binary with `APPDIR` set. `platform::python()` →
`$APPDIR/usr/python/bin/python3.11`; `extra_path()` → `$APPDIR/usr/bin`;
`package_dir()` → `$APPDIR/usr/lib`. The server writes only to
`~/.local/share/com.meetingprocessor.desktop/`.

## CI workflow

`.github/workflows/linux-appimage.yml`:

- **Runner:** `ubuntu-22.04` — deliberately an older glibc baseline so the
  AppImage runs on a wide range of distros (AppImages are forward-, not
  backward-compatible).
- **Triggers:** `workflow_dispatch` (manual) + tag push `v*` (cut a release).
- **Steps:** checkout → install system deps (`libwebkit2gtk-4.1-dev`,
  `libgtk-3-dev`, libappindicator, `fuse`) → Rust + Node toolchains → run
  `desktop/build-linux.sh` → upload the `.AppImage` as a workflow artifact; on a
  tag, attach it to a GitHub Release.
- The workflow only *calls* `build-linux.sh`, so local and CI builds are
  identical (the "Both" requirement) — the script is the single source of truth.

## Error handling

Reuses the existing diagnostic path: if the bundled Python/ffmpeg is missing or
the server fails to boot, `start_server` already surfaces the `desktop.log` tail
in the ERROR state.

## Testing

- **Rust unit tests:** `platform.rs` path-assembly logic, unit-tested with a fake
  `APPDIR` (e.g. `python()`/`package_dir()` compose the expected paths). Existing
  `port`/`prereq`/`state` tests unchanged; macOS behavior stays green.
- **CI smoke step:** after building, run the AppImage under `xvfb-run` far enough
  to confirm it launches and `$APPDIR/usr/python/bin/python3.11 -m meeting_processor
  --help` works inside the AppDir (validates the relocatable Python + package
  import without a full GUI/transcription run).
- **Manual smoke (documented):** on a real Linux box — launch the AppImage,
  confirm the SPA loads at `/ui`, run one transcription end-to-end (exercises the
  bundled ffmpeg + CPU torch), confirm data lands in `~/.local/share/...`, and the
  server is killed on quit.

## Out of scope (YAGNI)

- `.deb`/`.rpm` packages (AppImage only).
- ARM Linux (x86_64 only for now).
- Notarization/signing equivalents (AppImages are typically unsigned; the macOS
  Gatekeeper concern has no direct Linux analog).
- Auto-update.

## Files

**New:**
- `desktop/src-tauri/src/platform.rs` — OS-difference isolation + unit tests.
- `desktop/build-linux.sh` — AppDir assembly → AppImage.
- `.github/workflows/linux-appimage.yml` — CI build.
- `desktop/AppDir/` templates: `AppRun`, `meeting-processor.desktop` (icon reused
  from `desktop/icon-source.png` / generated set).

**Modified:**
- `desktop/src-tauri/src/lib.rs` — declare `mod platform;`.
- `desktop/src-tauri/src/setup.rs` — `check_prerequisites` short-circuits via
  `platform::needs_bootstrap()`.
- `desktop/src-tauri/src/server.rs` — use `platform::python()` / `extra_path()` /
  `package_dir()` instead of the macOS-specific resolution.
- `desktop/src-tauri/src/paths.rs` — `shell_path()` becomes the macOS arm of
  `platform::extra_path()`.
- `desktop/README.md` — Linux build + smoke instructions.
