import type { WordSegment } from "../api/types";

export interface TalkTimeRow {
  speaker: string;
  seconds: number;
  pct: number;
}

export function talkTime(segments: WordSegment[] | null): TalkTimeRow[] {
  if (!Array.isArray(segments) || segments.length === 0) return [];
  const totals = new Map<string, number>();
  for (const s of segments) {
    if (s.speaker == null) continue;
    totals.set(s.speaker, (totals.get(s.speaker) ?? 0) + Math.max(0, s.end - s.start));
  }
  if (totals.size < 2) return [];
  const total = [...totals.values()].reduce((a, b) => a + b, 0);
  const rows: TalkTimeRow[] = [...totals.entries()].map(([speaker, seconds]) => ({
    speaker,
    seconds,
    pct: total > 0 ? (seconds / total) * 100 : 0,
  }));
  rows.sort((a, b) => b.seconds - a.seconds);
  return rows;
}
