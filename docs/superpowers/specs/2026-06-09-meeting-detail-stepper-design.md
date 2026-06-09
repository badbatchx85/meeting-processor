# Live Processing Stepper on the Meeting Detail Page

**Date:** 2026-06-09
**Status:** Approved design

## Goal

When a user clicks **"Gerar transcrição"** or **"Gerar resumo"** on a meeting's
detail page, show the same live **"Em processamento"** stepper that the Dashboard
shows — on the detail page itself — so the user can watch progress without
navigating back to the Dashboard. Include full parity: the "Limpar (parou de
responder)" cancel button, disabling the generate buttons while a job for this
meeting runs, and auto-refreshing the note when the job finishes.

## The matching key (crux — no backend change needed)

Jobs started from the detail page are stored with `job.file === meeting_id`:
both `MeetingPipeline.summarize_existing(meeting_id)` and
`transcribe_existing(meeting_id)` call `self.dashboard.new_job(meeting_id)`, and
`new_job`'s argument is persisted as `"file"` in `.processing-history.json` and
surfaced by `_job_progress` / `GET /api/status`. The detail page's route param
`id` (`useParams()`, URL-decoded) equals that stored string. So:

```ts
const activeJob = status.data?.active?.find((j) => j.file === id);
```

Watcher/upload jobs use a bare video filename (`new_job(video_path.name)`), so
they correctly never match a meeting page. **No encoding** is needed — the stored
value is the decoded folder name, the same string `useParams()` returns.

## Frontend changes

### 1. New shared component `frontend/src/components/ActiveJob.tsx`

Extract the Dashboard's per-job block (stepper + cancel button) so both pages
reuse it. `<ActiveJob job={job} />` owns its `useCancelJob` + `useToast`:

```tsx
import { X } from "lucide-react";
import { ProcessingStepper } from "./ProcessingStepper";
import { useCancelJob } from "../hooks/useApi";
import { useToast } from "./Toast";
import { ApiError } from "../api/client";
import type { JobProgress } from "../api/types";

const btnGhost =
  "inline-flex items-center gap-1.5 rounded-lg border border-line-soft px-2.5 py-1.5 text-muted hover:bg-surface-soft disabled:opacity-50";

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
              onError: (e) =>
                toast("err", e instanceof ApiError ? e.message : "Erro"),
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

The `btnGhost` string is copied verbatim from `Dashboard.tsx:19` so the visual is
identical. `Dashboard.tsx` keeps its own local `btnGhost` (it's still used there
for the "Reiniciar" button), so nothing is deleted from the Dashboard — the
shared component just gets its own copy of the constant.

### 2. `frontend/src/pages/Dashboard.tsx` — use the shared component

Replace the inline `status.data.active?.map((job) => <div ...>stepper + Limpar
button</div>)` block with:

```tsx
{status.data.active?.map((job) => (
  <ActiveJob key={job.file} job={job} />
))}
```

Remove the now-unused local cancel wiring / `X` import / `btnGhost` only if they
become unused (the page may still use them elsewhere — check before deleting).
Behavior is unchanged, so `dashboardCancel.test.tsx` must still pass.

### 3. `frontend/src/pages/MeetingDetail.tsx`

- Call `const status = useStatus();` (shared `["status"]` query, already polls
  every 2 s — no extra polling).
- `const activeJob = status.data?.active?.find((j) => j.file === id);`
- Render, just below the action buttons, when `activeJob` is truthy:

```tsx
{activeJob && (
  <Card title="Em processamento" eyebrow="Ao vivo" index="●">
    <ActiveJob job={activeJob} />
  </Card>
)}
```

- Disable both generate buttons while a job for this meeting is active:
  - transcript: `disabled={transcribe.isPending || sourceGone || !!activeJob}`
  - summary: `disabled={summarize.isPending || !!activeJob}`
- **Auto-refresh on completion.** Track previous `activeJob` presence; when it
  goes from present → absent, invalidate the queries that feed this page so the
  finished note appears without a manual reload:

```tsx
const qc = useQueryClient();
const wasActive = useRef(false);
useEffect(() => {
  const isActive = !!activeJob;
  if (wasActive.current && !isActive) {
    qc.invalidateQueries({ queryKey: ["meeting", id] });      // useMeeting note query
    qc.invalidateQueries({ queryKey: ["meeting-log", id] });
    qc.invalidateQueries({ queryKey: ["meetings"] });
    qc.invalidateQueries({ queryKey: ["history"] });
  }
  wasActive.current = isActive;
}, [activeJob, id, qc]);
```

The note-query key is confirmed: `MeetingDetail` loads the note via
`useMeeting(id)` (`useApi.ts:42`), whose key is `["meeting", id]`.

## Testing (TDD, Vitest — `frontend/src/__tests__/`)

- **`activeJob.test.tsx`** (new): render `<ActiveJob job={JOB} />` → the stepper
  renders (e.g. stage label visible) and a "Limpar" button is present; clicking
  it POSTs `{ file, started }` to `/api/process/cancel` (mirror
  `dashboardCancel.test.tsx`).
- **`meetingDetailStepper.test.tsx`** (new):
  - `/api/status` returns `{ active: [{ ...job, file: id }] }` ⇒ the
    "Em processamento" card + stepper render, and both "Gerar transcrição" and
    "Gerar resumo" buttons are `disabled`.
  - `/api/status` returns an active job whose `file !== id` (or empty) ⇒ no
    stepper card, buttons enabled.
- **Regression:** existing `dashboardCancel.test.tsx` and
  `processingStepper.test.tsx` must still pass after the refactor.

## Out of scope

- No backend changes — the `job.file === meeting_id` matching already holds.
- No change to `ProcessingStepper` visuals or the `/api/process/cancel` endpoint.
- Not testing the auto-refresh effect's invalidation directly (it depends on
  React Query internals); the present→absent logic is simple and covered by code
  review. Manual verification: finish a "Gerar resumo" and confirm the note
  updates in place.
