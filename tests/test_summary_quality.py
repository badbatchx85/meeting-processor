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
