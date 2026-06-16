# Windows Lite Installer (Tauri NSIS)

**Date:** 2026-06-15
**Status:** Approved design

## Goal

Ship a Windows installer for the Tauri desktop app, mirroring the existing macOS
first-run flow: the installer bundles the raw `meeting_processor/` source + built
SPA; on first launch the Rust shell detects Python 3.11 + ffmpeg, creates a venv,
and `pip install`s. No frozen binary, no bundled Python. Verified by a
`windows-latest` CI build (cannot be built on the macOS dev machine).

## Background (exact, from exploration)

- Desktop app: Tauri 2 at `desktop/src-tauri/` (Rust) + a vanilla-JS setup screen
  `desktop/ui/setup.js` + the React SPA (built into `desktop/ui`).
- **macOS** = first-run bootstrap (`platform::needs_bootstrap()==true`): system
  `python3.11` → `data_dir/.venv` → `pip install -r requirements.txt`. The Python
  payload is injected into the `.app` *after* `tauri build` by `desktop/build.sh`.
- **Linux** = self-contained AppImage (`needs_bootstrap()==false`).
- `platform.rs` splits **macos vs not-macos** (the not-macos arm == Linux today).
- `paths.rs::venv_python` = `data_dir/.venv/bin/python` (POSIX layout).
- `server.rs::kill` uses `unsafe { libc::kill(pid, SIGTERM) }` then `child.kill()`.
- `Cargo.toml` has `libc = "0.2"` unconditionally (POSIX-only crate).
- `setup.rs`: `check_prerequisites` (brew/python311/ffmpeg/venv), `install_prerequisite`
  (brew/python311/ffmpeg via Homebrew), `bootstrap_venv` (`python3.11 -m venv` +
  `venv/bin/pip install`). Registered in `lib.rs` `generate_handler!`.
- `prereq.rs`: `Prerequisites { brew, python311, ffmpeg, venv: Status }`;
  `parse_python_version` accepts any `3.11.x` (works for `py -3.11 --version` too).
- `tauri.conf.json`: `bundle.targets=["app"]`, `icon.icns` only, **no** `resources`
  key (macOS injects post-build). `icon.ico` ALREADY exists in `src-tauri/icons/`.
- CI to mirror: `.github/workflows/linux-appimage.yml` (ubuntu-22.04, Node 20, Rust
  stable, runs the build script, uploads the artifact).
- `audio.py:15` already prints `winget install Gyan.FFmpeg` on `win32`;
  `web/runtime.py:84` already sets `CREATE_NEW_PROCESS_GROUP` on `win32`.

## 1. Rust portability (the shell must compile on Windows)

### `Cargo.toml`
Move `libc` under a unix target table:
```toml
[target.'cfg(unix)'.dependencies]
libc = "0.2"
```

### `platform.rs` — three-way macos / windows / linux
- Add a pure builder (compiled everywhere, unit-tested on macOS):
  ```rust
  /// Windows: the venv python created during bootstrap (Scripts\python.exe).
  pub fn windows_python(data_dir: &Path) -> PathBuf {
      data_dir.join(".venv").join("Scripts").join("python.exe")
  }
  ```
- `needs_bootstrap()`: `true` for macos AND windows; `false` only for the
  remaining (linux) arm. Restructure to `#[cfg(any(target_os="macos",
  target_os="windows"))] -> true` / `#[cfg(not(any(...)))] -> false`.
- `python(app)`: add `#[cfg(target_os="windows")]` →
  `Ok(windows_python(&crate::paths::data_dir(app)?))`. The existing linux arm
  becomes `#[cfg(all(not(target_os="macos"), not(target_os="windows")))]`.
- `package_dir(app)`: windows arm → `crate::paths::resource_dir(app)` (the
  installer lays the source under the Tauri resource dir, like macOS).
- `extra_path()`: windows arm → return the existing `PATH` unchanged (ffmpeg is
  expected on PATH; Windows uses `;` separators and no AppDir). Just
  `std::env::var("PATH").unwrap_or_default()`.
- The `appdir()` helper stays gated to the linux arm only
  (`#[cfg(all(not(macos), not(windows)))]`).

### `paths.rs::venv_python` — cfg-aware layout
```rust
#[cfg(not(target_os = "windows"))]
pub fn venv_python(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(data_dir(app)?.join(".venv").join("bin").join("python"))
}
#[cfg(target_os = "windows")]
pub fn venv_python(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(data_dir(app)?.join(".venv").join("Scripts").join("python.exe"))
}
```
(`shell_path()` stays `#[cfg(target_os="macos")]` — Windows never calls it.)

### `server.rs::kill` — Windows arm
Gate the POSIX block and add a Windows one:
```rust
        #[cfg(unix)]
        unsafe { libc::kill(child.id() as libc::pid_t, libc::SIGTERM); }
        #[cfg(windows)]
        {
            // No POSIX signals — ask the tree to close, then force below.
            let _ = std::process::Command::new("taskkill")
                .args(["/PID", &child.id().to_string(), "/T", "/F"])
                .creation_flags(0x0800_0000) // CREATE_NO_WINDOW
                .status();
        }
```
The existing 3s `try_wait` loop + `child.kill()` fallback stay (they're portable).
`creation_flags` needs `use std::os::windows::process::CommandExt;` under
`#[cfg(windows)]`.

## 2. Windows first-run bootstrap (`setup.rs` + `prereq.rs`)

Keep the macOS code paths; add Windows ones via `cfg` so each platform compiles
only its own. A small internal abstraction keeps it DRY:

- **Python launcher:** macOS uses `"python3.11"`; Windows uses the Python launcher
  `py` with args `["-3.11", ...]`. Add:
  ```rust
  #[cfg(target_os = "windows")]
  fn py_cmd() -> (&'static str, Vec<&'static str>) { ("py", vec!["-3.11"]) }
  #[cfg(not(target_os = "windows"))]
  fn py_cmd() -> (&'static str, Vec<&'static str>) { ("python3.11", vec![]) }
  ```
- **`check_prerequisites`:** on Windows, skip brew (report `brew: Status::Ok` so it
  drops out of the missing list) and detect python via `py -3.11 --version`. The
  `venv` check already uses `paths::venv_python` (now Scripts-aware). Add an
  `os: String` field to `Prerequisites` (`std::env::consts::OS`) so the UI can
  hide the Homebrew row and relabel install actions.
- **`install_prerequisite`:** Windows arm via winget —
  `"python311"` → `winget install -e --id Python.Python.3.11`,
  `"ffmpeg"` → `winget install -e --id Gyan.FFmpeg`; `"brew"` is a no-op/Err on
  Windows (the UI won't request it).
- **`bootstrap_venv`:** Windows uses `py -3.11 -m venv <venv>` then
  `<venv>\Scripts\pip.exe install -r requirements.txt`. Factor the pip path:
  ```rust
  #[cfg(target_os = "windows")]
  let pip = venv.join("Scripts").join("pip.exe");
  #[cfg(not(target_os = "windows"))]
  let pip = venv.join("bin").join("pip");
  ```

`prereq.rs::parse_python_version` is unchanged (the `Python 3.11.x` format is
identical from `py -3.11 --version`). The `Prerequisites` struct gains
`pub os: String`.

## 3. Packaging

### `desktop/src-tauri/tauri.windows.conf.json` (overlay, Windows-only)
Merged via `tauri build --config`. Declares the NSIS target, the bundled source
(NSIS must include it *during* the build, unlike the macOS post-build inject),
and the `.ico`:
```json
{
  "bundle": {
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
(The `resources` map preserves the tree under the resource dir, which
`platform::package_dir`/`paths::resource_dir` already point at.)

### `desktop/build-windows.ps1` (mirror of `build.sh`)
```
1. build the SPA:  cd frontend; npm ci/install; npm run build  (outputs to desktop/ui)
2. stage payload into desktop/src-tauri/resources/:
   - copy meeting_processor\  (exclude __pycache__, *.pyc)
   - copy requirements.txt, config.default.yaml
3. tauri build:  cd desktop/src-tauri;
   npx @tauri-apps/cli@^2 build --config tauri.windows.conf.json --bundles nsis
4. echo the produced installer path
   (target/release/bundle/nsis/Meeting Processor_1.0.0_x64-setup.exe)
```
PowerShell, `$ErrorActionPreference = "Stop"`.

## 4. Setup UI (`desktop/ui/setup.js`)

- Read `p.os` from `check_prerequisites`. When `os === "windows"`: drop `brew`
  from `LABELS`/`missingList` (hide the Homebrew row) and set the install button
  copy to mention winget. Keep the macOS behavior otherwise. A one-spot change:
  build `LABELS`/`missingList` from `p.os`.

## 5. CI — `.github/workflows/windows-installer.yml`

Mirror `linux-appimage.yml` on `windows-latest`:
- Triggers: `workflow_dispatch` + push to `v*` tags.
- Steps: checkout; Node 20; Rust stable (`dtolnay/rust-toolchain@stable`);
  `./desktop/build-windows.ps1` (shell: pwsh).
- Upload artifact: `desktop/src-tauri/target/release/bundle/nsis/*-setup.exe`.
- On tag: attach to the GitHub Release (`softprops/action-gh-release@v2`).
- (No bundled-deps smoke test like Linux — the lite installer pip-installs at
  user runtime, not build time; the CI proves the installer *builds*.)

## Verification reality

- On macOS I can only confirm `cargo check` still builds the macОS+common arms
  and the pure path-builder unit tests pass — the `cfg(windows)` arms compile
  ONLY on Windows. The real signal is the `windows-latest` CI run; expect 1–3
  iterations (commit → push branch → read CI logs → fix). Each fix is committed
  file-scoped.

## Testing

- **Rust unit tests** (`platform.rs`, run on macOS): `windows_python(Path::new("C:\\data"))`
  ends with `\.venv\Scripts\python.exe` (assert the components, OS-agnostic).
- **`cargo check`** on macOS: the macОS build still compiles after the cfg
  restructure (no regression to the working platform).
- **`prereq.rs`** unit tests: `parse_python_version("Python 3.11.9", "")` → Ok
  (unchanged; confirms `py -3.11` output parses).
- **CI build**: `windows-installer.yml` produces a `*-setup.exe` artifact (the
  end-to-end proof; iterated until green).
- **Manual (user, post-CI):** run the `.exe` on a Windows box → first-run installs
  Python/ffmpeg via winget if missing → venv bootstraps → SPA loads.

## Out of scope

- A self-contained installer bundling Python/ffmpeg (chosen: lite).
- Code signing / notarization of the Windows installer (unsigned for now).
- Auto-update.
- whisper.cpp on Windows (the `.exe` discovery already exists in `transcriber.py`).
- Changing the macOS or Linux builds.
