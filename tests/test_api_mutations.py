"""Tests for the JSON mutation endpoints used by the SPA."""
from pathlib import Path


def test_watcher_start_stop_returns_json(client):
    r = client.post("/api/watcher/start")
    assert r.status_code == 200
    body = r.json()
    assert "ok" in body and "watcher" in body
    assert set(body["watcher"]) >= {"running", "pid", "started_at", "exit_code"}

    r2 = client.post("/api/watcher/stop")
    assert r2.status_code == 200
    assert r2.json()["watcher"]["running"] is False


def test_watcher_restart_returns_json(client):
    r = client.post("/api/watcher/restart")
    assert r.status_code == 200
    assert "watcher" in r.json()


def test_set_llm_provider_valid(client):
    r = client.post("/api/llm/provider", json={"provider": "none"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["llm"]["provider"] == "none"


def test_set_llm_provider_invalid_returns_400(client):
    r = client.post("/api/llm/provider", json={"provider": "bogus"})
    assert r.status_code == 400
    assert r.json()["ok"] is False


def test_set_steps_persists(client):
    r = client.post(
        "/api/config/steps",
        json={"summary": True, "note": False, "kanban": True, "wiki": False},
    )
    assert r.status_code == 200
    steps = r.json()["steps"]
    assert steps == {"summary": True, "note": False, "kanban": True, "wiki": False}


def test_set_watch_dir_returns_paths(client, tmp_path):
    target = tmp_path / "videos"
    target.mkdir()
    r = client.post("/api/config/watch-dir", json={"watch_dir": str(target)})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["exists"] is True


def test_process_missing_file_returns_400(client):
    r = client.post("/api/process", json={"file": "/no/such/file.mp4"})
    assert r.status_code == 400
    assert r.json()["ok"] is False


def test_process_existing_file_queues(client, tmp_path, monkeypatch):
    # Stop the real pipeline from running; just assert it gets queued.
    class _FakePipeline:
        def __init__(self, *a, **k): ...
        def process(self, path): ...

    monkeypatch.setattr("meeting_processor.pipeline.MeetingPipeline", _FakePipeline, raising=False)

    f = tmp_path / "clip.mp4"
    f.write_bytes(b"x")
    r = client.post("/api/process", json={"file": str(f)})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["queued"] is True


def test_process_rejects_unsupported_extension(client, tmp_path):
    f = tmp_path / "notes.txt"
    f.write_text("hi")
    r = client.post("/api/process", json={"file": str(f)})
    assert r.status_code == 400
    assert r.json()["ok"] is False


def test_upload_rejects_unsupported_extension(client):
    r = client.post(
        "/api/process/upload",
        files={"file": ("notas.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 400
    assert r.json()["ok"] is False


def test_upload_accepts_media_saves_and_queues(client, config, monkeypatch):
    started = {"path": None}

    class _FakePipeline:
        def __init__(self, *a, **k): ...
        def process(self, path):
            started["path"] = path

    monkeypatch.setattr(
        "meeting_processor.pipeline.MeetingPipeline", _FakePipeline, raising=False
    )

    r = client.post(
        "/api/process/upload",
        files={"file": ("reuniao.mp4", b"\x00\x01\x02", "video/mp4")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["queued"] is True
    assert body["file"] == "reuniao.mp4"
    # arquivo realmente gravado em uploads/
    saved = Path(config.project_root) / "uploads" / "reuniao.mp4"
    assert saved.exists() and saved.read_bytes() == b"\x00\x01\x02"


def test_status_reports_active_job_progress(client, config):
    import json

    history = config.vault_path / "wiki" / ".processing-history.json"
    history.write_text(
        json.dumps([
            {
                "file": "reuniao.mp4",
                "status": "processing",
                "started": "2026-06-03T20:00:00",
                "completed": None,
                "details": {"transcription": "120 segmentos"},
                "stage": 1,  # transcription (0-based)
                "stage_progress": {"transcription": 50},
            }
        ]),
        encoding="utf-8",
    )

    r = client.get("/api/status")
    assert r.status_code == 200
    body = r.json()
    assert len(body["active"]) == 1
    job = body["active"][0]
    assert job["file"] == "reuniao.mp4"
    assert job["stage_number"] == 2 and job["stage_total"] == 6
    assert "Transcre" in job["stage_label"]
    assert job["stage_percent"] == 50
    # overall = (1 + 0.5) / 6 = 25%
    assert job["percent"] == 25
    assert job["detail"] == "120 segmentos"


def test_status_empty_when_no_active_jobs(client):
    r = client.get("/api/status")
    assert r.status_code == 200
    assert r.json()["active"] == []
