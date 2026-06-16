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
