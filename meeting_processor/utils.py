"""Funções utilitárias compartilhadas.

Centraliza helpers usados por vários módulos (formatação de tempo,
parsing de timestamps) para evitar duplicação — DRY.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path


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


def slugify(name: str) -> str:
    """Nome de pessoa -> nome de arquivo seguro (sem acento, minúsculo)."""
    nfkd = unicodedata.normalize("NFD", name or "")
    ascii_name = "".join(c for c in nfkd if unicodedata.category(c) != "Mn")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    return slug or "sem-nome"


def write_json_atomic(path, data) -> None:
    """Grava ``data`` como JSON de forma atômica (.tmp + os.replace).

    Evita corromper o arquivo se o processo morrer no meio da escrita.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


# Segredos que podem vazar em mensagens de erro (URLs com chave, tokens, etc.).
_SECRET_PATTERNS = [
    # chave/token em query string de URL: ...?key=ABC  /  &access_token=ABC
    (
        re.compile(r"(?i)([?&](?:key|api[-_]?key|access[-_]?token|token)=)[^&\s'\"]+"),
        r"\1REDACTED",
    ),
    # cabeçalho Authorization: Bearer <token>
    (re.compile(r"(?i)(authorization:\s*bearer\s+)\S+"), r"\1REDACTED"),
    # chaves estilo sk-... (OpenAI/Anthropic)
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"), "sk-REDACTED"),
]


def redact_secrets(text: str) -> str:
    """Remove segredos (chaves de API, tokens) de uma string.

    Aplicado antes de persistir/exibir mensagens de erro, que às vezes embutem a
    URL completa do provedor — incluindo a chave de API em ``?key=...``.
    """
    if not text:
        return text
    for pattern, repl in _SECRET_PATTERNS:
        text = pattern.sub(repl, text)
    return text
