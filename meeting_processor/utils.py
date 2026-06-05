"""Funções utilitárias compartilhadas.

Centraliza helpers usados por vários módulos (formatação de tempo,
parsing de timestamps) para evitar duplicação — DRY.
"""

from __future__ import annotations


def yaml_quote(value: str) -> str:
    """Encode a string as a YAML double-quoted scalar (escapes ``\\`` and ``"``).

    Keeps free-form frontmatter values (e.g. an LLM-generated ``purpose``) valid
    even when they contain a double quote. Inverse of :func:`yaml_unquote`.
    """
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def yaml_unquote(raw: str) -> str:
    """Decode a single frontmatter scalar produced by :func:`yaml_quote`.

    If the value is wrapped in double quotes, return the unescaped inner text;
    otherwise return it stripped — matching how unquoted/list-literal values
    (e.g. ``["Ana"]``) were already read.
    """
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        return raw[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return raw


def format_duration(seconds: float) -> str:
    """Formata segundos como ``HH:MM:SS``."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_timestamp(seconds: float) -> str:
    """Formata segundos como ``MM:SS`` (para marcação de falas)."""
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


def parse_timestamp(ts: str) -> float:
    """Converte ``HH:MM:SS`` ou ``MM:SS`` (com ``.``/``,`` nos ms) para segundos."""
    ts = ts.replace(",", ".")
    parts = ts.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    if len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return 0.0
