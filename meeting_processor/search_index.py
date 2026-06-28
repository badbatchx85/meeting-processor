"""Índice de busca semântica sobre transcrições (sub-projeto #4 v1).

Espelha ``voiceprints.py``: vetores são listas de float, persistência em JSON
atômico, cosseno em Python puro. O índice fica em
``<vault>/wiki/.search-index.json`` = lista de rows
``{"meeting_id": str, "text": str, "start": float, "end": float, "vector": [...]}``.

Corpus pequeno (vault pessoal) => varredura linear basta; sem dep de vector DB.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .utils import write_json_atomic
from .voiceprints import _cosine_distance

logger = logging.getLogger(__name__)


def index_path(vault: Path) -> Path:
    return Path(vault) / "wiki" / ".search-index.json"


def load_index(vault: Path) -> list[dict]:
    p = index_path(vault)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def save_index(vault: Path, rows: list[dict]) -> None:
    write_json_atomic(index_path(vault), rows)


def chunk_segments(segments: list[dict], max_chars: int = 500) -> list[dict]:
    """Agrupa segmentos consecutivos até ~``max_chars`` por chunk.

    Cada chunk = ``{text, start, end}`` (start do 1º segmento do grupo, end do
    último). Puro, sem I/O. Segmentos com texto vazio são ignorados.
    """
    chunks: list[dict] = []
    cur_texts: list[str] = []
    cur_start: float | None = None
    cur_end: float | None = None

    def flush() -> None:
        nonlocal cur_texts, cur_start, cur_end
        if cur_texts:
            chunks.append({
                "text": " ".join(cur_texts),
                "start": cur_start,
                "end": cur_end,
            })
        cur_texts, cur_start, cur_end = [], None, None

    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        # Estouraria o limite e já há conteúdo => fecha o chunk atual primeiro.
        if cur_texts and len(" ".join(cur_texts)) + 1 + len(text) > max_chars:
            flush()
        if not cur_texts:
            cur_start = seg.get("start")
        cur_texts.append(text)
        cur_end = seg.get("end")

    flush()
    return chunks


def add_meeting(vault: Path, meeting_id: str, chunks_with_vectors: list[dict]) -> None:
    """Substitui os chunks de ``meeting_id`` no índice (idempotente p/ reindex)."""
    rows = [r for r in load_index(vault) if r.get("meeting_id") != meeting_id]
    for ch in chunks_with_vectors:
        rows.append({
            "meeting_id": meeting_id,
            "text": ch["text"],
            "start": ch["start"],
            "end": ch["end"],
            "vector": ch["vector"],
        })
    save_index(vault, rows)


def remove_meeting(vault: Path, meeting_id: str) -> None:
    """Remove do índice os chunks daquela reunião (no-op se ausente)."""
    rows = load_index(vault)
    kept = [r for r in rows if r.get("meeting_id") != meeting_id]
    if len(kept) != len(rows):
        save_index(vault, kept)


def query(rows: list[dict], query_vec: list[float], k: int, min_score: float) -> list[dict]:
    """Top-k rows por similaridade de cosseno (1 - distância), desc.

    Filtra ``score >= min_score``; devolve cada row sem o campo ``vector``.
    """
    scored = []
    for r in rows:
        vec = r.get("vector")
        if not vec or len(vec) != len(query_vec):
            continue
        score = 1.0 - _cosine_distance(query_vec, vec)
        if score < min_score:
            continue
        scored.append({
            "meeting_id": r["meeting_id"],
            "text": r["text"],
            "start": r["start"],
            "end": r["end"],
            "score": score,
        })
    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[:k]
