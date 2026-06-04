"""Servidor HTTP local para controlar o watcher via links do Obsidian."""

import logging
import os
import signal
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from .config import Settings

logger = logging.getLogger(__name__)

PORT = 45678
_watcher_process = None
_config = None


class ControlHandler(BaseHTTPRequestHandler):
    """Trata requisições de controle do watcher."""

    def do_GET(self):
        global _watcher_process

        if self.path == "/start":
            self._start_watcher()
            self._respond("Watcher iniciado.")
        elif self.path == "/stop":
            self._stop_watcher()
            self._respond("Watcher parado.")
        elif self.path == "/restart":
            self._stop_watcher()
            self._start_watcher()
            self._respond("Watcher reiniciado.")
        elif self.path == "/status":
            running = _watcher_process is not None and _watcher_process.poll() is None
            status = "ativo" if running else "offline"
            self._respond(f"Status: {status}")
        else:
            self._respond("Comandos: /start /stop /restart /status", 404)

    def _start_watcher(self):
        global _watcher_process
        if _watcher_process is not None and _watcher_process.poll() is None:
            return  # já rodando

        project_root = Path(__file__).parent.parent
        env = os.environ.copy()

        # Permite injetar um diretório extra no PATH (útil quando
        # ffmpeg foi instalado em local não-padrão).
        extra_path = os.environ.get("MEETING_EXTRA_PATH", "")
        if extra_path:
            env["PATH"] = extra_path + os.pathsep + env.get("PATH", "")

        _watcher_process = subprocess.Popen(
            [sys.executable, "-m", "meeting_processor", "watch"],
            cwd=str(project_root),
            env=env,
        )
        logger.info("Watcher iniciado (PID: %d)", _watcher_process.pid)

    def _stop_watcher(self):
        global _watcher_process
        if _watcher_process is not None and _watcher_process.poll() is None:
            _watcher_process.terminate()
            _watcher_process.wait(timeout=10)
            logger.info("Watcher parado.")
        _watcher_process = None

    def _respond(self, message: str, code: int = 200):
        html = f"""<html><body>
        <h2>{message}</h2>
        <p>Volte ao Obsidian.</p>
        <script>window.close()</script>
        </body></html>"""
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        logger.debug("Control server: %s", format % args)


def start_control_server(config: Settings) -> HTTPServer:
    """Inicia o servidor de controle em background."""
    global _config
    _config = config

    server = HTTPServer(("127.0.0.1", PORT), ControlHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Servidor de controle ativo em http://localhost:%d", PORT)
    return server
