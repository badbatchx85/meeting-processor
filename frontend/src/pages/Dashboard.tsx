import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Play, Square, RotateCw, FileVideo, Upload } from "lucide-react";
import { Card } from "../components/Card";
import { PageHeader } from "../components/PageHeader";
import { StatusBadge } from "../components/StatusBadge";
import { EmptyState } from "../components/EmptyState";
import { useToast } from "../components/Toast";
import { useHealth, useWatcher, useMeetings, useWatcherControl, useProcessFile, useUploadFile, useStatus, useHistory } from "../hooks/useApi";
import { ConversionHistory } from "../components/ConversionHistory";
import { ProcessingStepper } from "../components/ProcessingStepper";
import { ApiError } from "../api/client";

const btnPrimary =
  "inline-flex items-center justify-center gap-1.5 rounded-lg bg-ink px-3.5 py-2 text-sm font-medium text-paper transition-colors hover:bg-ink-soft disabled:opacity-40";
const btnOutline =
  "inline-flex items-center justify-center gap-1.5 rounded-lg border border-line px-3.5 py-2 text-sm font-medium text-ink transition-colors hover:border-ink hover:bg-ink hover:text-paper disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-ink";
const btnGhost =
  "inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-muted transition-colors hover:bg-line-soft hover:text-ink";

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
  const [transcriptOnly, setTranscriptOnly] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Quando um job termina (lista de ativos esvazia), recarrega as reuniões.
  const activeCount = status.data?.active?.length ?? 0;
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
    process.mutate(
      { file: file.trim(), mode: transcriptOnly ? "transcript" : "full" },
      {
        onSuccess: () => { toast("ok", "Processamento enfileirado."); setFile(""); },
        onError: (e) => toast("err", e instanceof ApiError ? e.message : "Erro"),
      },
    );
  };

  const submitUpload = () => {
    if (!selected) return;
    upload.mutate(
      { file: selected, mode: transcriptOnly ? "transcript" : "full" },
      {
        onSuccess: () => {
          toast("ok", "Arquivo enviado — processando.");
          setSelected(null);
          if (fileInputRef.current) fileInputRef.current.value = "";
        },
        onError: (e) => toast("err", e instanceof ApiError ? e.message : "Erro no envio"),
      },
    );
  };

  return (
    <div>
      <PageHeader
        index="01"
        eyebrow="Painel"
        title="Dashboard"
        description="Envie uma gravação, acompanhe o processamento e revise as reuniões — tudo local."
        actions={<StatusBadge on={!!watcher.data?.running} labelOn="Watcher ativo" labelOff="Watcher offline" />}
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Status" eyebrow="Serviço" index="A">
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between border-b border-line-soft pb-3">
              <span className="eyebrow">Watcher</span>
              <StatusBadge on={!!watcher.data?.running} labelOn={`ativo · pid ${watcher.data?.pid}`} labelOff="offline" />
            </div>
            <div className="flex items-center justify-between border-b border-line-soft pb-3">
              <span className="eyebrow">Provedor LLM</span>
              <span className="font-mono text-[13px] font-medium text-ink">{health.data?.llm_provider ?? "—"}</span>
            </div>
            <div className="mt-1 flex gap-2">
              <button onClick={() => start.mutate()} className={btnPrimary}><Play size={15} /> Iniciar</button>
              <button onClick={() => stop.mutate()} className={btnOutline}><Square size={15} /> Parar</button>
              <button onClick={() => restart.mutate()} className={btnGhost}><RotateCw size={15} /> Reiniciar</button>
            </div>
          </div>
        </Card>

        <Card title="Processar um arquivo" eyebrow="Entrada" index="B">
          <div className="flex flex-col gap-5">
            <label className="flex cursor-pointer items-center gap-2.5 text-sm text-ink-soft">
              <input
                type="checkbox"
                checked={transcriptOnly}
                onChange={(e) => setTranscriptOnly(e.target.checked)}
                className="h-4 w-4 rounded border-line accent-ink"
              />
              Apenas transcrição (sem resumo)
            </label>

            {/* Enviar do computador */}
            <div className="flex flex-col gap-2">
              <span className="eyebrow">Enviar do seu computador</span>
              <input
                ref={fileInputRef}
                type="file"
                accept=".mkv,.mp4,.webm,video/*"
                onChange={(e) => setSelected(e.target.files?.[0] ?? null)}
                className="block w-full text-sm text-muted file:mr-3 file:cursor-pointer file:rounded-lg file:border-0 file:bg-ink file:px-3 file:py-2 file:text-sm file:font-medium file:text-paper hover:file:bg-ink-soft"
              />
              {selected && (
                <p className="font-mono text-xs text-muted">{selected.name} · {formatBytes(selected.size)}</p>
              )}
              {upload.progress !== null && (
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-line">
                  <div className="h-full bg-ink transition-all" style={{ width: `${upload.progress}%` }} />
                </div>
              )}
              <button onClick={submitUpload} disabled={!selected || upload.isPending} className={btnPrimary}>
                <Upload size={15} /> {upload.isPending ? `Enviando… ${upload.progress ?? 0}%` : "Enviar e processar"}
              </button>
            </div>

            {/* Divisória */}
            <div className="flex items-center gap-3 font-mono text-[10px] uppercase tracking-label text-muted-soft">
              <span className="h-px flex-1 bg-line" /> ou um caminho no servidor <span className="h-px flex-1 bg-line" />
            </div>

            {/* Caminho no servidor */}
            <div className="flex flex-col gap-2">
              <input
                value={file}
                onChange={(e) => setFile(e.target.value)}
                placeholder="/Users/voce/Videos/reuniao.mp4"
                className="rounded-lg border border-line bg-surface px-3 py-2 font-mono text-[13px] outline-none placeholder:text-muted-soft focus:border-ink"
              />
              <button onClick={submit} disabled={process.isPending} className={btnOutline}>
                <FileVideo size={15} /> {process.isPending ? "Enviando…" : "Processar caminho"}
              </button>
            </div>
          </div>
        </Card>

        {status.data && status.data.active?.length > 0 && (
          <div className="lg:col-span-2">
            <Card title="Em processamento" eyebrow="Ao vivo" index="●">
              <div className="flex flex-col gap-6">
                {status.data.active?.map((job) => (
                  <ProcessingStepper key={job.file} job={job} />
                ))}
              </div>
            </Card>
          </div>
        )}

        <Card title="Reuniões recentes" eyebrow="Arquivo" index="02">
          {meetings.data && meetings.data.length > 0 ? (
            <ul className="divide-y divide-line-soft">
              {meetings.data.slice(0, 5).map((m) => (
                <li key={m.id}>
                  <Link to={`/meetings/${encodeURIComponent(m.id)}`} className="flex items-center justify-between gap-3 py-2.5 text-sm transition-colors hover:text-ink">
                    <span className="truncate text-ink-soft">{m.title}</span>
                    <span className="shrink-0 font-mono text-xs tabular-nums text-muted-soft">{m.task_count} tarefas</span>
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState title="Nenhuma reunião ainda" hint="Processe um arquivo para começar." />
          )}
        </Card>

        <Card title="Conversões recentes" eyebrow="Auditoria" index="↻">
          <ConversionHistory entries={history.data ?? []} limit={5} />
        </Card>
      </div>
    </div>
  );
}
