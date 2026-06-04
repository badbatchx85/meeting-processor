"""Gerenciamento de quadros Kanban individuais por reunião no Obsidian."""

import logging
from pathlib import Path

from .config import Settings
from .models import ActionItem

logger = logging.getLogger(__name__)

EMPTY_BOARD = """\
---
kanban-plugin: basic
---

## A Fazer

## Em Progresso

## Concluido
"""


class KanbanManager:
    """Cria um quadro Kanban individual para cada reunião."""

    def __init__(self, config: Settings):
        self.config = config

    def create_board(
        self,
        meeting_dir: Path,
        tasks: list[ActionItem],
        meeting_title: str,
    ) -> Path:
        """Cria o quadro Kanban de uma reunião dentro da pasta da reunião.

        Args:
            meeting_dir: Pasta da reunião onde o Kanban será criado.
            tasks: Tarefas extraídas da reunião.
            meeting_title: Título para referência.

        Returns:
            Caminho do arquivo Kanban criado.
        """
        folder_name = meeting_dir.name
        kanban_path = meeting_dir / f"Tarefas - {folder_name}.md"

        if not tasks:
            kanban_path.write_text(EMPTY_BOARD, encoding="utf-8")
            logger.info("Kanban vazio criado (sem tarefas): %s", kanban_path)
            return kanban_path

        lines = [
            "---",
            "kanban-plugin: basic",
            "---",
            "",
            "## A Fazer",
            "",
        ]

        for task in tasks:
            # Linha principal do card
            card = f"- [ ] **{task.description}**"
            if task.due_date:
                card += f" @{{{task.due_date}}}"
            card += "\n"

            # Metadados do card
            details = []
            if task.assignee:
                details.append(f"\tresponsavel:: {task.assignee}")
            if task.priority:
                details.append(f"\tprioridade:: {task.priority}")
            if task.source_timestamp:
                details.append(f"\ttimestamp:: {task.source_timestamp}")

            card += "\n".join(details)
            lines.append(card)

        lines.extend([
            "",
            "## Em Progresso",
            "",
            "## Concluido",
            "",
        ])

        kanban_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(
            "%d tarefa(s) no Kanban: %s",
            len(tasks),
            kanban_path,
        )
        return kanban_path
