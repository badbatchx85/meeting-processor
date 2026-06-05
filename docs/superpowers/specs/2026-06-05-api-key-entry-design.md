# API Key Entry in the Front-end + Local-model Suggestions

**Date:** 2026-06-05
**Status:** Approved design

## Goal

Let the user enter/save API keys for the cloud providers (Anthropic, OpenAI,
Gemini) from Settings — today only `.env` works. Keys are write-only: stored in
the local `.env` and never returned to the UI or logged. Also refresh the local
(Ollama) model dropdown with options tuned for an Apple M5 / 16 GB machine.

## Security model

- Keys persist in the local `.env` (plaintext, gitignored) — the existing
  local, single-user model. No encryption/vault (out of scope; surfaced to user).
- The key value is **never** sent back: `GET /api/llm` exposes only booleans
  (`anthropic_key_set`, `openai_key_set`, `gemini_key_set`). `POST /api/llm/key`
  returns the same booleans, not the key. The key value is **not logged**.
- Frontend uses `type="password"` inputs; the field is write-only (never
  prefilled with the stored key).

## Backend

1. **`meeting_processor/web/runtime.py`** — `set_llm_key(config, provider, key) -> dict`:
   - Normalize provider (`ollama`→`local`). Map provider → (field, env var):
     `anthropic`→(`anthropic_api_key`, `ANTHROPIC_API_KEY`),
     `openai`→(`openai_api_key`, `OPENAI_API_KEY`),
     `gemini`→(`gemini_api_key`, `GEMINI_API_KEY`).
   - Reject providers without keys (`local`, `none`, unknown) and empty key →
     `{"ok": False, "error": …}`.
   - Else `persist_env_setting(project_root, env, key)` (writes `.env` + sets
     `os.environ`, so it takes effect immediately and the watcher inherits it),
     `setattr(config, field, key)`, `logger.info("Chave de API de %s atualizada.")`
     (no value), return `{"ok": True, "provider": provider}`.

2. **`GET /api/llm`** (`_llm_info`) — add `openai_key_set` and `gemini_key_set`
   (already returns `anthropic_key_set`).

3. **`POST /api/llm/key`** (`web/app.py`) — body `{provider, key}`:
   - `set_llm_key(...)`; if not ok → 400 JSON.
   - Restart watcher if running. Return `{"ok": True, "llm": _llm_info()}`.

## Frontend

4. **`types.ts`** — `Llm` gains `openai_key_set: boolean; gemini_key_set: boolean;`.
5. **`hooks/useApi.ts`** — `useSetKey()` mutation → `POST /api/llm/key`
   `{provider, key}`; on success invalidate `["llm"]`.
6. **`pages/Settings.tsx`** — in the "Provedor LLM" card, for the selected
   provider when it needs a key (`anthropic`/`openai`/`gemini`): a **password**
   input + "Salvar chave" button + a "✓ configurada" / "não configurada" badge
   from `*_key_set`. Local state cleared after a successful save; placeholder
   indicates whether a key is already set. Never display the stored key.
7. **`MODEL_OPTIONS.local`** → `["qwen2.5:7b", "qwen2.5:14b", "llama3.1:8b", "gemma2:9b"]`
   (7b first as the suggested default for M5/16 GB).

## Testing (TDD)

**Backend (`tests/`):**
- `set_llm_key(config, "openai", "sk-x")` → ok, `config.openai_api_key == "sk-x"`.
- Rejects `local`/`none`/unknown provider and empty key.
- `GET /api/llm` includes `openai_key_set` + `gemini_key_set`, and the response
  contains **no** raw key value.
- `POST /api/llm/key {"provider":"gemini","key":"AIza-x"}` → 200,
  `llm.gemini_key_set is True`, response body has no key value; invalid provider
  → 400.

**Frontend (`frontend/src/__tests__/`):**
- Settings with `provider:"openai"`, `openai_key_set:false`: a password field +
  "Salvar chave"; typing a key + save POSTs `{provider:"openai", key:"sk-test"}`.
- The local model dropdown lists `qwen2.5:7b`.

## Out of scope

- Encrypting keys / OS keychain integration.
- Editing `*_base_url` from the UI (still `.env`).
- Validating the key against the provider (a bad key surfaces as a run error in
  the Conversões history).
