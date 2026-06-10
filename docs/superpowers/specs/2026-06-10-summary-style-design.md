# Summary Style: time-windowed vs plain

**Date:** 2026-06-10
**Status:** Approved design

## Goal

Let the user choose between the current **time-windowed** summary (per-block
"Resumo por Período") and a **plain** summary (no time blocks). A global default
in Settings plus a per-summarization choice on the meeting detail's "Gerar
resumo".

## Background (exact, from exploration)

- `note_generator.py:234` already renders the time section conditionally:
  `if summary.time_windows: body_parts.append("## Resumo por Periodo\n") ...`.
  So an empty `time_windows` ⇒ no section, no note change needed.
- `_BaseSummarizer.summarize(self, transcript, source_filename)`
  (`summarizer.py`) builds `system_prompt = SYSTEM_PROMPT.replace("{chunk_minutes}", ...)`
  then either runs single-pass or calls
  `_map_reduce_summarize(transcript, source_filename, system_prompt)` — so a
  directive appended to `system_prompt` reaches both paths and every chunk.
  `REDUCE_SYSTEM_PROMPT` does not include `time_windows`, so reduce is unaffected.
- Pipeline: `process()` → `_summarize(self, transcript, paths, source_file,
  created_at, job, steps)` → the summarizer's `.summarize(...)`. The manual path
  `summarize_existing(meeting_id, job_started=None, cancel_event=None)` also goes
  through `_summarize`.
- The "Gerar resumo" UI calls `POST /api/meetings/{id}/summarize` →
  `summarize_existing`. The hook `useSummarizeMeeting()` posts `id`.

## 1. Config

`Settings.summary_style: str = "timeline"` (values `"timeline"` | `"plain"`).
Env `MEETING_SUMMARY_STYLE` in `string_overrides`. Default `"timeline"` =
current behavior. Any value other than `"plain"` is treated as `"timeline"`
(no hard validation needed; the directive only fires on exactly `"plain"`).

## 2. Summarizer behavior (`summarizer.py`)

Change the signature to
`summarize(self, transcript, source_filename, style: str | None = None)`. At the
top: `effective = (style or self.config.summary_style or "timeline")`. After
building `system_prompt`, if `effective == "plain"`, append:

```python
        if effective == "plain":
            system_prompt += (
                "\n\nMODO RESUMO SIMPLES: NÃO segmente o resumo por blocos de "
                'tempo — retorne "time_windows": [] (lista vazia).'
            )
```

This single change covers single-pass and map-reduce (the directive is in
`system_prompt`, already threaded into `_map_reduce_summarize`). When `plain`,
the model returns empty `time_windows`, which the note already omits.

## 3. Pipeline threading (`pipeline.py`)

- `_summarize(self, transcript, paths, source_file, created_at, job, steps, style=None)`
  — add the `style` param; pass it to `self.summarizer.summarize(transcript,
  source_file, style=style)`.
- `process()` calls `_summarize(...)` with no `style` → `None` → the summarizer
  uses `config.summary_style` (global default). Auto-ingest unchanged.
- `summarize_existing(self, meeting_id, job_started=None, cancel_event=None,
  style=None)` — add `style`; pass it to its `_summarize(..., style=style)` call.

## 4. Backend (`web/app.py` + `web/runtime.py`)

- `set_summary_style(config, style) -> dict` in `runtime.py`: normalize to
  `"plain"` if `style == "plain"` else `"timeline"`; `persist_env_setting(root,
  "MEETING_SUMMARY_STYLE", value)`; `config.summary_style = value`;
  `return {"ok": True, "summary_style": value}`. Mirrors `set_watch_dir`.
- `api_get_config` (`/api/config` GET): add `"summary_style": config.summary_style`.
- `POST /api/config/summary-style` (`{style}`): calls `set_summary_style`.
- `POST /api/meetings/{meeting_id}/summarize`: read an optional `style` from the
  JSON body (`(payload or {}).get("style")`), pass it into the
  `summarize_existing(meeting_id, ..., style=style)` lambda submitted to the job
  executor. (The endpoint currently takes no body; accept an optional `payload:
  dict | None = Body(default=None)`.)

## 5. Frontend

- **Type** (`api/types.ts`): `Config` gains `summary_style: string`.
- **Hooks** (`hooks/useApi.ts`):
  - `useSetSummaryStyle()` → POST `/api/config/summary-style` `{style}`,
    invalidate `["config"]`.
  - `useSummarizeMeeting()` mutationFn changes to accept
    `{ id: string; style?: string }` and POST `{style}` to the summarize
    endpoint (keep the existing `onSuccess` invalidations, keyed off `id`).
- **Settings page:** an "Estilo do resumo" control (two radios / a select):
  *Com períodos* (`timeline`) / *Resumo simples* (`plain`), seeded from
  `config.summary_style`, saved via `useSetSummaryStyle`.
- **MeetingDetail page:** a small `<select aria-label="Estilo do resumo">` next
  to "Gerar resumo", seeded from `config.summary_style` via `useConfig`
  (defaulting `"timeline"`); the existing summary button passes the selected
  value: `summarize.mutate({ id, style })`.

## Testing (TDD)

**Python (`tests/`):**
- `summarize(style="plain")` → the captured `system_prompt` contains
  "MODO RESUMO SIMPLES"; `style="timeline"`/default → it does not. Use a
  `FakeSummarizer(_BaseSummarizer)` that records the `system_prompt` passed to
  `_call_llm` and returns a canned JSON; with `plain`, a response carrying
  `time_windows` is still parsed, but the directive presence is what's asserted.
- `summarize` with `style=None` uses `config.summary_style` (set
  `config.summary_style="plain"` → directive present).
- `set_summary_style` round-trips (`config.summary_style` updated; normalizes a
  garbage value to `"timeline"`).
- `/api/config` GET includes `summary_style`; `POST /api/config/summary-style`
  `{style:"plain"}` then GET reflects `"plain"`.
- `POST /api/meetings/{id}/summarize` `{style:"plain"}` → `summarize_existing`
  receives `style="plain"` (monkeypatch `MeetingPipeline.summarize_existing` to
  capture kwargs; assert the endpoint returns `queued`).

**Frontend (Vitest):**
- Settings: the "Estilo do resumo" control renders seeded from
  `config.summary_style` and POSTs `/api/config/summary-style` on change/save.
- MeetingDetail: the style `<select>` renders; clicking "Gerar resumo" POSTs
  `{style}` matching the selection to the summarize endpoint.

## Out of scope

- Additional styles (bullet-only, exec-only, etc.).
- Changing what the `timeline` style produces.
- Persisting the per-meeting chosen style (it's a one-shot choice at summarize
  time; the global default persists).
- Speaker attribution (the next spine piece).
