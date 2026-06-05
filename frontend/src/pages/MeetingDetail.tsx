import { useState } from "react";
import { useParams } from "react-router-dom";
import { Sparkles, FileText, Trash2 } from "lucide-react";
import { Card } from "../components/Card";
import { MarkdownView } from "../components/MarkdownView";
import { GenerationLog } from "../components/GenerationLog";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import {
  useMeeting, useSummarizeMeeting, useTranscribeMeeting,
  useGenerationLog, useMeetingSource, useDeleteMeetingSource,
} from "../hooks/useApi";
import { ApiError } from "../api/client";

type Tab = "summary" | "tasks" | "transcript";

function formatBytes(n: number | null): string {
  if (n == null) return "";
  if (n < 1024) return `${n} B`;
  const units = ["KB", "MB", "GB"];
  let v = n / 1024, i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(1)} ${units[i]}`;
}

export function MeetingDetail() {
  const { id = "" } = useParams();
  const meeting = useMeeting(id);
  const summarize = useSummarizeMeeting();
  const transcribe = useTranscribeMeeting();
  const log = useGenerationLog(id);
  const source = useMeetingSource(id);
  const deleteSource = useDeleteMeetingSource();
  const toast = useToast();
  const [tab, setTab] = useState<Tab>("summary");
  const [confirmDelete, setConfirmDelete] = useState(false);

  const obsidianUri = `obsidian://open?path=${encodeURIComponent(id)}`;
  const tabs: { key: Tab; label: string }[] = [
    { key: "summary", label: "Resumo" },
    { key: "tasks", label: "Tarefas" },
    { key: "transcript", label: "Transcrição" },
  ];

  if (meeting.isLoading) return <p className="text-slate-500">Carregando…</p>;
  if (meeting.isError || !meeting.data) return <p className="text-rose-600">Reunião não encontrada.</p>;
  const d = meeting.data;
  const enc = encodeURIComponent(id);
  const sourceGone = source.data ? !source.data.exists : false;

  const generateSummary = () =>
    summarize.mutate(id, {
      onSuccess: () => toast("ok", "Gerando resumo — acompanhe abaixo e no Dashboard."),
      onError: (e) => toast("err", e instanceof ApiError ? e.message : "Erro"),
    });
  const generateTranscript = () =>
    transcribe.mutate(id, {
      onSuccess: () => toast("ok", "Gerando transcrição — acompanhe abaixo."),
      onError: (e) => toast("err", e instanceof ApiError ? e.message : "Erro"),
    });
  const removeSource = () =>
    deleteSource.mutate(id, {
      onSuccess: () => toast("ok", "Arquivo de origem apagado."),
      onError: (e) => toast("err", e instanceof ApiError ? e.message : "Erro"),
    });

  return (
    <Card title={d.title} actions={
      <div className="flex items-center gap-3 text-sm">
        <button onClick={generateTranscript} disabled={transcribe.isPending || sourceGone}
          title={sourceGone ? "Arquivo de origem indisponível" : ""}
          className="flex items-center gap-1 text-brand hover:underline disabled:opacity-40 disabled:no-underline">
          <FileText size={14} /> {transcribe.isPending ? "Enviando…" : "Gerar transcrição"}
        </button>
        <button onClick={generateSummary} disabled={summarize.isPending}
          className="flex items-center gap-1 text-brand hover:underline disabled:opacity-40">
          <Sparkles size={14} /> {summarize.isPending ? "Enviando…" : "Gerar resumo"}
        </button>
        <a href={`/api/meetings/${enc}/export.md`} className="text-brand hover:underline">Markdown</a>
        <a href={`/api/meetings/${enc}/export.docx`} className="text-brand hover:underline">Word</a>
        <a href={obsidianUri} className="text-brand hover:underline">Abrir no Obsidian</a>
      </div>
    }>
      <div className="mb-3 flex items-center gap-3 text-xs text-slate-500">
        <span className="font-medium text-slate-600">Arquivo de origem:</span>
        {source.data?.exists ? (
          <>
            <span>{source.data.name} · {formatBytes(source.data.size)}</span>
            <button onClick={() => setConfirmDelete(true)} disabled={deleteSource.isPending}
              className="flex items-center gap-1 text-slate-400 hover:text-rose-600 disabled:opacity-40">
              <Trash2 size={13} /> Apagar arquivo de origem
            </button>
          </>
        ) : (
          <span className="italic">indisponível</span>
        )}
      </div>

      {(d.meta.purpose || d.meta.meeting_type) && (
        <div className="mb-4 flex items-center gap-2">
          {d.meta.meeting_type && (
            <span className="rounded-full bg-brand/10 px-2.5 py-0.5 text-xs font-medium text-brand">
              {d.meta.meeting_type}
            </span>
          )}
          {d.meta.purpose && <p className="text-sm text-slate-600">{d.meta.purpose}</p>}
        </div>
      )}
      <div className="mb-4 flex gap-1 border-b border-slate-200">
        {tabs.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${
              tab === t.key ? "border-brand text-brand" : "border-transparent text-slate-500 hover:text-slate-700"}`}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === "summary" && (d.resumo_md.trim().length > 0 ? (
        <MarkdownView>{d.resumo_md}</MarkdownView>
      ) : (
        <p className="py-6 text-sm text-slate-500">
          Sem resumo ainda — use "Gerar resumo" acima.
        </p>
      ))}
      {tab === "transcript" && <MarkdownView>{d.transcricao_md}</MarkdownView>}
      {tab === "tasks" && (
        <ul className="space-y-1">
          {d.tasks.length === 0 && <li className="text-slate-500">Sem tarefas.</li>}
          {d.tasks.map((t, i) => (
            <li key={i} className="flex items-center gap-2">
              <input type="checkbox" checked={t.done} readOnly />
              <span className={t.done ? "text-slate-400 line-through" : ""}>{t.description}</span>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-6 border-t border-slate-100 pt-4">
        <h3 className="mb-2 text-sm font-semibold text-slate-700">Log de geração</h3>
        <GenerationLog entries={log.data ?? []} />
      </div>

      <ConfirmDialog open={confirmDelete}
        title="Apagar o arquivo de origem? A transcrição e o resumo são mantidos, mas não será possível gerar a transcrição novamente."
        onConfirm={() => { setConfirmDelete(false); removeSource(); }}
        onCancel={() => setConfirmDelete(false)} />
    </Card>
  );
}
