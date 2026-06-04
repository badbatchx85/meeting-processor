"""Tests for SPA serving at /ui with graceful fallback to the HTMX UI."""


def test_root_redirects_to_dashboard_when_build_absent(client):
    # No SPA build exists in the test tree, so / keeps legacy behavior.
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/dashboard"


def test_ui_returns_hint_when_build_absent(client):
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
