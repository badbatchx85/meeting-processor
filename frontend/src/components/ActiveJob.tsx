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
