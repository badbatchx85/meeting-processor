"""Gerenciamento de runtime do frontend web.

Aqui mora a lógica que precisa de estado vivo enquanto o servidor web
está de pé:

- ``WatcherSupervisor``: sobe/derruba o ``python -m meeting_processor watch``
  como subprocess gerenciado.
- ``set_llm_provider``: alterna entre Claude API e Ollama, persistindo
  a escolha no ``.env`` e atualizando o ``Settings`` em memória.

O design é deliberadamente simples (singleton in-process). Como o
servidor web roda em um único processo uvicorn, dá conta — sem precisar
de banco, fila ou IPC.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from ..config import Settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Watcher supervisor
# ---------------------------------------------------------------------------


class WatcherSupervisor:
    """Mantém uma referência ao subprocess do watcher.

    Thread-safe — start/stop podem ser chamados de qualquer handler.
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._started_at: datetime | None = None

    # ---- estado ---------------------------------------------------------

    def is_running(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def info(self) -> dict:
        with self._lock:
            running = self._proc is not None and self._proc.poll() is None
            return {
                "running": running,
                "pid": self._proc.pid if running and self._proc else None,
                "started_at": self._started_at.isoformat()
                if self._started_at
                else None,
                "exit_code": self._proc.returncode
                if self._proc and self._proc.poll() is not None
                else None,
            }

    # ---- ações ----------------------------------------------------------

    def start(self) -> dict:
        """Sobe o watcher. No-op se já estiver rodando."""
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return {"ok": True, "already_running": True, "pid": self._proc.pid}

            env = os.environ.copy()
            extra_path = os.environ.get("MEETING_EXTRA_PATH", "")
            if extra_path:
                env["PATH"] = extra_path + os.pathsep + env.get("PATH", "")

            # CREATE_NEW_PROCESS_GROUP no Windows permite enviar Ctrl+Break
            # sem matar o processo pai. Em outros SOs, deixa flags=0.
            creationflags = 0
            if sys.platform == "win32":
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

            try:
                self._proc = subprocess.Popen(
                    [sys.executable, "-m", "meeting_processor", "watch"],
                    cwd=str(self.project_root),
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=creationflags,
                )
            except Exception as e:  # noqa: BLE001
                logger.exception("Falha ao iniciar watcher")
                return {"ok": False, "error": str(e)}

            self._started_at = datetime.now()
            logger.info("Watcher iniciado (PID=%d)", self._proc.pid)
            return {"ok": True, "pid": self._proc.pid}

    def stop(self, timeout: float = 10.0) -> dict:
        """Termina o watcher graciosamente; força em último caso."""
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                self._proc = None
                self._started_at = None
                return {"ok": True, "already_stopped": True}

            proc = self._proc
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    logger.warning("Watcher não respondeu a terminate(); kill().")
                    proc.kill()
                    proc.wait(timeout=5)
            except Exception as e:  # noqa: BLE001
                logger.exception("Erro ao parar watcher")
                return {"ok": False, "error": str(e)}
            finally:
                self._proc = None
                self._started_at = None

            logger.info("Watcher parado.")
            return {"ok": True}

    def restart(self) -> dict:
        self.stop()
        return self.start()


# Singleton compartilhado pela aplicação FastAPI
_supervisor: WatcherSupervisor | None = None
_supervisor_lock = threading.Lock()


def get_supervisor(project_root: Path) -> WatcherSupervisor:
    global _supervisor
    with _supervisor_lock:
        if _supervisor is None:
            _supervisor = WatcherSupervisor(project_root)
        return _supervisor


# ---------------------------------------------------------------------------
# LLM provider toggle (persistente em .env + atualiza Settings em memória)
# ---------------------------------------------------------------------------


VALID_PROVIDERS = ("anthropic", "openai", "gemini", "local", "none")


def _env_path(project_root: Path) -> Path:
    return project_root / ".env"


def _read_env_lines(env_file: Path) -> list[str]:
    if not env_file.exists():
        return []
    return env_file.read_text(encoding="utf-8").splitlines()


def _upsert_env_var(lines: list[str], key: str, value: str) -> list[str]:
    """Atualiza ou adiciona ``key=value`` preservando comentários e ordem."""
    new_lines: list[str] = []
    found = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue
        existing_key, _, _ = stripped.partition("=")
        if existing_key.strip() == key:
            new_lines.append(f"{key}={value}")
            found = True
        else:
            new_lines.append(line)
    if not found:
        if new_lines and new_lines[-1].strip() != "":
            new_lines.append("")
        new_lines.append(f"{key}={value}")
    return new_lines


def persist_env_setting(project_root: Path, key: str, value: str) -> None:
    """Grava ``key=value`` no ``.env`` e na env do processo atual.

    Centraliza o padrão usado para persistir configurações editáveis pela
    interface (provedor de LLM, pasta monitorada, ...).
    """
    env_file = _env_path(project_root)
    lines = _read_env_lines(env_file)
    new_lines = _upsert_env_var(lines, key, value)
    env_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    os.environ[key] = value


def set_llm_provider(config: Settings, provider: str) -> dict:
    """Altera o provedor de LLM em runtime e persiste no ``.env``.

    Returns:
        dict com flags de status:
            ok: True/False
            previous: provedor anterior
            current: provedor agora ativo
            watcher_restart_needed: o watcher subprocess herda a env só na
                inicialização — se estiver rodando, precisa restart para ler
                a nova preferência.
    """
    provider = provider.lower().strip()
    if provider == "ollama":
        provider = "local"
    if provider not in VALID_PROVIDERS:
        return {
            "ok": False,
            "error": f"provider inválido: '{provider}' (esperado: {VALID_PROVIDERS})",
        }

    previous = config.llm_provider

    # 1. Persiste no .env + env do processo atual (subprocess novos herdam)
    persist_env_setting(Path(config.project_root), "MEETING_LLM_PROVIDER", provider)

    # 2. Atualiza o Settings em memória (Pipeline novos pegam isso)
    config.llm_provider = provider

    logger.info("LLM provider alterado: %s -> %s", previous, provider)
    return {
        "ok": True,
        "previous": previous,
        "current": provider,
        # O processo atual já enxerga a mudança. Mas se o watcher subprocess
        # estiver rodando, ele iniciou com a env antiga.
        "watcher_restart_needed": True,
    }


# Provedor -> (campo no Settings, variável de ambiente). "none" não tem modelo.
_MODEL_FIELDS = {
    "anthropic": ("anthropic_model", "MEETING_ANTHROPIC_MODEL"),
    "openai": ("openai_model", "MEETING_OPENAI_MODEL"),
    "gemini": ("gemini_model", "MEETING_GEMINI_MODEL"),
    "local": ("ollama_model", "MEETING_OLLAMA_MODEL"),
}


def set_llm_model(config: Settings, provider: str, model: str) -> dict:
    """Altera o modelo de um provedor em runtime e persiste no ``.env``."""
    provider = (provider or "").lower().strip()
    if provider == "ollama":
        provider = "local"
    if provider not in _MODEL_FIELDS:
        return {"ok": False, "error": f"Provedor sem modelo configurável: {provider}"}
    model = (model or "").strip()
    if not model:
        return {"ok": False, "error": "Modelo vazio"}

    field, env_key = _MODEL_FIELDS[provider]
    persist_env_setting(Path(config.project_root), env_key, model)
    setattr(config, field, model)
    logger.info("Modelo de %s alterado para: %s", provider, model)
    return {"ok": True, "provider": provider, "model": model}


# Provedor -> (campo da chave no Settings, variável de ambiente).
_KEY_FIELDS = {
    "anthropic": ("anthropic_api_key", "ANTHROPIC_API_KEY"),
    "openai": ("openai_api_key", "OPENAI_API_KEY"),
    "gemini": ("gemini_api_key", "GEMINI_API_KEY"),
}


def set_llm_key(config: Settings, provider: str, key: str) -> dict:
    """Grava a chave de API de um provedor no ``.env`` (write-only).

    Nunca devolve o valor da chave nem o registra em log.
    """
    provider = (provider or "").lower().strip()
    if provider == "ollama":
        provider = "local"
    if provider not in _KEY_FIELDS:
        return {"ok": False, "error": f"Provedor sem chave de API: {provider}"}
    key = (key or "").strip()
    if not key:
        return {"ok": False, "error": "Chave vazia"}

    field, env_key = _KEY_FIELDS[provider]
    persist_env_setting(Path(config.project_root), env_key, key)
    setattr(config, field, key)
    logger.info("Chave de API de %s atualizada.", provider)  # sem o valor
    return {"ok": True, "provider": provider}


def set_pipeline_steps(
    config: Settings,
    *,
    summary: bool,
    note: bool,
    kanban: bool,
    wiki: bool,
) -> dict:
    """Liga/desliga etapas do pipeline e persiste no ``.env``.

    Áudio e transcrição rodam sempre; aqui controlamos apenas as
    etapas opcionais. As dependências (nota/kanban/wiki exigem resumo)
    são resolvidas por ``Settings.steps()``.
    """
    root = Path(config.project_root)
    values = {
        "MEETING_ENABLE_SUMMARY": summary,
        "MEETING_ENABLE_NOTE": note,
        "MEETING_ENABLE_KANBAN": kanban,
        "MEETING_ENABLE_WIKI": wiki,
    }
    for key, value in values.items():
        persist_env_setting(root, key, "true" if value else "false")

    config.enable_summary = summary
    config.enable_note = note
    config.enable_kanban = kanban
    config.enable_wiki = wiki

    logger.info("Etapas do pipeline atualizadas: %s", config.steps())
    return {"ok": True, "steps": config.steps(), "watcher_restart_needed": True}


def set_watch_dir(config: Settings, watch_dir: str) -> dict:
    """Altera a pasta monitorada (OBS) em runtime e persiste no ``.env``.

    O caminho não precisa existir ainda (a pasta pode ser criada depois);
    nesse caso devolvemos ``exists: False`` para a interface avisar.
    """
    watch_dir = (watch_dir or "").strip()
    if not watch_dir:
        return {"ok": False, "error": "Informe um caminho para a pasta monitorada."}

    resolved = str(Path(watch_dir).expanduser())
    previous = config.watch_dir

    persist_env_setting(Path(config.project_root), "MEETING_WATCH_DIR", resolved)
    config.watch_dir = resolved

    logger.info("Pasta monitorada alterada: %s -> %s", previous, resolved)
    return {
        "ok": True,
        "previous": previous,
        "current": resolved,
        "exists": Path(resolved).is_dir(),
        # O watcher subprocess lê a env só ao iniciar.
        "watcher_restart_needed": True,
    }
