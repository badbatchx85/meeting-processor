# Speaker Diarization (who-said-what)

**Date:** 2026-06-10
**Status:** Approved design

## Goal

After transcription, label each transcript segment with the speaker who said it
("Falante 1/2/…"), using a local pyannote pass aligned to the Whisper segments.
Opt-in, env-configured, degrades to today's behavior when off/unavailable. Final
piece of the "who-said-what / who-owes-what" spine.

## Background (exact, from exploration)

- `TranscriptSegment` (`models.py`) is `BaseModel{start, end, text}` — no speaker.
- Two render sites consume segments:
  - `note_generator._write_raw_transcription`: `**[{ts}]** {seg.text}  ` per line.
  - `summarizer._build_chunked_transcript`: `  [{ts}] {seg.text}` per line.
- `note_generator.read_transcription` parses `**[(ts)]** (text)` back into segments
  (used by `summarize_existing`). `parseTranscript` (frontend) parses the same line
  shape for the clickable transcript. **Keeping the `**[MM:SS]**` structure intact
  (speaker inside the text) means none of these break.**
- Pipeline `process()`: `audio_path = extract_audio(...)` → transcription →
  (audio cleaned in `finally`). Diarization needs the audio, so it runs after
  transcription, before cleanup.
- `summarize_existing` has no audio (re-summarizes an existing transcript), so it
  cannot diarize; it uses whatever labels the transcript note already carries.
- `torch 2.12.0` is installed (via Whisper); `pyannote.audio` is NOT (optional dep).
- pyannote API (current): `Pipeline.from_pretrained("pyannote/speaker-diarization-3.1",
  token=hf_token)`; `.to(torch.device("cuda"))` when available; `diar = pipeline(wav)`;
  `for turn, _, label in diar.itertracks(yield_label=True): turn.start, turn.end, label`.

## 1. Config (`config.py`) — env only

- `enable_diarization: bool = False` → `bool_overrides["MEETING_ENABLE_DIARIZATION"]`.
- `hf_token: str = ""` → `string_overrides`: both `"MEETING_HF_TOKEN"` and `"HF_TOKEN"`
  map to `hf_token` (HF_TOKEN is the conventional name).
- `diarization_model: str = "pyannote/speaker-diarization-3.1"` →
  `string_overrides["MEETING_DIARIZATION_MODEL"]`.

## 2. Model (`models.py`)

Add `speaker: str | None = None` to `TranscriptSegment`, plus:

```python
    @property
    def display_text(self) -> str:
        """Texto com o rótulo do falante, quando houver."""
        return f"{self.speaker}: {self.text}" if self.speaker else self.text
```

## 3. Diarizer (`meeting_processor/diarizer.py`, new)

```python
def diarize(audio_path, config) -> list[tuple[float, float, str]]:
    """Roda o pyannote e devolve [(start, end, label_bruto)] ou [] em falha."""
```
- Lazy-import `from pyannote.audio import Pipeline` inside the function (optional dep).
- `pipeline = Pipeline.from_pretrained(config.diarization_model, token=config.hf_token)`;
  if `pipeline is None` (bad token/gated) → log warning, return `[]`.
- `import torch; if torch.cuda.is_available(): pipeline.to(torch.device("cuda"))`.
- `diar = pipeline(str(audio_path))`; return
  `[(t.start, t.end, label) for t, _, label in diar.itertracks(yield_label=True)]`.
- Wrap the whole body in `try/except Exception` → `logger.warning(...); return []`.

```python
def assign_speakers(segments: list[TranscriptSegment],
                    turns: list[tuple[float, float, str]]) -> None:
    """Atribui a cada segmento o falante (Falante N) de maior sobreposição."""
```
- Build a friendly map: iterate `turns` in order; first time a raw label is seen,
  assign `"Falante {n}"` (n = 1, 2, …). Deterministic by first appearance.
- For each segment, compute overlap with each turn:
  `overlap = max(0.0, min(seg.end, t_end) - max(seg.start, t_start))`; pick the turn
  with the largest positive overlap; set `seg.speaker = friendly[label]`. No positive
  overlap → leave `seg.speaker = None`.
- Mutates in place; returns `None`. Pure (no I/O) → fully unit-tested.
- Empty `turns` → every `speaker` stays `None` (no-op).

## 4. Pipeline hook (`pipeline.py` `process()`)

After the transcription step (when `transcript` exists and `audio_path` is still on
disk), before the `finally` cleanup, gated + guarded:

```python
            if self.config.enable_diarization:
                try:
                    from .diarizer import diarize, assign_speakers
                    turns = diarize(audio_path, self.config)
                    assign_speakers(transcript.segments, turns)
                    logger.info("Diarizacao: %d turnos.", len(turns))
                except Exception as e:  # noqa: BLE001 — nunca derruba o pipeline
                    logger.warning("Falha na diarizacao (nao critico): %s", e)
```

(No change to `summarize_existing`; `enable_diarization=False` → block skipped.)

## 5. Rendering + summary prompt

- `note_generator._write_raw_transcription`: `f"**[{timestamp}]** {seg.display_text}  "`.
- `summarizer._build_chunked_transcript`: `f"  [{timestamp}] {seg.display_text}"`.
  (Both: identical output when `speaker is None`.)
- `SYSTEM_PROMPT` (`summarizer.py`): add one rule —
  *Se a transcrição tiver rótulos "Falante N:", use-os para identificar os
  participantes e atribuir falas/decisões.*

## 6. Dependency

`pyannote.audio` stays optional. Add `requirements-diarization.txt` with
`pyannote.audio>=3.1` and a README line: enable diarization with
`pip install -r requirements-diarization.txt`, accept the
`pyannote/speaker-diarization-3.1` user conditions on Hugging Face, set
`MEETING_HF_TOKEN` + `MEETING_ENABLE_DIARIZATION=true`. The feature self-disables
(returns `[]`) when the package is absent.

## Testing (TDD)

`tests/test_diarization.py`:
- **`assign_speakers`** (pure): two turns (SPEAKER_00 0–5s, SPEAKER_01 5–10s) + three
  segments (1–2s, 6–7s, 4.4–5.4s) → speakers `Falante 1`, `Falante 2`, `Falante 1`
  (the third overlaps SPEAKER_00 by 0.6 vs SPEAKER_01 by 0.4). A segment at 20–21s
  (no overlap) → `None`. Friendly mapping is first-appearance order.
- **`display_text`**: `speaker="Falante 1"` → `"Falante 1: oi"`; `None` → `"oi"`.
- **renderers**: `_write_raw_transcription` and `_build_chunked_transcript` include the
  `Falante 1:` prefix when set and are byte-identical to before when not.
- **`diarize` graceful**: with pyannote absent (monkeypatch the import to raise) →
  returns `[]` and logs, does not raise.
- **pipeline gating**: `enable_diarization=False` → `assign_speakers` never called
  (segments keep `speaker=None`); `True` with `diarize` monkeypatched to a canned
  turn list → segments get speakers. (No real model in tests.)
- **Real model**: verified by the user with their HF token (out of CI).

## Out of scope

- Mapping `Falante N` → real names (the LLM may infer names in the summary text).
- Re-diarizing on `summarize_existing` (no audio there).
- A Settings UI (env-only, per decision).
- GPU/MPS tuning beyond `cuda-if-available`.
- Changing the `**[MM:SS]**` line structure (speaker stays inside the text).
