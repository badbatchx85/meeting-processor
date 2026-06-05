import { CheckCircle2, XCircle } from "lucide-react";
import type { GenerationLogEntry } from "../api/types";

const ACTION_LABEL: Record<GenerationLogEntry["action"], string> = {
  transcript: "Transcrição",
  summary: "Resumo",
  delete_source: "Exclusão do arquivo",
};

function when(iso: string | null): string {
  if (!iso) return "";
  return iso.replace("T", " ").slice(0, 16);
}

export function GenerationLog({ entries }: { entries: GenerationLogEntry[] }) {
  // Defensive: a misbehaving/edge response could be non-array — never .map a non-array.
  if (!Array.isArray(entries) || entries.length === 0)
    return <p className="text-sm text-slate-500">Nenhuma geração registrada ainda.</p>;
  return (
    <ul className="divide-y divide-slate-100">
      {entries.map((e, i) => {
        const ok = e.status === "ok";
        return (
          <li key={`${e.started}-${i}`} className="flex items-start gap-2 py-2">
            {ok ? (
              <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-emerald-500" />
            ) : (
              <XCircle size={16} className="mt-0.5 shrink-0 text-rose-500" />
            )}
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-slate-700">{ACTION_LABEL[e.action]}</span>
                <span className={`ml-2 shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${
                  ok ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"}`}>
                  {ok ? "OK" : "erro"}
                </span>
              </div>
              {ok && e.detail && <p className="truncate text-xs text-slate-500">{e.detail}</p>}
              {!ok && e.error && <p className="text-xs text-rose-600">{e.error}</p>}
              <p className="text-xs text-slate-400">{when(e.completed || e.started)}</p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
