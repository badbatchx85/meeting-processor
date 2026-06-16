"""Orquestrador do pipeline de processamento de reuniões."""

import logging
import re
import shutil
import time
from datetime import datetime
from pathlib import Path

from .audio import extract_audio, get_duration
from .config import Settings
from . import generation_log
from .dashboard import Dashboard
from .job_control import JobCancelled
from .kanban import KanbanManager
from .models import MeetingSummary, ProcessingResult, Transcript
from .note_generator import NoteGenerator
from .summarizer import MeetingSummarizer
from .transcriber import WhisperTranscriber, select_whisper_model
from .utils import format_duration
from .wiki_integrator import WikiIntegrator

logger = logging.getLogger(__name__)

_FOLDER_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}h\d{2} - (.+)$")


def locate_source_file(config: Settings, meeting_dir: Path) -> Path | None:
    """Encontra o arquivo de mídia que originou a transcrição da reunião.

    O nome da pasta é ``"<data> <hora> - <stem-do-arquivo>"`` e o stem é sempre
    igual ao do arquivo original (``NoteGenerator.prepare`` usa ``Path(src).stem``).
    Procura em ``uploads/`` e no ``watch_dir`` por um arquivo com esse stem e uma
    extensão suportada. Devolve o primeiro encontrado ou ``None``.
    """
    m = _FOLDER_PREFIX_RE.match(meeting_dir.name)
    stem = m.group(1) if m else meeting_dir.name
    exts = {e.lower() for e in config.watch_extensions}
    roots = [Path(config.project_root) / "uploads", config.watch_path]
    for root in roots:
        try:
            if not root.is_dir():
                continue
            for entry in root.iterdir():
                if (
                    entry.is_file()
                    and entry.stem == stem
                    and (not exts or entry.suffix.lower() in exts)
                ):
                    return entry
        except OSError:
            continue
    return None


class MeetingPipeline:
    """Coordena todas as etapas do processamento de uma reunião gravada."""

    def __init__(self, config: Settings):
        self.config = config
        self.transcriber = WhisperTranscriber(config)
        # O summarizer é criado sob demanda (lazy): no modo só transcrição
        # ou com llm_provider="none" nenhuma LLM é instanciada.
        self.summarizer = None
        self.note_generator = NoteGenerator(config)
        self.kanban = KanbanManager(config)
        self.wiki = WikiIntegrator(config)
        self.dashboard = Dashboard(config)
        self._cancel_event = None

    def _effective_whisper_model(self, audio_path: Path) -> str:
        """Modelo Whisper para esta transcrição: fixo, ou adaptativo pela duração."""
        if not self.config.whisper_adaptive:
            return self.config.whisper_model
        duration_s = get_duration(audio_path)
        chosen = select_whisper_model(duration_s, self.config.whisper_model)
        if chosen != self.config.whisper_model:
            logger.info(
                "Adaptativo: áudio %s → Whisper '%s' (configurado '%s').",
                format_duration(duration_s),
                chosen,
                self.config.whisper_model,
            )
        return chosen

    def _check_cancel(self) -> None:
        if self._cancel_event is not None and self._cancel_event.is_set():
            raise JobCancelled("Cancelado pelo usuário.")

    def process(self, video_path: Path, transcript_only: bool = False,
                job_started=None, cancel_event=None) -> ProcessingResult:
        """Processa um arquivo de vídeo de reunião completo.

        Atualiza o dashboard no Obsidian a cada etapa para
        acompanhamento em tempo real.

        Args:
            video_path: Caminho do arquivo de vídeo.

        Returns:
            ProcessingResult com todos os caminhos e dados gerados.
        """
        self._cancel_event = cancel_event
        start_time = time.time()
        steps = self.config.steps()
        if transcript_only:
            steps = {"summary": False, "note": False, "kanban": False, "wiki": False}
        mode = "completa" if steps["summary"] else "so transcricao"
        logger.info("=" * 60)
        logger.info("Processando reuniao (%s): %s", mode, video_path.name)
        logger.info("=" * 60)

        created_at = datetime.now()
        job = self.dashboard.new_job(video_path.name, started_at=job_started)
        for key in ("summary", "note", "kanban", "wiki"):
            if not steps[key]:
                job.skip(key)

        # ``audio_path`` precisa existir para o ``finally``: a extração roda
        # dentro do try para que qualquer falha aqui marque o job como erro
        # (do contrário ele ficaria preso em "processando").
        audio_path: Path | None = None
        try:
            # Pré-checagem de disco: falha rápida e legível em vez de OSError no meio.
            check_dir = self.config.temp_dir if Path(self.config.temp_dir).is_dir() else self.config.project_root
            free = shutil.disk_usage(check_dir).free
            need = video_path.stat().st_size * 3
            if free < need:
                raise RuntimeError(
                    f"Espaço em disco insuficiente: ~{need / 1e9:.1f} GB necessários, "
                    f"{free / 1e9:.1f} GB livres."
                )

            # Etapa 1: Extrair áudio (sempre)
            logger.info("[1] Extraindo audio...")
            job.advance("audio", "Convertendo video para WAV 16kHz")
            job.set_progress("audio", 10)
            self.dashboard.update(job)
            audio_path = extract_audio(video_path, self.config)
            self._check_cancel()
            size_mb = audio_path.stat().st_size / 1_048_576
            job.set_progress("audio", 100, f"{size_mb:.1f} MB extraidos")
            self.dashboard.update(job)
            self._check_cancel()

            diar = self._start_diarization(audio_path)

            # Etapa 2: Transcrever (sempre)
            logger.info("[2] Transcrevendo audio com Whisper...")
            whisper_model = self._effective_whisper_model(audio_path)
            job.advance("transcription", f"Modelo: {whisper_model}")
            job.set_progress("transcription", 5, "Carregando modelo...")
            self.dashboard.update(job)
            transcript = self.transcriber.transcribe(
                audio_path, progress_callback=self._make_progress_cb(job), model=whisper_model
            )
            duration_str = format_duration(transcript.duration)
            job.set_progress("transcription", 100, f"{len(transcript.segments)} segmentos, {duration_str}")
            self.dashboard.update(job)
            self._check_cancel()

            self._finish_diarization(diar, transcript)

            # Salvar transcrição no vault (sempre)
            paths = self.note_generator.prepare(video_path.name, created_at)
            self.note_generator.write_transcription(transcript, paths)

            # Etapas 3-6: resumo/nota/kanban/wiki (opcionais) — caminho único.
            summary = self._summarize(
                transcript, paths, video_path.name, created_at, job, steps
            )
            self._check_cancel()
            note_path = (
                str(paths.note_path) if summary is not None and steps["note"] else ""
            )

            elapsed = time.time() - start_time
            if summary is not None:
                job.complete(
                    f"{len(summary.action_items)} tarefas | "
                    f"{len(summary.participants)} participantes | "
                    f"{elapsed:.0f}s"
                )
            else:
                job.complete(
                    f"So transcricao | {len(transcript.segments)} segmentos | "
                    f"{elapsed:.0f}s"
                )
            self.dashboard.update(job)

            logger.info("=" * 60)
            logger.info("Processamento concluido em %.1f segundos!", elapsed)
            logger.info("  Transcricao: %s", paths.raw_path)
            if note_path:
                logger.info("  Nota: %s", note_path)
            if summary is not None:
                logger.info("  Tarefas: %d", len(summary.action_items))
            logger.info("=" * 60)

            return ProcessingResult(
                source_file=str(video_path),
                transcript=transcript,
                summary=summary,
                note_path=note_path,
                raw_path=str(paths.raw_path),
                processing_time=elapsed,
            )

        except Exception as e:
            job.fail(str(e))
            self.dashboard.update(job)
            raise

        finally:
            # Limpar arquivo temporário de áudio (pode não existir se a extração falhou)
            if self.config.cleanup_temp and audio_path is not None and audio_path.exists():
                audio_path.unlink()
                logger.debug("Arquivo temporario removido: %s", audio_path)

    def _start_diarization(self, audio_path):
        """Submete a diarização a uma thread (roda junto com a transcrição)."""
        if not self.config.enable_diarization:
            return None
        try:
            from concurrent.futures import ThreadPoolExecutor
            from .diarizer import diarize
            ex = ThreadPoolExecutor(max_workers=1)
            return (ex, ex.submit(diarize, audio_path, self.config))
        except Exception as e:  # noqa: BLE001
            logger.warning("Falha ao iniciar diarizacao (nao critico): %s", e)
            return None

    def _finish_diarization(self, handle, transcript):
        """Junta os turnos e atribui falantes. Nunca derruba o pipeline."""
        if handle is None:
            return
        ex, fut = handle
        try:
            from .diarizer import assign_speakers
            turns = fut.result()
            assign_speakers(transcript.segments, turns)
            logger.info("Diarizacao: %d turnos.", len(turns))
        except Exception as e:  # noqa: BLE001
            logger.warning("Falha na diarizacao (nao critico): %s", e)
        finally:
            ex.shutdown(wait=False)

    def _summarize(self, transcript, paths, source_file, created_at, job, steps, style=None):
        """Etapas 3-6 (resumo/nota/kanban/wiki) sobre um transcript + pasta.

        Caminho único usado pelo processamento normal e pelo re-resumo de uma
        reunião já transcrita. Retorna o ``MeetingSummary`` ou ``None`` quando o
        resumo está desligado.
        """
        title = f"Reuniao {created_at.strftime('%Y-%m-%d %Hh%M')}"
        date_str = created_at.strftime("%Y-%m-%d")
        summary: MeetingSummary | None = None

        # Etapa 3: Resumir (opcional)
        if steps["summary"]:
            # Provedor local: garante o Ollama no ar antes de falar com ele.
            if (self.config.llm_provider or "").lower() in ("local", "ollama"):
                from .ollama_service import ensure_running

                ensure_running(self.config)
            provider_label, model_label = self._llm_labels()
            logger.info("[3] Gerando resumo com %s...", provider_label)
            job.advance("summary", f"{provider_label}: {model_label}")
            job.set_progress("summary", 10, f"Enviando ao {provider_label}...")
            self.dashboard.update(job)
            if self.summarizer is None:
                self.summarizer = MeetingSummarizer(self.config)
            summary = self.summarizer.summarize(transcript, source_file, style=style)
            job.set_progress("summary", 100, f"{len(summary.action_items)} tarefas, {len(summary.participants)} participantes")
            self.dashboard.update(job)

            # Etapa 4: Gerar nota de resumo (opcional)
            if steps["note"]:
                logger.info("[4] Gerando nota de reuniao no Obsidian...")
                job.advance("note", "Gerando markdown")
                job.set_progress("note", 30)
                self.dashboard.update(job)
                self.note_generator.write_summary_note(
                    transcript, summary, source_file, created_at, paths
                )
                job.set_progress("note", 100, f"{paths.meeting_dir.name}/")
                self.dashboard.update(job)

            # Etapa 5: Criar Kanban da reunião (opcional)
            if steps["kanban"]:
                logger.info("[5] Criando quadro Kanban da reuniao...")
                job.advance("kanban", f"{len(summary.action_items)} tarefas")
                job.set_progress("kanban", 30)
                self.dashboard.update(job)
                try:
                    self.kanban.create_board(
                        meeting_dir=paths.meeting_dir,
                        tasks=summary.action_items,
                        meeting_title=title,
                    )
                    job.set_progress("kanban", 100, f"{len(summary.action_items)} tarefas criadas")
                except Exception as e:
                    logger.warning("Falha ao criar Kanban (nao critico): %s", e)
                    job.set_progress("kanban", 100, f"Falha: {e}")
                self.dashboard.update(job)
                try:
                    from .person_rollup import regenerate_person_rollups
                    from .vault_dashboard import regenerate_dashboard
                    regenerate_person_rollups(self.config)
                    regenerate_dashboard(self.config)
                except Exception as e:  # noqa: BLE001 — rollup/dashboard não são críticos
                    logger.warning("Falha ao gerar rollup/dashboard (nao critico): %s", e)

            # Etapa 6: Integrar com wiki (opcional)
            if steps["wiki"]:
                logger.info("[6] Integrando com wiki claude-obsidian...")
                duration = format_duration(transcript.duration)
                job.advance("wiki", "Atualizando index, log e hot cache")
                job.set_progress("wiki", 20)
                self.dashboard.update(job)
                try:
                    self.wiki.register_meeting(
                        title=title,
                        date_str=date_str,
                        source_file=source_file,
                        duration=duration,
                        task_count=len(summary.action_items),
                        key_topics=summary.key_topics,
                    )
                    job.set_progress("wiki", 100, "index, log e hot cache atualizados")
                except Exception as e:
                    logger.warning("Falha ao integrar com wiki (nao critico): %s", e)
                    job.set_progress("wiki", 100, f"Falha: {e}")

        # Nó central do grafo (liga só ao que foi gerado)
        self.note_generator.write_group_note(paths, has_summary=steps["note"])
        return summary

    def summarize_existing(self, meeting_id: str, job_started=None, cancel_event=None, style=None) -> None:
        """Gera o resumo de uma reunião já transcrita (sem re-transcrever)."""
        self._cancel_event = cancel_event
        # Defesa contra path traversal: meeting_dir deve ser filho direto de
        # reunioes/ (sem ``..`` nem separadores em meeting_id).
        base = self.config.reunioes_path.resolve()
        meeting_dir = (base / meeting_id).resolve()
        if meeting_dir.parent != base:
            raise FileNotFoundError(f"Reunião inválida: {meeting_id}")
        transcricoes = list(meeting_dir.glob("Transcricao - *.md"))
        if not meeting_dir.is_dir() or not transcricoes:
            raise FileNotFoundError(
                f"Transcrição não encontrada para a reunião: {meeting_id}"
            )

        logger.info("Gerando resumo da reuniao existente: %s", meeting_id)
        transcript = self.note_generator.read_transcription(transcricoes[0])
        paths = self.note_generator.paths_for_existing(meeting_dir)
        created_at = datetime.now()

        # Áudio e transcrição já estão prontos: começa em "summary".
        steps = {
            "summary": True,
            "note": True,
            "kanban": self.config.enable_kanban,
            "wiki": self.config.enable_wiki,
        }
        job = self.dashboard.new_job(meeting_id, started_at=job_started)
        for key in ("audio", "transcription"):
            job.advance(key)
            job.set_progress(key, 100)
        started = datetime.now()
        try:
            self._check_cancel()
            self._summarize(transcript, paths, meeting_id, created_at, job, steps, style=style)
            job.complete("resumo gerado a partir da transcrição")
            self.dashboard.update(job)
            generation_log.append(
                meeting_dir, "summary", "ok",
                detail="resumo gerado a partir da transcrição",
                started=started, completed=datetime.now(),
            )
        except Exception as e:
            job.fail(str(e))
            self.dashboard.update(job)
            generation_log.append(
                meeting_dir, "summary", "error", error=str(e),
                started=started, completed=datetime.now(),
            )
            raise

    def transcribe_existing(self, meeting_id: str, job_started=None, cancel_event=None) -> None:
        """Re-transcreve uma reunião já existente (só transcrição, sem resumo).

        Localiza o arquivo de origem, roda áudio+Whisper, sobrescreve a
        transcrição salva e registra o resultado no log de geração da reunião.
        Se a origem sumiu, registra um erro no log e retorna (sem exceção).
        """
        self._cancel_event = cancel_event
        base = self.config.reunioes_path.resolve()
        meeting_dir = (base / meeting_id).resolve()
        if meeting_dir.parent != base or not meeting_dir.is_dir():
            raise FileNotFoundError(f"Reunião inválida: {meeting_id}")

        started = datetime.now()
        source = locate_source_file(self.config, meeting_dir)
        if source is None:
            generation_log.append(
                meeting_dir,
                "transcript",
                "error",
                error=f"Arquivo de origem não encontrado: {meeting_dir.name}",
                started=started,
                completed=datetime.now(),
            )
            logger.warning("Re-transcrição: origem não encontrada para %s", meeting_id)
            return

        logger.info("Re-transcrevendo %s (origem: %s)", meeting_id, source.name)
        job = self.dashboard.new_job(meeting_id, started_at=job_started)
        for key in ("summary", "note", "kanban", "wiki"):
            job.skip(key)
        job.advance("audio", "Convertendo video para WAV 16kHz")
        job.set_progress("audio", 10)
        self.dashboard.update(job)
        audio_path = extract_audio(source, self.config)
        try:
            job.set_progress("audio", 100)
            whisper_model = self._effective_whisper_model(audio_path)
            job.advance("transcription", f"Modelo: {whisper_model}")
            job.set_progress("transcription", 5, "Carregando modelo...")
            self.dashboard.update(job)
            transcript = self.transcriber.transcribe(
                audio_path, progress_callback=self._make_progress_cb(job), model=whisper_model
            )
            self._check_cancel()
            paths = self.note_generator.paths_for_existing(meeting_dir)
            self.note_generator.write_transcription(transcript, paths)
            detail = f"{len(transcript.segments)} segmentos, {format_duration(transcript.duration)}"
            job.complete(f"So transcricao | {detail}")
            self.dashboard.update(job)
            generation_log.append(
                meeting_dir, "transcript", "ok", detail=detail,
                started=started, completed=datetime.now(),
            )
        except Exception as e:
            job.fail(str(e))
            self.dashboard.update(job)
            generation_log.append(
                meeting_dir, "transcript", "error", error=str(e),
                started=started, completed=datetime.now(),
            )
            raise
        finally:
            if self.config.cleanup_temp and audio_path.exists():
                audio_path.unlink()

    def _llm_labels(self) -> tuple[str, str]:
        """Retorna (label do provedor, label do modelo) para logs/dashboard."""
        provider = (self.config.llm_provider or "anthropic").lower()
        if provider in ("local", "ollama"):
            return ("Ollama (local)", self.config.ollama_model)
        if provider == "openai":
            return ("OpenAI", self.config.openai_model)
        if provider == "gemini":
            return ("Gemini", self.config.gemini_model)
        return ("Claude API", self.config.anthropic_model)

    def _make_progress_cb(self, job):
        """Cria callback para atualizar progresso da transcrição no dashboard."""
        def cb(pct: int, detail: str = ""):
            job.set_progress("transcription", pct, detail)
            self.dashboard.update(job)
        return cb
