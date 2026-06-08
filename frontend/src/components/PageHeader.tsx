import type { ReactNode } from "react";

export function PageHeader({
  index,
  eyebrow,
  title,
  description,
  actions,
}: {
  index?: string;
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-x-6 gap-y-4 border-b border-line pb-6">
      <div className="min-w-0">
        <div className="flex items-center gap-3">
          {index && <span className="index-num">{index}</span>}
          {eyebrow && <span className="eyebrow">{eyebrow}</span>}
        </div>
        <h1 className="mt-3 font-display text-4xl font-bold leading-[0.95] tracking-tightest text-ink md:text-5xl">
          {title}
        </h1>
        {description && <p className="mt-3 max-w-xl text-sm leading-relaxed text-muted">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}
