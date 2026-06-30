# Roadmap

Ideias e melhorias planejadas. Cada item vira um design em
`docs/superpowers/specs/` quando entra em desenvolvimento.

## Em aberto

### Controles de processamento — botão "Parar" na transcrição (+ etc.)

**Problema:** durante o processamento de uma reunião não há um jeito claro e
sempre visível de **parar/cancelar** a transcrição de onde o usuário está
acompanhando.

**O que já existe (ponto de partida):**
- Cancelamento cooperativo no backend: `job_control.JobCancelled`, endpoint
  `POST /api/process/cancel` (`_cancel_active_job`), hook `useCancelJob`.
- Botão "Cancelar" no componente `ActiveJob`, mas só renderizado no card de job
  ativo do **Dashboard** — não na página da reunião (`MeetingDetail`).

**Proposta:**
- Surfacing do "Parar" onde o usuário acompanha a transcrição (em
  `MeetingDetail`, junto do `ActiveJob`/stepper), não só no Dashboard.
- Feedback claro de estado cancelado (badge/toast + entrada no log de geração).
- "e etc." — controles de job adicionais a avaliar:
  - Retomar / reprocessar após cancelar (retry de uma etapa específica).
  - Parar etapas individuais (ex.: cancelar só o resumo, manter a transcrição).
  - Indicador de cancelável vs. ponto sem volta por etapa do pipeline.

**Notas:** o cancelamento é cooperativo (checado nos limites de etapa via
`_check_cancel`), então "parar" é responsivo entre etapas, não no meio de uma
transcrição longa de uma única etapa — vale comunicar isso na UI.
