import type { ReactNode } from "react";

export function Card({
  title,
  eyebrow,
  index,
  children,
  actions,
}: {
  title?: string;
  eyebrow?: string;
  index?: string;
  children: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <section className="overflow-hidden rounded-card border border-line bg-surface shadow-card">
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-line-soft px-5 py-4">
          <div className="flex min-w-0 items-baseline gap-3">
            {index && <span className="index-num">{index}</span>}
            <div className="min-w-0">
              {eyebrow && <p className="eyebrow mb-1">{eyebrow}</p>}
              {title && (
                <h2 className="truncate font-display text-lg font-semibold tracking-tightest text-ink">
                  {title}
                </h2>
              )}
            </div>
          </div>
          {actions && <div className="shrink-0">{actions}</div>}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}
