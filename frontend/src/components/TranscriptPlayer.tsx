import { useRef, useState } from "react";
import { MarkdownView } from "./MarkdownView";
import type { WordSegment } from "../api/types";

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
  words = null,
  seekTo = null,
}: {
  meetingId: string;
  markdown: string;
  hasSource: boolean;
  words?: WordSegment[] | null;
  seekTo?: number | null;
}) {
  const segments = parseTranscript(markdown);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [activeIdx, setActiveIdx] = useState(-1);
  const wlVideoRef = useRef<HTMLVideoElement>(null);
  const [wlTime, setWlTime] = useState(0);

  // Deep-link da busca: posiciona o vídeo no trecho assim que os metadados
  // carregam (currentTime só "pega" depois disso).
  const seekOnLoad = (v: HTMLVideoElement | null) => {
    if (v && seekTo != null && seekTo > 0) v.currentTime = seekTo;
  };

  if (hasSource && words && words.length > 0) {
    const seekWord = (s: number) => {
      const v = wlVideoRef.current;
      if (v) { v.currentTime = s; void v.play(); }
    };
    return (
      <div className="flex flex-col gap-4">
        <video ref={wlVideoRef} controls preload="metadata"
          onLoadedMetadata={() => seekOnLoad(wlVideoRef.current)}
          onTimeUpdate={() => setWlTime(wlVideoRef.current?.currentTime ?? 0)}
          src={`/api/meetings/${encodeURIComponent(meetingId)}/media`}
          className="w-full rounded-lg bg-black" />
        <p className="text-sm leading-7 text-ink-soft">
          {words.flatMap((seg, si) =>
            (seg.words ?? []).map((w, wi) => {
              const active = wlTime >= w.start && wlTime < w.end;
              return (
                <button key={`${si}-${wi}`} onClick={() => seekWord(w.start)}
                  aria-label={`Ir para palavra: ${w.text}`}
                  className={active ? "rounded bg-brand/20 px-0.5" : "px-0.5 hover:bg-line-soft"}>
                  {w.text}{" "}
                </button>
              );
            }),
          )}
        </p>
      </div>
    );
  }

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
        onLoadedMetadata={() => seekOnLoad(videoRef.current)}
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
