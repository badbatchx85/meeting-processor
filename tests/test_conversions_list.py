"""Un-hide transcription-only meetings + the conversions/history endpoint."""
import json


def _make_meeting(vault_path, folder, *, with_resumo: bool):
    d = vault_path / "wiki" / "reunioes" / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / f"Transcricao - {folder}.md").write_text("# Transcricao\n\n**[00:00]** oi\n", encoding="utf-8")
    if with_resumo:
        (d / f"Resumo - {folder}.md").write_text(
            f'---\ntitle: "{folder}"\ncreated: 2026-06-04\n---\n\n# {folder}\n\n## Resumo Executivo\n\nok\n',
            encoding="utf-8",
        )
    return folder


def test_list_includes_transcription_only_meeting(client, config):
    _make_meeting(config.vault_path, "2026-06-04 10h00 - so-transcricao", with_resumo=False)
    r = client.get("/api/meetings")
    assert r.status_code == 200
    items = {m["id"]: m for m in r.json()}
    assert "2026-06-04 10h00 - so-transcricao" in items
    assert items["2026-06-04 10h00 - so-transcricao"]["has_summary"] is False


def test_list_marks_summary_meeting(client, config):
    _make_meeting(config.vault_path, "2026-06-04 11h00 - com-resumo", with_resumo=True)
    r = client.get("/api/meetings")
    items = {m["id"]: m for m in r.json()}
    assert items["2026-06-04 11h00 - com-resumo"]["has_summary"] is True


def test_history_endpoint_returns_completed_and_error(client, config):
    history = config.vault_path / "wiki" / ".processing-history.json"
    history.write_text(
        json.dumps([
            {
                "file": "ok.mp4", "status": "completed",
                "started": "2026-06-04T09:00:00", "completed": "2026-06-04T09:05:00",
                "details": {"result": "3 tarefas, 2 participantes"},
                "stage": 6, "error_message": None, "failed_stage": None,
            },
            {
                "file": "bad.mp4", "status": "error",
                "started": "2026-06-04T10:00:00", "completed": "2026-06-04T10:40:00",
                "details": {"summary": "Enviando ao Gemini..."},
                "stage": 2, "error_message": "Gemini 429 Too Many Requests",
                "failed_stage": "Gerando resumo com LLM",
            },
        ]),
        encoding="utf-8",
    )
    r = client.get("/api/history")
    assert r.status_code == 200
    by_file = {e["file"]: e for e in r.json()}
    assert set(by_file) == {"ok.mp4", "bad.mp4"}

    ok = by_file["ok.mp4"]
    assert ok["status"] == "completed"
    assert ok["detail"] == "3 tarefas, 2 participantes"

    bad = by_file["bad.mp4"]
    assert bad["status"] == "error"
    assert bad["failed_stage"] == "Gerando resumo com LLM"
    assert "429" in bad["error"]
