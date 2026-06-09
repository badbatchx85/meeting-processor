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
