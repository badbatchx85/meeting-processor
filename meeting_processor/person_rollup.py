"""(Re)gera notas de tarefas por pessoa no vault (wiki/pessoas/)."""
from __future__ import annotations

import logging
from datetime import datetime

from .config import Settings
from .utils import slugify
from .web.tasks_io import COLUMN_DONE, list_all_tasks

logger = logging.getLogger(__name__)


def regenerate_person_rollups(config: Settings) -> int:
    """Reescreve wiki/pessoas/<slug>.md por responsável com as tarefas ABERTAS.

    Aberta = checkbox não marcado E fora da coluna "Concluido" (mover para
    Concluido não marca o checkbox, então a checagem de coluna é o que faz a
    tarefa sair do rollup). O diretório pessoas/ é totalmente gerenciado: cada
    execução limpa os .md e reescreve, então quem zera as tarefas perde a nota.
    Retorna o número de pessoas com tarefas abertas.
    """
    tasks = list_all_tasks(config.reunioes_path)
    open_tasks = [t for t in tasks if not t.done and t.column != COLUMN_DONE]

    by_person: dict[str, list] = {}
    for t in open_tasks:
        name = (t.assignee or "").strip() or "Sem responsável"
        by_person.setdefault(name, []).append(t)

    pessoas_dir = config.vault_path / "wiki" / "pessoas"
    pessoas_dir.mkdir(parents=True, exist_ok=True)
    for md in pessoas_dir.glob("*.md"):
        md.unlink()

    today = datetime.now().strftime("%Y-%m-%d")
    for name in sorted(by_person):
        items = sorted(by_person[name], key=lambda t: (t.meeting_id, t.description))
        lines = [
            "---",
            "type: person-tasks",
            f"updated: {today}",
            'tags: ["tarefas", "pessoa"]',
            "---",
            "",
            f"# Tarefas — {name}",
            "",
        ]
        for t in items:
            extra = ""
            if t.priority:
                extra += f" · {t.priority}"
            if t.due_date:
                extra += f" · prazo {t.due_date}"
            lines.append(f"- [ ] {t.description}{extra} — [[{t.meeting_id}]]")
        (pessoas_dir / f"{slugify(name)}.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

    dash = [
        "---",
        "type: tasks-dashboard",
        f"updated: {today}",
        "---",
        "",
        "# Tarefas Pendentes por Pessoa",
        "",
    ]
    for name in sorted(by_person):
        dash.append(f"- [[{slugify(name)}|{name}]] — {len(by_person[name])} tarefa(s)")
    dash += [
        "",
        "> [!info] Com o plugin Dataview, a lista abaixo agrega tudo em tempo real.",
        "",
        "```dataview",
        'TASK FROM "wiki/pessoas" WHERE !completed',
        "```",
        "",
    ]
    (pessoas_dir / "Tarefas Pendentes.md").write_text("\n".join(dash), encoding="utf-8")

    logger.info("Rollup de tarefas por pessoa: %d pessoa(s).", len(by_person))
    return len(by_person)
