"""Set provider API keys from the front-end (write-only, never echoed)."""
from meeting_processor.web.runtime import set_llm_key


def test_set_llm_key_updates_field(config):
    r = set_llm_key(config, "openai", "sk-test-123")
    assert r["ok"] is True
    assert config.openai_api_key == "sk-test-123"
    assert "key" not in r  # never echoes the secret


def test_set_llm_key_rejects_keyless_and_empty(config):
    assert set_llm_key(config, "local", "x")["ok"] is False
    assert set_llm_key(config, "none", "x")["ok"] is False
    assert set_llm_key(config, "bogus", "x")["ok"] is False
    assert set_llm_key(config, "openai", "")["ok"] is False


def test_api_llm_exposes_key_set_booleans_not_values(client, config):
    config.openai_api_key = "sk-secret-xyz"
    body = client.get("/api/llm").json()
    assert "openai_key_set" in body and "gemini_key_set" in body
    assert body["openai_key_set"] is True
    assert "sk-secret-xyz" not in client.get("/api/llm").text  # value never leaks


def test_api_set_key_valid(client):
    r = client.post("/api/llm/key", json={"provider": "gemini", "key": "AIza-secret"})
    assert r.status_code == 200
    assert "AIza-secret" not in r.text          # response never echoes the key
    assert r.json()["llm"]["gemini_key_set"] is True


def test_api_set_key_invalid_provider_400(client):
    r = client.post("/api/llm/key", json={"provider": "local", "key": "x"})
    assert r.status_code == 400
    assert r.json()["ok"] is False
