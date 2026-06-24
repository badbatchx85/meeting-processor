# Auto-resolução de identidade de falante via voice-ID

**Data:** 2026-06-24
**Status:** design aprovado (aguardando review do spec)
**Funde:** sub-projetos #1 (action items com dono) e #2 (auto-naming cross-meeting)

## Problema

O pipeline diariza e rotula os falantes como `Falante 1/2/…`. O LLM do resumo já
usa esses rótulos para atribuir o `assignee` das tarefas (summarizer.py), que flui
para `responsavel::` no kanban e para `person_rollup` (notas por pessoa).

A lacuna: `Falante N` é um rótulo *por reunião*, sem identidade estável. A mesma
pessoa vira "Falante 1" numa reunião e "Falante 2" noutra, então o `person_rollup`
**divide** as tarefas abertas dela em vez de agregar. O voice-ID (`voiceprints.py`)
já sabe casar uma voz a uma pessoa conhecida — mas hoje só *sugere* no `/speakers`,
exigindo confirmação humana.

**Objetivo:** quando o voice-ID reconhece uma voz com alta confiança, aplicar o
nome real **automaticamente**, antes da escrita dos artefatos, para que tarefas,
kanban e rollups saiam com a identidade real e consistente — sem passo humano.

## Decisões de design (do brainstorm)

1. **Onde:** no pipeline, *antes* do resumo. O nome real precisa existir antes do
   LLM rodar, senão o `assignee` nasce como "Falante N" e exigiria reescrita.
2. **Política de confiança — dois níveis:**
   - distância < `voice_id_auto_threshold` (~0.30) → **auto-aplica**.
   - `auto_threshold` ≤ distância < `voice_id_threshold` (0.45) → **sugere** (fluxo
     `/speakers` atual, humano confirma).
   - ≥ 0.45 → nada.
3. **Read-only:** o auto-resolve **não enrola** o voiceprint. Enroll continua só no
   rename humano explícito, para evitar a deriva da média-corrente-sem-L2
   (pendência conhecida) por reforço automático.
4. **Forward-only:** reuniões passadas não são tocadas. A consistência se constrói
   daqui para frente. Sem maquinaria de reescrita retroativa.

## Componentes

### `voiceprints.auto_resolve(emb_map, vault, auto_threshold) -> dict[str, str]`
Recebe `{label: vetor}` (a saída de `_finish_diarization`), carrega o repositório
(`load_repo`) e, para cada label, usa `match(repo, vetor, auto_threshold)`. Retorna
`{label: nome}` só para os matches com distância < `auto_threshold` (o `match` já
escolhe o de menor distância). Read-only — não chama `enroll` nem `save_repo`.
Repo vazio / embeddings vazios → `{}`.

### `speaker_names.apply_speaker_map(segments, mapping) -> None`
Renomeia `segment.speaker` in place para os labels presentes em `mapping`; deixa os
não-mapeados intactos. Helper in-memory sobre `TranscriptSegment`, distinto da
maquinaria de reescrita de `.md` que `speaker_names` já tem para o rename pós-fato.

### Glue no `pipeline.py`
Entre `_finish_diarization` (já devolve `voiceprints_emb = {Falante N: vetor}` e
marcou os segmentos) e a escrita da transcrição/resumo:
1. `eff = min(config.voice_id_auto_threshold, config.voice_id_threshold)` (clamp no
   call site; `auto_resolve` permanece função pura do threshold que recebe).
   `name_map = voiceprints.auto_resolve(voiceprints_emb, vault, eff)`
2. `speaker_names.apply_speaker_map(transcript.segments, name_map)`
3. Remapeia as chaves de `voiceprints_emb` pelos nomes resolvidos (sidecar fica
   keyed pelo nome real nos resolvidos, "Falante N" nos demais).
Segue o fluxo: `write_transcription` (raw já com nome real) → `write_embeddings` →
`_summarize` (LLM vê "Ana:").

### Config (`config.py`)
- Novo `voice_id_auto_threshold: float = 0.30`; env `MEETING_VOICE_ID_AUTO_THRESHOLD`.
- `voice_id_threshold = 0.45` continua sendo o de *sugestão*.
- Invariante: o call site no pipeline passa `min(auto_threshold, voice_id_threshold)`
  para `auto_resolve` — um misconfig nunca deixa o auto mais frouxo que o suggest.

## Casos de borda

- Sem repo ou sem embeddings → `auto_resolve` devolve `{}`, no-op, comportamento atual intacto.
- Zona 0.30–0.45 e não-matches → seguem para o `/speakers` suggest+confirm existente.
- Dois clusters casando a mesma pessoa (diarização dividiu uma voz) → ambos recebem
  o mesmo nome, efetivamente os fundindo. Aceitável.
- Correção humana (rename) continua sobrescrevendo **e** enrolando, como hoje.
- `enable_diarization` off → nada disso roda (gate existente).

## Plano de testes (TDD)

- `auto_resolve`: respeita a fronteira do threshold (match logo abaixo entra, logo
  acima não); repo/embeddings vazios → `{}`; escolhe o de menor distância por label;
  não muta o repositório (não enrola).
- `apply_speaker_map`: renomeia in place os mapeados; ignora labels ausentes do map.
- Pipeline (estende `test_maybe_diarize_enabled`): com um voiceprint conhecido de
  alta confiança no repo, o segmento sai com o nome real **antes** do `_summarize`
  e o sidecar de embeddings fica keyed pelo nome real.
- Config: default `0.30`; override por `MEETING_VOICE_ID_AUTO_THRESHOLD`.
- Clamp no call site: `min(auto, suggest)` (testar com auto > suggest → usa suggest).

## Dependências / notas

- Depende logicamente do fix de embeddings do pyannote 4.x (`speaker_embeddings`,
  PR #2): sem ele os embeddings não fluem e `auto_resolve` nunca recebe vetores em
  runtime. O código de `auto_resolve` é testável de forma independente (opera sobre
  mapas de embeddings), mas a feature só *funciona* de ponta a ponta com o PR #2
  mergeado e diarização ligada (modelo `community-1`).
- Não toca a UI: o `/speakers` continua igual, agora só recebendo os casos da zona
  de sugestão e os não reconhecidos.

## Fora de escopo (YAGNI)

- Reescrita retroativa de reuniões antigas (decisão: forward-only).
- Re-enroll/refinamento automático do voiceprint (decisão: read-only).
- Qualquer mudança na UI de rename ou no fluxo de sugestão.
