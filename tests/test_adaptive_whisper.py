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


# --- Task 2: função de seleção ---------------------------------------------

from meeting_processor.transcriber import select_whisper_model


def test_select_tiers():
    assert select_whisper_model(1199, "x") == "large"   # < 20 min
    assert select_whisper_model(1200, "x") == "large"   # == 20 min (inclusive)
    assert select_whisper_model(1201, "x") == "medium"  # > 20 min
    assert select_whisper_model(2700, "x") == "medium"  # == 45 min (inclusive)
    assert select_whisper_model(2701, "x") == "small"   # > 45 min
    assert select_whisper_model(5000, "x") == "small"


def test_select_unknown_duration_keeps_configured():
    assert select_whisper_model(0, "large") == "large"
    assert select_whisper_model(-5, "medium") == "medium"


# --- Task 3: override de modelo no transcribe ------------------------------


def test_transcribe_uses_model_override(config, monkeypatch):
    import whisper
    from meeting_processor.transcriber import WhisperTranscriber

    calls = []

    class FakeModel:
        def transcribe(self, path, language=None, initial_prompt=None):
            return {"segments": [{"start": 0.0, "end": 1.0, "text": "oi"}], "text": "oi"}

    monkeypatch.setattr(whisper, "load_model", lambda name: (calls.append(name), FakeModel())[1])

    config.whisper_backend = "openai"   # força o backend Python (sem whisper.cpp)
    config.whisper_model = "large"
    tr = WhisperTranscriber(config)

    tr.transcribe(Path("/tmp/does-not-exist.wav"), model="medium")
    assert calls[-1] == "medium"        # override usado

    tr.transcribe(Path("/tmp/does-not-exist.wav"))
    assert calls[-1] == "large"         # sem override => config.whisper_model
