"""Conversão das tarefas do Kanban para formatos de exportação.

Usado por ``GET /api/tasks/export.{csv,json,md,txt}``.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Iterable

from .tasks_io import COLUMN_LABEL, COLUMN_ORDER, TaskCard


def _column_label(col: str) -> str:
    return COLUMN_LABEL.get(col, col)


def to_csv(tasks: Iterable[TaskCard]) -> str:
    """CSV pronto para Excel/Sheets — UTF-8 com BOM, separador vírgula."""
    buf = io.StringIO()
    # BOM para Excel reconhecer UTF-8 automaticamente
    buf.write("﻿")
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    writer.writerow([
        "status",
        "tarefa",
        "responsavel",
        "prioridade",
        "prazo",
        "timestamp",
        "reuniao",
    ])
    for t in tasks:
        writer.writerow([
            _column_label(t.column),
            t.description,
            t.assignee or "",
            t.priority or "",
            t.due_date or "",
            t.timestamp or "",
            t.meeting_id,
        ])
    return buf.getvalue()


def to_json(tasks: Iterable[TaskCard]) -> str:
    """JSON pretty-printed."""
    payload = {
        "exported_at": datetime.now().isoformat(),
        "count": 0,
        "tasks": [],
    }
    items: list[dict] = []
    for t in tasks:
        items.append({
            "task_id": t.task_id,
            "meeting_id": t.meeting_id,
            "column": t.column,
            "column_label": _column_label(t.column),
            "description": t.description,
            "done": t.done,
            "assignee": t.assignee,
            "priority": t.priority,
            "due_date": t.due_date,
            "timestamp": t.timestamp,
        })
    payload["tasks"] = items
    payload["count"] = len(items)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def to_markdown(tasks: Iterable[TaskCard]) -> str:
    """Markdown com checklist por coluna."""
    tasks_list = list(tasks)
    lines: list[str] = []
    lines.append("# Tarefas exportadas")
    lines.append("")
    lines.append(f"_Gerado em {datetime.now().strftime('%Y-%m-%d %H:%M')}_  ")
    lines.append(f"_Total: {len(tasks_list)} tarefa(s)_")
    lines.append("")

    grouped: dict[str, list[TaskCard]] = {col: [] for col in COLUMN_ORDER}
    for t in tasks_list:
        grouped.setdefault(t.column, []).append(t)

    for col in COLUMN_ORDER:
        col_tasks = grouped.get(col, [])
        lines.append(f"## {_column_label(col)} ({len(col_tasks)})")
        lines.append("")
        if not col_tasks:
            lines.append("_(nenhuma)_")
            lines.append("")
            continue
        for t in col_tasks:
            checkbox = "[x]" if col == "done" else "[ ]"
            extras: list[str] = []
            if t.assignee:
                extras.append(f"@{t.assignee}")
            if t.priority:
                extras.append(f"prioridade: {t.priority}")
            if t.due_date:
                extras.append(f"prazo: {t.due_date}")
            extra_str = f" — _{', '.join(extras)}_" if extras else ""
            lines.append(f"- {checkbox} **{t.description}**{extra_str}")
            lines.append(f"  - Reunião: `{t.meeting_id}`")
        lines.append("")

    return "\n".join(lines)


def to_txt(tasks: Iterable[TaskCard]) -> str:
    """Texto plano com indentação ASCII — bom para colar em e-mail/chat."""
    tasks_list = list(tasks)
    lines: list[str] = []
    lines.append("TAREFAS EXPORTADAS")
    lines.append("=" * 60)
    lines.append(f"Gerado em: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"Total: {len(tasks_list)} tarefa(s)")
    lines.append("")

    grouped: dict[str, list[TaskCard]] = {col: [] for col in COLUMN_ORDER}
    for t in tasks_list:
        grouped.setdefault(t.column, []).append(t)

    for col in COLUMN_ORDER:
        col_tasks = grouped.get(col, [])
        lines.append("")
        lines.append(f"-- {_column_label(col).upper()} ({len(col_tasks)}) " + "-" * 30)
        if not col_tasks:
            lines.append("  (nenhuma)")
            continue
        for t in col_tasks:
            box = "[X]" if col == "done" else "[ ]"
            lines.append(f"")
            lines.append(f"  {box} {t.description}")
            details = []
            if t.assignee:
                details.append(f"resp: {t.assignee}")
            if t.priority:
                details.append(f"prio: {t.priority}")
            if t.due_date:
                details.append(f"prazo: {t.due_date}")
            if details:
                lines.append(f"      ({' | '.join(details)})")
            lines.append(f"      reuniao: {t.meeting_id}")

    return "\n".join(lines) + "\n"


__all__ = ["to_csv", "to_json", "to_markdown", "to_txt"]
