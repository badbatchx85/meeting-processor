"""Repositório de vozes conhecidas (voiceprints) + matching por cosseno.

Puro (sem pyannote/numpy): vetores são listas de float. O repositório fica em
``<vault>/wiki/voiceprints.json`` = {nome: {"vector": [...], "count": N}}.
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path

from .utils import write_json_atomic

logger = logging.getLogger(__name__)


def repo_path(vault: Path) -> Path:
    return Path(vault) / "wiki" / "voiceprints.json"


def load_repo(vault: Path) -> dict:
    p = repo_path(vault)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_repo(vault: Path, repo: dict) -> None:
    write_json_atomic(repo_path(vault), repo)


def enroll(repo: dict, name: str, vector: list[float]) -> dict:
    """Adiciona/refina a voiceprint de ``name`` (média corrente). In-place + retorna."""
    entry = repo.get(name)
    if entry and entry.get("vector") and len(entry["vector"]) == len(vector):
        c = entry["count"]
        repo[name] = {
            "vector": [(o * c + v) / (c + 1) for o, v in zip(entry["vector"], vector)],
            "count": c + 1,
        }
    else:
        repo[name] = {"vector": [float(v) for v in vector], "count": 1}
    return repo


def _cosine_distance(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 1.0
    return 1.0 - dot / (na * nb)


def match(repo: dict, vector: list[float], threshold: float) -> str | None:
    """Nome com menor distância de cosseno < threshold, ou None."""
    best_name, best_d = None, threshold
    for name, entry in repo.items():
        vec = entry.get("vector") if isinstance(entry, dict) else None
        if not vec or len(vec) != len(vector):
            continue
        d = _cosine_distance(vector, vec)
        if d < best_d:
            best_d, best_name = d, name
    return best_name


def _embeddings_sidecar(meeting_dir: Path) -> Path | None:
    hits = list(Path(meeting_dir).glob("Transcricao - *.embeddings.json"))
    return hits[0] if hits else None


def write_embeddings(raw_md_path: Path, emb: dict) -> None:
    """Escreve {Falante N: vetor} ao lado da transcrição. No-op se vazio."""
    if not emb:
        return
    write_json_atomic(Path(raw_md_path).with_suffix(".embeddings.json"), emb)


def read_meeting_embeddings(meeting_dir: Path) -> dict:
    side = _embeddings_sidecar(meeting_dir)
    if side is None:
        return {}
    try:
        data = json.loads(side.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def remove_embeddings(meeting_dir: Path) -> None:
    """Remove o sidecar de embeddings da reunião, se existir (no-op se ausente).

    Usado quando os rótulos de falante deixam de valer (ex.: re-transcrição sem
    diarização), para manter o invariante "embeddings sempre batem com .words.json".
    """
    side = _embeddings_sidecar(meeting_dir)
    if side is not None:
        side.unlink(missing_ok=True)


def auto_resolve(emb: dict, vault: Path, auto_threshold: float) -> dict:
    """{label: nome reconhecido} para clusters que casam com o repositório abaixo de
    ``auto_threshold``. Read-only: não enrola nem grava o repositório."""
    if not emb:
        return {}
    repo = load_repo(vault)
    if not repo:
        return {}
    out = {}
    for label, vec in emb.items():
        name = match(repo, vec, auto_threshold)
        if name:
            out[label] = name
    return out


def suggest(meeting_dir: Path, vault: Path, threshold: float) -> dict:
    """{Falante N: nome reconhecido} para clusters que casam com o repositório."""
    return auto_resolve(read_meeting_embeddings(meeting_dir), vault, threshold)
