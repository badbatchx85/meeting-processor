import { useRef, useState } from "react";
import { MarkdownView } from "./MarkdownView";

export interface TranscriptSegment {
  seconds: number;
  label: string;
  text: string;
}

const LINE_RE = /^\*\*\[(\d{1,2}:\d{2}(?::\d{2})?)\]\*\*\s*(.*)$/;

export function parseTranscript(md: string): TranscriptSegment[] {
  const out: TranscriptSegment[] = [];
  for (const line of md.split("\n")) {
    const m = line.match(LINE_RE);
    if (!m) continue;
    const parts = m[1].split(":").map(Number);
    const seconds =
      parts.length === 3
        ? parts[0] * 3600 + parts[1] * 60 + parts[2]
        : parts[0] * 60 + parts[1];
    out.push({ seconds, label: m[1], text: m[2] });
  }
  return out;
}

export function TranscriptPlayer({
  meetingId,
  markdown,
  hasSource,
}: {
  meetingId: string;
  markdown: string;
  hasSource: boolean;
}) {
  const segments = parseTranscript(markdown);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [activeIdx, setActiveIdx] = useState(-1);

  if (!hasSource || segments.length === 0) {
    return <MarkdownView>{markdown}</MarkdownView>;
  }

  const seek = (i: number, seconds: number) => {
    const v = videoRef.current;
    if (v) {
      v.currentTime = seconds;
      void v.play();
    }
    setActiveIdx(i);
  };

  const onTime = () => {
    const t = videoRef.current?.currentTime ?? 0;
    let idx = -1;
    for (let i = 0; i < segments.length; i++) {
      if (segments[i].seconds <= t) idx = i;
      else break;
    }
    setActiveIdx(idx);
  };

  return (
    <div className="flex flex-col gap-4">
      <video
        ref={videoRef}
        controls
        preload="metadata"
        onTimeUpdate={onTime}
        src={`/api/meetings/${encodeURIComponent(meetingId)}/media`}
        className="w-full rounded-lg bg-black"
      />
      <ul className="flex flex-col gap-1 text-sm">
        {segments.map((s, i) => (
          <li key={i} className={i === activeIdx ? "rounded bg-line-soft px-1" : "px-1"}>
            <button
              onClick={() => seek(i, s.seconds)}
              aria-label={`Ir para ${s.label}`}
              className="mr-2 font-mono text-xs text-brand hover:underline"
            >
              [{s.label}]
            </button>
            <span className="text-ink-soft">{s.text}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
