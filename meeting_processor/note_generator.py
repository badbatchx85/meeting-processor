"""Gerador de notas de reunião para Obsidian."""

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import Settings
from .models import MeetingSummary, Transcript, TranscriptSegment
from .utils import format_duration, format_timestamp, parse_timestamp, write_json_atomic, yaml_quote

logger = logging.getLogger(__name__)


@dataclass
class MeetingPaths:
    """Caminhos e nomes dos arquivos de uma reunião no vault."""

    meeting_dir: Path
    folder_name: str
    resumo_name: str
    tarefas_name: str
    transcricao_name: str
    raw_path: Path     # Transcricao ...md (sempre)
    note_path: Path    # Resumo ...md (só quando há resumo)
    group_path: Path   # nó central no grafo


class NoteGenerator:
    """Gera notas de reunião no formato Obsidian compatível com claude-obsidian."""

    def __init__(self, config: Settings):
        self.config = config

    def prepare(
        self, source_file: str, created_at: datetime | None = None
    ) -> MeetingPaths:
        """Cria a pasta da reunião e resolve os nomes dos arquivos."""
        if created_at is None:
            created_at = datetime.now()

        date_str = created_at.strftime("%Y-%m-%d")
        time_str = created_at.strftime("%Hh%M")
        video_name = Path(source_file).stem
        folder_name = f"{date_str} {time_str} - {video_name}"

        meeting_dir = self.config.reunioes_path / folder_name
        meeting_dir.mkdir(parents=True, exist_ok=True)
        return self._paths_from_folder(meeting_dir)

    def paths_for_existing(self, meeting_dir: Path) -> MeetingPaths:
        """Resolve os caminhos de uma reunião já existente (sem criar pasta)."""
        return self._paths_from_folder(meeting_dir)

    @staticmethod
    def _paths_from_folder(meeting_dir: Path) -> MeetingPaths:
        """Monta os nomes/caminhos a partir do nome da pasta da reunião."""
        folder_name = meeting_dir.name
        resumo_name = f"Resumo - {folder_name}"
        tarefas_name = f"Tarefas - {folder_name}"
        transcricao_name = f"Transcricao - {folder_name}"
        return MeetingPaths(
            meeting_dir=meeting_dir,
            folder_name=folder_name,
            resumo_name=resumo_name,
            tarefas_name=tarefas_name,
            transcricao_name=transcricao_name,
            raw_path=meeting_dir / f"{transcricao_name}.md",
            note_path=meeting_dir / f"{resumo_name}.md",
            group_path=meeting_dir / f"{folder_name}.md",
        )

    def write_transcription(self, transcript: Transcript, paths: MeetingPaths) -> None:
        """Salva a transcrição bruta (sempre) + sidecar de palavras quando houver."""
        self._write_raw_transcription(transcript, paths.raw_path)
        logger.info("Transcricao bruta salva: %s", paths.raw_path)
        if any(s.words or s.speaker for s in transcript.segments):
            words_path = paths.raw_path.with_suffix(".words.json")
            write_json_atomic(words_path, [s.model_dump() for s in transcript.segments])
            logger.info("Timestamps por palavra salvos: %s", words_path)

    def read_transcription(self, path: Path) -> Transcript:
        """Reconstrói um ``Transcript`` a partir de ``Transcricao - *.md``.

        Inverso de :meth:`_write_raw_transcription`: cada linha
        ``**[MM:SS]** texto`` vira um segmento (o fim de um segmento é o início
        do próximo, ou o seu próprio início no último).
        """
        line_re = re.compile(r"^\*\*\[(.+?)\]\*\*\s*(.*?)\s*$")
        starts: list[float] = []
        texts: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            m = line_re.match(line.strip())
            if m and m.group(2):
                starts.append(parse_timestamp(m.group(1)))
                texts.append(m.group(2))

        segments: list[TranscriptSegment] = []
        for i, (start, text) in enumerate(zip(starts, texts)):
            end = starts[i + 1] if i + 1 < len(starts) else start
            segments.append(TranscriptSegment(start=start, end=end, text=text))

        duration = segments[-1].end if segments else 0.0
        return Transcript(
            segments=segments,
            full_text=" ".join(texts),
            language=self.config.whisper_language,
            duration=duration,
        )

    def write_summary_note(
        self,
        transcript: Transcript,
        summary: MeetingSummary,
        source_file: str,
        created_at: datetime,
        paths: MeetingPaths,
    ) -> None:
        """Salva a nota de resumo da reunião."""
        note_content = self._build_note(
            title=paths.folder_name,
            summary=summary,
            transcript=transcript,
            source_file=source_file,
            date_str=created_at.strftime("%Y-%m-%d"),
            created_at=created_at,
            tarefas_link=paths.tarefas_name,
            transcricao_link=paths.transcricao_name,
        )
        paths.note_path.write_text(note_content, encoding="utf-8")
        logger.info("Nota de reuniao criada: %s", paths.note_path)

    def write_group_note(self, paths: MeetingPaths, has_summary: bool) -> None:
        """Cria o nó central do grafo, ligando só ao que foi gerado."""
        lines = [f"# {paths.folder_name}", ""]
        if has_summary:
            lines.append(f"- [[{paths.resumo_name}|Resumo]]")
            lines.append(f"- [[{paths.tarefas_name}|Tarefas]]")
        lines.append(f"- [[{paths.transcricao_name}|Transcricao]]")
        paths.group_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def generate(
        self,
        transcript: Transcript,
        summary: MeetingSummary,
        source_file: str,
        created_at: datetime | None = None,
    ) -> tuple[Path, Path, Path]:
        """Gera a reunião completa (transcrição + resumo + grafo).

        Mantido por compatibilidade; o pipeline chama os passos
        individualmente conforme as etapas habilitadas.

        Returns:
            (pasta da reunião, nota de resumo, transcrição).
        """
        if created_at is None:
            created_at = datetime.now()
        paths = self.prepare(source_file, created_at)
        self.write_transcription(transcript, paths)
        self.write_summary_note(transcript, summary, source_file, created_at, paths)
        self.write_group_note(paths, has_summary=True)
        return paths.meeting_dir, paths.note_path, paths.raw_path

    def _build_note(
        self,
        title: str,
        summary: MeetingSummary,
        transcript: Transcript,
        source_file: str,
        date_str: str,
        created_at: datetime,
        tarefas_link: str = "Tarefas",
        transcricao_link: str = "Transcricao",
    ) -> str:
        """Constrói o conteúdo completo da nota Obsidian."""
        duration = format_duration(transcript.duration)
        participants_yaml = self._format_yaml_list(summary.participants)
        tags_yaml = self._format_yaml_list(self.config.default_tags)
        # Double-quoted scalars are escaped so embedded quotes stay valid YAML.
        title_q = yaml_quote(title)
        source_file_q = yaml_quote(source_file)
        meeting_type_q = yaml_quote(summary.meeting_type)
        purpose_q = yaml_quote(summary.purpose)

        frontmatter = f"""\
---
type: source
source_type: meeting-transcription
title: {title_q}
created: {date_str}
updated: {date_str}
tags: {tags_yaml}
status: {self.config.note_status}
related: []
sources:
  - "[[{transcricao_link}|Transcricao]]"
participants: {participants_yaml}
source_file: {source_file_q}
duration: "{duration}"
meeting_type: {meeting_type_q}
purpose: {purpose_q}
---"""

        body_parts = [
            frontmatter,
            f"\n# {title}\n",
        ]

        # Info rápida + link para Tarefas
        participants_str = ", ".join(summary.participants) if summary.participants else "N/A"
        topics_str = ", ".join(summary.key_topics) if summary.key_topics else "N/A"
        quick_info = []
        if summary.meeting_type:
            quick_info.append(f"**Tipo:** {summary.meeting_type}  ")
        quick_info.extend([
            f"**Participantes:** {participants_str}  ",
            f"**Topicos:** {topics_str}  ",
            f"**Tarefas:** {len(summary.action_items)} - [[{tarefas_link}|Tarefas]]",
            "",
        ])
        body_parts.extend(quick_info)

        if summary.purpose:
            body_parts.extend([
                "## Propósito\n",
                f"{summary.purpose}\n",
            ])

        # Resumo executivo
        body_parts.extend([
            "## Resumo Executivo\n",
            f"{summary.executive_summary}\n",
        ])

        # Resumo por período
        if summary.time_windows:
            body_parts.append("## Resumo por Periodo\n")
            for tw in summary.time_windows:
                start = f"{tw.start_minutes:02d}:00"
                end = f"{tw.end_minutes:02d}:00"
                body_parts.append(f"### {start} - {end}\n")
                body_parts.append(f"{tw.summary}\n")

        # Decisões
        if summary.decisions:
            body_parts.append("## Decisões\n")
            for dec in summary.decisions:
                body_parts.append(f"- {dec}")
            body_parts.append("")

        # Tarefas identificadas
        body_parts.append("## Tarefas Identificadas\n")
        if summary.action_items:
            for item in summary.action_items:
                task_line = f"- [ ] {item.description}"
                details = []
                if item.assignee:
                    details.append(f"Responsavel: {item.assignee}")
                if item.due_date:
                    details.append(f"Prazo: {item.due_date}")
                if item.priority:
                    details.append(f"Prioridade: {item.priority}")
                if details:
                    task_line += f" ({', '.join(details)})"
                body_parts.append(task_line)
            body_parts.append("")
            body_parts.append("> [!tip] Quadro visual")
            body_parts.append(f"> Veja as tarefas no formato Kanban: [[{tarefas_link}|Tarefas]]")
        else:
            body_parts.append("Nenhuma tarefa identificada nesta reuniao.")
        body_parts.append("")

        # Questões em aberto
        if summary.open_questions:
            body_parts.append("## Questões em Aberto\n")
            for q in summary.open_questions:
                body_parts.append(f"- {q}")
            body_parts.append("")

        # Link para transcrição
        body_parts.append("## Transcricao Completa\n")
        body_parts.append("> [!info] Transcricao original")
        body_parts.append(f"> [[{transcricao_link}|Transcricao]]")
        body_parts.append("")

        return "\n".join(body_parts)

    def _write_raw_transcription(self, transcript: Transcript, path: Path, folder_name: str = "") -> None:
        lines = [
            "# Transcricao",
            "",
        ]
        for seg in transcript.segments:
            timestamp = format_timestamp(seg.start)
            lines.append(f"**[{timestamp}]** {seg.display_text}  ")
        path.write_text("\n".join(lines), encoding="utf-8")

    @staticmethod
    def _format_yaml_list(items: list[str]) -> str:
        if not items:
            return "[]"
        return "[" + ", ".join(f'"{item}"' for item in items) + "]"
