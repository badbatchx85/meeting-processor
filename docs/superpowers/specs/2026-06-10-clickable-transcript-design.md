# Click-to-Seek Transcript (web)

**Date:** 2026-06-10
**Status:** Approved design

## Goal

In the web app's meeting detail "Transcrição" tab, turn the existing
`**[MM:SS]** texto` timestamps into clickable markers that seek an inline
media player to that moment. Dependency-free; degrades to the current plain
transcript when the source recording is unavailable. Second piece of the
"who-said-what / who-owes-what" spine (playback half).

## Background (exact, from exploration)

- `locate_source_file(config, meeting_dir) -> Path | None`
  (`meeting_processor/pipeline.py`) finds the source recording by matching the
  meeting folder's stem against `uploads/` + `watch_dir` with a watched
  extension. The existing `GET /api/meetings/{id}/source` handler
  (`web/app.py:1270`) already uses it and returns
  `{exists, name, path, size}`.
- **Starlette 1.2.1's `FileResponse` is range-aware** (verified) — returning
  `FileResponse(path)` honors a `Range` request with `206 Partial Content` +
  `Content-Range`, so the browser streams and seeks a large file without
  loading it whole. No manual range handling needed.
- The transcript note (`Transcricao - *.md`, surfaced as `d.transcricao_md`)
  starts with `# Transcricao` and has one `**[MM:SS]** texto` line per segment.
- Frontend transcript tab today (`MeetingDetail.tsx:186`):
  `{tab === "transcript" && <MarkdownView>{d.transcricao_md}</MarkdownView>}`.
  `MeetingDetail` already calls `useMeetingSource(id)` (→ `source.data.exists`).

## 1. Backend — media-streaming endpoint

`GET /api/meetings/{meeting_id}/media` in `web/app.py`, placed next to
`api_meeting_source`:

```python
@app.get("/api/meetings/{meeting_id}/media")
async def api_meeting_media(meeting_id: str):
    meeting_dir = _reunioes_dir(config.vault_path, meeting_id)
    if meeting_dir is None or not meeting_dir.is_dir():
        raise HTTPException(status_code=404, detail="Reunião não encontrada")
    from ..pipeline import locate_source_file
    src = locate_source_file(config, meeting_dir)
    if src is None or not src.is_file():
        raise HTTPException(status_code=404, detail="Arquivo de origem indisponível")
    return FileResponse(src)
```

`FileResponse` is imported from `fastapi.responses` (or `starlette.responses`).
It sets `Content-Type` from the file suffix and serves `Range` requests as
`206`. Mirrors the validation pattern of `api_meeting_source` (uses
`_reunioes_dir`). No new dependency.

## 2. Frontend — `TranscriptPlayer` component

**New** `frontend/src/components/TranscriptPlayer.tsx`:
`TranscriptPlayer({ meetingId, markdown, hasSource })`.

- **Parse** `markdown` into segments with a module helper
  `parseTranscript(md: string): { seconds: number; label: string; text: string }[]`:
  for each line matching `^\*\*\[(\d{1,2}:\d{2}(?::\d{2})?)\]\*\*\s*(.*)$`, convert
  the `MM:SS`/`HH:MM:SS` label to `seconds` and capture the text. Non-matching
  lines (the `# Transcricao` header, blanks) are ignored. Exported for unit
  testing.
- **Fallback:** if `!hasSource` **or** `parseTranscript(markdown).length === 0`,
  render `<MarkdownView>{markdown}</MarkdownView>` (today's behavior) and nothing
  else.
- **Otherwise** render:
  - a `<video ref controls preload="metadata" src={/api/meetings/${encodeURIComponent(meetingId)}/media}>`
    (a `<video>` element plays audio-only sources too — shows just the controls
    bar);
  - a scrollable list; each segment is a row with a `[label]` `<button>` that on
    click sets `videoRef.current.currentTime = seg.seconds` then `.play()`, plus
    the segment text. The button has an accessible name including the label
    (e.g. `aria-label={`Ir para ${seg.label}`}`).
  - The row whose segment is currently playing (the last segment whose
    `seconds <= video.currentTime`) gets a subtle highlight class, updated via a
    `timeupdate` listener + local state.

**Wire `MeetingDetail.tsx`:** replace the transcript-tab line with
`{tab === "transcript" && <TranscriptPlayer meetingId={id} markdown={d.transcricao_md} hasSource={source.data?.exists ?? false} />}`.
Import the component.

## 3. Decisions (no API/data change)

- Timestamps already live in `transcricao_md` → **client-side parse**; the
  stored transcript format is untouched.
- One `<video>` element for both video and audio sources.
- The interactive view replaces the plain one only when a source exists and the
  transcript has timestamps; otherwise the plain `MarkdownView` renders.

## Testing (TDD)

**Backend (`tests/`):** for a seeded meeting with a fake source file in
`uploads/` (matching the folder stem + a watched extension):
- `GET /api/meetings/{id}/media` → `200`, body equals the file bytes,
  `accept-ranges: bytes` header present.
- `Range: bytes=0-3` → `206` with `Content-Range: bytes 0-3/<size>` and the first
  4 bytes.
- No source file → `404`.

**Frontend (Vitest, `frontend/src/__tests__/`):**
- `parseTranscript`: `"# Transcricao\n\n**[00:05]** oi\n**[01:09]** tchau"` →
  `[{seconds:5,label:"00:05",text:"oi"},{seconds:69,label:"01:09",text:"tchau"}]`;
  `"01:02:03"` → `3723`; a string with no timestamp lines → `[]`.
- `TranscriptPlayer` with `hasSource` + timestamped markdown: renders a
  `<video>` and a button named `/Ir para 00:05/`; clicking it sets the media
  element's `currentTime` to `5` (mock `HTMLMediaElement.prototype.play` and
  spy on `currentTime`).
- `TranscriptPlayer` with `hasSource=false`: renders the transcript text, no
  `<video>` element.

## Out of scope

- Per-word highlighting / karaoke.
- An Obsidian-side clickable transcript (the source isn't in the vault).
- A custom scrubber/waveform beyond the native `<video controls>`.
- Changing the stored transcript markdown format or adding structured segment
  data to the meeting API.
- Auth/streaming hardening beyond `locate_source_file`'s existing roots.
