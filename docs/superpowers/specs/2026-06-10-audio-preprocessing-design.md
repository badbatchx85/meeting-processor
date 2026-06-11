# Audio Pre-processing (denoise / normalize before Whisper)

**Date:** 2026-06-10
**Status:** Approved design

## Goal

Optionally clean the extracted audio before Whisper transcribes it — high-pass,
FFT denoise, loudness-normalize — so noisy/quiet recordings produce better
transcripts (and therefore better summaries). Opt-in, env-configured, with a
safety fallback so a bad filter never fails the job.

## Background (exact, from exploration)

- `extract_audio(video_path, config) -> Path` (`meeting_processor/audio.py`)
  runs `ffmpeg -i <in> -vn -acodec pcm_s16le -ar 16000 -ac 1 -y <out>.wav` via
  `subprocess.run([...], capture_output=True, text=True, check=True)`, raising
  `RuntimeError(f"Falha ao extrair áudio: {e.stderr}")` on
  `CalledProcessError`. No audio filters today.
- `config.temp_path` is the output dir; `validate_ffmpeg()` guards ffmpeg.
- `config.py` `load_config` has `bool_overrides` and `string_overrides` dicts
  (ENV_KEY → attr). The pipeline calls `extract_audio(video_path, self.config)`.

## 1. Config (`config.py`) — env only

- `enable_audio_denoise: bool = False` → `bool_overrides["MEETING_AUDIO_DENOISE"]`.
- `audio_filter: str = "highpass=f=80,afftdn=nf=-25,loudnorm=I=-16:TP=-1.5:LRA=11"`
  → `string_overrides["MEETING_AUDIO_FILTER"]`. One tunable ffmpeg `-af` string
  (high-pass at 80 Hz → FFT denoise → EBU R128 loudness normalize). Configurable
  so the user can A/B without code changes.

## 2. Command builder (`audio.py`)

`_ffmpeg_cmd(video_path: Path, output_path: Path, audio_filter: str | None) -> list[str]`:
returns the ffmpeg arg list — the existing flags, plus `["-af", audio_filter]`
inserted (before the output path) **only when `audio_filter` is truthy**. Pure,
unit-testable. `extract_audio` builds its command through this helper.

```python
def _ffmpeg_cmd(video_path, output_path, audio_filter):
    cmd = ["ffmpeg", "-i", str(video_path), "-vn",
           "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1"]
    if audio_filter:
        cmd += ["-af", audio_filter]
    cmd += ["-y", str(output_path)]
    return cmd
```

## 3. `extract_audio` behavior

- Compute `audio_filter = config.audio_filter if config.enable_audio_denoise else None`.
- Run `_ffmpeg_cmd(video_path, output_path, audio_filter)`.
- **Safety fallback:** if that raises `CalledProcessError` **and** a filter was
  applied (`audio_filter` truthy), log a warning and retry once with
  `_ffmpeg_cmd(..., None)` (no filters). If the no-filter run also fails (or the
  first run had no filter), raise `RuntimeError(f"Falha ao extrair áudio: ...")`
  as today.
- When denoise is off, the command and behavior are byte-identical to current.

```python
    audio_filter = config.audio_filter if config.enable_audio_denoise else None
    try:
        subprocess.run(_ffmpeg_cmd(video_path, output_path, audio_filter),
                       capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        if audio_filter:
            logger.warning(
                "Falha no ffmpeg com filtro de audio. Repetindo sem filtro. (%s)",
                (e.stderr or "").strip()[-300:] or e,
            )
            try:
                subprocess.run(_ffmpeg_cmd(video_path, output_path, None),
                               capture_output=True, text=True, check=True)
            except subprocess.CalledProcessError as e2:
                raise RuntimeError(f"Falha ao extrair áudio: {e2.stderr}") from e2
        else:
            raise RuntimeError(f"Falha ao extrair áudio: {e.stderr}") from e
```

## Testing (TDD — mock `subprocess.run`, no real ffmpeg/audio)

`tests/test_audio_preprocessing.py`:
- **`_ffmpeg_cmd`**: with a filter → the list contains `"-af"` immediately
  followed by the filter, before `"-y"`/output; with `None` → no `"-af"`.
- **`extract_audio` denoise on**: monkeypatch `subprocess.run` to capture the
  argv and create the output file; `config.enable_audio_denoise=True` → argv
  contains `"-af"` and `config.audio_filter`. Also monkeypatch `validate_ffmpeg`
  → True.
- **denoise off**: argv has no `"-af"`.
- **fallback**: `subprocess.run` raises `CalledProcessError` on the first call
  (filtered) then succeeds on the second; assert `extract_audio` returns the
  path, `subprocess.run` was called twice, and the second argv has no `"-af"`.
- **no-filter failure still raises**: denoise off + `subprocess.run` raises →
  `RuntimeError`.
- **config**: defaults (`enable_audio_denoise is False`, `audio_filter` default
  string) + `MEETING_AUDIO_DENOISE`/`MEETING_AUDIO_FILTER` env overrides.
- **Real A/B (out of CI):** compare a noisy clip's Whisper transcript with and
  without denoise; quality is judged on real audio.

## Out of scope

- Per-meeting denoise toggle (env-global, like diarization).
- Adaptive / automatic noise detection or per-recording filter selection.
- A Settings UI.
- Multiple named presets (one tunable filter string instead).
- Changing the 16 kHz / mono / PCM output format.
