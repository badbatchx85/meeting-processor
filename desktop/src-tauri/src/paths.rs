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
