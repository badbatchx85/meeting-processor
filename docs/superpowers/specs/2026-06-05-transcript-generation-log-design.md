# Re-generate Transcript / Summary Buttons + Per-Meeting Generation Log

**Date:** 2026-06-05
**Status:** Approved design

## Goal

Give the user explicit, auditable control over the two generation steps of a
meeting:

1. **Gerar transcrição** — re-run Whisper on the meeting's original media file
   (no summary), overwriting the saved transcript. Useful when a transcript is
   empty/garbled or the first run failed.
2. **Gerar resumo** — regenerate the summary from the existing transcript. This
   already exists (`summarize_existing`) but is only reachable when there is *no*
   summary; make it always-available so a **failed** summary (e.g. the
   `Erro ao processar resumo da reunião` note) can be retried.
3. **Apenas transcrição (novo arquivo)** — on the Dashboard, transcribe a freshly
   uploaded / pointed file **without** the summary step.
4. **Apagar arquivo de origem** — delete the original media file (video/audio)
   that produced the transcript, to reclaim disk once the transcript is good. The
   transcript/summary in the vault are **kept**; only the source file on disk is
   removed. After deletion re-transcription is no longer possible, so the UI
   disables "Gerar transcrição" and shows the source as unavailable.

Every run is recorded in a **dedicated per-meeting generation log** shown on the
meeting detail page: did it run OK, and if not, *why*. Runs happen in the
background (same daemon-thread + `ProcessingJob` model as today); the existing
Dashboard stepper and Conversões history keep working unchanged.

## Architecture

Mirror the existing `summarize_existing` pattern exactly. Two new pieces of
infrastructure:

- A small **generation log** subsystem (`generation_log.py`) that appends JSON
  entries to `<meeting_dir>/.generation-log.json`. Co-locating the log in the
  meeting folder means it is auto-scoped to the meeting and auto-removed when the
  meeting is deleted (the delete handler already `rmtree`s the folder).
- A new pipeline method `transcribe_existing(meeting_id)` that is the transcript
  twin of `summarize_existing`.

Source media is located by **filename search**, not a stored path. Two cases:
- A **summarized** meeting records `source_file` (bare name incl. extension, e.g.
  `Screen_Recording_….mkv`) in the Resumo note frontmatter.
- A **transcript-only** meeting records `source_file` **nowhere** (the raw
  transcription note has no frontmatter). But the meeting folder name is
  `"{date} {time} - {source_stem}"` (e.g.
  `2026-06-04 22h14 - Screen_Recording_20260531_114054_WhatsApp`), so the source
  *stem* is always recoverable by stripping the `YYYY-MM-DD HhMM - ` prefix.

So location works for both: prefer the exact recorded `source_file` if present,
otherwise match by stem against any supported extension. Re-transcription searches
`uploads/` then `watch_dir`. If the file is gone, that is logged as an error — not
a crash.

## Generation log format

`<meeting_dir>/.generation-log.json` — a JSON list, newest entries appended:

```json
[
  { "action": "transcript", "status": "ok",
    "error": null, "detail": "1240 segmentos, 38m12s",
    "started": "2026-06-05T10:00:00", "completed": "2026-06-05T10:03:11" },
  { "action": "summary", "status": "error",
    "error": "Gemini 429: rate limit", "detail": "",
    "started": "2026-06-05T10:05:00", "completed": "2026-06-05T10:05:02" }
]
```

- `action`: `"transcript"` | `"summary"` | `"delete_source"`.
- `status`: `"ok"` | `"error"`.
- `error`: human-readable reason when `status == "error"`, else `null`.
- `detail`: short success blurb (segment count, duration) when OK.
- `started` / `completed`: ISO-8601 local timestamps.

## Backend changes

1. **`meeting_processor/generation_log.py`** (new) — tiny helper, no class state:
   - `append(meeting_dir: Path, action: str, status: str, *, error: str | None = None, detail: str = "", started: datetime, completed: datetime) -> None`
     — read-or-init the list, append, write back (atomic-ish: write to temp +
     replace). Caps the list to the last ~50 entries.
   - `read(meeting_dir: Path) -> list[dict]` — return entries (newest-first) or
     `[]` if the file is missing/corrupt.

2. **`meeting_processor/pipeline.py`**
   - `_locate_source_file(meeting_dir: Path, source_file: str = "") -> Path | None`
     — build candidate roots `[Path(config.project_root) / "uploads", Path(config.watch_dir)]`.
     (1) If `source_file` is a non-empty exact name, look for that name in each
     root (and accept `source_file` if it is itself an existing path). (2) Else
     derive the stem from `meeting_dir.name` by stripping the leading
     `"YYYY-MM-DD HhMM - "` prefix, and match any file in the roots whose `.stem`
     equals it and whose suffix is in `config.watch_extensions`. Return the first
     match or `None`.
   - `transcribe_existing(meeting_id: str) -> None`:
     - `meeting_dir = config.reunioes_path / meeting_id`; if missing →
       `FileNotFoundError` (surfaced as 404 by the route).
     - Read `source_file` from the Resumo note frontmatter **if present** (reuse
       the web layer's frontmatter parse); transcript-only meetings have none and
       fall back to the folder-stem search above.
     - `started = datetime.now()`. Locate the source via `_locate_source_file`; if
       `None`, append an **error** log entry
       (`"Arquivo de origem não encontrado: <stem-or-name>"`) and return (no
       job/raise — nothing to do).
     - Otherwise build a `ProcessingJob`, run **audio → transcription** only
       (`extract_audio` + `transcriber.transcribe`), then
       `note_generator.write_transcription(transcript, paths_for_existing(meeting_dir))`
       to overwrite the existing `Transcricao - *.md`. Clean up temp audio in a
       `finally` (mirrors `process`).
     - On success: `job.complete(...)` and append an **ok** log entry
       (`detail = "<n> segmentos, <duração>"`).
     - On exception: `job.fail(str(e))`, append an **error** log entry with
       `str(e)`, and re-raise (so the Conversões history also reflects it).
   - **`summarize_existing`** — wrap its body so it appends a `summary` log entry
     (ok/error) to the same per-meeting log, reusing the `started`/`completed`
     timestamps it already has via the job. (Behavior otherwise unchanged.)

3. **`meeting_processor/web/app.py`**
   - `POST /api/meetings/{meeting_id}/transcribe` — mirror `/summarize`:
     - meeting dir missing → `HTTPException(404)`.
     - else spawn a daemon thread running
       `MeetingPipeline(config).transcribe_existing(meeting_id)` (wrapped in
       `try/except logger.exception`), return
       `{"ok": True, "queued": True, "meeting_id": meeting_id}`.
   - `GET /api/meetings/{meeting_id}/log` — return
     `generation_log.read(meeting_dir)`; `404` if the meeting dir is missing,
     `[]` if there is simply no log yet.
   - `GET /api/meetings/{meeting_id}/source` — locate the source via the same
     `_locate_source_file` logic and return
     `{ "exists": bool, "name": str, "path": str, "size": int | null }`
     (`name`/`path`/`size` empty/`null` when not found). `404` if the meeting dir
     is missing. The frontend uses `exists` to enable/disable re-transcribe and
     the delete button.
   - `DELETE /api/meetings/{meeting_id}/source` — locate and delete the source
     file from disk. The vault meeting (transcript/summary) is **not** touched.
     On success: append a `delete_source` **ok** log entry
     (`detail = "<arquivo> (12.4 MB)"`) and return `{ "ok": true, "deleted": true }`.
     If no source is found: append a `delete_source` **error** entry
     (`"Arquivo de origem não encontrado: <name>"`) and return
     `{ "ok": true, "deleted": false }` (idempotent — nothing to delete is not a
     hard error). On an `OSError` while deleting: append an **error** entry with
     `str(e)` and return `{ "ok": false, "error": … }` with `500`. Restricts
     deletion to files under `uploads/` or `watch_dir` (defense: never delete an
     arbitrary path).
   - `POST /api/process` — accept optional `"mode"` in the payload. When
     `mode == "transcript"`, run the pipeline with summary/note/kanban/wiki
     forced off for **this file only** (pass an override into `process`, or call a
     thin `process(path, summary=False)` variant), without touching global config
     `steps`. Default (absent/`"full"`) keeps current behavior.

4. **`meeting_processor/pipeline.py` `process()`** — accept an optional
   `transcript_only: bool = False` (or a `steps_override`) so the transcript-only
   Dashboard run can suppress the summary half without mutating `config`.

## Frontend changes

5. **`api/types.ts`** — add `GenerationLogEntry { action: "transcript" | "summary"
   | "delete_source"; status: "ok" | "error"; error: string | null; detail:
   string; started: string; completed: string | null }` and
   `SourceInfo { exists: boolean; name: string; path: string; size: number | null }`.

6. **`hooks/useApi.ts`**
   - `useTranscribeMeeting()` — POST `/api/meetings/{id}/transcribe`; on success
     invalidate `["status"]`, `["meetings"]`, `["history"]`, and
     `["meeting-log", id]`.
   - `useGenerationLog(id)` — GET `/api/meetings/{id}/log`, `refetchInterval`
     while a run for that meeting is active (poll every ~2s; simplest: always
     poll at 4s when the detail page is open).
   - `useProcessFile()` — extend to accept `{ file, mode }` so the Dashboard can
     pass `mode: "transcript"`.
   - `useMeetingSource(id)` — GET `/api/meetings/{id}/source` (query key
     `["meeting-source", id]`).
   - `useDeleteMeetingSource()` — DELETE `/api/meetings/{id}/source`; on success
     invalidate `["meeting-source", id]` and `["meeting-log", id]`.

7. **`pages/MeetingDetail.tsx`**
   - Header actions row: add **"Gerar transcrição"** and **"Gerar resumo"**
     buttons beside *Markdown / Word / Abrir no Obsidian*. Both always render
     (resumo is no longer gated on empty `resumo_md`). Disable while their
     mutation is pending; toast on trigger ("Gerando transcrição — acompanhe
     abaixo."). **"Gerar transcrição"** is also disabled when
     `useMeetingSource(id)` reports `exists: false`, with a tooltip explaining the
     source file is gone.
   - **"Arquivo de origem"** line (near the header): shows the source name + size
     from `useMeetingSource(id)`, or *"indisponível"* when missing. When present,
     an **"Apagar arquivo de origem"** button opens a `ConfirmDialog`
     ("Apagar o arquivo de origem? A transcrição e o resumo são mantidos, mas não
     será possível gerar a transcrição novamente.") → `useDeleteMeetingSource`.
     Toast on result; the log panel and source line refresh on success.
   - New **"Log de geração"** panel (below the tabs or as a small section under
     the header): renders `useGenerationLog(id)` entries — ✅/❌ icon, action
     label (`Transcrição` / `Resumo`), `detail` on success, `error` on failure,
     and the `completed`/`started` timestamp. Reuse the visual language of
     `ConversionHistory`.

8. **`pages/Meetings.tsx`** — each table row gets two compact icon-buttons
   (re-transcribe + re-summarize) next to the existing trash button, wired to the
   same hooks; toast on trigger; row-level pending state so the clicked icon
   disables.

9. **`pages/Dashboard.tsx`** — add an **"Apenas transcrição (sem resumo)"**
   checkbox to the *"Processar um arquivo"* card. When checked, the
   upload/process actions send `mode: "transcript"`.

## Error handling & feedback

Failures surface in three places: the immediate **toast**, the existing
**Conversões recentes** history, and the new per-meeting **Log de geração** (the
authoritative "why"). The two known failure modes are explicit: source media
missing (`Arquivo de origem não encontrado: …`) and transcription/summary
exceptions (the raw `str(e)`, e.g. provider 429).

## Testing (TDD)

**Backend (`tests/`):**
- `generation_log.append` then `read` round-trips; `read` on a missing file → `[]`;
  corrupt file → `[]` (no raise); list capped at the limit.
- `transcribe_existing` with a **monkeypatched `WhisperTranscriber`** returning a
  canned `Transcript` and a real source file placed in `uploads/`: overwrites
  `Transcricao - *.md`, appends an `ok` `transcript` entry. Cover both location
  paths — a summarized meeting (exact `source_file` from frontmatter) and a
  transcript-only meeting (located by folder-stem match, no frontmatter).
- `transcribe_existing` when the source file is absent: appends an `error` entry
  with `Arquivo de origem não encontrado`, writes no transcript, does not raise.
- `summarize_existing` (existing test still passes) now also appends a `summary`
  log entry.
- `POST /api/meetings/{id}/transcribe`: 404 for a missing meeting; 200 `queued`
  for an existing one (pipeline monkeypatched).
- `GET /api/meetings/{id}/log`: returns appended entries; `[]` when none.
- `GET /api/meetings/{id}/source`: `exists: true` + size when a matching file is
  in `uploads/`; `exists: false` when absent; `404` for a missing meeting.
- `DELETE /api/meetings/{id}/source`: with a file in `uploads/` → removes it from
  disk, leaves the meeting folder intact, appends a `delete_source` ok entry; with
  no source → `deleted: false` + a `delete_source` error entry; refuses a path
  outside `uploads/`/`watch_dir`.
- `POST /api/process` with `mode: "transcript"` runs the pipeline with the
  summary suppressed (pipeline monkeypatched to assert the flag).

**Frontend (`frontend/src/__tests__/`):**
- MeetingDetail: both "Gerar transcrição" and "Gerar resumo" buttons render even
  when `resumo_md` is non-empty; clicking each POSTs to the right endpoint; the
  "Log de geração" panel renders entries from a mocked `/log` response (ok + error
  rows show detail vs. reason). With `source.exists: false`, "Gerar transcrição"
  is disabled and the source line shows "indisponível"; with `exists: true`, the
  "Apagar arquivo de origem" button opens the confirm and DELETEs on confirm.
- Meetings: per-row re-transcribe / re-summarize buttons render and POST to the
  right endpoints.
- Dashboard: checking "Apenas transcrição" makes the process call include
  `mode: "transcript"`.

## Out of scope

- Updating the meeting's stored duration/metadata after a re-transcription (only
  the transcript file is overwritten; the Resumo note frontmatter is left as-is —
  regenerate the summary to refresh it).
- A global (cross-meeting) generation-log view — the log is per-meeting by design.
- Storing the full source path going forward / fixing historical meetings that
  have no `source_file`.
- Live in-place refresh of the transcript text on the detail page mid-run (the
  log panel polls; the transcript tab refreshes on the next meeting fetch).
