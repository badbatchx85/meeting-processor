import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { Sparkles, FileText, Trash2, Download, FileType, ExternalLink } from "lucide-react";
import { Card } from "../components/Card";
import { MarkdownView } from "../components/MarkdownView";
import { GenerationLog } from "../components/GenerationLog";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { useToast } from "../components/Toast";
import {
  useMeeting, useSummarizeMeeting, useTranscribeMeeting,
  useGenerationLog, useMeetingSource, useDeleteMeetingSource, useStatus,
} from "../hooks/useApi";
import { ApiError } from "../api/client";
import { useQueryClient } from "@tanstack/react-query";
import { ActiveJob } from "../components/ActiveJob";
import { TranscriptPlayer } from "../components/TranscriptPlayer";

type Tab = "summary" | "tasks" | "transcript";

function formatBytes(n: number | null): string {
  if (n == null) return "";
  if (n < 1024) return `${n} B`;
  const units = ["KB", "MB", "GB"];
  let v = n / 1024, i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(1)} ${units[i]}`;
}

const chip =
  "inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-[13px] font-medium text-ink transition-colors hover:border-ink hover:bg-ink hover:text-paper disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-ink";
// Export actions share the chip shape but read as a quieter "secondary" group:
// muted text/border at rest, inverting to ink on hover like the primary chips.
const exportChip =
  "inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-[13px] font-medium text-muted transition-colors hover:border-ink hover:bg-ink hover:text-paper";

export function MeetingDetail() {
  const { id = "" } = useParams();
  const meeting = useMeeting(id);
  const summarize = useSummarizeMeeting();
  const transcribe = useTranscribeMeeting();
  const log = useGenerationLog(id);
  const source = useMeetingSource(id);
  const deleteSource = useDeleteMeetingSource();
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

  const toast = useToast();
  const [tab, setTab] = useState<Tab>("summary");
  const [confirmDelete, setConfirmDelete] = useState(false);

  const obsidianUri = `obsidian://open?path=${encodeURIComponent(id)}`;
  const tabs: { key: Tab; label: string }[] = [
    { key: "summary", label: "Resumo" },
    { key: "tasks", label: "Tarefas" },
    { key: "transcript", label: "Transcrição" },
  ];

  if (meeting.isLoading) return <p className="text-muted">Carregando…</p>;
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
    <div className="flex flex-col gap-6">
      {/* Editorial header */}
      <header className="border-b border-line pb-6">
        <div className="flex items-center gap-3">
          <span className="index-num">▶</span>
          <span className="eyebrow">Reunião</span>
          {d.meta.meeting_type && (
            <span className="rounded-full border border-line bg-line-soft px-2 py-0.5 text-[11px] font-medium text-ink-soft">
              {d.meta.meeting_type}
            </span>
          )}
        </div>
        <h1 className="mt-3 break-words font-display text-2xl font-bold tracking-tightest text-ink md:text-[28px]">
          {d.title}
        </h1>
        {d.meta.purpose && <p className="mt-2 max-w-2xl text-sm text-muted">{d.meta.purpose}</p>}

        {/* Toolbar */}
        <div className="mt-5 flex flex-wrap items-center gap-2">
          <button
            onClick={generateTranscript}
            disabled={transcribe.isPending || sourceGone || !!activeJob}
            title={sourceGone ? "Arquivo de origem indisponível" : ""}
            className={chip}
          >
            <FileText size={14} /> {transcribe.isPending ? "Enviando…" : "Gerar transcrição"}
          </button>
          <button onClick={generateSummary} disabled={summarize.isPending || !!activeJob} className={chip}>
            <Sparkles size={14} /> {summarize.isPending ? "Enviando…" : "Gerar resumo"}
          </button>
          <span className="mx-1 h-5 w-px bg-line" />
          <a href={`/api/meetings/${enc}/export.md`} className={exportChip}>
            <Download size={14} /> Markdown
          </a>
          <a href={`/api/meetings/${enc}/export.docx`} className={exportChip}>
            <FileType size={14} /> Word
          </a>
          <a href={obsidianUri} className={exportChip}>
            <ExternalLink size={14} /> Abrir no Obsidian
          </a>
        </div>

        {/* Source line */}
        <div className="mt-4 flex flex-wrap items-center gap-3 text-xs">
          <span className="eyebrow">Arquivo de origem</span>
          {source.data?.exists ? (
            <>
              <span className="font-mono text-[12px] text-ink-soft">
                {source.data.name} · {formatBytes(source.data.size)}
              </span>
              <button
                onClick={() => setConfirmDelete(true)}
                disabled={deleteSource.isPending}
                className="inline-flex items-center gap-1 text-muted-soft transition-colors hover:text-rose-600 disabled:opacity-40"
              >
                <Trash2 size={13} /> Apagar arquivo de origem
              </button>
            </>
          ) : (
            <span className="font-mono text-[12px] italic text-muted-soft">indisponível</span>
          )}
        </div>
      </header>

      {activeJob && (
        <Card title="Em processamento" eyebrow="Ao vivo" index="●">
          <ActiveJob job={activeJob} />
        </Card>
      )}

      {/* Tabs + content */}
      <Card>
        <div className="-mt-1 mb-5 flex gap-6 border-b border-line">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`-mb-px border-b-2 pb-3 text-sm font-medium tracking-tight transition-colors ${
                tab === t.key ? "border-ink text-ink" : "border-transparent text-muted hover:text-ink"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {tab === "summary" && (d.resumo_md.trim().length > 0 ? (
          <MarkdownView>{d.resumo_md}</MarkdownView>
        ) : (
          <p className="py-6 text-sm text-muted">Sem resumo ainda — use "Gerar resumo" acima.</p>
        ))}
        {tab === "transcript" && (
          <TranscriptPlayer meetingId={id} markdown={d.transcricao_md} hasSource={source.data?.exists ?? false} />
        )}
        {tab === "tasks" && (
          <ul className="space-y-2">
            {d.tasks.length === 0 && <li className="text-muted">Sem tarefas.</li>}
            {d.tasks.map((t, i) => (
              <li key={i} className="flex items-center gap-2.5 text-sm">
                <input type="checkbox" checked={t.done} readOnly className="h-4 w-4 rounded border-line accent-ink" />
                <span className={t.done ? "text-muted-soft line-through" : "text-ink-soft"}>{t.description}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* Generation log */}
      <Card title="Log de geração" eyebrow="Auditoria" index="↻">
        <GenerationLog entries={log.data ?? []} />
      </Card>

      <ConfirmDialog open={confirmDelete}
        title="Apagar o arquivo de origem? A transcrição e o resumo são mantidos, mas não será possível gerar a transcrição novamente."
        onConfirm={() => { setConfirmDelete(false); removeSource(); }}
        onCancel={() => setConfirmDelete(false)} />
    </div>
  );
}
