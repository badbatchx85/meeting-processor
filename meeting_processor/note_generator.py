"""Gerador de notas de reunião para Obsidian."""

import logging
import re
from datetime import datetime
from pathlib import Path

from .config import Settings
from .models import MeetingSummary, Transcript
from .utils import format_duration, format_timestamp

logger = logging.getLogger(__name__)


class NoteGenerator:
    """Gera notas de reunião no formato Obsidian compatível com claude-obsidian."""

    def __init__(self, config: Settings):
        self.config = config

    def generate(
        self,
        transcript: Transcript,
        summary: MeetingSummary,
        source_file: str,
        created_at: datetime | None = None,
    ) -> tuple[Path, Path, Path]:
        """Gera pasta da reunião com nota principal e transcrição bruta.

        Estrutura criada:
            reunioes/<nome>/
                <nome>.md    <- nota principal (aparece no grafo)
                Tarefas.md   <- kanban (criado pelo pipeline)

        Quando o usuario renomear a pasta no Obsidian, basta
        renomear o .md junto e o grafo atualiza automaticamente.

        Returns:
            Tupla com (caminho da pasta, caminho da nota, caminho da transcrição).
        """
        if created_at is None:
            created_at = datetime.now()

        date_str = created_at.strftime("%Y-%m-%d")
        time_str = created_at.strftime("%Hh%M")
        video_name = Path(source_file).stem
        folder_name = f"{date_str} {time_str} - {video_name}"

        # Criar pasta da reunião
        meeting_dir = self.config.reunioes_path / folder_name
        meeting_dir.mkdir(parents=True, exist_ok=True)

        # Nomes dos arquivos: tipo - nome da pasta
        resumo_name = f"Resumo - {folder_name}"
        tarefas_name = f"Tarefas - {folder_name}"
        transcricao_name = f"Transcricao - {folder_name}"

        # Salvar transcrição
        raw_path = meeting_dir / f"{transcricao_name}.md"
        self._write_raw_transcription(transcript, raw_path)

        # Nota de resumo
        note_content = self._build_note(
            title=folder_name,
            summary=summary,
            transcript=transcript,
            source_file=source_file,
            date_str=date_str,
            created_at=created_at,
            tarefas_link=tarefas_name,
            transcricao_link=transcricao_name,
        )

        note_path = meeting_dir / f"{resumo_name}.md"
        note_path.write_text(note_content, encoding="utf-8")

        # Nota grupo: nome da pasta, aparece no grafo como nó central
        group_path = meeting_dir / f"{folder_name}.md"
        group_path.write_text(
            f"# {folder_name}\n\n"
            f"- [[{resumo_name}|Resumo]]\n"
            f"- [[{tarefas_name}|Tarefas]]\n"
            f"- [[{transcricao_name}|Transcricao]]\n",
            encoding="utf-8",
        )

        logger.info("Nota de reuniao criada: %s", note_path)
        logger.info("Transcricao bruta salva: %s", raw_path)

        return meeting_dir, note_path, raw_path

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

        frontmatter = f"""\
---
type: source
source_type: meeting-transcription
title: "{title}"
created: {date_str}
updated: {date_str}
tags: {tags_yaml}
status: {self.config.note_status}
related: []
sources:
  - "[[{transcricao_link}|Transcricao]]"
participants: {participants_yaml}
source_file: "{source_file}"
duration: "{duration}"
---"""

        body_parts = [
            frontmatter,
            f"\n# {title}\n",
        ]

        # Info rápida + link para Tarefas
        participants_str = ", ".join(summary.participants) if summary.participants else "N/A"
        topics_str = ", ".join(summary.key_topics) if summary.key_topics else "N/A"
        body_parts.extend([
            f"**Participantes:** {participants_str}  ",
            f"**Topicos:** {topics_str}  ",
            f"**Tarefas:** {len(summary.action_items)} - [[{tarefas_link}|Tarefas]]",
            "",
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
            body_parts.append("> Veja as tarefas no formato Kanban: [[{tarefas_link}|Tarefas]]")
        else:
            body_parts.append("Nenhuma tarefa identificada nesta reuniao.")
        body_parts.append("")

        # Link para transcrição
        body_parts.append("## Transcricao Completa\n")
        body_parts.append("> [!info] Transcricao original")
        body_parts.append("> [[{transcricao_link}|Transcricao]]")
        body_parts.append("")

        return "\n".join(body_parts)

    def _write_raw_transcription(self, transcript: Transcript, path: Path, folder_name: str = "") -> None:
        lines = [
            "# Transcricao",
            "",
        ]
        for seg in transcript.segments:
            timestamp = format_timestamp(seg.start)
            lines.append(f"**[{timestamp}]** {seg.text}  ")
        path.write_text("\n".join(lines), encoding="utf-8")

    @staticmethod
    def _format_yaml_list(items: list[str]) -> str:
        if not items:
            return "[]"
        return "[" + ", ".join(f'"{item}"' for item in items) + "]"
