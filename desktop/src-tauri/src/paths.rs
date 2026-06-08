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

/// A PATH that includes the Homebrew bins.
///
/// A Finder-launched `.app` inherits only a minimal PATH (`/usr/bin:/bin:…`)
/// without `/opt/homebrew/bin`, so bare `python3.11` / `ffmpeg` invocations
/// (and the server's own `ffmpeg` calls for audio extraction) fail to resolve.
/// We prepend the Homebrew bin dirs (incl. the keg-only python@3.11 bin) for
/// both Apple Silicon and Intel layouts to every process we spawn.
#[cfg(target_os = "macos")]
pub fn shell_path() -> String {
    let brew_dirs = [
        "/opt/homebrew/bin",
        "/opt/homebrew/opt/python@3.11/bin",
        "/usr/local/bin",
        "/usr/local/opt/python@3.11/bin",
    ];
    let prefix = brew_dirs.join(":");
    match std::env::var("PATH") {
        Ok(existing) if !existing.is_empty() => format!("{prefix}:{existing}"),
        _ => prefix,
    }
}
