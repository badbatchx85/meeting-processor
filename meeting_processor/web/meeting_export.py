"""Export a single meeting's summary to Markdown or Word (.docx).

Source of truth is the meeting's Resumo note (already parsed by
``_load_meeting`` into ``{meta, resumo_md, tasks}``). The transcript is
intentionally excluded — it is large and viewable separately.
"""
from __future__ import annotations

import io
import re

_TRANSCRIPT_HEADING = "## Transcricao Completa"


def to_markdown(meeting: dict) -> str:
    """Return the summary body, trimming the trailing Obsidian transcript link."""
    body = meeting.get("resumo_md", "") or ""
    idx = body.find(_TRANSCRIPT_HEADING)
    if idx != -1:
        body = body[:idx]
    return body.rstrip() + "\n"
