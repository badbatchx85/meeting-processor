# Design: Modern SPA Frontend for Meeting Processor

**Date:** 2026-06-03
**Status:** Approved (design), pending implementation plan
**Author:** brainstorming session

## 1. Goal

Build a modern single-page application (SPA) with **full feature parity** to the
existing server-rendered HTMX UI, served as static files by the existing FastAPI
server. The SPA reads from the existing `GET /api/*` endpoints and writes through a
new **additive JSON mutation layer** that reuses the same helper functions the
current HTML `/actions/*` handlers call.

Non-goals: replacing the backend, removing the HTMX UI (it stays as a fallback),
auth, real-time websockets, internationalization.

## 2. Stack

- **React 18 + Vite + TypeScript + Tailwind CSS**
- `react-router-dom` — client routing (history mode, `basename="/ui"`)
- `@tanstack/react-query` — data fetching, caching, polling, invalidation
- `@dnd-kit/core` + `@dnd-kit/sortable` — Kanban drag-and-drop
- `react-markdown` + `remark-gfm` — render summary & transcript markdown
- `lucide-react` — icons
- Dev/test: `vitest`, `@testing-library/react`, `msw` (mock API)

## 3. Integration & Routing

The backend already owns these page paths as HTMX routes: `/dashboard`,
`/reunioes`, `/tarefas`, `/configuracao`, `/meetings/{id}`. To avoid collisions the
SPA is namespaced under **`/ui`** with history routing.

Backend changes (all additive, in `meeting_processor/web/app.py`):

- `GET /` → `RedirectResponse("/ui")` (currently redirects to `/dashboard`).
- `GET /ui` and `GET /ui/{path:path}` → return the SPA `index.html` so client-side
  routes survive a hard refresh.
- Mount built assets with `StaticFiles` (Vite emits hashed assets under the
  `base:"/ui/"` prefix; serve `meeting_processor/web/spa/assets`).
- **Graceful fallback:** if `meeting_processor/web/spa/index.html` does not exist
  (Node/build not run), `GET /` keeps today's behavior (redirect to `/dashboard`)
  and `/ui` returns a short "run `npm run build`" message. The app must remain
  runnable without Node.

Existing `/api/*`, `/actions/*`, and all HTMX page routes are untouched.

## 4. Backend: New JSON Mutation Endpoints

Thin wrappers that call existing helpers (already return `{ok, ...}` dicts) and
return JSON. Errors return `{ok: false, error}` with appropriate status codes.

| Method & path | Calls | Returns |
|---|---|---|
| `POST /api/watcher/start` | `supervisor.start()` | `{ok, error?, watcher}` |
| `POST /api/watcher/stop` | `supervisor.stop()` | `{ok, error?, watcher}` |
| `POST /api/watcher/restart` | `supervisor.restart()` | `{ok, error?, watcher}` |
| `POST /api/llm/provider` `{provider}` | `set_llm_provider()` (+restart if running) | `{ok, error?, llm}` (400 if invalid) |
| `POST /api/config/watch-dir` `{watch_dir}` | `set_watch_dir()` (+restart if running) | `{ok, exists, error?, paths}` (400 if invalid) |
| `POST /api/config/steps` `{summary,note,kanban,wiki}` | `set_pipeline_steps()` (+restart if running) | `{ok, steps}` |
| `POST /api/process` `{file}` | spawn pipeline thread | `{ok, queued}` (400 if path missing) |
| `POST /api/meetings/{id}/delete` | `_delete_meeting()` | `{ok, removed}` (404 if absent) |
| `POST /api/history/remove` `{id}` | existing history helper | `{ok}` |
| `POST /api/history/clear-errors` | existing history helper | `{ok}` |
| `POST /api/tasks/move` `{task_id,to_column}` | existing move logic | `{ok, moved_to}` (reuse `/actions/tasks/move` JSON) |

`POST /api/process` stays **path-based** to match the current backend (the existing
`/actions/process` accepts a server-side file path, not an upload). Real multipart
upload is an explicit optional future enhancement, out of scope here.

## 5. Data Contract (existing reads, reused as-is)

- `GET /api/health` → `{status, llm_provider, vault, timestamp}`
- `GET /api/watcher` → `{running, pid, started_at, exit_code}`
- `GET /api/llm` → `{provider, label, anthropic_model, ollama_model, anthropic_key_set, valid_providers}`
- `GET /api/meetings` → `[{id, title, created, duration, task_count, participants, source_file}]`
- `GET /api/meetings/{id}` → `{id, title, meta, resumo_md, tasks, transcricao_md}`
- `GET /api/tasks` → `[{task_id, meeting_id, column, description, done, assignee, priority, due_date, timestamp}]`
- `GET /api/tasks/export.{csv,json,md,txt}?assignee=&meeting=&column=`

TypeScript types in `src/api/types.ts` mirror these exactly.

## 6. Frontend Structure

```
frontend/
  index.html  package.json  vite.config.ts  tsconfig.json
  tailwind.config.js  postcss.config.js
  src/
    main.tsx                  # bootstrap + QueryClientProvider + Router
    App.tsx                   # routes + AppShell
    api/types.ts              # API response/request types
    api/client.ts             # typed fetch wrapper, throws ApiError
    lib/queryClient.ts        # TanStack Query client
    hooks/                    # useHealth, useWatcher, useLlm,
                              #   useMeetings, useMeeting, useTasks (+ mutations)
    components/               # AppShell, Sidebar, TopBar, StatusBadge,
                              #   Card, MarkdownView, Toast, EmptyState, ConfirmDialog
    pages/                    # Dashboard, Meetings, MeetingDetail, Tasks, Settings
    styles/index.css          # tailwind directives + base theme
```

Build output: Vite `build.outDir = "../meeting_processor/web/spa"`, `base = "/ui/"`.

## 7. Pages (parity with HTMX UI)

1. **Dashboard** — health + LLM provider badge; watcher status card (running / pid /
   started_at) polling every 3s; start / stop / restart buttons; "process a file"
   input (path); recent meetings list; quick links.
2. **Meetings** — list (cards or table) with title, created, duration, participants,
   task_count; client-side search/filter; delete (with confirm).
3. **Meeting detail** — tabs: Summary (markdown), Tasks (list), Transcript
   (markdown); "open folder in Obsidian" link (`obsidian://` URI).
4. **Tasks (Kanban)** — columns A Fazer / Em Progresso / Concluído; drag-to-move
   (calls `POST /api/tasks/move`, optimistic update + invalidate); filters
   (assignee, meeting); export menu (csv/json/md/txt).
5. **Settings** — LLM provider select; watch-dir field; pipeline-step toggles
   (summary/note/kanban/wiki); each saves via the JSON config endpoints.

## 8. Data Flow & State

- All reads go through TanStack Query hooks. Live data (health, watcher) polls every
  3s via `refetchInterval`.
- Mutations are Query mutations that invalidate the relevant query keys on success;
  Kanban move uses optimistic update with rollback on error.
- Errors from `api/client.ts` (`ApiError` with status + message) surface as toasts.

## 9. Error Handling

- API client throws `ApiError`; non-2xx parsed for `{error}` message.
- Mutation endpoints return structured `{ok:false, error}` with 400/404 as noted.
- Missing SPA build → backend fallback (Section 3) keeps the app usable.
- Kanban move failure → optimistic state rolls back, toast shown.

## 10. Build & Run

- **Dev:** `cd frontend && npm install && npm run dev` (Vite on 5173, proxies
  `/api`, `/actions`, `/ui` to `http://127.0.0.1:8765`); run backend separately with
  `python -m meeting_processor web`.
- **Prod / local use:** `npm run build` → emits to `meeting_processor/web/spa/`;
  then `python -m meeting_processor web` serves the SPA at `/` (→ `/ui`).
- `meeting_processor/web/spa/` added to `.gitignore` (build artifact).
- Document the two commands in `docs/frontend-spa.md` and link from README.

## 11. Testing

- **Backend (pytest, extend `test_web_app.py`):** new JSON endpoints — watcher
  start/stop returns `{ok, watcher}`; invalid provider → 400; steps toggle persists;
  `process` with missing file → 400; delete missing meeting → 404; `/` redirects to
  `/ui` when build present and to `/dashboard` when absent.
- **Frontend (vitest + Testing Library + MSW):** `api/client` error mapping; Kanban
  drag-move calls the move mutation and updates columns; meeting-detail tab switching
  renders markdown. Keep the suite small and focused.
- **Manual:** `npm run build` then load `/`, click through all five pages.

## 12. Out of Scope (YAGNI)

- Authentication (local single-user app).
- WebSockets / SSE (3s polling is sufficient).
- Real multipart file upload (path-based parity now; optional future enhancement).
- Internationalization (UI stays Portuguese to match the existing app).
