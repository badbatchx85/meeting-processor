//! Detect host prerequisites (Homebrew, Python 3.11, ffmpeg) and parse their
//! version output. Parsing is pure and unit-tested; the actual command
//! execution is a thin wrapper kept separate so tests don't shell out.
use serde::Serialize;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Status {
    Ok,
    Missing,
    WrongVersion,
}

#[derive(Debug, Clone, Serialize)]
pub struct Prerequisites {
    pub brew: Status,
    pub python311: Status,
    pub ffmpeg: Status,
    pub venv: Status,
}

/// `python3.11 --version` prints e.g. "Python 3.11.9". Accept any 3.11.x.
pub fn parse_python_version(stdout: &str, stderr: &str) -> Status {
    let text = if stdout.trim().is_empty() { stderr } else { stdout };
    let text = text.trim();
    match text.strip_prefix("Python ") {
        Some(v) if v.starts_with("3.11.") || v == "3.11" => Status::Ok,
        Some(_) => Status::WrongVersion,
        None => Status::Missing,
    }
}

/// `ffmpeg -version` prints "ffmpeg version ..." on success.
pub fn parse_ffmpeg_version(stdout: &str) -> Status {
    if stdout.trim_start().starts_with("ffmpeg version") {
        Status::Ok
    } else {
        Status::Missing
    }
}

/// `brew --version` prints "Homebrew x.y.z".
pub fn parse_brew_version(stdout: &str) -> Status {
    if stdout.trim_start().starts_with("Homebrew") {
        Status::Ok
    } else {
        Status::Missing
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn python_311_is_ok() {
        assert_eq!(parse_python_version("Python 3.11.9\n", ""), Status::Ok);
    }

    #[test]
    fn python_312_is_wrong_version() {
        assert_eq!(parse_python_version("Python 3.12.1\n", ""), Status::WrongVersion);
    }

    #[test]
    fn python_uses_stderr_when_stdout_empty() {
        assert_eq!(parse_python_version("", "Python 3.11.2\n"), Status::Ok);
    }

    #[test]
    fn python_garbage_is_missing() {
        assert_eq!(parse_python_version("zsh: command not found", ""), Status::Missing);
    }

    #[test]
    fn ffmpeg_ok() {
        assert_eq!(parse_ffmpeg_version("ffmpeg version 6.1 Copyright"), Status::Ok);
    }

    #[test]
    fn ffmpeg_missing() {
        assert_eq!(parse_ffmpeg_version(""), Status::Missing);
    }

    #[test]
    fn brew_ok() {
        assert_eq!(parse_brew_version("Homebrew 4.2.0"), Status::Ok);
    }
}
