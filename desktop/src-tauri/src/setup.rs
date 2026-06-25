//! Tauri commands for first-run setup. Each long-running command streams
//! stdout/stderr lines to the webview via the `setup://log` event.
use crate::paths;
use crate::platform;
use crate::prereq::{parse_ffmpeg_version, parse_python_version, Prerequisites, Status};
#[cfg(not(target_os = "windows"))]
use crate::prereq::parse_brew_version;
use std::process::Stdio;
use tauri::{AppHandle, Emitter};
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::Command;

// Homebrew só existe no fluxo macOS; no Windows estes itens ficariam sem uso.
#[cfg(not(target_os = "windows"))]
const BREW: &str = "/opt/homebrew/bin/brew"; // Apple Silicon; Intel is /usr/local/bin/brew

#[cfg(target_os = "windows")]
fn py_program() -> &'static str { "py" }
#[cfg(target_os = "windows")]
fn py_prefix() -> Vec<&'static str> { vec!["-3.11"] }
#[cfg(not(target_os = "windows"))]
fn py_program() -> &'static str { "python3.11" }
#[cfg(not(target_os = "windows"))]
fn py_prefix() -> Vec<&'static str> { vec![] }

/// winget install args, including the agreement/interactivity flags a spawned,
/// non-interactive process needs — otherwise winget can block on a prompt or
/// exit non-zero, which run_streamed would surface as a hard error.
#[cfg(target_os = "windows")]
fn winget_install(id: &str) -> Vec<&str> {
    vec![
        "install",
        "-e",
        "--id",
        id,
        "--accept-package-agreements",
        "--accept-source-agreements",
        "--disable-interactivity",
    ]
}

fn emit_log(app: &AppHandle, line: &str) {
    let _ = app.emit("setup://log", line.to_string());
}

async fn capture(cmd: &str, args: &[&str]) -> (String, String) {
    let mut command = Command::new(cmd);
    command.args(args).env("PATH", platform::extra_path());
    #[cfg(target_os = "windows")]
    command.creation_flags(0x0800_0000); // CREATE_NO_WINDOW: no console flash
    match command.output().await {
        Ok(out) => (
            String::from_utf8_lossy(&out.stdout).to_string(),
            String::from_utf8_lossy(&out.stderr).to_string(),
        ),
        Err(_) => (String::new(), String::new()),
    }
}

#[cfg(not(target_os = "windows"))]
fn brew_path() -> &'static str {
    if std::path::Path::new(BREW).exists() {
        BREW
    } else {
        "/usr/local/bin/brew"
    }
}

#[tauri::command]
pub async fn check_prerequisites(app: AppHandle) -> Result<Prerequisites, String> {
    // Non-macOS (Linux AppImage) ships everything bundled — nothing to detect.
    if !platform::needs_bootstrap() {
        return Ok(Prerequisites {
            brew: Status::Ok,
            python311: Status::Ok,
            ffmpeg: Status::Ok,
            venv: Status::Ok,
            os: std::env::consts::OS.to_string(),
        });
    }

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

    let venv = if paths::venv_python(&app)?.exists() {
        Status::Ok
    } else {
        Status::Missing
    };

    Ok(Prerequisites {
        brew,
        python311: parse_python_version(&py_out, &py_err),
        ffmpeg: parse_ffmpeg_version(&ff_out),
        venv,
        os: std::env::consts::OS.to_string(),
    })
}

/// Run a command, streaming each output line to the webview. Returns Err on
/// non-zero exit so the UI transitions to ERROR.
async fn run_streamed(app: &AppHandle, program: &str, args: &[&str]) -> Result<(), String> {
    emit_log(app, &format!("$ {program} {}", args.join(" ")));
    let mut command = Command::new(program);
    command
        .args(args)
        .env("PATH", platform::extra_path())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    #[cfg(target_os = "windows")]
    command.creation_flags(0x0800_0000); // CREATE_NO_WINDOW: no console flash
    let mut child = command
        .spawn()
        .map_err(|e| format!("falha ao iniciar {program}: {e}"))?;

    let out_task = child.stdout.take().map(|out| {
        let app2 = app.clone();
        tokio::spawn(async move {
            let mut lines = BufReader::new(out).lines();
            while let Ok(Some(l)) = lines.next_line().await {
                emit_log(&app2, &l);
            }
        })
    });
    let err_task = child.stderr.take().map(|err| {
        let app2 = app.clone();
        tokio::spawn(async move {
            let mut lines = BufReader::new(err).lines();
            while let Ok(Some(l)) = lines.next_line().await {
                emit_log(&app2, &l);
            }
        })
    });

    let status = child.wait().await.map_err(|e| e.to_string())?;
    if let Some(t) = out_task { let _ = t.await; }
    if let Some(t) = err_task { let _ = t.await; }

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
        "python311" => {
            #[cfg(target_os = "windows")]
            { run_streamed(&app, "winget", &winget_install("Python.Python.3.11")).await }
            #[cfg(not(target_os = "windows"))]
            { run_streamed(&app, brew_path(), &["install", "python@3.11"]).await }
        }
        "ffmpeg" => {
            #[cfg(target_os = "windows")]
            { run_streamed(&app, "winget", &winget_install("Gyan.FFmpeg")).await }
            #[cfg(not(target_os = "windows"))]
            { run_streamed(&app, brew_path(), &["install", "ffmpeg"]).await }
        }
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
    let venv_s = venv.to_string_lossy().to_string();
    let mut venv_args = py_prefix();
    venv_args.extend(["-m", "venv", venv_s.as_str()]);
    run_streamed(&app, py_program(), &venv_args).await?;

    #[cfg(target_os = "windows")]
    let pip = venv.join("Scripts").join("pip.exe");
    #[cfg(not(target_os = "windows"))]
    let pip = venv.join("bin").join("pip");
    emit_log(&app, "Instalando dependências (pode demorar)…");
    run_streamed(
        &app,
        &pip.to_string_lossy(),
        &["install", "-r", &requirements.to_string_lossy()],
    )
    .await
}
