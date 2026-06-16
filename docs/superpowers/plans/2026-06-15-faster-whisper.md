# faster-whisper + parallel diarization + word timestamps — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a faster-whisper backend (default, ~4x faster, openai fallback), run diarization concurrently with transcription, and capture/surface word-level timestamps in the click-to-seek transcript.

**Architecture:** A new `_transcribe_faster` backend returning the same `Transcript` (now with optional per-word times); pyannote runs in a thread alongside transcription; word times persist as a sidecar `.words.json`, served by a `/words` endpoint and consumed by `TranscriptPlayer` (word-level, with segment-level fallback).

**Tech Stack:** Python 3.14, faster-whisper/CTranslate2, FastAPI; React/Vitest. Run Python tests `.venv/bin/python -m pytest`; frontend from `frontend/` `npx vitest run <f>` + `npx tsc --noEmit`.

---

## File Structure
- **Modify** `meeting_processor/models.py` — `WordTime` + `TranscriptSegment.words`.
- **Modify** `meeting_processor/transcriber.py` — `_faster_model_name`, `_transcribe_faster`, dispatch.
- **Modify** `meeting_processor/config.py` — `whisper_compute_type`, default backend `faster`.
- **Modify** `requirements.txt` — add `faster-whisper`.
- **Modify** `meeting_processor/pipeline.py` — `_start_diarization`/`_finish_diarization`.
- **Modify** `meeting_processor/note_generator.py` — sidecar `.words.json`.
- **Modify** `meeting_processor/web/app.py` — `GET /api/meetings/{id}/words`.
- **Modify** `frontend/src/{api/types.ts,hooks/useApi.ts,components/TranscriptPlayer.tsx,pages/MeetingDetail.tsx}`.
- **Create** `tests/test_faster_whisper.py`, `tests/test_parallel_diarization.py`, `tests/test_word_timestamps.py`, `frontend/src/__tests__/wordTimestamps.test.tsx`.

---

### Task 1: Model — `WordTime` + `TranscriptSegment.words`

**Files:** Modify `meeting_processor/models.py`; Test: `tests/test_faster_whisper.py`.

- [ ] **Step 1: Write the failing test** — create `tests/test_faster_whisper.py`:

```python
"""faster-whisper backend + word timestamps."""
from meeting_processor.models import TranscriptSegment, WordTime


def test_segment_words_default_none():
    s = TranscriptSegment(start=0, end=1, text="oi")
    assert s.words is None


def test_segment_with_words():
    w = WordTime(start=0.0, end=0.5, text="oi")
    s = TranscriptSegment(start=0, end=1, text="oi", words=[w])
    assert s.words[0].text == "oi" and s.words[0].end == 0.5
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_faster_whisper.py -q`
Expected: FAIL — `WordTime` doesn't exist / `words` not a field.

- [ ] **Step 3: Add to `meeting_processor/models.py`** (above `TranscriptSegment`):

```python
class WordTime(BaseModel):
    start: float
    end: float
    text: str
```

and add the field to `TranscriptSegment` (after `speaker`):

```python
    words: list[WordTime] | None = None
```

(Leave the `display_text` property unchanged.)

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_faster_whisper.py -q` → 2 pass.

- [ ] **Step 5: Commit**

```bash
git add meeting_processor/models.py tests/test_faster_whisper.py
git commit -m "feat(transcribe): WordTime model + TranscriptSegment.words"
```

---

### Task 2: faster-whisper backend

**Files:** Modify `meeting_processor/transcriber.py`, `meeting_processor/config.py`, `requirements.txt`; Test: `tests/test_faster_whisper.py`.

- [ ] **Step 1: Append the failing tests** to `tests/test_faster_whisper.py`:

```python
# --- Task 2: faster-whisper backend ----------------------------------------

import sys
import types

from meeting_processor.transcriber import WhisperTranscriber, _faster_model_name


class _FakeWord:
    def __init__(self, start, end, word):
        self.start, self.end, self.word = start, end, word


class _FakeSeg:
    def __init__(self, start, end, text, words=None):
        self.start, self.end, self.text, self.words = start, end, text, words


def _install_fake_faster(monkeypatch, segs, duration):
    mod = types.ModuleType("faster_whisper")

    class FakeModel:
        def __init__(self, *a, **k):
            pass

        def transcribe(self, *a, **k):
            info = types.SimpleNamespace(duration=duration)
            return iter(segs), info

    mod.WhisperModel = FakeModel
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)


def test_faster_model_name():
    assert _faster_model_name("large") == "large-v3"
    assert _faster_model_name("medium") == "medium"
    assert _faster_model_name("large-v3") == "large-v3"


def test_transcribe_faster_builds_transcript_with_words(config, monkeypatch):
    segs = [
        _FakeSeg(0.0, 1.0, " oi", [_FakeWord(0.0, 0.5, " oi")]),
        _FakeSeg(1.0, 2.0, " tchau", [_FakeWord(1.0, 1.8, " tchau")]),
    ]
    _install_fake_faster(monkeypatch, segs, duration=2.0)
    t = WhisperTranscriber(config)._transcribe_faster("/tmp/x.wav", None, "large")
    assert [s.text for s in t.segments] == ["oi", "tchau"]
    assert t.duration == 2.0
    assert t.full_text == "oi tchau"
    assert t.segments[0].words[0].text == "oi"


def test_transcribe_faster_falls_back_when_not_installed(config, monkeypatch):
    monkeypatch.setitem(sys.modules, "faster_whisper", None)  # import → ImportError
    called = {}
    monkeypatch.setattr(
        WhisperTranscriber, "_transcribe_openai",
        lambda self, a, p, m: called.setdefault("openai", True),
    )
    WhisperTranscriber(config)._transcribe_faster("/tmp/x.wav", None, "large")
    assert called.get("openai") is True


def test_dispatch_routes_to_faster(config, monkeypatch):
    config.whisper_backend = "faster"
    monkeypatch.setattr(
        WhisperTranscriber, "_transcribe_faster",
        lambda self, a, p, m: "FASTER",
    )
    assert WhisperTranscriber(config).transcribe("/tmp/x.wav") == "FASTER"


def test_compute_type_and_backend_defaults(config):
    assert config.whisper_compute_type == "int8"
    assert config.whisper_backend == "faster"
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_faster_whisper.py -k "faster or dispatch or compute" -q`
Expected: FAIL — `_faster_model_name`/`_transcribe_faster` missing; config defaults differ.

- [ ] **Step 3: Config.** In `meeting_processor/config.py`, change the `whisper_backend` default and add `whisper_compute_type`:

```python
    #   "faster" -> faster-whisper (CTranslate2; padrão, ~4x, fallback openai)
    #   "auto"   -> faster-whisper, senão whisper.cpp, senão openai-whisper
    #   "cpp"    -> força whisper.cpp
    #   "openai" -> força openai-whisper
    whisper_backend: str = "faster"
    whisper_compute_type: str = "int8"  # int8 (rápido/baixa RAM) | auto | int8_float16
```

In `load_config` `string_overrides`, add:

```python
        "MEETING_WHISPER_COMPUTE_TYPE": "whisper_compute_type",
```

- [ ] **Step 4: Backend.** In `meeting_processor/transcriber.py`:
  - Add `WordTime` to the models import: `from .models import Transcript, TranscriptSegment, WordTime`.
  - Add the name map (top-level, near `select_whisper_model`):

```python
_FASTER_NAMES = {"large": "large-v3"}


def _faster_model_name(name: str) -> str:
    """openai-whisper -> id do faster-whisper (large -> large-v3); resto passa direto."""
    return _FASTER_NAMES.get(name, name)
```

  - In `WhisperTranscriber.transcribe`, add a `faster` branch and make `auto` prefer it. Replace the dispatch body with:

```python
        backend = (self.config.whisper_backend or "faster").lower()
        if backend == "openai":
            return self._transcribe_openai(audio_path, progress_callback, model)
        if backend == "cpp":
            return self._transcribe_cpp(audio_path, progress_callback)
        if backend == "faster":
            return self._transcribe_faster(audio_path, progress_callback, model)
        # auto: faster-whisper, senão whisper.cpp, senão openai
        import importlib.util
        if importlib.util.find_spec("faster_whisper") is not None:
            return self._transcribe_faster(audio_path, progress_callback, model)
        if resolve_whisper_cli(self.config) is not None:
            return self._transcribe_cpp(audio_path, progress_callback)
        logger.info("whisper.cpp nao encontrado; usando openai-whisper (pip).")
        return self._transcribe_openai(audio_path, progress_callback, model)
```

(Keep whatever the current `auto` branch's cpp/openai logic was — the above
preserves it with faster-whisper preferred. If `resolve_whisper_cli` isn't the
exact symbol used, mirror the existing `auto` code and just prepend the
faster-whisper check.)

  - Add the method (after `_transcribe_openai`):

```python
    def _transcribe_faster(self, audio_path, progress_callback=None, model=None):
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            logger.warning("faster-whisper não instalado; usando openai-whisper.")
            return self._transcribe_openai(audio_path, progress_callback, model)

        model_name = _faster_model_name(model or self.config.whisper_model)
        ctx = {"model": model_name}
        try:
            wm = WhisperModel(
                model_name,
                device=self.config.whisper_device,
                compute_type=self.config.whisper_compute_type,
            )
            if progress_callback:
                progress_callback(15, "Transcrevendo áudio (faster-whisper)...")
            seg_iter, info = wm.transcribe(
                str(audio_path),
                language=self.config.whisper_language,
                initial_prompt=self.config.whisper_initial_prompt or None,
                vad_filter=True,
                word_timestamps=True,
            )
            segments = []
            for s in seg_iter:
                text = (s.text or "").strip()
                if not text:
                    continue
                words = [
                    WordTime(start=float(w.start), end=float(w.end), text=(w.word or "").strip())
                    for w in (getattr(s, "words", None) or [])
                    if (w.word or "").strip()
                ] or None
                segments.append(
                    TranscriptSegment(start=float(s.start), end=float(s.end), text=text, words=words)
                )
        except Exception as e:  # noqa: BLE001
            _log_run_failure(self.config, "faster", ctx, e)
            raise

        duration = float(getattr(info, "duration", 0.0)) or (segments[-1].end if segments else 0.0)
        full_text = " ".join(s.text for s in segments)
        if progress_callback:
            progress_callback(100, f"{len(segments)} segmentos, {duration/60:.1f} min")
        logger.info("Transcrição (faster-whisper): %d segmentos, %.1f min.", len(segments), duration / 60)
        return Transcript(
            segments=segments, full_text=full_text,
            language=self.config.whisper_language, duration=duration,
        )
```

- [ ] **Step 5: Add the dependency.** In `requirements.txt`, add under the whisper line:

```
faster-whisper>=1.0  # backend de transcrição padrão (CTranslate2); openai-whisper é fallback
```

- [ ] **Step 6: Run tests**

Run: `.venv/bin/python -m pytest tests/test_faster_whisper.py -q` → all pass (the fake module + fallback + dispatch + config).
Confirm import: `.venv/bin/python -c "import meeting_processor.transcriber"`.

- [ ] **Step 7: Commit**

```bash
git add meeting_processor/transcriber.py meeting_processor/config.py requirements.txt tests/test_faster_whisper.py
git commit -m "feat(transcribe): faster-whisper backend (default) + word capture + openai fallback"
```

---

### Task 3: Parallel transcription + diarization

**Files:** Modify `meeting_processor/pipeline.py`; Test: `tests/test_parallel_diarization.py`.

- [ ] **Step 1: Write the failing tests** — create `tests/test_parallel_diarization.py`:

```python
"""Diarização rodando em paralelo com a transcrição."""
from meeting_processor import diarizer
from meeting_processor.models import Transcript, TranscriptSegment
from meeting_processor.pipeline import MeetingPipeline


def _t():
    s = TranscriptSegment(start=0, end=1, text="oi")
    return Transcript(segments=[s], full_text="oi", language="pt", duration=1)


def test_diarization_disabled_noop(config):
    config.enable_diarization = False
    pipe = MeetingPipeline(config)
    h = pipe._start_diarization("/tmp/x.wav")
    assert h is None
    t = _t()
    pipe._finish_diarization(h, t)
    assert t.segments[0].speaker is None


def test_diarization_enabled_assigns(config, monkeypatch):
    config.enable_diarization = True
    monkeypatch.setattr(diarizer, "diarize", lambda audio, cfg: [(0.0, 1.0, "SPEAKER_00")])
    pipe = MeetingPipeline(config)
    h = pipe._start_diarization("/tmp/x.wav")
    t = _t()
    pipe._finish_diarization(h, t)
    assert t.segments[0].speaker == "Falante 1"


def test_diarization_failure_is_swallowed(config, monkeypatch):
    config.enable_diarization = True
    def boom(audio, cfg):
        raise RuntimeError("kaboom")
    monkeypatch.setattr(diarizer, "diarize", boom)
    pipe = MeetingPipeline(config)
    h = pipe._start_diarization("/tmp/x.wav")
    t = _t()
    pipe._finish_diarization(h, t)   # must not raise
    assert t.segments[0].speaker is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_parallel_diarization.py -q`
Expected: FAIL — `_start_diarization`/`_finish_diarization` don't exist.

- [ ] **Step 3: Replace `_maybe_diarize`** in `meeting_processor/pipeline.py` with the start/finish pair:

```python
    def _start_diarization(self, audio_path):
        """Submete a diarização a uma thread (roda junto com a transcrição)."""
        if not self.config.enable_diarization:
            return None
        try:
            from concurrent.futures import ThreadPoolExecutor
            from .diarizer import diarize
            ex = ThreadPoolExecutor(max_workers=1)
            return (ex, ex.submit(diarize, audio_path, self.config))
        except Exception as e:  # noqa: BLE001
            logger.warning("Falha ao iniciar diarizacao (nao critico): %s", e)
            return None

    def _finish_diarization(self, handle, transcript):
        """Junta os turnos e atribui falantes. Nunca derruba o pipeline."""
        if handle is None:
            return
        ex, fut = handle
        try:
            from .diarizer import assign_speakers
            turns = fut.result()
            assign_speakers(transcript.segments, turns)
            logger.info("Diarizacao: %d turnos.", len(turns))
        except Exception as e:  # noqa: BLE001
            logger.warning("Falha na diarizacao (nao critico): %s", e)
        finally:
            ex.shutdown(wait=False)
```

- [ ] **Step 4: Wire `process()`.** Find the transcription block. Immediately BEFORE the
`# Etapa 2: Transcrever` log line, add:

```python
            diar = self._start_diarization(audio_path)
```

and REPLACE the existing `self._maybe_diarize(transcript, audio_path)` line (after the
transcription progress/`_check_cancel`, before `# Salvar transcrição`) with:

```python
            self._finish_diarization(diar, transcript)
```

- [ ] **Step 5: Run tests + regression**

Run: `.venv/bin/python -m pytest tests/test_parallel_diarization.py tests/test_diarization.py -q`
Expected: all pass (the old diarization unit tests for `diarize`/`assign_speakers` are untouched; only the pipeline hook moved).
Confirm `.venv/bin/python -c "import meeting_processor.pipeline"`.

- [ ] **Step 6: Commit**

```bash
git add meeting_processor/pipeline.py tests/test_parallel_diarization.py
git commit -m "feat(transcribe): run diarization in parallel with transcription"
```

---

### Task 4: Word-timestamp sidecar persistence

**Files:** Modify `meeting_processor/note_generator.py`; Test: `tests/test_word_timestamps.py`.

- [ ] **Step 1: Write the failing tests** — create `tests/test_word_timestamps.py`:

```python
"""Persistência de timestamps por palavra (sidecar .words.json)."""
import json

from meeting_processor.models import Transcript, TranscriptSegment, WordTime
from meeting_processor.note_generator import NoteGenerator


def _paths(config, ng):
    from datetime import datetime
    return ng.prepare("reuniao.mp4", datetime(2026, 1, 1, 10, 0, 0))


def test_sidecar_written_when_words_present(config):
    ng = NoteGenerator(config)
    paths = _paths(config, ng)
    seg = TranscriptSegment(start=0, end=1, text="oi", words=[WordTime(start=0, end=0.5, text="oi")])
    ng.write_transcription(Transcript(segments=[seg], full_text="oi", language="pt", duration=1), paths)
    sidecar = paths.raw_path.with_suffix(".words.json")
    assert sidecar.exists()
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert data[0]["text"] == "oi" and data[0]["words"][0]["text"] == "oi"


def test_no_sidecar_without_words(config):
    ng = NoteGenerator(config)
    paths = _paths(config, ng)
    seg = TranscriptSegment(start=0, end=1, text="oi")  # words=None
    ng.write_transcription(Transcript(segments=[seg], full_text="oi", language="pt", duration=1), paths)
    assert not paths.raw_path.with_suffix(".words.json").exists()
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_word_timestamps.py -q`
Expected: FAIL — no sidecar written.

- [ ] **Step 3: Write the sidecar.** In `meeting_processor/note_generator.py`, add the import
`from .utils import write_json_atomic` (if not present), and change `write_transcription`:

```python
    def write_transcription(self, transcript: Transcript, paths: MeetingPaths) -> None:
        """Salva a transcrição bruta (sempre) + sidecar de palavras quando houver."""
        self._write_raw_transcription(transcript, paths.raw_path)
        logger.info("Transcricao bruta salva: %s", paths.raw_path)
        if any(s.words for s in transcript.segments):
            words_path = paths.raw_path.with_suffix(".words.json")
            write_json_atomic(words_path, [s.model_dump() for s in transcript.segments])
            logger.info("Timestamps por palavra salvos: %s", words_path)
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_word_timestamps.py -q` → 2 pass.

- [ ] **Step 5: Commit**

```bash
git add meeting_processor/note_generator.py tests/test_word_timestamps.py
git commit -m "feat(transcribe): persist word timestamps as a sidecar .words.json"
```

---

### Task 5: `GET /api/meetings/{id}/words`

**Files:** Modify `meeting_processor/web/app.py`; Test: `tests/test_word_timestamps.py`.

- [ ] **Step 1: Append the failing tests:**

```python
# --- Task 5: /words endpoint -----------------------------------------------


def test_words_endpoint_serves_sidecar(client, config):
    mid = "2026-01-01 10h00 - reu"
    d = config.reunioes_path / mid
    d.mkdir(parents=True, exist_ok=True)
    (d / f"Transcricao - {mid}.md").write_text("# Transcricao\n", encoding="utf-8")
    (d / f"Transcricao - {mid}.words.json").write_text(
        '[{"start":0,"end":1,"text":"oi","speaker":null,"words":[{"start":0,"end":0.5,"text":"oi"}]}]',
        encoding="utf-8",
    )
    r = client.get(f"/api/meetings/{mid}/words")
    assert r.status_code == 200
    assert r.json()[0]["words"][0]["text"] == "oi"


def test_words_endpoint_404_when_absent(client, config):
    mid = "2026-01-02 10h00 - sem"
    (config.reunioes_path / mid).mkdir(parents=True, exist_ok=True)
    assert client.get(f"/api/meetings/{mid}/words").status_code == 404
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_word_timestamps.py -k words_endpoint -q`
Expected: FAIL — route missing (404 for the served case too).

- [ ] **Step 3: Add the endpoint.** In `meeting_processor/web/app.py`, after `api_meeting_media`, add:

```python
    @app.get("/api/meetings/{meeting_id}/words")
    async def api_meeting_words(meeting_id: str):
        """Timestamps por palavra (sidecar .words.json), se houver."""
        meeting_dir = _reunioes_dir(config.vault_path, meeting_id)
        if meeting_dir is None or not meeting_dir.is_dir():
            raise HTTPException(status_code=404, detail="Reunião não encontrada")
        hits = list(meeting_dir.glob("Transcricao - *.words.json"))
        if not hits:
            raise HTTPException(status_code=404, detail="Sem timestamps por palavra")
        return json.loads(hits[0].read_text(encoding="utf-8"))
```

(`json` is already imported at the top of `app.py`.)

- [ ] **Step 4: Run tests + full suite**

Run: `.venv/bin/python -m pytest tests/test_word_timestamps.py -q` → 4 pass.
Run: `.venv/bin/python -m pytest -q` → all pass (1 skipped anthropic).
Confirm `.venv/bin/python -c "import meeting_processor.web.app"`.

- [ ] **Step 5: Commit**

```bash
git add meeting_processor/web/app.py tests/test_word_timestamps.py
git commit -m "feat(web): /api/meetings/{id}/words endpoint (sidecar word timestamps)"
```

---

### Task 6: Frontend — word-level player

**Files:** Modify `frontend/src/api/types.ts`, `frontend/src/hooks/useApi.ts`, `frontend/src/components/TranscriptPlayer.tsx`, `frontend/src/pages/MeetingDetail.tsx`; Create `frontend/src/__tests__/wordTimestamps.test.tsx`.

- [ ] **Step 1: Write the failing test** — create `frontend/src/__tests__/wordTimestamps.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { TranscriptPlayer } from "../components/TranscriptPlayer";

const WORDS = [
  { start: 0, end: 1, text: "oi", speaker: null, words: [
    { start: 0, end: 0.5, text: "oi" }, { start: 0.5, end: 1, text: "mundo" },
  ] },
];

describe("TranscriptPlayer word-level", () => {
  beforeEach(() => {
    let ct = 0;
    Object.defineProperty(HTMLMediaElement.prototype, "currentTime", {
      configurable: true, get: () => ct, set: (v) => { ct = v; },
    });
    Object.defineProperty(HTMLMediaElement.prototype, "play", { configurable: true, value: vi.fn() });
  });

  it("renders word spans and seeks to a word on click", () => {
    const { container } = render(
      <TranscriptPlayer meetingId="m1" markdown={"**[00:00]** oi mundo"} hasSource words={WORDS} />,
    );
    const video = container.querySelector("video")!;
    fireEvent.click(screen.getByRole("button", { name: /Ir para palavra: mundo/i }));
    expect(video.currentTime).toBe(0.5);
  });

  it("falls back to segment-level when words is null", () => {
    const { container } = render(
      <TranscriptPlayer meetingId="m1" markdown={"**[00:05]** oi"} hasSource words={null} />,
    );
    expect(container.querySelector("video")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Ir para 00:05/i })).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run (from `frontend/`): `npx vitest run src/__tests__/wordTimestamps.test.tsx`
Expected: FAIL — `TranscriptPlayer` doesn't accept `words` / no word spans.

- [ ] **Step 3: Type + hook.**
  - `frontend/src/api/types.ts` — add:
    ```ts
    export interface WordTime { start: number; end: number; text: string; }
    export interface WordSegment { start: number; end: number; text: string; speaker: string | null; words: WordTime[] | null; }
    ```
  - `frontend/src/hooks/useApi.ts` — add (after `useMeetingSource`):
    ```ts
    export const useMeetingWords = (id: string) =>
      useQuery({
        queryKey: ["meeting-words", id],
        queryFn: async () => {
          try { return await api.get<import("../api/types").WordSegment[]>(`/api/meetings/${encodeURIComponent(id)}/words`); }
          catch { return null; }   // 404 → no word timestamps
        },
      });
    ```

- [ ] **Step 4: `TranscriptPlayer` word-level mode.** In `frontend/src/components/TranscriptPlayer.tsx`,
add a `words?: WordSegment[] | null` prop and a word-level branch BEFORE the existing
segment-level body. Change the signature and add the branch:

```tsx
import type { WordSegment } from "../api/types";

export function TranscriptPlayer({
  meetingId, markdown, hasSource, words = null,
}: {
  meetingId: string; markdown: string; hasSource: boolean; words?: WordSegment[] | null;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [curTime, setCurTime] = useState(0);

  const mediaSrc = `/api/meetings/${encodeURIComponent(meetingId)}/media`;
  const seekTo = (s: number) => {
    const v = videoRef.current;
    if (v) { v.currentTime = s; void v.play(); }
  };

  // Word-level view when the sidecar payload is available.
  if (hasSource && words && words.length > 0) {
    return (
      <div className="flex flex-col gap-4">
        <video ref={videoRef} controls preload="metadata" onTimeUpdate={() => setCurTime(videoRef.current?.currentTime ?? 0)}
          src={mediaSrc} className="w-full rounded-lg bg-black" />
        <p className="text-sm leading-7 text-ink-soft">
          {words.flatMap((seg, si) =>
            (seg.words ?? []).map((w, wi) => {
              const active = curTime >= w.start && curTime < w.end;
              return (
                <button key={`${si}-${wi}`} onClick={() => seekTo(w.start)}
                  aria-label={`Ir para palavra: ${w.text}`}
                  className={active ? "rounded bg-brand/20 px-0.5" : "px-0.5 hover:bg-line-soft"}>
                  {w.text}{" "}
                </button>
              );
            }),
          )}
        </p>
      </div>
    );
  }
  // ... existing segment-level body unchanged (parseTranscript + [MM:SS] buttons + fallback) ...
```

(Keep the rest of the existing function — the `parseTranscript(markdown)` segment path and
the `!hasSource || segments.length === 0` MarkdownView fallback — exactly as is below the
new branch. The existing `activeIdx`/`seek`/`onTime` for the segment path stay.)

- [ ] **Step 5: Wire `MeetingDetail.tsx`.** Add `useMeetingWords` to the `../hooks/useApi`
import; near the other hooks add `const words = useMeetingWords(id);`; pass it to the player —
change the transcript-tab line to:

```tsx
        {tab === "transcript" && (
          <TranscriptPlayer meetingId={id} markdown={d.transcricao_md}
            hasSource={source.data?.exists ?? false} words={words.data ?? null} />
        )}
```

- [ ] **Step 6: Test + typecheck + full suite**

Run (from `frontend/`): `npx vitest run src/__tests__/wordTimestamps.test.tsx` (2 pass);
`npx tsc --noEmit` (0); `npx vitest run` (all pass — the existing `transcriptPlayer.test.tsx`
calls `<TranscriptPlayer ...>` WITHOUT `words`, which defaults to `null` → the segment-level
path runs unchanged; confirm it still passes).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/hooks/useApi.ts frontend/src/components/TranscriptPlayer.tsx frontend/src/pages/MeetingDetail.tsx frontend/src/__tests__/wordTimestamps.test.tsx
git commit -m "feat(ui): word-level transcript player (sidecar words) with segment fallback"
```

---

## Self-Review

**Spec coverage:** §1 model+backend (`WordTime`/`words`, `_faster_model_name`, `_transcribe_faster` w/ `word_timestamps`, dispatch+default, `whisper_compute_type`, requirements) → Tasks 1–2. §2 parallel diarization (`_start`/`_finish`, removed `_maybe_diarize`) → Task 3. §3 persist (sidecar) → Task 4; serve (`/words`) → Task 5; play (word-level + fallback) → Task 6. Testing across all. Out-of-scope (WhisperX, voice ID, removing openai, markdown format) untouched. ✓

**Placeholder scan:** none — every step has concrete code/commands.

**Type consistency:** `WordTime`/`TranscriptSegment.words` (Task 1) consumed by `_transcribe_faster` (Task 2), the sidecar dump (Task 4), and mirrored in TS `WordTime`/`WordSegment` (Task 6). `_faster_model_name`/`_transcribe_faster` signatures match the tests + dispatch. `whisper_compute_type`/`whisper_backend="faster"` (Task 2) read in the backend + tests. `_start_diarization`/`_finish_diarization(handle, transcript)` (Task 3) match the tests + `process()` wiring. The `/api/meetings/{id}/words` route (Task 5) matches `useMeetingWords` (Task 6). `TranscriptPlayer` gains optional `words` defaulting `null` so the existing `transcriptPlayer.test.tsx` (no `words` arg) is unaffected. `paths.raw_path.with_suffix(".words.json")` is the same path the endpoint globs. ✓
