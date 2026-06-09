"""Jobs presos em 'processing': reconciliação no boot, cancelamento manual e
a correção de origem no pipeline (falha na etapa de áudio marca erro)."""
import json
from pathlib import Path

import pytest

import meeting_processor.pipeline as pipemod
import meeting_processor.web.app as appmod
from meeting_processor.pipeline import MeetingPipeline


def _write_history(vault: Path, entries: list[dict]) -> Path:
    p = vault / "wiki" / ".processing-history.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    return p


def _read_history(vault: Path) -> list[dict]:
    return json.loads((vault / "wiki" / ".processing-history.json").read_text(encoding="utf-8"))


# --- Reconciliação de jobs órfãos no boot -----------------------------------


def test_reconcile_marks_active_jobs_as_error(config):
    vault = config.vault_path
    _write_history(vault, [
        {"file": "a.mp4", "status": "processing", "started": "2026-01-01T00:00:00", "stage": 2},
        {"file": "b.mp4", "status": "waiting", "started": "2026-01-01T00:00:00", "stage": -1},
        {"file": "c.mp4", "status": "completed", "started": "2026-01-01T00:00:00", "stage": 6},
    ])
    n = appmod._reconcile_stale_jobs(vault)
    assert n == 2
    data = _read_history(vault)
    by_file = {e["file"]: e for e in data}
    assert by_file["a.mp4"]["status"] == "error"
    assert by_file["a.mp4"]["error_message"]
    assert by_file["b.mp4"]["status"] == "error"
    assert by_file["c.mp4"]["status"] == "completed"  # intocado


def test_reconcile_noop_without_history(config):
    assert appmod._reconcile_stale_jobs(config.vault_path) == 0


# --- Cancelamento manual via API --------------------------------------------


def test_cancel_active_job_removes_it_from_active(client, config):
    vault = config.vault_path
    _write_history(vault, [
        {"file": "a.mp4", "status": "processing", "started": "2026-01-01T00:00:00", "stage": 1},
    ])
    r = client.post("/api/process/cancel", json={"file": "a.mp4"})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert client.get("/api/status").json()["active"] == []
    entry = _read_history(vault)[0]
    assert entry["status"] == "error"


def test_cancel_unknown_job_returns_error(client, config):
    _write_history(config.vault_path, [
        {"file": "a.mp4", "status": "completed", "started": "2026-01-01T00:00:00", "stage": 6},
    ])
    r = client.post("/api/process/cancel", json={"file": "a.mp4"})
    assert r.status_code == 404
    assert r.json()["ok"] is False


def test_status_exposes_started_for_cancel(client, config):
    _write_history(config.vault_path, [
        {"file": "a.mp4", "status": "processing", "started": "2026-01-01T00:00:00", "stage": 1},
    ])
    job = client.get("/api/status").json()["active"][0]
    assert job["started"] == "2026-01-01T00:00:00"


# --- Correção de origem: falha na etapa 1 (áudio) marca o job como erro ------


def test_audio_extraction_failure_marks_job_error(config, monkeypatch, tmp_path):
    def boom(*_a, **_k):
        raise RuntimeError("ffmpeg explodiu")

    monkeypatch.setattr(pipemod, "extract_audio", boom)
    pipe = MeetingPipeline(config)
    video = tmp_path / "reuniao.mp4"
    video.write_bytes(b"x")

    with pytest.raises(RuntimeError):
        pipe.process(video)

    entry = [e for e in _read_history(config.vault_path) if e["file"] == "reuniao.mp4"][-1]
    assert entry["status"] == "error"
    assert "ffmpeg" in (entry.get("error_message") or "")
