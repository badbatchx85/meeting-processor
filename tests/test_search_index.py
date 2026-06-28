"""Índice de busca semântica sobre transcrições (sub-projeto #4 v1).

Espelha a forma dos testes de ``voiceprints``: funções puras com vetores fixos
(sem Ollama) + round-trip de I/O atômico no vault.
"""
from meeting_processor import search_index as si


# --- chunk_segments (puro) --------------------------------------------------


def test_chunk_segments_groups_until_max_chars():
    segs = [
        {"start": 0.0, "end": 1.0, "text": "abc"},
        {"start": 1.0, "end": 2.0, "text": "def"},
        {"start": 2.0, "end": 3.0, "text": "ghijklmnop"},
    ]
    chunks = si.chunk_segments(segs, max_chars=8)
    # "abc" + "def" = 7 chars cabem juntos; o terceiro estoura => novo chunk.
    assert len(chunks) == 2
    assert chunks[0] == {"text": "abc def", "start": 0.0, "end": 2.0}
    assert chunks[1] == {"text": "ghijklmnop", "start": 2.0, "end": 3.0}


def test_chunk_segments_carries_first_start_and_last_end():
    segs = [
        {"start": 10.0, "end": 11.0, "text": "um"},
        {"start": 11.0, "end": 12.5, "text": "dois"},
    ]
    chunks = si.chunk_segments(segs, max_chars=500)
    assert len(chunks) == 1
    assert chunks[0]["start"] == 10.0
    assert chunks[0]["end"] == 12.5
    assert chunks[0]["text"] == "um dois"


def test_chunk_segments_empty():
    assert si.chunk_segments([], max_chars=500) == []


def test_chunk_segments_skips_blank_text():
    segs = [
        {"start": 0.0, "end": 1.0, "text": "  "},
        {"start": 1.0, "end": 2.0, "text": "oi"},
    ]
    chunks = si.chunk_segments(segs, max_chars=500)
    assert len(chunks) == 1
    assert chunks[0]["text"] == "oi"
    assert chunks[0]["start"] == 1.0


# --- I/O round-trip ---------------------------------------------------------


def _row(meeting_id, text, start, end, vector):
    return {"meeting_id": meeting_id, "text": text, "start": start, "end": end, "vector": vector}


def test_index_roundtrip(config):
    rows = [_row("m1", "oi", 0.0, 1.0, [1.0, 0.0])]
    si.save_index(config.vault_path, rows)
    assert si.load_index(config.vault_path) == rows


def test_load_index_missing_returns_empty(config):
    assert si.load_index(config.vault_path) == []


def test_add_meeting_replaces_only_that_meeting(config):
    si.add_meeting(config.vault_path, "m1", [
        {"text": "a", "start": 0.0, "end": 1.0, "vector": [1.0, 0.0]},
    ])
    si.add_meeting(config.vault_path, "m2", [
        {"text": "b", "start": 0.0, "end": 1.0, "vector": [0.0, 1.0]},
    ])
    # Reindexar m1 substitui só os chunks de m1, preservando m2.
    si.add_meeting(config.vault_path, "m1", [
        {"text": "a2", "start": 0.0, "end": 1.0, "vector": [1.0, 1.0]},
    ])
    rows = si.load_index(config.vault_path)
    by_meeting = {r["meeting_id"]: r["text"] for r in rows}
    assert by_meeting == {"m1": "a2", "m2": "b"}


def test_remove_meeting(config):
    si.add_meeting(config.vault_path, "m1", [
        {"text": "a", "start": 0.0, "end": 1.0, "vector": [1.0, 0.0]},
    ])
    si.add_meeting(config.vault_path, "m2", [
        {"text": "b", "start": 0.0, "end": 1.0, "vector": [0.0, 1.0]},
    ])
    si.remove_meeting(config.vault_path, "m1")
    rows = si.load_index(config.vault_path)
    assert [r["meeting_id"] for r in rows] == ["m2"]
    si.remove_meeting(config.vault_path, "nope")  # no-op, sem raise


# --- query (puro) -----------------------------------------------------------


def _rows():
    return [
        _row("m1", "perto", 0.0, 1.0, [1.0, 0.0]),
        _row("m2", "meio", 1.0, 2.0, [1.0, 1.0]),
        _row("m3", "longe", 2.0, 3.0, [0.0, 1.0]),
    ]


def test_query_orders_by_cosine_desc_and_strips_vector():
    out = si.query(_rows(), [1.0, 0.0], k=10, min_score=0.0)
    assert [r["meeting_id"] for r in out] == ["m1", "m2", "m3"]
    assert all("vector" not in r for r in out)
    assert out[0]["score"] == 1.0  # idêntico => similaridade 1
    assert set(out[0]) == {"meeting_id", "text", "start", "end", "score"}


def test_query_respects_k():
    out = si.query(_rows(), [1.0, 0.0], k=2, min_score=0.0)
    assert [r["meeting_id"] for r in out] == ["m1", "m2"]


def test_query_respects_min_score():
    # m3 é ortogonal ao alvo => score 0; exigir > 0 o exclui.
    out = si.query(_rows(), [1.0, 0.0], k=10, min_score=0.01)
    assert [r["meeting_id"] for r in out] == ["m1", "m2"]


def test_query_empty_index():
    assert si.query([], [1.0, 0.0], k=10, min_score=0.0) == []
