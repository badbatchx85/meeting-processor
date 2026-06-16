# Speaker Renaming (sub-project A)

**Date:** 2026-06-16
**Status:** Approved design

## Goal

Let the user rename diarization labels (`Falante 1 → Ana`) per meeting. Saving
rewrites the transcript `.md` (so Obsidian + web show real names) and re-generated
summaries pick up the names — while preserving the **original** labels in the
segment sidecar (the hook sub-project B / voice ID will enroll voiceprints
against). First of two cycles; B (voice ID + a repository of known voices) builds
on the `speakers.json` map this produces.

## Background (exact, from exploration)

- `diarizer.assign_speakers` sets `seg.speaker = "Falante N"`; `display_text`
  renders `"{speaker}: {text}"`.
- `note_generator.write_transcription(transcript, paths)`:
  `_write_raw_transcription(transcript, paths.raw_path)` writes the `.md`
  (`# Transcricao` + `**[MM:SS]** {seg.display_text}  ` lines), then writes the
  sidecar `paths.raw_path.with_suffix(".words.json")` = `[s.model_dump() for s in
  segments]` **only when `any(s.words ...)`**. `model_dump()` includes `speaker`.
- `read_transcription(path)` reconstructs a `Transcript` from the `.md` (used by
  `summarize_existing`).
- The meeting-detail endpoint (`web/app.py`) reads `Transcricao - *.md` fresh per
  request → returns `"transcricao_md"`. `GET /api/meetings/{id}/words` globs
  `Transcricao - *.words.json`, `json.loads`, returns the segment list.
- Frontend `MeetingDetail` has `useMeeting`, `useMeetingWords`, renders
  `<TranscriptPlayer meetingId markdown={d.transcricao_md} words={words.data} …>`.

## 1. Broaden the segment sidecar (`note_generator.py`)

Change the sidecar gate so any **diarized** meeting (faster OR openai backend)
gets the sidecar, not only word-timestamped ones:

```python
        if any(s.words or s.speaker for s in transcript.segments):
            words_path = paths.raw_path.with_suffix(".words.json")
            write_json_atomic(words_path, [s.model_dump() for s in transcript.segments])
```

The sidecar holds the **original** `speaker` labels and is the canonical
per-segment store. It is **never** name-rewritten.

## 2. `speaker_names.py` (new module)

```python
def names_path(meeting_dir: Path) -> Path        # meeting_dir / "speakers.json"
def read_names(meeting_dir) -> dict[str, str]    # {} if absent / unreadable
def write_names(meeting_dir, names: dict) -> None # write_json_atomic
def _segments_sidecar(meeting_dir) -> Path | None # first "Transcricao - *.words.json"
def detected_labels(meeting_dir) -> list[str]     # distinct non-null seg["speaker"] from the sidecar, in first-appearance order
def apply_names(segments: list[dict], names: dict) -> list[dict]
    # returns copies with seg["speaker"] mapped (names.get(label) or label); used by /words
def regenerate_md(config, meeting_dir, names) -> None
    # read the sidecar, build TranscriptSegments with speaker = (names.get(orig) or orig),
    # build a Transcript, write the .md via NoteGenerator(config)._write_raw_transcription.
    # IDEMPOTENT: the map is ALWAYS keyed by the original label (e.g. {"Falante 1": "Ana"});
    # regeneration applies it to the ORIGINAL sidecar labels each time, so a re-rename is just
    # changing that key's value ({"Falante 1": "Carlos"}) — names never accumulate or
    # double-prefix, and the sidecar is never touched.
```

`regenerate_md` reuses the existing `.md` renderer (build `TranscriptSegment(start,
end, text, speaker=mapped, words=...)` from the sidecar dicts → `Transcript` →
`_write_raw_transcription`). Finds the `.md` via the same glob the endpoint uses.

## 3. Endpoints (`web/app.py`)

- `GET /api/meetings/{id}/speakers` → `{"detected": detected_labels(dir),
  "names": read_names(dir)}` (validate via `_reunioes_dir`, 404 if no meeting).
  `detected` always lists the **original** labels (from the untouched sidecar), so
  the UI keeps working across re-renames.
- `POST /api/meetings/{id}/speakers` body `{names: {...}}` →
  `write_names(dir, names)` then `regenerate_md(config, dir, names)`; return
  `{ok: true}`. Empty/blank values in `names` are dropped (a label with no name
  stays `Falante N`).
- `GET …/words`: apply the map to the served segments —
  `return apply_names(json.loads(sidecar), read_names(dir))` — so the web
  word-level player shows names (the sidecar itself keeps originals). The `.md`
  path needs no apply (POST already rewrote it).

`summarize_existing` is unchanged: it reads the rewritten `.md` → re-generated
summaries use real names automatically.

## 4. Frontend

- `api/types.ts`: `SpeakerInfo { detected: string[]; names: Record<string,string> }`.
- `hooks/useApi.ts`: `useMeetingSpeakers(id)` (GET, queryKey `["meeting-speakers", id]`)
  + `useSetSpeakerNames()` (POST `{names}`, on success invalidate
  `["meeting", id]`, `["meeting-words", id]`, `["meeting-speakers", id]`).
- A `SpeakerNames` panel (new component) in the transcript tab, above the player:
  one row per `detected` label, a text input pre-filled with `names[label] ?? ""`
  (placeholder = the label), a "Salvar nomes" button → `setNames.mutate({names})`.
  Renders nothing when `detected` is empty (no diarization). After save, the
  invalidations re-fetch the transcript/words → names appear.

## Testing (TDD)

`tests/test_speaker_renaming.py`:
- **sidecar gate**: a transcript with `speaker` set but `words=None` → `.words.json`
  is now written (regression guard for the broadened gate; words-only still works).
- **`speaker_names`**: `read_names`/`write_names` round-trip; `detected_labels` from a
  seeded sidecar (distinct, first-appearance order); `apply_names` maps + passes through.
- **`regenerate_md` idempotent**: seed a sidecar (`Falante 1`/`Falante 2`); apply
  `{Falante 1: Ana}` → `.md` shows `**[..]** Ana: …` and keeps `Falante 2`; the
  sidecar is unchanged; applying `{Falante 1: Carlos}` next → `.md` shows `Carlos`
  (no `Ana`, no double-prefix).
- **endpoints** (`client`): `GET /speakers` returns detected+names; `POST` persists
  + rewrites the `.md` (read it back → names); `GET …/words` returns names-applied
  segments while the on-disk sidecar still has originals.

`frontend/src/__tests__/speakerNames.test.tsx`:
- the panel renders a row per detected label seeded from the speakers query; editing
  + "Salvar nomes" POSTs `{names: {...}}`; renders nothing when `detected` is empty.

## Out of scope

- **Voice ID / voiceprints / known-voices repository** → sub-project B (it enrolls
  voiceprints keyed by the sidecar's original `Falante N` labels + this
  `speakers.json` map).
- Re-renaming meetings transcribed **before** this feature that lack the segment
  sidecar (re-process to get one). New/diarized meetings are covered by §1.
- Changing how NEW (first-pass) summaries label speakers (they use `Falante N`
  until you rename + re-summarize).
- Per-vault global names (each meeting's map is independent in A; B introduces the
  cross-meeting roster).
