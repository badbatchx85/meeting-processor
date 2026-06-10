# Summary Style (time-windowed vs plain) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Choose between time-windowed and plain summaries — a global default in Settings plus a per-summarization choice on "Gerar resumo".

**Architecture:** A `summary_style` config; `summarize(..., style=None)` appends a "return empty time_windows" directive in plain mode (the note already hides the empty section); the `style` threads through `_summarize`/`summarize_existing`/the summarize endpoint; Settings radio (global) + a MeetingDetail `<select>` (per-meeting).

**Tech Stack:** Python 3.14, Pydantic, FastAPI; React/Vite/Vitest.

Run Python tests with `.venv/bin/python -m pytest`; frontend from `frontend/` with `npx vitest run <file>` + `npx tsc --noEmit`. The pre-existing `test_summarizer_mock.py::test_factory_selects_anthropic` failure (no `ANTHROPIC_API_KEY`) is unrelated.

---

## File Structure
- **Modify** `meeting_processor/config.py` — `summary_style` field + env.
- **Modify** `meeting_processor/summarizer.py` — `summarize(style=)` + plain directive (+ Protocol sig).
- **Modify** `meeting_processor/pipeline.py` — `style` through `_summarize` + `summarize_existing`.
- **Modify** `meeting_processor/web/runtime.py` — `set_summary_style`.
- **Modify** `meeting_processor/web/app.py` — `/api/config` field, `/api/config/summary-style`, summarize `style` body.
- **Modify** `frontend/src/api/types.ts`, `frontend/src/hooks/useApi.ts`, `frontend/src/pages/Settings.tsx`, `frontend/src/pages/MeetingDetail.tsx`.
- **Create** `tests/test_summary_style.py`, `frontend/src/__tests__/summaryStyle.test.tsx`.

---

### Task 1: Config + summarizer plain directive

**Files:** Modify `meeting_processor/config.py`, `meeting_processor/summarizer.py`; Create `tests/test_summary_style.py`.

- [ ] **Step 1: Write the failing tests** — create `tests/test_summary_style.py`:

```python
"""Estilo do resumo: timeline (com períodos) vs plain (sem períodos)."""
import json

from meeting_processor.models import Transcript, TranscriptSegment
from meeting_processor.summarizer import _BaseSummarizer


class _StyleFake(_BaseSummarizer):
    provider_name = "fake"

    def __init__(self, config):
        super().__init__(config)
        self.captured: list[str] = []

    def _call_llm(self, system_prompt, user_prompt):
        self.captured.append(system_prompt)
        return json.dumps({
            "executive_summary": "x", "time_windows": [], "action_items": [],
            "participants": [], "key_topics": [],
        })


def _tiny():
    s = TranscriptSegment(start=0.0, end=1.0, text="oi")
    return Transcript(segments=[s], full_text="oi", language="pt", duration=1.0)


def test_plain_style_adds_directive(config):
    f = _StyleFake(config)
    f.summarize(_tiny(), "a.mp4", style="plain")
    assert "MODO RESUMO SIMPLES" in f.captured[0]


def test_timeline_style_no_directive(config):
    f = _StyleFake(config)
    f.summarize(_tiny(), "a.mp4", style="timeline")
    assert "MODO RESUMO SIMPLES" not in f.captured[0]


def test_style_defaults_to_config(config):
    config.summary_style = "plain"
    f = _StyleFake(config)
    f.summarize(_tiny(), "a.mp4")
    assert "MODO RESUMO SIMPLES" in f.captured[0]
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_summary_style.py -q`
Expected: FAIL — `summarize()` rejects `style=` (unexpected kwarg) and `config` has no `summary_style`.

- [ ] **Step 3: Add the config field.** In `meeting_processor/config.py`, add near `summary_chunk_minutes` (the "Comum a todos os provedores" block):

```python
    # Estilo do resumo: "timeline" (com blocos de tempo) ou "plain" (sem).
    summary_style: str = "timeline"
```

And in `string_overrides` (in `load_config`), add:

```python
        "MEETING_SUMMARY_STYLE": "summary_style",
```

- [ ] **Step 4: Thread `style` into `summarize`.** In `meeting_processor/summarizer.py`:
  - Update the `SummarizerProtocol.summarize` stub signature to
    `def summarize(self, transcript: Transcript, source_filename: str, style: str | None = None) -> MeetingSummary: ...`.
  - Change `_BaseSummarizer.summarize` signature to
    `def summarize(self, transcript: Transcript, source_filename: str, style: str | None = None) -> MeetingSummary:`
  - After the `system_prompt = SYSTEM_PROMPT.replace("{chunk_minutes}", ...)` block and before the `if self._estimate_tokens(...)` branch, insert:

    ```python
        effective_style = (style or self.config.summary_style or "timeline")
        if effective_style == "plain":
            system_prompt += (
                "\n\nMODO RESUMO SIMPLES: NÃO segmente o resumo por blocos de "
                'tempo — retorne "time_windows": [] (lista vazia).'
            )
    ```

- [ ] **Step 5: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_summary_style.py tests/test_summary_chunking.py -q`
Expected: PASS (3 new + chunking suite — default `style=None`/`timeline` keeps the prompt unchanged).

- [ ] **Step 6: Commit**

```bash
git add meeting_processor/config.py meeting_processor/summarizer.py tests/test_summary_style.py
git commit -m "feat(summary): plain style directive (no time windows)"
```

---

### Task 2: Pipeline threading

**Files:** Modify `meeting_processor/pipeline.py` (`_summarize`, `summarize_existing`); Test: `tests/test_summary_style.py`.

- [ ] **Step 1: Append the failing test:**

```python
# --- Task 2: pipeline threads style ----------------------------------------

from datetime import datetime
from meeting_processor.models import MeetingSummary
from meeting_processor.pipeline import MeetingPipeline


class _CapSumm:
    def __init__(self):
        self.style = "UNSET"
    def summarize(self, transcript, source_file, style=None):
        self.style = style
        return MeetingSummary(executive_summary="x", time_windows=[], action_items=[],
                              participants=[], key_topics=[])


def test_summarize_forwards_style(config):
    pipe = MeetingPipeline(config)
    fake = _CapSumm()
    pipe.summarizer = fake   # pre-set so _summarize won't construct a real one
    paths = pipe.note_generator.prepare("x.mp4", datetime.now())
    job = pipe.dashboard.new_job("x.mp4")
    pipe._summarize(_tiny(), paths, "x.mp4", datetime.now(), job,
                    {"summary": True, "note": False, "kanban": False, "wiki": False},
                    style="plain")
    assert fake.style == "plain"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_summary_style.py -k forwards_style -q`
Expected: FAIL — `_summarize` got an unexpected keyword argument `style`.

- [ ] **Step 3: Add `style` to `_summarize`.** In `meeting_processor/pipeline.py`, change the signature:

```python
    def _summarize(self, transcript, paths, source_file, created_at, job, steps):
```

to:

```python
    def _summarize(self, transcript, paths, source_file, created_at, job, steps, style=None):
```

and change its summarizer call:

```python
            summary = self.summarizer.summarize(transcript, source_file)
```

to:

```python
            summary = self.summarizer.summarize(transcript, source_file, style=style)
```

- [ ] **Step 4: Thread `style` through `summarize_existing`.** Change the signature:

```python
    def summarize_existing(self, meeting_id: str, job_started=None, cancel_event=None) -> None:
```

to:

```python
    def summarize_existing(self, meeting_id: str, job_started=None, cancel_event=None, style=None) -> None:
```

and its `_summarize` call:

```python
            self._summarize(transcript, paths, meeting_id, created_at, job, steps)
```

to:

```python
            self._summarize(transcript, paths, meeting_id, created_at, job, steps, style=style)
```

(`process()` calls `_summarize(...)` with no `style` → `None` → the summarizer uses `config.summary_style`. Unchanged.)

- [ ] **Step 5: Run tests + regression**

Run: `.venv/bin/python -m pytest tests/test_summary_style.py tests/test_stuck_jobs.py -q`
Expected: PASS (the threading test + the pipeline/stuck-jobs suite — `process()` still works with the default).

- [ ] **Step 6: Commit**

```bash
git add meeting_processor/pipeline.py tests/test_summary_style.py
git commit -m "feat(summary): thread style through _summarize + summarize_existing"
```

---

### Task 3: Backend endpoints

**Files:** Modify `meeting_processor/web/runtime.py`, `meeting_processor/web/app.py`; Test: `tests/test_summary_style.py`.

- [ ] **Step 1: Append the failing tests:**

```python
# --- Task 3: backend endpoints ---------------------------------------------

import threading
from meeting_processor.web.runtime import set_summary_style


def test_set_summary_style_normalizes(config, monkeypatch):
    monkeypatch.delenv("MEETING_SUMMARY_STYLE", raising=False)
    set_summary_style(config, "plain")
    assert config.summary_style == "plain"
    set_summary_style(config, "lixo")     # invalid → timeline
    assert config.summary_style == "timeline"


def test_config_summary_style_endpoint(client, config):
    r = client.post("/api/config/summary-style", json={"style": "plain"})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert client.get("/api/config").json()["summary_style"] == "plain"


def test_summarize_endpoint_passes_style(client, config, monkeypatch):
    captured = {}
    done = threading.Event()

    def fake(self, meeting_id, job_started=None, cancel_event=None, style=None):
        captured["style"] = style
        done.set()

    monkeypatch.setattr(MeetingPipeline, "summarize_existing", fake)
    mid = "2026-01-01 10h00 - reu"
    d = config.reunioes_path / mid
    d.mkdir(parents=True, exist_ok=True)
    (d / f"Transcricao - {mid}.md").write_text("# Transcricao\n\n**[00:00]** oi\n", encoding="utf-8")
    r = client.post(f"/api/meetings/{mid}/summarize", json={"style": "plain"})
    assert r.status_code == 200 and r.json()["queued"] is True
    assert done.wait(2.0)
    assert captured["style"] == "plain"
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_summary_style.py -k "summary_style or summarize_endpoint" -q`
Expected: FAIL — `set_summary_style` missing; `/api/config/summary-style` 404; the summarize endpoint takes no body/style.

- [ ] **Step 3: Add `set_summary_style` to `meeting_processor/web/runtime.py`** (after `set_watch_dir`):

```python
def set_summary_style(config: Settings, style: str) -> dict:
    """Define o estilo padrão do resumo: 'timeline' (com períodos) ou 'plain'."""
    value = "plain" if (style or "").strip().lower() == "plain" else "timeline"
    persist_env_setting(Path(config.project_root), "MEETING_SUMMARY_STYLE", value)
    config.summary_style = value
    logger.info("Estilo do resumo: %s", value)
    return {"ok": True, "summary_style": value}
```

- [ ] **Step 4: Wire `web/app.py`.**
  - Add `Body` to the FastAPI import: change
    `from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile`
    to
    `from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile`.
  - Add `set_summary_style` to the `from .runtime import (...)` list.
  - In `api_get_config`, add `"summary_style": config.summary_style,` to the returned dict.
  - Add after `api_set_watch_dir` (or any `/api/config/*` setter):
    ```python
    @app.post("/api/config/summary-style")
    async def api_set_summary_style(payload: dict):
        set_summary_style(config, (payload or {}).get("style", ""))
        return {"ok": True}
    ```
  - Change `api_summarize` to accept an optional body + thread the style:
    ```python
    @app.post("/api/meetings/{meeting_id}/summarize")
    async def api_summarize(meeting_id: str, payload: dict | None = Body(default=None)):
        meeting_dir = _reunioes_dir(config.vault_path, meeting_id)
        if meeting_dir is None or not meeting_dir.is_dir() or not list(
            meeting_dir.glob("Transcricao - *.md")
        ):
            raise HTTPException(status_code=404, detail="Transcrição não encontrada")
        style = (payload or {}).get("style")
        _submit_job(meeting_id, lambda started, ev: MeetingPipeline(config).summarize_existing(
            meeting_id, job_started=started, cancel_event=ev, style=style))
        return {"ok": True, "queued": True, "meeting_id": meeting_id}
    ```

- [ ] **Step 5: Run tests + regression**

Run: `.venv/bin/python -m pytest tests/test_summary_style.py tests/test_transcribe_api.py -q`
Expected: PASS (the 3 endpoint/runtime tests + existing transcribe-api tests). Confirm `.venv/bin/python -c "import meeting_processor.web.app"`.

- [ ] **Step 6: Commit**

```bash
git add meeting_processor/web/runtime.py meeting_processor/web/app.py tests/test_summary_style.py
git commit -m "feat(summary): summary-style endpoints (global default + per-summarize)"
```

---

### Task 4: Frontend (Settings radio + MeetingDetail select)

**Files:** Modify `frontend/src/api/types.ts`, `frontend/src/hooks/useApi.ts`, `frontend/src/pages/Settings.tsx`, `frontend/src/pages/MeetingDetail.tsx`; Create `frontend/src/__tests__/summaryStyle.test.tsx`.

- [ ] **Step 1: Write the failing test** — create `frontend/src/__tests__/summaryStyle.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { MeetingDetail } from "../pages/MeetingDetail";
import { ToastProvider } from "../components/Toast";

const MEETING = {
  id: "abc", title: "abc", meta: { purpose: "", meeting_type: "" },
  resumo_md: "", tasks: [], transcricao_md: "",
};

function stub() {
  return vi.fn(async (url: string, opts?: RequestInit) => {
    const u = String(url);
    if (opts?.method === "POST") return new Response(JSON.stringify({ ok: true, queued: true }), { status: 200 });
    if (u.includes("/api/status")) return new Response(JSON.stringify({ watcher_alive: false, active: [] }), { status: 200 });
    if (u.includes("/source")) return new Response(JSON.stringify({ exists: false, name: "", path: "", size: null }), { status: 200 });
    if (u.includes("/log")) return new Response(JSON.stringify([]), { status: 200 });
    if (u.endsWith("/api/config")) return new Response(JSON.stringify({ watch_dir: "/x", steps: { summary: true, note: true, kanban: true, wiki: true }, meeting_context: "", summary_style: "timeline" }), { status: 200 });
    return new Response(JSON.stringify(MEETING), { status: 200 });
  });
}

function setup() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/meetings/abc"]}>
        <ToastProvider><Routes><Route path="/meetings/:id" element={<MeetingDetail />} /></Routes></ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("MeetingDetail — summary style", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("Gerar resumo POSTs the selected style", async () => {
    const f = stub();
    vi.stubGlobal("fetch", f);
    setup();
    const sel = await screen.findByRole("combobox", { name: /Estilo do resumo/i });
    fireEvent.change(sel, { target: { value: "plain" } });
    fireEvent.click(screen.getByRole("button", { name: /Gerar resumo/i }));
    await waitFor(() => {
      const call = f.mock.calls.find(([u, o]) =>
        String(u).endsWith("/api/meetings/abc/summarize") && (o as RequestInit)?.method === "POST");
      expect(call).toBeTruthy();
      expect(JSON.parse(String((call![1] as RequestInit).body))).toMatchObject({ style: "plain" });
    });
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run (from `frontend/`): `npx vitest run src/__tests__/summaryStyle.test.tsx`
Expected: FAIL — no "Estilo do resumo" combobox; `summarize.mutate` still takes a bare id.

- [ ] **Step 3: Add the type.** In `frontend/src/api/types.ts`, change `Config`:

```ts
export interface Config { watch_dir: string; steps: Steps; meeting_context: string; summary_style: string; }
```

- [ ] **Step 4: Update the hooks** in `frontend/src/hooks/useApi.ts`:
  - Change `useSummarizeMeeting` to take `{ id, style }`:
    ```ts
    export function useSummarizeMeeting() {
      const qc = useQueryClient();
      return useMutation({
        mutationFn: ({ id, style }: { id: string; style?: string }) =>
          api.post(`/api/meetings/${encodeURIComponent(id)}/summarize`, { style }),
        onSuccess: (_d, { id }) => {
          qc.invalidateQueries({ queryKey: ["status"] });
          qc.invalidateQueries({ queryKey: ["meetings"] });
          qc.invalidateQueries({ queryKey: ["history"] });
          qc.invalidateQueries({ queryKey: ["meeting-log", id] });
        },
      });
    }
    ```
  - Add `useSetSummaryStyle` (e.g. after `useSetMeetingContext`):
    ```ts
    export function useSetSummaryStyle() {
      const qc = useQueryClient();
      return useMutation({
        mutationFn: (style: string) => api.post("/api/config/summary-style", { style }),
        onSuccess: () => qc.invalidateQueries({ queryKey: ["config"] }),
      });
    }
    ```

- [ ] **Step 5: MeetingDetail — style select + pass it.** In `frontend/src/pages/MeetingDetail.tsx`:
  - Add `useConfig` and `useState` imports if missing (`useState` is already imported; add `useConfig` to the `useApi` import).
  - Add: `const config = useConfig();` near the other hooks, and `const [summaryStyle, setSummaryStyle] = useState("timeline");`
  - Seed it once config loads — add a small effect (next to the existing ones, or reuse): `useEffect(() => { if (config.data) setSummaryStyle(config.data.summary_style ?? "timeline"); }, [config.data]);`
  - Change `generateSummary` (line 79-82) to pass the style:
    ```tsx
      const generateSummary = () =>
        summarize.mutate({ id, style: summaryStyle }, {
          onSuccess: () => toast("ok", "Gerando resumo — acompanhe abaixo e no Dashboard."),
          onError: (e) => toast("err", e instanceof ApiError ? e.message : "Erro"),
        });
    ```
  - Next to the "Gerar resumo" button (the toolbar `<button onClick={generateSummary} ...>`), add a `<select>` before it:
    ```tsx
          <select aria-label="Estilo do resumo" value={summaryStyle}
            onChange={(e) => setSummaryStyle(e.target.value)} disabled={!!activeJob}
            className="rounded-lg border border-line px-2 py-1.5 text-[13px]">
            <option value="timeline">Com períodos</option>
            <option value="plain">Resumo simples</option>
          </select>
    ```

- [ ] **Step 6: Settings — global default radio/select.** In `frontend/src/pages/Settings.tsx`:
  - Add `useSetSummaryStyle` to the `useApi` import; `const setStyle = useSetSummaryStyle();` near the other hooks; `const [summaryStyle, setSummaryStyle] = useState("timeline");`
  - In the config-seeding `useEffect`, add: `setSummaryStyle(config.data.summary_style ?? "timeline");`
  - Add a Card after the "Contexto da reunião" Card:
    ```tsx
          <Card title="Estilo do resumo" eyebrow="LLM" index="B3">
            <select aria-label="Estilo padrão do resumo" value={summaryStyle}
              onChange={(e) => { setSummaryStyle(e.target.value); setStyle.mutate(e.target.value, { onSuccess: () => toast("ok", "Estilo salvo."), onError }); }}
              className="w-fit rounded-lg border border-line px-3 py-2 text-sm">
              <option value="timeline">Com períodos</option>
              <option value="plain">Resumo simples</option>
            </select>
          </Card>
    ```

- [ ] **Step 7: Run test + typecheck + full suite**

Run (from `frontend/`): `npx vitest run src/__tests__/summaryStyle.test.tsx` (PASS), then `npx tsc --noEmit` (exit 0), then `npx vitest run` (all pass — the existing `meetingDetail.test.tsx`/`meetingDetailStepper.test.tsx` provide `/api/config` via their stubs; if one lacks `summary_style` the `?? "timeline"` default keeps it working — verify those still pass).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/hooks/useApi.ts frontend/src/pages/Settings.tsx frontend/src/pages/MeetingDetail.tsx frontend/src/__tests__/summaryStyle.test.tsx
git commit -m "feat(ui): summary-style select (per-meeting) + Settings default"
```

---

## Self-Review

**Spec coverage:**
- `summary_style` config + env → Task 1. ✓
- `summarize(style=)` + plain directive (covers single-pass + map-reduce via system_prompt) → Task 1 Step 4. ✓
- `_summarize(style)` + `summarize_existing(style)`; `process()` uses the default → Task 2. ✓
- `set_summary_style` + `/api/config` field + `/api/config/summary-style` + summarize-endpoint `style` body → Task 3. ✓
- Frontend: `Config.summary_style`, `useSetSummaryStyle`, `useSummarizeMeeting({id,style})`, Settings select, MeetingDetail select → Task 4. ✓
- Tests across all layers → Tasks 1-4. ✓
- Out of scope (other styles, timeline behavior, per-meeting persistence) → untouched. ✓

**Placeholder scan:** none — every step has concrete code/commands.

**Type consistency:** `summary_style` (Task 1) read by `summarize` (Task 1), `set_summary_style` (Task 3), `/api/config` (Task 3), `Config.summary_style` (Task 4). `summarize(..., style=None)` (Task 1) called by `_summarize(..., style=None)` (Task 2) → `summarize_existing(..., style=None)` (Task 2) → the endpoint lambda (Task 3). `useSummarizeMeeting` now takes `{id, style}` (Task 4) and its sole caller `MeetingDetail.generateSummary` is updated in the same task. The `/api/config/summary-style` route + `{style}` body match `useSetSummaryStyle` (Task 4). Names consistent throughout. ✓
