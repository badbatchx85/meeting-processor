"""Parser/prompt coverage for the new structured summary fields."""
from meeting_processor.config import load_config
from meeting_processor.summarizer import _BaseSummarizer


class _Parser(_BaseSummarizer):
    """Concrete subclass so we can call the inherited _parse_response."""
    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:  # pragma: no cover
        return ""


def _parser() -> _Parser:
    return _Parser(load_config())


def test_parse_maps_new_fields():
    raw = """{
      "executive_summary": "ok",
      "time_windows": [],
      "action_items": [],
      "participants": [],
      "key_topics": [],
      "purpose": "Alinhar o roadmap do trimestre",
      "meeting_type": "planejamento",
      "decisions": ["Adiar o lançamento para julho"],
      "open_questions": ["Quem assume o suporte?"]
    }"""
    s = _parser()._parse_response(raw)
    assert s.purpose == "Alinhar o roadmap do trimestre"
    assert s.meeting_type == "planejamento"
    assert s.decisions == ["Adiar o lançamento para julho"]
    assert s.open_questions == ["Quem assume o suporte?"]


def test_parse_applies_defaults_when_fields_absent():
    raw = """{
      "executive_summary": "ok",
      "time_windows": [],
      "action_items": [],
      "participants": [],
      "key_topics": []
    }"""
    s = _parser()._parse_response(raw)
    assert s.purpose == ""
    assert s.meeting_type == ""
    assert s.decisions == []
    assert s.open_questions == []


def test_system_prompt_documents_new_fields():
    from meeting_processor.summarizer import SYSTEM_PROMPT
    for key in ("purpose", "meeting_type", "decisions", "open_questions"):
        assert key in SYSTEM_PROMPT
