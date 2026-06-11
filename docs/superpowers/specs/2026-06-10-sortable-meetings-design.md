# Sortable Meetings Table (+ broadened search)

**Date:** 2026-06-10
**Status:** Approved design

## Goal

Make the Reuniões table sortable by clicking column headers (Título, Data,
Duração, Tarefas), and broaden the existing search to match purpose/type — so a
growing meetings list stays scannable. Frontend-only, no API change.

## Background (exact, from exploration)

- `frontend/src/pages/Meetings.tsx` already has a search box: `const [q] =
  useState("")` and `items = (meetings.data ?? []).filter((m) =>
  m.title.toLowerCase().includes(q.toLowerCase()))`. The table renders columns
  **Título / Data / Duração / Tarefas** + an actions column, in API order.
- `useMeetings()` → `MeetingSummary[]`. `MeetingSummary` fields:
  `id, title, created, duration, task_count, participants, source_file,
  meeting_type, purpose, has_summary, source_exists`.
- Stored formats make string sorting correct:
  - `duration` = zero-padded `"HH:MM:SS"` (e.g. `"00:45:03"`) → lexical = numeric.
  - `created` = ISO `"YYYY-MM-DD"` (e.g. `"2026-06-05"`) → lexical = chronological.
  - `task_count` = number; `title` = string.
  - The API returns meetings newest-first (folder name reverse sort).
- No raw-seconds field exists, and none is needed.

## 1. Sort state + headers (`Meetings.tsx`)

- `type SortKey = "created" | "duration" | "task_count" | "title"`.
- `const [sortKey, setSortKey] = useState<SortKey>("created")` and
  `const [sortDir, setSortDir] = useState<"asc" | "desc">("desc")` — default
  `created`/`desc` reproduces today's newest-first order.
- `toggleSort(key)`: if `key === sortKey` → flip `sortDir`; else → `setSortKey(key)`
  and `setSortDir(key === "title" ? "asc" : "desc")` (titles default A–Z; the
  rest default highest/newest/longest-first).
- The four data-column `<th>`s become `<button>`s (full-width, left-aligned,
  keeping the `eyebrow` style) calling `toggleSort(key)` with an
  `aria-label` like `Ordenar por Tarefas`. The active column appends a ↑/↓
  glyph (e.g. `sortKey === key ? (sortDir === "asc" ? " ↑" : " ↓") : ""`).
- Render `sortMeetings(items, sortKey, sortDir)` (the filtered list) in `tbody`.

## 2. Pure sort helper

In `Meetings.tsx` (exported) or a small `frontend/src/lib/sortMeetings.ts`:

```ts
export type SortKey = "created" | "duration" | "task_count" | "title";

export function sortMeetings(
  items: MeetingSummary[],
  key: SortKey,
  dir: "asc" | "desc",
): MeetingSummary[] {
  const sign = dir === "asc" ? 1 : -1;
  return [...items].sort((a, b) => {
    let cmp: number;
    if (key === "task_count") cmp = a.task_count - b.task_count;
    else cmp = String(a[key]).localeCompare(String(b[key]));
    return cmp * sign;
  });
}
```

Copies the array (never mutates `items`). Decision: keep it in a small
`lib/sortMeetings.ts` module so it imports the `MeetingSummary` type and is unit
-testable without rendering the page.

## 3. Broaden search (one line)

Change the filter to match title OR purpose OR meeting_type:

```ts
const term = q.toLowerCase();
const items = (meetings.data ?? []).filter((m) =>
  `${m.title} ${m.purpose ?? ""} ${m.meeting_type ?? ""}`.toLowerCase().includes(term),
);
```

Then `const rows = sortMeetings(items, sortKey, sortDir);` and map `rows`.

## Testing (Vitest)

`frontend/src/__tests__/sortMeetings.test.ts` (helper):
- by `task_count` desc → highest first; asc → lowest first.
- by `created` asc → oldest (`"2026-06-01"`) before newest (`"2026-06-09"`).
- by `duration` desc → `"01:02:00"` before `"00:45:03"`.
- by `title` asc → A–Z.
- does NOT mutate the input array (the original order is unchanged after a call).

`frontend/src/__tests__/meetingsSort.test.tsx` (component, with a stubbed
`/api/meetings` returning 3 rows with distinct titles/task_counts):
- the "Tarefas" header is a button; clicking it reorders rows by task count
  (assert the first row's title); clicking again flips order and the header
  shows the direction glyph.
- typing a purpose substring in "Buscar…" filters to the matching row (proves
  search now matches purpose, not just title).

## Out of scope

- Server-side sorting / pagination (small list, client-side).
- Multi-column sort; persisting the sort across reloads.
- Changing the "Histórico de conversões" table below.
- Raw-seconds API fields (string formats already sort correctly).
- Empty-value special handling (missing `created`/`duration` sort naturally as
  the smallest string — acceptable).
