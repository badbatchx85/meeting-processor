import { useState } from "react";
import { Link } from "react-router-dom";
import { Play, Square, RotateCw, FileVideo } from "lucide-react";
import { Card } from "../components/Card";
import { StatusBadge } from "../components/StatusBadge";
import { EmptyState } from "../components/EmptyState";
import { useToast } from "../components/Toast";
import { useHealth, useWatcher, useMeetings, useWatcherControl, useProcessFile } from "../hooks/useApi";
import { ApiError } from "../api/client";

export function Dashboard() {
  const health = useHealth();
  const watcher = useWatcher();
  const meetings = useMeetings();
  const { start, stop, restart } = useWatcherControl();
  const process = useProcessFile();
  const toast = useToast();
  const [file, setFile] = useState("");

  const submit = () => {
    if (!file.trim()) return;
    process.mutate(file.trim(), {
      onSuccess: () => { toast("ok", "Processamento enfileirado."); setFile(""); },
      onError: (e) => toast("err", e instanceof ApiError ? e.message : "Erro"),
    });
  };

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card title="Status">
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <span className="text-slate-600">Watcher</span>
            <StatusBadge on={!!watcher.data?.running} labelOn={`ativo (pid ${watcher.data?.pid})`} labelOff="offline" />
          </div>
          <div className="flex items-center justify-between">
            <span className="text-slate-600">Provedor LLM</span>
            <span className="font-medium">{health.data?.llm_provider ?? "—"}</span>
          </div>
          <div className="mt-2 flex gap-2">
            <button onClick={() => start.mutate()} className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-sm text-white hover:bg-emerald-700"><Play size={15}/> Iniciar</button>
            <button onClick={() => stop.mutate()} className="flex items-center gap-1.5 rounded-lg bg-slate-600 px-3 py-1.5 text-sm text-white hover:bg-slate-700"><Square size={15}/> Parar</button>
            <button onClick={() => restart.mutate()} className="flex items-center gap-1.5 rounded-lg bg-slate-200 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-300"><RotateCw size={15}/> Reiniciar</button>
          </div>
        </div>
      </Card>

      <Card title="Processar um arquivo">
        <div className="flex flex-col gap-2">
          <label className="text-sm text-slate-600">Caminho do vídeo no disco</label>
          <input value={file} onChange={(e) => setFile(e.target.value)}
            placeholder="/Users/voce/Videos/reuniao.mp4"
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm" />
          <button onClick={submit} disabled={process.isPending}
            className="flex items-center justify-center gap-1.5 rounded-lg bg-brand px-3 py-2 text-sm text-white hover:bg-brand-dark disabled:opacity-50">
            <FileVideo size={15}/> {process.isPending ? "Enviando…" : "Processar"}
          </button>
        </div>
      </Card>

      <div className="lg:col-span-2">
        <Card title="Reuniões recentes">
          {meetings.data && meetings.data.length > 0 ? (
            <ul className="divide-y divide-slate-100">
              {meetings.data.slice(0, 5).map((m) => (
                <li key={m.id} className="py-2">
                  <Link to={`/meetings/${encodeURIComponent(m.id)}`} className="flex items-center justify-between hover:text-brand">
                    <span className="truncate">{m.title}</span>
                    <span className="ml-3 shrink-0 text-xs text-slate-400">{m.task_count} tarefas</span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="Nenhuma reunião ainda" hint="Processe um arquivo para começar." />
          )}
        </Card>
      </div>
    </div>
  );
}
