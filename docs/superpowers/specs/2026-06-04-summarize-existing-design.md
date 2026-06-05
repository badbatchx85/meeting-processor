# Generate Summary From an Existing Transcription

**Date:** 2026-06-04
**Status:** Approved design

## Goal

Let the user click **"Gerar resumo"** on a meeting that has only a transcription
(summary disabled, or the summary step failed — e.g. Gemini 429) and produce the
structured summary (purpose, meeting type, decisions, action items, …), the
Resumo note, and Kanban/wiki per Settings — **without re-doing audio or
transcription**. Runs in the background; the Dashboard stepper + Conversões
history reflect it, and a repeat failure is recorded.

## Architecture (DRY)

The summary half of `MeetingPipeline.process()` (steps 3–6: summary → note →
kanban → wiki) already operates only on a `transcript` + `MeetingPaths`. Extract
it into one shared helper and reuse it for both normal processing and
re-summarizing. The transcript is reconstructed from the saved
`Transcricao - *.md` (the module that wrote the format owns reading it).

## Backend changes

1. **`meeting_processor/utils.py`** — extend `parse_timestamp` to also handle
   2-part `MM:SS[.mmm]` (currently returns `0.0`). The saved transcript uses
   `MM:SS` (from `format_timestamp`), so reconstruction needs this. 3-part
   behavior is unchanged.

2. **`meeting_processor/note_generator.py`**
   - `read_transcription(path) -> Transcript`: parse `**[ts]** text` lines (skip
     the `# Transcricao` header / blanks) into `TranscriptSegment`s
     (`start = parse_timestamp(ts)`, `text`, `end = next start or own start`),
     `duration = last end`, `language = config.whisper_language`.
   - `paths_for_existing(meeting_dir: Path) -> MeetingPaths`: derive
     folder_name = `meeting_dir.name` and the Resumo/Tarefas/Transcricao names
     from it (reusing the same naming convention as `prepare`).

3. **`meeting_processor/pipeline.py`**
   - Extract the existing steps 3–6 from `process()` into
     `_summarize(transcript, paths, source_file, created_at, job, steps) -> MeetingSummary | None`.
     `process()` calls it (behavior unchanged).
   - `summarize_existing(meeting_id: str) -> None`:
     - `meeting_dir = config.reunioes_path / meeting_id`; locate the
       `Transcricao - *.md` (raise `FileNotFoundError` if absent).
     - `transcript = note_generator.read_transcription(...)`;
       `paths = note_generator.paths_for_existing(meeting_dir)`.
     - `job = dashboard.new_job(meeting_id)`; mark audio+transcription done by
       advancing current stage to `summary` (so the stepper shows them done).
     - effective `steps = {summary: True, note: True, kanban: config.enable_kanban, wiki: config.enable_wiki}`
       (forces summary+note; respects kanban/wiki toggles).
     - call `_summarize(...)`; on exception `job.fail(str(e))` and re-raise.

4. **`meeting_processor/web/app.py`** — `POST /api/meetings/{meeting_id}/summarize`:
   - `meeting_dir` missing or no `Transcricao - *.md` → `HTTPException(404)`.
   - else spawn a daemon thread running
     `MeetingPipeline(config).summarize_existing(meeting_id)` (mirrors
     `/api/process`: `try/except logger.exception`), return
     `{"ok": True, "queued": True, "meeting_id": meeting_id}`.

## Frontend changes

5. **`hooks/useApi.ts`** — `useSummarizeMeeting()` mutation → POST
   `/api/meetings/{id}/summarize`; on success invalidate `["status"]`,
   `["meetings"]`, `["history"]`.

6. **`pages/MeetingDetail.tsx`** — when `!d.resumo_md.trim()` (no summary yet),
   show a "sem resumo ainda" note + a **"Gerar resumo"** button (in the Summary
   tab and/or the card header). Click → `mutate(id)` → toast "Gerando resumo —
   acompanhe no Dashboard."; disable while pending.

## Testing (TDD)

**Backend (`tests/`):**
- `parse_timestamp("05:03") == 303.0`; `parse_timestamp("01:02:03") == 3723.0`
  (3-part unchanged).
- `read_transcription`: write a transcript via `NoteGenerator` then read it back
  → segment count + first text match, `duration > 0`.
- `summarize_existing` with a **monkeypatched `MeetingSummarizer`** returning a
  canned `MeetingSummary`: writes `Resumo - *.md` into the existing folder; and
  `GET /api/meetings` then reports `has_summary: true` for it.
- `POST /api/meetings/{id}/summarize`: 404 for a missing meeting; 200 `queued`
  for a transcription-only meeting (pipeline monkeypatched so no real LLM).

**Frontend (`frontend/src/__tests__/`):**
- MeetingDetail: with empty `resumo_md`, the "Gerar resumo" button renders and a
  click POSTs to the summarize endpoint; with non-empty `resumo_md`, the button
  is absent.

## Out of scope

- Auto-switching the LLM provider on a 429.
- Live in-place refresh of the detail page while summarizing (user watches the
  Dashboard / revisits).
- Re-transcription; editing the transcript before summarizing.
