# Speaker Diarization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Label each transcript segment with its speaker ("Falante N") via an opt-in local pyannote pass aligned to the Whisper segments.

**Architecture:** A `diarizer` module runs pyannote (optional dep, graceful) and aligns turns to segments by max overlap; `TranscriptSegment.speaker`/`display_text` carry the label inside the existing `**[MM:SS]**` line (so the clickable transcript / re-summarize keep working); a gated, guarded `_maybe_diarize` hook runs after transcription.

**Tech Stack:** Python 3.14, Pydantic, pyannote.audio (optional), torch; pytest.

Run tests with `.venv/bin/python -m pytest`. The pre-existing `test_summarizer_mock.py::test_factory_selects_anthropic` failure (no `ANTHROPIC_API_KEY`) is unrelated.

---

## File Structure
- **Modify** `meeting_processor/config.py` — 3 fields + overrides.
- **Modify** `meeting_processor/models.py` — `TranscriptSegment.speaker` + `display_text`.
- **Create** `meeting_processor/diarizer.py` — `diarize` + `assign_speakers`.
- **Modify** `meeting_processor/note_generator.py` + `meeting_processor/summarizer.py` — render `display_text` + a prompt rule.
- **Modify** `meeting_processor/pipeline.py` — `_maybe_diarize` + call site.
- **Create** `requirements-diarization.txt`; **Modify** `README.md`.
- **Create** `tests/test_diarization.py`.

---

### Task 1: Config + model

**Files:** Modify `meeting_processor/config.py`, `meeting_processor/models.py`; Create `tests/test_diarization.py`.

- [ ] **Step 1: Write the failing tests** — create `tests/test_diarization.py`:

```python
"""Diarização de falantes (quem falou)."""
from meeting_processor.models import TranscriptSegment


def test_segment_display_text():
    assert TranscriptSegment(start=0, end=1, text="oi").display_text == "oi"
    seg = TranscriptSegment(start=0, end=1, text="oi", speaker="Falante 1")
    assert seg.display_text == "Falante 1: oi"


def test_diarization_config_defaults(config):
    assert config.enable_diarization is False
    assert config.hf_token == ""
    assert config.diarization_model == "pyannote/speaker-diarization-3.1"


def test_diarization_env_overrides(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MEETING_ENABLE_DIARIZATION", "true")
    monkeypatch.setenv("MEETING_HF_TOKEN", "hf_abc")
    from meeting_processor.config import load_config
    cfg = load_config()
    assert cfg.enable_diarization is True
    assert cfg.hf_token == "hf_abc"
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_diarization.py -q`
Expected: FAIL — `TranscriptSegment` has no `speaker`/`display_text`; `config` has no `enable_diarization`.

- [ ] **Step 3: Add the model fields.** In `meeting_processor/models.py`, change `TranscriptSegment`:

```python
class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str
    speaker: str | None = None

    @property
    def display_text(self) -> str:
        """Texto com o rótulo do falante, quando houver."""
        return f"{self.speaker}: {self.text}" if self.speaker else self.text
```

- [ ] **Step 4: Add the config fields.** In `meeting_processor/config.py`, add to `Settings` (near `whisper_adaptive`):

```python
    # Diarização (quem falou) — opt-in, requer pyannote + token Hugging Face.
    enable_diarization: bool = False
    hf_token: str = ""
    diarization_model: str = "pyannote/speaker-diarization-3.1"
```

In `load_config`, add to `string_overrides`:

```python
        "MEETING_HF_TOKEN": "hf_token",
        "HF_TOKEN": "hf_token",
        "MEETING_DIARIZATION_MODEL": "diarization_model",
```

and to `bool_overrides`:

```python
        "MEETING_ENABLE_DIARIZATION": "enable_diarization",
```

- [ ] **Step 5: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_diarization.py -q`
Expected: PASS (3 tests). Confirm `.venv/bin/python -c "import meeting_processor.config, meeting_processor.models"`.

- [ ] **Step 6: Commit**

```bash
git add meeting_processor/config.py meeting_processor/models.py tests/test_diarization.py
git commit -m "feat(diarization): config + TranscriptSegment.speaker/display_text"
```

---

### Task 2: Diarizer module

**Files:** Create `meeting_processor/diarizer.py`; Test: `tests/test_diarization.py`.

- [ ] **Step 1: Append the failing tests:**

```python
# --- Task 2: diarizer -------------------------------------------------------

from meeting_processor import diarizer


def test_assign_speakers_overlap_and_labels():
    segs = [
        TranscriptSegment(start=1, end=2, text="a"),
        TranscriptSegment(start=6, end=7, text="b"),
        TranscriptSegment(start=4.4, end=5.4, text="c"),  # 0.6 vs SP0, 0.4 vs SP1
        TranscriptSegment(start=20, end=21, text="d"),    # no overlap
    ]
    turns = [(0.0, 5.0, "SPEAKER_00"), (5.0, 10.0, "SPEAKER_01")]
    diarizer.assign_speakers(segs, turns)
    assert [s.speaker for s in segs] == ["Falante 1", "Falante 2", "Falante 1", None]


def test_assign_speakers_empty_turns_noop():
    segs = [TranscriptSegment(start=0, end=1, text="a")]
    diarizer.assign_speakers(segs, [])
    assert segs[0].speaker is None


def test_diarize_graceful_when_pyannote_missing(config, monkeypatch):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name.startswith("pyannote"):
            raise ImportError("no pyannote here")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert diarizer.diarize("/tmp/does-not-matter.wav", config) == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_diarization.py -k "assign_speakers or graceful" -q`
Expected: FAIL — no `meeting_processor.diarizer`.

- [ ] **Step 3: Create `meeting_processor/diarizer.py`:**

```python
"""Diarização de falantes via pyannote (opcional, com degradação graciosa)."""
from __future__ import annotations

import logging
from pathlib import Path

from .config import Settings
from .models import TranscriptSegment

logger = logging.getLogger(__name__)


def diarize(audio_path, config: Settings) -> list[tuple[float, float, str]]:
    """Roda o pyannote e devolve [(start, end, label_bruto)] — [] em qualquer falha.

    pyannote é dependência opcional: import preguiçoso aqui dentro. Token/modelo
    inválidos, pacote ausente ou erro de runtime nunca propagam — devolvem [].
    """
    try:
        from pyannote.audio import Pipeline
        import torch

        pipeline = Pipeline.from_pretrained(
            config.diarization_model, token=config.hf_token or None
        )
        if pipeline is None:
            logger.warning(
                "pyannote retornou None (token/condições do modelo?). Diarizacao desligada."
            )
            return []
        if torch.cuda.is_available():
            pipeline.to(torch.device("cuda"))
        diar = pipeline(str(audio_path))
        return [
            (turn.start, turn.end, label)
            for turn, _, label in diar.itertracks(yield_label=True)
        ]
    except Exception as e:  # noqa: BLE001 — diarizacao nunca derruba o pipeline
        logger.warning("Falha na diarizacao (%s). Seguindo sem falantes.", e)
        return []


def assign_speakers(
    segments: list[TranscriptSegment],
    turns: list[tuple[float, float, str]],
) -> None:
    """Atribui a cada segmento o falante (Falante N) do turno de maior sobreposição.

    Rótulos brutos do pyannote (SPEAKER_00, ...) viram "Falante 1/2/..." na ordem
    de primeira aparição. Segmento sem sobreposição positiva fica com speaker None.
    Muta os segmentos no lugar.
    """
    friendly: dict[str, str] = {}
    for _s, _e, label in turns:
        if label not in friendly:
            friendly[label] = f"Falante {len(friendly) + 1}"

    for seg in segments:
        best_label = None
        best_overlap = 0.0
        for t_start, t_end, label in turns:
            overlap = min(seg.end, t_end) - max(seg.start, t_start)
            if overlap > best_overlap:
                best_overlap = overlap
                best_label = label
        seg.speaker = friendly[best_label] if best_label is not None else None
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_diarization.py -q`
Expected: PASS (6 tests). Confirm `.venv/bin/python -c "import meeting_processor.diarizer"`.

- [ ] **Step 5: Commit**

```bash
git add meeting_processor/diarizer.py tests/test_diarization.py
git commit -m "feat(diarization): diarize() + assign_speakers() with graceful degradation"
```

---

### Task 3: Rendering + prompt rule

**Files:** Modify `meeting_processor/note_generator.py`, `meeting_processor/summarizer.py`; Test: `tests/test_diarization.py`.

- [ ] **Step 1: Append the failing tests:**

```python
# --- Task 3: rendering ------------------------------------------------------

from meeting_processor.models import Transcript
from meeting_processor.note_generator import NoteGenerator
from meeting_processor.summarizer import SYSTEM_PROMPT, _BaseSummarizer


def _spk_transcript():
    segs = [
        TranscriptSegment(start=0, end=3, text="bom dia", speaker="Falante 1"),
        TranscriptSegment(start=3, end=6, text="ola", speaker="Falante 2"),
    ]
    return Transcript(segments=segs, full_text="bom dia ola", language="pt", duration=6)


def test_note_renders_speaker(config, tmp_path):
    ng = NoteGenerator(config)
    out = tmp_path / "t.md"
    ng._write_raw_transcription(_spk_transcript(), out)
    text = out.read_text(encoding="utf-8")
    assert "**[00:00]** Falante 1: bom dia" in text
    assert "Falante 2: ola" in text


def test_chunked_transcript_renders_speaker(config):
    class _F(_BaseSummarizer):
        provider_name = "f"
        def _call_llm(self, s, u): return "{}"
    chunked = _F(config)._build_chunked_transcript(_spk_transcript().segments, 5)
    assert "Falante 1: bom dia" in chunked
    assert "Falante 2: ola" in chunked


def test_system_prompt_mentions_speaker_labels():
    assert "Falante" in SYSTEM_PROMPT
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_diarization.py -k "renders_speaker or system_prompt" -q`
Expected: FAIL — renderers emit `seg.text` (no label); `SYSTEM_PROMPT` has no "Falante".

- [ ] **Step 3: Render `display_text`.**
  - In `meeting_processor/note_generator.py` `_write_raw_transcription`, change
    `lines.append(f"**[{timestamp}]** {seg.text}  ")` to
    `lines.append(f"**[{timestamp}]** {seg.display_text}  ")`.
  - In `meeting_processor/summarizer.py` `_build_chunked_transcript`, change
    `lines.append(f"  [{timestamp}] {seg.text}")` to
    `lines.append(f"  [{timestamp}] {seg.display_text}")`.

- [ ] **Step 4: Add the prompt rule.** In `meeting_processor/summarizer.py`, find `SYSTEM_PROMPT` and add one bullet to its rules list (the `- ` lines near the `time_windows` rule):

```python
- Se a transcrição tiver rótulos "Falante N:", use-os para identificar os participantes e atribuir falas, decisões e tarefas.
```

- [ ] **Step 5: Run tests + regression**

Run: `.venv/bin/python -m pytest tests/test_diarization.py tests/test_summary_chunking.py -q`
Expected: PASS (renderers emit the label when present; chunking suite unaffected — segments there have `speaker=None` so `display_text == text`).

- [ ] **Step 6: Commit**

```bash
git add meeting_processor/note_generator.py meeting_processor/summarizer.py tests/test_diarization.py
git commit -m "feat(diarization): render speaker labels in transcript + summary prompt"
```

---

### Task 4: Pipeline hook + optional dependency

**Files:** Modify `meeting_processor/pipeline.py`; Create `requirements-diarization.txt`; Modify `README.md`; Test: `tests/test_diarization.py`.

- [ ] **Step 1: Append the failing tests:**

```python
# --- Task 4: pipeline hook --------------------------------------------------

from meeting_processor.pipeline import MeetingPipeline


def test_maybe_diarize_disabled(config):
    config.enable_diarization = False
    segs = [TranscriptSegment(start=0, end=1, text="oi")]
    t = Transcript(segments=segs, full_text="oi", language="pt", duration=1)
    MeetingPipeline(config)._maybe_diarize(t, "/tmp/x.wav")
    assert segs[0].speaker is None


def test_maybe_diarize_enabled(config, monkeypatch):
    config.enable_diarization = True
    monkeypatch.setattr(diarizer, "diarize", lambda audio, cfg: [(0.0, 1.0, "SPEAKER_00")])
    segs = [TranscriptSegment(start=0, end=1, text="oi")]
    t = Transcript(segments=segs, full_text="oi", language="pt", duration=1)
    MeetingPipeline(config)._maybe_diarize(t, "/tmp/x.wav")
    assert segs[0].speaker == "Falante 1"
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_diarization.py -k maybe_diarize -q`
Expected: FAIL — `MeetingPipeline` has no `_maybe_diarize`.

- [ ] **Step 3: Add `_maybe_diarize` + call it.** In `meeting_processor/pipeline.py`, add the method to `MeetingPipeline` (e.g. right before `_summarize`):

```python
    def _maybe_diarize(self, transcript, audio_path) -> None:
        """Atribui falantes aos segmentos quando a diarização está ligada.

        Import preguiçoso (pyannote é opcional) e tudo embrulhado: a diarização
        nunca derruba o pipeline.
        """
        if not self.config.enable_diarization:
            return
        try:
            from .diarizer import diarize, assign_speakers
            turns = diarize(audio_path, self.config)
            assign_speakers(transcript.segments, turns)
            logger.info("Diarizacao: %d turnos.", len(turns))
        except Exception as e:  # noqa: BLE001 — nunca derruba o pipeline
            logger.warning("Falha na diarizacao (nao critico): %s", e)
```

Then in `process()`, immediately after the transcription block's final
`self._check_cancel()` (the one right after the transcription `set_progress`/
`dashboard.update`) and BEFORE `paths = self.note_generator.prepare(video_path.name, created_at)`, insert:

```python
            self._maybe_diarize(transcript, audio_path)
```

(So `write_transcription` persists the speaker labels.)

- [ ] **Step 4: Run the hook tests**

Run: `.venv/bin/python -m pytest tests/test_diarization.py -k maybe_diarize -q`
Expected: PASS.

- [ ] **Step 5: Add the optional dependency + docs.**
  - Create `requirements-diarization.txt`:
    ```
    # Diarização de falantes (opcional). Instale com:
    #   pip install -r requirements-diarization.txt
    # Depois aceite as condições de uso de pyannote/speaker-diarization-3.1 no
    # Hugging Face e defina MEETING_HF_TOKEN + MEETING_ENABLE_DIARIZATION=true.
    pyannote.audio>=3.1
    ```
  - In `README.md`, add a short "## Diarização (quem falou)" section: `pip install
    -r requirements-diarization.txt`, accept the model conditions on Hugging Face,
    set `MEETING_HF_TOKEN=hf_...` and `MEETING_ENABLE_DIARIZATION=true` in `.env`,
    restart. Note it runs locally after transcription and labels segments as
    "Falante N"; if disabled or unavailable the app behaves exactly as before.

- [ ] **Step 6: Full suite + import check**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS except the pre-existing `test_factory_selects_anthropic`.
Confirm `.venv/bin/python -c "import meeting_processor.pipeline"`.

- [ ] **Step 7: Commit**

```bash
git add meeting_processor/pipeline.py requirements-diarization.txt README.md tests/test_diarization.py
git commit -m "feat(diarization): pipeline hook + optional pyannote dependency"
```

---

## Self-Review

**Spec coverage:**
- Config: `enable_diarization`/`hf_token`/`diarization_model` + env overrides (bool + string incl. `HF_TOKEN`) → Task 1. ✓
- `TranscriptSegment.speaker` + `display_text` → Task 1. ✓
- `diarize` (lazy pyannote, `from_pretrained(token=)`, cuda-if-available, `itertracks(yield_label=True)`, `[]` on failure) + `assign_speakers` (friendly labels, max-overlap, None on no-overlap, in-place) → Task 2. ✓
- Renderers use `display_text`; `SYSTEM_PROMPT` speaker rule → Task 3. ✓
- Pipeline `_maybe_diarize` (gated + guarded), called after transcription before `write_transcription`; `summarize_existing` untouched → Task 4. ✓
- Optional `pyannote.audio` dep + README → Task 4. ✓
- Tests: overlap/labels, display_text, renderers, graceful-missing, gating → Tasks 1-4. ✓
- Out of scope (name mapping, re-diarize, Settings UI, line-structure change) → untouched. ✓

**Placeholder scan:** none — every step has concrete code/commands.

**Type consistency:** `TranscriptSegment.speaker`/`display_text` (Task 1) used by renderers (Task 3) + `assign_speakers` (Task 2). `diarize(audio_path, config) -> list[tuple[float,float,str]]` and `assign_speakers(segments, turns) -> None` (Task 2) called by `_maybe_diarize` (Task 4) and the tests. `config.enable_diarization`/`hf_token`/`diarization_model` (Task 1) read by `diarize`/`_maybe_diarize`. The pipeline hook monkeypatches `diarizer.diarize` (module attribute), which the lazy `from .diarizer import diarize` resolves at call time. Names consistent throughout. ✓
