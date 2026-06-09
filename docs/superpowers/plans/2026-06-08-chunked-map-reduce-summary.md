# Chunked Map-Reduce Summarization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Summarize transcripts of any length on a fixed local context window by chunking oversized transcripts (map) and merging the partial summaries (reduce), with zero behavior change for transcripts that already fit.

**Architecture:** All logic lives in `_BaseSummarizer` (`meeting_processor/summarizer.py`) and reuses the existing `_call_llm` + JSON parsing, so every provider inherits it. `summarize()` estimates the prompt's token count against the provider's context budget; if it fits, the current single-pass path runs unchanged, otherwise segments are split into context-sized chunks, each summarized, then merged — list fields programmatically, the narrative via one extra "reduce" LLM call.

**Tech Stack:** Python 3.14, Pydantic models, pytest. Tests use a `FakeSummarizer` subclass (stubbed `_call_llm`) — no network/LLM.

---

## File Structure

- **Modify** `meeting_processor/summarizer.py` — add constants (`_ERROR_SUMMARY`, `REDUCE_SYSTEM_PROMPT`, `_TOKEN_CHARS`, `_BUDGET_MARGIN`), refactor JSON extraction into `_extract_json`, add token-budget helpers, segment splitting, and map-reduce to `_BaseSummarizer`; add `context_token_budget` override to `OllamaSummarizer`.
- **Create** `tests/test_summary_chunking.py` — `FakeSummarizer` + unit/integration tests.

Run tests with `.venv/bin/python -m pytest`.

---

### Task 1: Constants + `_extract_json` refactor (no behavior change)

Pull the JSON-extraction logic out of `_parse_response` into a reusable static method, and introduce the module constants the later tasks need. Pure refactor — existing tests stay green.

**Files:**
- Modify: `meeting_processor/summarizer.py` (constants near `SYSTEM_PROMPT` ~line 88; `_parse_response`/`_empty_summary` ~lines 182-232; `__all__` ~line 610)

- [ ] **Step 1: Add module constants** after the `SYSTEM_PROMPT` block (after its closing `"""`):

```python
# Sentinela do resumo "falhou" — usada para detectar blocos que não puderam
# ser resumidos no caminho map-reduce.
_ERROR_SUMMARY = "Erro ao processar resumo da reunião."

# Estimativa de tokens: chars/_TOKEN_CHARS. Medido em PT + timestamps markdown
# (~2.5 chars/token). Conservador de propósito (superestima) para fragmentar um
# pouco antes em vez de estourar a janela de contexto.
_TOKEN_CHARS = 2.5
# Margem de segurança (tokens) reservada além do system prompt e da saída.
_BUDGET_MARGIN = 512

# System prompt do passo "reduce": combina resumos parciais em um só.
REDUCE_SYSTEM_PROMPT = """\
Você recebe vários resumos parciais de uma MESMA reunião, em ordem cronológica.
Combine-os em um único resumo coerente em português brasileiro.

Responda APENAS com JSON válido, sem markdown, sem blocos de código:

{
  "executive_summary": "Resumo executivo unificado de 3-5 frases cobrindo a reunião inteira",
  "purpose": "Uma frase com o objetivo central da reunião, ou string vazia"
}

Regras:
- Una as ideias dos trechos sem repetição; produza UM resumo executivo fluido.
- Não invente informação que não esteja nos resumos parciais.\
"""
```

- [ ] **Step 2: Add `_extract_json` static method** to `_BaseSummarizer`, immediately above `_parse_response`:

```python
    @staticmethod
    def _extract_json(response_text: str) -> dict | None:
        """Extrai um objeto JSON da resposta do LLM, ou ``None`` se não houver.

        Tolera blocos de código markdown e texto antes/depois do JSON (modelos
        locais às vezes adicionam preâmbulo).
        """
        cleaned = response_text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if not match:
                return None
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
```

- [ ] **Step 3: Rewrite `_parse_response`** to use it. Replace the whole method body (the `cleaned = ...` block through the `MeetingSummary(...)` return) with:

```python
    def _parse_response(self, response_text: str) -> MeetingSummary:
        data = self._extract_json(response_text)
        if data is None:
            logger.error("Não foi possível extrair JSON da resposta do LLM.")
            logger.debug("Resposta bruta: %s", response_text[:500])
            return self._empty_summary()

        return MeetingSummary(
            executive_summary=data.get("executive_summary", ""),
            time_windows=[
                TimeWindowSummary(**tw) for tw in data.get("time_windows", [])
            ],
            action_items=[ActionItem(**ai) for ai in data.get("action_items", [])],
            participants=data.get("participants", []),
            key_topics=data.get("key_topics", []),
            purpose=data.get("purpose", ""),
            meeting_type=data.get("meeting_type", ""),
            decisions=data.get("decisions", []),
            open_questions=data.get("open_questions", []),
        )
```

- [ ] **Step 4: Use the sentinel in `_empty_summary`.** Change its `executive_summary=` line to:

```python
            executive_summary=_ERROR_SUMMARY,
```

- [ ] **Step 5: Export `REDUCE_SYSTEM_PROMPT`.** In the `__all__` list add `"REDUCE_SYSTEM_PROMPT",` after `"SYSTEM_PROMPT",`.

- [ ] **Step 6: Run the existing suite to verify no behavior change**

Run: `.venv/bin/python -m pytest test_summarizer_mock.py tests/test_local_models.py -q`
Expected: PASS (the `test_factory_selects_anthropic` case may fail ONLY if `ANTHROPIC_API_KEY` is unset — that is pre-existing and unrelated).

- [ ] **Step 7: Commit**

```bash
git add meeting_processor/summarizer.py
git commit -m "refactor(summary): extract _extract_json + constants for map-reduce"
```

---

### Task 2: Token-budget primitives

**Files:**
- Modify: `meeting_processor/summarizer.py` (`_BaseSummarizer` methods; `OllamaSummarizer` ~line 300)
- Create: `tests/test_summary_chunking.py`

- [ ] **Step 1: Write the failing tests.** Create `tests/test_summary_chunking.py`:

```python
"""Map-reduce de transcrições longas: orçamento de tokens, divisão em blocos,
caminho single-pass (inalterado) e merge dos resumos parciais. Sem rede/LLM."""
from __future__ import annotations

import json

from meeting_processor.config import load_config
from meeting_processor.models import (
    ActionItem,
    MeetingSummary,
    TimeWindowSummary,
    Transcript,
    TranscriptSegment,
)
from meeting_processor.summarizer import (
    SYSTEM_PROMPT,
    REDUCE_SYSTEM_PROMPT,
    OllamaSummarizer,
    _BaseSummarizer,
    _BUDGET_MARGIN,
)


def _cfg():
    c = load_config()
    c.max_tokens_summary = 200      # orçamentos pequenos e previsíveis nos testes
    c.summary_chunk_minutes = 5
    c.ollama_num_ctx = 16384
    return c


class FakeSummarizer(_BaseSummarizer):
    """`_call_llm` devolve strings canned. Distingue map (SYSTEM_PROMPT) de
    reduce (REDUCE_SYSTEM_PROMPT) pelo system prompt. Se faltar resposta de map,
    repete a última (não precisamos saber a contagem exata de blocos)."""

    provider_name = "fake"

    def __init__(self, config, budget, map_responses=None, reduce_response="{}"):
        super().__init__(config)
        self._budget = budget
        self.map_responses = list(map_responses or ["{}"])
        self.reduce_response = reduce_response
        self.calls: list[tuple[str, str]] = []
        self._map_idx = 0

    @property
    def context_token_budget(self) -> int:
        return self._budget

    def _call_llm(self, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        if system_prompt == REDUCE_SYSTEM_PROMPT:
            return self.reduce_response
        i = min(self._map_idx, len(self.map_responses) - 1)
        self._map_idx += 1
        return self.map_responses[i]

    @property
    def map_calls(self):
        return [c for c in self.calls if c[0] != REDUCE_SYSTEM_PROMPT]

    @property
    def reduce_calls(self):
        return [c for c in self.calls if c[0] == REDUCE_SYSTEM_PROMPT]


def _segments(n, words=6):
    txt = "palavra " * words
    return [
        TranscriptSegment(start=float(i * 5), end=float(i * 5 + 5), text=f"{i:03d} {txt}")
        for i in range(n)
    ]


def _transcript(n):
    segs = _segments(n)
    return Transcript(
        segments=segs,
        full_text=" ".join(s.text for s in segs),
        language="pt",
        duration=segs[-1].end if segs else 0.0,
    )


def _summary_json(exec_summary, **kw):
    return json.dumps(
        {
            "executive_summary": exec_summary,
            "purpose": kw.get("purpose", ""),
            "meeting_type": kw.get("meeting_type", ""),
            "time_windows": kw.get("time_windows", []),
            "decisions": kw.get("decisions", []),
            "action_items": kw.get("action_items", []),
            "open_questions": kw.get("open_questions", []),
            "participants": kw.get("participants", []),
            "key_topics": kw.get("key_topics", []),
        }
    )


# --- Task 2: orçamento de tokens -------------------------------------------


def test_estimate_tokens_is_chars_over_ratio():
    assert _BaseSummarizer._estimate_tokens("x" * 250) == 100  # 250 / 2.5


def test_base_context_budget_is_large():
    assert _BaseSummarizer(_cfg()).context_token_budget == 200_000


def test_ollama_context_budget_is_num_ctx():
    cfg = _cfg()
    assert OllamaSummarizer(cfg).context_token_budget == cfg.ollama_num_ctx


def test_input_budget_reserves_system_and_output():
    s = OllamaSummarizer(_cfg())
    expected = (
        s.context_token_budget
        - s._estimate_tokens(SYSTEM_PROMPT)
        - s.config.max_tokens_summary
        - _BUDGET_MARGIN
    )
    assert s._input_token_budget() == expected
    assert 0 < s._input_token_budget() < s.context_token_budget


def test_input_budget_has_floor_for_tiny_context():
    assert FakeSummarizer(_cfg(), budget=100)._input_token_budget() == 1000
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_summary_chunking.py -q`
Expected: FAIL (`AttributeError: ... has no attribute '_estimate_tokens'` / `context_token_budget`).

- [ ] **Step 3: Implement the primitives.** First add the two module constants just after `_ERROR_SUMMARY` (near `SYSTEM_PROMPT`):

```python
# Estimativa de tokens: chars/_TOKEN_CHARS. Medido em PT + timestamps markdown
# (~2.5 chars/token). Conservador de propósito (superestima) para fragmentar um
# pouco antes em vez de estourar a janela de contexto.
_TOKEN_CHARS = 2.5
# Margem de segurança (tokens) reservada além do system prompt e da saída.
_BUDGET_MARGIN = 512
```

Then add to `_BaseSummarizer` (e.g. just after `__init__`):

```python
    @property
    def context_token_budget(self) -> int:
        """Tamanho efetivo da janela de contexto do provedor (em tokens).

        Padrão alto: provedores na nuvem (Claude/OpenAI/Gemini) têm janelas
        grandes e praticamente nunca precisam fragmentar. Subclasses locais
        sobrescrevem com o valor real.
        """
        return 200_000

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        import math

        return math.ceil(len(text) / _TOKEN_CHARS)

    def _input_token_budget(self) -> int:
        """Tokens disponíveis para a TRANSCRIÇÃO (fora system prompt + saída)."""
        budget = (
            self.context_token_budget
            - self._estimate_tokens(SYSTEM_PROMPT)
            - self.config.max_tokens_summary
            - _BUDGET_MARGIN
        )
        return max(budget, 1000)
```

Add to `OllamaSummarizer` (after its `__init__`):

```python
    @property
    def context_token_budget(self) -> int:
        return self.num_ctx
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_summary_chunking.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add meeting_processor/summarizer.py tests/test_summary_chunking.py
git commit -m "feat(summary): token-budget primitives for chunking"
```

---

### Task 3: Extract `_build_user_prompt` (no behavior change)

**Files:**
- Modify: `meeting_processor/summarizer.py` (`_BaseSummarizer.summarize` ~lines 118-146)

- [ ] **Step 1: Add the helper** to `_BaseSummarizer` (above `summarize`):

```python
    def _build_user_prompt(
        self, source_filename: str, duration: float, chunked_text: str
    ) -> str:
        return (
            f"Arquivo de origem: {source_filename}\n"
            f"Duração total: {format_duration(duration)}\n\n"
            f"--- TRANSCRIÇÃO ---\n\n{chunked_text}"
        )
```

- [ ] **Step 2: Use it in `summarize`.** Replace the inline `user_prompt = (...)` assignment in `summarize` with:

```python
        user_prompt = self._build_user_prompt(
            source_filename, transcript.duration, chunked_text
        )
```

- [ ] **Step 3: Run the suite to verify no behavior change**

Run: `.venv/bin/python -m pytest tests/test_summary_chunking.py test_summarizer_mock.py -q`
Expected: PASS (same as before; `test_factory_selects_anthropic` may fail only if `ANTHROPIC_API_KEY` unset — pre-existing).

- [ ] **Step 4: Commit**

```bash
git add meeting_processor/summarizer.py
git commit -m "refactor(summary): extract _build_user_prompt"
```

---

### Task 4: Segment splitting

**Files:**
- Modify: `meeting_processor/summarizer.py` (`_BaseSummarizer`)
- Test: `tests/test_summary_chunking.py`

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_summary_chunking.py`:

```python
# --- Task 4: divisão em blocos ---------------------------------------------


def test_split_preserves_all_segments_in_order():
    s = FakeSummarizer(_cfg(), budget=16384)
    segs = _segments(10)
    chunks = s._split_segments(segs, char_budget=200)
    flat = [seg for chunk in chunks for seg in chunk]
    assert flat == segs
    assert len(chunks) > 1


def test_split_respects_char_budget_except_single_segment():
    s = FakeSummarizer(_cfg(), budget=16384)
    segs = _segments(10)
    budget = 200
    for chunk in s._split_segments(segs, char_budget=budget):
        total = sum(len(seg.text) + 32 for seg in chunk)
        assert len(chunk) == 1 or total <= budget


def test_split_single_chunk_when_under_budget():
    s = FakeSummarizer(_cfg(), budget=16384)
    segs = _segments(3)
    assert len(s._split_segments(segs, char_budget=100_000)) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_summary_chunking.py -k split -q`
Expected: FAIL (`AttributeError: ... '_split_segments'`).

- [ ] **Step 3: Implement `_split_segments`** in `_BaseSummarizer`:

```python
    @staticmethod
    def _split_segments(
        segments: list[TranscriptSegment], char_budget: int
    ) -> list[list[TranscriptSegment]]:
        """Agrupa segmentos sequenciais em blocos sob ``char_budget`` chars.

        Nunca divide um segmento; um segmento maior que o orçamento vira um
        bloco sozinho. ``+ 32`` por segmento aproxima o overhead do timestamp
        markdown adicionado por ``_build_chunked_transcript``.
        """
        chunks: list[list[TranscriptSegment]] = []
        current: list[TranscriptSegment] = []
        current_len = 0
        for seg in segments:
            seg_len = len(seg.text) + 32
            if current and current_len + seg_len > char_budget:
                chunks.append(current)
                current = []
                current_len = 0
            current.append(seg)
            current_len += seg_len
        if current:
            chunks.append(current)
        return chunks
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_summary_chunking.py -k split -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add meeting_processor/summarizer.py tests/test_summary_chunking.py
git commit -m "feat(summary): split segments into context-sized chunks"
```

---

### Task 5: Reduce — merge partials (programmatic lists + narrative LLM call)

**Files:**
- Modify: `meeting_processor/summarizer.py` (`_BaseSummarizer`)
- Test: `tests/test_summary_chunking.py`

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_summary_chunking.py`:

```python
# --- Task 5: reduce / merge -------------------------------------------------


def _partials():
    return [
        MeetingSummary(
            executive_summary="Parte A",
            time_windows=[TimeWindowSummary(start_minutes=0, end_minutes=5, summary="x")],
            action_items=[ActionItem(description="Tarefa 1")],
            participants=["Ana"],
            key_topics=["t1"],
            purpose="obj A",
            meeting_type="",
            decisions=["d1"],
            open_questions=[],
        ),
        MeetingSummary(
            executive_summary="Parte B",
            time_windows=[TimeWindowSummary(start_minutes=5, end_minutes=10, summary="y")],
            action_items=[ActionItem(description="tarefa 1"), ActionItem(description="Tarefa 2")],
            participants=["ana", "Bia"],
            key_topics=["t1", "t2"],
            purpose="obj B",
            meeting_type="daily",
            decisions=["d1", "d2"],
            open_questions=["q1"],
        ),
    ]


def test_reduce_merges_lists_programmatically():
    s = FakeSummarizer(_cfg(), budget=16384, reduce_response=_summary_json("merged", purpose="P"))
    out = s._reduce_partials(_partials())
    assert [tw.summary for tw in out.time_windows] == ["x", "y"]            # ordem
    assert [a.description for a in out.action_items] == ["Tarefa 1", "Tarefa 2"]  # dedup case-insensitive
    assert out.participants == ["Ana", "Bia"]                               # dedup, ordem preservada
    assert out.key_topics == ["t1", "t2"]
    assert out.decisions == ["d1", "d2"]
    assert out.open_questions == ["q1"]
    assert out.meeting_type == "daily"                                      # 1º não-vazio


def test_reduce_uses_llm_narrative():
    s = FakeSummarizer(_cfg(), budget=16384, reduce_response=_summary_json("RESUMO FINAL", purpose="P"))
    out = s._reduce_partials(_partials())
    assert out.executive_summary == "RESUMO FINAL"
    assert out.purpose == "P"
    assert len(s.reduce_calls) == 1


def test_reduce_narrative_falls_back_on_bad_json():
    s = FakeSummarizer(_cfg(), budget=16384, reduce_response="desculpe, não consegui")
    out = s._reduce_partials(_partials())
    assert out.executive_summary == "Parte A\n\nParte B"   # concatenação dos parciais
    assert out.purpose == "obj A"                           # 1º purpose não-vazio
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_summary_chunking.py -k reduce -q`
Expected: FAIL (`AttributeError: ... '_reduce_partials'`).

- [ ] **Step 3: Implement the reduce helpers** in `_BaseSummarizer`:

```python
    @staticmethod
    def _dedupe_strings(items: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for it in items:
            key = it.strip().lower()
            if key and key not in seen:
                seen.add(key)
                out.append(it)
        return out

    @staticmethod
    def _dedupe_action_items(items: list[ActionItem]) -> list[ActionItem]:
        seen: set[str] = set()
        out: list[ActionItem] = []
        for ai in items:
            key = ai.description.strip().lower()
            if key and key not in seen:
                seen.add(key)
                out.append(ai)
        return out

    def _reduce_narrative(self, partials: list[MeetingSummary]) -> tuple[str, str]:
        """Sintetiza executive_summary + purpose via uma chamada LLM 'reduce'.

        Em qualquer falha (sem JSON, erro de chamada), cai para a concatenação
        dos resumos parciais — nunca perde conteúdo.
        """
        fallback_summary = "\n\n".join(
            p.executive_summary for p in partials if p.executive_summary
        )
        fallback_purpose = next((p.purpose for p in partials if p.purpose), "")

        blocks = []
        for i, p in enumerate(partials, 1):
            parts = [f"[Trecho {i}] {p.executive_summary}"]
            if p.key_topics:
                parts.append("Tópicos: " + ", ".join(p.key_topics))
            if p.decisions:
                parts.append("Decisões: " + "; ".join(p.decisions))
            blocks.append("\n".join(parts))
        user_prompt = "Resumos parciais (em ordem):\n\n" + "\n\n".join(blocks)

        try:
            data = self._extract_json(self._call_llm(REDUCE_SYSTEM_PROMPT, user_prompt))
            if data is None:
                raise ValueError("reduce sem JSON")
            return (
                data.get("executive_summary") or fallback_summary,
                data.get("purpose") or fallback_purpose,
            )
        except Exception as e:  # noqa: BLE001 — degradação graciosa
            logger.warning(
                "Reduce do resumo falhou (%s); usando concatenação dos parciais.", e
            )
            return fallback_summary, fallback_purpose

    def _reduce_partials(self, partials: list[MeetingSummary]) -> MeetingSummary:
        """Combina resumos parciais: listas no código, narrativa via LLM."""
        if not partials:
            return self._empty_summary()

        executive_summary, purpose = self._reduce_narrative(partials)
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
            decisions=self._dedupe_strings([x for p in partials for x in p.decisions]),
            open_questions=self._dedupe_strings(
                [x for p in partials for x in p.open_questions]
            ),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_summary_chunking.py -k reduce -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add meeting_processor/summarizer.py tests/test_summary_chunking.py
git commit -m "feat(summary): hybrid reduce of partial summaries"
```

---

### Task 6: Map + wire the branch into `summarize()`

**Files:**
- Modify: `meeting_processor/summarizer.py` (`_BaseSummarizer.summarize` + new `_map_reduce_summarize`)
- Test: `tests/test_summary_chunking.py`

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_summary_chunking.py`:

```python
# --- Task 6: integração summarize() single-pass vs map-reduce ---------------


def test_short_transcript_is_single_pass():
    s = FakeSummarizer(
        _cfg(), budget=200_000, map_responses=[_summary_json("um pass só")]
    )
    out = s.summarize(_transcript(3), "reuniao.mp4")
    assert out.executive_summary == "um pass só"
    assert len(s.map_calls) == 1
    assert len(s.reduce_calls) == 0


def test_long_transcript_maps_then_reduces():
    # orçamento pequeno => muitos blocos; transcrição grande o bastante p/ dividir
    s = FakeSummarizer(
        _cfg(),
        budget=2000,
        map_responses=[_summary_json("parcial")],
        reduce_response=_summary_json("RESUMO FINAL", purpose="P"),
    )
    out = s.summarize(_transcript(120), "reuniao.mp4")
    assert len(s.map_calls) >= 2            # dividiu em vários blocos
    assert len(s.reduce_calls) == 1         # exatamente um reduce
    assert out.executive_summary == "RESUMO FINAL"


def test_bad_chunk_is_skipped_not_fatal():
    # 1º bloco retorna lixo (vira _empty_summary e é ignorado), 2º é válido
    s = FakeSummarizer(
        _cfg(),
        budget=2000,
        map_responses=["isso não é json", _summary_json("parcial bom", participants=["Ana"])],
        reduce_response=_summary_json("RESUMO FINAL"),
    )
    out = s.summarize(_transcript(120), "reuniao.mp4")
    assert out.executive_summary == "RESUMO FINAL"   # não quebrou
    assert "Ana" in out.participants                  # bloco bom contribuiu
```

Note: `FakeSummarizer` repeats its last `map_responses` entry, so a single-element list answers every chunk; the two-element list in the last test answers chunk 1 with garbage and every later chunk with the good summary.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_summary_chunking.py -k "single_pass or maps_then or bad_chunk" -q`
Expected: FAIL (`summarize` still always single-pass → `reduce_calls == 0`, `map_calls == 1`).

- [ ] **Step 3: Implement `_map_reduce_summarize`** in `_BaseSummarizer`:

```python
    def _map_reduce_summarize(
        self, transcript: Transcript, source_filename: str, system_prompt: str
    ) -> MeetingSummary:
        """Resume uma transcrição que não cabe na janela: divide, resume cada
        bloco (map) e combina (reduce)."""
        char_budget = int(self._input_token_budget() * _TOKEN_CHARS)
        chunks = self._split_segments(transcript.segments, char_budget)
        logger.info(
            "Transcrição grande para '%s': %d segmentos em %d blocos (map-reduce).",
            self.provider_name,
            len(transcript.segments),
            len(chunks),
        )

        partials: list[MeetingSummary] = []
        for i, chunk in enumerate(chunks, 1):
            chunked_text = self._build_chunked_transcript(
                chunk, self.config.summary_chunk_minutes
            )
            user_prompt = self._build_user_prompt(
                source_filename, transcript.duration, chunked_text
            )
            logger.info("  Resumindo bloco %d/%d (%d segmentos)...", i, len(chunks), len(chunk))
            partial = self._parse_response(self._call_llm(system_prompt, user_prompt))
            if partial.executive_summary == _ERROR_SUMMARY:
                logger.warning("  Bloco %d não pôde ser resumido; ignorando.", i)
                continue
            partials.append(partial)

        return self._reduce_partials(partials)
```

- [ ] **Step 4: Wire the branch into `summarize()`.** In `summarize`, replace the block that currently logs "Enviando transcrição..." and does `response_text = self._call_llm(...)` / `summary = self._parse_response(...)` with:

```python
        if self._estimate_tokens(user_prompt) <= self._input_token_budget():
            logger.info(
                "Enviando transcrição ao provedor '%s' para resumo...",
                self.provider_name,
            )
            summary = self._parse_response(self._call_llm(system_prompt, user_prompt))
        else:
            summary = self._map_reduce_summarize(
                transcript, source_filename, system_prompt
            )
```

(The surrounding `chunked_text` / `system_prompt` / `user_prompt` setup above and the final summary `logger.info(...)` / `return summary` stay as they are.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_summary_chunking.py -q`
Expected: PASS (all tests in the file).

- [ ] **Step 6: Run the full suite for regressions**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS except the pre-existing `test_summarizer_mock.py::test_factory_selects_anthropic` (only if `ANTHROPIC_API_KEY` unset).

- [ ] **Step 7: Commit**

```bash
git add meeting_processor/summarizer.py tests/test_summary_chunking.py
git commit -m "feat(summary): chunked map-reduce for oversized transcripts"
```

---

## Self-Review

**Spec coverage:**
- Token estimation `/2.5`, conservative → Task 2 (`_estimate_tokens`). ✓
- Single-pass budget + no-regression trigger → Task 2 (`_input_token_budget`), Task 6 (branch, `test_short_transcript_is_single_pass`). ✓
- `context_token_budget` per provider (Ollama=num_ctx, base large) → Task 2. ✓
- Split into context-sized chunks, never split a segment → Task 4. ✓
- Map reuse `_call_llm`+`_parse_response`; skip bad chunk → Task 6 (`_map_reduce_summarize`, `test_bad_chunk_is_skipped_not_fatal`). ✓
- Hybrid reduce: programmatic lists + one narrative LLM call + fallback → Task 5. ✓
- `REDUCE_SYSTEM_PROMPT`, exported → Task 1. ✓
- Empty partials → `_empty_summary()` (existing error path) → Task 5 (`_reduce_partials` guard). ✓
- All providers inherit (logic in `_BaseSummarizer`) → Tasks 2-6. ✓

**Placeholder scan:** none — every step has concrete code/commands.

**Type consistency:** `_extract_json -> dict | None` (Task 1) used by `_parse_response` (Task 1) and `_reduce_narrative` (Task 5). `context_token_budget` property defined base (Task 2) + Ollama override (Task 2), read by `_input_token_budget` (Task 2). `_input_token_budget` used by branch (Task 6) and `_map_reduce_summarize` (Task 6). `_split_segments(segments, char_budget)` (Task 4) called in Task 6. `_reduce_partials(partials)` (Task 5) called in Task 6. `_build_user_prompt(source_filename, duration, chunked_text)` (Task 3) used in `summarize` and Task 6. Sentinel `_ERROR_SUMMARY` set in `_empty_summary` (Task 1), compared in Task 6. Names consistent throughout. ✓
