"""Root pytest config.

Isolate the test suite from a developer's local ``.env``. ``load_config()``
calls ``load_dotenv(project_root/.env)``, which writes the file's keys into the
*process* ``os.environ`` permanently — so a single ``load_config()`` (e.g. from
``test_pipeline.py`` at the repo root) leaks local overrides like
``MEETING_WHISPER_BACKEND`` / ``MEETING_ENABLE_SEARCH_INDEX`` into every later
test and breaks the default-asserting ones.

This autouse fixture (root-level, so it covers every test dir) no-ops
``load_dotenv`` AND strips any already-present ``MEETING_*`` vars before each
test, so tests see only the committed ``config.yaml`` + ``Settings`` defaults.
Tests that need a var still set it via ``monkeypatch.setenv`` (which runs after
this fixture and so survives), and ``load_config`` reads ``os.environ`` directly.
"""
import os

import pytest


@pytest.fixture(autouse=True)
def _isolate_local_dotenv(monkeypatch):
    monkeypatch.setattr("meeting_processor.config.load_dotenv", lambda *a, **k: None)
    for key in list(os.environ):
        if key.startswith("MEETING_"):
            monkeypatch.delenv(key, raising=False)
