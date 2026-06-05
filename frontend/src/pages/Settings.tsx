import { useEffect, useState } from "react";
import { Card } from "../components/Card";
import { useToast } from "../components/Toast";
import { useConfig, useLlm, useSetProvider, useSetWatchDir, useSetSteps } from "../hooks/useApi";
import { ApiError } from "../api/client";
import type { Steps } from "../api/types";

const STEP_LABELS: { key: keyof Steps; label: string }[] = [
  { key: "summary", label: "Resumo (IA)" },
  { key: "note", label: "Nota Obsidian" },
  { key: "kanban", label: "Kanban" },
  { key: "wiki", label: "Wiki" },
];

export function Settings() {
  const llm = useLlm();
  const config = useConfig();
  const setProvider = useSetProvider();
  const setWatchDir = useSetWatchDir();
  const setSteps = useSetSteps();
  const toast = useToast();

  const [watchDir, setWatchDirValue] = useState("");
  const [steps, setStepsValue] = useState<Steps>({ summary: true, note: true, kanban: true, wiki: true });

  // Seed the form from the backend's current config once it loads.
  useEffect(() => {
    if (config.data) {
      setWatchDirValue(config.data.watch_dir ?? "");
      setStepsValue(config.data.steps);
    }
  }, [config.data]);

  const onError = (e: unknown) => toast("err", e instanceof ApiError ? e.message : "Erro");

  return (
    <div className="grid max-w-2xl gap-6">
      <Card title="Provedor LLM">
        <select value={llm.data?.provider ?? ""} disabled={!llm.data}
          onChange={(e) => setProvider.mutate(e.target.value, {
            onSuccess: () => toast("ok", "Provedor atualizado."), onError })}
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm">
          {(llm.data?.valid_providers ?? []).map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
      </Card>

      <Card title="Pasta monitorada">
        <div className="flex gap-2">
          <input value={watchDir} onChange={(e) => setWatchDirValue(e.target.value)}
            placeholder="~/Videos/OBS" className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm" />
          <button onClick={() => setWatchDir.mutate(watchDir, {
            onSuccess: (r) => toast("ok", (r as { exists?: boolean })?.exists ? "Pasta salva." : "Salva (pasta ainda não existe)."), onError })}
            className="rounded-lg bg-brand px-3 py-2 text-sm text-white hover:bg-brand-dark">Salvar</button>
        </div>
      </Card>

      <Card title="Etapas do processamento">
        <div className="flex flex-col gap-2">
          {STEP_LABELS.map(({ key, label }) => (
            <label key={key} className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={steps[key]}
                onChange={(e) => setStepsValue((s) => ({ ...s, [key]: e.target.checked }))} />
              {label}
            </label>
          ))}
          <button onClick={() => setSteps.mutate(steps, { onSuccess: () => toast("ok", "Etapas salvas."), onError })}
            className="mt-2 w-fit rounded-lg bg-brand px-3 py-2 text-sm text-white hover:bg-brand-dark">Salvar etapas</button>
        </div>
      </Card>
    </div>
  );
}
