"""Per-meeting generation audit log."""
from datetime import datetime

from meeting_processor import generation_log


def test_append_then_read_newest_first(tmp_path):
    d = tmp_path
    t0 = datetime(2026, 6, 5, 10, 0, 0)
    t1 = datetime(2026, 6, 5, 10, 3, 0)
    generation_log.append(d, "transcript", "ok", detail="12 seg", started=t0, completed=t1)
    generation_log.append(d, "summary", "error", error="429", started=t1, completed=t1)
    entries = generation_log.read(d)
    assert [e["action"] for e in entries] == ["summary", "transcript"]  # newest first
    assert entries[0]["status"] == "error" and entries[0]["error"] == "429"
    assert entries[1]["detail"] == "12 seg" and entries[1]["error"] is None
    assert entries[1]["started"] == "2026-06-05T10:00:00"


def test_read_missing_returns_empty(tmp_path):
    assert generation_log.read(tmp_path) == []


def test_read_corrupt_returns_empty(tmp_path):
    (tmp_path / ".generation-log.json").write_text("{not json", encoding="utf-8")
    assert generation_log.read(tmp_path) == []


def test_append_caps_to_limit(tmp_path):
    t = datetime(2026, 6, 5, 10, 0, 0)
    for i in range(60):
        generation_log.append(tmp_path, "transcript", "ok", detail=str(i), started=t, completed=t)
    entries = generation_log.read(tmp_path)
    assert len(entries) == 50
    assert entries[0]["detail"] == "59"  # newest kept
