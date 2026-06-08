import { useEffect, useState } from "react";
import { Card } from "../components/Card";
import { PageHeader } from "../components/PageHeader";
import { useToast } from "../components/Toast";
import { useConfig, useLlm, useSetProvider, useSetModel, useSetKey, useSetWatchDir, useSetSteps, useLocalModels, usePullModel, usePullStatus } from "../hooks/useApi";
import { ApiError } from "../api/client";
import type { Llm, Steps } from "../api/types";

// Provedores que usam chave de API (local/none não usam).
const KEY_PROVIDERS = ["anthropic", "openai", "gemini"] as const;
function keyIsSet(llm: Llm | undefined, provider: string): boolean {
  if (!llm) return false;
  if (provider === "anthropic") return llm.anthropic_key_set;
  if (provider === "openai") return llm.openai_key_set;
  if (provider === "gemini") return llm.gemini_key_set;
  return false;
}

const STEP_LABELS: { key: keyof Steps; label: string }[] = [
  { key: "summary", label: "Resumo (IA)" },
  { key: "note", label: "Nota Obsidian" },
  { key: "kanban", label: "Kanban" },
  { key: "wiki", label: "Wiki" },
];

// Modelos sugeridos por provedor (atalhos de UI; "Outro…" aceita qualquer id).
const MODEL_OPTIONS: Record<string, string[]> = {
  anthropic: ["claude-sonnet-4-20250514", "claude-opus-4-20250514", "claude-3-5-sonnet-latest", "claude-3-5-haiku-latest"],
  openai: ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "o3-mini"],
  gemini: ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-pro", "gemini-1.5-flash"],
  local: ["qwen2.5:7b", "qwen2.5:14b", "llama3.1:8b", "gemma2:9b"],
};
const CUSTOM = "__custom__";

// O modelo atual de um provedor, conforme o backend (/api/llm).
function currentModel(llm: Llm | undefined, provider: string): string {
  if (!llm) return "";
  if (provider === "local") return llm.ollama_model ?? "";
  if (provider === "openai") return llm.openai_model ?? "";
  if (provider === "gemini") return llm.gemini_model ?? "";
  if (provider === "anthropic") return llm.anthropic_model ?? "";
  return "";
}

export function Settings() {
  const llm = useLlm();
  const config = useConfig();
  const setProvider = useSetProvider();
  const setModel = useSetModel();
  const setKey = useSetKey();
  const setWatchDir = useSetWatchDir();
  const setSteps = useSetSteps();
  const toast = useToast();

  const [watchDir, setWatchDirValue] = useState("");
  const [steps, setStepsValue] = useState<Steps>({ summary: true, note: true, kanban: true, wiki: true });
  const [model, setModelValue] = useState("");
  const [custom, setCustom] = useState(false);
  const [apiKey, setApiKey] = useState("");

  // Seed the form from the backend's current config once it loads.
  useEffect(() => {
    if (config.data) {
      setWatchDirValue(config.data.watch_dir ?? "");
      setStepsValue(config.data.steps);
    }
  }, [config.data]);

  const provider = llm.data?.provider ?? "";
  const isLocal = provider === "local";
  const localModels = useLocalModels(isLocal);
  const pull = usePullModel();
  const pullStatus = usePullStatus(isLocal);
  // Quando o download termina, atualiza a lista de instalados.
  const pullDone = pullStatus.data?.done;
  useEffect(() => {
    if (pullDone) localModels.refetch();
  }, [pullDone]); // eslint-disable-line react-hooks/exhaustive-deps
  // Seed the model from the active provider's current value.
  useEffect(() => {
    setModelValue(currentModel(llm.data, provider));
    setCustom(false);
  }, [llm.data, provider]);

  const onError = (e: unknown) => toast("err", e instanceof ApiError ? e.message : "Erro");

  const modelOptions = isLocal
    ? Array.from(new Set([...(localModels.data?.installed ?? []), model].filter(Boolean)))
    : provider in MODEL_OPTIONS
      ? Array.from(new Set([...MODEL_OPTIONS[provider], model].filter(Boolean)))
      : [];

  const saveModel = () =>
    setModel.mutate(
      { provider, model: model.trim() },
      { onSuccess: () => toast("ok", "Modelo atualizado."), onError },
    );

  const doPull = (m: string) =>
    pull.mutate(m, {
      onSuccess: () => toast("ok", `Baixando ${m}… clique Atualizar quando terminar.`),
      onError,
    });

  const saveKey = () =>
    setKey.mutate(
      { provider, key: apiKey.trim() },
      {
        onSuccess: () => { toast("ok", "Chave salva."); setApiKey(""); },
        onError,
      },
    );

  return (
    <div>
      <PageHeader
        index="05"
        eyebrow="Ajustes"
        title="Configuração"
        description="Provedor de IA, pasta monitorada e quais etapas rodar."
      />
      <div className="grid max-w-2xl gap-6">
      <Card title="Provedor LLM" eyebrow="IA" index="A">
        <div className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-muted">Provedor</span>
            <select value={provider} disabled={!llm.data}
              onChange={(e) => setProvider.mutate(e.target.value, {
                onSuccess: () => toast("ok", "Provedor atualizado."), onError })}
              className="rounded-lg border border-line px-3 py-2 text-sm">
              {(llm.data?.valid_providers ?? []).map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </label>

          {(KEY_PROVIDERS as readonly string[]).includes(provider) && (
            <label className="flex flex-col gap-1 text-sm">
              <span className="flex items-center gap-2 text-muted">
                Chave de API
                <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                  keyIsSet(llm.data, provider) ? "bg-emerald-100 text-emerald-700" : "bg-line text-muted"}`}>
                  {keyIsSet(llm.data, provider) ? "✓ configurada" : "não configurada"}
                </span>
              </span>
              <div className="flex gap-2">
                <input type="password" aria-label="Chave de API"
                  value={apiKey} onChange={(e) => setApiKey(e.target.value)}
                  placeholder={keyIsSet(llm.data, provider) ? "•••••••• (já configurada — cole para trocar)" : "cole a chave de API"}
                  className="flex-1 rounded-lg border border-line px-3 py-2 text-sm" />
                <button onClick={saveKey} disabled={setKey.isPending || !apiKey.trim()}
                  className="rounded-lg bg-brand px-3 py-2 text-sm text-white hover:bg-brand-dark disabled:opacity-50">
                  Salvar chave
                </button>
              </div>
            </label>
          )}

          {isLocal && (
            <div className="flex flex-col gap-2 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-muted">Modelo local (Ollama)</span>
                <button onClick={() => localModels.refetch()}
                  className="text-xs text-brand hover:underline">Atualizar</button>
              </div>
              {localModels.isLoading ? (
                <p className="text-muted-soft">Consultando o Ollama…</p>
              ) : !localModels.data?.ollama_running ? (
                <p className="text-amber-700">
                  Ollama não está rodando. Inicie com <code>ollama serve</code> ou instale em{" "}
                  <a className="text-brand hover:underline" href="https://ollama.com" target="_blank" rel="noreferrer">ollama.com</a>.
                </p>
              ) : localModels.data.installed.length > 0 ? (
                <>
                  <div className="flex gap-2">
                    <select aria-label="Modelo" value={custom ? CUSTOM : model}
                      onChange={(e) => {
                        if (e.target.value === CUSTOM) { setCustom(true); setModelValue(""); }
                        else { setCustom(false); setModelValue(e.target.value); }
                      }}
                      className="flex-1 rounded-lg border border-line px-3 py-2 text-sm">
                      {modelOptions.map((m) => <option key={m} value={m}>{m}</option>)}
                      <option value={CUSTOM}>Outro (personalizado)…</option>
                    </select>
                    <button onClick={saveModel} disabled={setModel.isPending || !model.trim()}
                      className="rounded-lg bg-brand px-3 py-2 text-sm text-white hover:bg-brand-dark disabled:opacity-50">
                      Salvar modelo
                    </button>
                  </div>
                  {custom && (
                    <input value={model} onChange={(e) => setModelValue(e.target.value)}
                      placeholder="ex.: qwen2.5:7b"
                      className="rounded-lg border border-line px-3 py-2 text-sm" />
                  )}
                </>
              ) : (
                <div className="flex flex-col gap-2">
                  {pullStatus.data?.model && !pullStatus.data.done && (
                    <div className="flex flex-col gap-1">
                      <span className="text-xs text-muted">
                        Baixando {pullStatus.data.model} — {pullStatus.data.percent ?? 0}%
                        {pullStatus.data.status ? ` (${pullStatus.data.status})` : ""}
                      </span>
                      <div className="h-2 w-full overflow-hidden rounded-full bg-line">
                        <div className="h-full bg-brand transition-all"
                          style={{ width: `${pullStatus.data.percent ?? 0}%` }} />
                      </div>
                    </div>
                  )}
                  <p className="text-muted">Nenhum modelo instalado. Baixe um recomendado:</p>
                  {localModels.data.suggested.map((m) => (
                    <div key={m} className="flex items-center justify-between gap-2">
                      <code className="text-xs text-muted">{m}</code>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-muted-soft">ollama pull {m}</span>
                        <button aria-label={`Baixar ${m}`} onClick={() => doPull(m)} disabled={pull.isPending}
                          className="rounded-lg bg-brand px-2.5 py-1 text-xs text-white hover:bg-brand-dark disabled:opacity-50">
                          Baixar
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {!isLocal && provider in MODEL_OPTIONS && (
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-muted">Modelo</span>
              <div className="flex gap-2">
                <select aria-label="Modelo"
                  value={custom ? CUSTOM : model}
                  onChange={(e) => {
                    if (e.target.value === CUSTOM) { setCustom(true); setModelValue(""); }
                    else { setCustom(false); setModelValue(e.target.value); }
                  }}
                  className="flex-1 rounded-lg border border-line px-3 py-2 text-sm">
                  {modelOptions.map((m) => <option key={m} value={m}>{m}</option>)}
                  <option value={CUSTOM}>Outro (personalizado)…</option>
                </select>
                <button onClick={saveModel} disabled={setModel.isPending || !model.trim()}
                  className="rounded-lg bg-brand px-3 py-2 text-sm text-white hover:bg-brand-dark disabled:opacity-50">
                  Salvar modelo
                </button>
              </div>
              {custom && (
                <input value={model} onChange={(e) => setModelValue(e.target.value)}
                  placeholder="id do modelo (ex.: gpt-4o, gemini-1.5-pro)"
                  className="mt-1 rounded-lg border border-line px-3 py-2 text-sm" />
              )}
            </label>
          )}
        </div>
      </Card>

      <Card title="Pasta monitorada" eyebrow="Watcher" index="B">
        <div className="flex gap-2">
          <input value={watchDir} onChange={(e) => setWatchDirValue(e.target.value)}
            placeholder="~/Videos/OBS" className="flex-1 rounded-lg border border-line px-3 py-2 text-sm" />
          <button onClick={() => setWatchDir.mutate(watchDir, {
            onSuccess: (r) => toast("ok", (r as { exists?: boolean })?.exists ? "Pasta salva." : "Salva (pasta ainda não existe)."), onError })}
            className="rounded-lg bg-brand px-3 py-2 text-sm text-white hover:bg-brand-dark">Salvar</button>
        </div>
      </Card>

      <Card title="Etapas do processamento" eyebrow="Pipeline" index="C">
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
    </div>
  );
}
