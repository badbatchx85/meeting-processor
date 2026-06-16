"""faster-whisper backend + word timestamps."""
from meeting_processor.models import TranscriptSegment, WordTime


def test_segment_words_default_none():
    s = TranscriptSegment(start=0, end=1, text="oi")
    assert s.words is None


def test_segment_with_words():
    w = WordTime(start=0.0, end=0.5, text="oi")
    s = TranscriptSegment(start=0, end=1, text="oi", words=[w])
    assert s.words[0].text == "oi" and s.words[0].end == 0.5
