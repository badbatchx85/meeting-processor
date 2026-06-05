"""Re-transcription of an existing meeting + source-file location."""
from datetime import datetime

from meeting_processor.models import Transcript, TranscriptSegment
from meeting_processor.note_generator import NoteGenerator
from meeting_processor.pipeline import locate_source_file


def _make_meeting(config, source_name="reuniao.mp4"):
    """Create a transcript-only meeting folder, return its id (folder name)."""
    transcript = Transcript(
        segments=[TranscriptSegment(start=0.0, end=5.0, text="Oi.")],
        full_text="Oi.",
        language="pt",
        duration=5.0,
    )
    gen = NoteGenerator(config)
    paths = gen.prepare(source_name, datetime(2026, 6, 4, 10, 0))
    gen.write_transcription(transcript, paths)
    gen.write_group_note(paths, has_summary=False)
    return paths.meeting_dir.name


def test_locate_source_in_uploads(config, tmp_path):
    config.watch_dir = str(tmp_path / "watch")  # isolate from real ~/Videos/OBS
    mid = _make_meeting(config, "reuniao.mp4")
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    media = uploads / "reuniao.mp4"
    media.write_bytes(b"fake")
    found = locate_source_file(config, config.reunioes_path / mid)
    assert found == media


def test_locate_source_missing_returns_none(config, tmp_path):
    config.watch_dir = str(tmp_path / "watch")
    mid = _make_meeting(config, "reuniao.mp4")
    assert locate_source_file(config, config.reunioes_path / mid) is None
