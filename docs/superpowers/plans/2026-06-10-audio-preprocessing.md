# Audio Pre-processing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Optionally run an ffmpeg denoise/normalize filter chain in `extract_audio` before Whisper, with a safety fallback so a bad filter never fails the job.

**Architecture:** A pure `_ffmpeg_cmd` builder makes the with/without-filter command testable; `extract_audio` applies `config.audio_filter` when `config.enable_audio_denoise`, and retries once without filters if the filtered run fails.

**Tech Stack:** Python 3.14, ffmpeg (subprocess), pytest (mock `subprocess.run`).

Run tests with `.venv/bin/python -m pytest`. The pre-existing `test_summarizer_mock.py::test_factory_selects_anthropic` failure (no `ANTHROPIC_API_KEY`) is unrelated.

---

## File Structure
- **Modify** `meeting_processor/config.py` — `enable_audio_denoise` + `audio_filter` + overrides.
- **Modify** `meeting_processor/audio.py` — `_ffmpeg_cmd` helper + `extract_audio` filter/fallback.
- **Create** `tests/test_audio_preprocessing.py`.

---

### Task 1: Config + `_ffmpeg_cmd` builder

**Files:** Modify `meeting_processor/config.py`, `meeting_processor/audio.py`; Create `tests/test_audio_preprocessing.py`.

- [ ] **Step 1: Write the failing tests** — create `tests/test_audio_preprocessing.py`:

```python
"""Pré-processamento de áudio (denoise/normalize) antes do Whisper."""
from pathlib import Path

from meeting_processor.audio import _ffmpeg_cmd


def test_audio_config_defaults(config):
    assert config.enable_audio_denoise is False
    assert "highpass" in config.audio_filter
    assert "loudnorm" in config.audio_filter


def test_audio_config_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MEETING_AUDIO_DENOISE", "true")
    monkeypatch.setenv("MEETING_AUDIO_FILTER", "anlmdn")
    from meeting_processor.config import load_config
    cfg = load_config()
    assert cfg.enable_audio_denoise is True
    assert cfg.audio_filter == "anlmdn"


def test_ffmpeg_cmd_with_filter():
    cmd = _ffmpeg_cmd(Path("/in.mp4"), Path("/out.wav"), "highpass=f=80")
    assert "-af" in cmd
    assert cmd[cmd.index("-af") + 1] == "highpass=f=80"
    assert cmd.index("-af") < cmd.index("-y")   # filter before output
    assert cmd[-1] == "/out.wav"


def test_ffmpeg_cmd_without_filter():
    cmd = _ffmpeg_cmd(Path("/in.mp4"), Path("/out.wav"), None)
    assert "-af" not in cmd
    assert "16000" in cmd and "-ac" in cmd
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_audio_preprocessing.py -q`
Expected: FAIL — `_ffmpeg_cmd` doesn't exist; `config` has no `enable_audio_denoise`.

- [ ] **Step 3: Add config fields.** In `meeting_processor/config.py`, add to `Settings` near `temp_dir`:

```python
    # Pré-processamento de áudio (denoise/normalize) antes do Whisper — opt-in.
    enable_audio_denoise: bool = False
    audio_filter: str = "highpass=f=80,afftdn=nf=-25,loudnorm=I=-16:TP=-1.5:LRA=11"
```

In `load_config`, add to `bool_overrides`:

```python
        "MEETING_AUDIO_DENOISE": "enable_audio_denoise",
```

and to `string_overrides`:

```python
        "MEETING_AUDIO_FILTER": "audio_filter",
```

- [ ] **Step 4: Add the `_ffmpeg_cmd` helper.** In `meeting_processor/audio.py`, add above `extract_audio`:

```python
def _ffmpeg_cmd(video_path: Path, output_path: Path, audio_filter: str | None) -> list[str]:
    """Monta a linha de comando do ffmpeg, com o filtro de áudio quando houver."""
    cmd = [
        "ffmpeg",
        "-i", str(video_path),
        "-vn",                   # sem vídeo
        "-acodec", "pcm_s16le",  # WAV PCM 16-bit
        "-ar", "16000",          # 16kHz (padrão Whisper)
        "-ac", "1",              # mono
    ]
    if audio_filter:
        cmd += ["-af", audio_filter]
    cmd += ["-y", str(output_path)]
    return cmd
```

- [ ] **Step 5: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_audio_preprocessing.py -q`
Expected: PASS (4 tests). Confirm `.venv/bin/python -c "import meeting_processor.audio, meeting_processor.config"`.

- [ ] **Step 6: Commit**

```bash
git add meeting_processor/config.py meeting_processor/audio.py tests/test_audio_preprocessing.py
git commit -m "feat(audio): denoise config + _ffmpeg_cmd builder"
```

---

### Task 2: `extract_audio` filter + fallback

**Files:** Modify `meeting_processor/audio.py`; Test: `tests/test_audio_preprocessing.py`.

- [ ] **Step 1: Append the failing tests:**

```python
# --- Task 2: extract_audio filter + fallback --------------------------------

import subprocess
import pytest

from meeting_processor.audio import extract_audio


def _fake_ok(cmd, **kwargs):
    """Simula ffmpeg com sucesso: cria o arquivo de saída e devolve um result."""
    Path(cmd[-1]).write_bytes(b"WAVDATA")

    class _R:
        stderr = ""
    return _R()


def test_extract_audio_denoise_on(config, monkeypatch):
    config.enable_audio_denoise = True
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _fake_ok(cmd, **kwargs)

    monkeypatch.setattr("meeting_processor.audio.validate_ffmpeg", lambda: True)
    monkeypatch.setattr("meeting_processor.audio.subprocess.run", fake_run)
    extract_audio(Path("/x.mp4"), config)
    assert "-af" in captured["cmd"]
    assert config.audio_filter in captured["cmd"]


def test_extract_audio_denoise_off(config, monkeypatch):
    config.enable_audio_denoise = False
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _fake_ok(cmd, **kwargs)

    monkeypatch.setattr("meeting_processor.audio.validate_ffmpeg", lambda: True)
    monkeypatch.setattr("meeting_processor.audio.subprocess.run", fake_run)
    extract_audio(Path("/x.mp4"), config)
    assert "-af" not in captured["cmd"]


def test_extract_audio_fallback_on_filter_failure(config, monkeypatch):
    config.enable_audio_denoise = True
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if "-af" in cmd:
            raise subprocess.CalledProcessError(1, cmd, stderr="bad filter")
        return _fake_ok(cmd, **kwargs)

    monkeypatch.setattr("meeting_processor.audio.validate_ffmpeg", lambda: True)
    monkeypatch.setattr("meeting_processor.audio.subprocess.run", fake_run)
    out = extract_audio(Path("/x.mp4"), config)
    assert out.exists()
    assert len(calls) == 2
    assert "-af" in calls[0] and "-af" not in calls[1]


def test_extract_audio_raises_when_unfiltered_fails(config, monkeypatch):
    config.enable_audio_denoise = False

    def fake_run(cmd, **kwargs):
        raise subprocess.CalledProcessError(1, cmd, stderr="boom")

    monkeypatch.setattr("meeting_processor.audio.validate_ffmpeg", lambda: True)
    monkeypatch.setattr("meeting_processor.audio.subprocess.run", fake_run)
    with pytest.raises(RuntimeError):
        extract_audio(Path("/x.mp4"), config)
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_audio_preprocessing.py -k "denoise or fallback or unfiltered" -q`
Expected: FAIL — `extract_audio` ignores `enable_audio_denoise` (no `-af`), and there's no fallback.

- [ ] **Step 3: Rewrite the `extract_audio` body.** In `meeting_processor/audio.py`, replace the `try/except subprocess.CalledProcessError` block (the one that builds the inline `ffmpeg` list and raises `RuntimeError`) with:

```python
    audio_filter = config.audio_filter if config.enable_audio_denoise else None
    try:
        subprocess.run(
            _ffmpeg_cmd(video_path, output_path, audio_filter),
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        if audio_filter:
            logger.warning(
                "Falha no ffmpeg com filtro de audio. Repetindo sem filtro. (%s)",
                (e.stderr or "").strip()[-300:] or e,
            )
            try:
                subprocess.run(
                    _ffmpeg_cmd(video_path, output_path, None),
                    capture_output=True,
                    text=True,
                    check=True,
                )
            except subprocess.CalledProcessError as e2:
                raise RuntimeError(f"Falha ao extrair áudio: {e2.stderr}") from e2
        else:
            raise RuntimeError(f"Falha ao extrair áudio: {e.stderr}") from e
```

(Keep the `validate_ffmpeg()` guard, the `output_path`/`mkdir`/`logger.info` lines above, and the final `logger.info(...)` + `return output_path` below, unchanged.)

- [ ] **Step 4: Run the new tests**

Run: `.venv/bin/python -m pytest tests/test_audio_preprocessing.py -q`
Expected: PASS (8 tests).

- [ ] **Step 5: Full suite + import check**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS except the pre-existing `test_factory_selects_anthropic`.
Confirm `.venv/bin/python -c "import meeting_processor.audio"`.

- [ ] **Step 6: Commit**

```bash
git add meeting_processor/audio.py tests/test_audio_preprocessing.py
git commit -m "feat(audio): apply denoise filter in extract_audio with safe fallback"
```

---

## Self-Review

**Spec coverage:**
- Config `enable_audio_denoise` (default False) + `audio_filter` (default chain) + env overrides (bool + string) → Task 1. ✓
- `_ffmpeg_cmd(video_path, output_path, audio_filter)` — adds `-af` only when filter truthy, before `-y`/output → Task 1. ✓
- `extract_audio`: filter when `enable_audio_denoise`; byte-identical when off; fallback retry without filters on `CalledProcessError` with a filter; still raises when an unfiltered run fails → Task 2. ✓
- Tests: `_ffmpeg_cmd` with/without; denoise on/off argv; fallback (2 calls, 2nd no `-af`); unfiltered-failure raises; config defaults/env → Tasks 1-2. ✓
- Out of scope (per-meeting toggle, auto-detect, Settings UI, presets, output format) → untouched. ✓

**Placeholder scan:** none — every step has concrete code/commands.

**Type consistency:** `_ffmpeg_cmd(video_path, output_path, audio_filter)` (Task 1) called by `extract_audio` (Task 2) and the tests with the same signature. `config.enable_audio_denoise`/`config.audio_filter` (Task 1) read in `extract_audio` (Task 2). The tests monkeypatch `meeting_processor.audio.subprocess.run` + `meeting_processor.audio.validate_ffmpeg` (the names as used in `audio.py`). `output_path = config.temp_path / f"{video_path.stem}.wav"` is created by the fake run writing to `cmd[-1]`, so the trailing `output_path.stat()` succeeds. Names consistent throughout. ✓
