"""Mapa de nomes de falantes por reunião (Falante N -> nome real)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .config import Settings
from .models import Transcript, TranscriptSegment, WordTime
from .utils import write_json_atomic

logger = logging.getLogger(__name__)


def names_path(meeting_dir: Path) -> Path:
    return meeting_dir / "speakers.json"


def read_names(meeting_dir: Path) -> dict[str, str]:
    """Mapa {rótulo original: nome}; {} se ausente/ilegível; valores vazios fora."""
    p = names_path(meeting_dir)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if str(v).strip()}


def write_names(meeting_dir: Path, names: dict) -> None:
    clean = {str(k): str(v).strip() for k, v in (names or {}).items() if str(v).strip()}
    write_json_atomic(names_path(meeting_dir), clean)


def _segments_sidecar(meeting_dir: Path) -> Path | None:
    hits = list(meeting_dir.glob("Transcricao - *.words.json"))
    return hits[0] if hits else None


def detected_labels(meeting_dir: Path) -> list[str]:
    """Rótulos de falante distintos no sidecar, na ordem de primeira aparição."""
    side = _segments_sidecar(meeting_dir)
    if side is None:
        return []
    try:
        raw = json.loads(side.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    out: list[str] = []
    for s in raw:
        sp = s.get("speaker")
        if sp and sp not in out:
            out.append(sp)
    return out


def apply_names(segments: list[dict], names: dict) -> list[dict]:
    """Cópias dos segmentos com speaker mapeado (não muta a entrada/sidecar)."""
    out = []
    for s in segments:
        c = dict(s)
        if c.get("speaker"):
            c["speaker"] = names.get(c["speaker"]) or c["speaker"]
        out.append(c)
    return out


def regenerate_md(config: Settings, meeting_dir: Path, names: dict) -> None:
    """Reescreve a transcrição .md a partir do sidecar (rótulos originais) com o mapa.

    Idempotente: aplica o mapa sempre aos rótulos ORIGINAIS do sidecar; o sidecar
    nunca é alterado. Sem sidecar -> no-op.
    """
    side = _segments_sidecar(meeting_dir)
    if side is None:
        return
    try:
        raw = json.loads(side.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    segs = []
    for s in raw:
        orig = s.get("speaker")
        mapped = (names.get(orig) or orig) if orig else None
        words = [WordTime(**w) for w in s["words"]] if s.get("words") else None
        segs.append(
            TranscriptSegment(start=s["start"], end=s["end"], text=s["text"], speaker=mapped, words=words)
        )
    transcript = Transcript(
        segments=segs, full_text=" ".join(x.text for x in segs),
        language="pt", duration=(segs[-1].end if segs else 0.0),
    )
    from .note_generator import NoteGenerator
    ng = NoteGenerator(config)
    raw_path = ng.paths_for_existing(meeting_dir).raw_path
    ng._write_raw_transcription(transcript, raw_path)
    logger.info("Transcricao reescrita com nomes: %s", raw_path)
