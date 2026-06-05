import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Play, Square, RotateCw, FileVideo, Upload, Loader2 } from "lucide-react";
import { Card } from "../components/Card";
import { StatusBadge } from "../components/StatusBadge";
import { EmptyState } from "../components/EmptyState";
import { useToast } from "../components/Toast";
import { useHealth, useWatcher, useMeetings, useWatcherControl, useProcessFile, useUploadFile, useStatus, useHistory } from "../hooks/useApi";
import { ConversionHistory } from "../components/ConversionHistory";
import { ApiError } from "../api/client";

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  const units = ["KB", "MB", "GB"];
  let v = n / 1024;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(1)} ${units[i]}`;
}

export function Dashboard() {
  const health = useHealth();
  const watcher = useWatcher();
  const meetings = useMeetings();
  const { start, stop, restart } = useWatcherControl();
  const process = useProcessFile();
  const upload = useUploadFile();
  const status = useStatus();
  const history = useHistory();
  const toast = useToast();
  const qc = useQueryClient();
  const [file, setFile] = useState("");
  const [selected, setSelected] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Quando um job termina (lista de ativos esvazia), recarrega as reuniões.
  const activeCount = status.data?.active.length ?? 0;
  const prevActive = useRef(0);
  useEffect(() => {
    if (prevActive.current > 0 && activeCount === 0) {
      qc.invalidateQueries({ queryKey: ["meetings"] });
      qc.invalidateQueries({ queryKey: ["history"] });
    }
    prevActive.current = activeCount;
  }, [activeCount, qc]);

  const submit = () => {
    if (!file.trim()) return;
    process.mutate(file.trim(), {
      onSuccess: () => { toast("ok", "Processamento enfileirado."); setFile(""); },
      onError: (e) => toast("err", e instanceof ApiError ? e.message : "Erro"),
    });
  };

  const submitUpload = () => {
    if (!selected) return;
    upload.mutate(selected, {
      onSuccess: () => {
        toast("ok", "Arquivo enviado — processando.");
        setSelected(null);
        if (fileInputRef.current) fileInputRef.current.value = "";
      },
      onError: (e) => toast("err", e instanceof ApiError ? e.message : "Erro no envio"),
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
        <div className="flex flex-col gap-4">
          {/* Enviar do computador */}
          <div className="flex flex-col gap-2">
            <label className="text-sm font-medium text-slate-600">Enviar do seu computador</label>
            <input
              ref={fileInputRef}
              type="file"
              accept=".mkv,.mp4,.webm,video/*"
              onChange={(e) => setSelected(e.target.files?.[0] ?? null)}
              className="block w-full text-sm text-slate-600 file:mr-3 file:cursor-pointer file:rounded-lg file:border-0 file:bg-brand file:px-3 file:py-2 file:text-sm file:font-medium file:text-white hover:file:bg-brand-dark"
            />
            {selected && (
              <p className="text-xs text-slate-500">{selected.name} · {formatBytes(selected.size)}</p>
            )}
            {upload.progress !== null && (
              <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200">
                <div className="h-full bg-brand transition-all" style={{ width: `${upload.progress}%` }} />
              </div>
            )}
            <button onClick={submitUpload} disabled={!selected || upload.isPending}
              className="flex items-center justify-center gap-1.5 rounded-lg bg-brand px-3 py-2 text-sm text-white hover:bg-brand-dark disabled:opacity-50">
              <Upload size={15}/> {upload.isPending ? `Enviando… ${upload.progress ?? 0}%` : "Enviar e processar"}
            </button>
          </div>

          {/* Divisória */}
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <span className="h-px flex-1 bg-slate-200" /> ou um caminho no servidor <span className="h-px flex-1 bg-slate-200" />
          </div>

          {/* Caminho no servidor */}
          <div className="flex flex-col gap-2">
            <input value={file} onChange={(e) => setFile(e.target.value)}
              placeholder="/Users/voce/Videos/reuniao.mp4"
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            <button onClick={submit} disabled={process.isPending}
              className="flex items-center justify-center gap-1.5 rounded-lg bg-slate-200 px-3 py-2 text-sm text-slate-700 hover:bg-slate-300 disabled:opacity-50">
              <FileVideo size={15}/> {process.isPending ? "Enviando…" : "Processar caminho"}
            </button>
          </div>
        </div>
      </Card>

      {status.data && status.data.active.length > 0 && (
        <div className="lg:col-span-2">
          <Card title="Em processamento">
            <div className="flex flex-col gap-5">
              {status.data.active.map((job) => (
                <div key={job.file} className="flex flex-col gap-1.5">
                  <div className="flex items-center justify-between text-sm">
                    <span className="flex items-center gap-2 truncate font-medium text-slate-700">
                      <Loader2 size={15} className="shrink-0 animate-spin text-brand" />
                      {job.file}
                    </span>
                    <span className="ml-3 shrink-0 text-xs text-slate-400">
                      {job.stage_number > 0 ? `Etapa ${job.stage_number}/${job.stage_total}` : "Aguardando"}
                    </span>
                  </div>
                  <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200">
                    <div className="h-full bg-brand transition-all duration-500" style={{ width: `${job.percent}%` }} />
                  </div>
                  <div className="flex items-center justify-between text-xs text-slate-500">
                    <span className="truncate">{job.stage_label}{job.detail ? ` · ${job.detail}` : ""}</span>
                    <span className="ml-3 shrink-0 font-medium text-slate-600">{job.percent}%</span>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

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

      <div className="lg:col-span-2">
        <Card title="Conversões recentes">
          <ConversionHistory entries={history.data ?? []} limit={5} />
        </Card>
      </div>
    </div>
  );
}
