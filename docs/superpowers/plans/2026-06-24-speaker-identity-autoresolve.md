# Speaker Identity Auto-Resolve Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-aplicar o nome real de um falante reconhecido pelo voice-ID (alta confiança) antes do resumo, para que tarefas/kanban/rollup saiam com identidade real e consistente.

**Architecture:** Um passo novo no `pipeline.py`, entre `_finish_diarization` e a escrita da transcrição/resumo, casa cada cluster de embedding contra o repositório de vozes num threshold estrito (`auto`) e renomeia os segmentos in place. Read-only (não enrola) e forward-only (não toca reuniões antigas). Reusa `voiceprints.match`/`load_repo`.

**Tech Stack:** Python 3, pydantic (models), pytest. Sem dependências novas.

## Global Constraints

- Testes rodam com `.venv/bin/python -m pytest`.
- `voice_id_threshold = 0.45` é o threshold de *sugestão* (não mudar).
- Auto-resolve é **read-only**: nunca chama `enroll`/`save_repo`.
- Auto-resolve é **forward-only**: só atua na reunião sendo processada.
- Clamp obrigatório no call site: `min(voice_id_auto_threshold, voice_id_threshold)`.
- Distância é cosseno; menor = mais parecido. `match()` devolve o nome de menor distância < threshold, ou `None`.

---

### Task 1: Config — `voice_id_auto_threshold`

**Files:**
- Modify: `meeting_processor/config.py` (campo do `Settings` + `float_overrides`)
- Test: `tests/test_diarization.py`

**Interfaces:**
- Produces: `Settings.voice_id_auto_threshold: float` (default `0.30`); env `MEETING_VOICE_ID_AUTO_THRESHOLD`.

- [ ] **Step 1: Write the failing tests**

Em `tests/test_diarization.py`, adicione:

```python
def test_voice_id_auto_threshold_default(config):
    assert config.voice_id_auto_threshold == 0.30


def test_voice_id_auto_threshold_env_override(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MEETING_VOICE_ID_AUTO_THRESHOLD", "0.25")
    from meeting_processor.config import load_config
    cfg = load_config()
    assert cfg.voice_id_auto_threshold == 0.25
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_diarization.py::test_voice_id_auto_threshold_default tests/test_diarization.py::test_voice_id_auto_threshold_env_override -v`
Expected: FAIL (`AttributeError`/`'voice_id_auto_threshold'` ausente).

- [ ] **Step 3: Add the Settings field**

Em `meeting_processor/config.py`, logo após a linha `voice_id_threshold: float = 0.45 ...`:

```python
    # Auto-resolve de identidade: aplica o nome reconhecido sem passo humano quando
    # a distância é < este valor (mais rígido que voice_id_threshold, o de sugestão).
    voice_id_auto_threshold: float = 0.30
```

- [ ] **Step 4: Add the env override**

Em `meeting_processor/config.py`, no dict `float_overrides`, após a linha `"MEETING_VOICE_ID_THRESHOLD": "voice_id_threshold",`:

```python
        "MEETING_VOICE_ID_AUTO_THRESHOLD": "voice_id_auto_threshold",
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_diarization.py -k voice_id_auto_threshold -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add meeting_processor/config.py tests/test_diarization.py
git commit -m "feat(voice-id): config voice_id_auto_threshold (default 0.30)"
```

---

### Task 2: `voiceprints.auto_resolve`

**Files:**
- Modify: `meeting_processor/voiceprints.py`
- Test: `tests/test_voiceprints.py`

**Interfaces:**
- Consumes: `load_repo(vault)`, `match(repo, vector, threshold)` (já existem no módulo).
- Produces: `auto_resolve(emb: dict, vault: Path, auto_threshold: float) -> dict[str, str]` — `{label: nome}` só para matches com distância < `auto_threshold`. Read-only.
- Refactor: `suggest(meeting_dir, vault, threshold)` passa a delegar para `auto_resolve` (DRY).

- [ ] **Step 1: Write the failing tests**

Em `tests/test_voiceprints.py`, adicione:

```python
def test_auto_resolve_matches_below_threshold(tmp_path):
    from meeting_processor import voiceprints
    repo = voiceprints.enroll({}, "Ana", [1.0, 0.0])
    voiceprints.save_repo(tmp_path, repo)
    out = voiceprints.auto_resolve({"Falante 1": [1.0, 0.0]}, tmp_path, 0.30)
    assert out == {"Falante 1": "Ana"}


def test_auto_resolve_skips_when_above_threshold(tmp_path):
    from meeting_processor import voiceprints
    repo = voiceprints.enroll({}, "Ana", [1.0, 0.0])
    voiceprints.save_repo(tmp_path, repo)
    # vetor ortogonal => distância de cosseno = 1.0, acima de qualquer threshold
    out = voiceprints.auto_resolve({"Falante 1": [0.0, 1.0]}, tmp_path, 0.30)
    assert out == {}


def test_auto_resolve_empty_inputs(tmp_path):
    from meeting_processor import voiceprints
    assert voiceprints.auto_resolve({}, tmp_path, 0.30) == {}            # sem embeddings
    assert voiceprints.auto_resolve({"Falante 1": [1.0]}, tmp_path, 0.30) == {}  # repo vazio


def test_auto_resolve_is_read_only(tmp_path):
    from meeting_processor import voiceprints
    repo = voiceprints.enroll({}, "Ana", [1.0, 0.0])
    voiceprints.save_repo(tmp_path, repo)
    before = voiceprints.load_repo(tmp_path)["Ana"]["count"]
    voiceprints.auto_resolve({"Falante 1": [1.0, 0.0]}, tmp_path, 0.30)
    assert voiceprints.load_repo(tmp_path)["Ana"]["count"] == before  # não enrolou
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_voiceprints.py -k auto_resolve -v`
Expected: FAIL (`auto_resolve` não existe).

- [ ] **Step 3: Implement `auto_resolve` and delegate `suggest`**

Em `meeting_processor/voiceprints.py`, adicione `auto_resolve` (antes de `suggest`):

```python
def auto_resolve(emb: dict, vault: Path, auto_threshold: float) -> dict:
    """{label: nome reconhecido} para clusters que casam com o repositório abaixo
    de ``auto_threshold``. Read-only: não enrola nem grava o repositório."""
    if not emb:
        return {}
    repo = load_repo(vault)
    if not repo:
        return {}
    out = {}
    for label, vec in emb.items():
        name = match(repo, vec, auto_threshold)
        if name:
            out[label] = name
    return out
```

E substitua o corpo de `suggest` para delegar (DRY):

```python
def suggest(meeting_dir: Path, vault: Path, threshold: float) -> dict:
    """{Falante N: nome reconhecido} para clusters que casam com o repositório."""
    return auto_resolve(read_meeting_embeddings(meeting_dir), vault, threshold)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_voiceprints.py -v`
Expected: PASS (os novos `auto_resolve` + os de `suggest` existentes continuam verdes).

- [ ] **Step 5: Commit**

```bash
git add meeting_processor/voiceprints.py tests/test_voiceprints.py
git commit -m "feat(voice-id): voiceprints.auto_resolve (read-only) + suggest delega"
```

---

### Task 3: `speaker_names.apply_speaker_map`

**Files:**
- Modify: `meeting_processor/speaker_names.py`
- Test: `tests/test_speaker_renaming.py`

**Interfaces:**
- Produces: `apply_speaker_map(segments: list, mapping: dict[str, str]) -> None` — muta `segment.speaker` in place para labels presentes em `mapping`; deixa os demais intactos. Opera sobre objetos `TranscriptSegment` (campo `.speaker`).

- [ ] **Step 1: Write the failing test**

Em `tests/test_speaker_renaming.py`, adicione:

```python
def test_apply_speaker_map_renames_in_place():
    from meeting_processor.models import TranscriptSegment
    from meeting_processor import speaker_names
    segs = [
        TranscriptSegment(start=0, end=1, text="a", speaker="Falante 1"),
        TranscriptSegment(start=1, end=2, text="b", speaker="Falante 2"),
        TranscriptSegment(start=2, end=3, text="c", speaker=None),
    ]
    speaker_names.apply_speaker_map(segs, {"Falante 1": "Ana"})
    assert [s.speaker for s in segs] == ["Ana", "Falante 2", None]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_speaker_renaming.py::test_apply_speaker_map_renames_in_place -v`
Expected: FAIL (`apply_speaker_map` não existe).

- [ ] **Step 3: Implement `apply_speaker_map`**

Em `meeting_processor/speaker_names.py`, adicione:

```python
def apply_speaker_map(segments: list, mapping: dict[str, str]) -> None:
    """Renomeia ``segment.speaker`` in place para os labels presentes em ``mapping``.

    In-memory (objetos TranscriptSegment), distinto de ``apply_names`` que opera
    sobre segmentos-dict para a reescrita do .md pós-fato.
    """
    for seg in segments:
        if seg.speaker in mapping:
            seg.speaker = mapping[seg.speaker]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_speaker_renaming.py::test_apply_speaker_map_renames_in_place -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add meeting_processor/speaker_names.py tests/test_speaker_renaming.py
git commit -m "feat(speakers): apply_speaker_map (rename in-memory segments)"
```

---

### Task 4: Pipeline glue — `_resolve_identities`

**Files:**
- Modify: `meeting_processor/pipeline.py` (novo método + 1 chamada no `process`)
- Test: `tests/test_diarization.py`

**Interfaces:**
- Consumes: `voiceprints.auto_resolve` (Task 2), `speaker_names.apply_speaker_map` (Task 3), `config.voice_id_auto_threshold` (Task 1), `config.voice_id_threshold`, `config.vault_path`.
- Produces: `MeetingPipeline._resolve_identities(self, transcript, voiceprints_emb: dict) -> dict` — renomeia os segmentos reconhecidos in place e devolve o `voiceprints_emb` com as chaves remapeadas pelos nomes resolvidos.

- [ ] **Step 1: Write the failing tests**

Em `tests/test_diarization.py`, adicione:

```python
def test_resolve_identities_auto_names_high_confidence(config, tmp_path):
    from meeting_processor import voiceprints
    from meeting_processor.pipeline import MeetingPipeline
    config.enable_diarization = True
    repo = voiceprints.enroll({}, "Ana", [1.0, 2.0, 3.0])
    voiceprints.save_repo(config.vault_path, repo)
    segs = [TranscriptSegment(start=0, end=1, text="oi", speaker="Falante 1")]
    t = Transcript(segments=segs, full_text="oi", language="pt", duration=1)
    emb = MeetingPipeline(config)._resolve_identities(t, {"Falante 1": [1.0, 2.0, 3.0]})
    assert segs[0].speaker == "Ana"
    assert emb == {"Ana": [1.0, 2.0, 3.0]}


def test_resolve_identities_noop_when_no_match(config, tmp_path):
    from meeting_processor import voiceprints
    from meeting_processor.pipeline import MeetingPipeline
    config.enable_diarization = True
    repo = voiceprints.enroll({}, "Ana", [1.0, 0.0])
    voiceprints.save_repo(config.vault_path, repo)
    segs = [TranscriptSegment(start=0, end=1, text="oi", speaker="Falante 1")]
    t = Transcript(segments=segs, full_text="oi", language="pt", duration=1)
    emb = MeetingPipeline(config)._resolve_identities(t, {"Falante 1": [0.0, 1.0]})
    assert segs[0].speaker == "Falante 1"      # ortogonal => não casa
    assert emb == {"Falante 1": [0.0, 1.0]}    # chaves intactas


def test_resolve_identities_empty_emb(config):
    from meeting_processor.pipeline import MeetingPipeline
    assert MeetingPipeline(config)._resolve_identities(None, {}) == {}


def test_resolve_identities_clamps_auto_to_suggest(config):
    from meeting_processor import voiceprints
    from meeting_processor.pipeline import MeetingPipeline
    config.enable_diarization = True
    config.voice_id_threshold = 0.45
    config.voice_id_auto_threshold = 0.99  # misconfig: mais frouxo que o suggest
    voiceprints.save_repo(config.vault_path, voiceprints.enroll({}, "Ana", [1.0, 0.0]))
    segs = [TranscriptSegment(start=0, end=1, text="oi", speaker="Falante 1")]
    t = Transcript(segments=segs, full_text="oi", language="pt", duration=1)
    # [1.0, 1.732] está a distância de cosseno 0.5 de [1.0, 0.0]: acima de 0.45
    # (suggest) e abaixo de 0.99 (auto solto). Com o clamp eff=0.45 => NÃO casa.
    emb = MeetingPipeline(config)._resolve_identities(t, {"Falante 1": [1.0, 1.732]})
    assert segs[0].speaker == "Falante 1"
    assert emb == {"Falante 1": [1.0, 1.732]}
```

(`TranscriptSegment` e `Transcript` já estão importados no topo de `tests/test_diarization.py`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_diarization.py -k resolve_identities -v`
Expected: FAIL (`_resolve_identities` não existe).

- [ ] **Step 3: Implement `_resolve_identities`**

Em `meeting_processor/pipeline.py`, adicione o método na classe `MeetingPipeline` (junto dos outros `_finish_diarization`/`_start_diarization`):

```python
    def _resolve_identities(self, transcript, voiceprints_emb: dict) -> dict:
        """Auto-nomeia falantes reconhecidos pelo voice-ID (alta confiança) para o
        nome real, in place nos segmentos, ANTES do resumo. Devolve o emb com as
        chaves remapeadas. Read-only (não enrola) e forward-only.
        """
        if not voiceprints_emb:
            return voiceprints_emb
        from . import voiceprints, speaker_names
        eff = min(self.config.voice_id_auto_threshold, self.config.voice_id_threshold)
        name_map = voiceprints.auto_resolve(voiceprints_emb, self.config.vault_path, eff)
        if not name_map:
            return voiceprints_emb
        speaker_names.apply_speaker_map(transcript.segments, name_map)
        return {name_map.get(k, k): v for k, v in voiceprints_emb.items()}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_diarization.py -k resolve_identities -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Wire it into `process`**

Em `meeting_processor/pipeline.py`, logo após a linha
`voiceprints_emb = self._finish_diarization(diar, transcript)`
(antes do bloco `# Salvar transcrição no vault`), adicione:

```python
            # Auto-resolve falantes reconhecidos -> nomes reais ANTES de escrever a
            # transcrição e rodar o resumo, para que assignee/kanban/rollup já saiam
            # com a identidade real e consistente.
            voiceprints_emb = self._resolve_identities(transcript, voiceprints_emb)
```

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (todos verdes; baseline + os novos).

- [ ] **Step 7: Commit**

```bash
git add meeting_processor/pipeline.py tests/test_diarization.py
git commit -m "feat(voice-id): pipeline auto-resolves recognized speakers before summary"
```

---

## Notas de execução

- A feature só atua de ponta a ponta com diarização ligada (modelo `community-1`) e o
  fix de embeddings do PR #2 mergeado; o código aqui é coberto por testes que injetam
  embeddings diretamente, então não depende disso para passar verde.
- Após a Task 4, a calibração real do `0.30` fica pendente do mesmo live-run cross-meeting
  do voice-ID (2ª gravação distinta) — fora do escopo deste plano.
