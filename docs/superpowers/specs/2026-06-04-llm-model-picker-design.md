# Choose the LLM Model on the Front-end

**Date:** 2026-06-04
**Status:** Approved design

## Goal

Besides the provider (already switchable in Settings), let the user pick the
**model** for the active provider from a curated dropdown (Gemini, OpenAI/GPT,
Anthropic, plus common local/Ollama), with the current model preserved and an
"Outro (personalizado)…" option to type any custom model. Persists like the
provider change.

## Backend (mirrors the provider flow — DRY)

1. **`meeting_processor/web/runtime.py`** — `set_llm_model(config, provider, model) -> dict`:
   - Normalize provider (`ollama` → `local`).
   - Maps provider → config field + env var:
     `anthropic`→(`anthropic_model`, `MEETING_ANTHROPIC_MODEL`),
     `openai`→(`openai_model`, `MEETING_OPENAI_MODEL`),
     `gemini`→(`gemini_model`, `MEETING_GEMINI_MODEL`),
     `local`→(`ollama_model`, `MEETING_OLLAMA_MODEL`).
   - Reject `none` / unknown provider and empty `model` → `{"ok": False, "error": …}`.
   - Else `persist_env_setting(project_root, env, model)` (same writer as
     `set_llm_provider`), `setattr(config, field, model)`, return
     `{"ok": True, "provider": provider, "model": model}`.

2. **`GET /api/llm`** — add `openai_model` and `gemini_model` to the response
   (it already returns `anthropic_model` + `ollama_model`).

3. **`POST /api/llm/model`** (`web/app.py`) — body `{provider, model}`:
   - `result = set_llm_model(config, provider, model)`; if not ok → 400 JSON.
   - If the watcher is running, `supervisor.restart()` (subprocess inherits env
     at start — same rationale as the provider endpoint).
   - Return `{"ok": True, "llm": {provider, label, anthropic_model, openai_model,
     gemini_model, ollama_model, valid_providers}}`.

## Frontend

4. **`types.ts`** — `Llm` gains `openai_model: string; gemini_model: string;`.

5. **`hooks/useApi.ts`** — `useSetModel()` mutation → `POST /api/llm/model`
   `{provider, model}`; on success invalidate `["llm"]` and `["health"]`.

6. **`pages/Settings.tsx`** — in the "Provedor LLM" card, below the provider
   `<select>`, add a **model picker** for the selected provider (hidden when
   provider is `none`):
   - `MODEL_OPTIONS: Record<string,string[]>` (frontend constant — UI sugar):
     - `anthropic`: claude-sonnet-4-20250514, claude-opus-4-20250514, claude-3-5-sonnet-latest, claude-3-5-haiku-latest
     - `openai`: gpt-4o, gpt-4o-mini, gpt-4.1, gpt-4.1-mini, o3-mini
     - `gemini`: gemini-2.0-flash, gemini-2.0-flash-lite, gemini-1.5-pro, gemini-1.5-flash
     - `local`: qwen2.5:14b, llama3.1:8b, mistral
   - The current model (from `/api/llm`: `<provider>_model`/`ollama_model`) is
     always included in the options (added if not in the curated list) and
     pre-selected.
   - A sentinel option **"Outro (personalizado)…"** (`__custom__`); selecting it
     reveals a text input for a free-form model id.
   - "Salvar modelo" button → `useSetModel.mutate({ provider, model })` with a
     success/error toast. Changing the provider dropdown reseeds the model from
     that provider's current value.

## Testing (TDD)

**Backend (`tests/`):**
- `set_llm_model(config, "gemini", "gemini-1.5-pro")` → ok, `config.gemini_model == "gemini-1.5-pro"`, and `.env`/env persisted (assert via `os.environ` or the config field).
- `set_llm_model(config, "none", "x")` → ok False; `set_llm_model(config, "gemini", "")` → ok False.
- `POST /api/llm/model {"provider":"openai","model":"gpt-4o-mini"}` → 200, body `llm.openai_model == "gpt-4o-mini"`; invalid provider → 400.
- `GET /api/llm` includes `openai_model` and `gemini_model`.

**Frontend (`frontend/src/__tests__/`):**
- Settings: with `provider: "gemini"`, `gemini_model: "gemini-2.0-flash"`, the
  model `<select>` shows the current value and a curated option (e.g.
  `gemini-1.5-pro`); selecting it + "Salvar modelo" POSTs
  `{provider:"gemini", model:"gemini-1.5-pro"}`.

## Out of scope

- A server-driven model catalog (curated list lives in the frontend for now).
- Editing API keys from the UI; validating the model id against the provider.
- Model picker in the TopBar (Settings only).
