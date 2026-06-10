"""Rollup de tarefas por pessoa no vault."""
from meeting_processor.utils import slugify


def test_slugify():
    assert slugify("Ana Júlia") == "ana-julia"
    assert slugify("João") == "joao"
    assert slugify("A/B C") == "a-b-c"
    assert slugify("   ") == "sem-nome"
    assert slugify("Sem responsável") == "sem-responsavel"
