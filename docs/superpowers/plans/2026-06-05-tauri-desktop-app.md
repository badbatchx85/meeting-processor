# Tauri macOS Desktop App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap the existing FastAPI server + React SPA in a native macOS `.app` (Tauri v2) with a guided first-run setup, so a non-technical friend can install from a `.dmg` and run without manual `venv`/`pip` steps.

**Architecture:** Approach A — a thin Tauri/Rust shell acts as a native window + process supervisor. It runs prerequisite detection/install (Homebrew), bootstraps a venv under Application Support, allocates a free port, spawns the unchanged `python -m meeting_processor web --port N`, health-polls it, then points the webview at the existing SPA at `http://127.0.0.1:N/ui`. The only change to existing code is `load_config()` honoring a `MEETING_DATA_DIR` env var for writable paths.

**Tech Stack:** Tauri v2 (Rust), tokio, serde, reqwest (http-only); existing Python (FastAPI/uvicorn) + React SPA (Vite); Homebrew for prerequisite install; `cargo test` + `pytest`.

**Reference spec:** `docs/superpowers/specs/2026-06-05-tauri-desktop-app-design.md`

---

## File Structure

**New (`desktop/`):**
- `desktop/src-tauri/Cargo.toml` — Rust crate manifest + deps.
- `desktop/src-tauri/tauri.conf.json` — bundle/window config (macOS `.app`/`.dmg`, unsigned).
- `desktop/src-tauri/build.rs` — Tauri build hook.
- `desktop/src-tauri/src/main.rs` — window, lifecycle, command registration, child cleanup.
- `desktop/src-tauri/src/port.rs` — free-port allocation (pure-ish, unit-tested).
- `desktop/src-tauri/src/prereq.rs` — prerequisite detection + output parsing (pure, unit-tested).
- `desktop/src-tauri/src/state.rs` — setup state-machine transitions (pure, unit-tested).
- `desktop/src-tauri/src/setup.rs` — Tauri commands: check/install/bootstrap (IO, log-streamed).
- `desktop/src-tauri/src/server.rs` — spawn/supervise/health-poll/kill the Python server.
- `desktop/src-tauri/src/paths.rs` — resolve data dir + bundled resource dir.
- `desktop/ui/index.html` — static setup page shell.
- `desktop/ui/setup.js` — setup-page logic (calls commands, renders state + log).
- `desktop/ui/setup.css` — minimal styling.
- `desktop/build.sh` — frontend build → resource copy → `tauri build` → ad-hoc sign.
- `desktop/README.md` — build + "right-click → Open" + manual smoke checklist.
- `desktop/.gitignore` — ignore `src-tauri/target/`, `src-tauri/resources/`, `src-tauri/gen/`.

**Modified (existing):**
- `meeting_processor/config.py:155-161` — `load_config()` honors `MEETING_DATA_DIR`.
- `tests/test_data_dir.py` (new) — verifies the override.

---

## Phase 0 — Writable data dir (Python, the only existing-code change)

### Task 0.1: `load_config()` honors `MEETING_DATA_DIR`

**Files:**
- Modify: `meeting_processor/config.py:155-161`
- Test: `tests/test_data_dir.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_data_dir.py`:

```python
"""MEETING_DATA_DIR redirects all writable paths to a single base dir."""
from pathlib import Path

from meeting_processor.config import load_config


def test_data_dir_env_redirects_writable_paths(tmp_path, monkeypatch):
    data_dir = tmp_path / "appsupport"
    monkeypatch.setenv("MEETING_DATA_DIR", str(data_dir))

    cfg = load_config()

    # project_root and everything derived from it move under the data dir.
    assert Path(cfg.project_root) == data_dir
    assert cfg.vault_path == data_dir / cfg.vault_dir
    assert cfg.temp_path == data_dir / cfg.temp_dir
    # load_config creates the temp dir under the data dir, not the repo.
    assert cfg.temp_path.exists()


def test_no_env_falls_back_to_package_root(tmp_path, monkeypatch):
    monkeypatch.delenv("MEETING_DATA_DIR", raising=False)
    cfg = load_config()
    # Default: two levels up from meeting_processor/config.py == repo root.
    expected = Path(__file__).resolve().parent.parent
    assert Path(cfg.project_root) == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_data_dir.py -v`
Expected: `test_data_dir_env_redirects_writable_paths` FAILS (project_root is the repo root, not `data_dir`).

- [ ] **Step 3: Write minimal implementation**

In `meeting_processor/config.py`, replace lines 155-161:

```python
def load_config(config_path: str | None = None) -> Settings:
    """Carrega configuração do YAML e variáveis de ambiente."""
    # MEETING_DATA_DIR redireciona TODOS os caminhos graváveis (vault, temp,
    # uploads, .env, config.yaml) para um diretório único — usado pelo app
    # desktop (Tauri), cujo bundle é somente-leitura. Sem a variável, mantém
    # o comportamento atual: dois níveis acima de config.py (raiz do repo).
    data_dir_env = os.environ.get("MEETING_DATA_DIR")
    project_root = (
        Path(data_dir_env).expanduser()
        if data_dir_env
        else Path(__file__).parent.parent
    )
    project_root.mkdir(parents=True, exist_ok=True)
    load_dotenv(project_root / ".env")

    if config_path is None:
        config_path = str(project_root / "config.yaml")
```

(The rest of `load_config` is unchanged — `config_data["project_root"] = str(project_root)` at line 239 already propagates it.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_data_dir.py -v`
Expected: both PASS.

- [ ] **Step 5: Run the full Python suite to confirm no regression**

Run: `.venv/bin/python -m pytest -q`
Expected: all pass (same count as before + 2).

- [ ] **Step 6: Commit**

```bash
git add meeting_processor/config.py tests/test_data_dir.py
git commit -m "feat(config): honor MEETING_DATA_DIR for writable data dir

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase 1 — Tauri scaffold

### Task 1.1: Verify Rust + Tauri CLI toolchain

**Files:** none (environment check).

- [ ] **Step 1: Confirm Rust is installed**

Run: `cargo --version && rustc --version`
Expected: prints versions (e.g. `cargo 1.7x`). If missing: `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh` then restart shell.

- [ ] **Step 2: Confirm Node/npm (already used by frontend)**

Run: `node --version && npm --version`
Expected: prints versions.

### Task 1.2: Create the Tauri crate manifest and config

**Files:**
- Create: `desktop/.gitignore`
- Create: `desktop/src-tauri/Cargo.toml`
- Create: `desktop/src-tauri/build.rs`
- Create: `desktop/src-tauri/tauri.conf.json`

- [ ] **Step 1: Create `desktop/.gitignore`**

```gitignore
src-tauri/target/
src-tauri/gen/
src-tauri/resources/
*.dmg
```

- [ ] **Step 2: Create `desktop/src-tauri/Cargo.toml`**

```toml
[package]
name = "meeting-processor-desktop"
version = "1.0.0"
description = "Meeting Processor desktop shell"
edition = "2021"

[lib]
name = "meeting_processor_desktop_lib"
crate-type = ["staticlib", "cdylib", "rlib"]

[build-dependencies]
tauri-build = { version = "2", features = [] }

[dependencies]
tauri = { version = "2", features = [] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
tokio = { version = "1", features = ["full"] }
reqwest = { version = "0.12", default-features = false }

[profile.release]
strip = true
lto = true
```

- [ ] **Step 3: Create `desktop/src-tauri/build.rs`**

```rust
fn main() {
    tauri_build::build()
}
```

- [ ] **Step 4: Create `desktop/src-tauri/tauri.conf.json`**

```json
{
  "$schema": "https://schema.tauri.app/config/2",
  "productName": "Meeting Processor",
  "version": "1.0.0",
  "identifier": "com.meetingprocessor.desktop",
  "build": {
    "frontendDist": "../ui"
  },
  "app": {
    "windows": [
      {
        "title": "Meeting Processor",
        "width": 1200,
        "height": 860,
        "minWidth": 900,
        "minHeight": 640,
        "resizable": true
      }
    ],
    "security": {
      "csp": null
    }
  },
  "bundle": {
    "active": true,
    "targets": ["app", "dmg"],
    "icon": ["icons/icon.icns"],
    "resources": {
      "resources/*": "./"
    },
    "macOS": {
      "minimumSystemVersion": "11.0"
    }
  }
}
```

- [ ] **Step 5: Create a placeholder icon so `tauri build` won't fail**

Run:
```bash
mkdir -p desktop/src-tauri/icons desktop/src-tauri/resources
# Generate a minimal icon set from any PNG you have, or use the Tauri default:
npx --yes @tauri-apps/cli icon frontend/src/assets/*.png --output desktop/src-tauri/icons 2>/dev/null || echo "Provide a 1024x1024 PNG and run: npx @tauri-apps/cli icon <png> --output desktop/src-tauri/icons"
```
Expected: `desktop/src-tauri/icons/icon.icns` exists. If no source PNG, create a 1024×1024 solid PNG first (any tool) and re-run the icon command.

- [ ] **Step 6: Commit**

```bash
git add desktop/.gitignore desktop/src-tauri/Cargo.toml desktop/src-tauri/build.rs desktop/src-tauri/tauri.conf.json
git commit -m "chore(desktop): scaffold Tauri crate manifest and config

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase 2 — Pure logic modules (unit-tested with `cargo test`)

### Task 2.1: Free-port allocation (`port.rs`)

**Files:**
- Create: `desktop/src-tauri/src/port.rs`

- [ ] **Step 1: Write the module with an inline failing test**

```rust
//! Allocate a free localhost TCP port by binding to :0 and reading it back.
use std::net::{Ipv4Addr, TcpListener};

/// Returns an OS-assigned free port on 127.0.0.1. The listener is dropped
/// immediately, so there is a tiny race window — acceptable for a local
/// single-user app, and far safer than the old hardcoded 8765.
pub fn free_port() -> std::io::Result<u16> {
    let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0))?;
    Ok(listener.local_addr()?.port())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::{Ipv4Addr, TcpListener};

    #[test]
    fn returns_a_bindable_port() {
        let port = free_port().expect("should allocate");
        assert!(port > 0);
        // We can bind to it after free_port released it.
        TcpListener::bind((Ipv4Addr::LOCALHOST, port)).expect("port should be free");
    }

    #[test]
    fn successive_calls_usually_differ_or_are_valid() {
        let a = free_port().unwrap();
        let b = free_port().unwrap();
        assert!(a > 0 && b > 0);
    }
}
```

- [ ] **Step 2: Register the module** — add `mod port;` near the top of `src/main.rs` (created in Task 5.1). If `main.rs` does not exist yet, defer this line; Task 5.1 includes all `mod` declarations.

- [ ] **Step 3: Run the test**

Run: `cd desktop/src-tauri && cargo test port::tests`
Expected: 2 tests PASS. (First run compiles dependencies — may take a few minutes.)

- [ ] **Step 4: Commit**

```bash
git add desktop/src-tauri/src/port.rs
git commit -m "feat(desktop): free-port allocation module

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 2.2: Prerequisite detection + parsing (`prereq.rs`)

**Files:**
- Create: `desktop/src-tauri/src/prereq.rs`

- [ ] **Step 1: Write the module with inline failing tests**

```rust
//! Detect host prerequisites (Homebrew, Python 3.11, ffmpeg) and parse their
//! version output. Parsing is pure and unit-tested; the actual command
//! execution is a thin wrapper kept separate so tests don't shell out.
use serde::Serialize;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Status {
    Ok,
    Missing,
    WrongVersion,
}

#[derive(Debug, Clone, Serialize)]
pub struct Prerequisites {
    pub brew: Status,
    pub python311: Status,
    pub ffmpeg: Status,
    pub venv: Status,
}

/// `python3.11 --version` prints e.g. "Python 3.11.9". Accept any 3.11.x.
pub fn parse_python_version(stdout: &str, stderr: &str) -> Status {
    let text = if stdout.trim().is_empty() { stderr } else { stdout };
    let text = text.trim();
    match text.strip_prefix("Python ") {
        Some(v) if v.starts_with("3.11.") || v == "3.11" => Status::Ok,
        Some(_) => Status::WrongVersion,
        None => Status::Missing,
    }
}

/// `ffmpeg -version` prints "ffmpeg version ..." on success.
pub fn parse_ffmpeg_version(stdout: &str) -> Status {
    if stdout.trim_start().starts_with("ffmpeg version") {
        Status::Ok
    } else {
        Status::Missing
    }
}

/// `brew --version` prints "Homebrew x.y.z".
pub fn parse_brew_version(stdout: &str) -> Status {
    if stdout.trim_start().starts_with("Homebrew") {
        Status::Ok
    } else {
        Status::Missing
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn python_311_is_ok() {
        assert_eq!(parse_python_version("Python 3.11.9\n", ""), Status::Ok);
    }

    #[test]
    fn python_312_is_wrong_version() {
        assert_eq!(parse_python_version("Python 3.12.1\n", ""), Status::WrongVersion);
    }

    #[test]
    fn python_uses_stderr_when_stdout_empty() {
        // Older pythons print version to stderr.
        assert_eq!(parse_python_version("", "Python 3.11.2\n"), Status::Ok);
    }

    #[test]
    fn python_garbage_is_missing() {
        assert_eq!(parse_python_version("zsh: command not found", ""), Status::Missing);
    }

    #[test]
    fn ffmpeg_ok() {
        assert_eq!(parse_ffmpeg_version("ffmpeg version 6.1 Copyright"), Status::Ok);
    }

    #[test]
    fn ffmpeg_missing() {
        assert_eq!(parse_ffmpeg_version(""), Status::Missing);
    }

    #[test]
    fn brew_ok() {
        assert_eq!(parse_brew_version("Homebrew 4.2.0"), Status::Ok);
    }
}
```

- [ ] **Step 2: Run the tests**

Run: `cd desktop/src-tauri && cargo test prereq::tests`
Expected: 7 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add desktop/src-tauri/src/prereq.rs
git commit -m "feat(desktop): prerequisite version parsing

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 2.3: Setup state machine (`state.rs`)

**Files:**
- Create: `desktop/src-tauri/src/state.rs`

- [ ] **Step 1: Write the module with inline failing tests**

```rust
//! Pure transitions for the first-run setup flow. The UI and commands drive
//! this; keeping it pure makes the flow unit-testable.
use serde::Serialize;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum SetupState {
    Detect,
    NeedsSetup,
    Installing,
    Bootstrap,
    Starting,
    Ready,
    Error,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Event {
    AllPresent,
    Missing,
    UserStartedSetup,
    InstallDone,
    BootstrapDone,
    ServerReady,
    Failed,
    Retry,
}

/// Compute the next state. Unknown (state, event) pairs stay put.
pub fn next_state(state: SetupState, event: Event) -> SetupState {
    use Event::*;
    use SetupState::*;
    match (state, event) {
        (Detect, AllPresent) => Starting,
        (Detect, Missing) => NeedsSetup,
        (NeedsSetup, UserStartedSetup) => Installing,
        (Installing, InstallDone) => Bootstrap,
        (Bootstrap, BootstrapDone) => Starting,
        (Starting, ServerReady) => Ready,
        (_, Failed) => Error,
        (Error, Retry) => Detect,
        (s, _) => s,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use Event::*;
    use SetupState::*;

    #[test]
    fn happy_path_when_all_present() {
        assert_eq!(next_state(Detect, AllPresent), Starting);
        assert_eq!(next_state(Starting, ServerReady), Ready);
    }

    #[test]
    fn setup_path_when_missing() {
        assert_eq!(next_state(Detect, Missing), NeedsSetup);
        assert_eq!(next_state(NeedsSetup, UserStartedSetup), Installing);
        assert_eq!(next_state(Installing, InstallDone), Bootstrap);
        assert_eq!(next_state(Bootstrap, BootstrapDone), Starting);
    }

    #[test]
    fn failure_from_any_state_goes_to_error() {
        assert_eq!(next_state(Installing, Failed), Error);
        assert_eq!(next_state(Bootstrap, Failed), Error);
        assert_eq!(next_state(Starting, Failed), Error);
    }

    #[test]
    fn retry_returns_to_detect() {
        assert_eq!(next_state(Error, Retry), Detect);
    }

    #[test]
    fn unknown_pair_is_noop() {
        assert_eq!(next_state(Ready, Missing), Ready);
    }
}
```

- [ ] **Step 2: Run the tests**

Run: `cd desktop/src-tauri && cargo test state::tests`
Expected: 5 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add desktop/src-tauri/src/state.rs
git commit -m "feat(desktop): setup state-machine transitions

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase 3 — IO modules (process supervision; verified via smoke tests)

### Task 3.1: Path resolution (`paths.rs`)

**Files:**
- Create: `desktop/src-tauri/src/paths.rs`

- [ ] **Step 1: Write the module**

```rust
//! Resolve the writable data dir (Application Support) and the read-only
//! bundled resource dir (Python source + prebuilt SPA + requirements.txt).
use std::path::PathBuf;
use tauri::{AppHandle, Manager};

/// `~/Library/Application Support/com.meetingprocessor.desktop/`
/// (Tauri derives this from the bundle identifier). All writable state lives here.
pub fn data_dir(app: &AppHandle) -> Result<PathBuf, String> {
    let dir = app
        .path()
        .app_data_dir()
        .map_err(|e| format!("app_data_dir: {e}"))?;
    std::fs::create_dir_all(&dir).map_err(|e| format!("create data dir: {e}"))?;
    Ok(dir)
}

/// Read-only resources copied in by `build.sh`: contains `meeting_processor/`,
/// `requirements.txt`, and `config.default.yaml`.
pub fn resource_dir(app: &AppHandle) -> Result<PathBuf, String> {
    app.path()
        .resource_dir()
        .map_err(|e| format!("resource_dir: {e}"))
}

/// The venv python created during bootstrap.
pub fn venv_python(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(data_dir(app)?.join(".venv").join("bin").join("python"))
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd desktop/src-tauri && cargo build`
Expected: compiles (after Task 5.1 adds `mod paths;`). If `main.rs` not yet present, this compiles once Phase 5 lands; for now run `cargo check` after adding the `mod` line in a scratch `main.rs` or defer build verification to Task 5.2.

- [ ] **Step 3: Commit**

```bash
git add desktop/src-tauri/src/paths.rs
git commit -m "feat(desktop): data + resource path resolution

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 3.2: Setup commands — detect/install/bootstrap (`setup.rs`)

**Files:**
- Create: `desktop/src-tauri/src/setup.rs`

- [ ] **Step 1: Write the module**

```rust
//! Tauri commands for first-run setup. Each long-running command streams
//! stdout/stderr lines to the webview via the `setup://log` event.
use crate::paths;
use crate::prereq::{parse_brew_version, parse_ffmpeg_version, parse_python_version, Prerequisites, Status};
use std::process::Stdio;
use tauri::{AppHandle, Emitter};
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::Command;

const BREW: &str = "/opt/homebrew/bin/brew"; // Apple Silicon; Intel is /usr/local/bin/brew

fn emit_log(app: &AppHandle, line: &str) {
    let _ = app.emit("setup://log", line.to_string());
}

async fn capture(cmd: &str, args: &[&str]) -> (String, String) {
    match Command::new(cmd).args(args).output().await {
        Ok(out) => (
            String::from_utf8_lossy(&out.stdout).to_string(),
            String::from_utf8_lossy(&out.stderr).to_string(),
        ),
        Err(_) => (String::new(), String::new()),
    }
}

fn brew_path() -> &'static str {
    if std::path::Path::new(BREW).exists() {
        BREW
    } else {
        "/usr/local/bin/brew"
    }
}

#[tauri::command]
pub async fn check_prerequisites(app: AppHandle) -> Result<Prerequisites, String> {
    let (brew_out, _) = capture(brew_path(), &["--version"]).await;
    let (py_out, py_err) = capture("python3.11", &["--version"]).await;
    let (ff_out, _) = capture("ffmpeg", &["-version"]).await;

    let venv = if paths::venv_python(&app)?.exists() {
        Status::Ok
    } else {
        Status::Missing
    };

    Ok(Prerequisites {
        brew: parse_brew_version(&brew_out),
        python311: parse_python_version(&py_out, &py_err),
        ffmpeg: parse_ffmpeg_version(&ff_out),
        venv,
    })
}

/// Run a command, streaming each output line to the webview. Returns Err on
/// non-zero exit so the UI transitions to ERROR.
async fn run_streamed(app: &AppHandle, program: &str, args: &[&str]) -> Result<(), String> {
    emit_log(app, &format!("$ {program} {}", args.join(" ")));
    let mut child = Command::new(program)
        .args(args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("falha ao iniciar {program}: {e}"))?;

    if let Some(out) = child.stdout.take() {
        let app2 = app.clone();
        let mut lines = BufReader::new(out).lines();
        tokio::spawn(async move {
            while let Ok(Some(l)) = lines.next_line().await {
                emit_log(&app2, &l);
            }
        });
    }
    if let Some(err) = child.stderr.take() {
        let app2 = app.clone();
        let mut lines = BufReader::new(err).lines();
        tokio::spawn(async move {
            while let Ok(Some(l)) = lines.next_line().await {
                emit_log(&app2, &l);
            }
        });
    }

    let status = child.wait().await.map_err(|e| e.to_string())?;
    if status.success() {
        Ok(())
    } else {
        Err(format!("{program} terminou com código {:?}", status.code()))
    }
}

/// Install a missing prerequisite. `name` is one of: "brew", "python311", "ffmpeg".
/// Only called after an explicit user click in the UI.
#[tauri::command]
pub async fn install_prerequisite(app: AppHandle, name: String) -> Result<(), String> {
    match name.as_str() {
        "brew" => {
            emit_log(&app, "Instalando Homebrew…");
            run_streamed(
                &app,
                "/bin/bash",
                &[
                    "-c",
                    "NONINTERACTIVE=1 /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"",
                ],
            )
            .await
        }
        "python311" => run_streamed(&app, brew_path(), &["install", "python@3.11"]).await,
        "ffmpeg" => run_streamed(&app, brew_path(), &["install", "ffmpeg"]).await,
        other => Err(format!("prerequisito desconhecido: {other}")),
    }
}

/// Create the venv under the data dir and install requirements.
#[tauri::command]
pub async fn bootstrap_venv(app: AppHandle) -> Result<(), String> {
    let data = paths::data_dir(&app)?;
    let resources = paths::resource_dir(&app)?;
    let venv = data.join(".venv");
    let requirements = resources.join("requirements.txt");

    // Seed a default config.yaml if the user has none yet.
    let default_cfg = resources.join("config.default.yaml");
    let target_cfg = data.join("config.yaml");
    if default_cfg.exists() && !target_cfg.exists() {
        std::fs::copy(&default_cfg, &target_cfg).map_err(|e| format!("copiar config: {e}"))?;
        emit_log(&app, "config.yaml padrão criado.");
    }

    emit_log(&app, "Criando ambiente Python (.venv)…");
    run_streamed(&app, "python3.11", &["-m", "venv", &venv.to_string_lossy()]).await?;

    let pip = venv.join("bin").join("pip");
    emit_log(&app, "Instalando dependências (pode demorar)…");
    run_streamed(
        &app,
        &pip.to_string_lossy(),
        &["install", "-r", &requirements.to_string_lossy()],
    )
    .await
}
```

- [ ] **Step 2: Commit (compilation verified in Task 5.2)**

```bash
git add desktop/src-tauri/src/setup.rs
git commit -m "feat(desktop): setup commands (detect/install/bootstrap) with log streaming

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 3.3: Server supervisor (`server.rs`)

**Files:**
- Create: `desktop/src-tauri/src/server.rs`

- [ ] **Step 1: Write the module**

```rust
//! Spawn and supervise the Python web server. Holds the child handle so the
//! app can kill it on quit (no orphan servers).
use crate::paths;
use crate::port::free_port;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::{AppHandle, Emitter};

/// Shared handle to the running server child, stored in Tauri state.
#[derive(Default)]
pub struct ServerProcess(pub Mutex<Option<Child>>);

fn emit_log(app: &AppHandle, line: &str) {
    let _ = app.emit("setup://log", line.to_string());
}

/// Start the server: allocate a port, spawn the venv python with
/// MEETING_DATA_DIR set, health-poll /api/health, return the port + /ui URL.
#[tauri::command]
pub async fn start_server(
    app: AppHandle,
    state: tauri::State<'_, ServerProcess>,
) -> Result<String, String> {
    let data = paths::data_dir(&app)?;
    let resources = paths::resource_dir(&app)?;
    let python = paths::venv_python(&app)?;
    let port = free_port().map_err(|e| format!("porta livre: {e}"))?;

    emit_log(&app, &format!("Iniciando servidor na porta {port}…"));

    let child = Command::new(&python)
        .args(["-m", "meeting_processor", "web", "--port", &port.to_string()])
        .env("MEETING_DATA_DIR", &data)
        // The bundled meeting_processor package lives in resources/; put it on the path.
        .env("PYTHONPATH", &resources)
        .current_dir(&data)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|e| format!("falha ao iniciar o servidor: {e}"))?;

    *state.0.lock().unwrap() = Some(child);

    // Health-poll up to ~30s.
    let url = format!("http://127.0.0.1:{port}/api/health");
    let client = reqwest::Client::new();
    for _ in 0..60 {
        if let Ok(resp) = client.get(&url).send().await {
            if resp.status().is_success() {
                emit_log(&app, "Servidor pronto.");
                return Ok(format!("http://127.0.0.1:{port}/ui"));
            }
        }
        tokio::time::sleep(std::time::Duration::from_millis(500)).await;
    }
    Err("o servidor não respondeu a tempo".into())
}

/// Kill the child if running. Called on window close / app exit.
pub fn kill(state: &ServerProcess) {
    if let Some(mut child) = state.0.lock().unwrap().take() {
        let _ = child.kill();
        let _ = child.wait();
    }
}
```

- [ ] **Step 2: Commit (compilation verified in Task 5.2)**

```bash
git add desktop/src-tauri/src/server.rs
git commit -m "feat(desktop): python server supervisor with health poll + kill-on-exit

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase 4 — Setup UI (static page)

### Task 4.1: Setup page HTML/CSS/JS

**Files:**
- Create: `desktop/ui/index.html`
- Create: `desktop/ui/setup.css`
- Create: `desktop/ui/setup.js`

- [ ] **Step 1: Create `desktop/ui/index.html`**

```html
<!doctype html>
<html lang="pt-BR">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Meeting Processor</title>
    <link rel="stylesheet" href="setup.css" />
  </head>
  <body>
    <main id="app">
      <h1>Meeting Processor</h1>
      <p id="status">Verificando o sistema…</p>
      <ul id="checks"></ul>
      <button id="action" hidden></button>
      <pre id="log" hidden></pre>
    </main>
    <script type="module" src="setup.js"></script>
  </body>
</html>
```

- [ ] **Step 2: Create `desktop/ui/setup.css`**

```css
:root { font-family: -apple-system, system-ui, sans-serif; }
body { margin: 0; background: #fafaf9; color: #1c1917; }
#app { max-width: 640px; margin: 0 auto; padding: 48px 24px; }
h1 { font-size: 22px; letter-spacing: -0.02em; }
#status { color: #57534e; }
#checks { list-style: none; padding: 0; }
#checks li { padding: 6px 0; font-size: 14px; }
#checks li.ok::before { content: "✓ "; color: #16a34a; }
#checks li.missing::before { content: "• "; color: #dc2626; }
button { margin-top: 16px; padding: 10px 16px; font-size: 14px; border: 1px solid #1c1917;
  background: #1c1917; color: #fafaf9; border-radius: 8px; cursor: pointer; }
button:disabled { opacity: 0.5; cursor: default; }
#log { margin-top: 20px; max-height: 260px; overflow: auto; background: #0a0a0a; color: #e7e5e4;
  font: 12px/1.5 ui-monospace, monospace; padding: 12px; border-radius: 8px; white-space: pre-wrap; }
```

- [ ] **Step 3: Create `desktop/ui/setup.js`**

```js
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

const statusEl = document.getElementById("status");
const checksEl = document.getElementById("checks");
const actionEl = document.getElementById("action");
const logEl = document.getElementById("log");

const LABELS = { brew: "Homebrew", python311: "Python 3.11", ffmpeg: "ffmpeg", venv: "Ambiente Python" };

listen("setup://log", (e) => {
  logEl.hidden = false;
  logEl.textContent += e.payload + "\n";
  logEl.scrollTop = logEl.scrollHeight;
});

function renderChecks(p) {
  checksEl.innerHTML = "";
  for (const [key, label] of Object.entries(LABELS)) {
    const li = document.createElement("li");
    const ok = p[key] === "ok";
    li.className = ok ? "ok" : "missing";
    li.textContent = `${label}: ${p[key] === "ok" ? "pronto" : p[key] === "wrong_version" ? "versão incorreta" : "faltando"}`;
    checksEl.appendChild(li);
  }
}

function missingList(p) {
  // venv is produced by bootstrap, not installed; brew/python311/ffmpeg are installable.
  return ["brew", "python311", "ffmpeg"].filter((k) => p[k] !== "ok");
}

async function launchServer() {
  statusEl.textContent = "Iniciando o servidor…";
  actionEl.hidden = true;
  try {
    const uiUrl = await invoke("start_server");
    window.location.replace(uiUrl); // hand off to the existing SPA
  } catch (err) {
    showError(String(err));
  }
}

function showError(msg) {
  statusEl.textContent = "Algo deu errado.";
  logEl.hidden = false;
  logEl.textContent += "ERRO: " + msg + "\n";
  actionEl.hidden = false;
  actionEl.textContent = "Tentar novamente";
  actionEl.disabled = false;
  actionEl.onclick = detect;
}

async function runSetup(missing) {
  actionEl.disabled = true;
  statusEl.textContent = "Instalando dependências…";
  try {
    if (missing.includes("brew")) await invoke("install_prerequisite", { name: "brew" });
    if (missing.includes("python311")) await invoke("install_prerequisite", { name: "python311" });
    if (missing.includes("ffmpeg")) await invoke("install_prerequisite", { name: "ffmpeg" });
    await invoke("bootstrap_venv");
    await launchServer();
  } catch (err) {
    showError(String(err));
  }
}

async function detect() {
  statusEl.textContent = "Verificando o sistema…";
  actionEl.hidden = true;
  logEl.hidden = true;
  logEl.textContent = "";
  let p;
  try {
    p = await invoke("check_prerequisites");
  } catch (err) {
    return showError(String(err));
  }
  renderChecks(p);

  const missing = missingList(p);
  const needsVenv = p.venv !== "ok";

  if (missing.length === 0 && !needsVenv) {
    return launchServer();
  }
  if (missing.length === 0 && needsVenv) {
    // Tools present, just need the venv.
    statusEl.textContent = "Configurando o ambiente pela primeira vez…";
    return runSetup([]);
  }
  statusEl.textContent = "Alguns componentes precisam ser instalados.";
  actionEl.hidden = false;
  actionEl.textContent = "Instalar e configurar";
  actionEl.disabled = false;
  actionEl.onclick = () => runSetup(missing);
}

detect();
```

- [ ] **Step 4: Commit**

```bash
git add desktop/ui/index.html desktop/ui/setup.css desktop/ui/setup.js
git commit -m "feat(desktop): first-run setup page (detect/install/bootstrap UI)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Phase 5 — Wire it together

### Task 5.1: `main.rs` — window, commands, lifecycle

**Files:**
- Create: `desktop/src-tauri/src/main.rs`

- [ ] **Step 1: Write `main.rs`**

```rust
// Prevents an extra console window on Windows (harmless on macOS).
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod paths;
mod port;
mod prereq;
mod server;
mod setup;
mod state;

use server::ServerProcess;
use tauri::{Manager, WindowEvent};

fn main() {
    tauri::Builder::default()
        .manage(ServerProcess::default())
        .invoke_handler(tauri::generate_handler![
            setup::check_prerequisites,
            setup::install_prerequisite,
            setup::bootstrap_venv,
            server::start_server,
        ])
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { .. } = event {
                let state = window.state::<ServerProcess>();
                server::kill(&state);
            }
        })
        .run(tauri::generate_context!())
        .expect("erro ao iniciar o Meeting Processor");
}
```

- [ ] **Step 2: Reference the pure modules so the compiler keeps them**

The `state` module's functions are used by tests but `main.rs` doesn't call `next_state` directly yet (the JS drives the flow). Add `#![allow(dead_code)]` is undesirable; instead add a tiny assertion in `main` is overkill. Leave `mod state;` — `cargo test` exercises it. If the compiler warns "unused", that is acceptable (warnings, not errors). Confirm no `-D warnings` is set.

- [ ] **Step 3: Commit**

```bash
git add desktop/src-tauri/src/main.rs
git commit -m "feat(desktop): main entrypoint — window, commands, kill-on-close

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 5.2: Full compile + unit tests green

**Files:** none (verification).

- [ ] **Step 1: Compile the whole crate**

Run: `cd desktop/src-tauri && cargo build`
Expected: builds with no errors (warnings about unused `state` helpers are OK).

- [ ] **Step 2: Run all Rust unit tests**

Run: `cd desktop/src-tauri && cargo test`
Expected: `port`, `prereq`, `state` tests all PASS (14 tests total).

- [ ] **Step 3: Fix any compile errors before proceeding.** Common issues: wrong Tauri trait import (`Emitter` for `.emit`, `Manager` for `.path()`/`.state()`), `reqwest` needing the `default-features = false` http path. Re-run until green.

---

## Phase 6 — Build pipeline, resources & docs

### Task 6.1: Default config template + resource staging

**Files:**
- Create: `desktop/src-tauri/resources/config.default.yaml` (copied from repo `config.yaml`, with `vault_dir: "./vault"` kept relative so it lands under the data dir)

- [ ] **Step 1: Create the default config**

Run:
```bash
cp config.yaml desktop/src-tauri/resources/config.default.yaml
```
Verify `vault_dir` is `"./vault"` and `temp_dir` is `".tmp"` (relative — they resolve under `MEETING_DATA_DIR`).

- [ ] **Step 2: Commit**

```bash
git add desktop/src-tauri/resources/config.default.yaml
git commit -m "chore(desktop): default config template for first run

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 6.2: `build.sh` — orchestrate the full build

**Files:**
- Create: `desktop/build.sh`

- [ ] **Step 1: Write `desktop/build.sh`**

```bash
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
# Copy the package but exclude caches and any local vault/uploads.
rsync -a --delete \
  --exclude '__pycache__' --exclude '*.pyc' \
  "$ROOT/meeting_processor/" "$RES/meeting_processor/"
cp "$ROOT/requirements.txt" "$RES/requirements.txt"
[ -f "$RES/config.default.yaml" ] || cp "$ROOT/config.yaml" "$RES/config.default.yaml"

echo "==> 3/4 tauri build"
( cd "$DESKTOP/src-tauri" && cargo build && npx --yes @tauri-apps/cli build )

APP="$DESKTOP/src-tauri/target/release/bundle/macos/Meeting Processor.app"
echo "==> 4/4 Ad-hoc codesign"
codesign --force --deep --sign - "$APP" || echo "codesign skipped"

echo "Done. App at: $APP"
echo "DMG at: $DESKTOP/src-tauri/target/release/bundle/dmg/"
```

- [ ] **Step 2: Make it executable**

Run: `chmod +x desktop/build.sh`

- [ ] **Step 3: Run the full build**

Run: `./desktop/build.sh`
Expected: ends with "Done. App at: …/Meeting Processor.app". First build downloads Rust deps (slow).

- [ ] **Step 4: Commit**

```bash
git add desktop/build.sh
git commit -m "build(desktop): full app+dmg build pipeline with ad-hoc signing

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 6.3: README + manual smoke checklist

**Files:**
- Create: `desktop/README.md`

- [ ] **Step 1: Write `desktop/README.md`**

````markdown
# Meeting Processor — Desktop (macOS)

Native macOS shell (Tauri) around the Meeting Processor server + SPA.

## Build

```bash
./desktop/build.sh
```

Produces `Meeting Processor.app` and a `.dmg` under
`desktop/src-tauri/target/release/bundle/`.

## First launch (for the people you share it with)

The app is **unsigned**. macOS Gatekeeper will block the first open. Once:

1. Right-click the app → **Open** → **Open** again. (Or run
   `xattr -dr com.apple.quarantine "/Applications/Meeting Processor.app"`.)
2. On first run the app detects/install missing tools (Homebrew, Python 3.11,
   ffmpeg) and sets up its environment. This needs an internet connection.
3. All data lives in `~/Library/Application Support/com.meetingprocessor.desktop/`.

## Manual smoke checklist

- [ ] **Fresh setup:** delete `~/Library/Application Support/com.meetingprocessor.desktop/.venv`,
      relaunch → setup runs, bootstraps venv, then the SPA loads.
- [ ] **Missing ffmpeg:** `brew uninstall ffmpeg`, relaunch → ffmpeg shown missing,
      "Instalar e configurar" installs it, then app starts.
- [ ] **Port in use:** start something on a random port, relaunch → app still
      picks a free port and starts (no 8765 dependency).
- [ ] **Quit kills server:** with the app running, `pgrep -fl "meeting_processor web"`
      shows the child; quit the app → re-run `pgrep` shows nothing (no orphan).
- [ ] **Data isolation:** confirm `vault/` and logs appear under Application Support,
      not inside the `.app` bundle.
````

- [ ] **Step 2: Commit**

```bash
git add desktop/README.md
git commit -m "docs(desktop): build + first-launch + smoke checklist

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 6.4: Manual end-to-end smoke run

**Files:** none (verification).

- [ ] **Step 1:** Run `./desktop/build.sh`, open the built `.app`, and walk the smoke checklist in `desktop/README.md`. Fix any issue in the relevant module and re-commit.

- [ ] **Step 2:** Confirm the SPA loads at the handed-off `/ui` URL and a meeting detail page renders (the existing app behind the wrapper).

---

## Self-Review Notes

- **Spec coverage:** architecture (Phase 1,5), setup state machine (2.3 + 4.1), commands check/install/bootstrap/start (3.2, 3.3), `MEETING_DATA_DIR` (0.1), free port (2.1), supervision/kill-on-exit (3.3, 5.1), packaging+ad-hoc sign (6.2), unsigned first-open docs (6.3), Rust unit tests + Python data-dir test + manual smoke (0.1, 2.x, 6.3/6.4). All spec sections map to a task.
- **Homebrew path:** Apple-Silicon default `/opt/homebrew`, Intel fallback `/usr/local` handled in `setup.rs::brew_path`.
- **Known follow-ups (out of scope per spec):** notarization, Windows/Linux, torch→faster-whisper.
