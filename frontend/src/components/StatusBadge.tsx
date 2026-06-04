export function StatusBadge({ on, labelOn, labelOff }: { on: boolean; labelOn: string; labelOff: string }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${
      on ? "bg-emerald-100 text-emerald-700" : "bg-slate-200 text-slate-600"}`}>
      <span className={`h-2 w-2 rounded-full ${on ? "bg-emerald-500" : "bg-slate-400"}`} />
      {on ? labelOn : labelOff}
    </span>
  );
}
