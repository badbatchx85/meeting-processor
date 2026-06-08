import { useHealth, useWatcher } from "../hooks/useApi";
import { StatusBadge } from "./StatusBadge";

export function TopBar() {
  const health = useHealth();
  const watcher = useWatcher();
  return (
    <header className="sticky top-0 z-10 flex items-center justify-between border-b border-line bg-paper px-6 py-3">
      <div className="flex items-center gap-2 text-sm">
        <span className="eyebrow">LLM</span>
        <span className="font-mono text-[13px] font-medium text-ink">{health.data?.llm_provider ?? "—"}</span>
      </div>
      <StatusBadge on={!!watcher.data?.running} labelOn="Watcher ativo" labelOff="Watcher offline" />
    </header>
  );
}
