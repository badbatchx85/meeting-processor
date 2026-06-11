"""Generate a summary from an existing transcription (no re-transcription)."""
from datetime import datetime

import pytest

from meeting_processor.models import (
    ActionItem,
    MeetingSummary,
    Transcript,
    TranscriptSegment,
)
from meeting_processor.note_generator import NoteGenerator
from meeting_processor.utils import parse_timestamp


def test_parse_timestamp_handles_mm_ss():
    assert parse_timestamp("05:03") == 303.0
    assert parse_timestamp("01:02:03") == 3723.0  # 3-part unchanged


def _write_transcript(config):
    """Write a meeting folder with only a transcription, return its id."""
    transcript = Transcript(
        segments=[
            TranscriptSegment(start=0.0, end=5.0, text="Olá, vamos começar."),
            TranscriptSegment(start=5.0, end=12.0, text="João atualiza o Alpha."),
        ],
        full_text="Olá, vamos começar. João atualiza o Alpha.",
        language="pt",
        duration=12.0,
    )
    gen = NoteGenerator(config)
    paths = gen.prepare("reuniao.mp4", datetime(2026, 6, 4, 10, 0))
    gen.write_transcription(transcript, paths)
    gen.write_group_note(paths, has_summary=False)
    return paths.meeting_dir.name


def test_read_transcription_round_trips(config):
    mid = _write_transcript(config)
    path = next((config.reunioes_path / mid).glob("Transcricao - *.md"))
    gen = NoteGenerator(config)
    t = gen.read_transcription(path)
    assert len(t.segments) == 2
    assert t.segments[0].text == "Olá, vamos começar."
    assert t.duration > 0


def _canned_summary() -> MeetingSummary:
    return MeetingSummary(
        executive_summary="Resumo do Alpha.",
        time_windows=[],
        action_items=[ActionItem(description="Atualizar o Alpha", assignee="João")],
        participants=["João"],
        key_topics=["Alpha"],
        purpose="Acompanhar o projeto Alpha",
        meeting_type="status",
        decisions=["Seguir com o Alpha"],
        open_questions=[],
    )


def test_summarize_existing_writes_resumo(config, monkeypatch):
    mid = _write_transcript(config)

    class _FakeSummarizer:
        def __init__(self, *a, **k): ...
        def summarize(self, transcript, source_filename, style=None):
            return _canned_summary()

    monkeypatch.setattr(
        "meeting_processor.pipeline.MeetingSummarizer",
        lambda cfg: _FakeSummarizer(),
    )

    from meeting_processor.pipeline import MeetingPipeline

    MeetingPipeline(config).summarize_existing(mid)

    resumos = list((config.reunioes_path / mid).glob("Resumo - *.md"))
    assert resumos, "Resumo note should have been written"
    text = resumos[0].read_text(encoding="utf-8")
    assert "Acompanhar o projeto Alpha" in text  # purpose in the note


def test_summarize_existing_missing_raises(config):
    from meeting_processor.pipeline import MeetingPipeline

    with pytest.raises(FileNotFoundError):
        MeetingPipeline(config).summarize_existing("nao-existe")


def test_summarize_endpoint_queues(client, config, monkeypatch):
    mid = _write_transcript(config)
    called = {"id": None}

    def _fake_summarize(self, meeting_id):
        called["id"] = meeting_id

    monkeypatch.setattr(
        "meeting_processor.pipeline.MeetingPipeline.summarize_existing",
        _fake_summarize,
    )
    r = client.post(f"/api/meetings/{mid}/summarize")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["queued"] is True


def test_summarize_endpoint_404_for_missing(client):
    r = client.post("/api/meetings/nao-existe/summarize")
    assert r.status_code == 404
