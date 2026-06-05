import { useState } from "react";
import { useParams } from "react-router-dom";
import { Card } from "../components/Card";
import { MarkdownView } from "../components/MarkdownView";
import { useMeeting } from "../hooks/useApi";

type Tab = "summary" | "tasks" | "transcript";

export function MeetingDetail() {
  const { id = "" } = useParams();
  const meeting = useMeeting(id);
  const [tab, setTab] = useState<Tab>("summary");

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

  return (
    <Card title={d.title} actions={
      <div className="flex items-center gap-3 text-sm">
        <a href={`/api/meetings/${enc}/export.md`} className="text-brand hover:underline">Markdown</a>
        <a href={`/api/meetings/${enc}/export.docx`} className="text-brand hover:underline">Word</a>
        <a href={obsidianUri} className="text-brand hover:underline">Abrir no Obsidian</a>
      </div>
    }>
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

      {tab === "summary" && <MarkdownView>{d.resumo_md}</MarkdownView>}
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
    </Card>
  );
}
