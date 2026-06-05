# Auto-start Ollama on Local Processing

**Date:** 2026-06-05
**Status:** Approved design

## Goal

When a meeting is processed/summarized with provider `local`, automatically
start the Ollama server (`ollama serve`) if it isn't already running — so the
user doesn't have to start it by hand. Scope: only at processing time.

## Backend

1. **`meeting_processor/ollama_service.py`** (new):
   - `is_running(base_url) -> bool`: `GET {base}/api/tags` (httpx, ~1.5s timeout);
     True iff 200, else False (any error).
   - `ensure_running(config, timeout=15.0) -> bool`:
     - if `is_running` → True (no spawn).
     - else find `ollama` via `shutil.which`; if missing → log a warning
       (install/`ollama serve` hint) and return False.
     - else `subprocess.Popen(["ollama","serve"], DEVNULL, start_new_session=True)`
       (detached, no shell); poll `is_running` until timeout; return True when up,
       else log warning + False.

2. **`meeting_processor/pipeline.py`** — in `_summarize`, when `steps["summary"]`
   and `config.llm_provider` is `local`/`ollama`, call
   `ollama_service.ensure_running(config)` **before** instantiating/calling the
   summarizer. Covers both normal processing and "Gerar resumo". Failure to start
   doesn't crash the pipeline — the summarizer's connection error surfaces in the
   Conversões history as before.

## Testing (TDD, `tests/test_ollama_service.py`)

- `is_running`: httpx.get 200 → True; raising → False (monkeypatched).
- `ensure_running` already up (is_running True) → True, `subprocess.Popen` never
  called.
- `ensure_running` with `ollama` missing (`shutil.which` None) → False, no spawn.
- `ensure_running` starts it: is_running False then True, `shutil.which` returns a
  path, `Popen` monkeypatched/recorded → True and Popen called once.
- pipeline: `summarize_existing` with `config.llm_provider="local"` and a mocked
  summarizer calls `ensure_running` (monkeypatched to record).

## Out of scope

- Auto-start when opening Settings / on server boot (only at processing).
- Stopping Ollama afterwards; managing the Ollama process lifecycle.
- Installing Ollama (only starts an installed binary).
