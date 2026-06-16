"""faster-whisper backend + word timestamps."""
from meeting_processor.models import TranscriptSegment, WordTime


def test_segment_words_default_none():
    s = TranscriptSegment(start=0, end=1, text="oi")
    assert s.words is None


def test_segment_with_words():
    w = WordTime(start=0.0, end=0.5, text="oi")
    s = TranscriptSegment(start=0, end=1, text="oi", words=[w])
    assert s.words[0].text == "oi" and s.words[0].end == 0.5


# --- Task 2: faster-whisper backend ----------------------------------------

import sys
import types

from meeting_processor.transcriber import WhisperTranscriber, _faster_model_name


class _FakeWord:
    def __init__(self, start, end, word):
        self.start, self.end, self.word = start, end, word


class _FakeSeg:
    def __init__(self, start, end, text, words=None):
        self.start, self.end, self.text, self.words = start, end, text, words


def _install_fake_faster(monkeypatch, segs, duration):
    mod = types.ModuleType("faster_whisper")

    class FakeModel:
        def __init__(self, *a, **k):
            pass

        def transcribe(self, *a, **k):
            info = types.SimpleNamespace(duration=duration)
            return iter(segs), info

    mod.WhisperModel = FakeModel
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)


def test_faster_model_name():
    assert _faster_model_name("large") == "large-v3"
    assert _faster_model_name("medium") == "medium"
    assert _faster_model_name("large-v3") == "large-v3"


def test_transcribe_faster_builds_transcript_with_words(config, monkeypatch):
    segs = [
        _FakeSeg(0.0, 1.0, " oi", [_FakeWord(0.0, 0.5, " oi")]),
        _FakeSeg(1.0, 2.0, " tchau", [_FakeWord(1.0, 1.8, " tchau")]),
    ]
    _install_fake_faster(monkeypatch, segs, duration=2.0)
    t = WhisperTranscriber(config)._transcribe_faster("/tmp/x.wav", None, "large")
    assert [s.text for s in t.segments] == ["oi", "tchau"]
    assert t.duration == 2.0
    assert t.full_text == "oi tchau"
    assert t.segments[0].words[0].text == "oi"


def test_transcribe_faster_falls_back_when_not_installed(config, monkeypatch):
    monkeypatch.setitem(sys.modules, "faster_whisper", None)  # import → ImportError
    called = {}
    monkeypatch.setattr(
        WhisperTranscriber, "_transcribe_openai",
        lambda self, a, p, m: called.setdefault("openai", True),
    )
    WhisperTranscriber(config)._transcribe_faster("/tmp/x.wav", None, "large")
    assert called.get("openai") is True


def test_dispatch_routes_to_faster(config, monkeypatch):
    config.whisper_backend = "faster"
    monkeypatch.setattr(
        WhisperTranscriber, "_transcribe_faster",
        lambda self, a, p, m: "FASTER",
    )
    assert WhisperTranscriber(config).transcribe("/tmp/x.wav") == "FASTER"


def test_compute_type_and_backend_defaults(config):
    assert config.whisper_compute_type == "int8"
    assert config.whisper_backend == "faster"
