# Summary Quality Multipliers (bundle)

**Date:** 2026-06-09
**Status:** Approved design

## Goal

Four small, high-leverage improvements to summary quality, all centered on the
summarizer: defensive output parsing, per-meeting context injection (with a
Settings textarea), a smarter map-reduce step, and configurable temperature for
the cloud providers. Tier-2 of the codebase review.

## 1. Defensive output parsing (`summarizer.py`)

**Problem:** `_parse_response` builds `MeetingSummary` with list comprehensions
(`[ActionItem(**ai) for ai in data.get("action_items", [])]`, `[TimeWindowSummary(**tw) ...]`).
One malformed entry (a float `start_minutes`, `"priority": "URGENT"`,
`action_items` returned as a string, an extra/unknown key) makes Pydantic raise
*inside* the comprehension → the whole parse aborts and `_empty_summary()` is
returned, silently discarding a mostly-good summary. Local models (qwen2.5,
llama3) do this regularly.

**Change:** add two static helpers to `_BaseSummarizer`:
- `_coerce_action_item(raw) -> ActionItem | None`: if `raw` isn't a dict, return
  None; build `ActionItem` in its own try/except (lowercase a string `priority`,
  coerce other fields straight through); on failure log debug + return None.
- `_coerce_time_window(raw) -> TimeWindowSummary | None`: if not a dict → None;
  `int()` `start_minutes`/`end_minutes`, str `summary`; try/except → None on bad.

`_parse_response` uses them with list filtering, and coerces the plain-list
fields defensively: `action_items = [a for a in (_coerce_action_item(x) for x in
_as_list(data.get("action_items"))) if a]`, same for `time_windows`; and
`participants`/`key_topics`/`decisions`/`open_questions` via an `_as_list(value)`
helper that returns `value` if it's a list else `[]` (so a model returning
`"action_items": "none"` yields `[]`, not a crash). A model that gets 9/10 items
right yields 9 items.

## 2. Per-meeting context injection (config + backend + Settings UI)

**Config (`config.py`):** `meeting_context: str = ""`, env `MEETING_CONTEXT` in
`string_overrides`. Persisted to a dedicated `.meeting-context.txt` in
`project_root` (free-form, possibly multi-line — unsuitable for `.env`).
`load_config` reads the file (if present) as the default for `meeting_context`,
then the env override (if set) takes precedence — consistent with how every
other setting lets env win.

**Prompt wiring (`summarizer.py`):** `_build_user_prompt` prepends, when
`self.config.meeting_context.strip()` is non-empty:
`"--- CONTEXTO DA REUNIÃO ---\n{context}\n\n"` before the `Arquivo de origem:`
line. Empty context ⇒ no block (byte-identical to today). `SYSTEM_PROMPT` gains
one rule line: *"Se um CONTEXTO DA REUNIÃO for fornecido, use-o para grafar
corretamente os nomes dos participantes e os termos/siglas técnicas."* The
context flows into single-pass and every map chunk (both go through
`_build_user_prompt`).

**Backend setter (`web/runtime.py`):** `set_meeting_context(config, text) -> dict`
writes `Path(config.project_root) / ".meeting-context.txt"` (create/overwrite;
empty text removes the file) and sets `config.meeting_context = text`. Returns
`{"ok": True}`. Mirrors `set_watch_dir`'s shape (no watcher restart needed).

**Endpoints (`web/app.py`):** `/api/config` GET adds `"meeting_context":
config.meeting_context`. New `POST /api/config/meeting-context` (`{context: str}`)
→ `set_meeting_context` → `{"ok": True}`.

**Frontend:** `Config` type (`api/types.ts`) gains `meeting_context: string`.
`useSetMeetingContext()` (`hooks/useApi.ts`) POSTs `/api/config/meeting-context`,
invalidates `["config"]`. Settings page: a "Contexto da reunião" `<textarea>`
seeded from `config.meeting_context` + a "Salvar" button calling the mutation
(toast on success), following the existing watch-dir field's pattern.

## 3. Smarter reduce step (`summarizer.py`)

`REDUCE_SYSTEM_PROMPT` currently asks the LLM only for `executive_summary` +
`purpose`; `_reduce_partials` exact-string-dedups `decisions`/`open_questions`
(`_dedupe_strings`), missing semantic duplicates across chunks ("Orçamento
aprovado" vs "Aprovado o orçamento"). Extend `REDUCE_SYSTEM_PROMPT` to also emit
`decisions: []` and `open_questions: []`. `_reduce_narrative` returns
`(executive_summary, purpose, decisions, open_questions)`; on any failure it
falls back to `("\n\n".join(...)`, first purpose, **and** the existing
programmatic `_dedupe_strings` union for the two lists). `_reduce_partials` uses
the synthesized `decisions`/`open_questions` (and keeps programmatic merge for
`time_windows`/`action_items`/`participants`/`key_topics`). Only affects long,
map-reduced transcripts.

## 4. Cloud temperature parity (`config.py` + providers)

Add `anthropic_temperature: float = 0.3`, `openai_temperature: float = 0.3`,
`gemini_temperature: float = 0.3` to `Settings` (+ `float_overrides`:
`MEETING_ANTHROPIC_TEMPERATURE`, `MEETING_OPENAI_TEMPERATURE`,
`MEETING_GEMINI_TEMPERATURE`). Wire each into its `_call_llm`:
- `AnthropicSummarizer`: `self.client.messages.create(..., temperature=self.config.anthropic_temperature)`.
- `OpenAISummarizer`: `payload["temperature"] = self.config.openai_temperature`.
- `GeminiSummarizer`: `generationConfig["temperature"] = self.config.gemini_temperature`.

Ollama already passes `self.temperature`. Default 0.3 = reliable JSON + natural
prose; configurable per provider.

## Testing (TDD, no real LLM/network)

- **Coercion:** `_coerce_action_item` skips a non-dict / a bad-typed entry,
  lowercases priority; `_parse_response` with `{"action_items": "none"}` →
  empty list (no crash); with one bad + one good action item → one item kept;
  a float `start_minutes` is `int()`-coerced.
- **Context injection:** `_build_user_prompt` includes the
  `CONTEXTO DA REUNIÃO` block iff `config.meeting_context` is non-empty.
  `set_meeting_context` writes `.meeting-context.txt`; a fresh `load_config`
  (env unset) returns that text in `config.meeting_context`; empty text removes
  the file.
- **`/api/config` + setter:** GET includes `meeting_context`; POST persists and
  GET reflects it (TestClient).
- **Reduce:** with a fake `_call_llm` returning `decisions`/`open_questions`,
  `_reduce_partials` uses them; on a bad reduce response it falls back to the
  programmatic dedup union.
- **Temperature:** each provider's `_call_llm` includes the configured
  temperature in the request — assert via a mocked transport/client (the
  Anthropic test monkeypatches `client.messages.create` to capture kwargs; the
  HTTP providers capture the posted payload).
- **Frontend (Vitest):** Settings renders the textarea seeded from
  `meeting_context` and POSTs `/api/config/meeting-context` on Salvar.

## Out of scope

- Per-meeting (vs single global) context.
- `open_questions` severity/category structure.
- Speaker/participant attribution (the separate "strategic spine").
- Synthesizing `key_topics`/`participants` via the reduce LLM (kept programmatic).
