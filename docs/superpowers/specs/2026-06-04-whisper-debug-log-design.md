# Whisper Debug Logging

**Date:** 2026-06-04
**Status:** Approved design

## Goal

Make Whisper transcription failures understandable. Today `whisper.load_model()`
and `model.transcribe()` (openai-whisper backend) have no `try/except`, so a
failure propagates to the pipeline's generic `job.fail(str(e))` with **no
traceback in any log** and **no record of what ran** (model/device/language).
The whisper.cpp backend logs stderr but truncated to 200–500 chars.

Add diagnostic logging around the Whisper run: a dedicated always-on
`whisper-debug.log` with full per-run detail, plus full tracebacks in the
existing `meeting_processor.log` so errors are visible by default.

## Architecture

A dedicated diagnostics logger writes `whisper-debug.log` at the project root,
always at DEBUG, with its own `FileHandler` and `propagate=False` (never spams
the console nor double-writes the main log), independent of the global
`config.log_level`. On any failure the full traceback + run context is logged to
**both** that file and the existing module `logger` (→ `meeting_processor.log` +
console). One shared helper is used by both backends (DRY). All changes live in
`meeting_processor/transcriber.py`.

## Component changes (`meeting_processor/transcriber.py`)

1. **`_debug_logger(config) -> logging.Logger`**
   - Logger name `"meeting_processor.whisper_debug"`, level DEBUG,
     `propagate = False`.
   - Target path `Path(config.project_root) / "whisper-debug.log"`.
   - Idempotent: if the logger already has a `FileHandler` whose `baseFilename`
     equals the absolute target path, reuse it; otherwise remove existing
     handlers (close them) and add a fresh `FileHandler(path, encoding="utf-8")`
     with formatter `"%(asctime)s [%(levelname)s] %(message)s"` /
     `"%Y-%m-%d %H:%M:%S"`. This keeps one handler pointing at the current path
     (test-safe across differing `project_root`s; no duplicate lines in prod).

2. **`_log_run_failure(config, backend, context, exc) -> None`**
   - `dbg = _debug_logger(config)`;
     `dbg.error("FALHA backend=%s contexto=%s", backend, context, exc_info=exc)`.
   - `logger.error("Whisper falhou (backend=%s): %s", backend, exc, exc_info=exc)`
     — ensures the traceback also lands in `meeting_processor.log`.
   - `context` is a small dict (e.g. `{"model": ..., "audio": ..., "language": ...}`).

3. **Wrap each backend's core in `try/except → _log_run_failure(...) → raise`:**

   - **`_transcribe_openai`:**
     - Before load: `dbg.debug("Início openai-whisper: model=%s lang=%s audio=%s (%.1f MB) initial_prompt=%s", ...)` and an informational line that the model may download to `~/.cache/whisper` and can take a while if not cached.
     - Time `whisper.load_model(...)`: `dbg.debug("Modelo carregado em %.1fs (device=%s)", elapsed, getattr(model, "device", "?"))`.
     - Time `model.transcribe(...)`: `dbg.debug("Transcrição concluída em %.1fs: %d segmentos", elapsed, len(segments))`.
     - Wrap the load+transcribe block; on `Exception` call `_log_run_failure(self.config, "openai", {...}, e)` then `raise`. The existing `ImportError → RuntimeError` guard stays as-is (outside the timed block).

   - **`_transcribe_cpp`:**
     - `dbg.debug("Início whisper.cpp: cmd=%s", " ".join(cmd))`.
     - Time the `subprocess.run`; on success `dbg.debug("whisper.cpp ok em %.1fs (rc=%d), stderr=%s", elapsed, rc, stderr)` (full stderr, not truncated).
     - On `subprocess.CalledProcessError`: call `_log_run_failure(self.config, "cpp", {"cmd": ..., "returncode": e.returncode}, e)` (logs full `e.stderr`), then raise `RuntimeError` as today (the user-facing message may stay truncated; the log keeps the full text).
     - Keep the existing JSON-parse fallback; if it raises, that also flows through a wrapping `try/except` to `_log_run_failure`.

## Behavior / levels

- Success → verbose play-by-play only in `whisper-debug.log`; `meeting_processor.log` keeps its current INFO lines unchanged.
- Failure → full traceback + context in **both** logs.
- `whisper-debug.log` is a runtime artifact → add to `.gitignore`.

## Concurrency note

Transcriptions run one at a time (sequential pipeline; the watcher processes one
file at a time), so the single shared dedicated logger is safe. The idempotent
handler check avoids churn on repeated runs to the same path.

## Testing (TDD, pytest — `tests/test_whisper_debug.py`)

- `test_debug_logger_writes_to_project_root`: `_debug_logger(cfg)` (cfg.project_root = tmp) returns a logger with exactly one `FileHandler` whose path is `tmp/whisper-debug.log`.
- `test_debug_logger_idempotent`: calling `_debug_logger(cfg)` twice with the same cfg yields one handler (no duplicates); a cfg with a new `project_root` re-points to the new file.
- `test_log_run_failure_writes_traceback_and_context`: raise a `ValueError("boom")`, call `_log_run_failure(cfg, "openai", {"model": "base"}, exc)`; assert `whisper-debug.log` contains `"FALHA"`, `"openai"`, `"base"`, and a `"Traceback"` block (full exc_info).
- `test_log_run_failure_also_hits_main_logger`: use pytest `caplog` to assert the module `logger` recorded an ERROR mentioning the backend with exception info.

## Out of scope

- Live model-download progress bar (terminal widget; needs stream hooking).
- The SPA processing stepper (separate parked spec).
- Changing the whisper.cpp command flags or JSON parsing beyond logging.
- Routing whisper's own internal library logger/warnings into the file.
