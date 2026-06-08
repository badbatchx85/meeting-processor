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
