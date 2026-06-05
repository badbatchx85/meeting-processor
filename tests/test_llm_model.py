"""Set the per-provider LLM model from the front-end."""
from meeting_processor.web.runtime import set_llm_model


def test_set_llm_model_updates_field(config):
    r = set_llm_model(config, "gemini", "gemini-1.5-pro")
    assert r["ok"] is True
    assert config.gemini_model == "gemini-1.5-pro"


def test_set_llm_model_normalizes_ollama(config):
    r = set_llm_model(config, "ollama", "llama3.1:8b")
    assert r["ok"] is True
    assert config.ollama_model == "llama3.1:8b"


def test_set_llm_model_rejects_none_and_empty(config):
    assert set_llm_model(config, "none", "x")["ok"] is False
    assert set_llm_model(config, "gemini", "")["ok"] is False
    assert set_llm_model(config, "bogus", "x")["ok"] is False


def test_api_llm_includes_all_models(client):
    body = client.get("/api/llm").json()
    for key in ("anthropic_model", "openai_model", "gemini_model", "ollama_model"):
        assert key in body


def test_api_set_model_valid(client):
    r = client.post("/api/llm/model", json={"provider": "openai", "model": "gpt-4o-mini"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["llm"]["openai_model"] == "gpt-4o-mini"


def test_api_set_model_invalid_provider_400(client):
    r = client.post("/api/llm/model", json={"provider": "none", "model": "x"})
    assert r.status_code == 400
    assert r.json()["ok"] is False
