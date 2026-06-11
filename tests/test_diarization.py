"""Diarização de falantes (quem falou)."""
from meeting_processor.models import TranscriptSegment


def test_segment_display_text():
    assert TranscriptSegment(start=0, end=1, text="oi").display_text == "oi"
    seg = TranscriptSegment(start=0, end=1, text="oi", speaker="Falante 1")
    assert seg.display_text == "Falante 1: oi"


def test_diarization_config_defaults(config):
    assert config.enable_diarization is False
    assert config.hf_token == ""
    assert config.diarization_model == "pyannote/speaker-diarization-3.1"


def test_diarization_env_overrides(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MEETING_ENABLE_DIARIZATION", "true")
    monkeypatch.setenv("MEETING_HF_TOKEN", "hf_abc")
    from meeting_processor.config import load_config
    cfg = load_config()
    assert cfg.enable_diarization is True
    assert cfg.hf_token == "hf_abc"
