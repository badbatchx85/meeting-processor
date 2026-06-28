"""Inicia o servidor Ollama automaticamente quando o provedor local é usado."""

from __future__ import annotations

import logging
import shutil
import subprocess
import time

import httpx

from .config import Settings

logger = logging.getLogger(__name__)


class EmbeddingError(RuntimeError):
    """Falha tratável ao gerar embedding (Ollama off, modelo ausente, etc.)."""


def embed(text: str, config: Settings) -> list[float]:
    """Embedding de ``text`` via Ollama (``POST /api/embeddings``).

    Levanta ``EmbeddingError`` quando o Ollama está off/inacessível ou a
    resposta não traz um vetor — o chamador decide se loga e segue (indexação
    best-effort) ou devolve erro amigável (busca).
    """
    base = config.ollama_base_url.rstrip("/")
    try:
        r = httpx.post(
            f"{base}/api/embeddings",
            json={"model": config.embedding_model, "prompt": text},
            timeout=config.ollama_request_timeout,
        )
        r.raise_for_status()
        vector = r.json().get("embedding")
    except Exception as e:  # noqa: BLE001 — qualquer falha vira erro tratável
        raise EmbeddingError(str(e)) from e
    if not isinstance(vector, list) or not vector:
        raise EmbeddingError("resposta do Ollama sem 'embedding'")
    return [float(x) for x in vector]


def is_running(base_url: str) -> bool:
    """True se o Ollama responde em ``{base_url}/api/tags``."""
    try:
        r = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=1.5)
        return r.status_code == 200
    except Exception:  # noqa: BLE001 — desligado/inacessível
        return False


def is_installed() -> bool:
    """True se o binário ``ollama`` existe no PATH (mesmo que parado)."""
    return shutil.which("ollama") is not None


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
