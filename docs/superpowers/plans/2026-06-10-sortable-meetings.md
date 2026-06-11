# Sortable Meetings Table Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Reuniões table sortable by clicking column headers, and broaden the search to match purpose/type.

**Architecture:** A pure `sortMeetings(items, key, dir)` helper (testable without rendering) + sort state and header buttons in `Meetings.tsx`. Stored `HH:MM:SS`/ISO-date strings sort correctly via `localeCompare`, so no API change or parsing.

**Tech Stack:** React/Vite/TypeScript, Vitest, @testing-library/react.

Run from `frontend/`: `npx vitest run <file>`, `npx tsc --noEmit`.

---

## File Structure
- **Create** `frontend/src/lib/sortMeetings.ts` — the pure helper + `SortKey` type.
- **Modify** `frontend/src/pages/Meetings.tsx` — sort state, header buttons, broadened filter.
- **Create** `frontend/src/__tests__/sortMeetings.test.ts`, `frontend/src/__tests__/meetingsSort.test.tsx`.

---

### Task 1: `sortMeetings` pure helper

**Files:** Create `frontend/src/lib/sortMeetings.ts`, `frontend/src/__tests__/sortMeetings.test.ts`.

- [ ] **Step 1: Write the failing tests** — create `frontend/src/__tests__/sortMeetings.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { sortMeetings } from "../lib/sortMeetings";
import type { MeetingSummary } from "../api/types";

const M = (over: Partial<MeetingSummary>): MeetingSummary => ({
  id: "x", title: "t", created: "", duration: "", task_count: 0,
  participants: "", source_file: "", meeting_type: "", purpose: "", has_summary: false,
  ...over,
});

const items = [
  M({ id: "a", title: "Banana", created: "2026-06-05", duration: "00:45:03", task_count: 2 }),
  M({ id: "b", title: "Abacaxi", created: "2026-06-09", duration: "01:02:00", task_count: 5 }),
  M({ id: "c", title: "Caju", created: "2026-06-01", duration: "00:10:00", task_count: 0 }),
];

describe("sortMeetings", () => {
  it("sorts by task_count desc and asc", () => {
    expect(sortMeetings(items, "task_count", "desc").map((m) => m.id)).toEqual(["b", "a", "c"]);
    expect(sortMeetings(items, "task_count", "asc").map((m) => m.id)).toEqual(["c", "a", "b"]);
  });
  it("sorts by created asc (oldest first)", () => {
    expect(sortMeetings(items, "created", "asc").map((m) => m.id)).toEqual(["c", "a", "b"]);
  });
  it("sorts by duration desc (longest first)", () => {
    expect(sortMeetings(items, "duration", "desc").map((m) => m.id)).toEqual(["b", "a", "c"]);
  });
  it("sorts by title asc (A-Z)", () => {
    expect(sortMeetings(items, "title", "asc").map((m) => m.title)).toEqual(["Abacaxi", "Banana", "Caju"]);
  });
  it("does not mutate the input array", () => {
    const before = items.map((m) => m.id);
    sortMeetings(items, "title", "asc");
    expect(items.map((m) => m.id)).toEqual(before);
  });
});
```

- [ ] **Step 2: Run to verify they fail**

Run (from `frontend/`): `npx vitest run src/__tests__/sortMeetings.test.ts`
Expected: FAIL — cannot resolve `../lib/sortMeetings`.

- [ ] **Step 3: Create `frontend/src/lib/sortMeetings.ts`:**

```ts
import type { MeetingSummary } from "../api/types";

export type SortKey = "created" | "duration" | "task_count" | "title";

export function sortMeetings(
  items: MeetingSummary[],
  key: SortKey,
  dir: "asc" | "desc",
): MeetingSummary[] {
  const sign = dir === "asc" ? 1 : -1;
  return [...items].sort((a, b) => {
    const cmp =
      key === "task_count"
        ? a.task_count - b.task_count
        : String(a[key]).localeCompare(String(b[key]));
    return cmp * sign;
  });
}
```

- [ ] **Step 4: Run to verify they pass**

Run (from `frontend/`): `npx vitest run src/__tests__/sortMeetings.test.ts` (5 pass), then `npx tsc --noEmit` (exit 0).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/sortMeetings.ts frontend/src/__tests__/sortMeetings.test.ts
git commit -m "feat(ui): sortMeetings pure helper"
```

---

### Task 2: Wire sorting + broadened search into `Meetings.tsx`

**Files:** Modify `frontend/src/pages/Meetings.tsx`; Create `frontend/src/__tests__/meetingsSort.test.tsx`.

- [ ] **Step 1: Write the failing test** — create `frontend/src/__tests__/meetingsSort.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { Meetings } from "../pages/Meetings";
import { ToastProvider } from "../components/Toast";

const M = (over: Record<string, unknown>) => ({
  id: "x", title: "t", created: "", duration: "", task_count: 0,
  participants: "", source_file: "", meeting_type: "", purpose: "", has_summary: true, ...over,
});
const MEETINGS = [
  M({ id: "a", title: "Alpha", task_count: 1, purpose: "roadmap" }),
  M({ id: "b", title: "Bravo", task_count: 9, purpose: "orçamento" }),
  M({ id: "c", title: "Charlie", task_count: 3, purpose: "contratação" }),
];

function setup() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><ToastProvider><Meetings /></ToastProvider></MemoryRouter>
    </QueryClientProvider>,
  );
}

// Meeting title links carry the title text; the icon-only "Abrir" link has none.
function rowTitles(): string[] {
  return screen.getAllByRole("link")
    .map((a) => a.textContent ?? "")
    .filter((t) => ["Alpha", "Bravo", "Charlie"].includes(t));
}

describe("Meetings sort + search", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      const body = String(url).includes("/api/history") ? [] : MEETINGS;
      return new Response(JSON.stringify(body), { status: 200 });
    }));
  });

  it("sorts by Tarefas on header click and toggles direction", async () => {
    setup();
    await screen.findByText("Alpha");
    fireEvent.click(screen.getByRole("button", { name: /Ordenar por Tarefas/i }));
    expect(rowTitles()).toEqual(["Bravo", "Charlie", "Alpha"]);   // 9,3,1
    fireEvent.click(screen.getByRole("button", { name: /Ordenar por Tarefas/i }));
    expect(rowTitles()).toEqual(["Alpha", "Charlie", "Bravo"]);   // toggled asc
  });

  it("search matches purpose, not just title", async () => {
    setup();
    await screen.findByText("Bravo");
    fireEvent.change(screen.getByPlaceholderText("Buscar…"), { target: { value: "orçamento" } });
    expect(rowTitles()).toEqual(["Bravo"]);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run (from `frontend/`): `npx vitest run src/__tests__/meetingsSort.test.tsx`
Expected: FAIL — no "Ordenar por Tarefas" button; search doesn't match purpose.

- [ ] **Step 3: Add the import + sort state.** In `frontend/src/pages/Meetings.tsx`:
  - Add to the imports: `import { sortMeetings, type SortKey } from "../lib/sortMeetings";`
  - After `const [q, setQ] = useState("");` add:
    ```tsx
      const [sortKey, setSortKey] = useState<SortKey>("created");
      const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
      const toggleSort = (key: SortKey) => {
        if (key === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
        else { setSortKey(key); setSortDir(key === "title" ? "asc" : "desc"); }
      };
      const arrow = (key: SortKey) => (sortKey === key ? (sortDir === "asc" ? " ↑" : " ↓") : "");
    ```

- [ ] **Step 4: Broaden the filter + sort the rows.** Replace:
    ```tsx
      const items = (meetings.data ?? []).filter((m) => m.title.toLowerCase().includes(q.toLowerCase()));
    ```
  with:
    ```tsx
      const term = q.toLowerCase();
      const filtered = (meetings.data ?? []).filter((m) =>
        `${m.title} ${m.purpose ?? ""} ${m.meeting_type ?? ""}`.toLowerCase().includes(term),
      );
      const items = sortMeetings(filtered, sortKey, sortDir);
    ```
  (The `tbody` already maps `items`, so the rendered rows are now sorted. The empty-state check `items.length > 0` still works.)

- [ ] **Step 5: Make the four data headers sortable buttons.** Replace the `<thead>` header cells:
    ```tsx
                <th className="eyebrow pb-3 font-normal">Título</th>
                <th className="eyebrow pb-3 font-normal">Data</th>
                <th className="eyebrow pb-3 font-normal">Duração</th>
                <th className="eyebrow pb-3 font-normal">Tarefas</th>
                <th className="pb-3"></th>
    ```
  with:
    ```tsx
                <th className="pb-3">
                  <button onClick={() => toggleSort("title")} aria-label="Ordenar por Título"
                    className="eyebrow font-normal transition-colors hover:text-ink">Título{arrow("title")}</button>
                </th>
                <th className="pb-3">
                  <button onClick={() => toggleSort("created")} aria-label="Ordenar por Data"
                    className="eyebrow font-normal transition-colors hover:text-ink">Data{arrow("created")}</button>
                </th>
                <th className="pb-3">
                  <button onClick={() => toggleSort("duration")} aria-label="Ordenar por Duração"
                    className="eyebrow font-normal transition-colors hover:text-ink">Duração{arrow("duration")}</button>
                </th>
                <th className="pb-3">
                  <button onClick={() => toggleSort("task_count")} aria-label="Ordenar por Tarefas"
                    className="eyebrow font-normal transition-colors hover:text-ink">Tarefas{arrow("task_count")}</button>
                </th>
                <th className="pb-3"></th>
    ```

- [ ] **Step 6: Run the new test + typecheck + full suite**

Run (from `frontend/`): `npx vitest run src/__tests__/meetingsSort.test.tsx` (2 pass), `npx tsc --noEmit` (0), then `npx vitest run` (all pass — the existing `meetings.test.tsx` queries row-action buttons + `findByText`, which are unaffected by the header-button change; confirm it still passes).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/Meetings.tsx frontend/src/__tests__/meetingsSort.test.tsx
git commit -m "feat(ui): sortable meetings columns + purpose/type search"
```

---

## Self-Review

**Spec coverage:**
- `sortMeetings(items, key, dir)` pure helper (localeCompare strings, numeric task_count, copies array) → Task 1. ✓
- Sort state (`sortKey` default `created`, `sortDir` default `desc`) + `toggleSort` (flip if same, else set with title→asc / others→desc) + `arrow` indicator → Task 2 Step 3. ✓
- Four data headers become `Ordenar por …` buttons; rows rendered via `sortMeetings(filtered, …)` → Task 2 Steps 4-5. ✓
- Broadened search (title + purpose + meeting_type) → Task 2 Step 4. ✓
- Tests: helper (5 sorts incl. no-mutate) + component (header click reorders/toggles, search matches purpose) → Tasks 1-2. ✓
- Out of scope (server-side/pagination, multi-sort, persistence, history table, raw-seconds) → untouched. ✓

**Placeholder scan:** none — every step has concrete code/commands.

**Type consistency:** `SortKey` + `sortMeetings(items, key, dir) -> MeetingSummary[]` (Task 1) imported and used in `Meetings.tsx` (Task 2) and both tests with the same signature. `MeetingSummary` is the existing `api/types` interface. `toggleSort(key: SortKey)`/`arrow(key: SortKey)` match the header `onClick`s. The filter uses existing fields (`title`/`purpose`/`meeting_type`). The `items` variable name is reused (now the sorted list) so the existing `tbody` `.map((m) => …)` and `items.length > 0` keep working. Names consistent throughout. ✓
