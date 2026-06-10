"""Rollup de tarefas por pessoa no vault."""
from meeting_processor.utils import slugify


def test_slugify():
    assert slugify("Ana Júlia") == "ana-julia"
    assert slugify("João") == "joao"
    assert slugify("A/B C") == "a-b-c"
    assert slugify("   ") == "sem-nome"
    assert slugify("Sem responsável") == "sem-responsavel"


# --- Task 2: regenerate_person_rollups -------------------------------------

from meeting_processor.person_rollup import regenerate_person_rollups


def _board(folder, todo, done):
    """Monta um Tarefas - *.md com tarefas em 'A Fazer' e 'Concluido'.
    todo/done são listas de (descricao, assignee|None)."""
    lines = ["---", "kanban-plugin: basic", "---", "", "## A Fazer", ""]
    for desc, who in todo:
        lines.append(f"- [ ] **{desc}**")
        if who:
            lines.append(f"\tresponsavel:: {who}")
    lines += ["", "## Em Progresso", "", "## Concluido", ""]
    for desc, who in done:
        lines.append(f"- [ ] **{desc}**")
        if who:
            lines.append(f"\tresponsavel:: {who}")
    return "\n".join(lines)


def _write_board(config, folder, body):
    d = config.reunioes_path / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / f"Tarefas - {folder}.md").write_text(body, encoding="utf-8")


def test_rollup_creates_person_notes_with_backlinks(config):
    m1 = "2026-01-01 10h00 - Reuniao A"
    _write_board(config, m1, _board(m1,
        todo=[("Enviar relatorio", "Ana"), ("Sem dono task", None)],
        done=[("Fechar contrato", "Ana")]))
    m2 = "2026-01-02 10h00 - Reuniao B"
    _write_board(config, m2, _board(m2, todo=[("Revisar PR", "Bruno")], done=[]))

    n = regenerate_person_rollups(config)
    pessoas = config.vault_path / "wiki" / "pessoas"

    ana = (pessoas / "ana.md").read_text(encoding="utf-8")
    assert "Enviar relatorio" in ana
    assert f"[[{m1}]]" in ana
    assert "Fechar contrato" not in ana            # Concluido column → excluded
    assert (pessoas / "bruno.md").read_text(encoding="utf-8").count("Revisar PR") == 1
    assert (pessoas / "sem-responsavel.md").exists()   # unassigned bucket
    assert (pessoas / "Tarefas Pendentes.md").exists()
    assert n == 3                                   # Ana, Bruno, Sem responsável


def test_rollup_removes_stale_person_note(config):
    m1 = "2026-01-01 10h00 - Reuniao A"
    _write_board(config, m1, _board(m1, todo=[("T", "Ana")], done=[]))
    regenerate_person_rollups(config)
    assert (config.vault_path / "wiki" / "pessoas" / "ana.md").exists()
    _write_board(config, m1, _board(m1, todo=[], done=[("T", "Ana")]))
    regenerate_person_rollups(config)
    assert not (config.vault_path / "wiki" / "pessoas" / "ana.md").exists()


# --- Task 3: move hook regenerates the rollup ------------------------------


def test_move_to_done_drops_from_rollup(client, config):
    from meeting_processor.web.tasks_io import list_all_tasks
    m1 = "2026-01-01 10h00 - Reuniao A"
    _write_board(config, m1, _board(m1, todo=[("Tarefa Ana", "Ana")], done=[]))
    regenerate_person_rollups(config)
    pessoas = config.vault_path / "wiki" / "pessoas"
    assert "Tarefa Ana" in (pessoas / "ana.md").read_text(encoding="utf-8")

    task = next(t for t in list_all_tasks(config.reunioes_path) if t.description == "Tarefa Ana")
    r = client.post("/actions/tasks/move",
                    json={"task_id": task.task_id, "meeting_id": m1, "to_column": "done"})
    assert r.status_code == 200
    assert not (pessoas / "ana.md").exists()
