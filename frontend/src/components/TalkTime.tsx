import type { WordSegment } from "../api/types";
import { talkTime } from "../lib/talkTime";

function fmtClock(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function TalkTime({ segments }: { segments: WordSegment[] }): JSX.Element | null {
  const rows = talkTime(segments);
  if (rows.length === 0) return null;
  return (
    <div className="space-y-2">
      <h3 className="font-display text-sm font-semibold text-ink">Tempo de fala</h3>
      <ul className="space-y-1.5">
        {rows.map((r) => (
          <li key={r.speaker} className="flex items-center gap-3 text-sm">
            <span className="w-32 shrink-0 truncate text-ink">{r.speaker}</span>
            <span className="w-12 shrink-0 tabular-nums text-ink-soft">{fmtClock(r.seconds)}</span>
            <span className="h-2 flex-1 overflow-hidden rounded bg-ink/10">
              <span className="block h-full rounded bg-ink/40" style={{ width: `${r.pct}%` }} />
            </span>
            <span className="w-10 shrink-0 text-right tabular-nums text-ink-soft">
              {Math.round(r.pct)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
