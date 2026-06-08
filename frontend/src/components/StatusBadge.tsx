export function StatusBadge({ on, labelOn, labelOff }: { on: boolean; labelOn: string; labelOff: string }) {
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 font-mono text-[11px] uppercase tracking-label ${
        on ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-line bg-line-soft text-muted"
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${on ? "animate-pulse bg-emerald-500" : "bg-muted-soft"}`} />
      {on ? labelOn : labelOff}
    </span>
  );
}
