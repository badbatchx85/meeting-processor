"""Dashboard de acompanhamento em tempo real no Obsidian."""

import json
import logging
import threading
from datetime import datetime
from pathlib import Path

from .config import Settings

logger = logging.getLogger(__name__)

STAGES = [
    ("audio", "Extraindo audio"),
    ("transcription", "Transcrevendo com Whisper"),
    ("summary", "Gerando resumo com LLM"),
    ("note", "Criando nota da reuniao"),
    ("kanban", "Criando quadro Kanban"),
    ("wiki", "Integrando com wiki"),
]


class ProcessingJob:
    """Representa o estado de um job de processamento."""

    def __init__(self, source_file: str, started_at: datetime | None = None):
        self.source_file = source_file
        self.started_at = started_at or datetime.now()
        self.current_stage: int = -1
        self.total_stages: int = len(STAGES)
        self.status: str = "waiting"
        self.error_message: str = ""
        self.details: dict[str, str] = {}
        self.stage_progress: dict[str, int] = {}  # stage_key -> 0-100
        self.skipped: set[str] = set()
        self.completed_at: datetime | None = None

    def skip(self, stage_key: str, detail: str = "desativada") -> None:
        """Marca uma etapa como pulada (desligada na configuração)."""
        self.skipped.add(stage_key)
        if detail:
            self.details[stage_key] = detail

    def advance(self, stage_key: str, detail: str = "") -> None:
        for i, (key, _) in enumerate(STAGES):
            if key == stage_key:
                self.current_stage = i
                break
        self.status = "processing"
        self.stage_progress[stage_key] = 0
        if detail:
            self.details[stage_key] = detail

    def set_progress(self, stage_key: str, pct: int, detail: str = "") -> None:
        """Atualiza a porcentagem de progresso de uma etapa (0-100)."""
        self.stage_progress[stage_key] = min(pct, 100)
        if detail:
            self.details[stage_key] = detail

    def complete(self, detail: str = "") -> None:
        self.status = "completed"
        self.current_stage = self.total_stages
        self.completed_at = datetime.now()
        if detail:
            self.details["result"] = detail

    def fail(self, error: str) -> None:
        self.status = "error"
        self.error_message = error
        self.completed_at = datetime.now()


class Dashboard:
    """Dashboard de acompanhamento em tempo real no Obsidian."""

    def __init__(self, config: Settings):
        self.config = config
        self.dashboard_path = config.vault_path / "wiki" / "reunioes" / "Dashboard.md"
        self.history_path = config.vault_path / "wiki" / ".processing-history.json"
        self.heartbeat_path = config.vault_path / "wiki" / ".watcher-heartbeat"
        self.jobs: list[ProcessingJob] = []
        self._lock = threading.Lock()

        # Estado do watcher
        self.watcher_running = False
        self.watcher_started_at: datetime | None = None
        self.files_detected: int = 0
        self.pending_files: list[str] = []

        self._load_history()

    # --- Controle do Watcher ---

    def set_watcher_status(self, running: bool) -> None:
        """Atualiza status do watcher e renderiza."""
        self.watcher_running = running
        if running:
            self.watcher_started_at = datetime.now()
            self._write_heartbeat()
        else:
            self.heartbeat_path.unlink(missing_ok=True)
        self._render()

    def _write_heartbeat(self) -> None:
        """Escreve timestamp de heartbeat para detectar se o watcher morreu."""
        self.heartbeat_path.write_text(
            datetime.now().isoformat(), encoding="utf-8"
        )

    def _is_watcher_alive(self) -> bool:
        """Verifica se o watcher está vivo pelo heartbeat (max 10s de atraso)."""
        if not self.heartbeat_path.exists():
            return False
        try:
            ts = datetime.fromisoformat(
                self.heartbeat_path.read_text(encoding="utf-8").strip()
            )
            return (datetime.now() - ts).total_seconds() < 10
        except (ValueError, OSError):
            return False

    def file_detected(self, filename: str) -> None:
        """Registra que um arquivo foi detectado pelo watcher."""
        self.files_detected += 1
        if filename not in self.pending_files:
            self.pending_files.append(filename)
        self._render()

    def file_stabilized(self, filename: str) -> None:
        """Registra que um arquivo estabilizou e vai ser processado."""
        if filename in self.pending_files:
            self.pending_files.remove(filename)
        self._render()

    def heartbeat(self) -> None:
        """Atualiza o dashboard com timestamp atual (chamado periodicamente)."""
        self._write_heartbeat()
        self._render()

    # --- Controle de Jobs ---

    def new_job(self, source_file: str, started_at: datetime | None = None) -> ProcessingJob:
        job = ProcessingJob(source_file, started_at=started_at)
        self.jobs.append(job)
        self._render()
        return job

    def update(self, job: ProcessingJob) -> None:
        self._render()

    # --- Persistencia ---

    def _load_history(self) -> None:
        if self.history_path.exists():
            try:
                data = json.loads(self.history_path.read_text(encoding="utf-8"))
                for entry in data[-20:]:
                    j = ProcessingJob(entry["file"])
                    j.status = entry.get("status", "completed")
                    j.started_at = datetime.fromisoformat(entry["started"])
                    if entry.get("completed"):
                        j.completed_at = datetime.fromisoformat(entry["completed"])
                    j.details = entry.get("details", {})
                    j.current_stage = entry.get("stage", len(STAGES))
                    j.error_message = entry.get("error_message", "") or ""
                    self.jobs.append(j)
            except (json.JSONDecodeError, KeyError):
                pass

    @staticmethod
    def _stage_label_at(idx: int) -> str:
        """Retorna o label da etapa onde o job estava (ou string vazia)."""
        if 0 <= idx < len(STAGES):
            return STAGES[idx][1]
        return ""

    def _save_history(self) -> None:
        entries = []
        for j in self.jobs[-20:]:
            entries.append({
                "file": j.source_file,
                "status": j.status,
                "started": j.started_at.isoformat(),
                "completed": j.completed_at.isoformat() if j.completed_at else None,
                "details": j.details,
                "stage": j.current_stage,
                "stage_progress": dict(j.stage_progress),
                "skipped": sorted(j.skipped),
                "error_message": j.error_message or None,
                "failed_stage": self._stage_label_at(j.current_stage)
                if j.status == "error"
                else None,
            })
        from .utils import write_json_atomic
        write_json_atomic(self.history_path, entries)

    # --- Renderizacao ---

    def _render(self) -> None:
        with self._lock:
            self._render_unsafe()

    def _render_unsafe(self) -> None:
        now = datetime.now()

        active = [j for j in self.jobs if j.status in ("waiting", "processing")]
        history = [j for j in self.jobs if j.status in ("completed", "error")]

        lines = [
            "---",
            "cssclasses: [meeting-dashboard]",
            "---",
            "",
            "# Meeting Processor",
            "",
            f"> [!info] Ultima atualizacao: {now.strftime('%H:%M:%S')}",
            "",
        ]

        # --- Watcher Status ---
        lines.append("## Watcher")
        lines.append("")

        if self.watcher_running and self._is_watcher_alive():
            uptime = ""
            if self.watcher_started_at:
                secs = (now - self.watcher_started_at).total_seconds()
                h, rem = divmod(int(secs), 3600)
                m, s = divmod(rem, 60)
                uptime = f"{h}h {m}m {s}s"

            lines.extend([
                "> [!success] ATIVO - Monitorando",
                f"> `{self.config.watch_dir}`",
                f"> Uptime: {uptime} | Detectados: {self.files_detected} | Processados: {len(history)}",
                f"> Heartbeat: {now.strftime('%H:%M:%S')} *(se parou de atualizar, o watcher caiu)*",
                "",
            ])

            if self.pending_files:
                lines.append("**Aguardando estabilizacao:**")
                for f in self.pending_files:
                    lines.append(f"- `{f}` (OBS ainda gravando...)")
                lines.append("")

        else:
            lines.extend([
                "> [!danger] OFFLINE",
                "> O watcher nao esta rodando.",
                "",
            ])

        # --- Pipeline Ativo ---
        lines.append("## Pipeline")
        lines.append("")

        if not active:
            lines.extend([
                "> [!tip] Aguardando",
                "> Nenhuma reuniao sendo processada.",
                "",
            ])
        else:
            for job in active:
                lines.extend(self._render_active_job(job, now))

        # --- Historico ---
        lines.append("## Historico")
        lines.append("")

        if not history:
            lines.append("Nenhum processamento concluido.")
            lines.append("")
        else:
            lines.append("| | Arquivo | Duracao | Resultado |")
            lines.append("|---|---------|---------|-----------|")
            for job in reversed(history[-10:]):
                lines.append(self._render_history_row(job))
            lines.append("")

        self.dashboard_path.parent.mkdir(parents=True, exist_ok=True)
        self.dashboard_path.write_text("\n".join(lines), encoding="utf-8")
        self._save_history()

    def _render_active_job(self, job: ProcessingJob, now: datetime) -> list[str]:
        elapsed = (now - job.started_at).total_seconds()
        m, s = divmod(int(elapsed), 60)
        elapsed_str = f"{m}m {s}s"
        progress_pct = int((job.current_stage + 1) / job.total_stages * 100) if job.current_stage >= 0 else 0

        bar = self._progress_bar(progress_pct)

        lines = [
            f"> [!warning] `{job.source_file}`",
            f"> {elapsed_str} decorridos",
            "",
            f"{bar}",
            "",
        ]

        for i, (key, label) in enumerate(STAGES):
            detail = job.details.get(key, "")
            stage_pct = job.stage_progress.get(key, 0)
            if key in job.skipped:
                lines.append(f"- [ ] ~~{label}~~ *(desativada)*")
            elif i < job.current_stage:
                suffix = f" *{detail}*" if detail else ""
                lines.append(f"- [x] ~~{label}~~ 100%{suffix}")
            elif i == job.current_stage:
                bar = self._mini_bar(stage_pct)
                suffix = f" — {detail}" if detail else ""
                lines.append(f"- [ ] **{label}** {bar}{suffix}")
            else:
                lines.append(f"- [ ] {label}")

        if job.error_message:
            lines.extend([
                "",
                f"> [!danger] Erro: {job.error_message}",
            ])

        lines.append("")
        return lines

    def _progress_bar(self, pct: int) -> str:
        filled = pct // 5
        empty = 20 - filled
        bar = "#" * filled + "-" * empty
        return f"`[{bar}]` **{pct}%**"

    def _mini_bar(self, pct: int) -> str:
        filled = pct // 10
        empty = 10 - filled
        bar = "#" * filled + "-" * empty
        return f"`[{bar}]` {pct}%"

    def _render_history_row(self, job: ProcessingJob) -> str:
        icon = "OK" if job.status == "completed" else "ERRO"

        elapsed = ""
        if job.completed_at:
            secs = (job.completed_at - job.started_at).total_seconds()
            m, s = divmod(int(secs), 60)
            elapsed = f"{m}m {s}s"

        detail = job.details.get("result", job.error_message or "")
        if len(detail) > 60:
            detail = detail[:57] + "..."

        return f"| {icon} | `{job.source_file}` | {elapsed} | {detail} |"
