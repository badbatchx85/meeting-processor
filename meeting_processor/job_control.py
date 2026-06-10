"""Controle de jobs de processamento: cancelamento cooperativo."""
from __future__ import annotations

import threading
from typing import Any


class JobCancelled(Exception):
    """Levantada nos limites de etapa quando o usuário cancela um job."""


class CancelRegistry:
    """Mapeia ``(file, started_iso)`` para ``(Future, Event)`` de um job ativo.

    Thread-safe. Usado pelo endpoint de cancelamento para parar um job em
    execução (``event.set()``) ou remover um job ainda na fila
    (``future.cancel()``).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[tuple[str, str], tuple[Any, threading.Event]] = {}

    def register(self, file: str, started_iso: str, future: Any, event: threading.Event) -> None:
        with self._lock:
            self._jobs[(file, started_iso)] = (future, event)

    def lookup(self, file: str, started_iso: str):
        with self._lock:
            return self._jobs.get((file, started_iso))

    def discard(self, file: str, started_iso: str) -> None:
        with self._lock:
            self._jobs.pop((file, started_iso), None)
