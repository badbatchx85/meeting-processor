//! Spawn and supervise the Python web server. Holds the child handle so the
//! app can kill it on quit (no orphan servers).
use crate::paths;
use crate::platform;
use crate::port::free_port;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;
use tauri::{AppHandle, Emitter};
#[cfg(windows)]
use std::os::windows::process::CommandExt;

/// Shared handle to the running server child, stored in Tauri state.
#[derive(Default)]
pub struct ServerProcess(pub Mutex<Option<Child>>);

fn emit_log(app: &AppHandle, line: &str) {
    let _ = app.emit("setup://log", line.to_string());
}

/// Return the last `lines` lines of a log file (empty string if unreadable).
fn read_log_tail(path: &std::path::Path, lines: usize) -> String {
    match std::fs::read_to_string(path) {
        Ok(s) => {
            let mut tail: Vec<&str> = s.lines().rev().take(lines).collect();
            tail.reverse();
            tail.join("\n")
        }
        Err(_) => String::new(),
    }
}

/// Start the server: kill any leftover child, allocate a port, spawn the venv
/// python with MEETING_DATA_DIR set, capture output to desktop.log, health-poll
/// /api/health, return the /ui URL. On timeout, reap the child and surface the
/// log tail so a failed boot is diagnosable.
#[tauri::command]
pub async fn start_server(
    app: AppHandle,
    state: tauri::State<'_, ServerProcess>,
) -> Result<String, String> {
    let data = paths::data_dir(&app)?;
    let resources = platform::package_dir(&app)?;
    let python = platform::python(&app)?;

    // Reap any server left over from a previous (failed) attempt before spawning
    // a new one — otherwise retries would stack orphaned python processes.
    kill(&state);

    let port = free_port().map_err(|e| format!("porta livre: {e}"))?;
    emit_log(&app, &format!("Iniciando servidor na porta {port}…"));

    let log_path = data.join("desktop.log");
    let log = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)
        .map_err(|e| format!("abrir desktop.log: {e}"))?;
    let log_err = log.try_clone().map_err(|e| format!("clonar log: {e}"))?;

    let child = Command::new(&python)
        .args(["-m", "meeting_processor", "web", "--port", &port.to_string()])
        .env("MEETING_DATA_DIR", &data)
        // A Finder-launched .app has a minimal PATH; the server shells out to
        // ffmpeg for audio extraction, so include the Homebrew bins.
        .env("PATH", platform::extra_path())
        // The bundled meeting_processor package lives in resources/; prepend it
        // to any existing PYTHONPATH so `import meeting_processor` resolves.
        .env(
            "PYTHONPATH",
            match std::env::var("PYTHONPATH") {
                Ok(existing) if !existing.is_empty() => {
                    format!("{}:{}", resources.display(), existing)
                }
                _ => resources.display().to_string(),
            },
        )
        .current_dir(&data)
        .stdout(Stdio::from(log))
        .stderr(Stdio::from(log_err))
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
        tokio::time::sleep(Duration::from_millis(500)).await;
    }

    // Timed out: reap the failed child and surface the log tail for diagnosis.
    kill(&state);
    let tail = read_log_tail(&log_path, 20);
    Err(format!(
        "o servidor não respondeu a tempo.\n\nÚltimas linhas do log:\n{tail}"
    ))
}

/// Kill the child if running: graceful SIGTERM first (so FastAPI runs its
/// shutdown and child processes are cleaned up), then SIGKILL as a fallback.
/// Idempotent — `take()` makes a second call a no-op.
pub fn kill(state: &ServerProcess) {
    let child = state.0.lock().unwrap().take();
    if let Some(mut child) = child {
        // SIGTERM for a graceful shutdown.
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
        // Give it up to ~3s to exit on its own.
        for _ in 0..30 {
            match child.try_wait() {
                Ok(Some(_)) => return,
                Ok(None) => std::thread::sleep(Duration::from_millis(100)),
                Err(_) => break,
            }
        }
        // Still alive — force it.
        let _ = child.kill();
        let _ = child.wait();
    }
}
