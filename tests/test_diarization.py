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


# --- Task 2: diarizer -------------------------------------------------------

from meeting_processor import diarizer


def test_assign_speakers_overlap_and_labels():
    segs = [
        TranscriptSegment(start=1, end=2, text="a"),
        TranscriptSegment(start=6, end=7, text="b"),
        TranscriptSegment(start=4.4, end=5.4, text="c"),  # 0.6 vs SP0, 0.4 vs SP1
        TranscriptSegment(start=20, end=21, text="d"),    # no overlap
    ]
    turns = [(0.0, 5.0, "SPEAKER_00"), (5.0, 10.0, "SPEAKER_01")]
    diarizer.assign_speakers(segs, turns)
    assert [s.speaker for s in segs] == ["Falante 1", "Falante 2", "Falante 1", None]


def test_assign_speakers_empty_turns_noop():
    segs = [TranscriptSegment(start=0, end=1, text="a")]
    diarizer.assign_speakers(segs, [])
    assert segs[0].speaker is None


def test_diarize_graceful_when_pyannote_missing(config, monkeypatch):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name.startswith("pyannote"):
            raise ImportError("no pyannote here")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert diarizer.diarize("/tmp/does-not-matter.wav", config) == []
