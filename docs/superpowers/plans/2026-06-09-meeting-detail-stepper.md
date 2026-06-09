# Live Stepper on Meeting Detail Page — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the Dashboard's live "Em processamento" stepper (with cancel + auto-refresh) on the meeting detail page for the job belonging to that meeting.

**Architecture:** Extract the Dashboard's per-job block (stepper + "Limpar" cancel) into a reusable `<ActiveJob>` component. The detail page finds its job with `status.data.active.find(j => j.file === id)` (jobs started there are stored with `file === meeting_id`), renders `<ActiveJob>`, disables the generate buttons while active, and invalidates its queries when the job finishes. No backend change.

**Tech Stack:** React, @tanstack/react-query, Vitest + @testing-library/react, Tailwind, lucide-react.

Run frontend tests with `npx vitest run <file>` and typecheck with `npx tsc --noEmit`, all from `frontend/`.

---

## File Structure

- **Create** `frontend/src/components/ActiveJob.tsx` — one active job's UI: `<ProcessingStepper>` + the "Limpar (parou de responder)" cancel button. Owns `useCancelJob` + `useToast`.
- **Create** `frontend/src/__tests__/activeJob.test.tsx` — renders stepper + cancel POST.
- **Modify** `frontend/src/pages/Dashboard.tsx` — replace inline per-job block with `<ActiveJob>`.
- **Modify** `frontend/src/pages/MeetingDetail.tsx` — `useStatus`, matched-job card, disabled buttons, auto-refresh effect.
- **Create** `frontend/src/__tests__/meetingDetailStepper.test.tsx` — card renders + buttons disabled when a matching job is active.

---

### Task 1: `ActiveJob` shared component

**Files:**
- Create: `frontend/src/components/ActiveJob.tsx`
- Create: `frontend/src/__tests__/activeJob.test.tsx`

- [ ] **Step 1: Write the failing test** — `frontend/src/__tests__/activeJob.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ActiveJob } from "../components/ActiveJob";
import { ToastProvider } from "../components/Toast";
import type { JobProgress } from "../api/types";

const JOB: JobProgress = {
  file: "reuniao.mp4", started: "2026-06-09T12:00:00", status: "processing",
  stage_number: 1, stage_total: 6, stage_label: "Extraindo áudio",
  stage_percent: 10, percent: 5, detail: "", stages: [],
};

function setup(job: JobProgress) {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider><ActiveJob job={job} /></ToastProvider>
    </QueryClientProvider>,
  );
}

describe("ActiveJob", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders the stepper (file + percent) and a Limpar button", () => {
    setup(JOB);
    expect(screen.getByText("reuniao.mp4")).toBeInTheDocument();
    expect(screen.getByText("5%")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Limpar/i })).toBeInTheDocument();
  });

  it("POSTs cancel with file + started when Limpar is clicked", async () => {
    const f = vi.fn(async () => new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", f);
    setup(JOB);
    fireEvent.click(screen.getByRole("button", { name: /Limpar/i }));
    await waitFor(() => {
      const call = f.mock.calls.find(([u, o]) =>
        String(u).endsWith("/api/process/cancel") && (o as RequestInit)?.method === "POST");
      expect(call).toBeTruthy();
      expect(JSON.parse(String((call![1] as RequestInit).body))).toMatchObject({
        file: "reuniao.mp4", started: "2026-06-09T12:00:00",
      });
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/__tests__/activeJob.test.tsx`
Expected: FAIL — cannot resolve `../components/ActiveJob`.

- [ ] **Step 3: Create the component** — `frontend/src/components/ActiveJob.tsx`:

```tsx
import { X } from "lucide-react";
import { ProcessingStepper } from "./ProcessingStepper";
import { useCancelJob } from "../hooks/useApi";
import { useToast } from "./Toast";
import { ApiError } from "../api/client";
import type { JobProgress } from "../api/types";

// Copied verbatim from Dashboard.tsx:19 so the cancel button looks identical.
const btnGhost =
  "inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-muted transition-colors hover:bg-line-soft hover:text-ink";

export function ActiveJob({ job }: { job: JobProgress }) {
  const cancelJob = useCancelJob();
  const toast = useToast();
  return (
    <div className="flex flex-col gap-2">
      <ProcessingStepper job={job} />
      <button
        onClick={() =>
          cancelJob.mutate(
            { file: job.file, started: job.started },
            {
              onSuccess: () => toast("ok", "Job removido."),
              onError: (e) => toast("err", e instanceof ApiError ? e.message : "Erro"),
            },
          )
        }
        disabled={cancelJob.isPending}
        className={`${btnGhost} w-fit text-xs`}
      >
        <X size={13} /> Limpar (parou de responder)
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/__tests__/activeJob.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ActiveJob.tsx frontend/src/__tests__/activeJob.test.tsx
git commit -m "feat(ui): extract reusable ActiveJob (stepper + cancel)"
```

---

### Task 2: Dashboard uses `ActiveJob` (refactor, no behavior change) — DEFERRED

> **Deferred:** `Dashboard.tsx` currently carries uncommitted "stuck-jobs" work
> that modifies the very block this task would refactor. Committing `Dashboard.tsx`
> would entangle the two unrelated features. Skip this task until the stuck-jobs
> work is committed; then Dashboard can adopt `<ActiveJob>` in a one-line follow-up.
> The feature is fully functional without it (Dashboard keeps its inline block;
> only MeetingDetail consumes `ActiveJob` for now).

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: Add the import.** After the `ProcessingStepper` import line, add:

```tsx
import { ActiveJob } from "../components/ActiveJob";
```

- [ ] **Step 2: Replace the per-job block.** Replace this exact block:

```tsx
                {status.data.active?.map((job) => (
                  <div key={job.file} className="flex flex-col gap-2">
                    <ProcessingStepper job={job} />
                    <button
                      onClick={() =>
                        cancelJob.mutate(
                          { file: job.file, started: job.started },
                          { onSuccess: () => toast("ok", "Job removido."), onError },
                        )
                      }
                      disabled={cancelJob.isPending}
                      className={`${btnGhost} w-fit text-xs`}
                    >
                      <X size={13} /> Limpar (parou de responder)
                    </button>
                  </div>
                ))}
```

with:

```tsx
                {status.data.active?.map((job) => (
                  <ActiveJob key={job.file} job={job} />
                ))}
```

- [ ] **Step 3: Remove now-unused symbols.**
  - Delete the line `import { ProcessingStepper } from "../components/ProcessingStepper";`
  - Delete the line `const cancelJob = useCancelJob();` (find it in the component body).
  - In the hooks import line, remove `useCancelJob` from the `{ ... }` list (leave the others).
  - In the `lucide-react` import line, remove `X` from the `{ ... }` list (leave `Play, Square, RotateCw, FileVideo, Upload`).
  - Leave `btnGhost`, `toast`, and `onError` — they are still used elsewhere in the file.

- [ ] **Step 4: Typecheck (catches any symbol still referenced)**

Run: `npx tsc --noEmit`
Expected: exit 0, no errors. (If tsc reports a removed symbol is still used somewhere, restore that one import.)

- [ ] **Step 5: Run the regression tests**

Run: `npx vitest run src/__tests__/dashboardCancel.test.tsx src/__tests__/processingStepper.test.tsx`
Expected: PASS — the Dashboard's "Limpar" cancel still POSTs `{file, started}` (behavior preserved through `ActiveJob`).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "refactor(ui): Dashboard renders shared ActiveJob"
```

---

### Task 3: MeetingDetail shows the matched job

**Files:**
- Modify: `frontend/src/pages/MeetingDetail.tsx`
- Create: `frontend/src/__tests__/meetingDetailStepper.test.tsx`

- [ ] **Step 1: Write the failing test** — `frontend/src/__tests__/meetingDetailStepper.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { MeetingDetail } from "../pages/MeetingDetail";
import { ToastProvider } from "../components/Toast";

const MEETING = {
  id: "abc", title: "abc",
  meta: { purpose: "", meeting_type: "" },
  resumo_md: "", tasks: [], transcricao_md: "linha",
};
const JOB = {
  file: "abc", started: "2026-06-09T12:00:00", status: "processing",
  stage_number: 3, stage_total: 6, stage_label: "Gerando resumo com LLM",
  stage_percent: 10, percent: 35, detail: "", stages: [],
};

function stub(active: unknown[]) {
  return vi.fn(async (url: string) => {
    const u = String(url);
    if (u.includes("/api/status"))
      return new Response(JSON.stringify({ watcher_alive: false, active }), { status: 200 });
    if (u.includes("/source"))
      return new Response(JSON.stringify({ exists: true, name: "x.mp4", path: "/x.mp4", size: 1 }), { status: 200 });
    if (u.includes("/log")) return new Response(JSON.stringify([]), { status: 200 });
    return new Response(JSON.stringify(MEETING), { status: 200 });
  });
}

function setup() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/meetings/abc"]}>
        <ToastProvider>
          <Routes><Route path="/meetings/:id" element={<MeetingDetail />} /></Routes>
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("MeetingDetail — live stepper", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("shows the stepper card and disables the generate buttons when a matching job is active", async () => {
    vi.stubGlobal("fetch", stub([JOB]));
    setup();
    expect(await screen.findByText("Em processamento")).toBeInTheDocument();
    expect(await screen.findByText("35%")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Gerar resumo/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Gerar transcrição/i })).toBeDisabled();
  });

  it("shows no stepper card and leaves buttons enabled when no job matches this meeting", async () => {
    vi.stubGlobal("fetch", stub([{ ...JOB, file: "outro.mp4" }]));
    setup();
    expect(await screen.findByRole("button", { name: /Gerar resumo/i })).toBeEnabled();
    expect(screen.queryByText("Em processamento")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run src/__tests__/meetingDetailStepper.test.tsx`
Expected: FAIL — no "Em processamento" text; buttons not disabled by an active job.

- [ ] **Step 3: Update imports in `MeetingDetail.tsx`.**
  - Change `import { useState } from "react";` to:

    ```tsx
    import { useEffect, useRef, useState } from "react";
    ```
  - Add after the existing `import { ApiError } from "../api/client";` line:

    ```tsx
    import { useQueryClient } from "@tanstack/react-query";
    import { ActiveJob } from "../components/ActiveJob";
    ```
  - In the `useApi` import list, add `useStatus`:

    ```tsx
    import {
      useMeeting, useSummarizeMeeting, useTranscribeMeeting,
      useGenerationLog, useMeetingSource, useDeleteMeetingSource, useStatus,
    } from "../hooks/useApi";
    ```

- [ ] **Step 4: Add status + matched job + auto-refresh.** In the component body, right after `const deleteSource = useDeleteMeetingSource();`, add:

```tsx
  const status = useStatus();
  const qc = useQueryClient();
  const activeJob = status.data?.active?.find((j) => j.file === id);

  // When this meeting's job finishes (active → absent), refresh the note so the
  // new summary/transcript appears without a manual reload.
  const wasActive = useRef(false);
  useEffect(() => {
    const isActive = !!activeJob;
    if (wasActive.current && !isActive) {
      qc.invalidateQueries({ queryKey: ["meeting", id] });
      qc.invalidateQueries({ queryKey: ["meeting-log", id] });
      qc.invalidateQueries({ queryKey: ["meetings"] });
      qc.invalidateQueries({ queryKey: ["history"] });
    }
    wasActive.current = isActive;
  }, [activeJob, id, qc]);
```

- [ ] **Step 5: Disable the generate buttons while active.** Change the transcript button's `disabled` from `disabled={transcribe.isPending || sourceGone}` to:

```tsx
            disabled={transcribe.isPending || sourceGone || !!activeJob}
```

and the summary button's `disabled={summarize.isPending}` to:

```tsx
          <button onClick={generateSummary} disabled={summarize.isPending || !!activeJob} className={chip}>
```

- [ ] **Step 6: Render the stepper card.** Immediately after the closing `</header>` tag and before the `{/* Tabs + content */}` comment, insert:

```tsx
      {activeJob && (
        <Card title="Em processamento" eyebrow="Ao vivo" index="●">
          <ActiveJob job={activeJob} />
        </Card>
      )}
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `npx vitest run src/__tests__/meetingDetailStepper.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 8: Typecheck + full frontend suite (regressions)**

Run: `npx tsc --noEmit && npx vitest run`
Expected: tsc exit 0; all test files pass (including `meetingDetail.test.tsx`, `dashboardCancel.test.tsx`, `processingStepper.test.tsx`, the two new files).

- [ ] **Step 9: Commit**

```bash
git add frontend/src/pages/MeetingDetail.tsx frontend/src/__tests__/meetingDetailStepper.test.tsx
git commit -m "feat(ui): live stepper + cancel on meeting detail page"
```

---

## Self-Review

**Spec coverage:**
- Matching key `job.file === id` → Task 3 Step 4 (`activeJob`). ✓
- Shared `ActiveJob` (stepper + Limpar) → Task 1. ✓
- Dashboard reuses it → Task 2. ✓
- Stepper card on detail page → Task 3 Step 6. ✓
- Disable generate buttons while active → Task 3 Step 5. ✓
- Auto-refresh on completion (`["meeting", id]` + log + meetings + history) → Task 3 Step 4. ✓
- Tests: `activeJob.test.tsx` (Task 1), `meetingDetailStepper.test.tsx` (Task 3), regression of `dashboardCancel.test.tsx` (Task 2 Step 5). ✓
- No backend change. ✓

**Placeholder scan:** none — every step has concrete code/commands.

**Type consistency:** `ActiveJob` takes `{ job: JobProgress }` (Task 1), used identically in Dashboard (Task 2) and MeetingDetail (Task 3). The status match uses `useStatus()` → `StatusResponse.active: JobProgress[]` with `.file`/`.started`, matching the `JobProgress` fields the stepper and cancel use. `useMeeting(id)` key `["meeting", id]` matches the invalidation in Task 3 Step 4. Button `disabled` expressions reference the `activeJob` defined in Step 4 (Steps 4-6 ordered so `activeJob` exists before use). ✓
