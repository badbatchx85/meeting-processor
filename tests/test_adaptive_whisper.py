"""Seleção adaptativa do modelo Whisper pela duração do áudio."""
from pathlib import Path

from meeting_processor.config import load_config


# --- Task 1: flag de config ------------------------------------------------


def test_whisper_adaptive_defaults_false(monkeypatch):
    monkeypatch.delenv("MEETING_WHISPER_ADAPTIVE", raising=False)
    assert load_config().whisper_adaptive is False


def test_whisper_adaptive_env_on(monkeypatch):
    monkeypatch.setenv("MEETING_WHISPER_ADAPTIVE", "true")
    assert load_config().whisper_adaptive is True


def test_whisper_adaptive_env_off(monkeypatch):
    monkeypatch.setenv("MEETING_WHISPER_ADAPTIVE", "no")
    assert load_config().whisper_adaptive is False
