"""Frontend web local — alternativa ao Obsidian.

Servidor FastAPI + HTMX + Tailwind (CDN) que lê as reuniões processadas
diretamente do vault e expõe uma interface no navegador. Não substitui o
Obsidian, é uma opção paralela: ambos consomem os mesmos arquivos em
``vault/wiki/reunioes/``.

Uso:
    python -m meeting_processor web              # padrão: porta 8765
    python -m meeting_processor web --port 9000
"""

from .app import create_app, run

__all__ = ["create_app", "run"]
