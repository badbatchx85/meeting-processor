# Transcript / Summary Regen Buttons + Per-Meeting Generation Log — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add user-triggered "Gerar transcrição" / "Gerar resumo" actions (meeting detail + per-row on the meetings list), a transcript-only option for new files on the Dashboard, deletion of the original media file, and a dedicated per-meeting audit log that records each run with OK/error + reason.

**Architecture:** Mirror the existing `summarize_existing` background-job pattern. A new `generation_log` module appends JSON entries to `<meeting_dir>/.generation-log.json`. A new `transcribe_existing` pipeline method re-runs Whisper only. A single shared `locate_source_file(config, meeting_dir)` (folder-stem match against `uploads/` + `watch_dir`) powers re-transcribe, source-status, and delete. New FastAPI routes expose these; React gains buttons, a log panel, and a source-status line.

**Tech Stack:** Python 3.11+, FastAPI, pytest (TestClient); React + TypeScript, @tanstack/react-query, Vitest + Testing Library, lucide-react, Tailwind.

**Spec:** `docs/superpowers/specs/2026-06-05-transcript-generation-log-design.md`

---

## File Structure

**Backend**
- Create: `meeting_processor/generation_log.py` — read/append the per-meeting JSON audit log.
- Modify: `meeting_processor/pipeline.py` — add module-level `locate_source_file`, add `transcribe_existing`, add `transcript_only` param to `process`, add log writes to `summarize_existing`.
- Modify: `meeting_processor/web/app.py` — add routes `POST /api/meetings/{id}/transcribe`, `GET /api/meetings/{id}/log`, `GET /api/meetings/{id}/source`, `DELETE /api/meetings/{id}/source`; add `mode` to `/api/process` and `/api/process/upload`.

**Frontend**
- Modify: `frontend/src/api/types.ts` — `GenerationLogEntry`, `SourceInfo`.
- Modify: `frontend/src/hooks/useApi.ts` — `useTranscribeMeeting`, `useGenerationLog`, `useMeetingSource`, `useDeleteMeetingSource`; extend `useProcessFile` / `useUploadFile` with `mode`.
- Create: `frontend/src/components/GenerationLog.tsx` — renders log entries.
- Modify: `frontend/src/pages/MeetingDetail.tsx` — header buttons, source line + delete, log panel.
- Modify: `frontend/src/pages/Meetings.tsx` — per-row transcribe/summarize buttons.
- Modify: `frontend/src/pages/Dashboard.tsx` — "Apenas transcrição" checkbox.
- Modify: `frontend/src/__tests__/summarizeButton.test.tsx` — "Gerar resumo" is now always visible.

**Tests (new)**
- `tests/test_generation_log.py`, `tests/test_transcribe_existing.py`
- `frontend/src/__tests__/generationLog.test.tsx`, additions to `meetingDetail.test.tsx`, `meetings.test.tsx`, `settings.test.tsx`/dashboard.

---

## Task 1: `generation_log` module

**Files:**
- Create: `meeting_processor/generation_log.py`
- Test: `tests/test_generation_log.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_generation_log.py
"""Per-meeting generation audit log."""
from datetime import datetime

from meeting_processor import generation_log


def test_append_then_read_newest_first(tmp_path):
    d = tmp_path
    t0 = datetime(2026, 6, 5, 10, 0, 0)
    t1 = datetime(2026, 6, 5, 10, 3, 0)
    generation_log.append(d, "transcript", "ok", detail="12 seg", started=t0, completed=t1)
    generation_log.append(d, "summary", "error", error="429", started=t1, completed=t1)
    entries = generation_log.read(d)
    assert [e["action"] for e in entries] == ["summary", "transcript"]  # newest first
    assert entries[0]["status"] == "error" and entries[0]["error"] == "429"
    assert entries[1]["detail"] == "12 seg" and entries[1]["error"] is None
    assert entries[1]["started"] == "2026-06-05T10:00:00"


def test_read_missing_returns_empty(tmp_path):
    assert generation_log.read(tmp_path) == []


def test_read_corrupt_returns_empty(tmp_path):
    (tmp_path / ".generation-log.json").write_text("{not json", encoding="utf-8")
    assert generation_log.read(tmp_path) == []


def test_append_caps_to_limit(tmp_path):
    t = datetime(2026, 6, 5, 10, 0, 0)
    for i in range(60):
        generation_log.append(tmp_path, "transcript", "ok", detail=str(i), started=t, completed=t)
    entries = generation_log.read(tmp_path)
    assert len(entries) == 50
    assert entries[0]["detail"] == "59"  # newest kept
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_generation_log.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'meeting_processor.generation_log'`

- [ ] **Step 3: Write minimal implementation**

```python
# meeting_processor/generation_log.py
"""Log de auditoria por reunião das ações manuais de geração.

Cada reunião tem um ``.generation-log.json`` na sua pasta com uma lista de
entradas (transcrição / resumo / exclusão do arquivo de origem), do mais antigo
para o mais novo no arquivo. ``read`` devolve do mais novo para o mais antigo.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_FILENAME = ".generation-log.json"
_LIMIT = 50


def _path(meeting_dir: Path) -> Path:
    return meeting_dir / _FILENAME


def read(meeting_dir: Path) -> list[dict]:
    """Entradas do log, do mais novo para o mais antigo. ``[]`` se ausente/corrompido."""
    p = _path(meeting_dir)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, list):
        return []
    return list(reversed(data))


def append(
    meeting_dir: Path,
    action: str,
    status: str,
    *,
    error: str | None = None,
    detail: str = "",
    started: datetime,
    completed: datetime,
) -> None:
    """Acrescenta uma entrada e regrava (mantém só as últimas ``_LIMIT``)."""
    p = _path(meeting_dir)
    entries: list = []
    if p.exists():
        try:
            loaded = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                entries = loaded
        except (json.JSONDecodeError, OSError):
            entries = []
    entries.append(
        {
            "action": action,
            "status": status,
            "error": error,
            "detail": detail,
            "started": started.isoformat(timespec="seconds"),
            "completed": completed.isoformat(timespec="seconds"),
        }
    )
    entries = entries[-_LIMIT:]
    try:
        tmp = p.with_name(_FILENAME + ".tmp")
        tmp.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(p)
    except OSError:
        logger.exception("Falha ao gravar generation-log em %s", p)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_generation_log.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add meeting_processor/generation_log.py tests/test_generation_log.py
git commit -m "feat: per-meeting generation audit log module"
```

---

## Task 2: `locate_source_file` in pipeline

**Files:**
- Modify: `meeting_processor/pipeline.py` (add module-level function after imports / before the class, ~line 20)
- Test: `tests/test_transcribe_existing.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_transcribe_existing.py
"""Re-transcription of an existing meeting + source-file location."""
from datetime import datetime

from meeting_processor.models import Transcript, TranscriptSegment
from meeting_processor.note_generator import NoteGenerator
from meeting_processor.pipeline import locate_source_file


def _make_meeting(config, source_name="reuniao.mp4"):
    """Create a transcript-only meeting folder, return its id (folder name)."""
    transcript = Transcript(
        segments=[TranscriptSegment(start=0.0, end=5.0, text="Oi.")],
        full_text="Oi.",
        language="pt",
        duration=5.0,
    )
    gen = NoteGenerator(config)
    paths = gen.prepare(source_name, datetime(2026, 6, 4, 10, 0))
    gen.write_transcription(transcript, paths)
    gen.write_group_note(paths, has_summary=False)
    return paths.meeting_dir.name


def test_locate_source_in_uploads(config, tmp_path):
    config.watch_dir = str(tmp_path / "watch")  # isolate from real ~/Videos/OBS
    mid = _make_meeting(config, "reuniao.mp4")
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    media = uploads / "reuniao.mp4"
    media.write_bytes(b"fake")
    found = locate_source_file(config, config.reunioes_path / mid)
    assert found == media


def test_locate_source_missing_returns_none(config, tmp_path):
    config.watch_dir = str(tmp_path / "watch")
    mid = _make_meeting(config, "reuniao.mp4")
    assert locate_source_file(config, config.reunioes_path / mid) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_transcribe_existing.py::test_locate_source_in_uploads -v`
Expected: FAIL with `ImportError: cannot import name 'locate_source_file'`

- [ ] **Step 3: Write minimal implementation**

In `meeting_processor/pipeline.py`, add `import re` to the imports (top of file, alongside `import time`), then add this module-level function right after `logger = logging.getLogger(__name__)` (line ~19):

```python
_FOLDER_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}h\d{2} - (.+)$")


def locate_source_file(config: "Settings", meeting_dir: Path) -> Path | None:
    """Encontra o arquivo de mídia que originou a transcrição da reunião.

    O nome da pasta é ``"<data> <hora> - <stem-do-arquivo>"`` e o stem é sempre
    igual ao do arquivo original (``NoteGenerator.prepare`` usa ``Path(src).stem``).
    Procura em ``uploads/`` e no ``watch_dir`` por um arquivo com esse stem e uma
    extensão suportada. Devolve o primeiro encontrado ou ``None``.
    """
    m = _FOLDER_PREFIX_RE.match(meeting_dir.name)
    stem = m.group(1) if m else meeting_dir.name
    exts = {e.lower() for e in config.watch_extensions}
    roots = [Path(config.project_root) / "uploads", config.watch_path]
    for root in roots:
        try:
            if not root.is_dir():
                continue
            for entry in root.iterdir():
                if (
                    entry.is_file()
                    and entry.stem == stem
                    and (not exts or entry.suffix.lower() in exts)
                ):
                    return entry
        except OSError:
            continue
    return None
```

(`Settings` is already imported at the top via `from .config import Settings`; the quotes are optional but harmless.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_transcribe_existing.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add meeting_processor/pipeline.py tests/test_transcribe_existing.py
git commit -m "feat: locate_source_file helper (folder-stem match)"
```

---

## Task 3: `transcribe_existing` + `transcript_only` in `process`

**Files:**
- Modify: `meeting_processor/pipeline.py` (new method after `summarize_existing`, ~line 258; edit `process` signature/body, lines 36/49)
- Test: `tests/test_transcribe_existing.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_transcribe_existing.py`:

```python
def test_transcribe_existing_overwrites_and_logs(config, tmp_path, monkeypatch):
    from meeting_processor import generation_log
    from meeting_processor.pipeline import MeetingPipeline

    config.watch_dir = str(tmp_path / "watch")
    mid = _make_meeting(config, "reuniao.mp4")
    (tmp_path / "uploads").mkdir()
    (tmp_path / "uploads" / "reuniao.mp4").write_bytes(b"fake")

    # Avoid touching ffmpeg/whisper: stub audio extraction + transcriber.
    monkeypatch.setattr(
        "meeting_processor.pipeline.extract_audio",
        lambda src, cfg: tmp_path / "audio.wav",
    )
    (tmp_path / "audio.wav").write_bytes(b"x")
    new_transcript = Transcript(
        segments=[
            TranscriptSegment(start=0.0, end=3.0, text="Texto novo um."),
            TranscriptSegment(start=3.0, end=6.0, text="Texto novo dois."),
        ],
        full_text="Texto novo um. Texto novo dois.",
        language="pt",
        duration=6.0,
    )

    class _FakeTranscriber:
        def __init__(self, *a, **k): ...
        def transcribe(self, audio_path, progress_callback=None):
            return new_transcript

    monkeypatch.setattr("meeting_processor.pipeline.WhisperTranscriber", lambda cfg: _FakeTranscriber())

    MeetingPipeline(config).transcribe_existing(mid)

    raw = next((config.reunioes_path / mid).glob("Transcricao - *.md")).read_text(encoding="utf-8")
    assert "Texto novo um." in raw
    entries = generation_log.read(config.reunioes_path / mid)
    assert entries and entries[0]["action"] == "transcript" and entries[0]["status"] == "ok"


def test_transcribe_existing_no_source_logs_error(config, tmp_path):
    from meeting_processor import generation_log
    from meeting_processor.pipeline import MeetingPipeline

    config.watch_dir = str(tmp_path / "watch")
    mid = _make_meeting(config, "reuniao.mp4")  # no media file on disk
    MeetingPipeline(config).transcribe_existing(mid)
    entries = generation_log.read(config.reunioes_path / mid)
    assert entries and entries[0]["action"] == "transcript" and entries[0]["status"] == "error"
    assert "não encontrado" in entries[0]["error"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_transcribe_existing.py::test_transcribe_existing_no_source_logs_error -v`
Expected: FAIL with `AttributeError: 'MeetingPipeline' object has no attribute 'transcribe_existing'`

- [ ] **Step 3: Write minimal implementation**

3a. Add the import at the top of `pipeline.py` (with the other `from .` imports):

```python
from . import generation_log
```

3b. Change `process` to accept the flag. Replace the signature (line 36) and the `steps` line (line 49):

```python
    def process(self, video_path: Path, transcript_only: bool = False) -> ProcessingResult:
```

```python
        start_time = time.time()
        steps = self.config.steps()
        if transcript_only:
            steps = {"summary": False, "note": False, "kanban": False, "wiki": False}
```

3c. Add the new method after `summarize_existing` (after line 258):

```python
    def transcribe_existing(self, meeting_id: str) -> None:
        """Re-transcreve uma reunião já existente (só transcrição, sem resumo).

        Localiza o arquivo de origem, roda áudio+Whisper, sobrescreve a
        transcrição salva e registra o resultado no log de geração da reunião.
        Se a origem sumiu, registra um erro no log e retorna (sem exceção).
        """
        base = self.config.reunioes_path.resolve()
        meeting_dir = (base / meeting_id).resolve()
        if meeting_dir.parent != base or not meeting_dir.is_dir():
            raise FileNotFoundError(f"Reunião inválida: {meeting_id}")

        started = datetime.now()
        source = locate_source_file(self.config, meeting_dir)
        if source is None:
            generation_log.append(
                meeting_dir,
                "transcript",
                "error",
                error=f"Arquivo de origem não encontrado: {meeting_dir.name}",
                started=started,
                completed=datetime.now(),
            )
            logger.warning("Re-transcrição: origem não encontrada para %s", meeting_id)
            return

        logger.info("Re-transcrevendo %s (origem: %s)", meeting_id, source.name)
        job = self.dashboard.new_job(meeting_id)
        for key in ("summary", "note", "kanban", "wiki"):
            job.skip(key)
        job.advance("audio", "Convertendo video para WAV 16kHz")
        job.set_progress("audio", 10)
        self.dashboard.update(job)
        audio_path = extract_audio(source, self.config)
        try:
            job.set_progress("audio", 100)
            job.advance("transcription", f"Modelo: {self.config.whisper_model}")
            job.set_progress("transcription", 5, "Carregando modelo...")
            self.dashboard.update(job)
            transcript = self.transcriber.transcribe(
                audio_path, progress_callback=self._make_progress_cb(job)
            )
            paths = self.note_generator.paths_for_existing(meeting_dir)
            self.note_generator.write_transcription(transcript, paths)
            detail = f"{len(transcript.segments)} segmentos, {format_duration(transcript.duration)}"
            job.complete(f"So transcricao | {detail}")
            self.dashboard.update(job)
            generation_log.append(
                meeting_dir, "transcript", "ok", detail=detail,
                started=started, completed=datetime.now(),
            )
        except Exception as e:
            job.fail(str(e))
            self.dashboard.update(job)
            generation_log.append(
                meeting_dir, "transcript", "error", error=str(e),
                started=started, completed=datetime.now(),
            )
            raise
        finally:
            if self.config.cleanup_temp and audio_path.exists():
                audio_path.unlink()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_transcribe_existing.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add meeting_processor/pipeline.py tests/test_transcribe_existing.py
git commit -m "feat: transcribe_existing + transcript_only process mode"
```

---

## Task 4: log writes in `summarize_existing`

**Files:**
- Modify: `meeting_processor/pipeline.py` (`summarize_existing`, lines 247-258)
- Test: `tests/test_transcribe_existing.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_transcribe_existing.py`:

```python
def test_summarize_existing_appends_log(config, tmp_path, monkeypatch):
    from meeting_processor import generation_log
    from meeting_processor.models import ActionItem, MeetingSummary
    from meeting_processor.pipeline import MeetingPipeline

    mid = _make_meeting(config, "reuniao.mp4")

    class _FakeSummarizer:
        def __init__(self, *a, **k): ...
        def summarize(self, transcript, source_filename):
            return MeetingSummary(
                executive_summary="ok", time_windows=[],
                action_items=[ActionItem(description="x", assignee="y")],
                participants=["y"], key_topics=["k"], purpose="p",
                meeting_type="status", decisions=[], open_questions=[],
            )

    monkeypatch.setattr("meeting_processor.pipeline.MeetingSummarizer", lambda cfg: _FakeSummarizer())
    MeetingPipeline(config).summarize_existing(mid)

    entries = generation_log.read(config.reunioes_path / mid)
    assert entries and entries[0]["action"] == "summary" and entries[0]["status"] == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_transcribe_existing.py::test_summarize_existing_appends_log -v`
Expected: FAIL (no `summary` entry — `assert entries` is empty / IndexError)

- [ ] **Step 3: Write minimal implementation**

Replace the body of `summarize_existing` from `job = self.dashboard.new_job(meeting_id)` (line 247) through the `except` block (line 258) with:

```python
        job = self.dashboard.new_job(meeting_id)
        for key in ("audio", "transcription"):
            job.advance(key)
            job.set_progress(key, 100)
        started = datetime.now()
        try:
            self._summarize(transcript, paths, meeting_id, created_at, job, steps)
            job.complete("resumo gerado a partir da transcrição")
            self.dashboard.update(job)
            generation_log.append(
                meeting_dir, "summary", "ok",
                detail="resumo gerado a partir da transcrição",
                started=started, completed=datetime.now(),
            )
        except Exception as e:
            job.fail(str(e))
            self.dashboard.update(job)
            generation_log.append(
                meeting_dir, "summary", "error", error=str(e),
                started=started, completed=datetime.now(),
            )
            raise
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_transcribe_existing.py tests/test_summarize_existing.py -v`
Expected: PASS (all green — existing summarize tests still pass)

- [ ] **Step 5: Commit**

```bash
git add meeting_processor/pipeline.py tests/test_transcribe_existing.py
git commit -m "feat: record summary runs in the generation log"
```

---

## Task 5: API routes (transcribe, log, source GET/DELETE, process mode)

**Files:**
- Modify: `meeting_processor/web/app.py` (add routes near the summarize route ~line 1139; edit `api_process` ~line 1300 and `api_process_upload` ~line 1345)
- Test: `tests/test_transcribe_api.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_transcribe_api.py
"""API for re-transcribe, generation log, and source-file management."""
from datetime import datetime

from meeting_processor.models import Transcript, TranscriptSegment
from meeting_processor.note_generator import NoteGenerator


def _make_meeting(config, source_name="reuniao.mp4"):
    transcript = Transcript(
        segments=[TranscriptSegment(start=0.0, end=5.0, text="Oi.")],
        full_text="Oi.", language="pt", duration=5.0,
    )
    gen = NoteGenerator(config)
    paths = gen.prepare(source_name, datetime(2026, 6, 4, 10, 0))
    gen.write_transcription(transcript, paths)
    gen.write_group_note(paths, has_summary=False)
    return paths.meeting_dir.name


def test_transcribe_endpoint_queues(client, config, monkeypatch):
    mid = _make_meeting(config)
    called = {"id": None}
    monkeypatch.setattr(
        "meeting_processor.pipeline.MeetingPipeline.transcribe_existing",
        lambda self, meeting_id: called.__setitem__("id", meeting_id),
    )
    r = client.post(f"/api/meetings/{mid}/transcribe")
    assert r.status_code == 200 and r.json()["queued"] is True


def test_transcribe_endpoint_404(client):
    assert client.post("/api/meetings/nao-existe/transcribe").status_code == 404


def test_log_endpoint_returns_entries(client, config):
    from meeting_processor import generation_log
    mid = _make_meeting(config)
    t = datetime(2026, 6, 5, 10, 0, 0)
    generation_log.append(config.reunioes_path / mid, "transcript", "ok", detail="d", started=t, completed=t)
    r = client.get(f"/api/meetings/{mid}/log")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1 and body[0]["action"] == "transcript"


def test_source_endpoint_reports_existence(client, config, tmp_path):
    config.watch_dir = str(tmp_path / "watch")
    mid = _make_meeting(config, "reuniao.mp4")
    r = client.get(f"/api/meetings/{mid}/source")
    assert r.status_code == 200 and r.json()["exists"] is False
    (tmp_path / "uploads").mkdir()
    (tmp_path / "uploads" / "reuniao.mp4").write_bytes(b"1234")
    r = client.get(f"/api/meetings/{mid}/source")
    assert r.json() == {"exists": True, "name": "reuniao.mp4",
                        "path": str(tmp_path / "uploads" / "reuniao.mp4"), "size": 4}


def test_delete_source_removes_and_logs(client, config, tmp_path):
    from meeting_processor import generation_log
    config.watch_dir = str(tmp_path / "watch")
    mid = _make_meeting(config, "reuniao.mp4")
    (tmp_path / "uploads").mkdir()
    media = tmp_path / "uploads" / "reuniao.mp4"
    media.write_bytes(b"1234")
    r = client.delete(f"/api/meetings/{mid}/source")
    assert r.status_code == 200 and r.json()["deleted"] is True
    assert not media.exists()
    assert (config.reunioes_path / mid).is_dir()  # meeting kept
    entries = generation_log.read(config.reunioes_path / mid)
    assert entries[0]["action"] == "delete_source" and entries[0]["status"] == "ok"


def test_delete_source_missing_is_idempotent(client, config, tmp_path):
    config.watch_dir = str(tmp_path / "watch")
    mid = _make_meeting(config, "reuniao.mp4")
    r = client.delete(f"/api/meetings/{mid}/source")
    assert r.status_code == 200 and r.json()["deleted"] is False


def test_process_transcript_mode(client, config, tmp_path, monkeypatch):
    media = tmp_path / "reuniao.mp4"
    media.write_bytes(b"x")
    seen = {}
    monkeypatch.setattr(
        "meeting_processor.pipeline.MeetingPipeline.process",
        lambda self, path, transcript_only=False: seen.update(to=transcript_only),
    )
    r = client.post("/api/process", json={"file": str(media), "mode": "transcript"})
    assert r.status_code == 200 and r.json()["queued"] is True
    # thread runs async; poll briefly
    import time as _t
    for _ in range(50):
        if "to" in seen:
            break
        _t.sleep(0.02)
    assert seen.get("to") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_transcribe_api.py -v`
Expected: FAIL (404s / KeyError — routes not defined; `mode` ignored)

- [ ] **Step 3: Write minimal implementation**

3a. Add the four routes immediately after the `api_summarize` route (after line 1139, before `@app.get("/api/watcher")`):

```python
    @app.post("/api/meetings/{meeting_id}/transcribe")
    async def api_transcribe(meeting_id: str):
        meeting_dir = _reunioes_dir(config.vault_path, meeting_id)
        if meeting_dir is None or not meeting_dir.is_dir():
            raise HTTPException(status_code=404, detail="Reunião não encontrada")

        def _run():
            try:
                from ..pipeline import MeetingPipeline

                MeetingPipeline(config).transcribe_existing(meeting_id)
            except Exception:  # noqa: BLE001
                logger.exception("Falha ao re-transcrever via API")

        threading.Thread(target=_run, daemon=True).start()
        return {"ok": True, "queued": True, "meeting_id": meeting_id}

    @app.get("/api/meetings/{meeting_id}/log")
    async def api_meeting_log(meeting_id: str):
        meeting_dir = _reunioes_dir(config.vault_path, meeting_id)
        if meeting_dir is None or not meeting_dir.is_dir():
            raise HTTPException(status_code=404, detail="Reunião não encontrada")
        from .. import generation_log

        return generation_log.read(meeting_dir)

    @app.get("/api/meetings/{meeting_id}/source")
    async def api_meeting_source(meeting_id: str):
        meeting_dir = _reunioes_dir(config.vault_path, meeting_id)
        if meeting_dir is None or not meeting_dir.is_dir():
            raise HTTPException(status_code=404, detail="Reunião não encontrada")
        from ..pipeline import locate_source_file

        src = locate_source_file(config, meeting_dir)
        if src is None:
            return {"exists": False, "name": "", "path": "", "size": None}
        return {"exists": True, "name": src.name, "path": str(src), "size": src.stat().st_size}

    @app.delete("/api/meetings/{meeting_id}/source")
    async def api_delete_meeting_source(meeting_id: str):
        meeting_dir = _reunioes_dir(config.vault_path, meeting_id)
        if meeting_dir is None or not meeting_dir.is_dir():
            raise HTTPException(status_code=404, detail="Reunião não encontrada")
        from .. import generation_log
        from ..pipeline import locate_source_file

        started = datetime.now()
        src = locate_source_file(config, meeting_dir)
        if src is None:
            generation_log.append(
                meeting_dir, "delete_source", "error",
                error=f"Arquivo de origem não encontrado: {meeting_dir.name}",
                started=started, completed=datetime.now(),
            )
            return {"ok": True, "deleted": False}
        try:
            size_mb = src.stat().st_size / 1_048_576
            src.unlink()
        except OSError as e:
            generation_log.append(
                meeting_dir, "delete_source", "error", error=str(e),
                started=started, completed=datetime.now(),
            )
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
        generation_log.append(
            meeting_dir, "delete_source", "ok",
            detail=f"{src.name} ({size_mb:.1f} MB)",
            started=started, completed=datetime.now(),
        )
        return {"ok": True, "deleted": True}
```

3b. In `api_process` (line ~1322), read `mode` and pass the flag. Change the `_run` inner function's process call:

```python
        mode = (payload or {}).get("mode", "full")

        def _run():
            try:
                from ..pipeline import MeetingPipeline

                MeetingPipeline(config).process(path, transcript_only=(mode == "transcript"))
            except Exception:  # noqa: BLE001
                logger.exception("Falha ao processar via API")
```

3c. Let uploads honor the mode too. Change `_process_path_async` (line 1333) to accept the flag, and `api_process_upload` (line 1345) to read a `mode` query param:

```python
    def _process_path_async(path: Path, transcript_only: bool = False) -> None:
        """Dispara o pipeline para um arquivo em uma thread daemon."""
        def _run():
            try:
                from ..pipeline import MeetingPipeline

                MeetingPipeline(config).process(path, transcript_only=transcript_only)
            except Exception:  # noqa: BLE001
                logger.exception("Falha ao processar arquivo enviado")

        threading.Thread(target=_run, daemon=True).start()

    @app.post("/api/process/upload")
    async def api_process_upload(file: UploadFile = File(...), mode: str = "full"):
```

…and at the end of `api_process_upload`, change the call to:

```python
        _process_path_async(dest, transcript_only=(mode == "transcript"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_transcribe_api.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add meeting_processor/web/app.py tests/test_transcribe_api.py
git commit -m "feat: API for re-transcribe, generation log, source mgmt, transcript-only mode"
```

---

## Task 6: Frontend types + hooks

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/hooks/useApi.ts`
- (No standalone test — exercised by component tests in Tasks 7-9.)

- [ ] **Step 1: Add types**

Append to `frontend/src/api/types.ts`:

```typescript
export interface GenerationLogEntry {
  action: "transcript" | "summary" | "delete_source";
  status: "ok" | "error";
  error: string | null;
  detail: string;
  started: string;
  completed: string | null;
}
export interface SourceInfo {
  exists: boolean; name: string; path: string; size: number | null;
}
```

- [ ] **Step 2: Add hooks**

In `frontend/src/hooks/useApi.ts`, add `GenerationLogEntry` and `SourceInfo` to the type import block (lines 4-7), then add these hooks. Add `useTranscribeMeeting` right after `useSummarizeMeeting` (line 169):

```typescript
export function useTranscribeMeeting() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.post(`/api/meetings/${encodeURIComponent(id)}/transcribe`),
    onSuccess: (_d, id) => {
      qc.invalidateQueries({ queryKey: ["status"] });
      qc.invalidateQueries({ queryKey: ["meetings"] });
      qc.invalidateQueries({ queryKey: ["history"] });
      qc.invalidateQueries({ queryKey: ["meeting-log", id] });
    },
  });
}

export const useGenerationLog = (id: string) =>
  useQuery({
    queryKey: ["meeting-log", id],
    queryFn: () => api.get<GenerationLogEntry[]>(`/api/meetings/${encodeURIComponent(id)}/log`),
    enabled: !!id,
    refetchInterval: 4000,
  });

export const useMeetingSource = (id: string) =>
  useQuery({
    queryKey: ["meeting-source", id],
    queryFn: () => api.get<SourceInfo>(`/api/meetings/${encodeURIComponent(id)}/source`),
    enabled: !!id,
  });

export function useDeleteMeetingSource() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.del(`/api/meetings/${encodeURIComponent(id)}/source`),
    onSuccess: (_d, id) => {
      qc.invalidateQueries({ queryKey: ["meeting-source", id] });
      qc.invalidateQueries({ queryKey: ["meeting-log", id] });
    },
  });
}
```

- [ ] **Step 3: Extend process/upload hooks with `mode`**

Replace `useProcessFile` (lines 129-135) and `useUploadFile` (lines 137-148):

```typescript
export function useProcessFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { file: string; mode?: string }) =>
      api.post("/api/process", { file: v.file, mode: v.mode ?? "full" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["meetings"] }),
  });
}

export function useUploadFile() {
  const qc = useQueryClient();
  const [progress, setProgress] = useState<number | null>(null);
  const mutation = useMutation({
    mutationFn: (v: { file: File; mode?: string }) =>
      uploadFile(
        `/api/process/upload?mode=${encodeURIComponent(v.mode ?? "full")}`,
        v.file,
        setProgress,
      ),
    onMutate: () => setProgress(0),
    onSettled: () => setProgress(null),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["meetings"] }),
  });
  return { ...mutation, progress };
}
```

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: errors only in call sites (`Dashboard.tsx` passes a `File`/`string` directly) — those are fixed in Tasks 7-9. If other errors appear, fix them. (It is acceptable for this step to surface the Dashboard call-site errors; they are resolved in Task 9.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/hooks/useApi.ts
git commit -m "feat: frontend hooks for transcribe, generation log, source mgmt"
```

---

## Task 7: MeetingDetail — buttons, source line, log panel

**Files:**
- Create: `frontend/src/components/GenerationLog.tsx`
- Modify: `frontend/src/pages/MeetingDetail.tsx`
- Modify: `frontend/src/__tests__/summarizeButton.test.tsx` (button now always shown)
- Test: `frontend/src/__tests__/generationLog.test.tsx` (new)

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/__tests__/generationLog.test.tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { MeetingDetail } from "../pages/MeetingDetail";
import { ToastProvider } from "../components/Toast";

function setup() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/meetings/abc"]}>
        <ToastProvider>
          <Routes><Route path="/meetings/:id" element={<MeetingDetail />} /></Routes>
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function stub({ exists = true, log = [] as unknown[] } = {}) {
  return vi.fn(async (url: string, opts?: RequestInit) => {
    const u = String(url);
    if (opts?.method === "POST" || opts?.method === "DELETE") {
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    }
    if (u.includes("/source"))
      return new Response(JSON.stringify({ exists, name: "reuniao.mp4", path: "/u/reuniao.mp4", size: 1048576 }), { status: 200 });
    if (u.includes("/log"))
      return new Response(JSON.stringify(log), { status: 200 });
    return new Response(JSON.stringify({ id: "abc", title: "abc", meta: {}, resumo_md: "# Resumo", tasks: [], transcricao_md: "linha" }), { status: 200 });
  });
}

describe("MeetingDetail — generation actions", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("POSTs to transcribe when 'Gerar transcrição' is clicked", async () => {
    const f = stub();
    vi.stubGlobal("fetch", f);
    setup();
    fireEvent.click(await screen.findByRole("button", { name: /Gerar transcrição/i }));
    await waitFor(() =>
      expect(f.mock.calls.some(([url, o]) =>
        String(url).endsWith("/api/meetings/abc/transcribe") && o?.method === "POST")).toBe(true));
  });

  it("disables 'Gerar transcrição' when the source is gone", async () => {
    vi.stubGlobal("fetch", stub({ exists: false }));
    setup();
    await screen.findByText("Resumo");
    const btn = await screen.findByRole("button", { name: /Gerar transcrição/i });
    expect(btn).toBeDisabled();
    expect(screen.getByText(/indisponível/i)).toBeInTheDocument();
  });

  it("renders log entries (ok detail + error reason)", async () => {
    vi.stubGlobal("fetch", stub({ log: [
      { action: "transcript", status: "error", error: "Arquivo de origem não encontrado: x", detail: "", started: "2026-06-05T10:00:00", completed: "2026-06-05T10:00:01" },
      { action: "summary", status: "ok", error: null, detail: "12 tarefas", started: "2026-06-05T09:00:00", completed: "2026-06-05T09:01:00" },
    ] }));
    setup();
    expect(await screen.findByText(/Arquivo de origem não encontrado: x/)).toBeInTheDocument();
    expect(screen.getByText(/12 tarefas/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/__tests__/generationLog.test.tsx`
Expected: FAIL ("Gerar transcrição" button not found).

- [ ] **Step 3: Implement GenerationLog component**

```tsx
// frontend/src/components/GenerationLog.tsx
import { CheckCircle2, XCircle } from "lucide-react";
import type { GenerationLogEntry } from "../api/types";

const ACTION_LABEL: Record<GenerationLogEntry["action"], string> = {
  transcript: "Transcrição",
  summary: "Resumo",
  delete_source: "Exclusão do arquivo",
};

function when(iso: string | null): string {
  if (!iso) return "";
  return iso.replace("T", " ").slice(0, 16);
}

export function GenerationLog({ entries }: { entries: GenerationLogEntry[] }) {
  // Defensive: a misbehaving/edge response could be non-array — never .map a non-array.
  if (!Array.isArray(entries) || entries.length === 0)
    return <p className="text-sm text-slate-500">Nenhuma geração registrada ainda.</p>;
  return (
    <ul className="divide-y divide-slate-100">
      {entries.map((e, i) => {
        const ok = e.status === "ok";
        return (
          <li key={`${e.started}-${i}`} className="flex items-start gap-2 py-2">
            {ok ? (
              <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-emerald-500" />
            ) : (
              <XCircle size={16} className="mt-0.5 shrink-0 text-rose-500" />
            )}
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-slate-700">{ACTION_LABEL[e.action]}</span>
                <span className={`ml-2 shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${
                  ok ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"}`}>
                  {ok ? "OK" : "erro"}
                </span>
              </div>
              {ok && e.detail && <p className="truncate text-xs text-slate-500">{e.detail}</p>}
              {!ok && e.error && <p className="text-xs text-rose-600">{e.error}</p>}
              <p className="text-xs text-slate-400">{when(e.completed || e.started)}</p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
```

- [ ] **Step 4: Rewrite MeetingDetail**

Replace the whole `frontend/src/pages/MeetingDetail.tsx` with:

```tsx
import { useState } from "react";
import { useParams } from "react-router-dom";
import { Sparkles, FileText, Trash2 } from "lucide-react";
import { Card } from "../components/Card";
import { MarkdownView } from "../components/MarkdownView";
import { GenerationLog } from "../components/GenerationLog";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import {
  useMeeting, useSummarizeMeeting, useTranscribeMeeting,
  useGenerationLog, useMeetingSource, useDeleteMeetingSource,
} from "../hooks/useApi";
import { ApiError } from "../api/client";

type Tab = "summary" | "tasks" | "transcript";

function formatBytes(n: number | null): string {
  if (n == null) return "";
  if (n < 1024) return `${n} B`;
  const units = ["KB", "MB", "GB"];
  let v = n / 1024, i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(1)} ${units[i]}`;
}

export function MeetingDetail() {
  const { id = "" } = useParams();
  const meeting = useMeeting(id);
  const summarize = useSummarizeMeeting();
  const transcribe = useTranscribeMeeting();
  const log = useGenerationLog(id);
  const source = useMeetingSource(id);
  const deleteSource = useDeleteMeetingSource();
  const toast = useToast();
  const [tab, setTab] = useState<Tab>("summary");
  const [confirmDelete, setConfirmDelete] = useState(false);

  const obsidianUri = `obsidian://open?path=${encodeURIComponent(id)}`;
  const tabs: { key: Tab; label: string }[] = [
    { key: "summary", label: "Resumo" },
    { key: "tasks", label: "Tarefas" },
    { key: "transcript", label: "Transcrição" },
  ];

  if (meeting.isLoading) return <p className="text-slate-500">Carregando…</p>;
  if (meeting.isError || !meeting.data) return <p className="text-rose-600">Reunião não encontrada.</p>;
  const d = meeting.data;
  const enc = encodeURIComponent(id);
  const sourceGone = source.data ? !source.data.exists : false;

  const generateSummary = () =>
    summarize.mutate(id, {
      onSuccess: () => toast("ok", "Gerando resumo — acompanhe abaixo e no Dashboard."),
      onError: (e) => toast("err", e instanceof ApiError ? e.message : "Erro"),
    });
  const generateTranscript = () =>
    transcribe.mutate(id, {
      onSuccess: () => toast("ok", "Gerando transcrição — acompanhe abaixo."),
      onError: (e) => toast("err", e instanceof ApiError ? e.message : "Erro"),
    });
  const removeSource = () =>
    deleteSource.mutate(id, {
      onSuccess: () => toast("ok", "Arquivo de origem apagado."),
      onError: (e) => toast("err", e instanceof ApiError ? e.message : "Erro"),
    });

  return (
    <Card title={d.title} actions={
      <div className="flex items-center gap-3 text-sm">
        <button onClick={generateTranscript} disabled={transcribe.isPending || sourceGone}
          title={sourceGone ? "Arquivo de origem indisponível" : ""}
          className="flex items-center gap-1 text-brand hover:underline disabled:opacity-40 disabled:no-underline">
          <FileText size={14} /> {transcribe.isPending ? "Enviando…" : "Gerar transcrição"}
        </button>
        <button onClick={generateSummary} disabled={summarize.isPending}
          className="flex items-center gap-1 text-brand hover:underline disabled:opacity-40">
          <Sparkles size={14} /> {summarize.isPending ? "Enviando…" : "Gerar resumo"}
        </button>
        <a href={`/api/meetings/${enc}/export.md`} className="text-brand hover:underline">Markdown</a>
        <a href={`/api/meetings/${enc}/export.docx`} className="text-brand hover:underline">Word</a>
        <a href={obsidianUri} className="text-brand hover:underline">Abrir no Obsidian</a>
      </div>
    }>
      <div className="mb-3 flex items-center gap-3 text-xs text-slate-500">
        <span className="font-medium text-slate-600">Arquivo de origem:</span>
        {source.data?.exists ? (
          <>
            <span>{source.data.name} · {formatBytes(source.data.size)}</span>
            <button onClick={() => setConfirmDelete(true)} disabled={deleteSource.isPending}
              className="flex items-center gap-1 text-slate-400 hover:text-rose-600 disabled:opacity-40">
              <Trash2 size={13} /> Apagar arquivo de origem
            </button>
          </>
        ) : (
          <span className="italic">indisponível</span>
        )}
      </div>

      {(d.meta.purpose || d.meta.meeting_type) && (
        <div className="mb-4 flex items-center gap-2">
          {d.meta.meeting_type && (
            <span className="rounded-full bg-brand/10 px-2.5 py-0.5 text-xs font-medium text-brand">
              {d.meta.meeting_type}
            </span>
          )}
          {d.meta.purpose && <p className="text-sm text-slate-600">{d.meta.purpose}</p>}
        </div>
      )}
      <div className="mb-4 flex gap-1 border-b border-slate-200">
        {tabs.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${
              tab === t.key ? "border-brand text-brand" : "border-transparent text-slate-500 hover:text-slate-700"}`}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === "summary" && (d.resumo_md.trim().length > 0 ? (
        <MarkdownView>{d.resumo_md}</MarkdownView>
      ) : (
        <p className="py-6 text-sm text-slate-500">
          Sem resumo ainda — use "Gerar resumo" acima.
        </p>
      ))}
      {tab === "transcript" && <MarkdownView>{d.transcricao_md}</MarkdownView>}
      {tab === "tasks" && (
        <ul className="space-y-1">
          {d.tasks.length === 0 && <li className="text-slate-500">Sem tarefas.</li>}
          {d.tasks.map((t, i) => (
            <li key={i} className="flex items-center gap-2">
              <input type="checkbox" checked={t.done} readOnly />
              <span className={t.done ? "text-slate-400 line-through" : ""}>{t.description}</span>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-6 border-t border-slate-100 pt-4">
        <h3 className="mb-2 text-sm font-semibold text-slate-700">Log de geração</h3>
        <GenerationLog entries={log.data ?? []} />
      </div>

      <ConfirmDialog open={confirmDelete}
        title="Apagar o arquivo de origem? A transcrição e o resumo são mantidos, mas não será possível gerar a transcrição novamente."
        onConfirm={() => { setConfirmDelete(false); removeSource(); }}
        onCancel={() => setConfirmDelete(false)} />
    </Card>
  );
}
```

- [ ] **Step 5: Update the existing summarize-button test**

In `frontend/src/__tests__/summarizeButton.test.tsx`, the second test now needs updating — "Gerar resumo" is always present. Replace the second `it(...)` block with:

```tsx
  it("shows 'Gerar resumo' even when a summary already exists", async () => {
    vi.stubGlobal("fetch", stubFetch("# Resumo aqui"));
    setup();
    expect(await screen.findByText("Resumo aqui")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Gerar resumo/i })).toBeInTheDocument();
  });
```

Also extend `stubFetch` in that file so the new `/log` and `/source` GETs resolve (otherwise they 404 in the test). Replace its non-POST branch:

```tsx
function stubFetch(resumo_md: string) {
  return vi.fn(async (url: string, opts?: RequestInit) => {
    const u = String(url);
    if (opts?.method === "POST") {
      return new Response(JSON.stringify({ ok: true, queued: true, meeting_id: "abc" }), { status: 200 });
    }
    if (u.includes("/source"))
      return new Response(JSON.stringify({ exists: true, name: "x.mp4", path: "/x.mp4", size: 1 }), { status: 200 });
    if (u.includes("/log")) return new Response(JSON.stringify([]), { status: 200 });
    return new Response(
      JSON.stringify({ id: "abc", title: "abc", meta: {}, resumo_md, tasks: [], transcricao_md: "linha" }),
      { status: 200 },
    );
  });
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/__tests__/generationLog.test.tsx src/__tests__/summarizeButton.test.tsx src/__tests__/meetingDetail.test.tsx`
Expected: PASS (all green). The `meetingDetail.test.tsx` stub returns a plain object for every GET, which already satisfies `/source` and `/log` (missing fields → `undefined`, tolerated).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/GenerationLog.tsx frontend/src/pages/MeetingDetail.tsx frontend/src/__tests__/generationLog.test.tsx frontend/src/__tests__/summarizeButton.test.tsx
git commit -m "feat: meeting detail transcribe/summarize buttons, source mgmt, log panel"
```

---

## Task 8: Meetings list — per-row transcribe / summarize buttons

**Files:**
- Modify: `frontend/src/pages/Meetings.tsx`
- Test: `frontend/src/__tests__/meetings.test.tsx` (append)

- [ ] **Step 1: Write the failing test**

Append a test to `frontend/src/__tests__/meetings.test.tsx`. Its `setup()` already wraps in `ToastProvider`. Update its top import line to add `fireEvent, waitFor`:

```tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
```

Then add this test inside the existing `describe("Meetings list", …)` block:

```tsx
  it("per-row buttons POST to transcribe and summarize", async () => {
    const f = vi.fn(async (url: string, opts?: RequestInit) => {
      const u = String(url);
      if (opts?.method === "POST")
        return new Response(JSON.stringify({ ok: true }), { status: 200 });
      if (u.includes("/api/meetings"))
        return new Response(JSON.stringify([
          { id: "m1", title: "Reunião 1", created: "", duration: "", task_count: 0,
            participants: "", source_file: "", meeting_type: "", purpose: "", has_summary: false },
        ]), { status: 200 });
      if (u.includes("/api/history")) return new Response(JSON.stringify([]), { status: 200 });
      return new Response(JSON.stringify([]), { status: 200 });
    });
    vi.stubGlobal("fetch", f);
    setup();
    const tBtn = await screen.findByRole("button", { name: /Gerar transcrição da Reunião 1/i });
    fireEvent.click(tBtn);
    await waitFor(() =>
      expect(f.mock.calls.some(([url, o]) =>
        String(url).endsWith("/api/meetings/m1/transcribe") && o?.method === "POST")).toBe(true));
  });
```

(If `meetings.test.tsx`'s `setup()` does not already wrap in `ToastProvider`, wrap it — the page now calls `useToast()` for row actions, same as it already does for delete.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/__tests__/meetings.test.tsx`
Expected: FAIL (button "Gerar transcrição da Reunião 1" not found).

- [ ] **Step 3: Implement**

In `frontend/src/pages/Meetings.tsx`:

3a. Update imports:

```tsx
import { Trash2, Search, FileText, Sparkles } from "lucide-react";
import { useMeetings, useDeleteMeeting, useHistory, useTranscribeMeeting, useSummarizeMeeting } from "../hooks/useApi";
```

3b. Inside the component, add the mutations:

```tsx
  const transcribe = useTranscribeMeeting();
  const summarize = useSummarizeMeeting();
```

3c. Add handlers (above the `return`):

```tsx
  const runTranscribe = (id: string) =>
    transcribe.mutate(id, {
      onSuccess: () => toast("ok", "Gerando transcrição — acompanhe no Dashboard."),
      onError: (e) => toast("err", e instanceof ApiError ? e.message : "Erro"),
    });
  const runSummarize = (id: string) =>
    summarize.mutate(id, {
      onSuccess: () => toast("ok", "Gerando resumo — acompanhe no Dashboard."),
      onError: (e) => toast("err", e instanceof ApiError ? e.message : "Erro"),
    });
```

3d. Replace the actions cell (the `<td className="text-right">` block, lines 63-65) with:

```tsx
                <td className="text-right">
                  <div className="flex items-center justify-end gap-2">
                    <button onClick={() => runTranscribe(m.id)} disabled={transcribe.isPending}
                      aria-label={`Gerar transcrição da ${m.title}`} title="Gerar transcrição"
                      className="text-slate-400 hover:text-brand disabled:opacity-40">
                      <FileText size={16} />
                    </button>
                    <button onClick={() => runSummarize(m.id)} disabled={summarize.isPending}
                      aria-label={`Gerar resumo da ${m.title}`} title="Gerar resumo"
                      className="text-slate-400 hover:text-brand disabled:opacity-40">
                      <Sparkles size={16} />
                    </button>
                    <button onClick={() => setPending(m.id)}
                      aria-label={`Apagar ${m.title}`} title="Apagar"
                      className="text-slate-400 hover:text-rose-600">
                      <Trash2 size={16} />
                    </button>
                  </div>
                </td>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/__tests__/meetings.test.tsx`
Expected: PASS (all green).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Meetings.tsx frontend/src/__tests__/meetings.test.tsx
git commit -m "feat: per-row transcribe/summarize buttons on meetings list"
```

---

## Task 9: Dashboard — "Apenas transcrição" checkbox

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`
- Test: `frontend/src/__tests__/dashboardTranscript.test.tsx` (new)

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/__tests__/dashboardTranscript.test.tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { Dashboard } from "../pages/Dashboard";
import { ToastProvider } from "../components/Toast";

function setup() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ToastProvider><Dashboard /></ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Dashboard — transcript-only", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("sends mode=transcript when 'Apenas transcrição' is checked", async () => {
    const f = vi.fn(async (url: string, opts?: RequestInit) => {
      if (opts?.method === "POST")
        return new Response(JSON.stringify({ ok: true, queued: true }), { status: 200 });
      return new Response(JSON.stringify({}), { status: 200 });
    });
    vi.stubGlobal("fetch", f);
    setup();

    fireEvent.click(screen.getByLabelText(/Apenas transcrição/i));
    const input = screen.getByPlaceholderText(/reuniao\.mp4/i);
    fireEvent.change(input, { target: { value: "/v/x.mp4" } });
    fireEvent.click(screen.getByRole("button", { name: /Processar caminho/i }));

    await waitFor(() => {
      const call = f.mock.calls.find(([url, o]) =>
        String(url).endsWith("/api/process") && o?.method === "POST");
      expect(call).toBeTruthy();
      expect(JSON.parse(String(call![1]!.body))).toMatchObject({ file: "/v/x.mp4", mode: "transcript" });
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/__tests__/dashboardTranscript.test.tsx`
Expected: FAIL (checkbox not found / body lacks `mode`).

- [ ] **Step 3: Implement**

In `frontend/src/pages/Dashboard.tsx`:

3a. Add state near the other `useState`s (after line 35):

```tsx
  const [transcriptOnly, setTranscriptOnly] = useState(false);
```

3b. Update `submit` and `submitUpload` to pass the object shape + mode:

```tsx
  const submit = () => {
    if (!file.trim()) return;
    process.mutate(
      { file: file.trim(), mode: transcriptOnly ? "transcript" : "full" },
      {
        onSuccess: () => { toast("ok", "Processamento enfileirado."); setFile(""); },
        onError: (e) => toast("err", e instanceof ApiError ? e.message : "Erro"),
      },
    );
  };

  const submitUpload = () => {
    if (!selected) return;
    upload.mutate(
      { file: selected, mode: transcriptOnly ? "transcript" : "full" },
      {
        onSuccess: () => {
          toast("ok", "Arquivo enviado — processando.");
          setSelected(null);
          if (fileInputRef.current) fileInputRef.current.value = "";
        },
        onError: (e) => toast("err", e instanceof ApiError ? e.message : "Erro no envio"),
      },
    );
  };
```

3c. Add the checkbox inside the "Processar um arquivo" `Card`, right after the opening `<div className="flex flex-col gap-4">` (line 90):

```tsx
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input type="checkbox" checked={transcriptOnly}
              onChange={(e) => setTranscriptOnly(e.target.checked)} />
            Apenas transcrição (sem resumo)
          </label>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/__tests__/dashboardTranscript.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx frontend/src/__tests__/dashboardTranscript.test.tsx
git commit -m "feat: transcript-only checkbox on the Dashboard process card"
```

---

## Task 10: Full suite, typecheck, SPA build

**Files:** none (verification + build artifacts)

- [ ] **Step 1: Backend — full test suite**

Run: `.venv/bin/pytest -q`
Expected: PASS (all tests, including the new modules and the untouched suites).

- [ ] **Step 2: Frontend — typecheck + full test suite**

Run: `cd frontend && npx tsc --noEmit && npx vitest run`
Expected: PASS (no type errors; all test files green).

- [ ] **Step 3: Build the SPA**

The backend serves a pre-built SPA from `meeting_processor/web/spa/`. Rebuild it so the new UI ships:

Run: `cd frontend && npm run build`
Expected: build succeeds; updated assets emitted to `meeting_processor/web/spa/` (per `vite.config.ts` outDir).

Verify the output landed: `git status --short meeting_processor/web/spa/` should show changed `assets/*` files.

- [ ] **Step 4: Manual smoke (optional but recommended)**

Use the `run` skill (or `./start_web.sh`) to launch the app. On a meeting detail page, confirm: "Gerar transcrição"/"Gerar resumo" buttons appear, the "Log de geração" panel renders, and the "Arquivo de origem" line shows status. Trigger "Gerar transcrição" on a meeting whose source still exists and confirm an OK entry appears in the log.

- [ ] **Step 5: Commit the build**

```bash
git add meeting_processor/web/spa
git commit -m "build: rebuild SPA with transcript/summary regen UI"
```

---

## Self-Review notes (for the implementer)

- **`format_duration` / `extract_audio`** are already imported in `pipeline.py` — no new import needed for them. Only `re` and `from . import generation_log` are added.
- **Existing test churn:** `summarizeButton.test.tsx` is intentionally updated in Task 7 (the "hide when summary exists" behavior is reversed by design). No other existing test should change behavior; if `meetings.test.tsx`/`meetingDetail.test.tsx` reference the old actions cell, adjust selectors as needed.
- **Type consistency:** the hook object shapes (`{ file, mode }` for both `useProcessFile` and `useUploadFile`) must match the call sites updated in Task 9 — do Task 6 and Task 9 together if running inline.
- **Security:** `locate_source_file` only ever returns paths under `uploads/` or `watch_dir`, so `DELETE /source` can never unlink an arbitrary path. `_reunioes_dir` already guards meeting-id path traversal.
