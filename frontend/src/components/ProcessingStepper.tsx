import { CheckCircle2, Circle, Loader2, Ban } from "lucide-react";
import type { JobProgress, StageStep } from "../api/types";

function StageIcon({ state }: { state: StageStep["state"] }) {
  if (state === "done") return <CheckCircle2 size={16} className="shrink-0 text-emerald-500" />;
  if (state === "active") return <Loader2 size={16} className="shrink-0 animate-spin text-brand" />;
  if (state === "skipped") return <Ban size={16} className="shrink-0 text-slate-300" />;
  return <Circle size={16} className="shrink-0 text-slate-300" />;
}

export function ProcessingStepper({ job }: { job: JobProgress }) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between text-sm">
        <span className="truncate font-medium text-slate-700">{job.file}</span>
        <span className="ml-3 shrink-0 font-medium text-slate-600">{job.percent}%</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200">
        <div
          className="h-full bg-brand transition-all duration-500"
          style={{ width: `${job.percent}%` }}
        />
      </div>

      <ul className="flex flex-col gap-1.5">
        {job.stages.map((s) => (
          <li key={s.key} className="flex flex-col gap-0.5">
            <div className="flex items-center gap-2 text-sm">
              <StageIcon state={s.state} />
              <span
                className={
                  s.state === "skipped"
                    ? "text-slate-400 line-through"
                    : s.state === "active"
                      ? "font-medium text-slate-700"
                      : s.state === "done"
                        ? "text-slate-500"
                        : "text-slate-400"
                }
              >
                {s.label}
                {s.state === "skipped" && " (desativada)"}
              </span>
            </div>
            {s.state === "active" && (
              <div className="ml-6 flex items-center gap-2">
                <div className="h-1.5 w-32 overflow-hidden rounded-full bg-slate-200">
                  <div className="h-full bg-brand transition-all" style={{ width: `${s.percent}%` }} />
                </div>
                <span className="text-xs text-slate-500">
                  {s.percent}%{s.detail ? ` · ${s.detail}` : ""}
                </span>
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
