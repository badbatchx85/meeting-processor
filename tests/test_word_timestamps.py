"""Persistência de timestamps por palavra (sidecar .words.json)."""
import json

from meeting_processor.models import Transcript, TranscriptSegment, WordTime
from meeting_processor.note_generator import NoteGenerator


def _paths(config, ng):
    from datetime import datetime
    return ng.prepare("reuniao.mp4", datetime(2026, 1, 1, 10, 0, 0))


def test_sidecar_written_when_words_present(config):
    ng = NoteGenerator(config)
    paths = _paths(config, ng)
    seg = TranscriptSegment(start=0, end=1, text="oi", words=[WordTime(start=0, end=0.5, text="oi")])
    ng.write_transcription(Transcript(segments=[seg], full_text="oi", language="pt", duration=1), paths)
    sidecar = paths.raw_path.with_suffix(".words.json")
    assert sidecar.exists()
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert data[0]["text"] == "oi" and data[0]["words"][0]["text"] == "oi"


def test_no_sidecar_without_words(config):
    ng = NoteGenerator(config)
    paths = _paths(config, ng)
    seg = TranscriptSegment(start=0, end=1, text="oi")  # words=None
    ng.write_transcription(Transcript(segments=[seg], full_text="oi", language="pt", duration=1), paths)
    assert not paths.raw_path.with_suffix(".words.json").exists()
