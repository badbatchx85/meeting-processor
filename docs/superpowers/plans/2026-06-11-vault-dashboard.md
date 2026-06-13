# Dataview Vault Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate `wiki/Dashboard Geral.md` — vault stats + recent meetings + open tasks (plain content + live Dataview), regenerated on each ingest and task-move.

**Architecture:** A `vault_dashboard` module (mirroring `person_rollup`) reads `list_all_tasks` + meeting folders and writes the note; hooked next to the existing `regenerate_person_rollups` calls in the pipeline and the task-move endpoint.

**Tech Stack:** Python 3.14, pytest + FastAPI TestClient.

Run tests with `.venv/bin/python -m pytest`. The pre-existing `test_summarizer_mock.py::test_factory_selects_anthropic` failure (no `ANTHROPIC_API_KEY`) is unrelated.

---

## File Structure
- **Create** `meeting_processor/vault_dashboard.py` — `_meeting_dirs` + `regenerate_dashboard`.
- **Modify** `meeting_processor/pipeline.py` — call it next to the rollup (in `_summarize`).
- **Modify** `meeting_processor/web/app.py` — call it next to the rollup (in `task_move`).
- **Create** `tests/test_vault_dashboard.py`.

---

### Task 1: `vault_dashboard` module

**Files:** Create `meeting_processor/vault_dashboard.py`, `tests/test_vault_dashboard.py`.

- [ ] **Step 1: Write the failing tests** — create `tests/test_vault_dashboard.py`:

```python
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_vault_dashboard.py -q`
Expected: FAIL — no `meeting_processor.vault_dashboard`.

- [ ] **Step 3: Create `meeting_processor/vault_dashboard.py`:**

```python
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
    são inertes sem o Dataview. Nunca levanta para o chamador embrulhar.
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
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_vault_dashboard.py -q`
Expected: PASS (4 tests). Confirm `.venv/bin/python -c "import meeting_processor.vault_dashboard"`.

- [ ] **Step 5: Commit**

```bash
git add meeting_processor/vault_dashboard.py tests/test_vault_dashboard.py
git commit -m "feat(vault): Dashboard Geral generator (stats + meetings + Dataview)"
```

---

### Task 2: Hooks (pipeline + task-move)

**Files:** Modify `meeting_processor/pipeline.py`, `meeting_processor/web/app.py`; Test: `tests/test_vault_dashboard.py`.

- [ ] **Step 1: Append the failing test** to `tests/test_vault_dashboard.py`:

```python
# --- Task 2: the task-move hook also writes the dashboard -------------------


def test_move_endpoint_writes_dashboard(client, config):
    from meeting_processor.web.tasks_io import list_all_tasks
    m1 = "2026-01-01 10h00 - A"
    _seed_meeting(config, m1, _board(m1, todo=[("T", "Ana")], done=[]))
    task = next(t for t in list_all_tasks(config.reunioes_path) if t.description == "T")
    r = client.post("/actions/tasks/move",
                    json={"task_id": task.task_id, "meeting_id": m1, "to_column": "done"})
    assert r.status_code == 200
    assert (config.vault_path / "wiki" / "Dashboard Geral.md").exists()
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_vault_dashboard.py -k move_endpoint -q`
Expected: FAIL — the move endpoint regenerates the rollup but not the dashboard, so `Dashboard Geral.md` doesn't exist.

- [ ] **Step 3: Hook the pipeline.** In `meeting_processor/pipeline.py`, the `_summarize` rollup block currently reads:

```python
                try:
                    from .person_rollup import regenerate_person_rollups
                    regenerate_person_rollups(self.config)
                except Exception as e:  # noqa: BLE001 — rollup não é crítico
                    logger.warning("Falha ao gerar rollup de tarefas (nao critico): %s", e)
```

Replace it with:

```python
                try:
                    from .person_rollup import regenerate_person_rollups
                    from .vault_dashboard import regenerate_dashboard
                    regenerate_person_rollups(self.config)
                    regenerate_dashboard(self.config)
                except Exception as e:  # noqa: BLE001 — rollup/dashboard não são críticos
                    logger.warning("Falha ao gerar rollup/dashboard (nao critico): %s", e)
```

- [ ] **Step 4: Hook the task-move endpoint.** In `meeting_processor/web/app.py`, the `task_move` rollup block currently reads:

```python
        try:
            from ..person_rollup import regenerate_person_rollups
            regenerate_person_rollups(config)
        except Exception:  # noqa: BLE001 — rollup não pode derrubar o move
            logger.warning("Falha ao regenerar rollup após mover tarefa", exc_info=True)
```

Replace it with:

```python
        try:
            from ..person_rollup import regenerate_person_rollups
            from ..vault_dashboard import regenerate_dashboard
            regenerate_person_rollups(config)
            regenerate_dashboard(config)
        except Exception:  # noqa: BLE001 — agregados não podem derrubar o move
            logger.warning("Falha ao regenerar rollup/dashboard após mover tarefa", exc_info=True)
```

- [ ] **Step 5: Run the move test + full suite**

Run: `.venv/bin/python -m pytest tests/test_vault_dashboard.py -q` (5 pass), then
`.venv/bin/python -m pytest -q`
Expected: PASS except the pre-existing `test_factory_selects_anthropic`.
Confirm `.venv/bin/python -c "import meeting_processor.pipeline, meeting_processor.web.app"`.

- [ ] **Step 6: Commit**

```bash
git add meeting_processor/pipeline.py meeting_processor/web/app.py tests/test_vault_dashboard.py
git commit -m "feat(vault): regenerate Dashboard Geral after kanban write + task move"
```

---

## Self-Review

**Spec coverage:**
- `_meeting_dirs` (filter Resumo/Transcricao, newest-first, `[]` when absent) → Task 1. ✓
- `regenerate_dashboard`: stats callout (meetings/open-tasks/people; open = `not done and != COLUMN_DONE`), recent `[[folder]]` links (+ empty fallback), Dataview TABLE + TASK blocks, `[[Tarefas Pendentes]]` link; plain `write_text` to `wiki/Dashboard Geral.md` → Task 1. ✓
- Hooks next to the rollup in `_summarize` + `task_move`, inside the existing guards → Task 2. ✓
- Tests: `_meeting_dirs` filter/sort/missing; dashboard stats+links+Dataview; empty vault; move-endpoint writes it → Tasks 1-2. ✓
- Out of scope (frontend, configurability, replacing other notes, factoring the filter) → untouched. ✓

**Placeholder scan:** none — every step has concrete code/commands.

**Type consistency:** `_meeting_dirs(reunioes_dir) -> list[Path]` and `regenerate_dashboard(config) -> None` (Task 1) called by the hooks (Task 2) and the tests. Imports `COLUMN_DONE`/`list_all_tasks` from `meeting_processor.web.tasks_io` (matches `person_rollup`). `config.reunioes_path`/`config.vault_path` are existing `Settings` properties. The open-task filter matches the rollup exactly. The `_board`/`_seed_meeting` test helpers match the kanban format (`## A Fazer`/`## Concluido`, `- [ ] **desc**`, `\tresponsavel:: name`) that `parse_kanban_file` reads. Names consistent throughout. ✓
