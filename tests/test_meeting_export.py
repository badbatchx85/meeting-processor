"""Tests for the meetings list new fields + markdown/docx export."""
import io


def _write_meeting(vault_path):
    """Create a meeting folder with a Resumo note carrying the new fields."""
    folder = vault_path / "wiki" / "reunioes" / "2026-06-04 10h00 - reuniao"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "Resumo - 2026-06-04 10h00 - reuniao.md").write_text(
        """---
type: source
title: "2026-06-04 10h00 - reuniao"
created: 2026-06-04
duration: "10m"
participants: ["Ana"]
meeting_type: "planejamento"
purpose: "Alinhar o roadmap"
---

# 2026-06-04 10h00 - reuniao

**Tipo:** planejamento
**Participantes:** Ana

## Propósito

Alinhar o roadmap

## Resumo Executivo

Discussão do roadmap.

## Decisões

- Adiar o lançamento

## Tarefas Identificadas

- [ ] Preparar deck (Responsavel: Ana)

## Questões em Aberto

- Quem assume o suporte?

## Transcricao Completa

> [!info] Transcricao original
> [[Transcricao - 2026-06-04 10h00 - reuniao|Transcricao]]
""",
        encoding="utf-8",
    )
    return folder.name


def test_list_meetings_includes_type_and_purpose(client, config):
    _write_meeting(config.vault_path)
    r = client.get("/api/meetings")
    assert r.status_code == 200
    m = r.json()[0]
    assert m["meeting_type"] == "planejamento"
    assert m["purpose"] == "Alinhar o roadmap"


def test_export_md_returns_summary_without_transcript_link(client, config):
    mid = _write_meeting(config.vault_path)
    r = client.get(f"/api/meetings/{mid}/export.md")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert "attachment" in r.headers.get("content-disposition", "")
    body = r.text
    assert "Alinhar o roadmap" in body          # purpose
    assert "- Adiar o lançamento" in body        # decision
    assert "Quem assume o suporte?" in body       # open question
    assert "## Transcricao Completa" not in body  # transcript link stripped


def test_export_md_missing_meeting_404(client):
    r = client.get("/api/meetings/nope/export.md")
    assert r.status_code == 404
