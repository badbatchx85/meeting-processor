import { useEffect, useState } from "react";
import { useMeetingSpeakers, useSetSpeakerNames } from "../hooks/useApi";

export function SpeakerNames({ meetingId }: { meetingId: string }) {
  const sp = useMeetingSpeakers(meetingId);
  const save = useSetSpeakerNames(meetingId);
  const [names, setNames] = useState<Record<string, string>>({});

  useEffect(() => {
    if (sp.data) setNames(sp.data.names ?? {});
  }, [sp.data]);

  const detected = sp.data?.detected ?? [];
  if (detected.length === 0) return null;

  return (
    <div className="mb-4 rounded-lg border border-line bg-surface p-3">
      <p className="eyebrow mb-2">Falantes</p>
      <div className="flex flex-col gap-2">
        {detected.map((label) => (
          <label key={label} className="flex items-center gap-2 text-sm">
            <span className="w-24 shrink-0 font-mono text-xs text-muted">{label}</span>
            <input
              value={names[label] ?? ""}
              placeholder={label}
              onChange={(e) => setNames((n) => ({ ...n, [label]: e.target.value }))}
              className="flex-1 rounded-md border border-line px-2 py-1 text-sm"
            />
          </label>
        ))}
      </div>
      <button
        onClick={() => save.mutate(names)}
        disabled={save.isPending}
        className="mt-3 rounded-lg border border-line px-3 py-1.5 text-[13px] font-medium hover:border-ink hover:bg-ink hover:text-paper disabled:opacity-40"
      >
        {save.isPending ? "Salvando…" : "Salvar nomes"}
      </button>
    </div>
  );
}
