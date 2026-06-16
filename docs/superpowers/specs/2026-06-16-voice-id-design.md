# Voice ID + known-voices repository (sub-project B)

**Date:** 2026-06-16
**Status:** Approved design

## Goal

Recognize speakers by voice across meetings. Capture a voiceprint (embedding)
per diarization cluster; when the user renames `Falante N → Ana` (sub-project A),
enroll Ana's voiceprint into a vault-level **known-voices repository**; on new
meetings, match each cluster's voiceprint against the repository and **suggest**
the recognized name in the rename panel (the user confirms with *Salvar*, which
re-enrolls/refines). Built on sub-project A; suggest-and-confirm (no auto-apply).

## Background (exact, from exploration)

- `diarizer.diarize(audio_path, config) -> list[(start,end,label)]` runs the
  pyannote pipeline and returns turns. `assign_speakers(segments, turns)` builds
  `friendly = {raw_label: "Falante N"}` (first-appearance) and mutates
  `seg.speaker`; returns `None` today.
- Pipeline: `_start_diarization` submits `diarize` to a thread; `_finish_diarization`
  does `turns = fut.result(); assign_speakers(...)`. `process()` order:
  `_start_diarization` → `transcribe` → `_finish_diarization` → `paths =
  prepare(...)` → `write_transcription`. **`paths` exists only AFTER
  `_finish_diarization`.**
- pyannote API (verified): the diarization pipeline supports
  `pipeline(audio, return_embeddings=True) -> (diarization, embeddings)` where
  `embeddings[i]` aligns to `diarization.labels()[i]`. Cosine distance ~0.25 =
  same speaker.
- Sub-project A: `speakers.json` map `{Falante N: name}`; `GET/POST
  /api/meetings/{id}/speakers`; the rename panel; the `.words.json` sidecar.
- Config has `enable_diarization`, `hf_token`, `diarization_model`.

## 1. Config

`voice_id_threshold: float = 0.45` (cosine **distance**; lower = stricter match)
+ `string_overrides["MEETING_VOICE_ID_THRESHOLD"]` parsed via the float overrides
(add to `float_overrides` if that dict is used for floats; else string + cast).
No separate enable flag — embeddings are captured whenever diarization runs.

## 2. Embedding extraction (`diarizer.py`)

Change `diarize` to return `(turns, emb_by_raw)`:

```python
def diarize(audio_path, config) -> tuple[list[tuple[float, float, str]], dict[str, list[float]]]:
    # ... load pipeline as today ...
    try:
        result = pipeline(str(audio_path), return_embeddings=True)
    except TypeError:                       # older pipeline: no embeddings arg
        result = pipeline(str(audio_path))
    if isinstance(result, tuple) and len(result) == 2:
        ann, emb = result                   # pyannote 3.1
    else:
        ann = getattr(result, "speaker_diarization", result)   # community-1
        emb = getattr(result, "embeddings", None)
    ann = getattr(ann, "speaker_diarization", ann)
    labels = list(ann.labels())
    turns = [(t.start, t.end, lbl) for t, _, lbl in ann.itertracks(yield_label=True)]
    emb_by_raw = {}
    if emb is not None:
        for i, lbl in enumerate(labels):
            try:
                emb_by_raw[lbl] = [float(x) for x in emb[i]]
            except Exception:               # noqa: BLE001
                pass
    return turns, emb_by_raw
```
The whole body stays wrapped → returns `([], {})` on any failure (graceful, as today).

`assign_speakers` now **returns** the friendly map (still mutates):

```python
    ...
    return friendly      # {raw_label: "Falante N"}
```

## 3. Pipeline — write the embeddings sidecar (`pipeline.py`)

`_finish_diarization(handle, transcript) -> dict[str, list[float]]` unpacks the
tuple, re-keys the embeddings to friendly labels, and **returns** them:

```python
        turns, emb_by_raw = fut.result()
        friendly = assign_speakers(transcript.segments, turns)
        emb_friendly = {friendly[raw]: vec for raw, vec in emb_by_raw.items() if raw in friendly}
        logger.info("Diarizacao: %d turnos, %d voiceprints.", len(turns), len(emb_friendly))
        return emb_friendly
```
(returns `{}` on the None/exception paths). In `process()`:
`diar = self._start_diarization(audio_path)` (unchanged) → after transcription,
`emb = self._finish_diarization(diar, transcript)`; then **after**
`paths = self.note_generator.prepare(...)`, write the sidecar:
`voiceprints.write_embeddings(paths.raw_path, emb)` (no-op when `emb` is empty).

## 4. Voiceprints module (`voiceprints.py`, new — pure, fully tested)

```python
def repo_path(vault: Path) -> Path                # vault/"wiki"/"voiceprints.json"
def load_repo(vault) -> dict                       # {name: {"vector":[...], "count":N}}; {} if absent
def save_repo(vault, repo) -> None                 # write_json_atomic
def enroll(repo, name, vector) -> dict             # running mean: new=(old*c+v)/(c+1); count+1; in-place+return
def _cosine_distance(a, b) -> float                # pure python; 1.0 if a zero-vector
def match(repo, vector, threshold) -> str | None   # smallest distance < threshold, else None
def write_embeddings(raw_md_path, emb) -> None      # write {Falante N: vec} to raw_md_path.with_suffix(".embeddings.json") when emb
def read_meeting_embeddings(meeting_dir) -> dict    # parse "Transcricao - *.embeddings.json" → {Falante N: vec}; {} if absent
def suggest(meeting_dir, vault, threshold) -> dict  # {Falante N: matched_name} for clusters whose voiceprint matches the repo
```
No new deps (pure-Python cosine; `write_json_atomic` from utils).

## 5. Endpoints (`web/app.py`)

- `GET …/speakers` gains `"suggestions": voiceprints.suggest(meeting_dir,
  config.vault_path, config.voice_id_threshold)` alongside `detected`/`names`.
- `POST …/speakers`: after `write_names` + `regenerate_md`, **enroll** —
  ```python
  embs = voiceprints.read_meeting_embeddings(meeting_dir)
  if embs:
      repo = voiceprints.load_repo(config.vault_path)
      for label, name in speaker_names.read_names(meeting_dir).items():
          if label in embs:
              voiceprints.enroll(repo, name, embs[label])
      voiceprints.save_repo(config.vault_path, repo)
  ```
  (wrapped so enrollment failure never fails the save).

## 6. Frontend

- `SpeakerInfo` type gains `suggestions: Record<string, string>`.
- `SpeakerNames` panel: seed inputs from `{...suggestions, ...names}` (confirmed
  names win; suggestions fill the rest). For a label whose value comes from a
  **suggestion** and is not in confirmed `names`, show a small `reconhecido`
  badge. *Salvar* POSTs the (reviewed) names → backend enrolls.

## Testing

`tests/test_voiceprints.py` (pure — fully verified locally):
- `enroll` running mean (two enrollments of `[2,0]` then `[0,2]` → `[1,1]`, count 2);
  `match` returns the nearest name under threshold and `None` above; `_cosine_distance`
  (identical→0, orthogonal→1, zero-vector→1); `load_repo`/`save_repo` round-trip;
  `read_meeting_embeddings`/`write_embeddings` sidecar round-trip; `suggest` from a
  seeded repo + embeddings sidecar returns the matched label→name.
- `diarizer`: a fake pipeline returning `(annotation, embeddings)` with
  `return_embeddings=True` → `diarize` returns `(turns, emb_by_raw)`;
  `assign_speakers` returns the friendly map.
- `pipeline._finish_diarization` re-keys embeddings to `Falante N` and returns them
  (mock `diarize` to return `([(0,1,"SPEAKER_00")], {"SPEAKER_00":[...]})`); `process`
  writes the `.embeddings.json` sidecar (covered via a focused `_finish` test +
  asserting the sidecar from `write_embeddings`).
- endpoints: `GET /speakers` returns `suggestions` from a seeded repo + sidecar;
  `POST /speakers` enrolls (repo gains the name with the cluster's vector).
- `frontend/src/__tests__/voiceId.test.tsx`: the panel pre-fills a suggested name +
  shows the `reconhecido` badge; confirmed names override suggestions.
- **Real model**: the user verifies embedding accuracy (recognition across two real
  meetings) with their HF token — the pyannote-gated part, same as diarization.

## Out of scope

- Auto-apply (chose suggest+confirm).
- A roster-management UI (list/delete known voices) — enrollment is via renaming;
  deletion is a future nicety.
- Shared/cross-vault voiceprints; verification beyond nearest-match; tuning the
  threshold per person.
- Capturing embeddings for the openai/cpp backends (only the pyannote diarization
  pass yields them — which is exactly where speakers come from anyway).
