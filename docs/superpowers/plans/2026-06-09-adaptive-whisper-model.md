# Adaptive Whisper Model by Audio Duration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Optionally choose the Whisper model by audio duration (≤20 min→large, ≤45 min→medium, >45 min→small) behind an opt-in flag, with current behavior unchanged when off.

**Architecture:** A pure `select_whisper_model(duration_s, configured)` in `transcriber.py`; `WhisperTranscriber.transcribe` gains a `model` override param (no shared-config mutation); a `MeetingPipeline._effective_whisper_model(audio_path)` helper computes the model once (using the already-present `get_duration` ffprobe helper) and feeds both the live stage label and `transcribe(model=...)` in `process()` and `transcribe_existing()`.

**Tech Stack:** Python 3.14, Pydantic Settings, openai-whisper, pytest. Tests mock `whisper.load_model` and `get_duration` — no real models/audio.

Run tests with `.venv/bin/python -m pytest`.

---

## File Structure

- **Modify** `meeting_processor/config.py` — add `whisper_adaptive: bool` field + env mapping.
- **Modify** `meeting_processor/transcriber.py` — `_ADAPTIVE_TIERS` + `select_whisper_model`; thread a `model` override through `transcribe`/`_transcribe_openai`.
- **Modify** `meeting_processor/pipeline.py` — `_effective_whisper_model` helper; wire it into `process()` and `transcribe_existing()`.
- **Create** `tests/test_adaptive_whisper.py` — config, selection, override, and helper tests.

---

### Task 1: Config flag `whisper_adaptive`

**Files:**
- Modify: `meeting_processor/config.py` (Settings fields ~line 37; `bool_overrides` ~line 231)
- Create: `tests/test_adaptive_whisper.py`

- [ ] **Step 1: Write the failing tests** — create `tests/test_adaptive_whisper.py`:

```python
"""Seleção adaptativa do modelo Whisper pela duração do áudio."""
from pathlib import Path

from meeting_processor.config import load_config


# --- Task 1: flag de config ------------------------------------------------


def test_whisper_adaptive_defaults_false(monkeypatch):
    monkeypatch.delenv("MEETING_WHISPER_ADAPTIVE", raising=False)
    assert load_config().whisper_adaptive is False


def test_whisper_adaptive_env_on(monkeypatch):
    monkeypatch.setenv("MEETING_WHISPER_ADAPTIVE", "true")
    assert load_config().whisper_adaptive is True


def test_whisper_adaptive_env_off(monkeypatch):
    monkeypatch.setenv("MEETING_WHISPER_ADAPTIVE", "no")
    assert load_config().whisper_adaptive is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_adaptive_whisper.py -q`
Expected: FAIL — `Settings` has no attribute `whisper_adaptive` (Pydantic ignores unknown → `AttributeError`).

- [ ] **Step 3: Add the field.** In `meeting_processor/config.py`, add after the `whisper_backend: str = "auto"` line (around line 37) — keep it with the other whisper fields:

```python
    # Adaptativo: escolhe o modelo Whisper pela duração do áudio (ver
    # transcriber.select_whisper_model). Off => usa whisper_model fixo.
    whisper_adaptive: bool = False
```

- [ ] **Step 4: Map the env var.** In the `bool_overrides` dict (around line 231), add the entry:

```python
        "MEETING_WHISPER_ADAPTIVE": "whisper_adaptive",
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_adaptive_whisper.py -q`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add meeting_processor/config.py tests/test_adaptive_whisper.py
git commit -m "feat(config): add whisper_adaptive flag"
```

---

### Task 2: `select_whisper_model` pure function

**Files:**
- Modify: `meeting_processor/transcriber.py` (module scope, near the top after imports)
- Test: `tests/test_adaptive_whisper.py`

- [ ] **Step 1: Write the failing tests** — append to `tests/test_adaptive_whisper.py`:

```python
# --- Task 2: função de seleção ---------------------------------------------

from meeting_processor.transcriber import select_whisper_model


def test_select_tiers():
    assert select_whisper_model(1199, "x") == "large"   # < 20 min
    assert select_whisper_model(1200, "x") == "large"   # == 20 min (inclusive)
    assert select_whisper_model(1201, "x") == "medium"  # > 20 min
    assert select_whisper_model(2700, "x") == "medium"  # == 45 min (inclusive)
    assert select_whisper_model(2701, "x") == "small"   # > 45 min
    assert select_whisper_model(5000, "x") == "small"


def test_select_unknown_duration_keeps_configured():
    assert select_whisper_model(0, "large") == "large"
    assert select_whisper_model(-5, "medium") == "medium"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_adaptive_whisper.py -k select -q`
Expected: FAIL — `ImportError: cannot import name 'select_whisper_model'`.

- [ ] **Step 3: Implement.** In `meeting_processor/transcriber.py`, add at module scope (after the imports / `logger = ...`, before the first class):

```python
# Duração do áudio (s) -> modelo Whisper, no modo adaptativo. Acima do último
# limite, usa "small". Limites medidos no benchmark de qualidade/velocidade.
_ADAPTIVE_TIERS: tuple[tuple[int, str], ...] = ((20 * 60, "large"), (45 * 60, "medium"))


def select_whisper_model(duration_s: float, configured_model: str) -> str:
    """Escolhe o modelo Whisper pela duração do áudio (modo adaptativo).

    Duração desconhecida (<= 0, ex.: ffprobe falhou) mantém o modelo configurado
    — não degradamos a qualidade sem saber o tamanho.
    """
    if duration_s <= 0:
        return configured_model
    for limit, model in _ADAPTIVE_TIERS:
        if duration_s <= limit:
            return model
    return "small"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_adaptive_whisper.py -k select -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add meeting_processor/transcriber.py tests/test_adaptive_whisper.py
git commit -m "feat(transcribe): select_whisper_model by duration"
```

---

### Task 3: `transcribe(model=...)` override

**Files:**
- Modify: `meeting_processor/transcriber.py` (`transcribe` dispatcher ~line 122; `_transcribe_openai` ~line 141-197)
- Test: `tests/test_adaptive_whisper.py`

- [ ] **Step 1: Write the failing test** — append to `tests/test_adaptive_whisper.py`:

```python
# --- Task 3: override de modelo no transcribe ------------------------------


def test_transcribe_uses_model_override(config, monkeypatch):
    import whisper
    from meeting_processor.transcriber import WhisperTranscriber

    calls = []

    class FakeModel:
        def transcribe(self, path, language=None, initial_prompt=None):
            return {"segments": [{"start": 0.0, "end": 1.0, "text": "oi"}], "text": "oi"}

    monkeypatch.setattr(whisper, "load_model", lambda name: (calls.append(name), FakeModel())[1])

    config.whisper_backend = "openai"   # força o backend Python (sem whisper.cpp)
    config.whisper_model = "large"
    tr = WhisperTranscriber(config)

    tr.transcribe(Path("/tmp/does-not-exist.wav"), model="medium")
    assert calls[-1] == "medium"        # override usado

    tr.transcribe(Path("/tmp/does-not-exist.wav"))
    assert calls[-1] == "large"         # sem override => config.whisper_model
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_adaptive_whisper.py -k override -q`
Expected: FAIL — `transcribe()` got an unexpected keyword argument `model`.

- [ ] **Step 3: Thread the param through the dispatcher.** In `transcriber.py`, change the `transcribe` method signature and its two `_transcribe_openai` calls. Replace:

```python
    def transcribe(self, audio_path: Path, progress_callback=None) -> Transcript:
        """Transcreve um arquivo de áudio escolhendo o backend disponível."""
        backend = (self.config.whisper_backend or "auto").lower()
        cli = resolve_whisper_cli(self.config)

        if backend == "openai":
            return self._transcribe_openai(audio_path, progress_callback)
        if backend == "cpp":
            return self._transcribe_cpp(audio_path, progress_callback)

        # auto: whisper.cpp se disponível, senão openai-whisper
        if cli is not None and resolve_whisper_model(self.config) is not None:
            return self._transcribe_cpp(audio_path, progress_callback)
        logger.info("whisper.cpp nao encontrado; usando openai-whisper (pip).")
        return self._transcribe_openai(audio_path, progress_callback)
```

with:

```python
    def transcribe(
        self, audio_path: Path, progress_callback=None, model: str | None = None
    ) -> Transcript:
        """Transcreve um arquivo de áudio escolhendo o backend disponível.

        ``model`` sobrescreve ``config.whisper_model`` apenas no backend
        openai-whisper (o whisper.cpp usa um .bin fixo e ignora o override).
        """
        backend = (self.config.whisper_backend or "auto").lower()
        cli = resolve_whisper_cli(self.config)

        if backend == "openai":
            return self._transcribe_openai(audio_path, progress_callback, model)
        if backend == "cpp":
            return self._transcribe_cpp(audio_path, progress_callback)

        # auto: whisper.cpp se disponível, senão openai-whisper
        if cli is not None and resolve_whisper_model(self.config) is not None:
            return self._transcribe_cpp(audio_path, progress_callback)
        logger.info("whisper.cpp nao encontrado; usando openai-whisper (pip).")
        return self._transcribe_openai(audio_path, progress_callback, model)
```

- [ ] **Step 4: Use the override in `_transcribe_openai`.** Change its signature to add `model`, and resolve `model_name` once at the top, then replace every `self.config.whisper_model` reference inside the method body with `model_name`. Replace the method header + body down to the `whisper.load_model` line:

```python
    def _transcribe_openai(
        self, audio_path: Path, progress_callback=None, model: str | None = None
    ) -> Transcript:
        try:
            import whisper  # openai-whisper
        except ImportError as e:
            raise RuntimeError(
                "openai-whisper não instalado. Rode: pip install -r requirements.txt"
            ) from e

        model_name = model or self.config.whisper_model

        if progress_callback:
            progress_callback(5, f"Carregando modelo {model_name}...")
        logger.info(
            "Transcrevendo %s com openai-whisper (modelo=%s)...",
            audio_path.name,
            model_name,
        )

        dbg = _debug_logger(self.config)
        size_mb = audio_path.stat().st_size / 1e6 if audio_path.exists() else 0.0
        ctx = {
            "model": model_name,
            "language": self.config.whisper_language,
            "audio": str(audio_path),
            "audio_mb": round(size_mb, 1),
        }
        dbg.debug(
            "Início openai-whisper: model=%s lang=%s audio=%s (%.1f MB) initial_prompt=%s",
            model_name,
            self.config.whisper_language,
            audio_path.name,
            size_mb,
            bool(self.config.whisper_initial_prompt),
        )
        dbg.debug(
            "Se o modelo não estiver em cache (~/.cache/whisper), será baixado "
            "agora — pode demorar (carga lenta = download)."
        )

        try:
            t0 = time.monotonic()
            model = whisper.load_model(model_name)
```

(Leave everything from `dbg.debug("Modelo carregado em ...")` onward unchanged — note the local variable `model` is now reassigned from the param to the loaded model object after this point, which is fine since the param is no longer needed.)

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_adaptive_whisper.py -k override -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add meeting_processor/transcriber.py tests/test_adaptive_whisper.py
git commit -m "feat(transcribe): optional model override (no config mutation)"
```

---

### Task 4: Pipeline helper + wiring (both transcription paths)

**Files:**
- Modify: `meeting_processor/pipeline.py` (imports ~line 9, 17; `process()` transcription block ~line 110-115; `transcribe_existing()` transcription block; add helper method)
- Test: `tests/test_adaptive_whisper.py`

- [ ] **Step 1: Write the failing tests** — append to `tests/test_adaptive_whisper.py`:

```python
# --- Task 4: helper do pipeline --------------------------------------------


def test_effective_model_adaptive_long(config, monkeypatch):
    import meeting_processor.pipeline as pipemod
    from meeting_processor.pipeline import MeetingPipeline

    config.whisper_adaptive = True
    config.whisper_model = "large"
    monkeypatch.setattr(pipemod, "get_duration", lambda p: 3000.0)   # 50 min
    assert MeetingPipeline(config)._effective_whisper_model(Path("/tmp/x.wav")) == "small"


def test_effective_model_adaptive_short(config, monkeypatch):
    import meeting_processor.pipeline as pipemod
    from meeting_processor.pipeline import MeetingPipeline

    config.whisper_adaptive = True
    config.whisper_model = "large"
    monkeypatch.setattr(pipemod, "get_duration", lambda p: 600.0)    # 10 min
    assert MeetingPipeline(config)._effective_whisper_model(Path("/tmp/x.wav")) == "large"


def test_effective_model_off_returns_configured(config, monkeypatch):
    import meeting_processor.pipeline as pipemod
    from meeting_processor.pipeline import MeetingPipeline

    config.whisper_adaptive = False
    config.whisper_model = "base"
    monkeypatch.setattr(pipemod, "get_duration", lambda p: 99999.0)
    assert MeetingPipeline(config)._effective_whisper_model(Path("/tmp/x.wav")) == "base"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_adaptive_whisper.py -k effective -q`
Expected: FAIL — `MeetingPipeline` has no attribute `_effective_whisper_model`.

- [ ] **Step 3: Import `select_whisper_model`.** In `meeting_processor/pipeline.py`, change the transcriber import line:

```python
from .transcriber import WhisperTranscriber
```

to:

```python
from .transcriber import WhisperTranscriber, select_whisper_model
```

(`get_duration` and `format_duration` are already imported at lines 9 and 18.)

- [ ] **Step 4: Add the helper method** to the `MeetingPipeline` class (place it just above `process`):

```python
    def _effective_whisper_model(self, audio_path: Path) -> str:
        """Modelo Whisper para esta transcrição: fixo, ou adaptativo pela duração."""
        if not self.config.whisper_adaptive:
            return self.config.whisper_model
        duration_s = get_duration(audio_path)
        chosen = select_whisper_model(duration_s, self.config.whisper_model)
        if chosen != self.config.whisper_model:
            logger.info(
                "Adaptativo: áudio %s → Whisper '%s' (configurado '%s').",
                format_duration(duration_s),
                chosen,
                self.config.whisper_model,
            )
        return chosen
```

- [ ] **Step 5: Wire into `process()`.** In `process()`, replace this block:

```python
            # Etapa 2: Transcrever (sempre)
            logger.info("[2] Transcrevendo audio com Whisper...")
            job.advance("transcription", f"Modelo: {self.config.whisper_model}")
            job.set_progress("transcription", 5, "Carregando modelo...")
            self.dashboard.update(job)
            transcript = self.transcriber.transcribe(audio_path, progress_callback=self._make_progress_cb(job))
```

with:

```python
            # Etapa 2: Transcrever (sempre)
            logger.info("[2] Transcrevendo audio com Whisper...")
            whisper_model = self._effective_whisper_model(audio_path)
            job.advance("transcription", f"Modelo: {whisper_model}")
            job.set_progress("transcription", 5, "Carregando modelo...")
            self.dashboard.update(job)
            transcript = self.transcriber.transcribe(
                audio_path, progress_callback=self._make_progress_cb(job), model=whisper_model
            )
```

- [ ] **Step 6: Wire into `transcribe_existing()`.** In `transcribe_existing()`, replace this block:

```python
            job.set_progress("audio", 100)
            job.advance("transcription", f"Modelo: {self.config.whisper_model}")
            job.set_progress("transcription", 5, "Carregando modelo...")
            self.dashboard.update(job)
            transcript = self.transcriber.transcribe(
                audio_path, progress_callback=self._make_progress_cb(job)
```

with:

```python
            job.set_progress("audio", 100)
            whisper_model = self._effective_whisper_model(audio_path)
            job.advance("transcription", f"Modelo: {whisper_model}")
            job.set_progress("transcription", 5, "Carregando modelo...")
            self.dashboard.update(job)
            transcript = self.transcriber.transcribe(
                audio_path, progress_callback=self._make_progress_cb(job), model=whisper_model
```

(The `transcribe_existing` call spans multiple lines — only the call's argument list gains `, model=whisper_model`. Ensure the closing `)` of that call still follows; add `model=whisper_model` as the final argument before it.)

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_adaptive_whisper.py -q`
Expected: PASS (all tests in the file).

- [ ] **Step 8: Full suite (regressions)**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS except the pre-existing `test_summarizer_mock.py::test_factory_selects_anthropic` (only if `ANTHROPIC_API_KEY` unset). The stuck-jobs / pipeline tests (`tests/test_stuck_jobs.py`) must still pass — they construct `MeetingPipeline` and exercise `process()`; with `whisper_adaptive` defaulting to `False`, transcription behavior is unchanged.

- [ ] **Step 9: Commit**

```bash
git add meeting_processor/pipeline.py tests/test_adaptive_whisper.py
git commit -m "feat(pipeline): adaptive Whisper model in process + transcribe_existing"
```

---

## Self-Review

**Spec coverage:**
- `whisper_adaptive` flag + `MEETING_WHISPER_ADAPTIVE` env → Task 1. ✓
- `select_whisper_model` + tiers (≤20→large, ≤45→medium, else small, unknown→configured) → Task 2. ✓
- `transcribe(model=...)` override, openai backend only, no config mutation → Task 3. ✓
- cpp backend unaffected (dispatcher passes `model` only to `_transcribe_openai`) → Task 3 Step 3. ✓
- `_effective_whisper_model` helper used by both `process()` and `transcribe_existing()`, feeding label + transcribe → Task 4 Steps 4-6. ✓
- `get_duration` reuse (already imported) → Task 4 Step 3/4. ✓
- Off = unchanged behavior → Task 4 Step 8 (full suite incl. stuck-jobs). ✓

**Placeholder scan:** none — every step has concrete code/commands.

**Type consistency:** `select_whisper_model(duration_s: float, configured_model: str) -> str` defined in Task 2, imported in Task 4. `transcribe(..., model: str | None = None)` defined Task 3, called with `model=whisper_model` in Task 4. `_effective_whisper_model(self, audio_path: Path) -> str` defined Task 4 Step 4, used Steps 5-6. `whisper_adaptive` field (Task 1) read in Task 4's helper. `get_duration`/`format_duration` already imported. Names consistent throughout. ✓
