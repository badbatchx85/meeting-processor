"""Repositório de vozes conhecidas + matching (sub-projeto B)."""
import json

from meeting_processor import voiceprints as vp


def test_cosine_distance():
    assert vp._cosine_distance([1, 0], [1, 0]) == 0.0
    assert abs(vp._cosine_distance([1, 0], [0, 1]) - 1.0) < 1e-9
    assert vp._cosine_distance([0, 0], [1, 0]) == 1.0


def test_enroll_running_mean():
    repo = {}
    vp.enroll(repo, "Ana", [2.0, 0.0])
    vp.enroll(repo, "Ana", [0.0, 2.0])
    assert repo["Ana"]["count"] == 2
    assert repo["Ana"]["vector"] == [1.0, 1.0]


def test_match_threshold():
    repo = {"Ana": {"vector": [1.0, 0.0], "count": 1}}
    assert vp.match(repo, [0.99, 0.01], 0.45) == "Ana"
    assert vp.match(repo, [0.0, 1.0], 0.45) is None


def test_repo_roundtrip(config):
    repo = {"Ana": {"vector": [1.0, 2.0], "count": 1}}
    vp.save_repo(config.vault_path, repo)
    assert vp.load_repo(config.vault_path) == repo


def test_meeting_embeddings_roundtrip_and_suggest(config):
    d = config.reunioes_path / "m1"
    d.mkdir(parents=True, exist_ok=True)
    raw_md = d / "Transcricao - m1.md"
    vp.write_embeddings(raw_md, {"Falante 1": [1.0, 0.0], "Falante 2": [0.0, 1.0]})
    assert vp.read_meeting_embeddings(d) == {"Falante 1": [1.0, 0.0], "Falante 2": [0.0, 1.0]}
    vp.save_repo(config.vault_path, {"Ana": {"vector": [1.0, 0.0], "count": 1}})
    assert vp.suggest(d, config.vault_path, 0.45) == {"Falante 1": "Ana"}


def test_write_embeddings_noop_when_empty(config):
    d = config.reunioes_path / "m2"
    d.mkdir(parents=True, exist_ok=True)
    vp.write_embeddings(d / "Transcricao - m2.md", {})
    assert vp.read_meeting_embeddings(d) == {}


def test_voice_id_threshold_default_and_env(config, monkeypatch, tmp_path):
    assert config.voice_id_threshold == 0.45
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MEETING_VOICE_ID_THRESHOLD", "0.3")
    from meeting_processor.config import load_config
    assert load_config().voice_id_threshold == 0.3


# --- Task 4: endpoints -----------------------------------------------------


def _seed(config, folder, emb):
    d = config.reunioes_path / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / f"Transcricao - {folder}.md").write_text("# Transcricao\n", encoding="utf-8")
    (d / f"Transcricao - {folder}.words.json").write_text(
        json.dumps([{"start": 0, "end": 1, "text": "oi", "speaker": "Falante 1", "words": None}]),
        encoding="utf-8")
    (d / f"Transcricao - {folder}.embeddings.json").write_text(json.dumps(emb), encoding="utf-8")
    return d


def test_get_speakers_includes_suggestions(client, config):
    mid = "2026-02-01 10h00 - reu"
    _seed(config, mid, {"Falante 1": [1.0, 0.0]})
    vp.save_repo(config.vault_path, {"Ana": {"vector": [1.0, 0.0], "count": 1}})
    body = client.get(f"/api/meetings/{mid}/speakers").json()
    assert body["suggestions"] == {"Falante 1": "Ana"}


def test_post_speakers_enrolls_voiceprint(client, config):
    mid = "2026-02-02 10h00 - reu"
    _seed(config, mid, {"Falante 1": [0.0, 1.0]})
    client.post(f"/api/meetings/{mid}/speakers", json={"names": {"Falante 1": "Bruno"}})
    repo = vp.load_repo(config.vault_path)
    assert "Bruno" in repo and repo["Bruno"]["vector"] == [0.0, 1.0]
