"""Tests for SPA serving at /ui with graceful fallback to the HTMX UI."""
from pathlib import Path


def test_root_redirects_to_dashboard_when_build_absent(client, monkeypatch, tmp_path):
    # Monkeypatch spa_serving so the SPA appears absent regardless of build state.
    from meeting_processor.web import spa_serving

    absent_dir = tmp_path / "spa_absent"
    monkeypatch.setattr(spa_serving, "SPA_DIR", absent_dir)
    monkeypatch.setattr(spa_serving, "SPA_INDEX", absent_dir / "index.html")

    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/dashboard"


def test_ui_returns_hint_when_build_absent(client, monkeypatch, tmp_path):
    from meeting_processor.web import spa_serving

    absent_dir = tmp_path / "spa_absent"
    monkeypatch.setattr(spa_serving, "SPA_DIR", absent_dir)
    monkeypatch.setattr(spa_serving, "SPA_INDEX", absent_dir / "index.html")

    r = client.get("/ui", follow_redirects=False)
    assert r.status_code == 200
    assert "npm run build" in r.text


def test_root_redirects_to_ui_when_build_present(client, monkeypatch, tmp_path):
    from meeting_processor.web import spa_serving

    spa_dir = tmp_path / "spa"
    (spa_dir / "assets").mkdir(parents=True)
    (spa_dir / "index.html").write_text("<!doctype html><title>Meeting Processor</title>")
    monkeypatch.setattr(spa_serving, "SPA_DIR", spa_dir)
    monkeypatch.setattr(spa_serving, "SPA_INDEX", spa_dir / "index.html")

    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/ui"

    r2 = client.get("/ui/meetings", follow_redirects=False)
    assert r2.status_code == 200
    assert "Meeting Processor" in r2.text
