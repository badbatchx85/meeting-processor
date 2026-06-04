"""Orquestrador do pipeline de processamento de reuniões."""

import logging
import time
from datetime import datetime
from pathlib import Path

from .audio import extract_audio, get_duration
from .config import Settings
from .dashboard import Dashboard
from .kanban import KanbanManager
from .models import MeetingSummary, ProcessingResult, Transcript
from .note_generator import NoteGenerator
from .summarizer import MeetingSummarizer
from .transcriber import WhisperTranscriber
from .wiki_integrator import WikiIntegrator

logger = logging.getLogger(__name__)


class MeetingPipeline:
    """Coordena todas as etapas do processamento de uma reunião gravada."""

    def __init__(self, config: Settings):
        self.config = config
        self.transcriber = WhisperTranscriber(config)
        self.summarizer = MeetingSummarizer(config)
        self.note_generator = NoteGenerator(config)
        self.kanban = KanbanManager(config)
        self.wiki = WikiIntegrator(config)
        self.dashboard = Dashboard(config)

    def process(self, video_path: Path) -> ProcessingResult:
        """Processa um arquivo de vídeo de reunião completo.

        Atualiza o dashboard no Obsidian a cada etapa para
        acompanhamento em tempo real.

        Args:
            video_path: Caminho do arquivo de vídeo.

        Returns:
            ProcessingResult com todos os caminhos e dados gerados.
        """
        start_time = time.time()
        logger.info("=" * 60)
        logger.info("Processando reuniao: %s", video_path.name)
        logger.info("=" * 60)

        created_at = datetime.now()
        job = self.dashboard.new_job(video_path.name)

        # Etapa 1: Extrair áudio
        logger.info("[1/6] Extraindo audio...")
        job.advance("audio", "Convertendo video para WAV 16kHz")
        job.set_progress("audio", 10)
        self.dashboard.update(job)
        audio_path = extract_audio(video_path, self.config)
        size_mb = audio_path.stat().st_size / 1_048_576
        job.set_progress("audio", 100, f"{size_mb:.1f} MB extraidos")
        self.dashboard.update(job)

        try:
            # Etapa 2: Transcrever
            logger.info("[2/6] Transcrevendo audio com Whisper...")
            job.advance("transcription", f"Modelo: {self.config.whisper_model}")
            job.set_progress("transcription", 5, "Carregando modelo...")
            self.dashboard.update(job)
            transcript = self.transcriber.transcribe(audio_path, progress_callback=self._make_progress_cb(job))
            duration_str = self._format_duration(transcript.duration)
            job.set_progress("transcription", 100, f"{len(transcript.segments)} segmentos, {duration_str}")
            self.dashboard.update(job)

            # Etapa 3: Resumir
            provider_label, model_label = self._llm_labels()
            logger.info("[3/6] Gerando resumo com %s...", provider_label)
            job.advance("summary", f"{provider_label}: {model_label}")
            job.set_progress("summary", 10, f"Enviando ao {provider_label}...")
            self.dashboard.update(job)
            summary = self.summarizer.summarize(transcript, video_path.name)
            job.set_progress("summary", 100, f"{len(summary.action_items)} tarefas, {len(summary.participants)} participantes")
            self.dashboard.update(job)

            # Etapa 4: Gerar nota
            logger.info("[4/6] Gerando nota de reuniao no Obsidian...")
            job.advance("note", "Gerando markdown")
            job.set_progress("note", 30)
            self.dashboard.update(job)
            meeting_dir, note_path, raw_path = self.note_generator.generate(
                transcript=transcript,
                summary=summary,
                source_file=video_path.name,
                created_at=created_at,
            )
            title = f"Reuniao {created_at.strftime('%Y-%m-%d %Hh%M')}"
            date_str = created_at.strftime("%Y-%m-%d")
            job.set_progress("note", 100, f"{meeting_dir.name}/")
            self.dashboard.update(job)

            # Etapa 5: Criar Kanban da reunião
            logger.info("[5/6] Criando quadro Kanban da reuniao...")
            job.advance("kanban", f"{len(summary.action_items)} tarefas")
            job.set_progress("kanban", 30)
            self.dashboard.update(job)
            try:
                self.kanban.create_board(
                    meeting_dir=meeting_dir,
                    tasks=summary.action_items,
                    meeting_title=title,
                )
                job.set_progress("kanban", 100, f"{len(summary.action_items)} tarefas criadas")
            except Exception as e:
                logger.warning("Falha ao criar Kanban (nao critico): %s", e)
                job.set_progress("kanban", 100, f"Falha: {e}")
            self.dashboard.update(job)

            # Etapa 6: Integrar com wiki
            logger.info("[6/6] Integrando com wiki claude-obsidian...")
            duration = self._format_duration(transcript.duration)
            job.advance("wiki", "Atualizando index, log e hot cache")
            job.set_progress("wiki", 20)
            self.dashboard.update(job)
            try:
                self.wiki.register_meeting(
                    title=title,
                    date_str=date_str,
                    source_file=video_path.name,
                    duration=duration,
                    task_count=len(summary.action_items),
                    key_topics=summary.key_topics,
                )
                job.set_progress("wiki", 100, "index, log e hot cache atualizados")
            except Exception as e:
                logger.warning("Falha ao integrar com wiki (nao critico): %s", e)
                job.set_progress("wiki", 100, f"Falha: {e}")

            elapsed = time.time() - start_time
            job.complete(
                f"{len(summary.action_items)} tarefas | "
                f"{len(summary.participants)} participantes | "
                f"{elapsed:.0f}s"
            )
            self.dashboard.update(job)

            logger.info("=" * 60)
            logger.info("Processamento concluido em %.1f segundos!", elapsed)
            logger.info("  Nota: %s", note_path)
            logger.info("  Transcricao: %s", raw_path)
            logger.info("  Tarefas: %d", len(summary.action_items))
            logger.info("=" * 60)

            return ProcessingResult(
                source_file=str(video_path),
                transcript=transcript,
                summary=summary,
                note_path=str(note_path),
                raw_path=str(raw_path),
                processing_time=elapsed,
            )

        except Exception as e:
            job.fail(str(e))
            self.dashboard.update(job)
            raise

        finally:
            # Limpar arquivo temporário de áudio
            if self.config.cleanup_temp and audio_path.exists():
                audio_path.unlink()
                logger.debug("Arquivo temporario removido: %s", audio_path)

    def _llm_labels(self) -> tuple[str, str]:
        """Retorna (label do provedor, label do modelo) para logs/dashboard."""
        provider = (self.config.llm_provider or "anthropic").lower()
        if provider in ("local", "ollama"):
            return ("Ollama (local)", self.config.ollama_model)
        return ("Claude API", self.config.anthropic_model)

    def _make_progress_cb(self, job):
        """Cria callback para atualizar progresso da transcrição no dashboard."""
        def cb(pct: int, detail: str = ""):
            job.set_progress("transcription", pct, detail)
            self.dashboard.update(job)
        return cb

    @staticmethod
    def _format_duration(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
