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
