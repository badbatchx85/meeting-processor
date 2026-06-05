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


def test_pull_rejects_empty(client):
    r = client.post("/api/llm/local-models/pull", json={"model": ""})
    assert r.status_code == 400


def test_pull_queues(client, monkeypatch):
    monkeypatch.setattr(appmod, "_ollama_pull", lambda base, model: None)
    r = client.post("/api/llm/local-models/pull", json={"model": "llama3.1:8b"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["queued"] is True and body["model"] == "llama3.1:8b"
