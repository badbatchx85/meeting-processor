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
    assert out.decisions == ["Orçamento aprovado"]
    assert out.open_questions == ["Quem assume o deploy?"]
    assert out.executive_summary == "RES"


def test_reduce_falls_back_on_bad_json(config):
    out = _ReduceFake(config, "desculpe, não consegui")._reduce_partials(_partials())
    assert set(out.decisions) == {"Aprovado o orçamento", "Orçamento aprovado"}
    assert out.open_questions == ["Quem assume o deploy?"]


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
