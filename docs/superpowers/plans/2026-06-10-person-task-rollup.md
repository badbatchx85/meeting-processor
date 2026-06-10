# Per-Person Task Rollup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate `wiki/pessoas/<slug>.md` notes per assignee (open tasks + meeting backlinks) plus a "Tarefas Pendentes" index, regenerated on each ingest and on task-move.

**Architecture:** A `slugify` helper in `utils.py`; a `meeting_processor/person_rollup.py` module reading `list_all_tasks` and writing the per-person notes + index; two hooks (pipeline `_summarize` after the kanban board is written, and the `/actions/tasks/move` endpoint after a successful move) that call it inside a try/except.

**Tech Stack:** Python 3.14, stdlib (`unicodedata`, `pathlib`), pytest + FastAPI TestClient.

Run tests with `.venv/bin/python -m pytest`. The pre-existing `test_summarizer_mock.py::test_factory_selects_anthropic` failure (no `ANTHROPIC_API_KEY`) is unrelated.

---

## File Structure
- **Modify** `meeting_processor/utils.py` — add `slugify`.
- **Create** `meeting_processor/person_rollup.py` — `regenerate_person_rollups`.
- **Modify** `meeting_processor/pipeline.py` — hook in `_summarize` (after kanban).
- **Modify** `meeting_processor/web/app.py` — hook in `task_move`.
- **Create** `tests/test_person_rollup.py`.

---

### Task 1: `slugify` helper

**Files:** Modify `meeting_processor/utils.py`; Create `tests/test_person_rollup.py`.

- [ ] **Step 1: Write the failing tests** — create `tests/test_person_rollup.py`:

```python
"""Rollup de tarefas por pessoa no vault."""
from meeting_processor.utils import slugify


def test_slugify():
    assert slugify("Ana Júlia") == "ana-julia"
    assert slugify("João") == "joao"
    assert slugify("A/B C") == "a-b-c"
    assert slugify("   ") == "sem-nome"
    assert slugify("Sem responsável") == "sem-responsavel"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_person_rollup.py -q`
Expected: FAIL — `cannot import name 'slugify'`.

- [ ] **Step 3: Implement.** In `meeting_processor/utils.py`, add `import unicodedata` and `import re` to the top (if `re` isn't already imported), then add:

```python
def slugify(name: str) -> str:
    """Nome de pessoa -> nome de arquivo seguro (sem acento, minúsculo)."""
    nfkd = unicodedata.normalize("NFD", name or "")
    ascii_name = "".join(c for c in nfkd if unicodedata.category(c) != "Mn")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    return slug or "sem-nome"
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_person_rollup.py -q`
Expected: PASS (1 test).

- [ ] **Step 5: Commit**

```bash
git add meeting_processor/utils.py tests/test_person_rollup.py
git commit -m "feat(tasks): slugify helper for person filenames"
```

---

### Task 2: `regenerate_person_rollups`

**Files:** Create `meeting_processor/person_rollup.py`; Test: `tests/test_person_rollup.py`.

- [ ] **Step 1: Append the failing tests** to `tests/test_person_rollup.py`:

```python
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
    # Ana's only task moves to Concluido → she has no open tasks now
    _write_board(config, m1, _board(m1, todo=[], done=[("T", "Ana")]))
    regenerate_person_rollups(config)
    assert not (config.vault_path / "wiki" / "pessoas" / "ana.md").exists()
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_person_rollup.py -k rollup -q`
Expected: FAIL — no `meeting_processor.person_rollup`.

- [ ] **Step 3: Create `meeting_processor/person_rollup.py`:**

```python
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
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_person_rollup.py -q`
Expected: PASS (slugify + 2 rollup tests). Confirm import: `.venv/bin/python -c "import meeting_processor.person_rollup"`.

- [ ] **Step 5: Commit**

```bash
git add meeting_processor/person_rollup.py tests/test_person_rollup.py
git commit -m "feat(tasks): per-person rollup generator (wiki/pessoas/)"
```

---

### Task 3: Hooks (pipeline + task-move)

**Files:** Modify `meeting_processor/pipeline.py` (`_summarize`), `meeting_processor/web/app.py` (`task_move`); Test: `tests/test_person_rollup.py`.

- [ ] **Step 1: Append the failing test** to `tests/test_person_rollup.py`:

```python
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
    # the move hook regenerated the rollup → Ana now has no open tasks
    assert not (pessoas / "ana.md").exists()
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_person_rollup.py -k move_to_done -q`
Expected: FAIL — the move endpoint doesn't regenerate the rollup, so `ana.md` still exists.

- [ ] **Step 3: Hook the task-move endpoint.** In `meeting_processor/web/app.py`, in `task_move`, replace the success return:

```python
        if not ok:
            raise HTTPException(status_code=404, detail="Tarefa não encontrada")

        return JSONResponse({"ok": True, "moved_to": to_column})
```

with:

```python
        if not ok:
            raise HTTPException(status_code=404, detail="Tarefa não encontrada")

        try:
            from ..person_rollup import regenerate_person_rollups
            regenerate_person_rollups(config)
        except Exception:  # noqa: BLE001 — rollup não pode derrubar o move
            logger.warning("Falha ao regenerar rollup após mover tarefa", exc_info=True)

        return JSONResponse({"ok": True, "moved_to": to_column})
```

- [ ] **Step 4: Run the move test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_person_rollup.py -k move_to_done -q`
Expected: PASS.

- [ ] **Step 5: Hook the pipeline.** In `meeting_processor/pipeline.py`, in `_summarize`, find the end of the `if steps["kanban"]:` block — the final `self.dashboard.update(job)` that follows the kanban `try/except`. Immediately after it (still indented inside `if steps["kanban"]:`), add:

```python
                try:
                    from .person_rollup import regenerate_person_rollups
                    regenerate_person_rollups(self.config)
                except Exception as e:  # noqa: BLE001 — rollup não é crítico
                    logger.warning("Falha ao gerar rollup de tarefas (nao critico): %s", e)
```

- [ ] **Step 6: Run full suite (regression + confirm the pipeline still works)**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS except the pre-existing `test_summarizer_mock.py::test_factory_selects_anthropic` (no `ANTHROPIC_API_KEY`). `tests/test_stuck_jobs.py::test_audio_extraction_failure_marks_job_error` and the other pipeline tests still pass — the rollup hook is wrapped in try/except and the kanban step is off in those paths or the rollup runs harmlessly on an empty/no-task vault.
Confirm import: `.venv/bin/python -c "import meeting_processor.pipeline, meeting_processor.web.app"`.

- [ ] **Step 7: Commit**

```bash
git add meeting_processor/pipeline.py meeting_processor/web/app.py tests/test_person_rollup.py
git commit -m "feat(tasks): regenerate person rollups after kanban write + task move"
```

---

## Self-Review

**Spec coverage:**
- `slugify` (NFD + strip Mn + lowercase + `-`, empty→"sem-nome") → Task 1. ✓
- `regenerate_person_rollups`: open filter (`not done and column != COLUMN_DONE`), group by assignee with "Sem responsável" bucket, wipe+rewrite `pessoas/`, per-person note with frontmatter + backlinks, "Tarefas Pendentes" index (plain list + Dataview block), return count → Task 2. ✓
- Hooks: pipeline `_summarize` after kanban (try/except) + `task_move` after success (try/except) → Task 3. ✓
- Tests: slugify; rollup creates notes/backlinks/excludes done/unassigned bucket/index/count; stale removal; move-to-Done drops the task → Tasks 1-3. ✓
- Plain `write_text`; no new config flag; no frontend → matches spec out-of-scope. ✓

**Placeholder scan:** none — every step has concrete code/commands.

**Type consistency:** `slugify(name) -> str` (Task 1) used in `person_rollup.py` (Task 2). `regenerate_person_rollups(config) -> int` (Task 2) called in both hooks (Task 3) and the tests. `COLUMN_DONE`/`list_all_tasks`/`TaskCard` imported from `meeting_processor.web.tasks_io` (matches the explored module). `config.reunioes_path` + `config.vault_path` are existing `Settings` properties. The test board format matches `KanbanManager.create_board`'s output (`## A Fazer`/`## Concluido`, `- [ ] **desc**`, `\tresponsavel:: name`), and `parse_kanban_file` sets `done` from the `[x]` checkbox and `column` from the section header. Names consistent throughout. ✓
