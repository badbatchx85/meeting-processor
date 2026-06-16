"""Renomeação de falantes (sub-projeto A)."""
from datetime import datetime

from meeting_processor.models import Transcript, TranscriptSegment
from meeting_processor.note_generator import NoteGenerator


def test_sidecar_written_for_diarized_without_words(config):
    ng = NoteGenerator(config)
    paths = ng.prepare("reu.mp4", datetime(2026, 1, 1, 10, 0, 0))
    seg = TranscriptSegment(start=0, end=1, text="oi", speaker="Falante 1")  # words=None
    ng.write_transcription(Transcript(segments=[seg], full_text="oi", language="pt", duration=1), paths)
    assert paths.raw_path.with_suffix(".words.json").exists()
