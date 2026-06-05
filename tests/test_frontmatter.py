"""Round-trip safety for double-quoted YAML frontmatter scalars.

A free-form field (e.g. an LLM-generated ``purpose``) may contain a double
quote. The note writer and the lenient frontmatter reader must round-trip it.
"""
import pytest

from meeting_processor.utils import yaml_quote, yaml_unquote


@pytest.mark.parametrize(
    "value",
    [
        "Alinhar o roadmap",
        'Alinhar o "roadmap" do Q3',   # embedded double quotes
        r"caminho\com\barra",          # embedded backslashes
        'aspas " e barra \\ juntas',    # both
        "",                             # empty
    ],
)
def test_quote_unquote_round_trip(value):
    assert yaml_unquote(yaml_quote(value)) == value


def test_unquote_leaves_unquoted_legacy_values_untouched():
    # Pre-feature notes stored plain (or list-literal) values without quoting.
    assert yaml_unquote("2026-06-04") == "2026-06-04"
    assert yaml_unquote('["Ana"]') == '["Ana"]'


def test_note_with_quoted_purpose_round_trips_through_reader(tmp_path):
    from datetime import datetime

    from meeting_processor.config import load_config
    from meeting_processor.models import MeetingSummary, Transcript
    from meeting_processor.note_generator import NoteGenerator
    from meeting_processor.web.app import _strip_frontmatter

    cfg = load_config()
    cfg.project_root = str(tmp_path)
    cfg.vault_dir = "vault"
    summary = MeetingSummary(
        executive_summary="x",
        time_windows=[],
        action_items=[],
        participants=[],
        key_topics=[],
        purpose='Definir a estratégia "go-to-market"',
        meeting_type="planejamento",
    )
    gen = NoteGenerator(cfg)
    note = gen._build_note(
        title="2026-06-04 10h00 - reuniao",
        summary=summary,
        transcript=Transcript(segments=[], full_text="", language="pt", duration=1.0),
        source_file="reuniao.mp4",
        date_str="2026-06-04",
        created_at=datetime(2026, 6, 4, 10, 0),
    )
    meta, _body = _strip_frontmatter(note)
    assert meta["purpose"] == 'Definir a estratégia "go-to-market"'
    assert meta["meeting_type"] == "planejamento"
