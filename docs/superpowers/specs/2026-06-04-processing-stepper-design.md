# Dashboard Multi-Step Processing Stepper

**Date:** 2026-06-04
**Status:** Approved design

## Goal

Show the meeting-conversion pipeline as a **multi-step vertical checklist** on the
SPA Dashboard's "Em processamento" card: each of the 6 phases evolves through
done → active → pending (or skipped), the active phase shows a live mini-percent
+ detail, and an overall progress bar + percent sits on top.

## The 6 phases (source of truth: `dashboard.py` `STAGES`)

| # | key | label |
|---|-----|-------|
| 1 | `audio` | Extraindo audio |
| 2 | `transcription` | Transcrevendo com Whisper (reports a live sub-%) |
| 3 | `summary` | Gerando resumo com LLM |
| 4 | `note` | Criando nota da reuniao |
| 5 | `kanban` | Criando quadro Kanban |
| 6 | `wiki` | Integrando com wiki |

Phases 3–6 are optional; when disabled the pipeline calls `job.skip(key)`.

## Architecture decision

The backend owns the phase list and per-phase state. `/api/status` is extended
to emit a `stages` array per active job; the frontend renders it verbatim and
does **not** re-hardcode the 6 labels (DRY — avoids label/i18n drift). The
overall `percent` math is **unchanged** (computed over all 6 phases; a run with
phases off tops out below 100% — pre-existing, intentionally out of scope).

## Components & changes

### Backend

1. **`meeting_processor/dashboard.py`** — `_save_history`: add
   `"skipped": sorted(j.skipped)` to each persisted entry. Currently the
   in-memory `job.skipped` set is dropped on save, so `/api/status` (which reads
   the history JSON) can't know which phases were skipped.

2. **`meeting_processor/web/app.py`** — `_job_progress(entry)`: add a `stages`
   key to the returned dict (all existing keys unchanged). Build one item per
   `STAGES` entry:
   ```python
   {"key": key, "label": label, "state": state, "percent": pct, "detail": detail}
   ```
   where, given `stage_idx = entry.get("stage", -1)`,
   `skipped = set(entry.get("skipped", []))`,
   `stage_progress = entry.get("stage_progress") or {}`,
   `details = entry.get("details") or {}`:
   - `state = "skipped"` if `key in skipped`
   - else `"done"` if `i < stage_idx`
   - else `"active"` if `i == stage_idx`
   - else `"pending"`
   - `pct = 100` if state == "done"; `int(stage_progress.get(key, 0))` if
     "active"; else `0`
   - `detail = details.get(key, "")`

   Back-compat: entries written before change 1 have no `skipped` key →
   `set()` → no phases shown as skipped (they fall through to done/pending).

### Frontend

3. **`frontend/src/api/types.ts`** — add:
   ```ts
   export interface StageStep {
     key: string; label: string;
     state: "done" | "active" | "pending" | "skipped";
     percent: number; detail: string;
   }
   ```
   and `stages: StageStep[];` on the existing `JobProgress` interface.

4. **`frontend/src/components/ProcessingStepper.tsx`** (new) — renders one job:
   - Header row: filename (truncated) + overall `percent`%.
   - Overall progress bar (reuse the existing bar style: `bg-slate-200` track,
     `bg-brand` fill at `job.percent`%).
   - Vertical list of `job.stages`, one row each:
     - icon by state — lucide `CheckCircle2` (done, emerald), spinning `Loader2`
       (active, brand), `Circle` (pending, slate-300), `Ban` (skipped, slate-300);
     - label (skipped → muted + "(desativada)" suffix, strikethrough-muted);
     - active row only: a mini-bar + `{percent}%` and `· {detail}` when present.
   - Pure presentational component; takes `job: JobProgress`, no data fetching.

5. **`frontend/src/pages/Dashboard.tsx`** — in the "Em processamento" card,
   replace the current inline per-job block with
   `{status.data.active.map((job) => <ProcessingStepper key={job.file} job={job} />)}`.
   Polling/refresh logic (`useStatus`, the active-count effect) is unchanged.

## Data flow

```
pipeline (skip/advance/set_progress) → ProcessingJob
  → _save_history → .processing-history.json  (now incl. "skipped")
  → GET /api/status → _job_progress builds job.stages[]
  → SPA useStatus (poll 3s) → <ProcessingStepper job> → vertical checklist
```

## Error handling / edge cases

- `stage_idx == -1` (waiting): every phase `pending` (or `skipped`); overall 0%.
- `stage_idx >= 6` (finalizing): every non-skipped phase `done`.
- Old history entries without `skipped`: treated as none skipped (back-compat).
- A job leaves the `active` list once completed/errored (existing behavior); the
  card disappears, list reloads (existing effect).

## Testing (TDD)

**Backend (`tests/`):**
- `_job_progress` (or via `GET /api/status` with a fixture history entry):
  given `stage=1` (transcription) with `stage_progress={"transcription":50}`,
  assert `stages` has 6 items; `audio` → done/100, `transcription` →
  active/50 with its detail, `summary..wiki` → pending/0.
- Given an entry with `skipped: ["kanban","wiki"]`, assert those two stages have
  `state == "skipped"`.

**Frontend (`frontend/src/__tests__/`):**
- `ProcessingStepper.test.tsx`: render a job whose `stages` mixes done/active/
  pending/skipped; assert the active phase shows its label + `%`, a done phase is
  present, a skipped phase shows its label, and the overall `percent` renders.

## Out of scope

- Whisper **model-download** progress (terminal-only; needs backend stream hooks).
- Changing the overall `percent` denominator for skipped phases.
- Any change to the Obsidian dashboard renderer (`_render_active_job`).
- History/past-meeting step visualization (this is for the active card only).
