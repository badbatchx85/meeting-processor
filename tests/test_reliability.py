"""Reliability bundle: atomic writes, job queue, cooperative cancel, disk preflight."""
import json
from pathlib import Path

import pytest

from meeting_processor.utils import write_json_atomic


def test_write_json_atomic_writes_and_roundtrips(tmp_path):
    p = tmp_path / "sub" / "data.json"
    write_json_atomic(p, [{"a": 1}, {"b": "ç"}])
    assert json.loads(p.read_text(encoding="utf-8")) == [{"a": 1}, {"b": "ç"}]
    assert not p.with_suffix(p.suffix + ".tmp").exists()   # tmp cleaned up


def test_write_json_atomic_failure_keeps_original(tmp_path, monkeypatch):
    p = tmp_path / "data.json"
    write_json_atomic(p, {"v": 1})                          # original good content
    import meeting_processor.utils as u
    monkeypatch.setattr(u.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("boom")))
    with pytest.raises(OSError):
        write_json_atomic(p, {"v": 2})
    assert json.loads(p.read_text(encoding="utf-8")) == {"v": 1}   # untouched


# --- Task 2: disk preflight ------------------------------------------------

import meeting_processor.pipeline as pipemod
from meeting_processor.pipeline import MeetingPipeline


def test_disk_preflight_fails_fast(config, monkeypatch, tmp_path):
    extract_called = []
    monkeypatch.setattr(pipemod, "extract_audio", lambda *a, **k: extract_called.append(1))

    class _DU:  # free < need
        free = 1
    monkeypatch.setattr(pipemod.shutil, "disk_usage", lambda p: _DU())

    video = tmp_path / "reuniao.mp4"
    video.write_bytes(b"x" * 1000)
    with pytest.raises(RuntimeError, match="Espaço em disco"):
        MeetingPipeline(config).process(video)
    assert extract_called == []   # never reached extraction

    entry = [e for e in json.loads((config.vault_path / "wiki" / ".processing-history.json").read_text()) if e["file"] == "reuniao.mp4"][-1]
    assert entry["status"] == "error"

# --- Task 3: identity plumbing ---------------------------------------------

from datetime import datetime
from meeting_processor.config import load_config
from meeting_processor.dashboard import Dashboard


def test_max_concurrent_jobs_default_and_env(monkeypatch):
    monkeypatch.delenv("MEETING_MAX_CONCURRENT_JOBS", raising=False)
    assert load_config().max_concurrent_jobs == 1
    monkeypatch.setenv("MEETING_MAX_CONCURRENT_JOBS", "3")
    assert load_config().max_concurrent_jobs == 3


def test_new_job_accepts_started_at(config):
    d = Dashboard(config)
    ts = datetime(2026, 6, 9, 10, 0, 0)
    job = d.new_job("x.mp4", started_at=ts)
    assert job.started_at == ts
