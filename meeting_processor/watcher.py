"""Monitoramento de pasta para novas gravações do OBS."""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .config import Settings
from .pipeline import MeetingPipeline

logger = logging.getLogger(__name__)


class RecordingHandler(FileSystemEventHandler):
    """Detecta novas gravações e dispara o processamento."""

    def __init__(self, pipeline: MeetingPipeline, config: Settings):
        super().__init__()
        self.pipeline = pipeline
        self.config = config
        self.extensions = set(config.watch_extensions)
        self._pending: dict[str, float] = {}
        self._processing: set[str] = set()
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._processed_dir = Path(config.project_root) / ".processed"
        self._processed_dir.mkdir(exist_ok=True)

    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() in self.extensions:
            logger.info("Novo arquivo detectado: %s", path.name)
            self.pipeline.dashboard.file_detected(path.name)
            self._schedule_stability_check(path)

    def on_modified(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() in self.extensions and str(path) in self._pending:
            try:
                self._pending[str(path)] = path.stat().st_size
            except OSError:
                pass

    def _schedule_stability_check(self, path: Path) -> None:
        path_str = str(path)

        if path_str in self._processing:
            return

        if self._is_already_processed(path):
            logger.debug("Arquivo ja processado: %s", path.name)
            return

        try:
            self._pending[path_str] = path.stat().st_size
        except OSError:
            return

        thread = threading.Thread(
            target=self._check_stable,
            args=(path,),
            daemon=True,
        )
        thread.start()

    def _check_stable(self, path: Path) -> None:
        path_str = str(path)
        stable_seconds = self.config.file_stable_seconds

        while True:
            time.sleep(stable_seconds)

            try:
                current_size = path.stat().st_size
            except OSError:
                self._pending.pop(path_str, None)
                return

            last_size = self._pending.get(path_str, -1)

            if current_size == last_size and current_size > 0:
                self._pending.pop(path_str, None)
                self.pipeline.dashboard.file_stabilized(path.name)
                self._submit_processing(path)
                return

            self._pending[path_str] = current_size

    def _submit_processing(self, path: Path) -> None:
        path_str = str(path)

        if path_str in self._processing:
            return

        self._processing.add(path_str)
        logger.info("Arquivo estavel. Iniciando processamento: %s", path.name)

        def _process():
            try:
                self.pipeline.process(path)
                self._mark_processed(path)
            except Exception:
                logger.exception("Erro ao processar %s", path.name)
            finally:
                self._processing.discard(path_str)

        self._executor.submit(_process)

    def _is_already_processed(self, path: Path) -> bool:
        marker = self._processed_dir / f"{path.name}.done"
        return marker.exists()

    def _mark_processed(self, path: Path) -> None:
        marker = self._processed_dir / f"{path.name}.done"
        marker.write_text(
            f"processed_at={time.strftime('%Y-%m-%d %H:%M:%S')}",
            encoding="utf-8",
        )


def _heartbeat_loop(dashboard, interval: int = 3) -> None:
    """Atualiza o dashboard periodicamente para mostrar que o watcher esta vivo."""
    while True:
        time.sleep(interval)
        try:
            dashboard.heartbeat()
        except Exception:
            logger.debug("Falha no heartbeat do dashboard", exc_info=True)


def start_watching(config: Settings) -> None:
    """Inicia o monitoramento da pasta de gravações do OBS."""
    pipeline = MeetingPipeline(config)
    handler = RecordingHandler(pipeline, config)
    observer = Observer()

    watch_path = str(config.watch_path)
    observer.schedule(handler, watch_path, recursive=False)
    observer.start()

    # Ativar dashboard
    pipeline.dashboard.set_watcher_status(True)

    # Heartbeat: atualiza o dashboard a cada 30s
    heartbeat_thread = threading.Thread(
        target=_heartbeat_loop,
        args=(pipeline.dashboard,),
        daemon=True,
    )
    heartbeat_thread.start()

    logger.info("Monitorando pasta: %s", watch_path)
    logger.info("Extensoes: %s", ", ".join(config.watch_extensions))
    logger.info("Dashboard ativo em: wiki/reunioes/Dashboard.md")
    logger.info("Pressione Ctrl+C para parar.")

    try:
        while observer.is_alive():
            observer.join(timeout=1)
    except KeyboardInterrupt:
        logger.info("Parando monitoramento...")
    finally:
        pipeline.dashboard.set_watcher_status(False)
        observer.stop()
        observer.join()
        logger.info("Monitoramento encerrado.")
