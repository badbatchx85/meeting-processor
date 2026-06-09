# Chunked Map-Reduce Summarization

**Date:** 2026-06-08
**Status:** Approved design

## Goal

Summarize transcripts of **any length** on a fixed local context window, with no
regression for short meetings.

### Root cause this fixes

A 45-minute transcript tokenizes to ~17,200 tokens, which exceeds the local
model's configured context window (`ollama_num_ctx = 16384`). Ollama truncates
the prompt to fill the window, leaving ~1 token for output. With `format: "json"`
the model emits a lone `{`, hits the length limit (`done_reason = length`), and
stops. The unparseable `{` falls through `_parse_response` → `_empty_summary()`,
whose `executive_summary` is the string **"Erro ao processar resumo da
reunião."** — silently written into the note. Verified directly against Ollama:
`prompt_eval_count = 16383`, `eval_count = 1`, `content = "{"`. Raising `num_ctx`
to 32768 produced a complete, valid summary (`done_reason = stop`), confirming
the diagnosis: the input simply doesn't fit alongside the output budget.

The prompt is **not** the problem; context budget is.

## Architecture (DRY)

All changes live in `_BaseSummarizer` (`meeting_processor/summarizer.py`). The
map/reduce logic reuses the existing `_call_llm` + `_parse_response` hooks, so
**every provider** (Ollama, Anthropic, OpenAI) inherits it. Each summarizer
exposes its effective context budget via a new property:

- `OllamaSummarizer.context_token_budget` → `self.num_ctx`
- `_BaseSummarizer.context_token_budget` (default) → a large value (200_000) so
  cloud providers effectively never chunk.

## Backend changes (`meeting_processor/summarizer.py`)

1. **Token estimation** — `_estimate_tokens(text: str) -> int` returns
   `ceil(len(text) / 2.5)`. The `/2.5` ratio was measured on PT + markdown
   timestamps (43,088 chars → 17,216 tokens ≈ 2.50). Intentionally conservative
   (over-counts) so we chunk slightly early rather than overflow. No tokenizer
   dependency.

2. **Single-pass budget** — `_input_token_budget() -> int` returns
   `context_token_budget − _estimate_tokens(SYSTEM_PROMPT) − max_tokens_summary
   − MARGIN` (MARGIN = 512). Floored at a small positive minimum.

3. **`summarize()` branch** — after building `chunked_text`/`user_prompt`
   (unchanged), if `_estimate_tokens(system_prompt + user_prompt) <=
   _input_token_budget()` → **single-pass path, behavior unchanged** (one
   `_call_llm`, same logging). Else → `_map_reduce_summarize(...)`.

4. **Split** — `_split_segments(segments, char_budget) -> list[list[segment]]`:
   accumulate segments (using each segment's rendered length) until adding the
   next would exceed `char_budget`, then start a new chunk. Never splits a
   segment. `char_budget = _input_token_budget() * 2.5`. A single segment larger
   than the budget gets its own chunk (best effort).

5. **Map** — `_map_reduce_summarize(segments, source_filename, duration)`:
   for each chunk, build the same user prompt over that chunk's text and call
   `_call_llm` + `_parse_response` → partial `MeetingSummary`. A chunk whose
   parse yields the empty/error sentinel is logged (`warning`) and skipped, not
   merged. Log `info`: number of chunks.

6. **Reduce (hybrid)** — `_reduce_partials(partials) -> MeetingSummary`:
   - **Programmatic (deterministic facts):**
     - `time_windows` = concatenation of all partials' windows in order
       (chunks are already sequential in time).
     - `action_items` = concatenation, deduped by normalized `description`.
     - `participants` / `key_topics` / `decisions` / `open_questions` =
       order-preserving union-dedupe (case-insensitive).
     - `meeting_type` = first non-empty.
   - **Narrative (one LLM call):** `_reduce_narrative(partials) ->
     (executive_summary, purpose)`. Build a compact user prompt from the
     partials' `executive_summary` + `key_topics` + `decisions`; call `_call_llm`
     with a new `REDUCE_SYSTEM_PROMPT` (also `format: "json"` for Ollama) and
     parse `{executive_summary, purpose}`. On any failure/truncation, **fall
     back** to `"\n\n".join(p.executive_summary for p in partials)` and the first
     non-empty `purpose`.
   - If `partials` is empty (every chunk failed) → return `_empty_summary()`
     (existing error path preserved).

7. **`REDUCE_SYSTEM_PROMPT`** — new module-level constant: instructs the model to
   merge several partial meeting summaries into one coherent executive summary +
   purpose, returning a small JSON object `{"executive_summary": "...",
   "purpose": "..."}`. Added to `__all__`.

## Testing (TDD) — `tests/test_summary_chunking.py`

A `FakeSummarizer(_BaseSummarizer)` subclass with a stubbed `_call_llm` (records
calls; returns canned JSON keyed by a marker in the prompt) and a small
`context_token_budget`, so **no LLM/network**:

- **Short transcript → single-pass:** below budget ⇒ exactly one `_call_llm`,
  returned summary matches the canned single-pass JSON (no behavior change).
- **Long transcript → map-reduce:** above budget ⇒ `_call_llm` invoked
  `n_chunks + 1` times (maps + one reduce); result has merged fields.
- **List merge:** `time_windows` preserved in order; duplicate `action_items`
  across chunks deduped; `key_topics`/`participants` unioned.
- **Bad chunk skipped:** one map call returns non-JSON garbage ⇒ that chunk
  contributes nothing, other chunks still merged, no crash.
- **Reduce fallback:** the reduce `_call_llm` returns garbage ⇒
  `executive_summary` falls back to the concatenated partial summaries.
- **`_estimate_tokens` / `_split_segments`:** splitting respects the char budget
  and never splits a segment; estimate is monotonic in length.

## Out of scope

- No change to `ollama_num_ctx` default, the main `SYSTEM_PROMPT` content, the
  pipeline, or the frontend.
- The existing "summary failure silently marks the job completed" behavior is
  left as-is (it was the alternative fix option; chunking makes failure far less
  likely).
- No streaming, no parallel chunk calls (sequential is simpler; map calls are
  CPU-bound on a local model anyway).
