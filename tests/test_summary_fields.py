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


def _summary_with_new_fields():
    from meeting_processor.models import MeetingSummary
    return MeetingSummary(
        executive_summary="Resumo.",
        time_windows=[],
        action_items=[],
        participants=["Ana"],
        key_topics=["Roadmap"],
        purpose="Alinhar o roadmap do trimestre",
        meeting_type="planejamento",
        decisions=["Adiar o lançamento para julho"],
        open_questions=["Quem assume o suporte?"],
    )


def test_note_includes_new_frontmatter_and_sections(tmp_path):
    from datetime import datetime
    from meeting_processor.config import load_config
    from meeting_processor.models import Transcript
    from meeting_processor.note_generator import NoteGenerator

    cfg = load_config()
    cfg.project_root = str(tmp_path)
    cfg.vault_dir = "vault"
    transcript = Transcript(segments=[], full_text="", language="pt", duration=60.0)
    gen = NoteGenerator(cfg)
    note = gen._build_note(
        title="2026-06-04 10h00 - reuniao",
        summary=_summary_with_new_fields(),
        transcript=transcript,
        source_file="reuniao.mp4",
        date_str="2026-06-04",
        created_at=datetime(2026, 6, 4, 10, 0),
    )
    # frontmatter scalars
    assert 'meeting_type: "planejamento"' in note
    assert 'purpose: "Alinhar o roadmap do trimestre"' in note
    # body sections
    assert "## Propósito" in note
    assert "## Decisões" in note
    assert "- Adiar o lançamento para julho" in note
    assert "## Questões em Aberto" in note
    assert "- Quem assume o suporte?" in note
    assert "**Tipo:** planejamento" in note


def test_note_omits_empty_new_sections(tmp_path):
    from datetime import datetime
    from meeting_processor.config import load_config
    from meeting_processor.models import MeetingSummary, Transcript
    from meeting_processor.note_generator import NoteGenerator

    cfg = load_config()
    cfg.project_root = str(tmp_path)
    cfg.vault_dir = "vault"
    summary = MeetingSummary(
        executive_summary="x", time_windows=[], action_items=[],
        participants=[], key_topics=[],
    )
    gen = NoteGenerator(cfg)
    note = gen._build_note(
        title="t", summary=summary,
        transcript=Transcript(segments=[], full_text="", language="pt", duration=1.0),
        source_file="x.mp4", date_str="2026-06-04",
        created_at=datetime(2026, 6, 4, 10, 0),
    )
    assert "## Propósito" not in note
    assert "## Decisões" not in note
    assert "## Questões em Aberto" not in note
    assert "**Tipo:** " not in note


def test_note_resolves_kanban_and_transcript_links(tmp_path):
    from datetime import datetime
    from meeting_processor.config import load_config
    from meeting_processor.models import ActionItem, MeetingSummary, Transcript
    from meeting_processor.note_generator import NoteGenerator

    cfg = load_config()
    cfg.project_root = str(tmp_path)
    cfg.vault_dir = "vault"
    summary = MeetingSummary(
        executive_summary="x",
        time_windows=[],
        action_items=[ActionItem(description="Fazer algo")],
        participants=[], key_topics=[],
    )
    gen = NoteGenerator(cfg)
    paths = gen.prepare("reuniao.mp4", datetime(2026, 6, 4, 10, 0))
    note = gen._build_note(
        title=paths.folder_name,
        summary=summary,
        transcript=Transcript(segments=[], full_text="", language="pt", duration=1.0),
        source_file="reuniao.mp4",
        date_str="2026-06-04",
        created_at=datetime(2026, 6, 4, 10, 0),
        tarefas_link=paths.tarefas_name,
        transcricao_link=paths.transcricao_name,
    )
    # No unresolved f-string placeholders leaked into the note:
    assert "{tarefas_link}" not in note
    assert "{transcricao_link}" not in note
    # The Kanban tip link resolved to the real Tarefas note name:
    assert f"[[{paths.tarefas_name}|Tarefas]]" in note
