"""(Re)gera o painel geral do vault (wiki/Dashboard Geral.md)."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from .config import Settings
from .web.tasks_io import COLUMN_DONE, list_all_tasks

logger = logging.getLogger(__name__)


def _meeting_dirs(reunioes_dir: Path) -> list[Path]:
    """Pastas de reunião (com Resumo ou Transcricao), mais novas primeiro."""
    if not reunioes_dir.exists():
        return []
    dirs = [
        d
        for d in reunioes_dir.iterdir()
        if d.is_dir()
        and (list(d.glob("Resumo - *.md")) or list(d.glob("Transcricao - *.md")))
    ]
    return sorted(dirs, key=lambda d: d.name, reverse=True)


def regenerate_dashboard(config: Settings) -> None:
    """Reescreve wiki/Dashboard Geral.md: stats + reuniões recentes + tarefas.

    Conteúdo simples (stats + links) funciona sem plugin; os blocos ```dataview```
    são inertes sem o Dataview.
    """
    tasks = list_all_tasks(config.reunioes_path)
    open_tasks = [t for t in tasks if not t.done and t.column != COLUMN_DONE]
    people = {(t.assignee or "").strip() or "Sem responsável" for t in open_tasks}
    dirs = _meeting_dirs(config.reunioes_path)
    recent = dirs[:15]

    today = datetime.now().strftime("%Y-%m-%d")
    lines = [
        "---",
        "type: dashboard",
        f"updated: {today}",
        "---",
        "",
        "# Dashboard Geral",
        "",
        f"> [!info] {len(dirs)} reuniões · {len(open_tasks)} tarefas abertas · "
        f"{len(people)} pessoa(s) com tarefas",
        "",
        "## Reuniões recentes",
        "",
    ]
    lines += [f"- [[{d.name}]]" for d in recent] if recent else ["_Nenhuma reunião ainda._"]
    lines += [
        "",
        "> [!tip] Com o plugin Dataview, a tabela abaixo agrega tudo dinamicamente.",
        "",
        "```dataview",
        'TABLE WITHOUT ID file.link AS "Reunião", created AS "Data", '
        'duration AS "Duração", meeting_type AS "Tipo"',
        'FROM "wiki/reunioes"',
        'WHERE type = "source"',
        "SORT created DESC",
        "LIMIT 20",
        "```",
        "",
        "## Tarefas abertas",
        "",
        "Lista completa por pessoa em [[Tarefas Pendentes]].",
        "",
        "```dataview",
        'TASK FROM "wiki/pessoas" WHERE !completed',
        "```",
        "",
    ]

    wiki_dir = config.vault_path / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    (wiki_dir / "Dashboard Geral.md").write_text("\n".join(lines), encoding="utf-8")
    logger.info(
        "Dashboard geral: %d reuniões, %d tarefas abertas.", len(dirs), len(open_tasks)
    )
