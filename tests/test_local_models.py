"""List installed Ollama models + trigger a download."""
import meeting_processor.web.app as appmod


def test_local_models_running(client, monkeypatch):
    monkeypatch.setattr(appmod, "_ollama_installed", lambda base: ["qwen2.5:7b"])
    body = client.get("/api/llm/local-models").json()
    assert body["ollama_running"] is True
    assert "qwen2.5:7b" in body["installed"]
    assert "qwen2.5:7b" not in body["suggested"]      # already installed
    assert "llama3.1:8b" in body["suggested"]


def test_local_models_not_running(client, monkeypatch):
    monkeypatch.setattr(appmod, "_ollama_installed", lambda base: None)
    body = client.get("/api/llm/local-models").json()
    assert body["ollama_running"] is False
    assert body["installed"] == []
    assert "qwen2.5:7b" in body["suggested"]


def test_local_models_installed_but_not_running(client, monkeypatch):
    """Ollama binário presente porém servidor parado: installed=True, running=False."""
    monkeypatch.setattr(appmod, "_ollama_installed", lambda base: None)
    monkeypatch.setattr(appmod, "_ollama_binary_present", lambda: True)
    body = client.get("/api/llm/local-models").json()
    assert body["ollama_running"] is False
    assert body["ollama_installed"] is True


def test_local_models_not_installed(client, monkeypatch):
    """Sem binário e sem servidor: o usuário precisa instalar."""
    monkeypatch.setattr(appmod, "_ollama_installed", lambda base: None)
    monkeypatch.setattr(appmod, "_ollama_binary_present", lambda: False)
    body = client.get("/api/llm/local-models").json()
    assert body["ollama_running"] is False
    assert body["ollama_installed"] is False


def test_local_models_running_implies_installed(client, monkeypatch):
    """Se está rodando, está instalado — sem precisar olhar o PATH."""
    monkeypatch.setattr(appmod, "_ollama_installed", lambda base: ["qwen2.5:7b"])
    monkeypatch.setattr(appmod, "_ollama_binary_present", lambda: False)
    body = client.get("/api/llm/local-models").json()
    assert body["ollama_running"] is True
    assert body["ollama_installed"] is True


def test_start_ollama_rejects_when_not_installed(client, monkeypatch):
    monkeypatch.setattr(appmod, "_ollama_binary_present", lambda: False)
    r = client.post("/api/llm/local-models/start")
    assert r.status_code == 400
    assert r.json()["ok"] is False


def test_start_ollama_invokes_ensure_running(client, monkeypatch):
    monkeypatch.setattr(appmod, "_ollama_binary_present", lambda: True)
    calls = {}
    monkeypatch.setattr(
        "meeting_processor.ollama_service.ensure_running",
        lambda cfg, *a, **k: calls.setdefault("called", True) or True,
    )
    r = client.post("/api/llm/local-models/start")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "running": True}
    assert calls.get("called") is True


def test_start_ollama_reports_failure_to_come_up(client, monkeypatch):
    monkeypatch.setattr(appmod, "_ollama_binary_present", lambda: True)
    monkeypatch.setattr(
        "meeting_processor.ollama_service.ensure_running", lambda cfg, *a, **k: False
    )
    r = client.post("/api/llm/local-models/start")
    assert r.status_code == 200
    assert r.json() == {"ok": False, "running": False}


def test_pull_rejects_empty(client):
    r = client.post("/api/llm/local-models/pull", json={"model": ""})
    assert r.status_code == 400


def test_pull_queues(client, monkeypatch):
    monkeypatch.setattr(appmod, "_ollama_pull", lambda base, model: None)
    r = client.post("/api/llm/local-models/pull", json={"model": "llama3.1:8b"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["queued"] is True and body["model"] == "llama3.1:8b"


def test_pull_status_endpoint_reflects_state(client):
    appmod._set_pull(model="qwen2.5:7b", percent=42, status="downloading", done=False, error=None)
    body = client.get("/api/llm/local-models/pull/status").json()
    assert body["model"] == "qwen2.5:7b"
    assert body["percent"] == 42
    assert body["done"] is False


def test_ollama_pull_tracks_progress(monkeypatch):
    import contextlib
    import json

    lines = [
        json.dumps({"status": "downloading", "total": 100, "completed": 50}),
        json.dumps({"status": "downloading", "total": 100, "completed": 100}),
        json.dumps({"status": "success"}),
    ]

    class _FakeResp:
        def iter_lines(self):
            yield from lines

    @contextlib.contextmanager
    def _fake_stream(method, url, **kw):
        yield _FakeResp()

    monkeypatch.setattr("httpx.stream", _fake_stream)
    appmod._ollama_pull("http://x", "qwen2.5:7b")
    assert appmod._PULL_STATE["done"] is True
    assert appmod._PULL_STATE["percent"] == 100
    assert appmod._PULL_STATE["model"] == "qwen2.5:7b"
