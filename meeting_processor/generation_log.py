"""Log de auditoria por reunião das ações manuais de geração.

Cada reunião tem um ``.generation-log.json`` na sua pasta com uma lista de
entradas (transcrição / resumo / exclusão do arquivo de origem), do mais antigo
para o mais novo no arquivo. ``read`` devolve do mais novo para o mais antigo.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_FILENAME = ".generation-log.json"
_LIMIT = 50
_lock = threading.Lock()


def _path(meeting_dir: Path) -> Path:
    return meeting_dir / _FILENAME


def read(meeting_dir: Path) -> list[dict]:
    """Entradas do log, do mais novo para o mais antigo. ``[]`` se ausente/corrompido."""
    p = _path(meeting_dir)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(data, list):
        return []
    return list(reversed(data))


def append(
    meeting_dir: Path,
    action: str,
    status: str,
    *,
    error: str | None = None,
    detail: str = "",
    started: datetime,
    completed: datetime,
) -> None:
    """Acrescenta uma entrada e regrava (mantém só as últimas ``_LIMIT``)."""
    with _lock:
        p = _path(meeting_dir)
        entries: list = []
        if p.exists():
            try:
                loaded = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(loaded, list):
                    entries = loaded
            except (json.JSONDecodeError, OSError):
                entries = []
        entries.append(
            {
                "action": action,
                "status": status,
                "error": error,
                "detail": detail,
                "started": started.isoformat(timespec="seconds"),
                "completed": completed.isoformat(timespec="seconds"),
            }
        )
        entries = entries[-_LIMIT:]
        try:
            tmp = p.with_name(_FILENAME + ".tmp")
            tmp.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(p)
        except OSError:
            logger.exception("Falha ao gravar generation-log em %s", p)
