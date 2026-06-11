import { useState } from "react";
import { Link } from "react-router-dom";
import { Trash2, Search, FileText, Sparkles, ArrowUpRight } from "lucide-react";
import { Card } from "../components/Card";
import { PageHeader } from "../components/PageHeader";
import { EmptyState } from "../components/EmptyState";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import { useMeetings, useDeleteMeeting, useHistory, useTranscribeMeeting, useSummarizeMeeting } from "../hooks/useApi";
import { ConversionHistory } from "../components/ConversionHistory";
import { ApiError } from "../api/client";
import { sortMeetings, type SortKey } from "../lib/sortMeetings";

export function Meetings() {
  const meetings = useMeetings();
  const history = useHistory();
  const del = useDeleteMeeting();
  const transcribe = useTranscribeMeeting();
  const summarize = useSummarizeMeeting();
  const toast = useToast();
  const [q, setQ] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("created");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const toggleSort = (key: SortKey) => {
    if (key === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(key); setSortDir(key === "title" ? "asc" : "desc"); }
  };
  const arrow = (key: SortKey) => (sortKey === key ? (sortDir === "asc" ? " ↑" : " ↓") : "");
  const [pending, setPending] = useState<string | null>(null);

  const term = q.toLowerCase();
  const filtered = (meetings.data ?? []).filter((m) =>
    `${m.title} ${m.purpose ?? ""} ${m.meeting_type ?? ""}`.toLowerCase().includes(term),
  );
  const items = sortMeetings(filtered, sortKey, sortDir);

  const runTranscribe = (id: string) =>
    transcribe.mutate(id, {
      onSuccess: () => toast("ok", "Gerando transcrição — acompanhe no Dashboard."),
      onError: (e) => toast("err", e instanceof ApiError ? e.message : "Erro"),
    });
  const runSummarize = (id: string) =>
    summarize.mutate({ id }, {
      onSuccess: () => toast("ok", "Gerando resumo — acompanhe no Dashboard."),
      onError: (e) => toast("err", e instanceof ApiError ? e.message : "Erro"),
    });

  const confirmDelete = () => {
    if (!pending) return;
    del.mutate(pending, {
      onSuccess: () => toast("ok", "Reunião apagada."),
      onError: (e) => toast("err", e instanceof ApiError ? e.message : "Erro"),
    });
    setPending(null);
  };

  const iconBtn =
    "grid h-8 w-8 place-items-center rounded-md text-muted-soft transition-colors hover:bg-line-soft hover:text-ink disabled:opacity-30 disabled:hover:bg-transparent disabled:hover:text-muted-soft";

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        index="02"
        eyebrow="Arquivo"
        title="Reuniões"
        description="Todas as reuniões processadas — inclusive as que só têm transcrição."
        actions={
          <label className="flex items-center gap-2 rounded-lg border border-line bg-surface px-3 focus-within:border-ink">
            <Search size={15} className="text-muted-soft" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Buscar…"
              className="w-40 bg-transparent py-2 text-sm outline-none placeholder:text-muted-soft"
            />
          </label>
        }
      />

      <Card>
        {items.length > 0 ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left">
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
              </tr>
            </thead>
            <tbody className="divide-y divide-line-soft">
              {items.map((m) => (
                <tr key={m.id} className="group transition-colors hover:bg-line-soft/40">
                  <td className="py-3.5 pr-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <Link
                        to={`/meetings/${encodeURIComponent(m.id)}`}
                        className="font-medium text-ink decoration-line-soft underline-offset-4 hover:underline"
                      >
                        {m.title}
                      </Link>
                      {m.meeting_type && (
                        <span className="rounded-full border border-line bg-line-soft px-2 py-0.5 text-[11px] font-medium text-ink-soft">
                          {m.meeting_type}
                        </span>
                      )}
                      {!m.has_summary && (
                        <span className="rounded-full px-2 py-0.5 font-mono text-[10px] uppercase tracking-label text-muted-soft ring-1 ring-line">
                          só transcrição
                        </span>
                      )}
                    </div>
                    {m.purpose && <p className="mt-1 text-xs text-muted-soft">{m.purpose}</p>}
                  </td>
                  <td className="font-mono text-[13px] tabular-nums text-muted">{m.created || "—"}</td>
                  <td className="font-mono text-[13px] tabular-nums text-muted">{m.duration || "—"}</td>
                  <td className="font-mono text-[13px] tabular-nums text-muted">{m.task_count}</td>
                  <td className="text-right">
                    <div className="flex items-center justify-end gap-1 opacity-60 transition-opacity group-hover:opacity-100">
                      <button
                        onClick={() => runTranscribe(m.id)}
                        disabled={transcribe.isPending || m.source_exists === false}
                        aria-label={`Gerar transcrição da ${m.title}`}
                        title={m.source_exists === false ? "Arquivo de origem indisponível" : "Gerar transcrição"}
                        className={iconBtn}
                      >
                        <FileText size={15} />
                      </button>
                      <button
                        onClick={() => runSummarize(m.id)}
                        disabled={summarize.isPending}
                        aria-label={`Gerar resumo da ${m.title}`}
                        title="Gerar resumo"
                        className={iconBtn}
                      >
                        <Sparkles size={15} />
                      </button>
                      <Link
                        to={`/meetings/${encodeURIComponent(m.id)}`}
                        aria-label={`Abrir ${m.title}`}
                        title="Abrir"
                        className={iconBtn}
                      >
                        <ArrowUpRight size={15} />
                      </Link>
                      <button
                        onClick={() => setPending(m.id)}
                        aria-label={`Apagar ${m.title}`}
                        title="Apagar"
                        className={`${iconBtn} hover:bg-rose-50 hover:text-rose-600`}
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <EmptyState title="Nenhuma reunião encontrada" hint="Processe um vídeo no Dashboard para começar." />
        )}
        <ConfirmDialog open={!!pending} title="Apagar esta reunião?" onConfirm={confirmDelete} onCancel={() => setPending(null)} />
      </Card>

      <Card title="Histórico de conversões" eyebrow="Auditoria" index="↻">
        <ConversionHistory entries={history.data ?? []} />
      </Card>
    </div>
  );
}
