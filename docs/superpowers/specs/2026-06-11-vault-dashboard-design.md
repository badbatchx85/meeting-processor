# Dataview Vault Dashboard

**Date:** 2026-06-11
**Status:** Approved design

## Goal

A single regenerated landing note `wiki/Dashboard Geral.md` that aggregates the
vault: stats + recent meetings + open tasks. Pairs plugin-free content (always
works in Obsidian) with live Dataview blocks (for plugin users). Last Tier-3
backlog item; complements — does not duplicate — the per-person rollup.

## Background (exact, from exploration)

- `Resumo - *.md` notes carry Dataview-queryable frontmatter: `type: source`,
  `created`, `updated`, `participants`, `duration` (`"HH:MM:SS"`),
  `meeting_type`, `source_file`, `title`.
- `wiki/` currently has only `hot.md` and `log.md` — no general dashboard. The
  pipeline-status note is `wiki/reunioes/Dashboard.md`; the per-person rollup
  lives in `wiki/pessoas/` (incl. `Tarefas Pendentes.md`). The new note
  `wiki/Dashboard Geral.md` collides with none of these.
- `tasks_io.list_all_tasks(reunioes_dir) -> list[TaskCard]` and the constant
  `COLUMN_DONE` (`meeting_processor/web/tasks_io.py`). `TaskCard` has `done`,
  `column`, `assignee`. The rollup's "open" filter is
  `not t.done and t.column != COLUMN_DONE` (move_task does NOT flip the checkbox,
  so the column check is what drops a UI move-to-Done).
- Rollup hook sites to mirror: `pipeline.py:293-294` (in `_summarize`, inside the
  kanban `try`) and `web/app.py:1174-1175` (in the `/actions/tasks/move`
  handler, inside its `try`). Both call `regenerate_person_rollups(config)`.
- `config.reunioes_path` = `vault/wiki/reunioes`; `config.vault_path` = `vault`.

## 1. New module `meeting_processor/vault_dashboard.py`

```python
def _meeting_dirs(reunioes_dir: Path) -> list[Path]:
    """Pastas de reunião (com Resumo ou Transcricao), mais novas primeiro."""
```
- If `reunioes_dir` doesn't exist → `[]`.
- Keep dirs that have a `Resumo - *.md` OR `Transcricao - *.md`.
- `sorted(dirs, key=lambda d: d.name, reverse=True)` (folder name starts with
  `YYYY-MM-DD HHhMM`, so lexical desc = newest first). Returns ALL such dirs; the
  caller counts `len(...)` and slices `[:15]` for the recent list. Pure, testable.

```python
def regenerate_dashboard(config: Settings) -> None:
    """(Re)escreve wiki/Dashboard Geral.md com stats + reuniões + tarefas."""
```
1. `tasks = list_all_tasks(config.reunioes_path)`;
   `open_tasks = [t for t in tasks if not t.done and t.column != COLUMN_DONE]`.
2. `people = {(t.assignee or "").strip() or "Sem responsável" for t in open_tasks}`.
3. `dirs = _meeting_dirs(config.reunioes_path)`; `total_meetings = len(dirs)`;
   `recent = dirs[:15]` (the list rendered below).
4. Write `config.vault_path / "wiki" / "Dashboard Geral.md"` (mkdir the `wiki`
   dir; plain `write_text`, matching `WikiIntegrator`/person_rollup):

```markdown
---
type: dashboard
updated: <YYYY-MM-DD>
---

# Dashboard Geral

> [!info] {total_meetings} reuniões · {len(open_tasks)} tarefas abertas · {len(people)} pessoa(s) com tarefas

## Reuniões recentes

- [[<folder name>]]
... (the recent dirs, newest first; "_Nenhuma reunião ainda._" if empty)

> [!tip] Com o plugin Dataview, a tabela abaixo agrega tudo dinamicamente.

```dataview
TABLE WITHOUT ID file.link AS "Reunião", created AS "Data", duration AS "Duração", meeting_type AS "Tipo"
FROM "wiki/reunioes"
WHERE type = "source"
SORT created DESC
LIMIT 20
```

## Tarefas abertas

Lista completa por pessoa em [[Tarefas Pendentes]].

```dataview
TASK FROM "wiki/pessoas" WHERE !completed
```
```

`updated` = `datetime.now().strftime("%Y-%m-%d")`. The two fenced `dataview`
blocks are inert without the plugin (safe).

## 2. Hooks (mirror the rollup; same try/except)

Add `regenerate_dashboard(config)` immediately after the existing
`regenerate_person_rollups(config)` call at BOTH sites, inside the same guard:

- `pipeline.py` `_summarize` (after the `regenerate_person_rollups(self.config)`
  line): `from .vault_dashboard import regenerate_dashboard; regenerate_dashboard(self.config)`.
- `web/app.py` `task_move` (after `regenerate_person_rollups(config)`):
  `from ..vault_dashboard import regenerate_dashboard; regenerate_dashboard(config)`.

Both already sit in a `try/except … logger.warning`, so a dashboard failure is
non-fatal and never breaks the pipeline or the move request.

## Testing (TDD, no LLM/audio)

`tests/test_vault_dashboard.py` (uses the `config` fixture + a `_board` helper
like the rollup tests):
- **`_meeting_dirs`**: seed three dirs under `reunioes/` — two with a
  `Resumo - *.md` / `Transcricao - *.md`, one empty → returns only the two,
  newest-first by name. An absent `reunioes/` → `[]`.
- **`regenerate_dashboard`**: seed two meeting folders with kanban boards (open
  task for "Ana", a Done-column task, an unassigned open task) → `wiki/Dashboard
  Geral.md` exists; contains `# Dashboard Geral`; the stats callout shows
  `2 reuniões`, the open-task count (Done excluded), and the people count; both
  meeting folders appear as `[[…]]` links; both ```dataview``` blocks and the
  `[[Tarefas Pendentes]]` link are present.
- **empty vault**: `regenerate_dashboard` on a vault with no meetings → file
  written, `0 reuniões · 0 tarefas`, `_Nenhuma reunião ainda._`.

## Out of scope

- A frontend/web view (Obsidian-side note only).
- Configurable sections/limits.
- Replacing `hot.md`/`log.md`/the pipeline `Dashboard.md`.
- Factoring the shared open-task filter into `tasks_io` (kept inline, matching
  the rollup).
- A task-move test (the rollup's move test already covers the shared hook site;
  this feature's tests cover the generator directly).
