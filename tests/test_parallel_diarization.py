"""Diarização rodando em paralelo com a transcrição."""
from meeting_processor import diarizer
from meeting_processor.models import Transcript, TranscriptSegment
from meeting_processor.pipeline import MeetingPipeline


def _t():
    s = TranscriptSegment(start=0, end=1, text="oi")
    return Transcript(segments=[s], full_text="oi", language="pt", duration=1)


def test_diarization_disabled_noop(config):
    config.enable_diarization = False
    pipe = MeetingPipeline(config)
    h = pipe._start_diarization("/tmp/x.wav")
    assert h is None
    t = _t()
    pipe._finish_diarization(h, t)
    assert t.segments[0].speaker is None


def test_diarization_enabled_assigns(config, monkeypatch):
    config.enable_diarization = True
    monkeypatch.setattr(diarizer, "diarize", lambda audio, cfg: [(0.0, 1.0, "SPEAKER_00")])
    pipe = MeetingPipeline(config)
    h = pipe._start_diarization("/tmp/x.wav")
    t = _t()
    pipe._finish_diarization(h, t)
    assert t.segments[0].speaker == "Falante 1"


def test_diarization_failure_is_swallowed(config, monkeypatch):
    config.enable_diarization = True
    def boom(audio, cfg):
        raise RuntimeError("kaboom")
    monkeypatch.setattr(diarizer, "diarize", boom)
    pipe = MeetingPipeline(config)
    h = pipe._start_diarization("/tmp/x.wav")
    t = _t()
    pipe._finish_diarization(h, t)   # must not raise
    assert t.segments[0].speaker is None
