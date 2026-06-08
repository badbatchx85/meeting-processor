import type { ReactNode } from "react";

export function EmptyState({ icon, title, hint }: { icon?: ReactNode; title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center gap-3 border border-dashed border-line py-14 text-center">
      {icon && <div className="text-muted-soft">{icon}</div>}
      <p className="font-display text-base font-semibold tracking-tight text-ink">{title}</p>
      {hint && <p className="max-w-xs text-sm text-muted">{hint}</p>}
    </div>
  );
}
