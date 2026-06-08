# Tauri Desktop App — Design

**Date:** 2026-06-05
**Status:** Approved (pending written-spec review)
**Topic:** Wrap the Meeting Processor (FastAPI server + React SPA) in a native macOS `.app` using Tauri.

## Goal

Turn Meeting Processor from a double-click bash launcher (`Meeting Processor.command`)
into a real native macOS application that a non-technical friend can install from a
`.dmg` and run, with a guided first-run setup instead of manual `venv`/`pip` steps.

## Decisions (from brainstorming)

| Question | Decision |
|----------|----------|
| Target scope | macOS only; shareable to a few friends |
| Bundling | First-run bootstrap — small `.app`; venv created on first launch; needs system Python 3.11 + ffmpeg |
| Missing prerequisites | Guided setup screen with **auto-install via Homebrew** (installs Homebrew first if absent), with a live log |
| Code signing | None (no Apple Developer account) — ship unsigned/ad-hoc; first open via right-click → Open |
| Structure | **Approach A** — thin Tauri shell + process supervisor; existing SPA/server reused untouched behind an HTTP boundary |

## Architecture

Three layers, each single-purpose:

- **Rust/Tauri** — owns the native window, runs prerequisite detection & install, supervises
  the Python server process, allocates the port.
- **Python server** — unchanged; spawned as a child via `python -m meeting_processor web --port N`.
- **Webview** — shows the bundled setup page first, then navigates to
  `http://127.0.0.1:N/ui` (the existing SPA, untouched).

The Rust↔webview boundary is a small set of Tauri commands plus a log event stream.

### Directory layout

```
desktop/
  build.sh             # orchestrates frontend build → resource copy → tauri build → ad-hoc sign
  src-tauri/
    src/
      main.rs          # window, app lifecycle, command registration
      setup.rs         # detect/install commands (prerequisite logic)
      server.rs        # spawn/supervise the Python server, port allocation
    tauri.conf.json    # bundle config (macOS .app/.dmg, unsigned)
    icons/
    resources/         # populated by build.sh (read-only payload): meeting_processor/, spa/, requirements.txt, default config.yaml
  ui/                  # tiny static setup page (plain HTML/CSS/JS)
    index.html
    setup.js
  README.md            # build + "right-click → Open" instructions + manual smoke checklist
```

Nothing in `meeting_processor/` or `frontend/` changes except the single `load_config`
data-dir override (below) and the build wiring.

## First-run setup flow (state machine)

State is derived fresh each launch (no persisted flag that can go stale). A marker file
only suppresses the intro copy on later launches.

```
launch ─▶ DETECT ──(all present)──▶ STARTING ─▶ READY (webview → /ui)
            │
            └──(missing)──▶ NEEDS_SETUP ──(user clicks "Install & set up")──▶
                 INSTALLING (brew; install Homebrew if absent) ─▶ BOOTSTRAP (venv + pip) ─▶ STARTING
                 any failure ─▶ ERROR (message + log + Retry → re-enter DETECT)
```

### Tauri commands (each streams `setup://log` events)

- `check_prerequisites() -> { brew, python311, ffmpeg, venv }` — each `ok | missing | wrong_version`.
- `install_prerequisite(name)` — install Homebrew (official curl script, **only on explicit click**),
  then `brew install python@3.11` / `ffmpeg`. Long-running, log-streamed.
- `bootstrap_venv()` — `python3.11 -m venv <data>/.venv && <data>/.venv/bin/pip install -r requirements.txt`.
- `start_server()` — allocate port, spawn supervised child, health-poll, return port.

All steps are idempotent and re-runnable; Retry simply re-enters DETECT.

### Setup invariants

- The venv and all writable state live under `~/Library/Application Support/MeetingProcessor/`
  (the `.app` bundle is read-only).
- Homebrew/install actions never run without an explicit user click — no silent shell execution.
- The prebuilt SPA ships inside the Python package (`meeting_processor/web/spa/`) so Node is
  not needed at runtime.

## Server lifecycle, port & writable data dir

### Writable data dir (the one required code change)

`vault_path`, `temp_path`, `uploads_dir`, logs, and `config.yaml`/`.env` all resolve from
`project_root = Path(__file__).parent.parent` (config.py:157, 239; app.py:1443). Inside a
read-only `.app` this breaks writes.

**Change:** `load_config()` honors a new env var `MEETING_DATA_DIR` to set `project_root`,
defaulting to today's `Path(__file__).parent.parent` when unset.

- One override redirects every writable location at once (vault/temp/uploads/config/.env
  all derive from `project_root`).
- Python source and the prebuilt SPA are located via `__file__`/package paths
  (`spa_serving.SPA_DIR`), **not** `project_root`, so they correctly stay in the read-only bundle.
- On bootstrap, Rust seeds `~/Library/Application Support/MeetingProcessor/` with a default
  `config.yaml` (+ empty `.env`) if absent, then always spawns Python with `MEETING_DATA_DIR`
  set there.

### Port management

Rust asks the OS for a free port (bind `127.0.0.1:0`, read it back, release), then spawns
`python -m meeting_processor web --port N`. Eliminates the hardcoded-8765 collision in
today's launcher.

### Supervision

- Spawn the venv `python`; env includes `MEETING_DATA_DIR`; cwd = data dir (cwd-relative logs
  land in writable space).
- Health-poll `GET /api/health` until 200; timeout → ERROR with captured stderr tail.
- Capture child stdout/stderr to a rotating `desktop.log` in the data dir.
- On window close / app quit / Rust panic: terminate the child (SIGTERM → SIGKILL) so no
  orphan server survives (fixes today's "stale server serving old code" footgun).

## Packaging, build & distribution

**Inside the `.app` (`Resources/`, read-only):** `meeting_processor/` source, prebuilt `spa/`,
`requirements.txt`, default `config.yaml` template. **Excluded:** `node_modules`, `.venv`,
`vault/`, `uploads/`, `.env`.

**Build pipeline (`desktop/build.sh`):**

1. `cd frontend && npm run build` → `meeting_processor/web/spa/`.
2. Copy `meeting_processor/` + `requirements.txt` + default config into `src-tauri/resources/`.
3. `npm run tauri build` → `MeetingProcessor.app` + `.dmg`.
4. `codesign -s - --deep` (ad-hoc) for a stable identity / to avoid "damaged app" errors
   (still unsigned re: notarization).

**Distribution:** a `.dmg` (drag to Applications) + short README. First launch: right-click →
Open once to clear Gatekeeper; `xattr -dr com.apple.quarantine` documented as fallback. Python
is not bundled — the setup flow installs it via Homebrew on first run.

## Error handling

- Every setup step failing → ERROR state with a human message + the captured log + Retry.
- Server spawn/health-check failure → ERROR with stderr tail; Retry re-runs DETECT.
- Missing prerequisites are a normal state (NEEDS_SETUP), not an error.
- Orphan-server prevention via guaranteed child termination on exit.

## Testing

- **Rust unit tests** (pure, isolated from spawning): free-port allocation, prerequisite-detection
  parsing (`brew list` / `python3.11 --version` / `ffmpeg -version` → status enum), setup
  state-machine transitions.
- **Python:** existing suite unchanged; **add one test** that `load_config()` honors
  `MEETING_DATA_DIR` and that `vault_path`/`temp_path`/uploads resolve under it.
- **Manual smoke checklist** (in `desktop/README.md`): fresh setup (move `.venv` aside), missing
  ffmpeg, port-in-use, quit-kills-server / no orphan.
- Full Tauri UI e2e is **out of scope** (heavy, low ROI) — existing web tests cover app behavior
  behind the HTTP boundary.

## Out of scope (YAGNI)

- Windows/Linux builds; notarization/auto-update.
- Bundling Python/torch/ffmpeg inside the app (first-run bootstrap chosen instead).
- Dropping torch / faster-whisper migration (separate effort; would shrink a future
  self-contained build but is not required here).
- Prefetching the Whisper model during setup (downloads on first transcription as today).
```
