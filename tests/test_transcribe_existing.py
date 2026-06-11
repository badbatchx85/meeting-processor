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


def test_transcribe_existing_overwrites_and_logs(config, tmp_path, monkeypatch):
    from meeting_processor import generation_log
    from meeting_processor.pipeline import MeetingPipeline

    config.watch_dir = str(tmp_path / "watch")
    mid = _make_meeting(config, "reuniao.mp4")
    (tmp_path / "uploads").mkdir()
    (tmp_path / "uploads" / "reuniao.mp4").write_bytes(b"fake")

    # Avoid touching ffmpeg/whisper: stub audio extraction + transcriber.
    monkeypatch.setattr(
        "meeting_processor.pipeline.extract_audio",
        lambda src, cfg: tmp_path / "audio.wav",
    )
    (tmp_path / "audio.wav").write_bytes(b"x")
    new_transcript = Transcript(
        segments=[
            TranscriptSegment(start=0.0, end=3.0, text="Texto novo um."),
            TranscriptSegment(start=3.0, end=6.0, text="Texto novo dois."),
        ],
        full_text="Texto novo um. Texto novo dois.",
        language="pt",
        duration=6.0,
    )

    class _FakeTranscriber:
        def __init__(self, *a, **k): ...
        def transcribe(self, audio_path, progress_callback=None, **kwargs):
            return new_transcript

    monkeypatch.setattr("meeting_processor.pipeline.WhisperTranscriber", lambda cfg: _FakeTranscriber())

    MeetingPipeline(config).transcribe_existing(mid)

    raw = next((config.reunioes_path / mid).glob("Transcricao - *.md")).read_text(encoding="utf-8")
    assert "Texto novo um." in raw
    entries = generation_log.read(config.reunioes_path / mid)
    assert entries and entries[0]["action"] == "transcript" and entries[0]["status"] == "ok"


def test_transcribe_existing_no_source_logs_error(config, tmp_path):
    from meeting_processor import generation_log
    from meeting_processor.pipeline import MeetingPipeline

    config.watch_dir = str(tmp_path / "watch")
    mid = _make_meeting(config, "reuniao.mp4")  # no media file on disk
    MeetingPipeline(config).transcribe_existing(mid)
    entries = generation_log.read(config.reunioes_path / mid)
    assert entries and entries[0]["action"] == "transcript" and entries[0]["status"] == "error"
    assert "não encontrado" in entries[0]["error"]


def test_summarize_existing_appends_log(config, tmp_path, monkeypatch):
    from meeting_processor import generation_log
    from meeting_processor.models import ActionItem, MeetingSummary
    from meeting_processor.pipeline import MeetingPipeline

    mid = _make_meeting(config, "reuniao.mp4")

    class _FakeSummarizer:
        def __init__(self, *a, **k): ...
        def summarize(self, transcript, source_filename, style=None):
            return MeetingSummary(
                executive_summary="ok", time_windows=[],
                action_items=[ActionItem(description="x", assignee="y")],
                participants=["y"], key_topics=["k"], purpose="p",
                meeting_type="status", decisions=[], open_questions=[],
            )

    monkeypatch.setattr("meeting_processor.pipeline.MeetingSummarizer", lambda cfg: _FakeSummarizer())
    MeetingPipeline(config).summarize_existing(mid)

    entries = generation_log.read(config.reunioes_path / mid)
    assert entries and entries[0]["action"] == "summary" and entries[0]["status"] == "ok"
