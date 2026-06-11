"""Pré-processamento de áudio (denoise/normalize) antes do Whisper."""
from pathlib import Path

from meeting_processor.audio import _ffmpeg_cmd


def test_audio_config_defaults(config):
    assert config.enable_audio_denoise is False
    assert "highpass" in config.audio_filter
    assert "loudnorm" in config.audio_filter


def test_audio_config_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MEETING_AUDIO_DENOISE", "true")
    monkeypatch.setenv("MEETING_AUDIO_FILTER", "anlmdn")
    from meeting_processor.config import load_config
    cfg = load_config()
    assert cfg.enable_audio_denoise is True
    assert cfg.audio_filter == "anlmdn"


def test_ffmpeg_cmd_with_filter():
    cmd = _ffmpeg_cmd(Path("/in.mp4"), Path("/out.wav"), "highpass=f=80")
    assert "-af" in cmd
    assert cmd[cmd.index("-af") + 1] == "highpass=f=80"
    assert cmd.index("-af") < cmd.index("-y")   # filter before output
    assert cmd[-1] == "/out.wav"


def test_ffmpeg_cmd_without_filter():
    cmd = _ffmpeg_cmd(Path("/in.mp4"), Path("/out.wav"), None)
    assert "-af" not in cmd
    assert "16000" in cmd and "-ac" in cmd


# --- Task 2: extract_audio filter + fallback --------------------------------

import subprocess
import pytest

from meeting_processor.audio import extract_audio


def _fake_ok(cmd, **kwargs):
    """Simula ffmpeg com sucesso: cria o arquivo de saída e devolve um result."""
    Path(cmd[-1]).write_bytes(b"WAVDATA")

    class _R:
        stderr = ""
    return _R()


def test_extract_audio_denoise_on(config, monkeypatch):
    config.enable_audio_denoise = True
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _fake_ok(cmd, **kwargs)

    monkeypatch.setattr("meeting_processor.audio.validate_ffmpeg", lambda: True)
    monkeypatch.setattr("meeting_processor.audio.subprocess.run", fake_run)
    extract_audio(Path("/x.mp4"), config)
    assert "-af" in captured["cmd"]
    assert config.audio_filter in captured["cmd"]


def test_extract_audio_denoise_off(config, monkeypatch):
    config.enable_audio_denoise = False
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _fake_ok(cmd, **kwargs)

    monkeypatch.setattr("meeting_processor.audio.validate_ffmpeg", lambda: True)
    monkeypatch.setattr("meeting_processor.audio.subprocess.run", fake_run)
    extract_audio(Path("/x.mp4"), config)
    assert "-af" not in captured["cmd"]


def test_extract_audio_fallback_on_filter_failure(config, monkeypatch):
    config.enable_audio_denoise = True
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if "-af" in cmd:
            raise subprocess.CalledProcessError(1, cmd, stderr="bad filter")
        return _fake_ok(cmd, **kwargs)

    monkeypatch.setattr("meeting_processor.audio.validate_ffmpeg", lambda: True)
    monkeypatch.setattr("meeting_processor.audio.subprocess.run", fake_run)
    out = extract_audio(Path("/x.mp4"), config)
    assert out.exists()
    assert len(calls) == 2
    assert "-af" in calls[0] and "-af" not in calls[1]


def test_extract_audio_raises_when_unfiltered_fails(config, monkeypatch):
    config.enable_audio_denoise = False

    def fake_run(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd, stderr="boom")

    monkeypatch.setattr("meeting_processor.audio.validate_ffmpeg", lambda: True)
    monkeypatch.setattr("meeting_processor.audio.subprocess.run", fake_run)
    with pytest.raises(RuntimeError):
        extract_audio(Path("/x.mp4"), config)
