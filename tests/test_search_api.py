"""Endpoints da busca semântica: /api/search e /api/search/reindex.

O ``embed`` do Ollama é sempre mockado — sem servidor real nos testes.
"""
import json

from meeting_processor import search_index as si


def _seed_meeting(config, folder, segments):
    d = config.reunioes_path / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / f"Transcricao - {folder}.md").write_text("# Transcricao\n", encoding="utf-8")
    (d / f"Transcricao - {folder}.words.json").write_text(
        json.dumps(segments), encoding="utf-8")
    return d


# --- /api/search ------------------------------------------------------------


def test_search_returns_ordered_results(client, config, monkeypatch):
    si.add_meeting(config.vault_path, "m1", [
        {"text": "perto", "start": 0.0, "end": 1.0, "vector": [1.0, 0.0]},
        {"text": "longe", "start": 1.0, "end": 2.0, "vector": [0.0, 1.0]},
    ])
    monkeypatch.setattr("meeting_processor.web.app.ollama_service.embed",
                        lambda q, cfg: [1.0, 0.0])
    body = client.post("/api/search", json={"q": "tema", "k": 10}).json()
    assert [r["meeting_id"] for r in body["results"]] == ["m1", "m1"]
    assert body["results"][0]["text"] == "perto"
    assert "vector" not in body["results"][0]


def test_search_ollama_off_returns_503(client, config, monkeypatch):
    from meeting_processor.ollama_service import EmbeddingError

    def _boom(q, cfg):
        raise EmbeddingError("off")

    monkeypatch.setattr("meeting_processor.web.app.ollama_service.embed", _boom)
    resp = client.post("/api/search", json={"q": "tema"})
    assert resp.status_code == 503


def test_search_empty_query_returns_empty(client, config, monkeypatch):
    monkeypatch.setattr("meeting_processor.web.app.ollama_service.embed",
                        lambda q, cfg: [1.0, 0.0])
    body = client.post("/api/search", json={"q": "   "}).json()
    assert body["results"] == []


# --- /api/search/reindex ----------------------------------------------------


def test_reindex_indexes_all_meetings(client, config, monkeypatch):
    _seed_meeting(config, "m1", [{"start": 0.0, "end": 1.0, "text": "alpha"}])
    _seed_meeting(config, "m2", [{"start": 0.0, "end": 1.0, "text": "beta"}])
    monkeypatch.setattr("meeting_processor.web.app.ollama_service.embed",
                        lambda text, cfg: [float(len(text)), 0.0])
    body = client.post("/api/search/reindex").json()
    assert body["ok"] is True
    rows = si.load_index(config.vault_path)
    assert {r["meeting_id"] for r in rows} == {"m1", "m2"}
    assert body["indexed"] == 2


def test_delete_meeting_prunes_search_index(client, config):
    _seed_meeting(config, "m1", [{"start": 0.0, "end": 1.0, "text": "alpha"}])
    si.add_meeting(config.vault_path, "m1", [
        {"text": "alpha", "start": 0.0, "end": 1.0, "vector": [1.0, 0.0]},
    ])
    si.add_meeting(config.vault_path, "m2", [
        {"text": "beta", "start": 0.0, "end": 1.0, "vector": [0.0, 1.0]},
    ])
    client.delete("/api/meetings/m1")
    rows = si.load_index(config.vault_path)
    assert [r["meeting_id"] for r in rows] == ["m2"]


def test_reindex_ollama_off_returns_503(client, config, monkeypatch):
    _seed_meeting(config, "m1", [{"start": 0.0, "end": 1.0, "text": "alpha"}])
    from meeting_processor.ollama_service import EmbeddingError

    def _boom(text, cfg):
        raise EmbeddingError("off")

    monkeypatch.setattr("meeting_processor.web.app.ollama_service.embed", _boom)
    resp = client.post("/api/search/reindex")
    assert resp.status_code == 503
