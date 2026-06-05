"""Per-phase stage breakdown for the Dashboard processing stepper."""
import json


def _write_active(config, stage, stage_progress, skipped=None):
    entry = {
        "file": "reuniao.mp4",
        "status": "processing",
        "started": "2026-06-04T20:00:00",
        "completed": None,
        "details": {"transcription": "120 segmentos", "summary": "Enviando…"},
        "stage": stage,
        "stage_progress": stage_progress,
    }
    if skipped is not None:
        entry["skipped"] = skipped
    (config.vault_path / "wiki" / ".processing-history.json").write_text(
        json.dumps([entry]), encoding="utf-8"
    )


def test_status_includes_stage_breakdown(client, config):
    _write_active(config, 1, {"transcription": 50})
    job = client.get("/api/status").json()["active"][0]
    stages = job["stages"]
    assert len(stages) == 6
    assert stages[0]["key"] == "audio" and stages[0]["state"] == "done" and stages[0]["percent"] == 100
    assert stages[1]["key"] == "transcription" and stages[1]["state"] == "active"
    assert stages[1]["percent"] == 50 and stages[1]["detail"] == "120 segmentos"
    assert stages[2]["state"] == "pending" and stages[2]["percent"] == 0
    assert all(s["label"] for s in stages)  # every phase has a label


def test_status_marks_skipped_stages(client, config):
    _write_active(config, 2, {"summary": 10}, skipped=["kanban", "wiki"])
    by_key = {s["key"]: s for s in client.get("/api/status").json()["active"][0]["stages"]}
    assert by_key["kanban"]["state"] == "skipped"
    assert by_key["wiki"]["state"] == "skipped"
    assert by_key["summary"]["state"] == "active"


def test_history_persists_skipped(config):
    from meeting_processor.dashboard import Dashboard

    dash = Dashboard(config)
    job = dash.new_job("x.mp4")
    job.skip("kanban")
    dash.update(job)
    data = json.loads(
        (config.vault_path / "wiki" / ".processing-history.json").read_text(encoding="utf-8")
    )
    assert "kanban" in data[0]["skipped"]
