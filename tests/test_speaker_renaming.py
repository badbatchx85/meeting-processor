"""Renomeação de falantes (sub-projeto A)."""
from datetime import datetime

from meeting_processor.models import Transcript, TranscriptSegment
from meeting_processor.note_generator import NoteGenerator


def test_sidecar_written_for_diarized_without_words(config):
    ng = NoteGenerator(config)
    paths = ng.prepare("reu.mp4", datetime(2026, 1, 1, 10, 0, 0))
    seg = TranscriptSegment(start=0, end=1, text="oi", speaker="Falante 1")  # words=None
    ng.write_transcription(Transcript(segments=[seg], full_text="oi", language="pt", duration=1), paths)
    assert paths.raw_path.with_suffix(".words.json").exists()


# --- Task 2: speaker_names module ------------------------------------------

import json

from meeting_processor import speaker_names as sn


def _seed_sidecar(config, folder, segs):
    d = config.reunioes_path / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / f"Transcricao - {folder}.words.json").write_text(json.dumps(segs), encoding="utf-8")
    return d


def test_names_roundtrip_and_blank_dropped(config):
    d = config.reunioes_path / "m1"
    d.mkdir(parents=True, exist_ok=True)
    sn.write_names(d, {"Falante 1": "Ana", "Falante 2": "  "})
    assert sn.read_names(d) == {"Falante 1": "Ana"}     # blank dropped


def test_detected_labels_distinct_in_order(config):
    d = _seed_sidecar(config, "m2", [
        {"start": 0, "end": 1, "text": "a", "speaker": "Falante 2", "words": None},
        {"start": 1, "end": 2, "text": "b", "speaker": "Falante 1", "words": None},
        {"start": 2, "end": 3, "text": "c", "speaker": "Falante 2", "words": None},
        {"start": 3, "end": 4, "text": "d", "speaker": None, "words": None},
    ])
    assert sn.detected_labels(d) == ["Falante 2", "Falante 1"]


def test_apply_names_maps_and_passes_through():
    segs = [{"start": 0, "end": 1, "text": "a", "speaker": "Falante 1", "words": None},
            {"start": 1, "end": 2, "text": "b", "speaker": "Falante 9", "words": None}]
    out = sn.apply_names(segs, {"Falante 1": "Ana"})
    assert out[0]["speaker"] == "Ana" and out[1]["speaker"] == "Falante 9"


def test_regenerate_md_idempotent(config):
    d = _seed_sidecar(config, "m3", [
        {"start": 0, "end": 1, "text": "oi", "speaker": "Falante 1", "words": None},
        {"start": 1, "end": 2, "text": "ola", "speaker": "Falante 2", "words": None},
    ])
    md = d / "Transcricao - m3.md"
    side = d / "Transcricao - m3.words.json"
    before = side.read_text(encoding="utf-8")

    sn.regenerate_md(config, d, {"Falante 1": "Ana"})
    text = md.read_text(encoding="utf-8")
    assert "Ana: oi" in text and "Falante 2: ola" in text
    assert side.read_text(encoding="utf-8") == before          # sidecar untouched

    sn.regenerate_md(config, d, {"Falante 1": "Carlos"})        # re-rename
    text2 = md.read_text(encoding="utf-8")
    assert "Carlos: oi" in text2 and "Ana" not in text2        # no accumulation


# --- Task 3: endpoints -----------------------------------------------------


def _seed_meeting(config, folder, segs):
    d = config.reunioes_path / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / f"Transcricao - {folder}.md").write_text("# Transcricao\n\n**[00:00]** Falante 1: oi  \n", encoding="utf-8")
    (d / f"Transcricao - {folder}.words.json").write_text(json.dumps(segs), encoding="utf-8")
    return d


def test_get_speakers_detected_and_names(client, config):
    mid = "2026-01-01 10h00 - reu"
    _seed_meeting(config, mid, [
        {"start": 0, "end": 1, "text": "oi", "speaker": "Falante 1", "words": None},
        {"start": 1, "end": 2, "text": "ola", "speaker": "Falante 2", "words": None},
    ])
    r = client.get(f"/api/meetings/{mid}/speakers")
    assert r.status_code == 200
    assert r.json()["detected"] == ["Falante 1", "Falante 2"]
    assert r.json()["names"] == {}


def test_post_speakers_persists_and_rewrites_md(client, config):
    mid = "2026-01-02 10h00 - reu"
    d = _seed_meeting(config, mid, [
        {"start": 0, "end": 1, "text": "oi", "speaker": "Falante 1", "words": None},
    ])
    r = client.post(f"/api/meetings/{mid}/speakers", json={"names": {"Falante 1": "Ana"}})
    assert r.status_code == 200
    assert "Ana: oi" in (d / f"Transcricao - {mid}.md").read_text(encoding="utf-8")
    side = json.loads((d / f"Transcricao - {mid}.words.json").read_text(encoding="utf-8"))
    assert side[0]["speaker"] == "Falante 1"
    assert client.get(f"/api/meetings/{mid}/speakers").json()["names"] == {"Falante 1": "Ana"}


def test_words_endpoint_applies_names(client, config):
    mid = "2026-01-03 10h00 - reu"
    _seed_meeting(config, mid, [
        {"start": 0, "end": 1, "text": "oi", "speaker": "Falante 1", "words": None},
    ])
    client.post(f"/api/meetings/{mid}/speakers", json={"names": {"Falante 1": "Ana"}})
    served = client.get(f"/api/meetings/{mid}/words").json()
    assert served[0]["speaker"] == "Ana"


def test_apply_speaker_map_renames_in_place():
    from meeting_processor.models import TranscriptSegment
    from meeting_processor import speaker_names
    segs = [
        TranscriptSegment(start=0, end=1, text="a", speaker="Falante 1"),
        TranscriptSegment(start=1, end=2, text="b", speaker="Falante 2"),
        TranscriptSegment(start=2, end=3, text="c", speaker=None),
    ]
    speaker_names.apply_speaker_map(segs, {"Falante 1": "Ana"})
    assert [s.speaker for s in segs] == ["Ana", "Falante 2", None]
