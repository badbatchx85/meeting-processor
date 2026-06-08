import { CheckCircle2, XCircle } from "lucide-react";
import type { HistoryEntry } from "../api/types";
import { EmptyState } from "./EmptyState";

function when(iso: string | null): string {
  if (!iso) return "";
  // "2026-06-04T09:05:00" → "2026-06-04 09:05"
  return iso.replace("T", " ").slice(0, 16);
}

export function ConversionHistory({
  entries,
  limit,
}: {
  entries: HistoryEntry[];
  limit?: number;
}) {
  if (entries.length === 0) {
    return <EmptyState title="Nenhuma conversão ainda" hint="Processe um arquivo para começar." />;
  }
  const rows = limit ? entries.slice(0, limit) : entries;

  return (
    <ul className="divide-y divide-line-soft">
      {rows.map((e) => {
        const ok = e.status === "completed";
        return (
          <li key={`${e.file}-${e.started}`} className="flex items-start gap-2 py-2">
            {ok ? (
              <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-emerald-500" />
            ) : (
              <XCircle size={16} className="mt-0.5 shrink-0 text-rose-500" />
            )}
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate font-mono text-[13px] text-ink-soft">{e.file}</span>
                <span
                  className={`ml-2 shrink-0 rounded-full px-2 py-0.5 font-mono text-[10px] uppercase tracking-label ${
                    ok ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200" : "bg-rose-50 text-rose-700 ring-1 ring-rose-200"
                  }`}
                >
                  {ok ? "OK" : "erro"}
                </span>
              </div>
              {ok && e.detail && <p className="truncate text-xs text-muted">{e.detail}</p>}
              {!ok && (
                <p className="text-xs text-rose-600">
                  {e.failed_stage ? `${e.failed_stage}: ` : ""}
                  {e.error ?? "Falha"}
                </p>
              )}
              {(e.completed || e.started) && (
                <p className="font-mono text-[11px] text-muted-soft">{when(e.completed || e.started)}</p>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
