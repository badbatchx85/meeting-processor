//! Library crate root: module declarations + the Tauri application entrypoint.
pub mod paths;
pub mod platform;
pub mod port;
pub mod prereq;
pub mod server;
pub mod setup;
pub mod state;

use server::ServerProcess;
use tauri::{Manager, WindowEvent};

/// Build and run the Tauri application: register commands, supervise the
/// Python server, and guarantee the child is killed on window-close or app-quit.
pub fn run() {
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
                server::kill(&window.state::<ServerProcess>());
            }
        })
        .build(tauri::generate_context!())
        .expect("erro ao iniciar o Meeting Processor")
        .run(|app_handle, event| {
            if let tauri::RunEvent::ExitRequested { .. } = event {
                server::kill(&app_handle.state::<ServerProcess>());
            }
        });
}
