# Reliability Hardening Bundle

**Date:** 2026-06-09
**Status:** Approved design

## Goal

Make the job-processing layer robust against the failure modes a parallel
code review surfaced: corrupt history on crash, two Whisper models racing to
OOM the machine, a "cancel" that doesn't stop work, and opaque mid-run disk
failures. Four interlocking fixes, scoped to the **web process** (the watcher
runs in its own process; atomic writes keep the shared history file safe
regardless).

## Background (current behavior)

- `Dashboard` is created **per `MeetingPipeline`** (`pipeline.py` `__init__`),
  and `_save_history` (`dashboard.py:177-198`) writes its whole in-memory list
  with `history_path.write_text(...)` — **non-atomic** and with **no dedup** by
  `(file, started)`. A crash mid-write corrupts `.processing-history.json`;
  `_load_history_data` then returns `None`, losing all history.
- Job endpoints fire `threading.Thread(target=_run, daemon=True).start()`
  immediately (`app.py` ~1067/1225/1505 and `_process_path_async`). N
  simultaneous submissions ⇒ N Whisper + LLM runs against one history file.
- `_cancel_active_job` (`app.py`) only edits the history entry; the thread keeps
  running (documented: "Não tenta matar a thread").

## Components

### 1. Atomic history writes (S)

Add to `meeting_processor/utils.py`:

```python
def write_json_atomic(path, data) -> None:
    """Grava JSON de forma atômica: escreve em .tmp e faz os.replace()."""
```

It `mkdir`s the parent, writes `path.with_suffix(path.suffix + ".tmp")` with
`json.dumps(..., ensure_ascii=False, indent=2)`, then `os.replace(tmp, path)`
(atomic same-filesystem rename on POSIX/Windows). Used by:
- `Dashboard._save_history` (`dashboard.py:195`) — replace the inline
  `write_text` with `write_json_atomic(self.history_path, entries)`.
- The web layer's `_write_history_data` (`app.py`) — replace its inline
  `write_text` with `write_json_atomic(...)`.

### 2. Single-slot job queue (S)

- New config field `max_concurrent_jobs: int = 1` (`config.py`), env
  `MEETING_MAX_CONCURRENT_JOBS` via the existing `int_overrides` map.
- In `create_app`'s `lifespan`, create a module/app-scoped
  `ThreadPoolExecutor(max_workers=config.max_concurrent_jobs)` and shut it down
  on exit (`executor.shutdown(wait=False, cancel_futures=True)`).
- The four job entry points submit to it instead of starting raw threads:
  `/api/process`, `/api/process/upload`, `/api/meetings/{id}/summarize`,
  `/api/meetings/{id}/transcribe` (and the shared `_process_path_async`).
  `future = executor.submit(_run)`.
- With `max_workers=1`, jobs run one at a time; extra submissions queue. Log
  `"Job enfileirado: %s"` when a submission is made while the worker is busy
  (best-effort: log at submit time).

### 3. Cooperative cancel (M)

- New `meeting_processor/cancellation.py` (or a small registry in `app.py`):
  a `JobCancelled(Exception)` plus a process-wide `CancelRegistry` mapping
  `(file, started_iso) -> (Future, threading.Event)`, with `register`,
  `lookup`, and `discard` (called on job completion).
- The submit wrapper, for each job: generate `started = datetime.now()` and an
  `Event`; register `(file, started.isoformat()) -> (future, event)`; pass
  **both** `started` and `event` into the pipeline call.
- `Dashboard.new_job(source_file, started_at=None)` gains the optional
  `started_at` so the submit-side `(file, started)` identity equals the
  pipeline-side job's identity exactly.
- `MeetingPipeline.process(...)`, `summarize_existing(...)`, and
  `transcribe_existing(...)` accept an optional `cancel_event: threading.Event`
  and a `job_started: datetime` (threaded to `new_job`). They call a helper
  `_check_cancel(cancel_event)` that, if the event is set, raises
  `JobCancelled("Cancelado pelo usuário.")` at each stage boundary (after audio,
  after transcription, after summary). `JobCancelled` subclasses `Exception`, so
  the existing `except Exception` in `process()` catches it and calls
  `job.fail("Cancelado pelo usuário.")` — same path as any failure.
- The cancel endpoint (`/api/process/cancel`): look up `(file, started)` in the
  registry. If the future is still queued → `future.cancel()`. If running →
  `event.set()`. Then call the existing `_cancel_active_job` to mark history
  (atomic write via #1). On job completion the wrapper `discard`s the registry
  entry.
- Whisper is not interrupted mid-segment; cancellation lands at the next stage
  boundary. Audio extraction (ffmpeg subprocess) is not force-killed in this
  bundle (noted follow-up).

### 4. Disk-space preflight (S)

At the top of `MeetingPipeline.process()` (inside the `try`, before
`extract_audio`): compute `free = shutil.disk_usage(check_dir).free` and
`need = video_path.stat().st_size * 3`; if `free < need`, **raise
`RuntimeError("Espaço em disco insuficiente: ~{need_gb:.1f} GB necessários,
{free_gb:.1f} GB livres.")`**. The existing `except Exception` in `process()`
already calls `job.fail(str(e))` and re-raises, so the job ends with the readable
message in history — no double-marking, consistent with every other stage
failure. `check_dir` is `config.temp_dir` if it exists, else `config.project_root`
(temp_dir may not be created yet).

## Out of scope (follow-ups)

- **Queued-job visibility** (rendering "waiting" entries before a job starts) —
  needs a shared/singleton `Dashboard` instead of per-pipeline instances.
- **Cross-process serialization** with the watcher subprocess (web-process scope
  was chosen; atomic writes still prevent corruption).
- Force-killing the ffmpeg/Whisper subprocess on cancel.
- Retry/resume of failed stages.

## Testing (TDD, no real audio/LLM/network)

- **`write_json_atomic`**: writes valid JSON; a monkeypatched `os.replace` that
  raises leaves the original file intact (no partial corruption); round-trips a
  dict/list.
- **Queue serialization**: submit two jobs whose `_run` increments a shared
  "currently running" counter and asserts it never exceeds 1 (using a barrier /
  sleep-free Event), with `max_workers=1`.
- **Cancel — running**: build a `MeetingPipeline` with monkeypatched stage
  functions; set the `cancel_event` before the transcription checkpoint; assert
  `process()` raises/handles `JobCancelled` and the job is marked `error` with
  "Cancelado". **Cancel — queued**: a submitted-but-not-started `future.cancel()`
  returns True and the job never runs.
- **Disk preflight**: monkeypatch `shutil.disk_usage` to report low free space →
  `process()` ends with `job.fail("Espaço em disco insuficiente…")` and
  `extract_audio` is never called (asserted via a monkeypatched spy).
- **Regression**: existing `tests/test_stuck_jobs.py` (reconcile + cancel +
  pipeline) and the full suite stay green; `MEETING_MAX_CONCURRENT_JOBS` default
  1 and `cancel_event=None`/`job_started=None` defaults keep all current call
  sites behaving identically.
