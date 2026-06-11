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
