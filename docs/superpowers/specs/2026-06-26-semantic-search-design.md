# Busca semântica sobre transcrições (v1)

**Data:** 2026-06-26
**Status:** design aprovado (aguardando review do spec)
**Sub-projeto:** #4 do roadmap (v1 = busca; chat/RAG fica para depois)

## Problema

Não há como buscar entre reuniões. Quer-se: digitar uma pergunta/tema e receber os
**trechos verbatim** mais relevantes de todas as reuniões, cada um com link para o
ponto no áudio.

## Decisões (do brainstorm)

1. **v1 = busca**, não chat: embed → recupera → mostra trechos. Sem LLM/síntese.
2. **Embeddings: Ollama local** (`nomic-embed-text`). Offline, nada sai da máquina.
3. **Índice = trechos da transcrição** (verbatim) com timestamp.
4. **Vector store: cosseno em Python puro**, espelhando `voiceprints.py` — corpus
   pequeno (vault pessoal). Zero dep nova. (sqlite-vec fica para se/quando crescer.)

## Arquitetura

- **Indexar (write):** após a transcrição, fatiar em chunks (janela de segmentos),
  embeddar cada um via Ollama, anexar ao índice persistido. Best-effort, opt-in.
- **Buscar (read):** query → embedding via Ollama → cosseno contra o índice → top-k
  → resultados `{meeting_id, text, start, end, score}`.

## Componentes

### `ollama_service.embed(text, config) -> list[float]`
`POST {base_url}/api/embeddings` com `{"model": config.embedding_model, "prompt": text}`
→ resposta `{"embedding": [...]}`. Levanta/retorna erro tratável quando Ollama está
off (mesmo padrão de `is_running`). Timeout razoável.

### `search_index.py` (espelha `voiceprints.py`)
- `index_path(vault) -> Path` → `vault/wiki/.search-index.json`.
- `load_index(vault) -> list[dict]` / `save_index(vault, rows)` (atômico via `write_json_atomic`).
- `chunk_segments(segments, max_chars=500) -> list[dict]` — agrupa segmentos
  consecutivos até `max_chars`; cada chunk = `{text, start, end}` (start do 1º
  segmento, end do último). Puro, sem I/O.
- `add_meeting(vault, meeting_id, chunks_with_vectors)` — remove chunks antigos desse
  `meeting_id` e anexa os novos. (Re-transcrição reindexar = idempotente.)
- `remove_meeting(vault, meeting_id)` — tira os chunks daquela reunião.
- `query(rows, query_vec, k, min_score) -> list[dict]` — para cada row,
  `score = 1 - cosine_distance(query_vec, row["vector"])` (= similaridade de cosseno,
  maior = mais parecido). Devolve os top-k com `score >= min_score`, ordenados por
  `score` desc, cada um sem o campo `vector` (só `{meeting_id, text, start, end, score}`).
  Reusa a fórmula de cosseno do `voiceprints` (`_cosine_distance`).

Formato de cada row: `{"meeting_id": str, "text": str, "start": float, "end": float, "vector": list[float]}`.

### Hook no `pipeline.py`
Após `write_transcription`, se `config.enable_search_index` e Ollama disponível:
`chunks = chunk_segments(transcript.segments)`; embeddar cada `chunk["text"]`;
`add_meeting(vault, meeting_id, chunks_com_vetores)`. Best-effort: qualquer falha
(Ollama off, etc.) loga warning e segue — nunca derruba o pipeline (igual à diarização).

### Web (`web/app.py`)
- `POST /api/search` body `{"q": str, "k": int=10}` → embeddar `q`, `query(...)`,
  devolver `[{meeting_id, text, start, end, score}]`. Erro amigável se Ollama off.
- `POST /api/search/reindex` → reindexa todas as reuniões existentes (lê os
  segmentos `.words.json` de cada `wiki/reunioes/<pasta>/`, chunk + embed + add_meeting).

### Config (`config.py`)
- `enable_search_index: bool = False` + env `MEETING_ENABLE_SEARCH_INDEX`.
- `embedding_model: str = "nomic-embed-text"` + env `MEETING_EMBEDDING_MODEL`.

### Frontend
- Página/box de busca (`pages/Search.tsx` ou em Meetings): input → `POST /api/search`
  → lista de resultados (trecho · reunião · data · link para `MeetingDetail` no
  timestamp). Reusa o seek do player existente. Vazio → "nada encontrado".

## Erros / bordas

- Ollama off na indexação → pula (best-effort), reunião não indexada até reindex.
- Ollama off na busca → `/api/search` devolve erro amigável (ex.: 503 + mensagem).
- Índice inexistente/vazio → `query` devolve `[]`.
- Re-transcrição → `add_meeting` substitui os chunks antigos daquela reunião.
- `min_score` evita lixo: resultados muito distantes não aparecem.

## Plano de testes (TDD)

- `chunk_segments`: agrupa por `max_chars`; carrega `start` do 1º e `end` do último;
  segmentos vazios → `[]`.
- `search_index` I/O: save→load round-trip; `add_meeting` substitui só aquela reunião;
  `remove_meeting` idem; persistência atômica.
- `query`: ordena por cosseno desc; respeita `k` e `min_score`; índice vazio → `[]`.
  (Vetores fixos nos testes — função pura, como nos testes de `voiceprints`.)
- `ollama_service.embed`: parse de `{"embedding": [...]}`; erro tratável quando off (mock httpx).
- `/api/search` (mock do `embed`): resultados ordenados; Ollama off → erro amigável.
- frontend: componente de busca (mock da API) renderiza resultados + links; vazio → mensagem.

## Fora de escopo (YAGNI)

- Chat / síntese de resposta por LLM (sub-projeto futuro reusando a recuperação).
- Embeddings via API ou sentence-transformers (decisão: Ollama local).
- Vector DB (chroma/faiss/sqlite-vec) — cosseno puro basta nesta escala.
- Reindex incremental automático em massa / agendado (há o endpoint manual de reindex).
- Indexar resumos (decisão: só transcrição).
