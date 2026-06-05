# Meeting Summary: Purpose/Type/Decisions/Open-Questions + Markdown/Word Export

**Date:** 2026-06-04
**Status:** Approved design

## Goal

Enrich the meeting summary with four new structured fields — **purpose**,
**meeting type**, **decisions**, and **open questions/risks** — surface them in
the SPA meeting detail, the meetings list, and the Obsidian note, and let users
**export a meeting's summary as Markdown or Word (.docx)**.

## Architecture decision

**Markdown-as-truth (Approach 1).** The web layer never sees the in-memory
`MeetingSummary`; it reads the vault's `Resumo - *.md` file — frontmatter
becomes `meta`, the body becomes `resumo_md` (rendered by react-markdown).
Therefore the new fields travel through the note:

- `purpose` and `meeting_type` → **frontmatter scalars** (structured access for
  the list badge and detail header; `_load_meeting` already returns the full
  `meta` dict, so the SPA gets them with no load-path change).
- `decisions` and `open_questions` → **body sections** (render automatically via
  `resumo_md`).

Exports are built from the meeting's parsed content (`meta` + body + tasks). No
second source of truth (`summary.json` was considered and rejected as YAGNI /
drift risk).

**Backward compatibility:** all new model fields default to empty; meetings
processed before this change (no new frontmatter/sections) still load, list,
and export — just without the new content.

## Components & changes

### Backend

1. **`meeting_processor/models.py`** — extend `MeetingSummary`:
   ```python
   purpose: str = ""
   meeting_type: str = ""
   decisions: list[str] = []
   open_questions: list[str] = []
   ```

2. **`meeting_processor/summarizer.py`**
   - Extend `SYSTEM_PROMPT`'s JSON schema with the four fields and add rules:
     - `purpose`: one sentence — why the meeting happened / its objective.
     - `meeting_type`: short label inferred from content (e.g. `daily/standup`,
       `1:1`, `planejamento`, `retrospectiva`, `reunião com cliente`,
       `brainstorm`); empty string if unclear.
     - `decisions`: list of decisions made (distinct from action items); `[]` if
       none.
     - `open_questions`: unresolved questions / risks / blockers raised but not
       settled; `[]` if none.
   - Map all four in `_parse_response` with safe defaults
     (`data.get("purpose", "")`, `data.get("decisions", [])`, etc.).
   - Include the four fields in `_empty_summary()` (empty values).

3. **`meeting_processor/note_generator.py`** — in `_build_note`:
   - Frontmatter: add `meeting_type: "<value>"` and `purpose: "<value>"`
     (single-line scalars, quoted; reuse existing escaping conventions).
   - Body, inserted in this order relative to existing sections:
     - `## Propósito` (a paragraph) — after the quick-info block, before
       `## Resumo Executivo`. Omitted if `purpose` is empty.
     - `## Decisões` (bulleted list) — after `## Resumo por Periodo`, before
       `## Tarefas Identificadas`. Omitted if `decisions` is empty.
     - `## Questões em Aberto` (bulleted list) — after `## Tarefas
       Identificadas`. Omitted if `open_questions` is empty.
   - `meeting_type` is shown in the quick-info block (e.g. `**Tipo:** <value>`)
     when non-empty.

4. **`meeting_processor/web/app.py`**
   - `_list_meetings`: add `"meeting_type": meta.get("meeting_type", "")` and
     `"purpose": meta.get("purpose", "")` to each meeting dict.
   - Two new routes near the other `/api/meetings` routes:
     - `GET /api/meetings/{meeting_id}/export.md` → `text/markdown`
       (Content-Disposition attachment).
     - `GET /api/meetings/{meeting_id}/export.docx` →
       `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
       (attachment).
     - Both 404 when the meeting does not exist.

5. **`meeting_processor/web/meeting_export.py`** (new module)
   - `to_markdown(meeting: dict) -> str` — compose a clean summary document from
     `_load_meeting` output: a title, a metadata block (type, purpose,
     participants, duration, date from `meta`), then the `resumo_md` body, then
     a tasks checklist from `meeting["tasks"]`. Transcript excluded.
   - `to_docx(meeting: dict) -> bytes` — build a `.docx` via `python-docx`. A
     small line-based renderer walks the composed Markdown (from
     `to_markdown`): `#`/`##`/`###` → `add_heading(level)`, `- [ ] ` →
     checkbox-style paragraph, `- ` → `List Bullet` paragraph, blank line →
     skip, anything else → normal paragraph (bold `**...**` runs handled
     minimally). Returns the document serialized to bytes via an in-memory
     `io.BytesIO`. Scope is bounded because we only ever render our own
     known-format Markdown.

6. **`requirements.txt`** — add `python-docx>=1.1.0`.

### Frontend

7. **`frontend/src/api/types.ts`**
   - `MeetingSummary` (list item): add `meeting_type: string; purpose: string;`.
   - `MeetingDetail.meta` is already `Record<string, string>`, so
     `meta.meeting_type` / `meta.purpose` need no type change.

8. **`frontend/src/pages/MeetingDetail.tsx`**
   - Header above the tabbed content: render `meta.purpose` as a subtitle and a
     `meeting_type` badge (reuse a small pill style) when present.
   - An **Export** control (two links/buttons) pointing at
     `/api/meetings/{id}/export.md` and `/api/meetings/{id}/export.docx`
     (plain anchor downloads — no client JS needed beyond the href).

9. **`frontend/src/pages/Meetings.tsx`**
   - Add a meeting-type badge next to the title and `purpose` as a muted
     subtitle in the table row, when present.

## Data flow

```
LLM → MeetingSummary(+purpose,type,decisions,open_questions)   [pipeline, in-memory]
  → NoteGenerator._build_note → Resumo - *.md  (frontmatter: type,purpose;
                                                 body: Propósito/Decisões/Questões)
  → vault                                              [persisted, source of truth]

Web read:
  _load_meeting → {meta(type,purpose,…), resumo_md(body incl. new sections), tasks}
    → SPA detail: header(purpose+type) + markdown body(decisions/open-qs render)
    → export.md  = meeting_export.to_markdown(meeting)
    → export.docx = meeting_export.to_docx(meeting)   [python-docx]
  _list_meetings → adds meeting_type, purpose → SPA list badge + subtitle
```

## Error handling

- Missing meeting on export routes → 404 (mirror existing `_load_meeting`
  `FileNotFoundError` → `HTTPException(404)` pattern).
- Empty/absent new fields → sections and frontmatter values omitted or empty;
  never crash. Existing (pre-feature) meetings export fine.
- LLM omitting the fields → defaults applied in `_parse_response`.

## Testing (TDD)

**Backend (`tests/`):**
- Parser: `_parse_response` maps `purpose`, `meeting_type`, `decisions`,
  `open_questions`; and applies defaults when the keys are absent.
- Note generator: `_build_note` output contains `meeting_type:`/`purpose:` in
  frontmatter and `## Decisões` / `## Questões em Aberto` sections when data is
  present; omits them when empty.
- `_list_meetings`: returns `meeting_type` and `purpose` from frontmatter.
- Export markdown: `GET /api/meetings/{id}/export.md` → 200, `text/markdown`,
  body contains the purpose text and a decision bullet (fixture meeting written
  into a tmp vault). Missing id → 404.
- Export docx: `GET /api/meetings/{id}/export.docx` → 200, correct content-type,
  non-empty body; parse the bytes back with `python-docx` and assert a heading
  paragraph exists. Missing id → 404.

**Frontend (`frontend/src/__tests__/`):**
- MeetingDetail: stub fetch with `meta.purpose`/`meta.meeting_type`; assert the
  purpose text and type badge render, and that export links carry the correct
  hrefs.
- Meetings list: stub meetings with `meeting_type`/`purpose`; assert badge +
  subtitle render.

## Out of scope

- Persisting structured `summary.json` (Approach 2).
- Exporting the full transcript (large; viewable in the detail tab).
- PDF export, batch/multi-meeting export, server-side pandoc.
- Speaker diarization (separate feature, deferred).
