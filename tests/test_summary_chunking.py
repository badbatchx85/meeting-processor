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


# --- _extract_json só devolve dict --------------------------------------


def test_extract_json_rejects_non_dict_and_parses_dict():
    assert _BaseSummarizer._extract_json('{"a": 1}') == {"a": 1}
    assert _BaseSummarizer._extract_json("[1, 2, 3]") is None
    assert _BaseSummarizer._extract_json("texto sem json") is None
    # objeto embutido em texto/array ainda é recuperado:
    assert _BaseSummarizer._extract_json('lixo [{"a": 1}] fim') == {"a": 1}
