# Local (Ollama) Models: List Installed + Download

**Date:** 2026-06-05
**Status:** Approved design

## Goal

When the provider is `local`, show which Ollama models are **actually installed**
on the machine (querying Ollama), let the user pick one, and — if none are
installed — offer a **Baixar** button to download a recommended model (plus the
manual command). Detect when Ollama isn't running.

## Backend (`meeting_processor/web/app.py`)

Suggested set (reuses the M5/16GB recommendation):
`_LOCAL_SUGGESTED = ["qwen2.5:7b", "qwen2.5:14b", "llama3.1:8b", "gemma2:9b"]`.

1. `_ollama_installed(base_url) -> list[str] | None` — `GET {base_url}/api/tags`
   via httpx (timeout ~2s). Reachable → list of model names (possibly empty);
   any error/unreachable → `None`.

2. `GET /api/llm/local-models` →
   `{"ollama_running": installed is not None, "installed": installed or [],
     "suggested": [m for m in _LOCAL_SUGGESTED if m not in installed]}`.

3. `_ollama_pull(base_url, model)` — `POST {base_url}/api/pull` (httpx stream,
   drained to completion; logs start/finish/failure). No shell.

4. `POST /api/llm/local-models/pull {model}` — empty model → 400; else spawn a
   daemon thread running `_ollama_pull(config.ollama_base_url, model)` and return
   `{"ok": True, "queued": True, "model": model}`. (Progress not streamed in v1;
   user clicks Atualizar when done.)

## Frontend

5. `types.ts` — `LocalModels { ollama_running: boolean; installed: string[]; suggested: string[] }`.
6. `hooks/useApi.ts` — `useLocalModels()` query (`["local-models"]`, enabled when
   provider is `local`); `usePullModel()` mutation → `POST …/pull {model}`,
   on success invalidate `["local-models"]`.
7. `pages/Settings.tsx` — when `provider === "local"`, replace the static model
   dropdown with Ollama-driven UI + an **Atualizar** button (refetch):
   - Ollama **not running** → notice: "Ollama não está rodando" + `ollama serve` /
     install hint (https://ollama.com). No model dropdown.
   - running **with** installed models → model `<select>` of the **installed**
     names (current preserved) + "Salvar modelo" (existing `useSetModel`).
   - running **without** models → "Nenhum modelo instalado." + the `suggested`
     list, each row: model name + **Baixar** button (`usePullModel`) + the
     `ollama pull <model>` command as a copyable fallback. Pull → toast "Baixando
     <model>… pode demorar; clique Atualizar quando terminar."
   - Non-`local` providers keep the curated `MODEL_OPTIONS` dropdown + key field.

## Testing (TDD)

**Backend (`tests/`):**
- `GET /api/llm/local-models` with `_ollama_installed` monkeypatched to
  `["qwen2.5:7b"]` → `ollama_running True`, `installed` has it, `suggested`
  excludes it; monkeypatched to `None` → `ollama_running False`, suggested =
  full list.
- `POST /api/llm/local-models/pull {"model":""}` → 400; `{"model":"llama3.1:8b"}`
  → 200 `queued` (with `_ollama_pull` monkeypatched to a no-op).

**Frontend (`frontend/src/__tests__/`):**
- provider `local`, installed `["qwen2.5:7b"]` → model dropdown lists it.
- provider `local`, none installed (running) → a **Baixar** button that POSTs
  `{model}` to the pull endpoint.
- provider `local`, ollama_running false → the "não está rodando" notice.

## Out of scope

- Streaming pull progress into the UI (v1: background + manual Atualizar).
- Deleting local models; switching Ollama base URL from the UI.
