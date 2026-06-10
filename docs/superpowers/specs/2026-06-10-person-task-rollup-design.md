# Per-Person Task Rollup (vault)

**Date:** 2026-06-10
**Status:** Approved design

## Goal

Answer "what does each person still owe?" natively in the Obsidian vault. After
every ingest (and on every task move), regenerate one note per assignee under
`wiki/pessoas/<slug>.md` listing that person's **open** tasks with backlinks to
the source meeting, plus a `wiki/pessoas/Tarefas Pendentes.md` index. First
piece of the "who-said-what / who-owes-what" strategic spine.

## Background (exact, from exploration)

- `meeting_processor/web/tasks_io.py` already aggregates all tasks:
  `list_all_tasks(reunioes_dir: Path) -> list[TaskCard]` iterates each meeting
  folder under `reunioes_dir`, parses its `Tarefas - *.md`, and returns
  `TaskCard`s. `TaskCard` fields: `meeting_id` (the meeting **folder name**),
  `column`, `description`, `done: bool`, `assignee: str | None`,
  `priority`/`due_date`/`timestamp: str | None`.
- Kanban boards are written by `KanbanManager.create_board(meeting_dir, tasks,
  meeting_title)` at `Tarefas - {meeting_dir.name}.md` (plain `write_text`).
- `WikiIntegrator` writes `index.md`/`log.md`/`hot.md` with plain `write_text`
  (non-atomic) — the established pattern for regenerated vault artifacts.
- Pipeline hook: `_summarize` (`pipeline.py`) calls `self.kanban.create_board(...)`
  inside the `if steps["kanban"]:` block; the rollup runs right after.
- Task-move hook: `POST /actions/tasks/move` (`app.py`) calls
  `move_task(kanban_path, task_id, meeting_id, to_column)`; the rollup runs after
  a successful move.
- **No** name-slug helper exists (`utils.py` has no `unicodedata`). **No**
  `wiki/pessoas/` dir or cross-meeting aggregation exists. **Name collision to
  avoid:** `wiki/reunioes/Dashboard.md` is the pipeline-status note — the rollup
  output lives under `wiki/pessoas/` with distinct names.

## 1. Slug helper (`meeting_processor/utils.py`)

```python
def slugify(name: str) -> str:
    """Nome de pessoa -> nome de arquivo seguro (sem acento, minúsculo)."""
```
Implementation: `unicodedata.normalize("NFD", name)`, drop chars whose category
is `Mn` (combining marks), lowercase, replace runs of non-`[a-z0-9]` with `-`,
strip leading/trailing `-`. Empty result → `"sem-nome"`. Examples:
`"Ana Júlia"` → `"ana-julia"`, `"João"` → `"joao"`.

## 2. Rollup generator (`meeting_processor/person_rollup.py`, new)

`regenerate_person_rollups(config: Settings) -> int`:

1. `tasks = list_all_tasks(config.reunioes_path)` (import from
   `meeting_processor.web.tasks_io`).
2. Keep **open** tasks: `[t for t in tasks if not t.done]` (a card's `done` is set
   from its column being the DONE column; `not done` == not completed).
3. Group by assignee: `assignee = (t.assignee or "").strip() or "Sem responsável"`
   — unassigned open tasks collect under "Sem responsável" so they surface.
4. **Fully manage `pessoas_dir = config.vault_path / "wiki" / "pessoas"`**: create
   it; delete every existing `*.md` in it (the dir is app-owned), then write the
   current set. People whose tasks all closed get no note (removed by the wipe).
5. For each person, write `pessoas_dir / f"{slugify(name)}.md"`:
   ```markdown
   ---
   type: person-tasks
   updated: <YYYY-MM-DD>
   tags: ["tarefas", "pessoa"]
   ---

   # Tarefas — <Name>

   - [ ] <description>{ · <priority>}{ · prazo <due_date>} — [[<meeting_id>]]
   ...
   ```
   (priority/due_date segments only when present.) Tasks ordered by `meeting_id`
   then description.
6. Write `pessoas_dir / "Tarefas Pendentes.md"` — a plain-markdown index that
   always works, plus one Dataview block for plugin users:
   ```markdown
   ---
   type: tasks-dashboard
   updated: <YYYY-MM-DD>
   ---

   # Tarefas Pendentes por Pessoa

   - [[<slug>|<Name>]] — <N> tarefa(s)
   ...

   > [!info] Com o plugin Dataview, a lista abaixo agrega tudo em tempo real.

   ```dataview
   TASK FROM "wiki/pessoas" WHERE !completed
   ```
   ```
   (The fenced Dataview block is inert without the plugin — safe. It lists every
   incomplete checkbox across the per-person notes, grouped by file by default.)
7. Return the number of people written (for `logger.info`).

`updated` date: `datetime.now().strftime("%Y-%m-%d")`.

## 3. Hooks (DRY)

Both call `regenerate_person_rollups(config)`; failures are caught and logged
(a rollup error must never fail the pipeline or the move request).

- **Pipeline** (`pipeline.py` `_summarize`): immediately after
  `self.kanban.create_board(...)` (inside `if steps["kanban"]:`), call
  `regenerate_person_rollups(self.config)` wrapped in try/except → `logger.warning`.
- **Task-move** (`app.py` `task_move`): after `move_task(...)` returns truthy and
  before the success `JSONResponse`, call `regenerate_person_rollups(config)`
  wrapped in try/except → `logger.warning`.

No new config flag — the rollup is a kanban-derived artifact and runs whenever
the kanban step runs (pipeline) or a task is moved (always).

## 4. Writes

Plain `path.write_text(content, encoding="utf-8")`, matching `WikiIntegrator`/
`KanbanManager`. These notes are fully regenerated each run, so a torn write
self-heals on the next run — atomic writes (reserved for the history JSON) are
unnecessary here.

## Testing (TDD, no LLM/audio)

`tests/test_person_rollup.py`:
- **`slugify`**: `"Ana Júlia"`→`"ana-julia"`, `"João"`→`"joao"`, `"  "`→`"sem-nome"`,
  `"A/B C"`→`"a-b-c"`.
- **`regenerate_person_rollups`** (seed a temp vault via the `config` fixture):
  write two meeting folders each with a `Tarefas - <folder>.md` containing open
  + done checkboxes assigned to "Ana"/"Bruno" (use `KanbanManager.create_board`
  or hand-written files matching the kanban format). Then:
  - `pessoas/ana.md` and `pessoas/bruno.md` exist; each lists that person's
    **open** tasks with a `[[<meeting_id>]]` backlink; the done task is absent.
  - an unassigned open task lands in `pessoas/sem-responsavel.md`.
  - `pessoas/Tarefas Pendentes.md` lists each person with a count.
  - **stale removal:** after rewriting a board so Ana has no open tasks, a second
    `regenerate_person_rollups` run leaves no `pessoas/ana.md`.
  - returns the person count.
- **Move integration** (`client` fixture): seed a meeting + board with one open
  task for "Ana"; `regenerate_person_rollups`; `POST /actions/tasks/move` that
  task to the DONE column → `pessoas/ana.md` no longer lists it (regenerated).

## Out of scope

- Any frontend change (Obsidian renders the notes; the web Tasks board exists).
- Per-person completed-task history (open tasks only).
- A config toggle (tied to the kanban step / move action).
- Atomic writes for these notes.
- Speaker attribution / diarization (later spine pieces).
