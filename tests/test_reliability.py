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
