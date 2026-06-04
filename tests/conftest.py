"""Shared pytest fixtures: an isolated config + vault per test."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from meeting_processor.config import load_config
from meeting_processor.web.app import create_app


@pytest.fixture
def config(tmp_path: Path):
    """A Settings object pointed at a throwaway vault/project dir.

    Settings.vault_path is a computed property: Path(project_root) / vault_dir.
    We set project_root = tmp_path and vault_dir = "vault" so that
    config.vault_path == tmp_path / "vault".
    """
    cfg = load_config()
    # Settings is a plain (non-frozen) Pydantic BaseModel — direct assignment works.
    cfg.project_root = str(tmp_path)
    cfg.vault_dir = "vault"
    # Ensure the directories the app expects actually exist in the temp tree.
    (tmp_path / "vault" / "wiki" / "reunioes").mkdir(parents=True, exist_ok=True)
    return cfg


@pytest.fixture
def client(config):
    return TestClient(create_app(config))
