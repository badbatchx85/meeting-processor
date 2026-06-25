# Analytics de talk-time (v1)

**Data:** 2026-06-25
**Status:** design aprovado (aguardando review do spec)
**Sub-projeto:** #3 do roadmap de features

## Problema

A diarização rotula cada segmento com um falante (`Falante N` ou nome real após
auto-resolve/rename). Hoje nada mostra **quem falou quanto** numa reunião — uma
métrica simples e útil que os dados já permitem.

**Objetivo:** mostrar, no `MeetingDetail`, o tempo de fala por pessoa (duração + %),
ordenado por tempo, só quando a reunião tem 2+ falantes.

## Decisões de design (do brainstorm)

1. **Escopo v1:** só talk-time por pessoa (duração total + %). Sem nº de turnos,
   sem interrupções/sobreposição, sem timeline. (YAGNI; interrupções exigiriam
   persistir os turnos brutos do pyannote, fora de escopo.)
2. **Apresentação:** lista, uma linha por pessoa — nome · `mm:ss` · barra inline
   (largura = %) · %. Ordenada desc por tempo.
3. **Onde computa:** **client-side**, a partir dos segmentos que o
   `useMeetingWords(id)` já carrega (com nomes reais já aplicados pelo `/words`).
   Zero backend novo — evita um endpoint que re-leria o mesmo sidecar.

## Dados disponíveis

`WordSegment` (frontend/src/api/types.ts:60):
```ts
interface WordSegment { start: number; end: number; text: string; speaker: string | null; words: WordTime[] | null; }
```
`useMeetingWords(id)` (hooks/useApi.ts) → `WordSegment[] | null` (null em 404 / sem
word timestamps). Já consumido pelo `TranscriptPlayer` no `MeetingDetail`.

## Componentes

### `frontend/src/lib/talkTime.ts` (util pura)
```ts
export interface TalkTimeRow { speaker: string; seconds: number; pct: number; }
export function talkTime(segments: WordSegment[]): TalkTimeRow[];
```
- Agrupa por `speaker`, ignorando `speaker === null`; soma `end - start` por falante.
- `total` = soma de todas as durações contadas; `pct = seconds / total * 100`
  (0 se `total === 0`).
- Ordena desc por `seconds`.
- Retorna `[]` se houver **< 2 falantes distintos** (analytics só faz sentido
  multi-speaker) ou se `segments` for vazio/null.

### `frontend/src/components/TalkTime.tsx`
- Props: `{ segments: WordSegment[] }`.
- Chama `talkTime`; se `[]`, **renderiza `null`**.
- Senão renderiza o título "Tempo de fala" + uma linha por `TalkTimeRow`:
  nome, `mm:ss` (helper local `fmtClock(seconds)`), barra com `width: ${pct}%`, `${Math.round(pct)}%`.

### Ligação em `frontend/src/pages/MeetingDetail.tsx`
- Já existe `const words = useMeetingWords(id)`. Na aba de transcrição, junto de
  `SpeakerNames`/`TranscriptPlayer`, renderizar:
  `<TalkTime segments={words.data ?? []} />`.

## Casos de borda

- Reunião sem diarização (todos `speaker === null`, ou só 1 falante) → `talkTime`
  devolve `[]` → componente some. Comportamento atual intacto.
- `words.data === null` (404 / sem sidecar) → `segments = []` → `[]` → some.
- `total === 0` (durações zeradas, improvável) → `pct = 0`, sem divisão por zero.

## Plano de testes (TDD, vitest)

- `talkTime`: soma por falante; `pct` correto; ordenação desc; `< 2 falantes → []`;
  ignora segmentos com `speaker null`; `[]`/null → `[]`; sem divisão por zero.
- `TalkTime` (component, @testing-library/react): renderiza uma linha por pessoa
  no caso multi-speaker (assert nomes + %); **não renderiza nada** quando vazio.

## Fora de escopo (YAGNI)

- Nº de turnos, duração média de turno.
- Interrupções / análise de sobreposição (exigiria persistir turnos do pyannote).
- Timeline visual de quem-falou-quando.
- Qualquer mudança no backend (endpoint, persistência).
