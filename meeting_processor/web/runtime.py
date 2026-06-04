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


VALID_PROVIDERS = ("anthropic", "local")


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
