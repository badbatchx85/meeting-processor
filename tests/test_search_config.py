"""Config da busca semântica: defaults + overrides por env."""
from meeting_processor.config import load_config


def test_search_defaults(config):
    assert config.enable_search_index is False
    assert config.embedding_model == "nomic-embed-text"


def test_enable_search_index_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MEETING_ENABLE_SEARCH_INDEX", "true")
    assert load_config().enable_search_index is True


def test_embedding_model_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MEETING_EMBEDDING_MODEL", "mxbai-embed-large")
    assert load_config().embedding_model == "mxbai-embed-large"
