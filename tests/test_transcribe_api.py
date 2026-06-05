"""API for re-transcribe, generation log, and source-file management."""
from datetime import datetime

from meeting_processor.models import Transcript, TranscriptSegment
from meeting_processor.note_generator import NoteGenerator


def _make_meeting(config, source_name="reuniao.mp4"):
    transcript = Transcript(
        segments=[TranscriptSegment(start=0.0, end=5.0, text="Oi.")],
        full_text="Oi.", language="pt", duration=5.0,
    )
    gen = NoteGenerator(config)
    paths = gen.prepare(source_name, datetime(2026, 6, 4, 10, 0))
    gen.write_transcription(transcript, paths)
    gen.write_group_note(paths, has_summary=False)
    return paths.meeting_dir.name


def test_transcribe_endpoint_queues(client, config, monkeypatch):
    mid = _make_meeting(config)
    called = {"id": None}
    monkeypatch.setattr(
        "meeting_processor.pipeline.MeetingPipeline.transcribe_existing",
        lambda self, meeting_id: called.__setitem__("id", meeting_id),
    )
    r = client.post(f"/api/meetings/{mid}/transcribe")
    assert r.status_code == 200 and r.json()["queued"] is True


def test_transcribe_endpoint_404(client):
    assert client.post("/api/meetings/nao-existe/transcribe").status_code == 404


def test_log_endpoint_returns_entries(client, config):
    from meeting_processor import generation_log
    mid = _make_meeting(config)
    t = datetime(2026, 6, 5, 10, 0, 0)
    generation_log.append(config.reunioes_path / mid, "transcript", "ok", detail="d", started=t, completed=t)
    r = client.get(f"/api/meetings/{mid}/log")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1 and body[0]["action"] == "transcript"


def test_source_endpoint_reports_existence(client, config, tmp_path):
    config.watch_dir = str(tmp_path / "watch")
    mid = _make_meeting(config, "reuniao.mp4")
    r = client.get(f"/api/meetings/{mid}/source")
    assert r.status_code == 200 and r.json()["exists"] is False
    (tmp_path / "uploads").mkdir()
    (tmp_path / "uploads" / "reuniao.mp4").write_bytes(b"1234")
    r = client.get(f"/api/meetings/{mid}/source")
    assert r.json() == {"exists": True, "name": "reuniao.mp4",
                        "path": str(tmp_path / "uploads" / "reuniao.mp4"), "size": 4}


def test_delete_source_removes_and_logs(client, config, tmp_path):
    from meeting_processor import generation_log
    config.watch_dir = str(tmp_path / "watch")
    mid = _make_meeting(config, "reuniao.mp4")
    (tmp_path / "uploads").mkdir()
    media = tmp_path / "uploads" / "reuniao.mp4"
    media.write_bytes(b"1234")
    r = client.delete(f"/api/meetings/{mid}/source")
    assert r.status_code == 200 and r.json()["deleted"] is True
    assert not media.exists()
    assert (config.reunioes_path / mid).is_dir()  # meeting kept
    entries = generation_log.read(config.reunioes_path / mid)
    assert entries[0]["action"] == "delete_source" and entries[0]["status"] == "ok"


def test_delete_source_missing_is_idempotent(client, config, tmp_path):
    config.watch_dir = str(tmp_path / "watch")
    mid = _make_meeting(config, "reuniao.mp4")
    r = client.delete(f"/api/meetings/{mid}/source")
    assert r.status_code == 200 and r.json()["deleted"] is False


def test_process_transcript_mode(client, config, tmp_path, monkeypatch):
    media = tmp_path / "reuniao.mp4"
    media.write_bytes(b"x")
    seen = {}
    monkeypatch.setattr(
        "meeting_processor.pipeline.MeetingPipeline.process",
        lambda self, path, transcript_only=False: seen.update(to=transcript_only),
    )
    r = client.post("/api/process", json={"file": str(media), "mode": "transcript"})
    assert r.status_code == 200 and r.json()["queued"] is True
    import time as _t
    for _ in range(50):
        if "to" in seen:
            break
        _t.sleep(0.02)
    assert seen.get("to") is True
