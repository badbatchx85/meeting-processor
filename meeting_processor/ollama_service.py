"""Inicia o servidor Ollama automaticamente quando o provedor local é usado."""

from __future__ import annotations

import logging
import shutil
import subprocess
import time

import httpx

from .config import Settings

logger = logging.getLogger(__name__)


def is_running(base_url: str) -> bool:
    """True se o Ollama responde em ``{base_url}/api/tags``."""
    try:
        r = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=1.5)
        return r.status_code == 200
    except Exception:  # noqa: BLE001 — desligado/inacessível
        return False


def ensure_running(config: Settings, timeout: float = 15.0) -> bool:
    """Garante o Ollama no ar; se preciso, roda ``ollama serve`` e aguarda.

    Retorna False (sem derrubar nada) se o binário não existir ou não subir a
    tempo — o erro de conexão aparece normalmente no histórico de processamento.
    """
    base = config.ollama_base_url
    if is_running(base):
        return True

    exe = shutil.which("ollama")
    if not exe:
        logger.warning(
            "Ollama não encontrado no PATH — não foi possível iniciá-lo "
            "automaticamente. Instale em https://ollama.com ou rode 'ollama serve'."
        )
        return False

    logger.info("Ollama não está rodando; iniciando automaticamente (ollama serve)...")
    try:
        subprocess.Popen(  # noqa: S603 — binário resolvido via which, sem shell
            [exe, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("Falha ao iniciar o Ollama automaticamente: %s", e)
        return False

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_running(base):
            logger.info("Ollama disponível.")
            return True
        time.sleep(0.5)

    logger.warning("Ollama não respondeu a tempo após iniciar.")
    return False
