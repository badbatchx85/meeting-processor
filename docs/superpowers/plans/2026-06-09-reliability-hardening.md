# Reliability Hardening Bundle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make job processing crash-safe (atomic history writes), OOM-safe (single-slot queue), genuinely cancellable (cooperative cancel), and fail-fast on low disk.

**Architecture:** A `write_json_atomic` util used by both history writers; a single-worker `ThreadPoolExecutor` all web job endpoints submit to via a `_submit_job` helper; a `CancelRegistry` (`(file, started) → (Future, Event)`) plus `JobCancelled` checked at pipeline stage boundaries; a `shutil.disk_usage` preflight.

**Tech Stack:** Python 3.14, FastAPI, Pydantic, `concurrent.futures`, `threading`, pytest.

Run tests with `.venv/bin/python -m pytest`. The pre-existing `test_summarizer_mock.py::test_factory_selects_anthropic` failure (no `ANTHROPIC_API_KEY`) is unrelated — ignore it.

---

## File Structure
- **Modify** `meeting_processor/utils.py` — add `write_json_atomic`.
- **Modify** `meeting_processor/dashboard.py` — `_save_history` uses it; `new_job` gains `started_at`.
- **Modify** `meeting_processor/web/app.py` — `_write_history_data` uses it; executor + `_submit_job`; rewire 5 job sites + the cancel endpoint.
- **Modify** `meeting_processor/pipeline.py` — disk preflight; `job_started`/`cancel_event` params + `_check_cancel`.
- **Modify** `meeting_processor/config.py` — `max_concurrent_jobs`.
- **Create** `meeting_processor/job_control.py` — `JobCancelled`, `CancelRegistry`.
- **Create** `tests/test_reliability.py`.

---

### Task 1: Atomic JSON writes

**Files:** Modify `meeting_processor/utils.py`, `meeting_processor/dashboard.py:195`, `meeting_processor/web/app.py:408`; Create `tests/test_reliability.py`.

- [ ] **Step 1: Write the failing test** — create `tests/test_reliability.py`:

```python
"""Reliability bundle: atomic writes, job queue, cooperative cancel, disk preflight."""
import json
from pathlib import Path

import pytest

from meeting_processor.utils import write_json_atomic


def test_write_json_atomic_writes_and_roundtrips(tmp_path):
    p = tmp_path / "sub" / "data.json"
    write_json_atomic(p, [{"a": 1}, {"b": "ç"}])
    assert json.loads(p.read_text(encoding="utf-8")) == [{"a": 1}, {"b": "ç"}]
    assert not p.with_suffix(p.suffix + ".tmp").exists()   # tmp cleaned up


def test_write_json_atomic_failure_keeps_original(tmp_path, monkeypatch):
    p = tmp_path / "data.json"
    write_json_atomic(p, {"v": 1})                          # original good content
    import meeting_processor.utils as u
    monkeypatch.setattr(u.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("boom")))
    with pytest.raises(OSError):
        write_json_atomic(p, {"v": 2})
    assert json.loads(p.read_text(encoding="utf-8")) == {"v": 1}   # untouched
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_reliability.py -q`
Expected: FAIL — `cannot import name 'write_json_atomic'`.

- [ ] **Step 3: Implement** — add to `meeting_processor/utils.py` (ensure `import json`, `import os` at the top of that file; add them if missing):

```python
def write_json_atomic(path, data) -> None:
    """Grava ``data`` como JSON de forma atômica (.tmp + os.replace).

    Evita corromper o arquivo se o processo morrer no meio da escrita.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
```

(If `Path` isn't imported in utils.py, add `from pathlib import Path`.)

- [ ] **Step 4: Use it in `dashboard.py`.** Replace the `_save_history` write (`dashboard.py:194-198`):

```python
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        self.history_path.write_text(
            json.dumps(entries, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
```

with:

```python
        from .utils import write_json_atomic
        write_json_atomic(self.history_path, entries)
```

- [ ] **Step 5: Use it in `web/app.py`.** Replace `_write_history_data` (`app.py:408-411`):

```python
def _write_history_data(vault_path: Path, data: list[dict[str, Any]]) -> None:
    _history_file(vault_path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
```

with:

```python
def _write_history_data(vault_path: Path, data: list[dict[str, Any]]) -> None:
    from ..utils import write_json_atomic
    write_json_atomic(_history_file(vault_path), data)
```

- [ ] **Step 6: Run tests + regression**

Run: `.venv/bin/python -m pytest tests/test_reliability.py tests/test_stuck_jobs.py -q`
Expected: PASS (2 new + the stuck-jobs suite — they exercise history read/write).

- [ ] **Step 7: Commit**

```bash
git add meeting_processor/utils.py meeting_processor/dashboard.py meeting_processor/web/app.py tests/test_reliability.py
git commit -m "feat(reliability): atomic history writes"
```

---

### Task 2: Disk-space preflight

**Files:** Modify `meeting_processor/pipeline.py` (`process`, ~line 114); Test: `tests/test_reliability.py`.

- [ ] **Step 1: Append the failing test** to `tests/test_reliability.py`:

```python
# --- Task 2: disk preflight ------------------------------------------------

import meeting_processor.pipeline as pipemod
from meeting_processor.pipeline import MeetingPipeline


def test_disk_preflight_fails_fast(config, monkeypatch, tmp_path):
    extract_called = []
    monkeypatch.setattr(pipemod, "extract_audio", lambda *a, **k: extract_called.append(1))

    class _DU:  # free < need
        free = 1
    monkeypatch.setattr(pipemod.shutil, "disk_usage", lambda p: _DU())

    video = tmp_path / "reuniao.mp4"
    video.write_bytes(b"x" * 1000)
    with pytest.raises(RuntimeError, match="Espaço em disco"):
        MeetingPipeline(config).process(video)
    assert extract_called == []   # never reached extraction

    entry = [e for e in json.loads((config.vault_path / "wiki" / ".processing-history.json").read_text()) if e["file"] == "reuniao.mp4"][-1]
    assert entry["status"] == "error"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_reliability.py -k disk -q`
Expected: FAIL — no `shutil` on `pipemod` / extraction runs (no preflight).

- [ ] **Step 3: Implement.** In `meeting_processor/pipeline.py`, add `import shutil` to the imports (top of file). Then, in `process()`, immediately after `audio_path: Path | None = None` and the `try:` line, BEFORE `# Etapa 1: Extrair áudio`, insert:

```python
            # Pré-checagem de disco: falha rápida e legível em vez de OSError no meio.
            check_dir = self.config.temp_dir if Path(self.config.temp_dir).is_dir() else self.config.project_root
            free = shutil.disk_usage(check_dir).free
            need = video_path.stat().st_size * 3
            if free < need:
                raise RuntimeError(
                    f"Espaço em disco insuficiente: ~{need / 1e9:.1f} GB necessários, "
                    f"{free / 1e9:.1f} GB livres."
                )
```

(The existing `except Exception as e: job.fail(str(e)); ...; raise` records the readable message in history — no extra handling needed.)

- [ ] **Step 4: Run test + regression**

Run: `.venv/bin/python -m pytest tests/test_reliability.py tests/test_stuck_jobs.py -q`
Expected: PASS. (`test_stuck_jobs.py::test_audio_extraction_failure_marks_job_error` still passes — disk check passes for tiny test files since real free space ≫ `1000*3`.)

- [ ] **Step 5: Commit**

```bash
git add meeting_processor/pipeline.py tests/test_reliability.py
git commit -m "feat(reliability): disk-space preflight before extraction"
```

---

### Task 3: Config flag + job identity plumbing

Threads a caller-supplied `started`/`cancel_event` into the pipeline so the queue (Task 4) and cancel (Task 5) can address a job precisely. No behavior change (defaults preserve today).

**Files:** Modify `meeting_processor/config.py`, `meeting_processor/dashboard.py:142`, `meeting_processor/pipeline.py`; Test: `tests/test_reliability.py`.

- [ ] **Step 1: Append the failing test:**

```python
# --- Task 3: identity plumbing ---------------------------------------------

from datetime import datetime
from meeting_processor.config import load_config
from meeting_processor.dashboard import Dashboard


def test_max_concurrent_jobs_default_and_env(monkeypatch):
    monkeypatch.delenv("MEETING_MAX_CONCURRENT_JOBS", raising=False)
    assert load_config().max_concurrent_jobs == 1
    monkeypatch.setenv("MEETING_MAX_CONCURRENT_JOBS", "3")
    assert load_config().max_concurrent_jobs == 3


def test_new_job_accepts_started_at(config):
    d = Dashboard(config)
    ts = datetime(2026, 6, 9, 10, 0, 0)
    job = d.new_job("x.mp4", started_at=ts)
    assert job.started_at == ts
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_reliability.py -k "max_concurrent or started_at" -q`
Expected: FAIL — no `max_concurrent_jobs`; `new_job` rejects `started_at`.

- [ ] **Step 3: Add the config field.** In `meeting_processor/config.py`, add a field near the other ints (e.g. after `max_tokens_summary`):

```python
    # Jobs simultâneos de processamento (fila de slot único por padrão).
    max_concurrent_jobs: int = 1
```

And in the `int_overrides` dict add:

```python
        "MEETING_MAX_CONCURRENT_JOBS": "max_concurrent_jobs",
```

- [ ] **Step 4: `new_job` accepts `started_at`.** In `dashboard.py:142-146`, change:

```python
    def new_job(self, source_file: str) -> ProcessingJob:
        job = ProcessingJob(source_file)
        self.jobs.append(job)
        self._render()
        return job
```

to:

```python
    def new_job(self, source_file: str, started_at: datetime | None = None) -> ProcessingJob:
        job = ProcessingJob(source_file, started_at=started_at)
        self.jobs.append(job)
        self._render()
        return job
```

(`ProcessingJob.__init__` already accepts `started_at`.)

- [ ] **Step 5: Pipeline accepts `job_started` + `cancel_event`.** In `pipeline.py`:
  - Add to `MeetingPipeline.__init__` (after the existing attributes): `self._cancel_event = None`.
  - Change `process` signature and its `new_job` call:

    ```python
    def process(self, video_path: Path, transcript_only: bool = False,
                job_started=None, cancel_event=None) -> ProcessingResult:
    ```
    Set `self._cancel_event = cancel_event` as the first line of the body, and change `job = self.dashboard.new_job(video_path.name)` to `job = self.dashboard.new_job(video_path.name, started_at=job_started)`.
  - Change `summarize_existing` signature to `def summarize_existing(self, meeting_id: str, job_started=None, cancel_event=None) -> None:`, set `self._cancel_event = cancel_event` first, and change its `new_job(meeting_id)` to `new_job(meeting_id, started_at=job_started)`.
  - Change `transcribe_existing` signature to `def transcribe_existing(self, meeting_id: str, job_started=None, cancel_event=None) -> None:`, set `self._cancel_event = cancel_event` first, and change its `new_job(meeting_id)` to `new_job(meeting_id, started_at=job_started)`.

- [ ] **Step 6: Run tests + regression**

Run: `.venv/bin/python -m pytest tests/test_reliability.py tests/test_stuck_jobs.py -q`
Expected: PASS (defaults `job_started=None`/`cancel_event=None` keep current behavior).

- [ ] **Step 7: Commit**

```bash
git add meeting_processor/config.py meeting_processor/dashboard.py meeting_processor/pipeline.py tests/test_reliability.py
git commit -m "feat(reliability): job-identity plumbing (started_at, cancel_event, max_concurrent_jobs)"
```

---

### Task 4: Single-slot executor + CancelRegistry + submit wiring

**Files:** Create `meeting_processor/job_control.py`; Modify `meeting_processor/web/app.py` (lifespan + 5 job sites); Test: `tests/test_reliability.py`.

- [ ] **Step 1: Append the failing tests:**

```python
# --- Task 4: queue + registry ----------------------------------------------

from meeting_processor.job_control import CancelRegistry, JobCancelled


def test_cancel_registry_register_lookup_discard():
    import threading
    reg = CancelRegistry()
    fut, ev = object(), threading.Event()
    reg.register("a.mp4", "2026-01-01T00:00:00", fut, ev)
    assert reg.lookup("a.mp4", "2026-01-01T00:00:00") == (fut, ev)
    reg.discard("a.mp4", "2026-01-01T00:00:00")
    assert reg.lookup("a.mp4", "2026-01-01T00:00:00") is None


def test_executor_serializes_jobs():
    from concurrent.futures import ThreadPoolExecutor
    import threading, time
    ex = ThreadPoolExecutor(max_workers=1)
    overlap = {"max": 0, "cur": 0}
    lock = threading.Lock()

    def work():
        with lock:
            overlap["cur"] += 1
            overlap["max"] = max(overlap["max"], overlap["cur"])
        time.sleep(0.02)
        with lock:
            overlap["cur"] -= 1

    futs = [ex.submit(work) for _ in range(4)]
    for f in futs:
        f.result()
    ex.shutdown()
    assert overlap["max"] == 1   # never two at once
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_reliability.py -k "registry or serializes" -q`
Expected: FAIL — `cannot import name 'CancelRegistry'`.

- [ ] **Step 3: Create `meeting_processor/job_control.py`:**

```python
"""Controle de jobs de processamento: cancelamento cooperativo."""
from __future__ import annotations

import threading
from typing import Any


class JobCancelled(Exception):
    """Levantada nos limites de etapa quando o usuário cancela um job."""


class CancelRegistry:
    """Mapeia ``(file, started_iso)`` para ``(Future, Event)`` de um job ativo.

    Thread-safe. Usado pelo endpoint de cancelamento para parar um job em
    execução (``event.set()``) ou remover um job ainda na fila
    (``future.cancel()``).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[tuple[str, str], tuple[Any, threading.Event]] = {}

    def register(self, file: str, started_iso: str, future: Any, event: threading.Event) -> None:
        with self._lock:
            self._jobs[(file, started_iso)] = (future, event)

    def lookup(self, file: str, started_iso: str):
        with self._lock:
            return self._jobs.get((file, started_iso))

    def discard(self, file: str, started_iso: str) -> None:
        with self._lock:
            self._jobs.pop((file, started_iso), None)
```

- [ ] **Step 4: Create the executor + registry + `_submit_job` in `app.py`.** Near the top of `create_app` (before the endpoints, after `config` is in scope), add:

```python
    from concurrent.futures import ThreadPoolExecutor
    from ..job_control import CancelRegistry

    job_executor = ThreadPoolExecutor(
        max_workers=config.max_concurrent_jobs, thread_name_prefix="job"
    )
    cancel_registry = CancelRegistry()

    def _submit_job(file_label: str, run_fn) -> None:
        """Enfileira um job no executor de slot único e registra-o para cancelamento.

        ``run_fn(started, event)`` roda o pipeline com a identidade
        ``(file_label, started)`` e o ``Event`` de cancelamento.
        """
        started = datetime.now()
        key = started.isoformat()
        event = threading.Event()

        def _wrapped():
            try:
                run_fn(started, event)
            except Exception:  # noqa: BLE001
                logger.exception("Falha no job: %s", file_label)
            finally:
                cancel_registry.discard(file_label, key)

        future = job_executor.submit(_wrapped)
        cancel_registry.register(file_label, key, future, event)
        logger.info("Job enfileirado: %s", file_label)
```

In the `lifespan` function, after the `yield`, add executor shutdown (alongside the existing watcher stop):

```python
        job_executor.shutdown(wait=False, cancel_futures=True)
```

- [ ] **Step 5: Rewire the 5 meeting-job sites.** Replace each `threading.Thread(target=_run, daemon=True).start()` (and its `_run` closure) with a `_submit_job` call. Do NOT touch the Ollama-pull thread (`/api/llm/local-models/pull`, ~line 1411) — that's a model download, not a meeting job.

  **5a. `/actions/process` (~line 1058):** replace the `def _run(): ... threading.Thread(...).start()` block with:
  ```python
        _submit_job(path.name, lambda started, ev: MeetingPipeline(config).process(
            path, job_started=started, cancel_event=ev))
  ```
  (Add `from ..pipeline import MeetingPipeline` at the top of the endpoint body if the inline import was inside `_run`.)

  **5b. `/api/meetings/{id}/summarize` (~line 1217):**
  ```python
        _submit_job(meeting_id, lambda started, ev: MeetingPipeline(config).summarize_existing(
            meeting_id, job_started=started, cancel_event=ev))
  ```

  **5c. `/api/meetings/{id}/transcribe` (~line 1234):**
  ```python
        _submit_job(meeting_id, lambda started, ev: MeetingPipeline(config).transcribe_existing(
            meeting_id, job_started=started, cancel_event=ev))
  ```

  **5d. `/api/process` (~line 1497):**
  ```python
        _submit_job(path.name, lambda started, ev: MeetingPipeline(config).process(
            path, transcript_only=(mode == "transcript"), job_started=started, cancel_event=ev))
  ```

  **5e. `_process_path_async` (~line 1524):** replace its `_run`/thread body with:
  ```python
        _submit_job(path.name, lambda started, ev: MeetingPipeline(config).process(
            path, transcript_only=transcript_only, job_started=started, cancel_event=ev))
  ```

  Each site needs `MeetingPipeline` importable; add `from ..pipeline import MeetingPipeline` at the top of `create_app` (once) so all lambdas resolve it.

- [ ] **Step 6: Run tests + regression**

Run: `.venv/bin/python -m pytest tests/test_reliability.py tests/test_stuck_jobs.py tests/test_local_models.py -q`
Expected: PASS. Confirm `.venv/bin/python -c "import meeting_processor.web.app"` imports cleanly.

- [ ] **Step 7: Commit**

```bash
git add meeting_processor/job_control.py meeting_processor/web/app.py tests/test_reliability.py
git commit -m "feat(reliability): single-slot job queue + cancel registry"
```

---

### Task 5: Cooperative cancel (pipeline checks + endpoint)

**Files:** Modify `meeting_processor/pipeline.py` (`_check_cancel` + boundary calls), `meeting_processor/web/app.py` (cancel endpoint); Test: `tests/test_reliability.py`.

- [ ] **Step 1: Append the failing test:**

```python
# --- Task 5: cooperative cancel --------------------------------------------

import threading


def test_cancel_event_aborts_pipeline(config, monkeypatch, tmp_path):
    from meeting_processor.models import Transcript, TranscriptSegment
    monkeypatch.setattr(pipemod, "extract_audio", lambda *a, **k: tmp_path / "a.wav")
    monkeypatch.setattr(pipemod.shutil, "disk_usage", lambda p: type("D", (), {"free": 10**12})())
    seg = TranscriptSegment(start=0.0, end=1.0, text="oi")
    fake_tr = Transcript(segments=[seg], full_text="oi", language="pt", duration=1.0)
    monkeypatch.setattr(MeetingPipeline, "transcriber", property(lambda self: type("T", (), {"transcribe": lambda *a, **k: fake_tr})()))

    ev = threading.Event()
    ev.set()   # cancel before the first checkpoint fires
    video = tmp_path / "reuniao.mp4"
    video.write_bytes(b"x")
    with pytest.raises(Exception):
        MeetingPipeline(config).process(video, cancel_event=ev)
    entry = [e for e in json.loads((config.vault_path / "wiki" / ".processing-history.json").read_text()) if e["file"] == "reuniao.mp4"][-1]
    assert entry["status"] == "error"
    assert "Cancelado" in (entry.get("error_message") or "")
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_reliability.py -k cancel_event_aborts -q`
Expected: FAIL — no cancel check; pipeline runs past the audio stage.

- [ ] **Step 3: Add `_check_cancel` + boundary calls.** In `pipeline.py`, add the import `from .job_control import JobCancelled` at the top. Add a method to `MeetingPipeline`:

```python
    def _check_cancel(self) -> None:
        if self._cancel_event is not None and self._cancel_event.is_set():
            raise JobCancelled("Cancelado pelo usuário.")
```

In `process()`, call `self._check_cancel()` at three boundaries (each on its own line, correctly indented inside the `try`):
- immediately after the audio stage finishes (after `self.dashboard.update(job)` that follows the `size_mb` progress line),
- immediately after the transcription stage finishes (after the `job.set_progress("transcription", 100, ...)` + `self.dashboard.update(job)`),
- immediately after `summary = self._summarize(...)` returns.

In `transcribe_existing()`, add `self._check_cancel()` after the transcription completes (after its `transcript = self.transcriber.transcribe(...)` block). In `summarize_existing()`, add `self._check_cancel()` right after it loads the transcript and before calling `_summarize`.

(`JobCancelled` subclasses `Exception`, so the existing `except Exception as e: job.fail(str(e)); ...; raise` in `process()` records "Cancelado pelo usuário." For `summarize_existing`/`transcribe_existing`, ensure their own `try/except` — which already records to the generation log / fails the job — likewise catch it; if a method lacks a broad except around the work, wrap the `_check_cancel`+work so `JobCancelled` marks the job failed.)

- [ ] **Step 4: Rewire the cancel endpoint** to actually stop work. Replace `api_cancel_job` (`app.py:1508-1520`) body with:

```python
    @app.post("/api/process/cancel")
    async def api_cancel_job(payload: dict):
        """Cancela um job: para a execução (ou tira da fila) e marca o histórico."""
        p = payload or {}
        file_name = p.get("file", "")
        started = p.get("started") or None
        if started is not None:
            entry = cancel_registry.lookup(file_name, started)
            if entry is not None:
                future, event = entry
                if not future.cancel():     # já rodando → sinaliza parada cooperativa
                    event.set()
        result = _cancel_active_job(config.vault_path, file_name, started)
        if not result["ok"]:
            return JSONResponse(
                {"ok": False, "error": result.get("error", "Não encontrado")},
                status_code=404,
            )
        return {"ok": True}
```

- [ ] **Step 5: Run tests + full regression**

Run: `.venv/bin/python -m pytest tests/test_reliability.py -q` (all pass), then `.venv/bin/python -m pytest -q`.
Expected: full suite passes except the pre-existing `test_factory_selects_anthropic` (no `ANTHROPIC_API_KEY`).

- [ ] **Step 6: Commit**

```bash
git add meeting_processor/pipeline.py meeting_processor/web/app.py tests/test_reliability.py
git commit -m "feat(reliability): cooperative cancel stops running/queued jobs"
```

---

## Self-Review

**Spec coverage:**
- Atomic writes (both writers) → Task 1. ✓
- Disk preflight (raise → existing except) → Task 2. ✓
- `max_concurrent_jobs` config + env → Task 3. ✓
- `new_job(started_at)` + pipeline `job_started`/`cancel_event` plumbing → Task 3. ✓
- Single-worker executor + `_submit_job` + 5 sites rewired (pull excluded) → Task 4. ✓
- `CancelRegistry` + `JobCancelled` → Task 4 (registry) + Task 5 (exception + checks). ✓
- Cancel endpoint: future.cancel (queued) / event.set (running) + `_cancel_active_job` → Task 5. ✓
- Defaults preserve current behavior (off-path) → Tasks 3-5 use `None`/`1` defaults; full suite in Task 5 Step 5. ✓
- Out-of-scope (queued visibility, watcher cross-process, ffmpeg kill) → untouched. ✓

**Placeholder scan:** none — every code step has concrete content. The 5 site rewrites give the exact lambda per site.

**Type consistency:** `write_json_atomic(path, data)` (Task 1) used in dashboard/app. `new_job(source_file, started_at=None)` (Task 3) called with `started_at=job_started` in pipeline (Task 3) — `job_started` is the `started` from `_submit_job` (Task 4). `process/summarize_existing/transcribe_existing(..., job_started=None, cancel_event=None)` (Task 3) called with `job_started=started, cancel_event=ev` in the `_submit_job` lambdas (Task 4). `self._cancel_event` set in Task 3, read by `_check_cancel` in Task 5. `CancelRegistry.register/lookup/discard` (Task 4) used by `_submit_job` (Task 4) and the cancel endpoint (Task 5). `JobCancelled` defined Task 4, raised Task 5. Names consistent throughout. ✓
