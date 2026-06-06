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
