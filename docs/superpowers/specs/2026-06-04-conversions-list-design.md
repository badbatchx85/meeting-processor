# Conversions List + Un-hide Transcription-only Meetings

**Date:** 2026-06-04
**Status:** Approved design

## Problem

A processed file "disappeared" from the SPA. Root cause: the summary step
failed (Gemini HTTP 429), so no `Resumo - *.md` was written, and
`_list_meetings` only lists folders that contain a `Resumo - *.md`. The
transcription is safe on disk but invisible. The SPA also has no view of the
processing history, so the failure itself is invisible.

## Goal

1. **Un-hide** meetings that have a transcription but no summary.
2. Add a **conversions/history list** (incl. failures + reason) to the SPA, on
   both the Dashboard (compact recent runs) and the Meetings page (full list).

## Backend

1. **`_list_meetings`** (`web/app.py`): list a folder when it has a
   `Resumo - *.md` **or** a `Transcricao - *.md` (not Resumo-only). When no
   Resumo exists, `meta` is `{}` (created/duration/etc. empty). Add a
   `"has_summary": bool(resumos)` flag to each meeting dict so the UI can badge
   transcription-only meetings.

2. **`_history_entry(entry)`** (new helper, `web/app.py`): shape a raw history
   record into `{file, status, started, completed, failed_stage, error, detail}`
   where `error = entry.get("error_message")`,
   `detail = (entry.get("details") or {}).get("result", "")`.

3. **`GET /api/history`** (new route): return
   `[_history_entry(e) for e in _read_status(config.vault_path, config.watch_dir)["history"]]`
   (already most-recent-first, capped at 20). 404 is N/A — empty list when none.

## Frontend

4. **`types.ts`**: add `has_summary: boolean` to `MeetingSummary`; add
   ```ts
   export interface HistoryEntry {
     file: string; status: string; started: string; completed: string | null;
     failed_stage: string | null; error: string | null; detail: string;
   }
   ```

5. **`hooks/useApi.ts`**: `useHistory()` → `api.get<HistoryEntry[]>("/api/history")`,
   query key `["history"]`. Dashboard's existing "active drained" effect also
   invalidates `["history"]` (so a finished/failed run shows up).

6. **`components/ConversionHistory.tsx`** (new, presentational): given
   `entries: HistoryEntry[]` and optional `limit`, render rows: filename, a
   status pill (`completed` → "OK" emerald, `error` → "erro" rose), the
   timestamp, and for errors the `failed_stage` + truncated `error` reason; for
   completed, the `detail`. Empty state when no entries.

7. **`pages/Meetings.tsx`**: below the table, a "Histórico de conversões"
   section using `<ConversionHistory entries={...} />` (full). Also show a "só
   transcrição" badge on rows where `!has_summary`.

8. **`pages/Dashboard.tsx`**: a "Conversões recentes" card using
   `<ConversionHistory entries={...} limit={5} />`.

## Testing (TDD)

**Backend (`tests/`):**
- `_list_meetings` lists a folder with only a `Transcricao - *.md`
  (`has_summary == False`); a folder with a Resumo has `has_summary == True`.
- `GET /api/history`: given a `.processing-history.json` with one `completed`
  and one `error` entry, returns both shaped, with the error's `failed_stage`
  and `error` reason present.

**Frontend (`frontend/src/__tests__/`):**
- `ConversionHistory.test.tsx`: renders a completed row (OK + detail) and an
  error row (erro + failed_stage + reason).
- Extend `meetings.test.tsx`: a meeting with `has_summary: false` shows the "só
  transcrição" badge.

## Out of scope

- Re-running only the summary on an existing transcription (resume) — a useful
  follow-up, noted but separate.
- Linking each history row to its meeting detail (filename→folder mapping).
- Auto-retry / provider fallback on LLM 429.
