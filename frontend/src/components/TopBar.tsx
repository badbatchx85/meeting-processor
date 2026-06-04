import { useHealth, useWatcher } from "../hooks/useApi";
import { StatusBadge } from "./StatusBadge";

export function TopBar() {
  const health = useHealth();
  const watcher = useWatcher();
  return (
    <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3">
      <div className="text-sm text-slate-500">
        LLM: <span className="font-medium text-slate-700">{health.data?.llm_provider ?? "—"}</span>
      </div>
      <StatusBadge on={!!watcher.data?.running} labelOn="Watcher ativo" labelOff="Watcher offline" />
    </header>
  );
}
