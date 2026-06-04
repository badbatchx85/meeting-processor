"""Leitura e escrita do quadro Kanban (formato obsidian-kanban).

Formato esperado de cada arquivo ``Tarefas - <pasta>.md``:

    ---
    kanban-plugin: basic
    ---

    ## A Fazer

    - [ ] **Descrição da tarefa** @{prazo opcional}
    \tresponsavel:: Nome
    \tprioridade:: alta
    \ttimestamp:: 03:28

    ## Em Progresso

    ## Concluido

Os campos depois do checkbox vêm indentados com TAB (não espaços) e
seguem a sintaxe do Dataview do Obsidian (``chave:: valor``).

Cada tarefa é um *bloco* — uma linha ``- [ ]`` seguida de zero ou mais
linhas indentadas. Esse módulo move blocos inteiros entre seções,
preservando a indentação original.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Identificadores canônicos das colunas (independem do label exibido).
COLUMN_TODO = "todo"
COLUMN_DOING = "doing"
COLUMN_DONE = "done"

# Mapeamento label-no-arquivo -> id canônico. Aceita acentos e variações.
SECTION_TO_COLUMN = {
    "a fazer": COLUMN_TODO,
    "to do": COLUMN_TODO,
    "todo": COLUMN_TODO,
    "em progresso": COLUMN_DOING,
    "in progress": COLUMN_DOING,
    "doing": COLUMN_DOING,
    "concluido": COLUMN_DONE,
    "concluído": COLUMN_DONE,
    "done": COLUMN_DONE,
}

COLUMN_LABEL = {
    COLUMN_TODO: "A Fazer",
    COLUMN_DOING: "Em Progresso",
    COLUMN_DONE: "Concluido",
}

COLUMN_ORDER = [COLUMN_TODO, COLUMN_DOING, COLUMN_DONE]

TASK_LINE_RE = re.compile(r"^\s*-\s*\[( |x|X)\]\s+(.*)$")
META_RE = re.compile(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)::\s*(.+?)\s*$")
DUE_RE = re.compile(r"@\{([^}]+)\}")


@dataclass
class TaskCard:
    """Uma tarefa do Kanban com seus metadados parsed."""

    task_id: str  # hash estável (meeting_id + linha do checkbox)
    meeting_id: str
    column: str  # COLUMN_TODO / COLUMN_DOING / COLUMN_DONE
    description: str
    raw_block: list[str]  # linhas originais (incluindo as indentadas)
    done: bool = False
    assignee: str | None = None
    priority: str | None = None  # alta / média / baixa
    due_date: str | None = None
    timestamp: str | None = None
    extra_meta: dict[str, str] = field(default_factory=dict)


def _hash_id(meeting_id: str, raw_line: str) -> str:
    """Hash curto baseado no conteúdo da linha do checkbox."""
    h = hashlib.sha256()
    h.update(meeting_id.encode("utf-8"))
    h.update(b"\x00")
    h.update(raw_line.strip().encode("utf-8"))
    return h.hexdigest()[:16]


def _normalize_section(label: str) -> str | None:
    return SECTION_TO_COLUMN.get(label.strip().lower())


# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------


def parse_kanban_file(path: Path, meeting_id: str) -> list[TaskCard]:
    """Lê um arquivo de Kanban e devolve todas as tarefas como ``TaskCard``."""
    if not path.exists():
        return []

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning("Falha ao ler %s: %s", path, e)
        return []

    lines = text.splitlines()
    cards: list[TaskCard] = []

    current_column: str | None = None
    current_block: list[str] = []
    current_card: TaskCard | None = None

    def _flush():
        nonlocal current_card, current_block
        if current_card is not None:
            current_card.raw_block = list(current_block)
            cards.append(current_card)
        current_card = None
        current_block = []

    for line in lines:
        stripped = line.lstrip()
        # Cabeçalho de seção
        if stripped.startswith("##"):
            _flush()
            label = stripped.lstrip("#").strip()
            current_column = _normalize_section(label)
            continue

        if current_column is None:
            continue

        m_task = TASK_LINE_RE.match(line)
        if m_task:
            # Nova tarefa começa — fecha a anterior
            _flush()
            done_flag = m_task.group(1).lower() == "x"
            description_raw = m_task.group(2)

            # Remove **bold** e captura @{...} due_date
            due_match = DUE_RE.search(description_raw)
            due = due_match.group(1) if due_match else None
            description_clean = DUE_RE.sub("", description_raw)
            description_clean = re.sub(r"\*\*", "", description_clean).strip()

            current_card = TaskCard(
                task_id=_hash_id(meeting_id, line),
                meeting_id=meeting_id,
                column=current_column,
                description=description_clean,
                raw_block=[],
                done=done_flag,
                due_date=due,
            )
            current_block = [line]
            continue

        # Linha de metadado / continuação?
        if current_card is not None:
            # Vazio: encerra o bloco atual
            if line.strip() == "":
                _flush()
                continue

            # Metadado dataview: chave:: valor
            m_meta = META_RE.match(line)
            if m_meta:
                key, value = m_meta.group(1).lower(), m_meta.group(2)
                if key in ("responsavel", "responsável", "assignee"):
                    current_card.assignee = value
                elif key in ("prioridade", "priority"):
                    current_card.priority = value
                elif key == "timestamp":
                    current_card.timestamp = value
                else:
                    current_card.extra_meta[key] = value
                current_block.append(line)
                continue

            # Linha indentada (continuação textual)
            if line.startswith(("\t", "    ", "  ")):
                current_block.append(line)
                continue

            # Linha não indentada e não checkbox → encerrou o bloco
            _flush()

    _flush()
    return cards


# ---------------------------------------------------------------------------
# Move (drag and drop)
# ---------------------------------------------------------------------------


def move_task(path: Path, task_id: str, meeting_id: str, to_column: str) -> bool:
    """Move uma tarefa para outra coluna no arquivo, in-place.

    Retorna True se a tarefa foi encontrada e movida, False caso contrário.
    """
    if to_column not in (COLUMN_TODO, COLUMN_DOING, COLUMN_DONE):
        raise ValueError(f"coluna inválida: {to_column}")

    if not path.exists():
        return False

    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # 1) Localiza a tarefa por hash, captura seu bloco completo
    target_block: list[str] | None = None
    target_start = -1
    target_end = -1
    current_column: str | None = None

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        if stripped.startswith("##"):
            label = stripped.lstrip("#").strip()
            current_column = _normalize_section(label)
            i += 1
            continue

        m = TASK_LINE_RE.match(line)
        if m and current_column is not None:
            tid = _hash_id(meeting_id, line)
            if tid == task_id:
                # captura este bloco
                start = i
                j = i + 1
                while j < len(lines):
                    nxt = lines[j]
                    if nxt.strip() == "":
                        break
                    if TASK_LINE_RE.match(nxt):
                        break
                    if nxt.lstrip().startswith("##"):
                        break
                    if not nxt.startswith(("\t", "    ", "  ")):
                        break
                    j += 1
                target_block = lines[start:j]
                target_start = start
                target_end = j
                if current_column == to_column:
                    return True  # já está lá
                break
        i += 1

    if target_block is None:
        return False

    # 2) Remove o bloco da posição original
    new_lines = lines[:target_start] + lines[target_end:]

    # Limpa linhas em branco duplicadas que possam ter sobrado
    cleaned: list[str] = []
    for ln in new_lines:
        if ln.strip() == "" and cleaned and cleaned[-1].strip() == "":
            continue
        cleaned.append(ln)
    new_lines = cleaned

    # 3) Encontra a seção destino e insere o bloco no fim dela
    target_label = COLUMN_LABEL[to_column]
    insert_idx: int | None = None
    in_target = False
    for k, ln in enumerate(new_lines):
        s = ln.lstrip()
        if s.startswith("##"):
            label_norm = _normalize_section(s.lstrip("#").strip())
            if label_norm == to_column:
                in_target = True
                continue
            if in_target:
                # próxima seção: insere antes
                insert_idx = k
                break
        # fim do arquivo dentro da target
    if insert_idx is None and in_target:
        insert_idx = len(new_lines)

    if insert_idx is None:
        # Seção destino não existe — adiciona no final
        if new_lines and new_lines[-1].strip() != "":
            new_lines.append("")
        new_lines.append(f"## {target_label}")
        new_lines.append("")
        insert_idx = len(new_lines)

    # Garante linha em branco antes do bloco se não houver
    block_to_insert = list(target_block)
    if (
        insert_idx > 0
        and new_lines[insert_idx - 1].strip() != ""
        and not new_lines[insert_idx - 1].lstrip().startswith("##")
    ):
        block_to_insert = [""] + block_to_insert

    new_lines = new_lines[:insert_idx] + block_to_insert + new_lines[insert_idx:]

    # 4) Persiste
    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    logger.info("Tarefa %s movida para %s em %s", task_id, to_column, path.name)
    return True


# ---------------------------------------------------------------------------
# Aggregação para o Kanban global
# ---------------------------------------------------------------------------


def list_all_tasks(reunioes_dir: Path) -> list[TaskCard]:
    """Percorre todas as reuniões e retorna a lista agregada de tarefas."""
    if not reunioes_dir.exists():
        return []

    all_tasks: list[TaskCard] = []
    for meeting_dir in sorted(reunioes_dir.iterdir()):
        if not meeting_dir.is_dir():
            continue
        for tarefas_path in meeting_dir.glob("Tarefas - *.md"):
            all_tasks.extend(parse_kanban_file(tarefas_path, meeting_dir.name))
    return all_tasks


def kanban_path_for(reunioes_dir: Path, meeting_id: str) -> Path | None:
    """Retorna o caminho do arquivo de Kanban da reunião informada."""
    base = reunioes_dir / meeting_id
    if not base.exists():
        return None
    matches = list(base.glob("Tarefas - *.md"))
    return matches[0] if matches else None
