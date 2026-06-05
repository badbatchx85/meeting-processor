# Summary Fields + Markdown/Word Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four structured summary fields (purpose, meeting_type, decisions, open_questions) to the meeting pipeline and surface them in the SPA, the meetings list, and the Obsidian note; let users export a meeting's summary as Markdown or Word (.docx).

**Architecture:** Markdown-as-truth. New fields flow into the `Resumo - *.md` note — `meeting_type`/`purpose` as frontmatter scalars (read into `meta`), `decisions`/`open_questions` as body sections (rendered via `resumo_md`). Exports are built from the meeting's already-parsed content; the `.docx` is rendered from our own known-format Markdown via a small line-based renderer using `python-docx`.

**Tech Stack:** Python 3.11+, FastAPI, pydantic, pytest (backend, venv at `.venv/bin/`); React 18 + TypeScript + Vite + vitest (frontend, run from `frontend/`); `python-docx` for Word export.

**Reference spec:** `docs/superpowers/specs/2026-06-04-summary-fields-export-design.md`

**Conventions:**
- Backend commands prefixed with `.venv/bin/`. Frontend commands run from `frontend/`.
- Commit after every green step.

---

## File Structure

**Backend (modify):**
- `meeting_processor/models.py` — add 4 fields to `MeetingSummary`.
- `meeting_processor/summarizer.py` — extend `SYSTEM_PROMPT`, `_parse_response`, `_empty_summary`.
- `meeting_processor/note_generator.py` — frontmatter + body sections in `_build_note`.
- `meeting_processor/web/app.py` — `_list_meetings` fields; 2 export routes.
- `requirements.txt` — add `python-docx`.

**Backend (create):**
- `meeting_processor/web/meeting_export.py` — `to_markdown(meeting)` + `to_docx(meeting)`.
- `tests/test_summary_fields.py`, `tests/test_meeting_export.py`.

**Frontend (modify):**
- `frontend/src/api/types.ts` — extend `MeetingSummary` list type.
- `frontend/src/pages/MeetingDetail.tsx` — purpose/type header + export links.
- `frontend/src/pages/Meetings.tsx` — type badge + purpose subtitle.

**Frontend (create):**
- `frontend/src/__tests__/meetings.test.tsx`.
- Extend `frontend/src/__tests__/meetingDetail.test.tsx`.

---

## Phase 1 — Backend data model + prompt + parser

### Task 1: Add the four fields to `MeetingSummary` and parse them

**Files:**
- Modify: `meeting_processor/models.py`
- Modify: `meeting_processor/summarizer.py` (`SYSTEM_PROMPT` ~41-76, `_parse_response` ~197-205, `_empty_summary` ~208-215)
- Create: `tests/test_summary_fields.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_summary_fields.py`:
```python
"""Parser/prompt coverage for the new structured summary fields."""
from meeting_processor.config import load_config
from meeting_processor.summarizer import _BaseSummarizer


class _Parser(_BaseSummarizer):
    """Concrete subclass so we can call the inherited _parse_response."""
    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:  # pragma: no cover
        return ""


def _parser() -> _Parser:
    return _Parser(load_config())


def test_parse_maps_new_fields():
    raw = """{
      "executive_summary": "ok",
      "time_windows": [],
      "action_items": [],
      "participants": [],
      "key_topics": [],
      "purpose": "Alinhar o roadmap do trimestre",
      "meeting_type": "planejamento",
      "decisions": ["Adiar o lançamento para julho"],
      "open_questions": ["Quem assume o suporte?"]
    }"""
    s = _parser()._parse_response(raw)
    assert s.purpose == "Alinhar o roadmap do trimestre"
    assert s.meeting_type == "planejamento"
    assert s.decisions == ["Adiar o lançamento para julho"]
    assert s.open_questions == ["Quem assume o suporte?"]


def test_parse_applies_defaults_when_fields_absent():
    raw = """{
      "executive_summary": "ok",
      "time_windows": [],
      "action_items": [],
      "participants": [],
      "key_topics": []
    }"""
    s = _parser()._parse_response(raw)
    assert s.purpose == ""
    assert s.meeting_type == ""
    assert s.decisions == []
    assert s.open_questions == []


def test_system_prompt_documents_new_fields():
    from meeting_processor.summarizer import SYSTEM_PROMPT
    for key in ("purpose", "meeting_type", "decisions", "open_questions"):
        assert key in SYSTEM_PROMPT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_summary_fields.py -v`
Expected: FAIL — `MeetingSummary` has no `purpose` (pydantic) / `SYSTEM_PROMPT` lacks keys.

- [ ] **Step 3: Add the fields to the model**

In `meeting_processor/models.py`, replace the `MeetingSummary` class:
```python
class MeetingSummary(BaseModel):
    executive_summary: str
    time_windows: list[TimeWindowSummary]
    action_items: list[ActionItem]
    participants: list[str]
    key_topics: list[str]
    purpose: str = ""
    meeting_type: str = ""
    decisions: list[str] = []
    open_questions: list[str] = []
```

- [ ] **Step 4: Extend the system prompt**

In `meeting_processor/summarizer.py`, replace the `SYSTEM_PROMPT` JSON block and rules (lines 41-76) with:
```python
SYSTEM_PROMPT = """\
Você é um assistente especializado em resumir reuniões transcritas em português brasileiro.
Analise a transcrição fornecida e produza uma análise estruturada em JSON.

Responda APENAS com JSON válido, sem markdown, sem blocos de código. O JSON deve seguir esta estrutura exata:

{
  "executive_summary": "Resumo executivo de 3-5 frases",
  "purpose": "Uma frase: por que a reunião aconteceu / qual o objetivo",
  "meeting_type": "Rótulo curto do tipo de reunião (ex.: daily, 1:1, planejamento, retrospectiva, reunião com cliente, brainstorm) ou string vazia",
  "time_windows": [
    {
      "start_minutes": 0,
      "end_minutes": 5,
      "summary": "Resumo do que foi discutido neste período"
    }
  ],
  "decisions": ["Decisão tomada na reunião"],
  "action_items": [
    {
      "description": "Descrição clara da tarefa",
      "assignee": "Nome do responsável ou null",
      "priority": "alta/média/baixa ou null",
      "due_date": "Prazo mencionado ou null",
      "source_timestamp": "MM:SS aproximado de quando foi mencionada"
    }
  ],
  "open_questions": ["Questão em aberto, risco ou bloqueio levantado mas não resolvido"],
  "participants": ["Nome1", "Nome2"],
  "key_topics": ["Tópico 1", "Tópico 2"]
}

Regras:
- O resumo executivo deve capturar as decisões principais e o tom geral da reunião.
- "purpose" deve ser uma única frase com o objetivo central da reunião; use string vazia se não der para inferir.
- "meeting_type" é um rótulo curto inferido do conteúdo; use string vazia se não estiver claro.
- Cada time_window cobre um bloco de {chunk_minutes} minutos da reunião.
- "decisions" lista apenas decisões efetivamente tomadas (distintas das tarefas); use lista vazia se não houver.
- Extraia TODAS as tarefas, ações e compromissos mencionados, mesmo os implícitos.
- "open_questions" lista perguntas/riscos/bloqueios levantados e não resolvidos; use lista vazia se não houver.
- Se não conseguir identificar participantes pelo nome, use "Participante 1", etc.
- Se não houver tarefas, retorne uma lista vazia para action_items.
- Tópicos principais devem ser 3-5 temas centrais discutidos.\
"""
```

- [ ] **Step 5: Map the fields in `_parse_response` and `_empty_summary`**

In `_parse_response`, replace the `return MeetingSummary(...)` (lines ~197-205) with:
```python
        return MeetingSummary(
            executive_summary=data.get("executive_summary", ""),
            time_windows=[
                TimeWindowSummary(**tw) for tw in data.get("time_windows", [])
            ],
            action_items=[ActionItem(**ai) for ai in data.get("action_items", [])],
            participants=data.get("participants", []),
            key_topics=data.get("key_topics", []),
            purpose=data.get("purpose", ""),
            meeting_type=data.get("meeting_type", ""),
            decisions=data.get("decisions", []),
            open_questions=data.get("open_questions", []),
        )
```
In `_empty_summary`, replace its `return MeetingSummary(...)` with:
```python
        return MeetingSummary(
            executive_summary="Erro ao processar resumo da reunião.",
            time_windows=[],
            action_items=[],
            participants=[],
            key_topics=[],
            purpose="",
            meeting_type="",
            decisions=[],
            open_questions=[],
        )
```

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_summary_fields.py -v`
Expected: 3 PASS.

- [ ] **Step 7: Commit**
```bash
git add meeting_processor/models.py meeting_processor/summarizer.py tests/test_summary_fields.py
git commit -m "feat(summary): add purpose, meeting_type, decisions, open_questions fields"
```

---

## Phase 2 — Obsidian note generation

### Task 2: Write new fields into the Resumo note

**Files:**
- Modify: `meeting_processor/note_generator.py` (`_build_note`, frontmatter ~155-176, body ~178-230)
- Modify: `tests/test_summary_fields.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_summary_fields.py`:
```python
def _summary_with_new_fields():
    from meeting_processor.models import MeetingSummary
    return MeetingSummary(
        executive_summary="Resumo.",
        time_windows=[],
        action_items=[],
        participants=["Ana"],
        key_topics=["Roadmap"],
        purpose="Alinhar o roadmap do trimestre",
        meeting_type="planejamento",
        decisions=["Adiar o lançamento para julho"],
        open_questions=["Quem assume o suporte?"],
    )


def test_note_includes_new_frontmatter_and_sections(tmp_path):
    from datetime import datetime
    from meeting_processor.config import load_config
    from meeting_processor.models import Transcript
    from meeting_processor.note_generator import NoteGenerator

    cfg = load_config()
    cfg.project_root = str(tmp_path)
    cfg.vault_dir = "vault"
    transcript = Transcript(segments=[], full_text="", language="pt", duration=60.0)
    gen = NoteGenerator(cfg)
    note = gen._build_note(
        title="2026-06-04 10h00 - reuniao",
        summary=_summary_with_new_fields(),
        transcript=transcript,
        source_file="reuniao.mp4",
        date_str="2026-06-04",
        created_at=datetime(2026, 6, 4, 10, 0),
    )
    # frontmatter scalars
    assert 'meeting_type: "planejamento"' in note
    assert 'purpose: "Alinhar o roadmap do trimestre"' in note
    # body sections
    assert "## Propósito" in note
    assert "## Decisões" in note
    assert "- Adiar o lançamento para julho" in note
    assert "## Questões em Aberto" in note
    assert "- Quem assume o suporte?" in note
    assert "**Tipo:** planejamento" in note


def test_note_omits_empty_new_sections(tmp_path):
    from datetime import datetime
    from meeting_processor.config import load_config
    from meeting_processor.models import MeetingSummary, Transcript
    from meeting_processor.note_generator import NoteGenerator

    cfg = load_config()
    cfg.project_root = str(tmp_path)
    cfg.vault_dir = "vault"
    summary = MeetingSummary(
        executive_summary="x", time_windows=[], action_items=[],
        participants=[], key_topics=[],
    )
    gen = NoteGenerator(cfg)
    note = gen._build_note(
        title="t", summary=summary,
        transcript=Transcript(segments=[], full_text="", language="pt", duration=1.0),
        source_file="x.mp4", date_str="2026-06-04",
        created_at=datetime(2026, 6, 4, 10, 0),
    )
    assert "## Propósito" not in note
    assert "## Decisões" not in note
    assert "## Questões em Aberto" not in note
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_summary_fields.py -v -k note`
Expected: FAIL — frontmatter/sections absent.

- [ ] **Step 3: Add frontmatter scalars**

In `meeting_processor/note_generator.py` `_build_note`, find the frontmatter f-string and replace the line:
```python
duration: "{duration}"
---"""
```
with:
```python
duration: "{duration}"
meeting_type: "{summary.meeting_type}"
purpose: "{summary.purpose}"
---"""
```

- [ ] **Step 4: Add the `Tipo` quick-info line and the `Propósito` section**

In `_build_note`, replace the quick-info block:
```python
        participants_str = ", ".join(summary.participants) if summary.participants else "N/A"
        topics_str = ", ".join(summary.key_topics) if summary.key_topics else "N/A"
        body_parts.extend([
            f"**Participantes:** {participants_str}  ",
            f"**Topicos:** {topics_str}  ",
            f"**Tarefas:** {len(summary.action_items)} - [[{tarefas_link}|Tarefas]]",
            "",
        ])
```
with:
```python
        participants_str = ", ".join(summary.participants) if summary.participants else "N/A"
        topics_str = ", ".join(summary.key_topics) if summary.key_topics else "N/A"
        quick_info = []
        if summary.meeting_type:
            quick_info.append(f"**Tipo:** {summary.meeting_type}  ")
        quick_info.extend([
            f"**Participantes:** {participants_str}  ",
            f"**Topicos:** {topics_str}  ",
            f"**Tarefas:** {len(summary.action_items)} - [[{tarefas_link}|Tarefas]]",
            "",
        ])
        body_parts.extend(quick_info)

        if summary.purpose:
            body_parts.extend([
                "## Propósito\n",
                f"{summary.purpose}\n",
            ])
```

- [ ] **Step 5: Add the `Decisões` section (after time windows) and `Questões em Aberto` (after tasks)**

In `_build_note`, immediately AFTER the time-windows block (the `for tw in summary.time_windows:` loop that ends before `# Tarefas identificadas`), insert:
```python
        # Decisões
        if summary.decisions:
            body_parts.append("## Decisões\n")
            for dec in summary.decisions:
                body_parts.append(f"- {dec}")
            body_parts.append("")
```
Then, AFTER the tasks block (`body_parts.append("")` that follows the `## Tarefas Identificadas` if/else) and BEFORE the `## Transcricao Completa` block, insert:
```python
        # Questões em aberto
        if summary.open_questions:
            body_parts.append("## Questões em Aberto\n")
            for q in summary.open_questions:
                body_parts.append(f"- {q}")
            body_parts.append("")
```

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_summary_fields.py -v`
Expected: all PASS (5 tests total).

- [ ] **Step 7: Commit**
```bash
git add meeting_processor/note_generator.py tests/test_summary_fields.py
git commit -m "feat(note): write purpose/type/decisions/open-questions into Resumo note"
```

---

## Phase 3 — Backend list field + exports

### Task 3: Expose `meeting_type` and `purpose` in the meetings list

**Files:**
- Modify: `meeting_processor/web/app.py` (`_list_meetings` ~123-133)
- Create: `tests/test_meeting_export.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_meeting_export.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_meeting_export.py -v -k list`
Expected: FAIL — `KeyError`/missing `meeting_type`.

- [ ] **Step 3: Add the fields to `_list_meetings`**

In `meeting_processor/web/app.py` `_list_meetings`, replace the appended dict:
```python
        meetings.append(
            {
                "id": entry.name,
                "title": entry.name,
                "created": meta.get("created", ""),
                "duration": meta.get("duration", ""),
                "task_count": task_count,
                "participants": meta.get("participants", ""),
                "source_file": meta.get("source_file", ""),
            }
        )
```
with:
```python
        meetings.append(
            {
                "id": entry.name,
                "title": entry.name,
                "created": meta.get("created", ""),
                "duration": meta.get("duration", ""),
                "task_count": task_count,
                "participants": meta.get("participants", ""),
                "source_file": meta.get("source_file", ""),
                "meeting_type": meta.get("meeting_type", ""),
                "purpose": meta.get("purpose", ""),
            }
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_meeting_export.py -v -k list`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add meeting_processor/web/app.py tests/test_meeting_export.py
git commit -m "feat(web): expose meeting_type and purpose in meetings list"
```

---

### Task 4: Markdown export module + route

**Files:**
- Create: `meeting_processor/web/meeting_export.py`
- Modify: `meeting_processor/web/app.py` (import + route after `/api/meetings/{meeting_id}` ~966)
- Modify: `tests/test_meeting_export.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_meeting_export.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_meeting_export.py -v -k "md"`
Expected: FAIL — 404 route absent.

- [ ] **Step 3: Create the export module (markdown half)**

Create `meeting_processor/web/meeting_export.py`:
```python
"""Export a single meeting's summary to Markdown or Word (.docx).

Source of truth is the meeting's Resumo note (already parsed by
``_load_meeting`` into ``{meta, resumo_md, tasks}``). The transcript is
intentionally excluded — it is large and viewable separately.
"""
from __future__ import annotations

import io
import re

_TRANSCRIPT_HEADING = "## Transcricao Completa"


def to_markdown(meeting: dict) -> str:
    """Return the summary body, trimming the trailing Obsidian transcript link."""
    body = meeting.get("resumo_md", "") or ""
    idx = body.find(_TRANSCRIPT_HEADING)
    if idx != -1:
        body = body[:idx]
    return body.rstrip() + "\n"
```

- [ ] **Step 4: Wire the markdown route**

In `meeting_processor/web/app.py`, add the import near the other `.` imports (after `from . import spa_serving`):
```python
from . import meeting_export
```
Then, immediately AFTER the `@app.get("/api/meetings/{meeting_id}")` handler (~966-970), add:
```python
    @app.get("/api/meetings/{meeting_id}/export.md")
    async def api_export_md(meeting_id: str):
        try:
            meeting = _load_meeting(config.vault_path, meeting_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Reunião não encontrada")
        body = meeting_export.to_markdown(meeting)
        return _attachment_response(
            body, f"{meeting_id}.md", "text/markdown; charset=utf-8"
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_meeting_export.py -v -k "md"`
Expected: 2 PASS.

- [ ] **Step 6: Commit**
```bash
git add meeting_processor/web/meeting_export.py meeting_processor/web/app.py tests/test_meeting_export.py
git commit -m "feat(web): GET /api/meetings/{id}/export.md (summary markdown)"
```

---

### Task 5: Word (.docx) export

**Files:**
- Modify: `requirements.txt`
- Modify: `meeting_processor/web/meeting_export.py` (add `to_docx`)
- Modify: `meeting_processor/web/app.py` (add `export.docx` route)
- Modify: `tests/test_meeting_export.py`

- [ ] **Step 1: Add and install python-docx**

Append to `requirements.txt`:
```
python-docx>=1.1.0
```
Run: `.venv/bin/pip install "python-docx>=1.1.0"`
Expected: installs `python-docx` and its dep `lxml`.

- [ ] **Step 2: Write the failing test**

Append to `tests/test_meeting_export.py`:
```python
def test_export_docx_returns_valid_document(client, config):
    import docx  # python-docx

    mid = _write_meeting(config.vault_path)
    r = client.get(f"/api/meetings/{mid}/export.docx")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert "attachment" in r.headers.get("content-disposition", "")
    assert len(r.content) > 0

    doc = docx.Document(io.BytesIO(r.content))
    full_text = "\n".join(p.text for p in doc.paragraphs)
    assert "Alinhar o roadmap" in full_text                 # purpose present
    assert any(p.style.name.startswith("Heading") for p in doc.paragraphs)  # a heading
    assert "Adiar o lançamento" in full_text                # decision bullet


def test_export_docx_missing_meeting_404(client):
    r = client.get("/api/meetings/nope/export.docx")
    assert r.status_code == 404
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_meeting_export.py -v -k docx`
Expected: FAIL — 404 route absent.

- [ ] **Step 4: Implement `to_docx` in `meeting_export.py`**

Append to `meeting_processor/web/meeting_export.py`:
```python
def _add_runs(paragraph, text: str) -> None:
    """Add text to a paragraph, rendering **bold** segments as bold runs."""
    for i, segment in enumerate(re.split(r"\*\*(.+?)\*\*", text)):
        if not segment:
            continue
        run = paragraph.add_run(segment)
        run.bold = i % 2 == 1  # odd indices are the captured bold groups


def to_docx(meeting: dict) -> bytes:
    """Render the summary markdown (from ``to_markdown``) into a .docx byte stream."""
    from docx import Document

    md = to_markdown(meeting)
    doc = Document()

    for raw_line in md.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if line.startswith("### "):
            doc.add_heading(line[4:].strip(), level=3)
        elif line.startswith("## "):
            doc.add_heading(line[3:].strip(), level=2)
        elif line.startswith("# "):
            doc.add_heading(line[2:].strip(), level=1)
        elif line.startswith("- [ ] ") or line.startswith("- [x] "):
            p = doc.add_paragraph(style="List Bullet")
            _add_runs(p, line[6:].strip())
        elif line.startswith("- "):
            p = doc.add_paragraph(style="List Bullet")
            _add_runs(p, line[2:].strip())
        elif line.startswith(">"):
            continue  # skip Obsidian callouts/quotes
        else:
            p = doc.add_paragraph()
            _add_runs(p, line)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
```

- [ ] **Step 5: Add the docx route**

In `meeting_processor/web/app.py`, immediately AFTER the `export.md` route added in Task 4, add:
```python
    @app.get("/api/meetings/{meeting_id}/export.docx")
    async def api_export_docx(meeting_id: str):
        try:
            meeting = _load_meeting(config.vault_path, meeting_id)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Reunião não encontrada")
        data = meeting_export.to_docx(meeting)
        return Response(
            content=data,
            media_type=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
            headers={
                "Content-Disposition": f'attachment; filename="{meeting_id}.docx"',
                "Cache-Control": "no-store",
            },
        )
```

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_meeting_export.py -v`
Expected: all PASS (list + md + docx + 404s).

- [ ] **Step 7: Run the full backend suite**

Run: `.venv/bin/pytest tests/ -q && .venv/bin/python test_web_app.py`
Expected: all green.

- [ ] **Step 8: Commit**
```bash
git add requirements.txt meeting_processor/web/meeting_export.py meeting_processor/web/app.py tests/test_meeting_export.py
git commit -m "feat(web): GET /api/meetings/{id}/export.docx via python-docx"
```

---

## Phase 4 — Frontend

### Task 6: Meeting detail — purpose/type header + export links

**Files:**
- Modify: `frontend/src/pages/MeetingDetail.tsx`
- Modify: `frontend/src/__tests__/meetingDetail.test.tsx`

- [ ] **Step 1: Write the failing test (extend existing)**

In `frontend/src/__tests__/meetingDetail.test.tsx`, update the fetch stub in `beforeEach` to include the new meta, and add a test. Replace the stub `Response` JSON with:
```tsx
      id: "abc", title: "abc",
      meta: { purpose: "Alinhar o roadmap", meeting_type: "planejamento" },
      resumo_md: "# Resumo aqui",
      tasks: [{ done: false, description: "Tarefa 1" }],
      transcricao_md: "linha de transcrição",
```
Then add this test inside the `describe("MeetingDetail", ...)` block:
```tsx
  it("renders purpose, a type badge, and export links", async () => {
    setup();
    expect(await screen.findByText("Alinhar o roadmap")).toBeInTheDocument();
    expect(screen.getByText("planejamento")).toBeInTheDocument();
    const md = screen.getByRole("link", { name: /Markdown/i });
    const docx = screen.getByRole("link", { name: /Word/i });
    expect(md).toHaveAttribute("href", "/api/meetings/abc/export.md");
    expect(docx).toHaveAttribute("href", "/api/meetings/abc/export.docx");
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/__tests__/meetingDetail.test.tsx`
Expected: FAIL — purpose text / export links not found.

- [ ] **Step 3: Implement the header + export links**

In `frontend/src/pages/MeetingDetail.tsx`, replace the opening of the returned `<Card ...>` (the `actions` prop and the line right after `const d = meeting.data;`) so the card actions include export links and a header renders. Replace:
```tsx
  const d = meeting.data;

  return (
    <Card title={d.title} actions={
      <a href={obsidianUri} className="text-sm text-brand hover:underline">Abrir no Obsidian</a>
    }>
      <div className="mb-4 flex gap-1 border-b border-slate-200">
```
with:
```tsx
  const d = meeting.data;
  const enc = encodeURIComponent(id);

  return (
    <Card title={d.title} actions={
      <div className="flex items-center gap-3 text-sm">
        <a href={`/api/meetings/${enc}/export.md`} className="text-brand hover:underline">Markdown</a>
        <a href={`/api/meetings/${enc}/export.docx`} className="text-brand hover:underline">Word</a>
        <a href={obsidianUri} className="text-brand hover:underline">Abrir no Obsidian</a>
      </div>
    }>
      {(d.meta.purpose || d.meta.meeting_type) && (
        <div className="mb-4 flex items-center gap-2">
          {d.meta.meeting_type && (
            <span className="rounded-full bg-brand/10 px-2.5 py-0.5 text-xs font-medium text-brand">
              {d.meta.meeting_type}
            </span>
          )}
          {d.meta.purpose && <p className="text-sm text-slate-600">{d.meta.purpose}</p>}
        </div>
      )}
      <div className="mb-4 flex gap-1 border-b border-slate-200">
```

- [ ] **Step 4: Run test + typecheck**

Run: `cd frontend && npx vitest run src/__tests__/meetingDetail.test.tsx && npx tsc -b --noEmit`
Expected: PASS, no type errors.

- [ ] **Step 5: Commit**
```bash
git add frontend/src/pages/MeetingDetail.tsx frontend/src/__tests__/meetingDetail.test.tsx
git commit -m "feat(spa): meeting detail purpose/type header + md/docx export links"
```

---

### Task 7: Meetings list — type badge + purpose subtitle

**Files:**
- Modify: `frontend/src/api/types.ts` (`MeetingSummary`)
- Modify: `frontend/src/pages/Meetings.tsx`
- Create: `frontend/src/__tests__/meetings.test.tsx`

- [ ] **Step 1: Extend the type**

In `frontend/src/api/types.ts`, replace the `MeetingSummary` interface:
```ts
export interface MeetingSummary {
  id: string; title: string; created: string; duration: string;
  task_count: number; participants: string; source_file: string;
  meeting_type: string; purpose: string;
}
```

- [ ] **Step 2: Write the failing test**

Create `frontend/src/__tests__/meetings.test.tsx`:
```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { Meetings } from "../pages/Meetings";
import { ToastProvider } from "../components/Toast";

function setup() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ToastProvider>
          <Meetings />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Meetings list", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify([
      {
        id: "abc", title: "Reunião X", created: "2026-06-04", duration: "10m",
        task_count: 2, participants: "Ana", source_file: "x.mp4",
        meeting_type: "planejamento", purpose: "Alinhar o roadmap",
      },
    ]), { status: 200 })));
  });

  it("shows the meeting type badge and purpose subtitle", async () => {
    setup();
    expect(await screen.findByText("Reunião X")).toBeInTheDocument();
    expect(screen.getByText("planejamento")).toBeInTheDocument();
    expect(screen.getByText("Alinhar o roadmap")).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/__tests__/meetings.test.tsx`
Expected: FAIL — badge/subtitle not rendered.

- [ ] **Step 4: Render the badge + subtitle**

In `frontend/src/pages/Meetings.tsx`, find the title cell (the `<td>` containing the `<Link ...>{m.title}</Link>`) and replace that `<td>` with:
```tsx
                <td className="py-2">
                  <div className="flex items-center gap-2">
                    <Link to={`/meetings/${encodeURIComponent(m.id)}`} className="font-medium hover:text-brand">{m.title}</Link>
                    {m.meeting_type && (
                      <span className="rounded-full bg-brand/10 px-2 py-0.5 text-xs font-medium text-brand">{m.meeting_type}</span>
                    )}
                  </div>
                  {m.purpose && <p className="text-xs text-slate-400">{m.purpose}</p>}
                </td>
```

- [ ] **Step 5: Run test + typecheck + full frontend suite**

Run: `cd frontend && npx vitest run && npx tsc -b --noEmit`
Expected: all PASS (5 test files), no type errors.

- [ ] **Step 6: Commit**
```bash
git add frontend/src/api/types.ts frontend/src/pages/Meetings.tsx frontend/src/__tests__/meetings.test.tsx
git commit -m "feat(spa): meetings list type badge + purpose subtitle"
```

---

## Phase 5 — Build + end-to-end verification

### Task 8: Build the SPA, run all suites, smoke test

**Files:** none (verification only)

- [ ] **Step 1: Build the SPA**

Run: `cd frontend && npm run build`
Expected: emits `meeting_processor/web/spa/index.html` + `assets/*`.

- [ ] **Step 2: Full test runs**

Run: `.venv/bin/pytest tests/ -q && .venv/bin/python test_web_app.py && cd frontend && npx vitest run`
Expected: backend all pass, smoke "TODOS PASSARAM", frontend all pass.

- [ ] **Step 3: Live smoke of the export endpoints**

Process or hand-create a meeting, then:
```bash
.venv/bin/python -m meeting_processor web --port 8799 > /tmp/mp_exp.log 2>&1 &
sleep 4
MID=$(/usr/bin/curl -s http://127.0.0.1:8799/api/meetings | python3 -c "import sys,json;d=json.load(sys.stdin);print(d[0]['id'] if d else '')")
echo "meeting: $MID"
/usr/bin/curl -s -o /dev/null -w "md=%{http_code} ct=%{content_type}\n" "http://127.0.0.1:8799/api/meetings/$MID/export.md"
/usr/bin/curl -s -o /dev/null -w "docx=%{http_code} ct=%{content_type}\n" "http://127.0.0.1:8799/api/meetings/$MID/export.docx"
kill %1
```
Expected: `md=200` (text/markdown), `docx=200` (…wordprocessingml.document). If there are no meetings yet, this step is informational only — the pytest export tests already cover behavior with a fixture meeting.

- [ ] **Step 4: Final commit (build artifacts are gitignored; nothing to add if clean)**

Run: `git status --short`
Expected: clean (SPA build under `meeting_processor/web/spa/` is gitignored).

---

## Self-Review

**Spec coverage:**
- New fields (purpose, meeting_type, decisions, open_questions) → Task 1 (model+prompt+parser).
- Obsidian note rendering → Task 2 (frontmatter + body sections).
- Meetings list fields → Task 3; SPA list badge/subtitle → Task 7.
- SPA detail header → Task 6.
- Markdown export endpoint/module → Task 4; Word export → Task 5; `python-docx` dep → Task 5 Step 1.
- Export scope = summary minus transcript → `to_markdown` strips `## Transcricao Completa` (Task 4) and docx renders from that (Task 5).
- Error handling (404 on missing) → Tasks 4/5 tests + route try/except.
- Backward compatibility (defaults) → Task 1 defaults; Task 2 omit-when-empty test.
- Testing (parser, note, list, export md/docx, frontend detail+list) → Tasks 1,2,3,4,5,6,7.

**Placeholder scan:** No TBD/TODO; every code step shows full code.

**Type/name consistency:** `meeting_export.to_markdown`/`to_docx` used in routes match the module (Tasks 4/5). `_attachment_response(body, filename, content_type)` signature matches its definition in app.py. `MeetingSummary` field names (`purpose`, `meeting_type`, `decisions`, `open_questions`) consistent across model, parser, note generator, and frontmatter keys read by `_list_meetings`/`meta`. Frontend `MeetingSummary` gains `meeting_type`/`purpose` (Task 7) used in Meetings.tsx; `d.meta.purpose`/`d.meta.meeting_type` used in MeetingDetail (meta is `Record<string,string>`, no type change needed).
