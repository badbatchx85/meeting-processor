# Talk-Time Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mostrar tempo de fala por pessoa (duração + %) no MeetingDetail, calculado no cliente a partir dos segmentos já carregados.

**Architecture:** Uma util pura (`lib/talkTime.ts`) agrega os `WordSegment` por falante; um componente (`components/TalkTime.tsx`) renderiza lista + barra inline; o `MeetingDetail` o renderiza com os segmentos do `useMeetingWords`. Zero backend.

**Tech Stack:** React + TypeScript, vitest + @testing-library/react, Tailwind.

## Global Constraints

- Testes do frontend: `npm test` (= `vitest run`), rodar dentro de `frontend/`.
- Typecheck: `npx tsc --noEmit` (dentro de `frontend/`).
- `WordSegment` (frontend/src/api/types.ts): `{ start: number; end: number; text: string; speaker: string | null; words: WordTime[] | null }`.
- Analytics só aparece com **2+ falantes distintos**; senão a util devolve `[]` e o componente renderiza `null`.

---

### Task 1: util `talkTime`

**Files:**
- Create: `frontend/src/lib/talkTime.ts`
- Test: `frontend/src/__tests__/talkTime.test.tsx`

**Interfaces:**
- Produces: `interface TalkTimeRow { speaker: string; seconds: number; pct: number }` e `talkTime(segments: WordSegment[] | null): TalkTimeRow[]`.

- [ ] **Step 1: Write the failing tests**

Crie `frontend/src/__tests__/talkTime.test.tsx`:

```tsx
import { describe, it, expect } from "vitest";
import { talkTime } from "../lib/talkTime";

const seg = (speaker: string | null, start: number, end: number) =>
  ({ start, end, text: "", speaker, words: null });

describe("talkTime util", () => {
  it("agrega duração por falante, % e ordena desc", () => {
    const rows = talkTime([seg("João", 60, 90), seg("Ana", 0, 60)]);
    expect(rows).toEqual([
      { speaker: "Ana", seconds: 60, pct: (60 / 90) * 100 },
      { speaker: "João", seconds: 30, pct: (30 / 90) * 100 },
    ]);
  });

  it("ignora segmentos sem falante", () => {
    const rows = talkTime([seg("Ana", 0, 60), seg(null, 60, 120), seg("João", 120, 150)]);
    expect(rows.map((r) => r.speaker)).toEqual(["Ana", "João"]);
    expect(rows.find((r) => r.speaker === "Ana")!.seconds).toBe(60);
  });

  it("devolve [] com menos de 2 falantes", () => {
    expect(talkTime([seg("Ana", 0, 60)])).toEqual([]);
  });

  it("devolve [] para vazio ou null", () => {
    expect(talkTime([])).toEqual([]);
    expect(talkTime(null)).toEqual([]);
  });

  it("não divide por zero quando todas as durações são 0", () => {
    const rows = talkTime([seg("Ana", 0, 0), seg("João", 0, 0)]);
    expect(rows.every((r) => r.pct === 0)).toBe(true);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run (em `frontend/`): `npm test -- talkTime`
Expected: FAIL (`Cannot find module '../lib/talkTime'`).

- [ ] **Step 3: Implement the util**

Crie `frontend/src/lib/talkTime.ts`:

```ts
import type { WordSegment } from "../api/types";

export interface TalkTimeRow {
  speaker: string;
  seconds: number;
  pct: number;
}

export function talkTime(segments: WordSegment[] | null): TalkTimeRow[] {
  if (!segments || segments.length === 0) return [];
  const totals = new Map<string, number>();
  for (const s of segments) {
    if (s.speaker == null) continue;
    totals.set(s.speaker, (totals.get(s.speaker) ?? 0) + Math.max(0, s.end - s.start));
  }
  if (totals.size < 2) return [];
  const total = [...totals.values()].reduce((a, b) => a + b, 0);
  const rows: TalkTimeRow[] = [...totals.entries()].map(([speaker, seconds]) => ({
    speaker,
    seconds,
    pct: total > 0 ? (seconds / total) * 100 : 0,
  }));
  rows.sort((a, b) => b.seconds - a.seconds);
  return rows;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run (em `frontend/`): `npm test -- talkTime`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/talkTime.ts frontend/src/__tests__/talkTime.test.tsx
git commit -m "feat(analytics): talkTime util (per-speaker duration + pct)"
```

---

### Task 2: componente `TalkTime`

**Files:**
- Create: `frontend/src/components/TalkTime.tsx`
- Test: `frontend/src/__tests__/talkTime.test.tsx` (adicionar ao arquivo da Task 1)

**Interfaces:**
- Consumes: `talkTime` (Task 1), `WordSegment`.
- Produces: `export function TalkTime({ segments }: { segments: WordSegment[] }): JSX.Element | null`.

- [ ] **Step 1: Write the failing tests**

Adicione ao fim de `frontend/src/__tests__/talkTime.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { TalkTime } from "../components/TalkTime";

describe("TalkTime component", () => {
  it("renderiza uma linha por falante com nome e %", () => {
    render(<TalkTime segments={[seg("Ana", 0, 60), seg("João", 60, 90)]} />);
    expect(screen.getByText("Ana")).toBeInTheDocument();
    expect(screen.getByText("João")).toBeInTheDocument();
    expect(screen.getByText("67%")).toBeInTheDocument();  // 60/90 = 66.7 -> 67
    expect(screen.getByText("33%")).toBeInTheDocument();  // 30/90 = 33.3 -> 33
  });

  it("não renderiza nada com menos de 2 falantes", () => {
    const { container } = render(<TalkTime segments={[seg("Ana", 0, 60)]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run (em `frontend/`): `npm test -- talkTime`
Expected: FAIL (`Cannot find module '../components/TalkTime'`).

- [ ] **Step 3: Implement the component**

Crie `frontend/src/components/TalkTime.tsx`:

```tsx
import type { WordSegment } from "../api/types";
import { talkTime } from "../lib/talkTime";

function fmtClock(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function TalkTime({ segments }: { segments: WordSegment[] }): JSX.Element | null {
  const rows = talkTime(segments);
  if (rows.length === 0) return null;
  return (
    <div className="space-y-2">
      <h3 className="font-display text-sm font-semibold text-ink">Tempo de fala</h3>
      <ul className="space-y-1.5">
        {rows.map((r) => (
          <li key={r.speaker} className="flex items-center gap-3 text-sm">
            <span className="w-32 shrink-0 truncate text-ink">{r.speaker}</span>
            <span className="w-12 shrink-0 tabular-nums text-ink-soft">{fmtClock(r.seconds)}</span>
            <span className="h-2 flex-1 overflow-hidden rounded bg-ink/10">
              <span className="block h-full rounded bg-ink/40" style={{ width: `${r.pct}%` }} />
            </span>
            <span className="w-10 shrink-0 text-right tabular-nums text-ink-soft">
              {Math.round(r.pct)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run (em `frontend/`): `npm test -- talkTime`
Expected: PASS (7 passed — 5 da util + 2 do componente).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/TalkTime.tsx frontend/src/__tests__/talkTime.test.tsx
git commit -m "feat(analytics): TalkTime component (list + inline bar)"
```

---

### Task 3: ligar no MeetingDetail

**Files:**
- Modify: `frontend/src/pages/MeetingDetail.tsx`

**Interfaces:**
- Consumes: `TalkTime` (Task 2), o `words` já existente (`useMeetingWords`).

- [ ] **Step 1: Import the component**

Em `frontend/src/pages/MeetingDetail.tsx`, junto dos outros imports de componentes, adicione:

```tsx
import { TalkTime } from "../components/TalkTime";
```

- [ ] **Step 2: Render it in the transcript tab**

Em `frontend/src/pages/MeetingDetail.tsx`, logo após `<SpeakerNames meetingId={id} />` (na aba de transcrição), adicione:

```tsx
              <TalkTime segments={words.data ?? []} />
```

- [ ] **Step 3: Typecheck**

Run (em `frontend/`): `npx tsc --noEmit`
Expected: sem erros.

- [ ] **Step 4: Run the full frontend suite**

Run (em `frontend/`): `npm test`
Expected: PASS (todos verdes, incl. os novos de talkTime e os meetingDetail existentes).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/MeetingDetail.tsx
git commit -m "feat(analytics): show TalkTime in MeetingDetail transcript tab"
```

---

## Notas de execução

- A barra usa classes Tailwind do tema (`text-ink`, `text-ink-soft`, `bg-ink/10`); se algum
  token não existir no projeto, troque pelo equivalente usado em componentes vizinhos
  (ex.: `SpeakerNames.tsx`) — os testes asseguram texto/%, não classes.
- `fmtClock` aceita durações > 60 min (ex.: `75:30`); formato `m:ss`.
