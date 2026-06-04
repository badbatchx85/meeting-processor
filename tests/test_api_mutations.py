"""Tests for the JSON mutation endpoints used by the SPA."""


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
