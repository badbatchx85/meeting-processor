# SPA Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a React + Vite + TypeScript + Tailwind SPA with full feature parity to the existing HTMX UI, served by FastAPI at `/ui`, backed by an additive JSON mutation layer.

**Architecture:** The SPA lives in `frontend/` and builds to `meeting_processor/web/spa/`. FastAPI redirects `/` → `/ui`, serves the SPA shell for `/ui/*` (history routing), and mounts hashed assets. A small set of new `POST /api/*` JSON endpoints wrap the same helpers the HTML `/actions/*` already use; existing JSON endpoints (`DELETE /api/meetings/{id}`, `DELETE /api/history`, `POST /actions/tasks/move`) are reused as-is. If the SPA build is absent, `/` falls back to today's redirect-to-`/dashboard`, so the app still runs without Node.

**Tech Stack:** Backend FastAPI + pytest. Frontend React 18, Vite, TypeScript, Tailwind, `react-router-dom`, `@tanstack/react-query`, `@dnd-kit`, `react-markdown`+`remark-gfm`, `lucide-react`; tests with `vitest` + `@testing-library/react` + `msw`.

**Reference spec:** `docs/superpowers/specs/2026-06-03-spa-frontend-design.md`

**Conventions:**
- Backend Python runs in the project venv: prefix commands with `.venv/bin/`.
- Frontend commands run from `frontend/`.
- Commit after every green step.

---

## File Structure

**Backend (modify/create):**
- Modify `meeting_processor/web/app.py` — add SPA-serving routes + JSON mutation endpoints.
- Create `meeting_processor/web/spa_serving.py` — helpers to locate the built SPA and build fallback responses (keeps `app.py` focused).
- Create `tests/__init__.py`, `tests/conftest.py`, `tests/test_spa_serving.py`, `tests/test_api_mutations.py`.
- Modify `requirements.txt` — add `pytest` (dev).
- Modify `.gitignore` — ignore `meeting_processor/web/spa/`.

**Frontend (create under `frontend/`):**
```
frontend/
  package.json  vite.config.ts  tsconfig.json  tsconfig.node.json
  tailwind.config.js  postcss.config.js  index.html  vitest.setup.ts
  src/
    main.tsx  App.tsx  styles/index.css
    api/types.ts  api/client.ts
    lib/queryClient.ts
    hooks/useApi.ts            # all read + mutation hooks
    components/
      AppShell.tsx  Sidebar.tsx  TopBar.tsx  StatusBadge.tsx
      Card.tsx  MarkdownView.tsx  Toast.tsx  EmptyState.tsx  ConfirmDialog.tsx
    pages/
      Dashboard.tsx  Meetings.tsx  MeetingDetail.tsx  Tasks.tsx  Settings.tsx
  src/__tests__/
      client.test.ts  tasks.test.tsx  meetingDetail.test.tsx
```

**Docs:**
- Create `docs/frontend-spa.md`; link from `README.md`.

---

## Phase 1 — Backend: SPA serving + JSON mutation layer

### Task 1: Test harness + SPA-serving with graceful fallback

**Files:**
- Modify: `requirements.txt`
- Create: `tests/__init__.py`, `tests/conftest.py`, `tests/test_spa_serving.py`
- Create: `meeting_processor/web/spa_serving.py`
- Modify: `meeting_processor/web/app.py` (imports, root route, `/ui` routes, asset mount)

- [ ] **Step 1: Add pytest to requirements and install**

Append to `requirements.txt`:
```
# Dev/test
pytest>=8.0.0
```
Run: `.venv/bin/pip install "pytest>=8.0.0"`
Expected: pytest installs.

- [ ] **Step 2: Create the test fixture**

Create `tests/__init__.py` (empty).

Create `tests/conftest.py`:
```python
"""Shared pytest fixtures: an isolated config + vault per test."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from meeting_processor.config import load_config
from meeting_processor.web.app import create_app


@pytest.fixture
def config(tmp_path: Path):
    """A Settings object pointed at a throwaway vault/project dir."""
    cfg = load_config()
    cfg.vault_path = tmp_path / "vault"
    (cfg.vault_path / "wiki" / "reunioes").mkdir(parents=True)
    cfg.project_root = str(tmp_path)
    return cfg


@pytest.fixture
def client(config):
    return TestClient(create_app(config))
```
Note: if `Settings` is frozen/immutable, set fields via `cfg.model_copy(update={...})` instead; verify by reading `meeting_processor/config.py` first.

- [ ] **Step 3: Write the failing test for SPA serving + fallback**

Create `tests/test_spa_serving.py`:
```python
def test_root_redirects_to_dashboard_when_build_absent(client):
    # No SPA build exists in the test tree, so / keeps legacy behavior.
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/dashboard"


def test_ui_returns_hint_when_build_absent(client):
    r = client.get("/ui", follow_redirects=False)
    assert r.status_code == 200
    assert "npm run build" in r.text


def test_root_redirects_to_ui_when_build_present(client, monkeypatch, tmp_path):
    from meeting_processor.web import spa_serving

    spa_dir = tmp_path / "spa"
    (spa_dir / "assets").mkdir(parents=True)
    (spa_dir / "index.html").write_text("<!doctype html><title>Meeting Processor</title>")
    monkeypatch.setattr(spa_serving, "SPA_DIR", spa_dir)
    monkeypatch.setattr(spa_serving, "SPA_INDEX", spa_dir / "index.html")

    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/ui"

    r2 = client.get("/ui/meetings", follow_redirects=False)
    assert r2.status_code == 200
    assert "Meeting Processor" in r2.text
```

- [ ] **Step 4: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_spa_serving.py -v`
Expected: FAIL (`/ui` 404, no `spa_serving` module).

- [ ] **Step 5: Create the SPA-serving helper module**

Create `meeting_processor/web/spa_serving.py`:
```python
"""Locate the built SPA and decide whether it is available.

The SPA is an optional build artifact. When it is missing (Node not run),
the app keeps working with the legacy HTMX UI.
"""
from __future__ import annotations

from pathlib import Path

from fastapi.responses import HTMLResponse, FileResponse

WEB_DIR = Path(__file__).parent
SPA_DIR = WEB_DIR / "spa"
SPA_INDEX = SPA_DIR / "index.html"

_MISSING_HTML = (
    "<!doctype html><html><head><meta charset='utf-8'>"
    "<title>Meeting Processor</title></head><body style='font-family:sans-serif;"
    "max-width:40rem;margin:4rem auto;line-height:1.5'>"
    "<h1>SPA build ausente</h1>"
    "<p>O frontend novo ainda não foi compilado. Rode:</p>"
    "<pre>cd frontend && npm install && npm run build</pre>"
    "<p>Enquanto isso, a interface clássica está em "
    "<a href='/dashboard'>/dashboard</a>.</p>"
    "</body></html>"
)


def spa_built() -> bool:
    return SPA_INDEX.exists()


def spa_index_response():
    """Serve the SPA shell (or a build hint if it is missing)."""
    if spa_built():
        return FileResponse(SPA_INDEX)
    return HTMLResponse(_MISSING_HTML, status_code=200)
```

- [ ] **Step 6: Wire SPA routes into `app.py`**

In `meeting_processor/web/app.py`, add to imports (near line 32):
```python
from . import spa_serving
```
Replace the existing root route (lines 478-480):
```python
    @app.get("/", response_class=HTMLResponse)
    async def root_redirect():
        if spa_serving.spa_built():
            return RedirectResponse(url="/ui", status_code=302)
        return RedirectResponse(url="/dashboard", status_code=302)

    @app.get("/ui", response_class=HTMLResponse)
    async def spa_root():
        return spa_serving.spa_index_response()

    @app.get("/ui/{full_path:path}", response_class=HTMLResponse)
    async def spa_catch_all(full_path: str):
        return spa_serving.spa_index_response()
```
In `create_app`, after the existing static mount (line 417), mount the SPA assets when present:
```python
    if spa_serving.SPA_DIR.exists():
        app.mount(
            "/ui/assets",
            StaticFiles(directory=str(spa_serving.SPA_DIR / "assets")),
            name="spa-assets",
        )
```
Note: Vite emits assets under `assets/` with `base:"/ui/"`, so references resolve to `/ui/assets/*`.

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_spa_serving.py -v`
Expected: 3 PASS.

- [ ] **Step 8: Verify the legacy script still passes**

Run: `.venv/bin/python test_web_app.py`
Expected: existing OK lines (root still reaches `/dashboard` in fallback mode).

- [ ] **Step 9: Commit**

```bash
git add requirements.txt tests/__init__.py tests/conftest.py tests/test_spa_serving.py \
        meeting_processor/web/spa_serving.py meeting_processor/web/app.py
git commit -m "feat(web): serve SPA at /ui with graceful fallback"
```

---

### Task 2: Watcher JSON endpoints

**Files:**
- Modify: `meeting_processor/web/app.py` (add 3 routes near the other `/api` routes, ~line 922)
- Create: `tests/test_api_mutations.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_api_mutations.py`:
```python
def test_watcher_start_stop_returns_json(client):
    r = client.post("/api/watcher/start")
    assert r.status_code == 200
    body = r.json()
    assert "ok" in body and "watcher" in body
    assert set(body["watcher"]) >= {"running", "pid", "started_at", "exit_code"}

    r2 = client.post("/api/watcher/stop")
    assert r2.status_code == 200
    assert r2.json()["watcher"]["running"] is False


def test_watcher_restart_returns_json(client):
    r = client.post("/api/watcher/restart")
    assert r.status_code == 200
    assert "watcher" in r.json()
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_api_mutations.py -v`
Expected: FAIL (404 — routes absent).

- [ ] **Step 3: Implement the watcher JSON routes**

In `app.py`, immediately after the `@app.get("/api/watcher")` handler (~line 911), add:
```python
    @app.post("/api/watcher/start")
    async def api_watcher_start():
        result = supervisor.start()
        return {"ok": result["ok"], "error": result.get("error"), "watcher": supervisor.info()}

    @app.post("/api/watcher/stop")
    async def api_watcher_stop():
        result = supervisor.stop()
        return {"ok": result["ok"], "error": result.get("error"), "watcher": supervisor.info()}

    @app.post("/api/watcher/restart")
    async def api_watcher_restart():
        result = supervisor.restart()
        return {"ok": result["ok"], "error": result.get("error"), "watcher": supervisor.info()}
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/test_api_mutations.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add meeting_processor/web/app.py tests/test_api_mutations.py
git commit -m "feat(web): JSON watcher control endpoints"
```

---

### Task 3: LLM provider + config JSON endpoints

**Files:**
- Modify: `meeting_processor/web/app.py` (add routes after Task 2's)
- Modify: `tests/test_api_mutations.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_api_mutations.py`:
```python
def test_set_llm_provider_valid(client):
    r = client.post("/api/llm/provider", json={"provider": "none"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["llm"]["provider"] == "none"


def test_set_llm_provider_invalid_returns_400(client):
    r = client.post("/api/llm/provider", json={"provider": "bogus"})
    assert r.status_code == 400
    assert r.json()["ok"] is False


def test_set_steps_persists(client):
    r = client.post(
        "/api/config/steps",
        json={"summary": True, "note": False, "kanban": True, "wiki": False},
    )
    assert r.status_code == 200
    steps = r.json()["steps"]
    assert steps == {"summary": True, "note": False, "kanban": True, "wiki": False}


def test_set_watch_dir_returns_paths(client, tmp_path):
    target = tmp_path / "videos"
    target.mkdir()
    r = client.post("/api/config/watch-dir", json={"watch_dir": str(target)})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["exists"] is True
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_api_mutations.py -v -k "llm or steps or watch_dir"`
Expected: FAIL (404).

- [ ] **Step 3: Implement the routes**

In `app.py`, after the watcher JSON routes, add. Reuse the existing `_provider_label()` and the `set_*` helpers already imported:
```python
    @app.post("/api/llm/provider")
    async def api_set_provider(payload: dict):
        provider = (payload or {}).get("provider", "")
        result = set_llm_provider(config, provider)
        if not result["ok"]:
            return JSONResponse(
                {"ok": False, "error": result.get("error", "Provedor inválido")},
                status_code=400,
            )
        if supervisor.is_running():
            supervisor.restart()
        return {
            "ok": True,
            "llm": {
                "provider": config.llm_provider,
                "label": _provider_label(),
                "valid_providers": list(VALID_PROVIDERS),
            },
        }

    @app.post("/api/config/watch-dir")
    async def api_set_watch_dir(payload: dict):
        watch_dir = (payload or {}).get("watch_dir", "")
        result = set_watch_dir(config, watch_dir)
        if not result["ok"]:
            return JSONResponse(
                {"ok": False, "error": result.get("error", "Caminho inválido")},
                status_code=400,
            )
        if supervisor.is_running():
            supervisor.restart()
        return {"ok": True, "exists": result["exists"], "watch_dir": config.watch_dir}

    @app.post("/api/config/steps")
    async def api_set_steps(payload: dict):
        p = payload or {}
        set_pipeline_steps(
            config,
            summary=bool(p.get("summary")),
            note=bool(p.get("note")),
            kanban=bool(p.get("kanban")),
            wiki=bool(p.get("wiki")),
        )
        if supervisor.is_running():
            supervisor.restart()
        return {
            "ok": True,
            "steps": {
                "summary": config.enable_summary,
                "note": config.enable_note,
                "kanban": config.enable_kanban,
                "wiki": config.enable_wiki,
            },
        }
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/test_api_mutations.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add meeting_processor/web/app.py tests/test_api_mutations.py
git commit -m "feat(web): JSON endpoints for LLM provider, watch-dir, steps"
```

---

### Task 4: Process + single history-remove JSON endpoints

**Files:**
- Modify: `meeting_processor/web/app.py`
- Modify: `tests/test_api_mutations.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_api_mutations.py`:
```python
def test_process_missing_file_returns_400(client):
    r = client.post("/api/process", json={"file": "/no/such/file.mp4"})
    assert r.status_code == 400
    assert r.json()["ok"] is False


def test_process_existing_file_queues(client, tmp_path, monkeypatch):
    # Stop the real pipeline from running; just assert it gets queued.
    import meeting_processor.web.app as appmod

    started = {"called": False}

    class _FakePipeline:
        def __init__(self, *a, **k): ...
        def process(self, path): started["called"] = True

    monkeypatch.setattr("meeting_processor.pipeline.MeetingPipeline", _FakePipeline, raising=False)

    f = tmp_path / "clip.mp4"
    f.write_bytes(b"x")
    r = client.post("/api/process", json={"file": str(f)})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["queued"] is True
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/pytest tests/test_api_mutations.py -v -k process`
Expected: FAIL (404).

- [ ] **Step 3: Implement the routes**

In `app.py`, after the config routes, add (mirrors the existing `/actions/process` but returns JSON):
```python
    @app.post("/api/process")
    async def api_process(payload: dict):
        file = (payload or {}).get("file", "")
        path = Path(file)
        if not file or not path.exists():
            return JSONResponse(
                {"ok": False, "error": f"Arquivo não encontrado: {file}"},
                status_code=400,
            )

        def _run():
            try:
                from ..pipeline import MeetingPipeline

                MeetingPipeline(config).process(path)
            except Exception:  # noqa: BLE001
                logger.exception("Falha ao processar via API")

        threading.Thread(target=_run, daemon=True).start()
        return {"ok": True, "queued": True, "file": str(path)}

    @app.post("/api/history/remove")
    async def api_history_remove(payload: dict):
        p = payload or {}
        result = _remove_history_entry(
            config.vault_path, p.get("file", ""), p.get("started") or None
        )
        if not result["ok"]:
            return JSONResponse(
                {"ok": False, "error": result.get("error", "Não encontrado")},
                status_code=404,
            )
        return {"ok": True}
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add meeting_processor/web/app.py tests/test_api_mutations.py
git commit -m "feat(web): JSON process + history-remove endpoints"
```

---

## Phase 2 — Frontend scaffold

### Task 5: Vite + Tailwind + TypeScript project

**Files:** create all listed config files under `frontend/`.

- [ ] **Step 1: Create `frontend/package.json`**
```json
{
  "name": "meeting-processor-spa",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run"
  },
  "dependencies": {
    "@dnd-kit/core": "^6.1.0",
    "@dnd-kit/sortable": "^8.0.0",
    "@tanstack/react-query": "^5.51.0",
    "lucide-react": "^0.400.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-markdown": "^9.0.1",
    "react-router-dom": "^6.24.0",
    "remark-gfm": "^4.0.0"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.4.6",
    "@testing-library/react": "^16.0.0",
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "autoprefixer": "^10.4.19",
    "jsdom": "^24.1.0",
    "msw": "^2.3.1",
    "postcss": "^8.4.39",
    "tailwindcss": "^3.4.4",
    "typescript": "^5.5.3",
    "vite": "^5.3.3",
    "vitest": "^2.0.0"
  }
}
```

- [ ] **Step 2: Create `frontend/vite.config.ts`**
```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/ui/",
  plugins: [react()],
  build: {
    outDir: "../meeting_processor/web/spa",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/actions": "http://127.0.0.1:8765",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./vitest.setup.ts",
  },
});
```

- [ ] **Step 3: Create `frontend/tsconfig.json` and `tsconfig.node.json`**

`tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src", "vitest.setup.ts"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```
`tsconfig.node.json`:
```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "noEmit": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 4: Create Tailwind config files**

`frontend/tailwind.config.js`:
```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: "#6366f1", dark: "#4f46e5" },
      },
    },
  },
  plugins: [],
};
```
`frontend/postcss.config.js`:
```js
export default { plugins: { tailwindcss: {}, autoprefixer: {} } };
```

- [ ] **Step 5: Create `frontend/index.html`, `src/styles/index.css`, `vitest.setup.ts`**

`frontend/index.html`:
```html
<!doctype html>
<html lang="pt-br">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Meeting Processor</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```
`frontend/src/styles/index.css`:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root { color-scheme: light dark; }
body { @apply bg-slate-50 text-slate-900 antialiased; }
```
`frontend/vitest.setup.ts`:
```ts
import "@testing-library/jest-dom";
```

- [ ] **Step 6: Install dependencies**

Run: `cd frontend && npm install`
Expected: installs without errors.

- [ ] **Step 7: Commit**
```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts \
        frontend/tsconfig.json frontend/tsconfig.node.json frontend/tailwind.config.js \
        frontend/postcss.config.js frontend/index.html frontend/src/styles/index.css \
        frontend/vitest.setup.ts
git commit -m "chore(spa): scaffold Vite + React + TS + Tailwind"
```

---

### Task 6: API types + typed client (with test)

**Files:**
- Create: `frontend/src/api/types.ts`, `frontend/src/api/client.ts`, `frontend/src/__tests__/client.test.ts`

- [ ] **Step 1: Create `src/api/types.ts`**
```ts
export interface Health {
  status: string; llm_provider: string; vault: string; timestamp: string;
}
export interface Watcher {
  running: boolean; pid: number | null; started_at: string | null; exit_code: number | null;
}
export interface Llm {
  provider: string; label: string; anthropic_model: string; ollama_model: string;
  anthropic_key_set: boolean; valid_providers: string[];
}
export interface MeetingSummary {
  id: string; title: string; created: string; duration: string;
  task_count: number; participants: string; source_file: string;
}
export interface MeetingTask { done: boolean; description: string; }
export interface MeetingDetail {
  id: string; title: string; meta: Record<string, string>;
  resumo_md: string; tasks: MeetingTask[]; transcricao_md: string;
}
export interface Task {
  task_id: string; meeting_id: string; column: string; description: string;
  done: boolean; assignee: string; priority: string; due_date: string; timestamp: string;
}
export interface Steps { summary: boolean; note: boolean; kanban: boolean; wiki: boolean; }
```

- [ ] **Step 2: Write the failing client test**

Create `frontend/src/__tests__/client.test.ts`:
```ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { api, ApiError } from "../api/client";

describe("api client", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("returns parsed JSON on 200", async () => {
    vi.stubGlobal("fetch", vi.fn(async () =>
      new Response(JSON.stringify({ status: "ok" }), { status: 200 })));
    const data = await api.get<{ status: string }>("/api/health");
    expect(data.status).toBe("ok");
  });

  it("throws ApiError with message on non-2xx", async () => {
    vi.stubGlobal("fetch", vi.fn(async () =>
      new Response(JSON.stringify({ error: "bad" }), { status: 400 })));
    await expect(api.post("/api/llm/provider", { provider: "x" }))
      .rejects.toMatchObject({ status: 400, message: "bad" } satisfies Partial<ApiError>);
  });
});
```

- [ ] **Step 3: Run to verify failure**

Run: `cd frontend && npx vitest run src/__tests__/client.test.ts`
Expected: FAIL (no `client` module).

- [ ] **Step 4: Implement `src/api/client.ts`**
```ts
export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const msg = (data && (data.error || data.detail)) || res.statusText;
    throw new ApiError(res.status, msg);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
};
```

- [ ] **Step 5: Run to verify pass**

Run: `cd frontend && npx vitest run src/__tests__/client.test.ts`
Expected: 2 PASS.

- [ ] **Step 6: Commit**
```bash
git add frontend/src/api/types.ts frontend/src/api/client.ts frontend/src/__tests__/client.test.ts
git commit -m "feat(spa): typed API client + types"
```

---

### Task 7: Query client + data hooks

**Files:** Create `frontend/src/lib/queryClient.ts`, `frontend/src/hooks/useApi.ts`

- [ ] **Step 1: Create `src/lib/queryClient.ts`**
```ts
import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});
```

- [ ] **Step 2: Create `src/hooks/useApi.ts` (reads + mutations)**
```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type {
  Health, Watcher, Llm, MeetingSummary, MeetingDetail, Task, Steps,
} from "../api/types";

export const useHealth = () =>
  useQuery({ queryKey: ["health"], queryFn: () => api.get<Health>("/api/health") });

export const useWatcher = () =>
  useQuery({
    queryKey: ["watcher"],
    queryFn: () => api.get<Watcher>("/api/watcher"),
    refetchInterval: 3000,
  });

export const useLlm = () =>
  useQuery({ queryKey: ["llm"], queryFn: () => api.get<Llm>("/api/llm") });

export const useMeetings = () =>
  useQuery({ queryKey: ["meetings"], queryFn: () => api.get<MeetingSummary[]>("/api/meetings") });

export const useMeeting = (id: string) =>
  useQuery({
    queryKey: ["meeting", id],
    queryFn: () => api.get<MeetingDetail>(`/api/meetings/${encodeURIComponent(id)}`),
    enabled: !!id,
  });

export const useTasks = () =>
  useQuery({ queryKey: ["tasks"], queryFn: () => api.get<Task[]>("/api/tasks") });

export function useWatcherControl() {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["watcher"] });
  return {
    start: useMutation({ mutationFn: () => api.post("/api/watcher/start"), onSuccess: invalidate }),
    stop: useMutation({ mutationFn: () => api.post("/api/watcher/stop"), onSuccess: invalidate }),
    restart: useMutation({ mutationFn: () => api.post("/api/watcher/restart"), onSuccess: invalidate }),
  };
}

export function useSetProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (provider: string) => api.post("/api/llm/provider", { provider }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["llm"] }),
  });
}

export function useSetSteps() {
  return useMutation({ mutationFn: (steps: Steps) => api.post("/api/config/steps", steps) });
}

export function useSetWatchDir() {
  return useMutation({ mutationFn: (watch_dir: string) => api.post("/api/config/watch-dir", { watch_dir }) });
}

export function useProcessFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: string) => api.post("/api/process", { file }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["meetings"] }),
  });
}

export function useDeleteMeeting() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.del(`/api/meetings/${encodeURIComponent(id)}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["meetings"] }),
  });
}

export function useMoveTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { task_id: string; meeting_id: string; to_column: string }) =>
      api.post("/actions/tasks/move", v),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tasks"] }),
  });
}
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**
```bash
git add frontend/src/lib/queryClient.ts frontend/src/hooks/useApi.ts
git commit -m "feat(spa): query client + data hooks"
```

---

### Task 8: AppShell, router, shared components

**Files:** Create `main.tsx`, `App.tsx`, and components `AppShell.tsx`, `Sidebar.tsx`, `TopBar.tsx`, `StatusBadge.tsx`, `Card.tsx`, `MarkdownView.tsx`, `EmptyState.tsx`, `ConfirmDialog.tsx`, `Toast.tsx`.

- [ ] **Step 1: Create `src/components/Card.tsx`**
```tsx
import type { ReactNode } from "react";

export function Card({ title, children, actions }: { title?: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
      {(title || actions) && (
        <header className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
          {title && <h2 className="font-semibold text-slate-700">{title}</h2>}
          {actions}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}
```

- [ ] **Step 2: Create `src/components/StatusBadge.tsx`**
```tsx
export function StatusBadge({ on, labelOn, labelOff }: { on: boolean; labelOn: string; labelOff: string }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${
      on ? "bg-emerald-100 text-emerald-700" : "bg-slate-200 text-slate-600"}`}>
      <span className={`h-2 w-2 rounded-full ${on ? "bg-emerald-500" : "bg-slate-400"}`} />
      {on ? labelOn : labelOff}
    </span>
  );
}
```

- [ ] **Step 3: Create `src/components/MarkdownView.tsx`**
```tsx
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function MarkdownView({ children }: { children: string }) {
  return (
    <div className="prose prose-slate max-w-none prose-headings:font-semibold prose-pre:bg-slate-100">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children || "_Sem conteúdo._"}</ReactMarkdown>
    </div>
  );
}
```
Note: `prose` classes work without the typography plugin (basic spacing). Optionally add `@tailwindcss/typography` later; not required.

- [ ] **Step 4: Create `src/components/EmptyState.tsx`**
```tsx
import type { ReactNode } from "react";

export function EmptyState({ icon, title, hint }: { icon?: ReactNode; title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center gap-2 py-12 text-center text-slate-500">
      {icon}
      <p className="font-medium">{title}</p>
      {hint && <p className="text-sm">{hint}</p>}
    </div>
  );
}
```

- [ ] **Step 5: Create `src/components/Toast.tsx` (context + hook)**
```tsx
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

type Toast = { id: number; kind: "ok" | "err"; msg: string };
const ToastCtx = createContext<(kind: Toast["kind"], msg: string) => void>(() => {});

export function useToast() { return useContext(ToastCtx); }

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((kind: Toast["kind"], msg: string) => {
    const id = Date.now() + Math.random();
    setItems((p) => [...p, { id, kind, msg }]);
    setTimeout(() => setItems((p) => p.filter((t) => t.id !== id)), 4000);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
        {items.map((t) => (
          <div key={t.id} className={`rounded-lg px-4 py-2 text-sm text-white shadow-lg ${
            t.kind === "ok" ? "bg-emerald-600" : "bg-rose-600"}`}>{t.msg}</div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}
```

- [ ] **Step 6: Create `src/components/ConfirmDialog.tsx`**
```tsx
export function ConfirmDialog({ open, title, onConfirm, onCancel }: {
  open: boolean; title: string; onConfirm: () => void; onCancel: () => void;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={onCancel}>
      <div className="w-80 rounded-xl bg-white p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <p className="mb-4 font-medium text-slate-800">{title}</p>
        <div className="flex justify-end gap-2">
          <button className="rounded-lg px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100" onClick={onCancel}>Cancelar</button>
          <button className="rounded-lg bg-rose-600 px-3 py-1.5 text-sm text-white hover:bg-rose-700" onClick={onConfirm}>Confirmar</button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 7: Create `src/components/Sidebar.tsx`**
```tsx
import { NavLink } from "react-router-dom";
import { LayoutDashboard, Video, KanbanSquare, Settings } from "lucide-react";

const links = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/meetings", label: "Reuniões", icon: Video, end: false },
  { to: "/tasks", label: "Tarefas", icon: KanbanSquare, end: false },
  { to: "/settings", label: "Configuração", icon: Settings, end: false },
];

export function Sidebar() {
  return (
    <aside className="flex w-56 flex-col gap-1 border-r border-slate-200 bg-white p-3">
      <div className="mb-4 px-2 text-lg font-bold text-brand">Meeting Processor</div>
      {links.map(({ to, label, icon: Icon, end }) => (
        <NavLink key={to} to={to} end={end} className={({ isActive }) =>
          `flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium ${
            isActive ? "bg-brand/10 text-brand" : "text-slate-600 hover:bg-slate-100"}`}>
          <Icon size={18} /> {label}
        </NavLink>
      ))}
    </aside>
  );
}
```

- [ ] **Step 8: Create `src/components/TopBar.tsx`**
```tsx
import { useHealth, useWatcher } from "../hooks/useApi";
import { StatusBadge } from "./StatusBadge";

export function TopBar() {
  const health = useHealth();
  const watcher = useWatcher();
  return (
    <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3">
      <div className="text-sm text-slate-500">
        LLM: <span className="font-medium text-slate-700">{health.data?.llm_provider ?? "—"}</span>
      </div>
      <StatusBadge on={!!watcher.data?.running} labelOn="Watcher ativo" labelOff="Watcher offline" />
    </header>
  );
}
```

- [ ] **Step 9: Create `src/components/AppShell.tsx`**
```tsx
import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

export function AppShell() {
  return (
    <div className="flex h-screen">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar />
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
```

- [ ] **Step 10: Create `src/App.tsx`**
```tsx
import { Routes, Route } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { Dashboard } from "./pages/Dashboard";
import { Meetings } from "./pages/Meetings";
import { MeetingDetail } from "./pages/MeetingDetail";
import { Tasks } from "./pages/Tasks";
import { Settings } from "./pages/Settings";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Dashboard />} />
        <Route path="meetings" element={<Meetings />} />
        <Route path="meetings/:id" element={<MeetingDetail />} />
        <Route path="tasks" element={<Tasks />} />
        <Route path="settings" element={<Settings />} />
      </Route>
    </Routes>
  );
}
```

- [ ] **Step 11: Create `src/main.tsx`**
```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "./lib/queryClient";
import { ToastProvider } from "./components/Toast";
import App from "./App";
import "./styles/index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename="/ui">
        <ToastProvider>
          <App />
        </ToastProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
```

- [ ] **Step 12: Add placeholder pages so it compiles, then typecheck**

Create stub files (replaced in Phase 3) for `pages/Dashboard.tsx`, `Meetings.tsx`, `MeetingDetail.tsx`, `Tasks.tsx`, `Settings.tsx`, each:
```tsx
export function Dashboard() { return <div />; }
```
(rename the export per file: `Meetings`, `MeetingDetail`, `Tasks`, `Settings`).

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 13: Commit**
```bash
git add frontend/src/main.tsx frontend/src/App.tsx frontend/src/components frontend/src/pages
git commit -m "feat(spa): app shell, router, shared components"
```

---

## Phase 3 — Pages

### Task 9: Dashboard page

**Files:** Replace `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: Implement Dashboard**
```tsx
import { useState } from "react";
import { Link } from "react-router-dom";
import { Play, Square, RotateCw, FileVideo } from "lucide-react";
import { Card } from "../components/Card";
import { StatusBadge } from "../components/StatusBadge";
import { EmptyState } from "../components/EmptyState";
import { useToast } from "../components/Toast";
import { useHealth, useWatcher, useMeetings, useWatcherControl, useProcessFile } from "../hooks/useApi";
import { ApiError } from "../api/client";

export function Dashboard() {
  const health = useHealth();
  const watcher = useWatcher();
  const meetings = useMeetings();
  const { start, stop, restart } = useWatcherControl();
  const process = useProcessFile();
  const toast = useToast();
  const [file, setFile] = useState("");

  const submit = () => {
    if (!file.trim()) return;
    process.mutate(file.trim(), {
      onSuccess: () => { toast("ok", "Processamento enfileirado."); setFile(""); },
      onError: (e) => toast("err", e instanceof ApiError ? e.message : "Erro"),
    });
  };

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card title="Status">
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <span className="text-slate-600">Watcher</span>
            <StatusBadge on={!!watcher.data?.running} labelOn={`ativo (pid ${watcher.data?.pid})`} labelOff="offline" />
          </div>
          <div className="flex items-center justify-between">
            <span className="text-slate-600">Provedor LLM</span>
            <span className="font-medium">{health.data?.llm_provider ?? "—"}</span>
          </div>
          <div className="mt-2 flex gap-2">
            <button onClick={() => start.mutate()} className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-sm text-white hover:bg-emerald-700"><Play size={15}/> Iniciar</button>
            <button onClick={() => stop.mutate()} className="flex items-center gap-1.5 rounded-lg bg-slate-600 px-3 py-1.5 text-sm text-white hover:bg-slate-700"><Square size={15}/> Parar</button>
            <button onClick={() => restart.mutate()} className="flex items-center gap-1.5 rounded-lg bg-slate-200 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-300"><RotateCw size={15}/> Reiniciar</button>
          </div>
        </div>
      </Card>

      <Card title="Processar um arquivo">
        <div className="flex flex-col gap-2">
          <label className="text-sm text-slate-600">Caminho do vídeo no disco</label>
          <input value={file} onChange={(e) => setFile(e.target.value)}
            placeholder="/Users/voce/Videos/reuniao.mp4"
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm" />
          <button onClick={submit} disabled={process.isPending}
            className="flex items-center justify-center gap-1.5 rounded-lg bg-brand px-3 py-2 text-sm text-white hover:bg-brand-dark disabled:opacity-50">
            <FileVideo size={15}/> {process.isPending ? "Enviando…" : "Processar"}
          </button>
        </div>
      </Card>

      <div className="lg:col-span-2">
        <Card title="Reuniões recentes">
          {meetings.data && meetings.data.length > 0 ? (
            <ul className="divide-y divide-slate-100">
              {meetings.data.slice(0, 5).map((m) => (
                <li key={m.id} className="py-2">
                  <Link to={`/meetings/${encodeURIComponent(m.id)}`} className="flex items-center justify-between hover:text-brand">
                    <span className="truncate">{m.title}</span>
                    <span className="ml-3 shrink-0 text-xs text-slate-400">{m.task_count} tarefas</span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="Nenhuma reunião ainda" hint="Processe um arquivo para começar." />
          )}
        </Card>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**
```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat(spa): dashboard page"
```

---

### Task 10: Meetings list + delete

**Files:** Replace `frontend/src/pages/Meetings.tsx`

- [ ] **Step 1: Implement Meetings**
```tsx
import { useState } from "react";
import { Link } from "react-router-dom";
import { Trash2, Search } from "lucide-react";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import { useMeetings, useDeleteMeeting } from "../hooks/useApi";
import { ApiError } from "../api/client";

export function Meetings() {
  const meetings = useMeetings();
  const del = useDeleteMeeting();
  const toast = useToast();
  const [q, setQ] = useState("");
  const [pending, setPending] = useState<string | null>(null);

  const items = (meetings.data ?? []).filter((m) => m.title.toLowerCase().includes(q.toLowerCase()));

  const confirmDelete = () => {
    if (!pending) return;
    del.mutate(pending, {
      onSuccess: () => toast("ok", "Reunião apagada."),
      onError: (e) => toast("err", e instanceof ApiError ? e.message : "Erro"),
    });
    setPending(null);
  };

  return (
    <Card title="Reuniões" actions={
      <div className="flex items-center gap-1.5 rounded-lg border border-slate-300 px-2">
        <Search size={15} className="text-slate-400" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar…"
          className="py-1.5 text-sm outline-none" />
      </div>
    }>
      {items.length > 0 ? (
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase text-slate-400">
            <tr><th className="py-2">Título</th><th>Data</th><th>Duração</th><th>Tarefas</th><th></th></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {items.map((m) => (
              <tr key={m.id} className="hover:bg-slate-50">
                <td className="py-2"><Link to={`/meetings/${encodeURIComponent(m.id)}`} className="font-medium hover:text-brand">{m.title}</Link></td>
                <td className="text-slate-500">{m.created || "—"}</td>
                <td className="text-slate-500">{m.duration || "—"}</td>
                <td className="text-slate-500">{m.task_count}</td>
                <td className="text-right">
                  <button onClick={() => setPending(m.id)} className="text-slate-400 hover:text-rose-600"><Trash2 size={16} /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <EmptyState title="Nenhuma reunião encontrada" />
      )}
      <ConfirmDialog open={!!pending} title="Apagar esta reunião?" onConfirm={confirmDelete} onCancel={() => setPending(null)} />
    </Card>
  );
}
```

- [ ] **Step 2: Typecheck + commit**

Run: `cd frontend && npx tsc -b --noEmit`  (Expected: no errors)
```bash
git add frontend/src/pages/Meetings.tsx
git commit -m "feat(spa): meetings list + delete"
```

---

### Task 11: Meeting detail (tabs + markdown) with test

**Files:** Replace `frontend/src/pages/MeetingDetail.tsx`; create `frontend/src/__tests__/meetingDetail.test.tsx`

- [ ] **Step 1: Write the failing render test**

Create `frontend/src/__tests__/meetingDetail.test.tsx`:
```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { MeetingDetail } from "../pages/MeetingDetail";

function setup() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/meetings/abc"]}>
        <Routes><Route path="/meetings/:id" element={<MeetingDetail />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("MeetingDetail", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      id: "abc", title: "abc", meta: {}, resumo_md: "# Resumo aqui",
      tasks: [{ done: false, description: "Tarefa 1" }], transcricao_md: "linha de transcrição",
    }), { status: 200 })));
  });

  it("shows summary by default and switches to transcript tab", async () => {
    setup();
    expect(await screen.findByText("Resumo aqui")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Transcrição/i }));
    expect(await screen.findByText(/linha de transcrição/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npx vitest run src/__tests__/meetingDetail.test.tsx`
Expected: FAIL (stub page renders empty `<div/>`).

- [ ] **Step 3: Implement MeetingDetail**
```tsx
import { useState } from "react";
import { useParams } from "react-router-dom";
import { Card } from "../components/Card";
import { MarkdownView } from "../components/MarkdownView";
import { useMeeting } from "../hooks/useApi";

type Tab = "summary" | "tasks" | "transcript";

export function MeetingDetail() {
  const { id = "" } = useParams();
  const meeting = useMeeting(id);
  const [tab, setTab] = useState<Tab>("summary");

  const obsidianUri = `obsidian://open?path=${encodeURIComponent(id)}`;
  const tabs: { key: Tab; label: string }[] = [
    { key: "summary", label: "Resumo" },
    { key: "tasks", label: "Tarefas" },
    { key: "transcript", label: "Transcrição" },
  ];

  if (meeting.isLoading) return <p className="text-slate-500">Carregando…</p>;
  if (meeting.isError || !meeting.data) return <p className="text-rose-600">Reunião não encontrada.</p>;
  const d = meeting.data;

  return (
    <Card title={d.title} actions={
      <a href={obsidianUri} className="text-sm text-brand hover:underline">Abrir no Obsidian</a>
    }>
      <div className="mb-4 flex gap-1 border-b border-slate-200">
        {tabs.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${
              tab === t.key ? "border-brand text-brand" : "border-transparent text-slate-500 hover:text-slate-700"}`}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === "summary" && <MarkdownView>{d.resumo_md}</MarkdownView>}
      {tab === "transcript" && <MarkdownView>{d.transcricao_md}</MarkdownView>}
      {tab === "tasks" && (
        <ul className="space-y-1">
          {d.tasks.length === 0 && <li className="text-slate-500">Sem tarefas.</li>}
          {d.tasks.map((t, i) => (
            <li key={i} className="flex items-center gap-2">
              <input type="checkbox" checked={t.done} readOnly />
              <span className={t.done ? "text-slate-400 line-through" : ""}>{t.description}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
```

- [ ] **Step 4: Run to verify pass**

Run: `cd frontend && npx vitest run src/__tests__/meetingDetail.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add frontend/src/pages/MeetingDetail.tsx frontend/src/__tests__/meetingDetail.test.tsx
git commit -m "feat(spa): meeting detail with tabs + markdown"
```

---

### Task 12: Tasks Kanban (dnd-kit) with move test

**Files:** Replace `frontend/src/pages/Tasks.tsx`; create `frontend/src/__tests__/tasks.test.tsx`

- [ ] **Step 1: Write the failing test (move calls the API)**

Create `frontend/src/__tests__/tasks.test.tsx`:
```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "../components/Toast";
import { Tasks } from "../pages/Tasks";

function setup() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider><Tasks /></ToastProvider>
    </QueryClientProvider>,
  );
}

describe("Tasks Kanban", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify([
      { task_id: "t1", meeting_id: "m1", column: "A Fazer", description: "Fazer X",
        done: false, assignee: "Ana", priority: "", due_date: "", timestamp: "" },
    ]), { status: 200 })));
  });

  it("renders columns and a task card", async () => {
    setup();
    expect(await screen.findByText("Fazer X")).toBeInTheDocument();
    expect(screen.getByText("A Fazer")).toBeInTheDocument();
    expect(screen.getByText("Concluído")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd frontend && npx vitest run src/__tests__/tasks.test.tsx`
Expected: FAIL (stub renders empty).

- [ ] **Step 3: Implement Tasks (Kanban with drag-and-drop + export)**
```tsx
import { useMemo, useState, useEffect } from "react";
import { DndContext, type DragEndEvent, PointerSensor, useSensor, useSensors } from "@dnd-kit/core";
import { useDroppable, useDraggable } from "@dnd-kit/core";
import { Download } from "lucide-react";
import { Card } from "../components/Card";
import { useTasks, useMoveTask } from "../hooks/useApi";
import { useToast } from "../components/Toast";
import type { Task } from "../api/types";
import { ApiError } from "../api/client";

const COLUMNS = ["A Fazer", "Em Progresso", "Concluído"];

function TaskCard({ task }: { task: Task }) {
  const { attributes, listeners, setNodeRef, transform } = useDraggable({ id: task.task_id, data: task });
  const style = transform ? { transform: `translate(${transform.x}px, ${transform.y}px)` } : undefined;
  return (
    <div ref={setNodeRef} style={style} {...listeners} {...attributes}
      className="cursor-grab rounded-lg border border-slate-200 bg-white p-3 text-sm shadow-sm active:cursor-grabbing">
      <p className="font-medium text-slate-700">{task.description}</p>
      {task.assignee && <p className="mt-1 text-xs text-slate-400">{task.assignee}</p>}
    </div>
  );
}

function Column({ name, tasks }: { name: string; tasks: Task[] }) {
  const { setNodeRef, isOver } = useDroppable({ id: name });
  return (
    <div ref={setNodeRef} className={`flex-1 rounded-xl p-3 ${isOver ? "bg-brand/10" : "bg-slate-100"}`}>
      <h3 className="mb-3 flex items-center justify-between text-sm font-semibold text-slate-600">
        {name} <span className="rounded-full bg-white px-2 text-xs text-slate-400">{tasks.length}</span>
      </h3>
      <div className="flex flex-col gap-2">
        {tasks.map((t) => <TaskCard key={t.task_id} task={t} />)}
      </div>
    </div>
  );
}

export function Tasks() {
  const query = useTasks();
  const move = useMoveTask();
  const toast = useToast();
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));
  const [local, setLocal] = useState<Task[]>([]);
  useEffect(() => { if (query.data) setLocal(query.data); }, [query.data]);

  const byColumn = useMemo(() => {
    const map: Record<string, Task[]> = {};
    for (const c of COLUMNS) map[c] = [];
    for (const t of local) (map[t.column] ?? (map[t.column] = [])).push(t);
    return map;
  }, [local]);

  const onDragEnd = (e: DragEndEvent) => {
    const task = e.active.data.current as Task | undefined;
    const to = e.over?.id as string | undefined;
    if (!task || !to || to === task.column) return;
    setLocal((prev) => prev.map((t) => t.task_id === task.task_id ? { ...t, column: to } : t)); // optimistic
    move.mutate(
      { task_id: task.task_id, meeting_id: task.meeting_id, to_column: to },
      {
        onError: (err) => {
          setLocal((prev) => prev.map((t) => t.task_id === task.task_id ? { ...t, column: task.column } : t));
          toast("err", err instanceof ApiError ? err.message : "Falha ao mover");
        },
      },
    );
  };

  return (
    <Card title="Tarefas (Kanban)" actions={
      <div className="flex gap-1 text-xs">
        {["csv", "json", "md", "txt"].map((ext) => (
          <a key={ext} href={`/api/tasks/export.${ext}`}
            className="flex items-center gap-1 rounded border border-slate-300 px-2 py-1 text-slate-600 hover:bg-slate-100">
            <Download size={12} /> {ext.toUpperCase()}
          </a>
        ))}
      </div>
    }>
      <DndContext sensors={sensors} onDragEnd={onDragEnd}>
        <div className="flex gap-4">
          {COLUMNS.map((c) => <Column key={c} name={c} tasks={byColumn[c] ?? []} />)}
        </div>
      </DndContext>
    </Card>
  );
}
```
Note: the column names match the backend `kanban_columns` labels in `config.yaml` ("A Fazer" / "Em Progresso" / "Concluído"), which is what `Task.column` contains.

- [ ] **Step 4: Run to verify pass**

Run: `cd frontend && npx vitest run src/__tests__/tasks.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add frontend/src/pages/Tasks.tsx frontend/src/__tests__/tasks.test.tsx
git commit -m "feat(spa): kanban board with drag-to-move + export"
```

---

### Task 13: Settings page

**Files:** Replace `frontend/src/pages/Settings.tsx`

- [ ] **Step 1: Implement Settings**
```tsx
import { useEffect, useState } from "react";
import { Card } from "../components/Card";
import { useToast } from "../components/Toast";
import { useLlm, useSetProvider, useSetWatchDir, useSetSteps } from "../hooks/useApi";
import { ApiError } from "../api/client";
import type { Steps } from "../api/types";

export function Settings() {
  const llm = useLlm();
  const setProvider = useSetProvider();
  const setWatchDir = useSetWatchDir();
  const setSteps = useSetSteps();
  const toast = useToast();

  const [watchDir, setWatchDirValue] = useState("");
  const [steps, setStepsValue] = useState<Steps>({ summary: true, note: true, kanban: true, wiki: true });
  useEffect(() => { /* provider comes from llm query; steps default true */ }, [llm.data]);

  const onError = (e: unknown) => toast("err", e instanceof ApiError ? e.message : "Erro");

  return (
    <div className="grid max-w-2xl gap-6">
      <Card title="Provedor LLM">
        <select value={llm.data?.provider ?? ""} disabled={!llm.data}
          onChange={(e) => setProvider.mutate(e.target.value, {
            onSuccess: () => toast("ok", "Provedor atualizado."), onError })}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm">
          {(llm.data?.valid_providers ?? []).map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
      </Card>

      <Card title="Pasta monitorada">
        <div className="flex gap-2">
          <input value={watchDir} onChange={(e) => setWatchDirValue(e.target.value)}
            placeholder="~/Videos/OBS" className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm" />
          <button onClick={() => setWatchDir.mutate(watchDir, {
            onSuccess: (r: any) => toast("ok", r?.exists ? "Pasta salva." : "Salva (pasta ainda não existe)."), onError })}
            className="rounded-lg bg-brand px-3 py-2 text-sm text-white hover:bg-brand-dark">Salvar</button>
        </div>
      </Card>

      <Card title="Etapas do processamento">
        <div className="flex flex-col gap-2">
          {(["summary", "note", "kanban", "wiki"] as const).map((k) => (
            <label key={k} className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={steps[k]}
                onChange={(e) => setStepsValue((s) => ({ ...s, [k]: e.target.checked }))} />
              {k}
            </label>
          ))}
          <button onClick={() => setSteps.mutate(steps, { onSuccess: () => toast("ok", "Etapas salvas."), onError })}
            className="mt-2 w-fit rounded-lg bg-brand px-3 py-2 text-sm text-white hover:bg-brand-dark">Salvar etapas</button>
        </div>
      </Card>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck + run full frontend suite**

Run: `cd frontend && npx tsc -b --noEmit && npx vitest run`
Expected: typecheck clean, all tests PASS.

- [ ] **Step 3: Commit**
```bash
git add frontend/src/pages/Settings.tsx
git commit -m "feat(spa): settings page"
```

---

## Phase 4 — Build integration, docs, verification

### Task 14: Build wiring, gitignore, docs, manual smoke test

**Files:** Modify `.gitignore`, `README.md`; create `docs/frontend-spa.md`

- [ ] **Step 1: Ignore the build artifact**

Append to `.gitignore`:
```
# SPA build output (run `cd frontend && npm run build`)
meeting_processor/web/spa/
```

- [ ] **Step 2: Build the SPA**

Run: `cd frontend && npm run build`
Expected: emits `meeting_processor/web/spa/index.html` and `meeting_processor/web/spa/assets/*`.

- [ ] **Step 3: Verify backend serves the built SPA**

Run the server in the background and probe it:
```bash
.venv/bin/python -m meeting_processor web --port 8799 &
sleep 4
/usr/bin/curl -s -o /dev/null -w "%{http_code}\n" -L http://127.0.0.1:8799/        # expect 200
/usr/bin/curl -s -L http://127.0.0.1:8799/ | grep -o "<title>.*</title>"           # expect Meeting Processor
/usr/bin/curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8799/ui/assets/ # assets mounted (403/200, not 404)
kill %1
```
Expected: `/` → 200 serving the SPA, title present.

- [ ] **Step 4: Full backend test run**

Run: `.venv/bin/pytest tests/ -v && .venv/bin/python test_web_app.py`
Expected: all green.

- [ ] **Step 5: Write `docs/frontend-spa.md`**
```markdown
# Frontend SPA (React)

A modern single-page interface served at `/` (redirects to `/ui`).

## Develop
```bash
cd frontend
npm install
npm run dev        # Vite on http://localhost:5173, proxies /api to :8765
# in another terminal:
.venv/bin/python -m meeting_processor web
```

## Build for normal use
```bash
cd frontend && npm run build      # outputs to meeting_processor/web/spa/
.venv/bin/python -m meeting_processor web   # serves the SPA at http://127.0.0.1:8765/
```

If the SPA build is absent, `/` falls back to the classic HTMX UI at `/dashboard`.
```

- [ ] **Step 6: Link from README**

Under the README section that mentions the web frontend, add:
```markdown
- Interface moderna (React SPA): veja [`docs/frontend-spa.md`](docs/frontend-spa.md).
```

- [ ] **Step 7: Commit**
```bash
git add .gitignore docs/frontend-spa.md README.md
git commit -m "docs(spa): build instructions + gitignore build artifact"
```

- [ ] **Step 8: Manual verification checklist**

With `npm run build` done and `python -m meeting_processor web` running, open `http://127.0.0.1:8765/` and confirm:
- Dashboard loads; watcher Start/Stop flips the badge within ~3s.
- Process-a-file with a real path enqueues (toast appears).
- Meetings list shows processed meetings; delete works with confirm.
- Meeting detail switches Summary/Tasks/Transcript; markdown renders.
- Tasks board shows columns; dragging a card moves it and persists after refresh.
- Settings changes provider and shows a success toast.

---

## Self-Review

**Spec coverage:**
- §3 SPA serving/fallback → Task 1. §4 mutation endpoints → Tasks 2-4 (delete/clear/move reuse existing JSON, noted). §5 reads → Task 6 types + Task 7 hooks. §6 structure → Tasks 5-8. §7 pages → Tasks 9-13. §8 data flow/polling → Task 7 (`refetchInterval`) + optimistic move in Task 12. §9 error handling → `ApiError` (Task 6) + toasts (Task 8) + fallback (Task 1). §10 build/run → Task 14. §11 testing → backend Tasks 1-4, frontend Tasks 6/11/12. §12 out-of-scope respected (process stays path-based).
- All spec sections map to tasks. No gaps.

**Placeholder scan:** No "TBD/TODO"; every code step shows complete code. The `useEffect` in Settings is intentionally empty (provider is read from the query); left as a no-op comment, not a placeholder for required logic.

**Type consistency:** `Task.column` values ("A Fazer"/"Em Progresso"/"Concluído") match `COLUMNS` in Task 12 and backend `config.yaml`. Hook names (`useWatcherControl`, `useMoveTask`, `useProcessFile`, `useDeleteMeeting`) are defined in Task 7 and used unchanged in Tasks 9-13. `api.get/post/del` signatures match usage. `ApiError` shape (`status`, `message`) matches the client test and page error handlers.

**Risk note for implementer:** Task 2 (`conftest.py`) assumes `Settings` fields are mutable. Before Task 1 Step 2, open `meeting_processor/config.py`; if `Settings` is a frozen pydantic model, build the fixture with `load_config().model_copy(update={...})` and adjust `set_*` helpers' expectations accordingly.
