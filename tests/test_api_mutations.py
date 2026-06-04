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
