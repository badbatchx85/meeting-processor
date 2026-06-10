# Summary Quality Multipliers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Four summarizer improvements — defensive parsing, per-meeting context injection (+ Settings textarea), smarter reduce, and configurable cloud temperature.

**Architecture:** Defensive coercion helpers in `_BaseSummarizer._parse_response`; a global `meeting_context` config (file-backed, env-overridable) injected into the prompt and editable from Settings; an extended `REDUCE_SYSTEM_PROMPT` that synthesizes `decisions`/`open_questions`; per-provider `temperature` config wired into each `_call_llm`.

**Tech Stack:** Python 3.14, Pydantic, FastAPI, httpx; React/Vite/Vitest.

Run Python tests with `.venv/bin/python -m pytest`; frontend with `cd frontend && npx vitest run <file>`. The pre-existing `test_summarizer_mock.py::test_factory_selects_anthropic` failure (no `ANTHROPIC_API_KEY`) is unrelated.

---

## File Structure
- **Modify** `meeting_processor/summarizer.py` — coercion helpers + `_parse_response`; `_build_user_prompt` context block + `SYSTEM_PROMPT` rule; `REDUCE_SYSTEM_PROMPT` + `_reduce_narrative` + `_reduce_partials`; temperature in 3 providers.
- **Modify** `meeting_processor/config.py` — `meeting_context` + 3 `*_temperature` fields + overrides + load_config file read.
- **Modify** `meeting_processor/web/runtime.py` — `set_meeting_context`.
- **Modify** `meeting_processor/web/app.py` — `/api/config` GET field + `POST /api/config/meeting-context`.
- **Modify** `frontend/src/api/types.ts`, `frontend/src/hooks/useApi.ts`, `frontend/src/pages/Settings.tsx`.
- **Create** `tests/test_summary_quality.py`, `frontend/src/__tests__/settingsContext.test.tsx`.

---

### Task 1: Defensive output parsing

**Files:** Modify `meeting_processor/summarizer.py` (`_parse_response` ~297); Create `tests/test_summary_quality.py`.

- [ ] **Step 1: Write the failing tests** — create `tests/test_summary_quality.py`:

```python
"""Summary quality multipliers: parsing, context, reduce, temperature."""
import json

from meeting_processor.summarizer import _BaseSummarizer


def test_parse_skips_bad_action_items(config):
    s = _BaseSummarizer(config)
    js = json.dumps({"executive_summary": "ok", "action_items": [
        {"description": "Tarefa boa"}, "não é dict", {"assignee": "Ana"}]})
    out = s._parse_response(js)
    assert [a.description for a in out.action_items] == ["Tarefa boa"]


def test_parse_action_items_as_string_yields_empty(config):
    s = _BaseSummarizer(config)
    out = s._parse_response(json.dumps({"executive_summary": "x", "action_items": "none"}))
    assert out.action_items == []
    assert out.executive_summary == "x"


def test_parse_coerces_priority_and_float_minutes(config):
    s = _BaseSummarizer(config)
    out = s._parse_response(json.dumps({
        "action_items": [{"description": "t", "priority": "ALTA"}],
        "time_windows": [{"start_minutes": 0.0, "end_minutes": 5.0, "summary": "s"}],
    }))
    assert out.action_items[0].priority == "alta"
    assert out.time_windows[0].start_minutes == 0
    assert out.time_windows[0].end_minutes == 5
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_summary_quality.py -q`
Expected: FAIL — current `_parse_response` raises on the non-dict / string `action_items` (Pydantic error inside the comprehension) → exception, not the expected coerced result.

- [ ] **Step 3: Add coercion helpers** to `_BaseSummarizer` (just above `_parse_response`):

```python
    @staticmethod
    def _as_list(value) -> list:
        return value if isinstance(value, list) else []

    @staticmethod
    def _coerce_action_item(raw):
        if not isinstance(raw, dict):
            return None
        data = dict(raw)
        if isinstance(data.get("priority"), str):
            data["priority"] = data["priority"].strip().lower() or None
        try:
            return ActionItem(**data)
        except Exception:  # noqa: BLE001 — pula item malformado, mantém os bons
            logger.debug("ActionItem inválido ignorado: %s", raw)
            return None

    @staticmethod
    def _coerce_time_window(raw):
        if not isinstance(raw, dict):
            return None
        try:
            return TimeWindowSummary(
                start_minutes=int(raw.get("start_minutes", 0)),
                end_minutes=int(raw.get("end_minutes", 0)),
                summary=str(raw.get("summary", "")),
            )
        except Exception:  # noqa: BLE001
            logger.debug("TimeWindow inválido ignorado: %s", raw)
            return None
```

- [ ] **Step 4: Rewrite the `MeetingSummary(...)` build** in `_parse_response` (the `return MeetingSummary(...)` block) to use them defensively:

```python
        return MeetingSummary(
            executive_summary=str(data.get("executive_summary", "") or ""),
            time_windows=[
                tw for tw in (self._coerce_time_window(x) for x in self._as_list(data.get("time_windows"))) if tw
            ],
            action_items=[
                ai for ai in (self._coerce_action_item(x) for x in self._as_list(data.get("action_items"))) if ai
            ],
            participants=[str(x) for x in self._as_list(data.get("participants"))],
            key_topics=[str(x) for x in self._as_list(data.get("key_topics"))],
            purpose=str(data.get("purpose", "") or ""),
            meeting_type=str(data.get("meeting_type", "") or ""),
            decisions=[str(x) for x in self._as_list(data.get("decisions"))],
            open_questions=[str(x) for x in self._as_list(data.get("open_questions"))],
        )
```

- [ ] **Step 5: Run tests + regression**

Run: `.venv/bin/python -m pytest tests/test_summary_quality.py tests/test_summary_chunking.py -q`
Expected: PASS (3 new + the chunking suite — `_parse_response` still produces the same result for well-formed input).

- [ ] **Step 6: Commit**

```bash
git add meeting_processor/summarizer.py tests/test_summary_quality.py
git commit -m "feat(summary): defensive output parsing (skip malformed items)"
```

---

### Task 2: Configurable cloud-provider temperature

**Files:** Modify `meeting_processor/config.py`, `meeting_processor/summarizer.py` (3 providers); Test: `tests/test_summary_quality.py`.

- [ ] **Step 1: Append the failing tests:**

```python
# --- Task 2: cloud temperature ---------------------------------------------

import httpx


def test_anthropic_passes_temperature(config, monkeypatch):
    config.anthropic_api_key = "test-key"
    config.anthropic_temperature = 0.3
    from meeting_processor.summarizer import AnthropicSummarizer
    s = AnthropicSummarizer(config)
    captured = {}

    class _Msg:
        content = [type("C", (), {"text": "{}"})()]

    monkeypatch.setattr(s.client.messages, "create", lambda **kw: (captured.update(kw), _Msg())[1])
    s._call_llm("sys", "usr")
    assert captured["temperature"] == 0.3


def _fake_post_capturing(captured):
    class _Resp:
        status_code = 200
        def json(self_inner):
            # both shapes so one helper serves OpenAI and Gemini
            return {
                "choices": [{"message": {"content": "{}"}}],
                "candidates": [{"content": {"parts": [{"text": "{}"}]}}],
            }
        def raise_for_status(self_inner):
            return None
    def fake_post(self_inner, url, headers=None, params=None, json=None):
        captured.update(json or {})
        return _Resp()
    return fake_post


def test_openai_passes_temperature(config, monkeypatch):
    config.openai_api_key = "k"
    config.openai_temperature = 0.3
    from meeting_processor.summarizer import OpenAISummarizer
    captured = {}
    monkeypatch.setattr(httpx.Client, "post", _fake_post_capturing(captured))
    OpenAISummarizer(config)._call_llm("sys", "usr")
    assert captured["temperature"] == 0.3


def test_gemini_passes_temperature(config, monkeypatch):
    config.gemini_api_key = "k"
    config.gemini_temperature = 0.3
    from meeting_processor.summarizer import GeminiSummarizer
    captured = {}
    monkeypatch.setattr(httpx.Client, "post", _fake_post_capturing(captured))
    GeminiSummarizer(config)._call_llm("sys", "usr")
    assert captured["generationConfig"]["temperature"] == 0.3
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_summary_quality.py -k temperature -q`
Expected: FAIL — `config` has no `anthropic_temperature` (AttributeError) and the payloads lack `temperature`.

- [ ] **Step 3: Add config fields.** In `meeting_processor/config.py`, add near the other LLM fields (e.g. after `gemini_model`):

```python
    anthropic_temperature: float = 0.3
    openai_temperature: float = 0.3
    gemini_temperature: float = 0.3
```

And in the `float_overrides` dict, add:

```python
        "MEETING_ANTHROPIC_TEMPERATURE": "anthropic_temperature",
        "MEETING_OPENAI_TEMPERATURE": "openai_temperature",
        "MEETING_GEMINI_TEMPERATURE": "gemini_temperature",
```

- [ ] **Step 4: Wire temperature into the 3 providers** in `meeting_processor/summarizer.py`:
  - **Anthropic** `_call_llm`: add `temperature=self.config.anthropic_temperature,` as a kwarg to `self.client.messages.create(...)` (e.g. right after `max_tokens=...`).
  - **OpenAI** `_call_llm`: in the `payload: dict = { ... }` literal, add `"temperature": self.config.openai_temperature,` (e.g. after `"model": self.model,`).
  - **Gemini** `_call_llm`: change the `generationConfig` to include temperature:
    ```python
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": self.config.gemini_temperature,
            },
    ```

- [ ] **Step 5: Run tests + regression**

Run: `.venv/bin/python -m pytest tests/test_summary_quality.py test_summarizer_mock.py -q`
Expected: PASS (the 3 temperature tests; summarizer-mock passes except the pre-existing anthropic-key factory test).

- [ ] **Step 6: Commit**

```bash
git add meeting_processor/config.py meeting_processor/summarizer.py tests/test_summary_quality.py
git commit -m "feat(summary): configurable temperature for cloud providers"
```

---

### Task 3: Smarter reduce (synthesize decisions + open_questions)

**Files:** Modify `meeting_processor/summarizer.py` (`REDUCE_SYSTEM_PROMPT`, `_reduce_narrative`, `_reduce_partials`); Test: `tests/test_summary_quality.py`.

Depends on Task 1's `_as_list`.

- [ ] **Step 1: Append the failing tests:**

```python
# --- Task 3: smarter reduce ------------------------------------------------

from meeting_processor.models import MeetingSummary
from meeting_processor.summarizer import _BaseSummarizer as _B


class _ReduceFake(_B):
    provider_name = "fake"
    def __init__(self, config, reduce_response):
        super().__init__(config)
        self._r = reduce_response
    def _call_llm(self, system_prompt, user_prompt):
        return self._r


def _partials():
    return [
        MeetingSummary(executive_summary="A", time_windows=[], action_items=[],
                       participants=[], key_topics=[], decisions=["Aprovado o orçamento"],
                       open_questions=["Quem assume o deploy?"]),
        MeetingSummary(executive_summary="B", time_windows=[], action_items=[],
                       participants=[], key_topics=[], decisions=["Orçamento aprovado"],
                       open_questions=[]),
    ]


def test_reduce_uses_llm_decisions_and_questions(config):
    rr = json.dumps({"executive_summary": "RES", "purpose": "P",
                     "decisions": ["Orçamento aprovado"], "open_questions": ["Quem assume o deploy?"]})
    out = _ReduceFake(config, rr)._reduce_partials(_partials())
    assert out.decisions == ["Orçamento aprovado"]          # LLM-merged (deduped semantically)
    assert out.open_questions == ["Quem assume o deploy?"]
    assert out.executive_summary == "RES"


def test_reduce_falls_back_on_bad_json(config):
    out = _ReduceFake(config, "desculpe, não consegui")._reduce_partials(_partials())
    # fallback = programmatic union of partials' decisions/open_questions
    assert set(out.decisions) == {"Aprovado o orçamento", "Orçamento aprovado"}
    assert out.open_questions == ["Quem assume o deploy?"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_summary_quality.py -k reduce -q`
Expected: FAIL — `_reduce_narrative` returns a 2-tuple; `_reduce_partials` still programmatically dedups (the first test expects the LLM's single merged decision, gets two).

- [ ] **Step 3: Extend `REDUCE_SYSTEM_PROMPT`** — replace its JSON block + rules. The new constant:

```python
REDUCE_SYSTEM_PROMPT = """\
Você recebe vários resumos parciais de uma MESMA reunião, em ordem cronológica.
Combine-os em um único resumo coerente em português brasileiro.

Responda APENAS com JSON válido, sem markdown, sem blocos de código:

{
  "executive_summary": "Resumo executivo unificado de 3-5 frases cobrindo a reunião inteira",
  "purpose": "Uma frase com o objetivo central da reunião, ou string vazia",
  "decisions": ["Decisões efetivamente tomadas, unificadas — funda duplicatas semânticas"],
  "open_questions": ["Perguntas/riscos/bloqueios em aberto, unificados sem duplicatas"]
}

Regras:
- Una as ideias dos trechos sem repetição; produza UM resumo executivo fluido.
- Em "decisions" e "open_questions", funda itens que dizem a mesma coisa com
  palavras diferentes (ex.: "Orçamento aprovado" == "Aprovado o orçamento").
- Não invente informação que não esteja nos resumos parciais.\
"""
```

- [ ] **Step 4: Rewrite `_reduce_narrative`** to return 4 values with list fallbacks:

```python
    def _reduce_narrative(self, partials: list[MeetingSummary]) -> tuple[str, str, list[str], list[str]]:
        """Sintetiza executive_summary + purpose + decisions + open_questions via
        uma chamada LLM 'reduce'. Em qualquer falha, cai para concatenação /
        união programática — nunca perde conteúdo."""
        fallback_summary = "\n\n".join(
            p.executive_summary for p in partials if p.executive_summary
        )
        fallback_purpose = next((p.purpose for p in partials if p.purpose), "")
        fallback_decisions = self._dedupe_strings([d for p in partials for d in p.decisions])
        fallback_questions = self._dedupe_strings([q for p in partials for q in p.open_questions])

        blocks = []
        for i, p in enumerate(partials, 1):
            parts = [f"[Trecho {i}] {p.executive_summary}"]
            if p.key_topics:
                parts.append("Tópicos: " + ", ".join(p.key_topics))
            if p.decisions:
                parts.append("Decisões: " + "; ".join(p.decisions))
            if p.open_questions:
                parts.append("Questões: " + "; ".join(p.open_questions))
            blocks.append("\n".join(parts))
        user_prompt = "Resumos parciais (em ordem):\n\n" + "\n\n".join(blocks)

        try:
            data = self._extract_json(self._call_llm(REDUCE_SYSTEM_PROMPT, user_prompt))
            if data is None:
                raise ValueError("reduce sem JSON")
            return (
                data.get("executive_summary") or fallback_summary,
                data.get("purpose") or fallback_purpose,
                [str(x) for x in self._as_list(data.get("decisions"))] or fallback_decisions,
                [str(x) for x in self._as_list(data.get("open_questions"))] or fallback_questions,
            )
        except Exception as e:  # noqa: BLE001 — degradação graciosa
            logger.warning(
                "Reduce do resumo falhou (%s); usando concatenação/união dos parciais.", e
            )
            return fallback_summary, fallback_purpose, fallback_decisions, fallback_questions
```

- [ ] **Step 5: Update `_reduce_partials`** to consume the 4-tuple. Change its unpacking + the `MeetingSummary` build so `decisions`/`open_questions` come from the narrative call:

```python
        executive_summary, purpose, decisions, open_questions = self._reduce_narrative(partials)
        return MeetingSummary(
            executive_summary=executive_summary,
            time_windows=[tw for p in partials for tw in p.time_windows],
            action_items=self._dedupe_action_items(
                [ai for p in partials for ai in p.action_items]
            ),
            participants=self._dedupe_strings(
                [x for p in partials for x in p.participants]
            ),
            key_topics=self._dedupe_strings([x for p in partials for x in p.key_topics]),
            purpose=purpose,
            meeting_type=next((p.meeting_type for p in partials if p.meeting_type), ""),
            decisions=decisions,
            open_questions=open_questions,
        )
```

- [ ] **Step 6: Run tests + regression**

Run: `.venv/bin/python -m pytest tests/test_summary_quality.py tests/test_summary_chunking.py -q`
Expected: PASS. Note: `tests/test_summary_chunking.py` has a reduce test that stubs `_call_llm`; if it asserted the old 2-tuple behavior it still holds (the fields it checks — executive_summary/purpose — are unchanged), but if any assertion there breaks due to decisions now coming from the LLM, update that test minimally to match (the new contract: reduce LLM supplies decisions/open_questions, fallback = programmatic union).

- [ ] **Step 7: Commit**

```bash
git add meeting_processor/summarizer.py tests/test_summary_quality.py
git commit -m "feat(summary): reduce step synthesizes decisions + open_questions"
```

---

### Task 4: Per-meeting context — backend

**Files:** Modify `meeting_processor/config.py`, `meeting_processor/summarizer.py`, `meeting_processor/web/runtime.py`, `meeting_processor/web/app.py`; Test: `tests/test_summary_quality.py`.

- [ ] **Step 1: Append the failing tests:**

```python
# --- Task 4: meeting context (backend) -------------------------------------

from meeting_processor.web.runtime import set_meeting_context


def test_build_user_prompt_includes_context_when_set(config):
    config.meeting_context = "Projeto X | Ana, Bruno"
    s = _BaseSummarizer(config)
    p = s._build_user_prompt("a.mp4", 60.0, "transcript")
    assert "CONTEXTO DA REUNIÃO" in p and "Projeto X" in p


def test_build_user_prompt_no_block_when_empty(config):
    config.meeting_context = ""
    s = _BaseSummarizer(config)
    assert "CONTEXTO DA REUNIÃO" not in s._build_user_prompt("a.mp4", 60.0, "t")


def test_set_meeting_context_roundtrips_via_file(config, monkeypatch):
    monkeypatch.delenv("MEETING_CONTEXT", raising=False)
    set_meeting_context(config, "Glossário: PO=Product Owner")
    from pathlib import Path
    assert (Path(config.project_root) / ".meeting-context.txt").read_text(encoding="utf-8") == "Glossário: PO=Product Owner"
    assert config.meeting_context == "Glossário: PO=Product Owner"


def test_config_meeting_context_endpoint(client, config):
    r = client.post("/api/config/meeting-context", json={"context": "abc"})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert client.get("/api/config").json()["meeting_context"] == "abc"
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_summary_quality.py -k "context or meeting_context" -q`
Expected: FAIL — `meeting_context` field, `set_meeting_context`, prompt block, and endpoint don't exist.

- [ ] **Step 3: Config field + load_config file read.** In `meeting_processor/config.py`:
  - Add field near the LLM fields: `meeting_context: str = ""`.
  - In `string_overrides`, add `"MEETING_CONTEXT": "meeting_context",`.
  - In `load_config`, right after `config_data["project_root"] = str(project_root)`, add:
    ```python
    # Contexto da reunião: arquivo dedicado (multi-linha); env tem precedência.
    ctx_file = project_root / ".meeting-context.txt"
    if not config_data.get("meeting_context") and ctx_file.exists():
        config_data["meeting_context"] = ctx_file.read_text(encoding="utf-8")
    ```

- [ ] **Step 4: Prompt injection.** In `meeting_processor/summarizer.py`:
  - Rewrite `_build_user_prompt`:
    ```python
    def _build_user_prompt(self, source_filename: str, duration: float, chunked_text: str) -> str:
        context = (self.config.meeting_context or "").strip()
        context_block = f"--- CONTEXTO DA REUNIÃO ---\n{context}\n\n" if context else ""
        return (
            f"{context_block}"
            f"Arquivo de origem: {source_filename}\n"
            f"Duração total: {format_duration(duration)}\n\n"
            f"--- TRANSCRIÇÃO ---\n\n{chunked_text}"
        )
    ```
  - In `SYSTEM_PROMPT`, add one rule line in the "Regras:" list (e.g. after the participants rule `- Se não conseguir identificar participantes...`):
    ```
    - Se um CONTEXTO DA REUNIÃO for fornecido, use-o para grafar corretamente os nomes dos participantes e os termos/siglas técnicos.
    ```

- [ ] **Step 5: `set_meeting_context` in `meeting_processor/web/runtime.py`** (add after `set_watch_dir`):

```python
def set_meeting_context(config: Settings, text: str) -> dict:
    """Salva o contexto global da reunião em ``.meeting-context.txt``.

    Texto livre (possivelmente multi-linha) que é injetado no prompt do resumo.
    Texto vazio remove o arquivo.
    """
    text = text or ""
    path = Path(config.project_root) / ".meeting-context.txt"
    if text.strip():
        path.write_text(text, encoding="utf-8")
    elif path.exists():
        path.unlink()
    config.meeting_context = text
    logger.info("Contexto da reunião atualizado (%d chars).", len(text))
    return {"ok": True}
```

- [ ] **Step 6: Endpoints in `meeting_processor/web/app.py`.**
  - Add `set_meeting_context` to the `runtime` import line (alongside `set_watch_dir`, near `app.py:37`).
  - In `api_get_config` (the `/api/config` GET), add `"meeting_context": config.meeting_context,` to the returned dict.
  - Add a new endpoint right after `api_set_watch_dir`:
    ```python
    @app.post("/api/config/meeting-context")
    async def api_set_meeting_context(payload: dict):
        set_meeting_context(config, (payload or {}).get("context", ""))
        return {"ok": True}
    ```

- [ ] **Step 7: Run tests + regression**

Run: `.venv/bin/python -m pytest tests/test_summary_quality.py tests/test_summary_chunking.py tests/test_stuck_jobs.py -q`
Expected: PASS (context tests + no regression — empty `meeting_context` default keeps `_build_user_prompt` byte-identical).

- [ ] **Step 8: Commit**

```bash
git add meeting_processor/config.py meeting_processor/summarizer.py meeting_processor/web/runtime.py meeting_processor/web/app.py tests/test_summary_quality.py
git commit -m "feat(summary): per-meeting context injection (backend + endpoint)"
```

---

### Task 5: Per-meeting context — Settings textarea (frontend)

**Files:** Modify `frontend/src/api/types.ts`, `frontend/src/hooks/useApi.ts`, `frontend/src/pages/Settings.tsx`; Create `frontend/src/__tests__/settingsContext.test.tsx`.

- [ ] **Step 1: Write the failing test** — create `frontend/src/__tests__/settingsContext.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { Settings } from "../pages/Settings";
import { ToastProvider } from "../components/Toast";

function setup() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><ToastProvider><Settings /></ToastProvider></MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Settings — meeting context", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async (url: string, opts?: RequestInit) => {
      const u = String(url);
      if (opts?.method === "POST") return new Response(JSON.stringify({ ok: true }), { status: 200 });
      if (u.includes("/api/llm")) return new Response(JSON.stringify({ provider: "local" }), { status: 200 });
      if (u.includes("/api/config"))
        return new Response(JSON.stringify({
          watch_dir: "/x", steps: { summary: true, note: true, kanban: true, wiki: true },
          meeting_context: "Projeto X",
        }), { status: 200 });
      return new Response(JSON.stringify({}), { status: 200 });
    }));
  });

  it("renders the context textarea seeded from config and POSTs on save", async () => {
    const f = global.fetch as ReturnType<typeof vi.fn>;
    setup();
    const ta = await screen.findByRole("textbox", { name: /Contexto da reuni/i });
    expect((ta as HTMLTextAreaElement).value).toContain("Projeto X");
    fireEvent.change(ta, { target: { value: "Projeto Y | Ana" } });
    fireEvent.click(screen.getByRole("button", { name: /Salvar contexto/i }));
    await waitFor(() => {
      const call = f.mock.calls.find(([u, o]) =>
        String(u).endsWith("/api/config/meeting-context") && (o as RequestInit)?.method === "POST");
      expect(call).toBeTruthy();
      expect(JSON.parse(String((call![1] as RequestInit).body))).toMatchObject({ context: "Projeto Y | Ana" });
    });
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run (from `frontend/`): `npx vitest run src/__tests__/settingsContext.test.tsx`
Expected: FAIL — no "Contexto da reunião" textarea.

- [ ] **Step 3: Add the type.** In `frontend/src/api/types.ts`, change the `Config` interface:

```ts
export interface Config { watch_dir: string; steps: Steps; meeting_context: string; }
```

- [ ] **Step 4: Add the hook.** In `frontend/src/hooks/useApi.ts`, after `useSetWatchDir`:

```ts
export function useSetMeetingContext() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (context: string) => api.post("/api/config/meeting-context", { context }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["config"] }),
  });
}
```

- [ ] **Step 5: Wire the Settings page.** In `frontend/src/pages/Settings.tsx`:
  - Add `useSetMeetingContext` to the `useApi` import.
  - Add state: `const [meetingContext, setMeetingContext] = useState("");`
  - Add the hook: `const setCtx = useSetMeetingContext();`
  - In the config-seeding `useEffect`, add: `setMeetingContext(config.data.meeting_context ?? "");`
  - Add a Card after the "Pasta monitorada" Card:
    ```tsx
          <Card title="Contexto da reunião" eyebrow="LLM" index="B2">
            <div className="flex flex-col gap-2">
              <textarea aria-label="Contexto da reunião" value={meetingContext}
                onChange={(e) => setMeetingContext(e.target.value)} rows={4}
                placeholder="Projeto, participantes habituais, siglas/glossário…"
                className="w-full rounded-lg border border-line px-3 py-2 text-sm" />
              <button onClick={() => setCtx.mutate(meetingContext, { onSuccess: () => toast("ok", "Contexto salvo."), onError })}
                className="w-fit rounded-lg bg-brand px-3 py-2 text-sm text-white hover:bg-brand-dark">
                Salvar contexto
              </button>
            </div>
          </Card>
    ```
    (`onError` is the existing local handler in Settings.tsx; reuse it.)

- [ ] **Step 6: Run test + typecheck + suite**

Run (from `frontend/`): `npx vitest run src/__tests__/settingsContext.test.tsx` (PASS), then `npx tsc --noEmit` (exit 0), then `npx vitest run` (all pass).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/hooks/useApi.ts frontend/src/pages/Settings.tsx frontend/src/__tests__/settingsContext.test.tsx
git commit -m "feat(ui): meeting-context textarea in Settings"
```

---

## Self-Review

**Spec coverage:**
- Defensive parsing (`_as_list`/`_coerce_*`, skip bad items) → Task 1. ✓
- Per-meeting context: config field + file persistence + env override + load_config read → Task 4 Step 3; prompt block + SYSTEM_PROMPT rule → Task 4 Step 4; `set_meeting_context` → Step 5; `/api/config` GET + POST → Step 6; frontend type/hook/textarea → Task 5. ✓
- Smarter reduce (REDUCE prompt + 4-tuple narrative + fallback union) → Task 3. ✓
- Cloud temperature (3 config fields + overrides + 3 providers) → Task 2. ✓
- Testing: coercion, context injection + roundtrip + endpoint, reduce + fallback, per-provider temperature, frontend textarea → Tasks 1-5. ✓
- Out of scope (per-meeting context, severity, speaker attribution, LLM-synth key_topics/participants) → untouched. ✓

**Placeholder scan:** none — every step has concrete code/commands.

**Type consistency:** `_as_list` (Task 1) used by `_parse_response` (Task 1) and `_reduce_narrative` (Task 3). `_coerce_action_item`/`_coerce_time_window` (Task 1) used in `_parse_response`. `_reduce_narrative -> tuple[str,str,list,list]` (Task 3) unpacked by `_reduce_partials` (Task 3). `meeting_context` field (Task 4) read in `_build_user_prompt` (Task 4) and `set_meeting_context` (Task 4), exposed by `/api/config` (Task 4), typed in `Config` (Task 5), set by `useSetMeetingContext` (Task 5). `*_temperature` fields (Task 2) read in each provider's `_call_llm` (Task 2). Names consistent throughout. ✓
