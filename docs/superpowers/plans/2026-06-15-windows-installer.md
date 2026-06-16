# Windows Lite Installer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a Windows NSIS installer for the Tauri desktop app that bootstraps a Python venv on first run (mirroring macOS).

**Architecture:** `cfg`-gated Rust arms (so each OS compiles only its own paths), a Windows-only `tauri.windows.conf.json` overlay that declares the bundled source, a `build-windows.ps1`, an OS-aware setup screen, and a `windows-latest` CI workflow.

**Tech Stack:** Rust/Tauri 2, PowerShell, GitHub Actions; the Python backend is unchanged.

**Verification reality:** the `cfg(windows)` Rust arms and NSIS bundling compile/build ONLY on Windows. On macOS the local signal is `cargo check` (the macOS+common arms must stay green after the cfg restructure — baseline confirmed green, ~3 min cold / seconds warm) plus the pure unit tests. The end-to-end proof is the `windows-installer.yml` CI run; expect 1–3 iterations. Run cargo commands from `desktop/src-tauri/`.

---

## File Structure
- **Modify** `desktop/src-tauri/Cargo.toml` — gate `libc` to unix.
- **Modify** `desktop/src-tauri/src/platform.rs` — three-way arms + `windows_python` + test.
- **Modify** `desktop/src-tauri/src/paths.rs` — `venv_python` cfg-aware.
- **Modify** `desktop/src-tauri/src/server.rs` — Windows `kill` arm.
- **Modify** `desktop/src-tauri/src/prereq.rs` — `os` field.
- **Modify** `desktop/src-tauri/src/setup.rs` — Windows bootstrap/prereq/install.
- **Create** `desktop/src-tauri/tauri.windows.conf.json` — NSIS overlay.
- **Create** `desktop/build-windows.ps1` — Windows build script.
- **Modify** `desktop/ui/setup.js` — OS-aware checks.
- **Create** `.github/workflows/windows-installer.yml`.

---

### Task 1: Rust portability (compile on Windows, stay green on macOS)

**Files:** Modify `Cargo.toml`, `src/platform.rs`, `src/paths.rs`, `src/server.rs`.

- [ ] **Step 1: Add the failing test** — in `src/platform.rs`, inside the existing `#[cfg(test)] mod tests`, add:

```rust
    #[test]
    fn windows_python_is_under_data_scripts() {
        let p = windows_python(Path::new("/data"));
        assert!(p.ends_with("Scripts/python.exe"), "got {p:?}");
        assert!(p.starts_with("/data/.venv"));
    }
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cargo test --lib platform 2>&1 | tail -15`
Expected: FAIL — `windows_python` not found.

- [ ] **Step 3: Add `windows_python` + restructure the cfg arms** in `src/platform.rs`.
  Add the pure builder next to `macos_python`/`linux_python`:

```rust
/// Windows: the venv python created during bootstrap (Scripts\python.exe).
pub fn windows_python(data_dir: &Path) -> PathBuf {
    data_dir.join(".venv").join("Scripts").join("python.exe")
}
```

  Replace the `needs_bootstrap` pair with:

```rust
#[cfg(any(target_os = "macos", target_os = "windows"))]
pub fn needs_bootstrap() -> bool {
    true
}
#[cfg(not(any(target_os = "macos", target_os = "windows")))]
pub fn needs_bootstrap() -> bool {
    false
}
```

  Gate `appdir()` to the linux-only arm:

```rust
#[cfg(all(not(target_os = "macos"), not(target_os = "windows")))]
fn appdir() -> PathBuf {
    std::env::var("APPDIR").map(PathBuf::from).unwrap_or_else(|_| PathBuf::from("."))
}
```

  Replace the `python` arms (macos stays; add windows; linux narrows):

```rust
#[cfg(target_os = "macos")]
pub fn python(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(macos_python(&crate::paths::data_dir(app)?))
}
#[cfg(target_os = "windows")]
pub fn python(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(windows_python(&crate::paths::data_dir(app)?))
}
#[cfg(all(not(target_os = "macos"), not(target_os = "windows")))]
pub fn python(_app: &AppHandle) -> Result<PathBuf, String> {
    Ok(linux_python(&appdir()))
}
```

  Replace the `package_dir` arms:

```rust
#[cfg(any(target_os = "macos", target_os = "windows"))]
pub fn package_dir(app: &AppHandle) -> Result<PathBuf, String> {
    crate::paths::resource_dir(app)
}
#[cfg(all(not(target_os = "macos"), not(target_os = "windows")))]
pub fn package_dir(_app: &AppHandle) -> Result<PathBuf, String> {
    Ok(linux_package_dir(&appdir()))
}
```

  Replace the `extra_path` arms (macos stays; add windows; linux narrows):

```rust
#[cfg(target_os = "macos")]
pub fn extra_path() -> String {
    crate::paths::shell_path()
}
#[cfg(target_os = "windows")]
pub fn extra_path() -> String {
    std::env::var("PATH").unwrap_or_default()
}
#[cfg(all(not(target_os = "macos"), not(target_os = "windows")))]
pub fn extra_path() -> String {
    let bin = linux_bin_dir(&appdir());
    match std::env::var("PATH") {
        Ok(p) if !p.is_empty() => format!("{}:{}", bin.display(), p),
        _ => bin.display().to_string(),
    }
}
```

- [ ] **Step 4: Run the test + macOS build check**

Run: `cargo test --lib platform 2>&1 | tail -15` → the 5 path tests pass (incl. `windows_python_is_under_data_scripts`).
Run: `cargo check --message-format=short 2>&1 | tail -3` → `Finished` (macOS build still green).

- [ ] **Step 5: `paths.rs::venv_python` cfg-aware.** Replace the single `venv_python` with:

```rust
/// The venv python created during bootstrap.
#[cfg(not(target_os = "windows"))]
pub fn venv_python(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(data_dir(app)?.join(".venv").join("bin").join("python"))
}
#[cfg(target_os = "windows")]
pub fn venv_python(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(data_dir(app)?.join(".venv").join("Scripts").join("python.exe"))
}
```

- [ ] **Step 6: `server.rs::kill` Windows arm + libc gating.** At the top of `server.rs`, under the existing imports, add:

```rust
#[cfg(windows)]
use std::os::windows::process::CommandExt;
```

  In `kill`, replace the `unsafe { libc::kill(...) }` line with:

```rust
        #[cfg(unix)]
        unsafe {
            libc::kill(child.id() as libc::pid_t, libc::SIGTERM);
        }
        #[cfg(windows)]
        {
            let _ = std::process::Command::new("taskkill")
                .args(["/PID", &child.id().to_string(), "/T", "/F"])
                .creation_flags(0x0800_0000) // CREATE_NO_WINDOW
                .status();
        }
```

  (The `try_wait` loop + `child.kill()` fallback below stay unchanged.)

- [ ] **Step 7: `Cargo.toml` — gate `libc` to unix.** Remove `libc = "0.2"` from `[dependencies]` and add at the end of the file:

```toml
[target.'cfg(unix)'.dependencies]
libc = "0.2"
```

- [ ] **Step 8: Verify macOS build intact + commit**

Run: `cargo check --message-format=short 2>&1 | tail -3` → `Finished` (no regression; `libc` still resolves on macOS via the unix table, `kill` still uses it under `#[cfg(unix)]`).
Run: `cargo test --lib 2>&1 | tail -6` → all path/prereq tests pass.

```bash
git add desktop/src-tauri/Cargo.toml desktop/src-tauri/src/platform.rs desktop/src-tauri/src/paths.rs desktop/src-tauri/src/server.rs
git commit -m "feat(desktop): cfg-gate the Rust shell for Windows (platform/paths/server/libc)"
```

---

### Task 2: Windows first-run bootstrap (`setup.rs` + `prereq.rs`)

**Files:** Modify `src/prereq.rs`, `src/setup.rs`.

- [ ] **Step 1: Add the `os` field test** — in `src/prereq.rs`, add a `#[cfg(test)] mod tests` (or extend it) with:

```rust
#[cfg(test)]
mod os_field_tests {
    use super::*;
    #[test]
    fn prerequisites_carries_os() {
        let p = Prerequisites {
            brew: Status::Ok, python311: Status::Ok, ffmpeg: Status::Ok,
            venv: Status::Ok, os: "windows".to_string(),
        };
        assert_eq!(p.os, "windows");
    }
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cargo test --lib prereq 2>&1 | tail -15`
Expected: FAIL — `Prerequisites` has no field `os`.

- [ ] **Step 3: Add the `os` field** to `Prerequisites` in `src/prereq.rs`:

```rust
#[derive(Debug, Clone, Serialize)]
pub struct Prerequisites {
    pub brew: Status,
    pub python311: Status,
    pub ffmpeg: Status,
    pub venv: Status,
    pub os: String,
}
```

- [ ] **Step 4: Run the test + find the other construction site**

Run: `cargo test --lib prereq 2>&1 | tail -8` → the test passes BUT `cargo check` will now fail because `setup.rs` builds a `Prerequisites` literal without `os`. That's expected — Step 5 fixes it.

- [ ] **Step 5: Update `setup.rs`** — add the Windows command helpers + `os` field + cfg-gated python/pip. At the top of `setup.rs` (after the existing `const BREW`), add:

```rust
#[cfg(target_os = "windows")]
fn py_program() -> &'static str { "py" }
#[cfg(target_os = "windows")]
fn py_prefix() -> Vec<&'static str> { vec!["-3.11"] }
#[cfg(not(target_os = "windows"))]
fn py_program() -> &'static str { "python3.11" }
#[cfg(not(target_os = "windows"))]
fn py_prefix() -> Vec<&'static str> { vec![] }
```

  In `check_prerequisites`, update BOTH return literals to include `os: std::env::consts::OS.to_string()` — the early non-bootstrap return:

```rust
    if !platform::needs_bootstrap() {
        return Ok(Prerequisites {
            brew: Status::Ok, python311: Status::Ok, ffmpeg: Status::Ok,
            venv: Status::Ok, os: std::env::consts::OS.to_string(),
        });
    }
```

  and the main return. In the main path, make brew Windows-safe and python detection use the launcher:

```rust
    #[cfg(target_os = "windows")]
    let brew = Status::Ok; // sem Homebrew no Windows
    #[cfg(not(target_os = "windows"))]
    let brew = {
        let (brew_out, _) = capture(brew_path(), &["--version"]).await;
        parse_brew_version(&brew_out)
    };

    let mut py_args = py_prefix();
    py_args.push("--version");
    let (py_out, py_err) = capture(py_program(), &py_args).await;
    let (ff_out, _) = capture("ffmpeg", &["-version"]).await;

    let venv = if paths::venv_python(&app)?.exists() { Status::Ok } else { Status::Missing };

    Ok(Prerequisites {
        brew,
        python311: parse_python_version(&py_out, &py_err),
        ffmpeg: parse_ffmpeg_version(&ff_out),
        venv,
        os: std::env::consts::OS.to_string(),
    })
```

  In `install_prerequisite`, add Windows winget arms. Replace the `match name.as_str()` body's `"python311"`/`"ffmpeg"` arms with cfg-gated versions:

```rust
        "python311" => {
            #[cfg(target_os = "windows")]
            { run_streamed(&app, "winget", &["install", "-e", "--id", "Python.Python.3.11"]).await }
            #[cfg(not(target_os = "windows"))]
            { run_streamed(&app, brew_path(), &["install", "python@3.11"]).await }
        }
        "ffmpeg" => {
            #[cfg(target_os = "windows")]
            { run_streamed(&app, "winget", &["install", "-e", "--id", "Gyan.FFmpeg"]).await }
            #[cfg(not(target_os = "windows"))]
            { run_streamed(&app, brew_path(), &["install", "ffmpeg"]).await }
        }
```

  In `bootstrap_venv`, replace the venv-create + pip lines:

```rust
    emit_log(&app, "Criando ambiente Python (.venv)…");
    let mut venv_args = py_prefix();
    venv_args.extend(["-m", "venv", &venv.to_string_lossy()]);
    run_streamed(&app, py_program(), &venv_args).await?;

    #[cfg(target_os = "windows")]
    let pip = venv.join("Scripts").join("pip.exe");
    #[cfg(not(target_os = "windows"))]
    let pip = venv.join("bin").join("pip");
    emit_log(&app, "Instalando dependências (pode demorar)…");
    run_streamed(&app, &pip.to_string_lossy(), &["install", "-r", &requirements.to_string_lossy()]).await
```

  Note: `&venv.to_string_lossy()` is a temporary; bind it first if the borrow
  checker complains: `let venv_s = venv.to_string_lossy().to_string();` then push `&venv_s`.

- [ ] **Step 6: Verify macOS build + tests, then commit**

Run: `cargo check --message-format=short 2>&1 | tail -3` → `Finished` (macOS arms compile; the `#[cfg(not(windows))]` brew/pip paths are the macOS ones).
Run: `cargo test --lib 2>&1 | tail -6` → all pass.

```bash
git add desktop/src-tauri/src/prereq.rs desktop/src-tauri/src/setup.rs
git commit -m "feat(desktop): Windows first-run bootstrap (py -3.11, winget, Scripts venv)"
```

---

### Task 3: Packaging — NSIS overlay + build script

**Files:** Create `desktop/src-tauri/tauri.windows.conf.json`, `desktop/build-windows.ps1`.

- [ ] **Step 1: Create `desktop/src-tauri/tauri.windows.conf.json`:**

```json
{
  "bundle": {
    "active": true,
    "targets": ["nsis"],
    "icon": ["icons/icon.ico"],
    "resources": {
      "resources/meeting_processor": "meeting_processor",
      "resources/requirements.txt": "requirements.txt",
      "resources/config.default.yaml": "config.default.yaml"
    }
  }
}
```

- [ ] **Step 2: Validate the JSON**

Run: `python3 -c "import json; json.load(open('desktop/src-tauri/tauri.windows.conf.json')); print('valid')"`
Expected: `valid`.

- [ ] **Step 3: Create `desktop/build-windows.ps1`:**

```powershell
# Build the Meeting Processor Windows NSIS installer.
#
# Lite strategy (mirrors macOS): bundle the raw meeting_processor source + built
# SPA; the app bootstraps a venv + pip install on first run. The Python payload
# is declared in tauri.windows.conf.json `bundle.resources` (NSIS must include
# it during the build, unlike the macOS post-build inject).
$ErrorActionPreference = "Stop"

$Root    = (Resolve-Path "$PSScriptRoot\..").Path
$Desktop = Join-Path $Root "desktop"
$Tauri   = Join-Path $Desktop "src-tauri"
$Res     = Join-Path $Tauri "resources"

Write-Host "==> 1/3 Building SPA"
Push-Location (Join-Path $Root "frontend")
if (-not (Test-Path "node_modules")) { npm ci }
npm run build
Pop-Location

Write-Host "==> 2/3 Staging Python payload into resources/"
New-Item -ItemType Directory -Force -Path (Join-Path $Res "meeting_processor") | Out-Null
robocopy (Join-Path $Root "meeting_processor") (Join-Path $Res "meeting_processor") /MIR /XD __pycache__ /XF *.pyc | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE)" } else { $global:LASTEXITCODE = 0 }
Copy-Item (Join-Path $Root "requirements.txt") (Join-Path $Res "requirements.txt") -Force

Write-Host "==> 3/3 tauri build (nsis)"
Push-Location $Tauri
npx --yes "@tauri-apps/cli@^2" build --config tauri.windows.conf.json --bundles nsis
Pop-Location

Write-Host "Done. Installer:"
Get-ChildItem (Join-Path $Tauri "target\release\bundle\nsis\*-setup.exe") | ForEach-Object { Write-Host $_.FullName }
```

(Note: `config.default.yaml` already lives in `resources/` checked into the repo;
robocopy mirrors only `meeting_processor/`, requirements is copied, and the YAML
is already present — so the `bundle.resources` map resolves all three.)

- [ ] **Step 4: Commit**

```bash
git add desktop/src-tauri/tauri.windows.conf.json desktop/build-windows.ps1
git commit -m "build(desktop): Windows NSIS overlay + build-windows.ps1"
```

---

### Task 4: OS-aware setup screen

**Files:** Modify `desktop/ui/setup.js`.

- [ ] **Step 1: Make the checks OS-aware.** In `desktop/ui/setup.js`:
  - Replace the module-level `const LABELS = {...}` with a function that drops brew
    off Windows, and thread `p.os` through. Change `renderChecks(p)` and
    `missingList(p)` to use it:

```javascript
function labelsFor(os) {
  const base = { python311: "Python 3.11", ffmpeg: "ffmpeg", venv: "Ambiente Python" };
  return os === "windows" ? base : { brew: "Homebrew", ...base };
}

function renderChecks(p) {
  checksEl.innerHTML = "";
  for (const [key, label] of Object.entries(labelsFor(p.os))) {
    const li = document.createElement("li");
    const ok = p[key] === "ok";
    li.className = ok ? "ok" : "missing";
    li.textContent = `${label}: ${p[key] === "ok" ? "pronto" : p[key] === "wrong_version" ? "versão incorreta" : "faltando"}`;
    checksEl.appendChild(li);
  }
}

function missingList(p) {
  const keys = p.os === "windows" ? ["python311", "ffmpeg"] : ["brew", "python311", "ffmpeg"];
  return keys.filter((k) => p[k] !== "ok");
}
```

  - In `runSetup(missing)`, the `brew` install line is now harmless (Windows never
    lists brew), but guard it anyway — it already does `if (missing.includes("brew"))`,
    so no change needed there.

- [ ] **Step 2: Syntax-check**

Run: `node --check desktop/ui/setup.js`
Expected: no output (valid). (`node --check` parses without the Tauri globals — it
only validates syntax, which is what we need here.)

- [ ] **Step 3: Commit**

```bash
git add desktop/ui/setup.js
git commit -m "feat(desktop): OS-aware setup screen (hide Homebrew on Windows)"
```

---

### Task 5: CI — `windows-installer.yml`

**Files:** Create `.github/workflows/windows-installer.yml`.

- [ ] **Step 1: Create `.github/workflows/windows-installer.yml`:**

```yaml
name: Windows Installer

on:
  workflow_dispatch:
  push:
    tags: ["v*"]

jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "20"

      - uses: dtolnay/rust-toolchain@stable

      - name: Build Windows installer
        shell: pwsh
        run: ./desktop/build-windows.ps1

      - name: Upload installer
        uses: actions/upload-artifact@v4
        with:
          name: meeting-processor-windows-nsis
          path: desktop/src-tauri/target/release/bundle/nsis/*-setup.exe
          if-no-files-found: error

      - name: Attach to release (on tag)
        if: startsWith(github.ref, 'refs/tags/v')
        uses: softprops/action-gh-release@v2
        with:
          files: desktop/src-tauri/target/release/bundle/nsis/*-setup.exe
```

- [ ] **Step 2: Validate the YAML**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/windows-installer.yml')); print('valid')"`
Expected: `valid` (if PyYAML is unavailable, `.venv/bin/python -c ...` from the repo root works — PyYAML is a backend dep).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/windows-installer.yml
git commit -m "ci(desktop): windows-latest NSIS installer build + release upload"
```

- [ ] **Step 4: Push to a branch + trigger CI (the real verification).**

```bash
git push -u origin HEAD:feat/windows-installer
gh workflow run windows-installer.yml --repo badbatchx85/meeting-processor --ref feat/windows-installer
```

Then read the run: `gh run list --repo badbatchx85/meeting-processor --workflow windows-installer.yml` →
`gh run view <id> --log-failed --repo badbatchx85/meeting-processor`. Fix any
compile/bundling errors (Windows-only arms surface here for the first time),
commit file-scoped, push, re-run. Repeat until the `*-setup.exe` artifact uploads.

---

## Self-Review

**Spec coverage:**
- §1 Rust portability: `libc` unix-gate, `platform.rs` three-way + `windows_python`, `paths.rs` venv layout, `server.rs` Windows kill → Task 1. ✓
- §2 Windows bootstrap: `prereq.rs` `os` field, `setup.rs` `py -3.11`/winget/Scripts pip + brew-skip → Task 2. ✓
- §3 Packaging: `tauri.windows.conf.json` overlay + `build-windows.ps1` → Task 3. ✓
- §4 Setup UI OS-awareness → Task 4. ✓
- §5 CI `windows-installer.yml` → Task 5. ✓
- Verification reality (cargo check on macOS + pure tests local; CI for Windows) → embedded in each task + Task 5 Step 4. ✓
- Out of scope (self-contained bundle, signing, auto-update) → untouched. ✓

**Placeholder scan:** none — every step has concrete code/commands.

**Type consistency:** `windows_python(&Path) -> PathBuf` (Task 1) used by `platform::python` (Task 1) + `paths::venv_python` mirrors the `Scripts/python.exe` layout (Task 1). `Prerequisites.os: String` (Task 2) set in both `setup.rs` returns (Task 2) and read by `setup.js` `p.os` (Task 4). `py_program()`/`py_prefix()` (Task 2) used in `check_prerequisites`/`bootstrap_venv` (Task 2). `tauri.windows.conf.json` `bundle.resources` dests align with `package_dir`==`resource_dir` (Task 1) so `import meeting_processor` resolves. The `--config tauri.windows.conf.json` flag (Task 3 PS1) matches the file (Task 3). The CI path `target/release/bundle/nsis/*-setup.exe` matches the PS1 output (Task 3). Names consistent throughout. ✓
```
