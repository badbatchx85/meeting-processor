"""Painel geral do vault (wiki/Dashboard Geral.md)."""
from meeting_processor.vault_dashboard import _meeting_dirs, regenerate_dashboard


def _board(folder, todo, done):
    """Quadro Tarefas - *.md com tarefas em 'A Fazer' e 'Concluido'."""
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


def _seed_meeting(config, folder, board=None):
    d = config.reunioes_path / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / f"Resumo - {folder}.md").write_text("# resumo", encoding="utf-8")
    if board is not None:
        (d / f"Tarefas - {folder}.md").write_text(board, encoding="utf-8")
    return d


def test_meeting_dirs_filters_and_sorts(config):
    _seed_meeting(config, "2026-01-01 10h00 - A")
    _seed_meeting(config, "2026-02-02 10h00 - B")
    (config.reunioes_path / "2026-03-03 10h00 - empty").mkdir(parents=True, exist_ok=True)
    dirs = _meeting_dirs(config.reunioes_path)
    assert [d.name for d in dirs] == ["2026-02-02 10h00 - B", "2026-01-01 10h00 - A"]


def test_meeting_dirs_missing(config, tmp_path):
    assert _meeting_dirs(tmp_path / "nope") == []


def test_regenerate_dashboard_stats_and_links(config):
    m1 = "2026-01-01 10h00 - A"
    _seed_meeting(config, m1, _board(m1, todo=[("T1", "Ana"), ("Orfa", None)], done=[("Feita", "Ana")]))
    m2 = "2026-02-02 10h00 - B"
    _seed_meeting(config, m2, _board(m2, todo=[("T2", "Bruno")], done=[]))

    regenerate_dashboard(config)
    text = (config.vault_path / "wiki" / "Dashboard Geral.md").read_text(encoding="utf-8")

    assert "# Dashboard Geral" in text
    assert "2 reuniões" in text
    assert "3 tarefas abertas" in text          # T1, Orfa, T2 — Feita (Concluido) excluded
    assert f"[[{m1}]]" in text and f"[[{m2}]]" in text
    assert "```dataview" in text
    assert "[[Tarefas Pendentes]]" in text


def test_regenerate_dashboard_empty_vault(config):
    regenerate_dashboard(config)
    text = (config.vault_path / "wiki" / "Dashboard Geral.md").read_text(encoding="utf-8")
    assert "0 reuniões · 0 tarefas abertas" in text
    assert "_Nenhuma reunião ainda._" in text
