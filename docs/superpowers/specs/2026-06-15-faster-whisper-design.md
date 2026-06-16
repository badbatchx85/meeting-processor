# faster-whisper backend + parallel diarization

**Date:** 2026-06-15
**Status:** Approved design

## Goal

Make transcription ~3–4x faster (and use ~1/3 the RAM) by adding a
`faster-whisper` (CTranslate2) backend as the default — same large-v3 quality —
while keeping `openai-whisper` as a fallback. Run pyannote diarization
**concurrently** with transcription so "quem falou" costs no extra wall-clock.

## Background (exact, from exploration)

- `WhisperTranscriber.transcribe(audio_path, progress_callback=None, model=None)`
  (`transcriber.py`) dispatches by `config.whisper_backend`:
  `"openai"` → `_transcribe_openai`, `"cpp"` → `_transcribe_cpp`, `"auto"` →
  cpp-if-found-else-openai. `model` overrides `config.whisper_model`.
- `_transcribe_openai` builds `Transcript(segments=[TranscriptSegment(start,end,text)],
  full_text=" ".join(...), language=config.whisper_language, duration=last_end)`
  from `whisper.load_model(name).transcribe(audio, language=..., initial_prompt=...)`.
- `select_whisper_model(duration_s, configured_model)` (adaptive) returns
  `"large"`/`"medium"`/`"small"`.
- Config fields: `whisper_model="base"`, `whisper_language="pt"`,
  `whisper_device="cpu"`, `whisper_initial_prompt`, `whisper_backend="auto"`,
  `whisper_adaptive=False`. Env overrides in `string_overrides`
  (`MEETING_WHISPER_BACKEND`, `_MODEL`, `_DEVICE`, …).
- Pipeline `process()`: `transcript = self.transcriber.transcribe(audio_path,
  progress_callback=self._make_progress_cb(job), model=whisper_model)` then
  `self._maybe_diarize(transcript, audio_path)` (gated on
  `config.enable_diarization`, lazy-imports `diarize`/`assign_speakers`,
  try/except warn-only). `summarize_existing` has no audio → no diarization.
- `diarizer.diarize(audio_path, config) -> list[(start,end,label)]` (returns `[]`
  on failure) and `assign_speakers(segments, turns) -> None` (mutates).

## 1. `faster-whisper` backend (`transcriber.py`)

### Model-name map (pure, unit-tested)
```python
_FASTER_NAMES = {"large": "large-v3"}  # adaptive/config names → faster-whisper ids

def _faster_model_name(name: str) -> str:
    """Mapeia nomes do openai-whisper p/ ids do faster-whisper (large→large-v3)."""
    return _FASTER_NAMES.get(name, name)
```
`medium`/`small`/`base`/`tiny` and any `*-v2/-v3` pass through unchanged.

### `_transcribe_faster(self, audio_path, progress_callback, model)`
```python
def _transcribe_faster(self, audio_path, progress_callback=None, model=None):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        logger.warning("faster-whisper não instalado; usando openai-whisper.")
        return self._transcribe_openai(audio_path, progress_callback, model)

    model_name = _faster_model_name(model or self.config.whisper_model)
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
        )
        segments = []
        for s in seg_iter:                 # generator — consume it
            text = (s.text or "").strip()
            if text:
                segments.append(TranscriptSegment(start=float(s.start), end=float(s.end), text=text))
    except Exception as e:  # noqa: BLE001
        _log_run_failure(self.config, "faster", {"model": model_name}, e)
        raise

    duration = float(getattr(info, "duration", 0.0)) or (segments[-1].end if segments else 0.0)
    full_text = " ".join(s.text for s in segments)
    if progress_callback:
        progress_callback(100, f"{len(segments)} segmentos, {duration/60:.1f} min")
    logger.info("Transcrição (faster-whisper): %d segmentos, %.1f min.", len(segments), duration/60)
    return Transcript(segments=segments, full_text=full_text,
                      language=self.config.whisper_language, duration=duration)
```
Note: the `import faster_whisper` failure falls back to openai; a *runtime* error
(after import) re-raises (the pipeline records the transcription failure as today).

### Dispatch + default
In `transcribe`, add `if backend == "faster": return self._transcribe_faster(...)`,
and make `"auto"` try faster-whisper first (if importable), then cpp, then openai.
Change the config default to `whisper_backend = "faster"`.

### Config
Add `whisper_compute_type: str = "int8"` + `string_overrides["MEETING_WHISPER_COMPUTE_TYPE"]`.
(`int8` = fast/low-RAM CPU; `"auto"`, `"int8_float16"` available for tuning.)
Change `whisper_backend` default to `"faster"`; update its doc comment to list
the new value.

### Dependencies
Add `faster-whisper>=1.0` to `requirements.txt`. Keep `openai-whisper` (fallback).

## 2. Parallel transcription + diarization (`pipeline.py`)

Replace `_maybe_diarize` (post-transcription) with a start/finish pair so pyannote
runs concurrently with faster-whisper:

```python
def _start_diarization(self, audio_path):
    """Submete a diarização a uma thread (roda junto com a transcrição). None se desligada."""
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
    """Junta os turnos da thread e atribui falantes. Nunca derruba o pipeline."""
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

In `process()`, replace `self._maybe_diarize(transcript, audio_path)` with the
start-before / finish-after pattern:

```python
            diar = self._start_diarization(audio_path)
            # ... existing transcription block ...
            transcript = self.transcriber.transcribe(...)
            # ... progress/cancel ...
            self._finish_diarization(diar, transcript)
```
`_start_diarization` is called BEFORE the transcription step; `_finish_diarization`
right after (where `_maybe_diarize` was), before `write_transcription`. `_maybe_diarize`
is removed (no other caller). Both threads read the same WAV read-only.

## Testing (TDD; mocks — no model download in CI)

`tests/test_faster_whisper.py`:
- **`_faster_model_name`**: `"large"→"large-v3"`; `"medium"`/`"small"`/`"large-v3"` pass through.
- **`_transcribe_faster`**: monkeypatch `faster_whisper.WhisperModel` with a fake whose
  `.transcribe` returns `([Seg(0,1,"oi"), Seg(1,2,"tchau")], Info(duration=2.0))` →
  assert the `Transcript` has 2 segments, `duration==2.0`, `full_text=="oi tchau"`.
- **import-fail fallback**: monkeypatch the import of `faster_whisper` to raise
  `ImportError` → `_transcribe_faster` calls `_transcribe_openai` (monkeypatched to a
  sentinel) — confirms graceful fallback.
- **dispatch**: `config.whisper_backend="faster"` → `transcribe` routes to
  `_transcribe_faster` (monkeypatch it to a sentinel).
- **config**: `whisper_compute_type` default `"int8"`; `whisper_backend` default
  `"faster"`; `MEETING_WHISPER_COMPUTE_TYPE` env override.

`tests/test_parallel_diarization.py`:
- **disabled**: `enable_diarization=False` → `_start_diarization` returns None;
  `_finish_diarization(None, t)` is a no-op (segments keep `speaker=None`).
- **enabled (mocked)**: monkeypatch `diarizer.diarize` to return canned turns; call
  `_start_diarization` then `_finish_diarization` → segments get speakers (proves the
  thread result is joined + `assign_speakers` applied). A `diarize` that raises →
  `_finish_diarization` swallows it (segments stay None), pipeline unaffected.

**Real smoke (out of CI; I run it):** `faster-whisper` `tiny` on a 20-s slice of the
WhatsApp recording → prints segments, proving the backend transcribes end-to-end
(~75 MB tiny CT2 model, no 3 GB download).

## Out of scope

- WhisperX / word-level timestamps.
- Removing `openai-whisper` (kept as fallback).
- whisper.cpp Metal bundling; GPU/Metal for CTranslate2 (CPU int8 only).
- Changing the summary / clickable transcript / note format.
- Parallelism beyond the one diarization thread.
