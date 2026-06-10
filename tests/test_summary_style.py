"""Estilo do resumo: timeline (com períodos) vs plain (sem períodos)."""
import json

from meeting_processor.models import Transcript, TranscriptSegment
from meeting_processor.summarizer import _BaseSummarizer


class _StyleFake(_BaseSummarizer):
    provider_name = "fake"

    def __init__(self, config):
        super().__init__(config)
        self.captured: list[str] = []

    def _call_llm(self, system_prompt, user_prompt):
        self.captured.append(system_prompt)
        return json.dumps({
            "executive_summary": "x", "time_windows": [], "action_items": [],
            "participants": [], "key_topics": [],
        })


def _tiny():
    s = TranscriptSegment(start=0.0, end=1.0, text="oi")
    return Transcript(segments=[s], full_text="oi", language="pt", duration=1.0)


def test_plain_style_adds_directive(config):
    f = _StyleFake(config)
    f.summarize(_tiny(), "a.mp4", style="plain")
    assert "MODO RESUMO SIMPLES" in f.captured[0]


def test_timeline_style_no_directive(config):
    f = _StyleFake(config)
    f.summarize(_tiny(), "a.mp4", style="timeline")
    assert "MODO RESUMO SIMPLES" not in f.captured[0]


def test_style_defaults_to_config(config):
    config.summary_style = "plain"
    f = _StyleFake(config)
    f.summarize(_tiny(), "a.mp4")
    assert "MODO RESUMO SIMPLES" in f.captured[0]


# --- Task 2: pipeline threads style ----------------------------------------

from datetime import datetime
from meeting_processor.models import MeetingSummary
from meeting_processor.pipeline import MeetingPipeline


class _CapSumm:
    def __init__(self):
        self.style = "UNSET"
    def summarize(self, transcript, source_file, style=None):
        self.style = style
        return MeetingSummary(executive_summary="x", time_windows=[], action_items=[],
                              participants=[], key_topics=[])


def test_summarize_forwards_style(config):
    pipe = MeetingPipeline(config)
    fake = _CapSumm()
    pipe.summarizer = fake   # pre-set so _summarize won't construct a real one
    paths = pipe.note_generator.prepare("x.mp4", datetime.now())
    job = pipe.dashboard.new_job("x.mp4")
    pipe._summarize(_tiny(), paths, "x.mp4", datetime.now(), job,
                    {"summary": True, "note": False, "kanban": False, "wiki": False},
                    style="plain")
    assert fake.style == "plain"
