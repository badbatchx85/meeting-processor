# Adaptive Whisper Model by Audio Duration

**Date:** 2026-06-09
**Status:** Approved design

## Goal

Optionally pick the Whisper transcription model based on the audio's duration, so
short meetings get the best-quality model (`large`) while long meetings use a
faster one (`medium`/`small`) instead of taking tens of minutes. Off by default —
current fixed-model behavior is unchanged until the user opts in.

Benchmarks that motivate this (5-min audio, CPU): `large` ≈ 0.5–1.9× realtime,
`medium` ≈ 3× faster, `small` ≈ 9× faster; quality degrades `large` > `medium` >
`small` (e.g. `large` alone got "sementes" not "cimentos" and added punctuation).
Transcription dominates wall-clock for long meetings, so this is the main lever.

## Decisions (from brainstorming)

- **Scope:** Whisper transcription model only. The summary (Ollama) model is
  unchanged — map-reduce already handles long transcripts, and its time cost is
  smaller.
- **Tiers (balanced):** ≤20 min → `large`, ≤45 min → `medium`, >45 min → `small`.
- **Enablement:** opt-in flag `MEETING_WHISPER_ADAPTIVE` (default `false`).

## Config (`meeting_processor/config.py`)

Add `whisper_adaptive: bool = False` to `Settings`. Wire it into the existing
`bool_overrides` env map as `"MEETING_WHISPER_ADAPTIVE" -> "whisper_adaptive"`.
`Settings` is a plain mutable Pydantic `BaseModel`; no validator needed.

## Selection function (`meeting_processor/transcriber.py`)

A pure, unit-testable function + tier constant at module scope:

```python
# Duração (s) -> modelo Whisper. Acima do último limite, usa "small".
_ADAPTIVE_TIERS: tuple[tuple[int, str], ...] = ((20 * 60, "large"), (45 * 60, "medium"))


def select_whisper_model(duration_s: float, configured_model: str) -> str:
    """Escolhe o modelo Whisper pela duração do áudio (modo adaptativo).

    Duração desconhecida (<= 0, ex.: ffprobe falhou) mantém o modelo configurado
    — não arriscamos degradar a qualidade sem saber o tamanho.
    """
    if duration_s <= 0:
        return configured_model
    for limit, model in _ADAPTIVE_TIERS:
        if duration_s <= limit:
            return model
    return "small"
```

Boundary behavior: ≤1200 s → `large`; (1200, 2700] s → `medium`; >2700 s →
`small`; `0`/negative → `configured_model`.

## Transcriber honors an explicit model

`WhisperTranscriber.transcribe(audio_path, progress_callback=None, model=None)`:
add the optional `model: str | None = None` param and thread it into
`_transcribe_openai(audio_path, progress_callback, model)`. Inside, use
`model_name = model or self.config.whisper_model` and pass `model_name` to
`whisper.load_model(...)` and to the log/`dbg`/ctx lines that currently read
`self.config.whisper_model`. Default `None` ⇒ identical to today.

This avoids mutating the shared `config` object — jobs run in daemon threads
sharing one `Settings`, so mutating `config.whisper_model` would race across
concurrent jobs.

The `cpp` backend uses a fixed `.bin` (`whisper_model_path`), not a model name,
so the `model` override is a **no-op for cpp** (documented; the openai backend is
the one in use here). `_transcribe_cpp` keeps its current signature; only the
`transcribe` dispatcher passes `model` through to `_transcribe_openai`.

## Pipeline wiring (`meeting_processor/pipeline.py`) — DRY, both paths

Add a helper used by **both** `process()` and `transcribe_existing()`:

```python
def _effective_whisper_model(self, audio_path: Path) -> str:
    if not self.config.whisper_adaptive:
        return self.config.whisper_model
    chosen = select_whisper_model(get_duration(audio_path), self.config.whisper_model)
    if chosen != self.config.whisper_model:
        logger.info(
            "Adaptativo: áudio %s → Whisper '%s' (configurado '%s').",
            format_duration(get_duration(audio_path)),
            chosen,
            self.config.whisper_model,
        )
    return chosen
```

(Implementation note: compute `get_duration` once into a local and reuse for both
the comparison and the log, rather than calling it twice — the code block above is
illustrative.)

`get_duration` and `select_whisper_model` are imported from `audio` /
`transcriber` (`get_duration` is already imported in `pipeline.py`, currently
unused). At each transcription site:

1. `model = self._effective_whisper_model(audio_path)`
2. Use `model` in the dashboard stage label (`job.advance("transcription",
   f"Modelo: {model}")`) so the live label matches what actually runs.
3. Call `self.transcriber.transcribe(audio_path, progress_callback=..., model=model)`.

When adaptive is off, `model == self.config.whisper_model` and behavior is
byte-identical to today.

## Testing (TDD)

**`tests/test_adaptive_whisper.py`:**
- `select_whisper_model` boundaries: `1199→large`, `1200→large`, `1201→medium`,
  `2700→medium`, `2701→small`, `5000→small`, `0→configured`, `-5→configured`.
- `transcribe(model=...)` override: monkeypatch `whisper.load_model` (return a
  fake whose `.transcribe` returns `{"segments": [...], "text": "..."}`) and
  assert `load_model` was called with the override string when `model="medium"`,
  and with `config.whisper_model` when `model=None`.
- Pipeline: with `config.whisper_adaptive=True` and `get_duration` monkeypatched
  to `3000.0`, `_effective_whisper_model(path)` returns `"small"`; with
  `whisper_adaptive=False` it returns `config.whisper_model` regardless of
  duration. (Pure/mocked — no real audio, no real Whisper.)

## Out of scope

- Adapting the Ollama/summary model by length.
- Exposing the tier thresholds/models to config/YAML (constant for now; a noted
  follow-up).
- Adaptive selection for the `whisper.cpp` backend.
- Persisting the chosen model into `.processing-history.json` / generation log
  (the `logger.info` line + live dashboard label cover visibility).
