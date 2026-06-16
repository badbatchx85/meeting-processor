# Speaker Renaming (sub-project A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user rename diarization labels (`Falante 1 → Ana`) per meeting; saving rewrites the `.md` (Obsidian + web show names) while the sidecar keeps the original labels.

**Architecture:** A per-meeting `speakers.json` map (keyed by original label) + a `speaker_names` module that regenerates the `.md` from the untouched segment sidecar with the map applied; GET/POST endpoints; a frontend rename panel.

**Tech Stack:** Python 3.14, FastAPI; React/Vitest. Python tests `.venv/bin/python -m pytest`; frontend from `frontend/` `npx vitest run <f>` + `npx tsc --noEmit`.

---

## File Structure
- **Modify** `meeting_processor/note_generator.py` — broaden the sidecar gate.
- **Create** `meeting_processor/speaker_names.py` — map I/O, detect, apply, regenerate `.md`.
- **Modify** `meeting_processor/web/app.py` — GET/POST `/speakers`, `/words` applies the map.
- **Modify** `frontend/src/{api/types.ts,hooks/useApi.ts,pages/MeetingDetail.tsx}`; **Create** `frontend/src/components/SpeakerNames.tsx`.
- **Create** `tests/test_speaker_renaming.py`, `frontend/src/__tests__/speakerNames.test.tsx`.

---

### Task 1: Broaden the segment sidecar gate

**Files:** Modify `meeting_processor/note_generator.py`; Create `tests/test_speaker_renaming.py`.

- [ ] **Step 1: Write the failing test** — create `tests/test_speaker_renaming.py`:

```python
"""Renomeação de falantes (sub-projeto A)."""
from datetime import datetime

from meeting_processor.models import Transcript, TranscriptSegment
from meeting_processor.note_generator import NoteGenerator


def test_sidecar_written_for_diarized_without_words(config):
    ng = NoteGenerator(config)
    paths = ng.prepare("reu.mp4", datetime(2026, 1, 1, 10, 0, 0))
    seg = TranscriptSegment(start=0, end=1, text="oi", speaker="Falante 1")  # words=None
    ng.write_transcription(Transcript(segments=[seg], full_text="oi", language="pt", duration=1), paths)
    assert paths.raw_path.with_suffix(".words.json").exists()
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_speaker_renaming.py -q`
Expected: FAIL — current gate is `any(s.words ...)`; a speaker-only segment writes no sidecar.

- [ ] **Step 3: Broaden the gate.** In `meeting_processor/note_generator.py` `write_transcription`, change:

```python
        if any(s.words for s in transcript.segments):
```

to:

```python
        if any(s.words or s.speaker for s in transcript.segments):
```

- [ ] **Step 4: Run to verify it passes + regression**

Run: `.venv/bin/python -m pytest tests/test_speaker_renaming.py tests/test_word_timestamps.py -q`
Expected: PASS (the new test + the existing words-sidecar tests — words-only still writes; `test_no_sidecar_without_words` still passes since a segment with neither words nor speaker writes nothing).

- [ ] **Step 5: Commit**

```bash
git add meeting_processor/note_generator.py tests/test_speaker_renaming.py
git commit -m "feat(speakers): write the segment sidecar for any diarized meeting"
```

---

### Task 2: `speaker_names` module

**Files:** Create `meeting_processor/speaker_names.py`; Test: `tests/test_speaker_renaming.py`.

- [ ] **Step 1: Append the failing tests:**

```python
# --- Task 2: speaker_names module ------------------------------------------

import json

from meeting_processor import speaker_names as sn


def _seed_sidecar(config, folder, segs):
    d = config.reunioes_path / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / f"Transcricao - {folder}.words.json").write_text(json.dumps(segs), encoding="utf-8")
    return d


def test_names_roundtrip_and_blank_dropped(config):
    d = config.reunioes_path / "m1"
    d.mkdir(parents=True, exist_ok=True)
    sn.write_names(d, {"Falante 1": "Ana", "Falante 2": "  "})
    assert sn.read_names(d) == {"Falante 1": "Ana"}     # blank dropped


def test_detected_labels_distinct_in_order(config):
    d = _seed_sidecar(config, "m2", [
        {"start": 0, "end": 1, "text": "a", "speaker": "Falante 2", "words": None},
        {"start": 1, "end": 2, "text": "b", "speaker": "Falante 1", "words": None},
        {"start": 2, "end": 3, "text": "c", "speaker": "Falante 2", "words": None},
        {"start": 3, "end": 4, "text": "d", "speaker": None, "words": None},
    ])
    assert sn.detected_labels(d) == ["Falante 2", "Falante 1"]


def test_apply_names_maps_and_passes_through():
    segs = [{"start": 0, "end": 1, "text": "a", "speaker": "Falante 1", "words": None},
            {"start": 1, "end": 2, "text": "b", "speaker": "Falante 9", "words": None}]
    out = sn.apply_names(segs, {"Falante 1": "Ana"})
    assert out[0]["speaker"] == "Ana" and out[1]["speaker"] == "Falante 9"


def test_regenerate_md_idempotent(config):
    d = _seed_sidecar(config, "m3", [
        {"start": 0, "end": 1, "text": "oi", "speaker": "Falante 1", "words": None},
        {"start": 1, "end": 2, "text": "ola", "speaker": "Falante 2", "words": None},
    ])
    md = d / "Transcricao - m3.md"
    side = d / "Transcricao - m3.words.json"
    before = side.read_text(encoding="utf-8")

    sn.regenerate_md(config, d, {"Falante 1": "Ana"})
    text = md.read_text(encoding="utf-8")
    assert "Ana: oi" in text and "Falante 2: ola" in text
    assert side.read_text(encoding="utf-8") == before          # sidecar untouched

    sn.regenerate_md(config, d, {"Falante 1": "Carlos"})        # re-rename
    text2 = md.read_text(encoding="utf-8")
    assert "Carlos: oi" in text2 and "Ana" not in text2        # no accumulation
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_speaker_renaming.py -k "names or detected or apply or regenerate" -q`
Expected: FAIL — no `meeting_processor.speaker_names`.

- [ ] **Step 3: Create `meeting_processor/speaker_names.py`:**

```python
"""Mapa de nomes de falantes por reunião (Falante N -> nome real)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .config import Settings
from .models import Transcript, TranscriptSegment, WordTime
from .utils import write_json_atomic

logger = logging.getLogger(__name__)


def names_path(meeting_dir: Path) -> Path:
    return meeting_dir / "speakers.json"


def read_names(meeting_dir: Path) -> dict[str, str]:
    """Mapa {rótulo original: nome}; {} se ausente/ilegível; valores vazios fora."""
    p = names_path(meeting_dir)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if str(v).strip()}


def write_names(meeting_dir: Path, names: dict) -> None:
    clean = {str(k): str(v).strip() for k, v in (names or {}).items() if str(v).strip()}
    write_json_atomic(names_path(meeting_dir), clean)


def _segments_sidecar(meeting_dir: Path) -> Path | None:
    hits = list(meeting_dir.glob("Transcricao - *.words.json"))
    return hits[0] if hits else None


def detected_labels(meeting_dir: Path) -> list[str]:
    """Rótulos de falante distintos no sidecar, na ordem de primeira aparição."""
    side = _segments_sidecar(meeting_dir)
    if side is None:
        return []
    try:
        raw = json.loads(side.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    out: list[str] = []
    for s in raw:
        sp = s.get("speaker")
        if sp and sp not in out:
            out.append(sp)
    return out


def apply_names(segments: list[dict], names: dict) -> list[dict]:
    """Cópias dos segmentos com speaker mapeado (não muta a entrada/sidecar)."""
    out = []
    for s in segments:
        c = dict(s)
        if c.get("speaker"):
            c["speaker"] = names.get(c["speaker"]) or c["speaker"]
        out.append(c)
    return out


def regenerate_md(config: Settings, meeting_dir: Path, names: dict) -> None:
    """Reescreve a transcrição .md a partir do sidecar (rótulos originais) com o mapa.

    Idempotente: aplica o mapa sempre aos rótulos ORIGINAIS do sidecar; o sidecar
    nunca é alterado. Sem sidecar -> no-op.
    """
    side = _segments_sidecar(meeting_dir)
    if side is None:
        return
    try:
        raw = json.loads(side.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    segs = []
    for s in raw:
        orig = s.get("speaker")
        mapped = (names.get(orig) or orig) if orig else None
        words = [WordTime(**w) for w in s["words"]] if s.get("words") else None
        segs.append(
            TranscriptSegment(start=s["start"], end=s["end"], text=s["text"], speaker=mapped, words=words)
        )
    transcript = Transcript(
        segments=segs, full_text=" ".join(x.text for x in segs),
        language="pt", duration=(segs[-1].end if segs else 0.0),
    )
    from .note_generator import NoteGenerator
    ng = NoteGenerator(config)
    raw_path = ng.paths_for_existing(meeting_dir).raw_path
    ng._write_raw_transcription(transcript, raw_path)
    logger.info("Transcricao reescrita com nomes: %s", raw_path)
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_speaker_renaming.py -q`
Expected: PASS. Confirm `.venv/bin/python -c "import meeting_processor.speaker_names"`.

- [ ] **Step 5: Commit**

```bash
git add meeting_processor/speaker_names.py tests/test_speaker_renaming.py
git commit -m "feat(speakers): speaker_names module (map I/O, detect, apply, regenerate .md)"
```

---

### Task 3: `/speakers` endpoints + `/words` applies the map

**Files:** Modify `meeting_processor/web/app.py`; Test: `tests/test_speaker_renaming.py`.

- [ ] **Step 1: Append the failing tests:**

```python
# --- Task 3: endpoints -----------------------------------------------------


def _seed_meeting(config, folder, segs):
    d = config.reunioes_path / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / f"Transcricao - {folder}.md").write_text("# Transcricao\n\n**[00:00]** Falante 1: oi  \n", encoding="utf-8")
    (d / f"Transcricao - {folder}.words.json").write_text(json.dumps(segs), encoding="utf-8")
    return d


def test_get_speakers_detected_and_names(client, config):
    mid = "2026-01-01 10h00 - reu"
    _seed_meeting(config, mid, [
        {"start": 0, "end": 1, "text": "oi", "speaker": "Falante 1", "words": None},
        {"start": 1, "end": 2, "text": "ola", "speaker": "Falante 2", "words": None},
    ])
    r = client.get(f"/api/meetings/{mid}/speakers")
    assert r.status_code == 200
    assert r.json()["detected"] == ["Falante 1", "Falante 2"]
    assert r.json()["names"] == {}


def test_post_speakers_persists_and_rewrites_md(client, config):
    mid = "2026-01-02 10h00 - reu"
    d = _seed_meeting(config, mid, [
        {"start": 0, "end": 1, "text": "oi", "speaker": "Falante 1", "words": None},
    ])
    r = client.post(f"/api/meetings/{mid}/speakers", json={"names": {"Falante 1": "Ana"}})
    assert r.status_code == 200
    assert "Ana: oi" in (d / f"Transcricao - {mid}.md").read_text(encoding="utf-8")
    # the on-disk sidecar still has the ORIGINAL label
    side = json.loads((d / f"Transcricao - {mid}.words.json").read_text(encoding="utf-8"))
    assert side[0]["speaker"] == "Falante 1"
    # GET now reflects the saved name
    assert client.get(f"/api/meetings/{mid}/speakers").json()["names"] == {"Falante 1": "Ana"}


def test_words_endpoint_applies_names(client, config):
    mid = "2026-01-03 10h00 - reu"
    _seed_meeting(config, mid, [
        {"start": 0, "end": 1, "text": "oi", "speaker": "Falante 1", "words": None},
    ])
    client.post(f"/api/meetings/{mid}/speakers", json={"names": {"Falante 1": "Ana"}})
    served = client.get(f"/api/meetings/{mid}/words").json()
    assert served[0]["speaker"] == "Ana"
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_speaker_renaming.py -k "speakers or words_endpoint_applies" -q`
Expected: FAIL — `/speakers` route missing; `/words` returns the original label.

- [ ] **Step 3: Add the imports + endpoints.** In `meeting_processor/web/app.py`, add near the top imports:

```python
from .. import speaker_names
```

(use the import style matching the file — it's `from ..pipeline import ...` elsewhere, so `from .. import speaker_names` is correct.)

Add the two endpoints right after `api_meeting_words`:

```python
    @app.get("/api/meetings/{meeting_id}/speakers")
    async def api_get_speakers(meeting_id: str):
        meeting_dir = _reunioes_dir(config.vault_path, meeting_id)
        if meeting_dir is None or not meeting_dir.is_dir():
            raise HTTPException(status_code=404, detail="Reunião não encontrada")
        return {
            "detected": speaker_names.detected_labels(meeting_dir),
            "names": speaker_names.read_names(meeting_dir),
        }

    @app.post("/api/meetings/{meeting_id}/speakers")
    async def api_set_speakers(meeting_id: str, payload: dict):
        meeting_dir = _reunioes_dir(config.vault_path, meeting_id)
        if meeting_dir is None or not meeting_dir.is_dir():
            raise HTTPException(status_code=404, detail="Reunião não encontrada")
        names = (payload or {}).get("names") or {}
        speaker_names.write_names(meeting_dir, names)
        speaker_names.regenerate_md(config, meeting_dir, speaker_names.read_names(meeting_dir))
        return {"ok": True}
```

- [ ] **Step 4: `/words` applies the map.** In `api_meeting_words`, replace the final
`return json.loads(hits[0].read_text(encoding="utf-8"))` with:

```python
        segments = json.loads(hits[0].read_text(encoding="utf-8"))
        return speaker_names.apply_names(segments, speaker_names.read_names(meeting_dir))
```

- [ ] **Step 5: Run tests + full suite**

Run: `.venv/bin/python -m pytest tests/test_speaker_renaming.py -q` (all pass).
Run: `.venv/bin/python -m pytest -q` (all pass, 1 skipped). Confirm `.venv/bin/python -c "import meeting_processor.web.app"`.

- [ ] **Step 6: Commit**

```bash
git add meeting_processor/web/app.py tests/test_speaker_renaming.py
git commit -m "feat(web): /speakers GET+POST (rewrite .md) + /words applies the name map"
```

---

### Task 4: Frontend rename panel

**Files:** Modify `frontend/src/api/types.ts`, `frontend/src/hooks/useApi.ts`, `frontend/src/pages/MeetingDetail.tsx`; Create `frontend/src/components/SpeakerNames.tsx`, `frontend/src/__tests__/speakerNames.test.tsx`.

- [ ] **Step 1: Write the failing test** — create `frontend/src/__tests__/speakerNames.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SpeakerNames } from "../components/SpeakerNames";

function setup(detected: string[], names: Record<string, string>, fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const qc = new QueryClient();
  // seed the query cache so the panel renders immediately
  qc.setQueryData(["meeting-speakers", "m1"], { detected, names });
  return render(
    <QueryClientProvider client={qc}><SpeakerNames meetingId="m1" /></QueryClientProvider>,
  );
}

describe("SpeakerNames", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders a row per detected label and POSTs edited names", async () => {
    const f = vi.fn(async () => new Response(JSON.stringify({ ok: true }), { status: 200 }));
    setup(["Falante 1", "Falante 2"], { "Falante 1": "Ana" }, f);
    const inputs = screen.getAllByRole("textbox");
    expect(inputs).toHaveLength(2);
    expect((inputs[0] as HTMLInputElement).value).toBe("Ana");
    fireEvent.change(inputs[1], { target: { value: "Bruno" } });
    fireEvent.click(screen.getByRole("button", { name: /Salvar nomes/i }));
    await waitFor(() => {
      const call = f.mock.calls.find(([u, o]) =>
        String(u).endsWith("/api/meetings/m1/speakers") && (o as RequestInit)?.method === "POST");
      expect(call).toBeTruthy();
      expect(JSON.parse(String((call![1] as RequestInit).body)).names).toMatchObject(
        { "Falante 1": "Ana", "Falante 2": "Bruno" });
    });
  });

  it("renders nothing when no speakers detected", () => {
    const f = vi.fn();
    const { container } = setup([], {}, f);
    expect(container.textContent).toBe("");
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run (from `frontend/`): `npx vitest run src/__tests__/speakerNames.test.tsx`
Expected: FAIL — no `SpeakerNames` component.

- [ ] **Step 3: Type + hooks.**
  - `src/api/types.ts` — add:
    ```ts
    export interface SpeakerInfo { detected: string[]; names: Record<string, string>; }
    ```
  - `src/hooks/useApi.ts` — add (after `useMeetingWords`):
    ```ts
    export const useMeetingSpeakers = (id: string) =>
      useQuery({
        queryKey: ["meeting-speakers", id],
        queryFn: () => api.get<import("../api/types").SpeakerInfo>(`/api/meetings/${encodeURIComponent(id)}/speakers`),
      });

    export function useSetSpeakerNames(id: string) {
      const qc = useQueryClient();
      return useMutation({
        mutationFn: (names: Record<string, string>) =>
          api.post(`/api/meetings/${encodeURIComponent(id)}/speakers`, { names }),
        onSuccess: () => {
          qc.invalidateQueries({ queryKey: ["meeting", id] });
          qc.invalidateQueries({ queryKey: ["meeting-words", id] });
          qc.invalidateQueries({ queryKey: ["meeting-speakers", id] });
        },
      });
    }
    ```

- [ ] **Step 4: Create `src/components/SpeakerNames.tsx`:**

```tsx
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
```

- [ ] **Step 5: Wire `MeetingDetail.tsx`.** Add `import { SpeakerNames } from "../components/SpeakerNames";`,
and render it just above the player in the transcript tab:

```tsx
        {tab === "transcript" && (
          <>
            <SpeakerNames meetingId={id} />
            <TranscriptPlayer meetingId={id} markdown={d.transcricao_md}
              hasSource={source.data?.exists ?? false} words={words.data ?? null} />
          </>
        )}
```

- [ ] **Step 6: Test + typecheck + full suite**

Run (from `frontend/`): `npx vitest run src/__tests__/speakerNames.test.tsx` (2 pass);
`npx tsc --noEmit` (0); `npx vitest run` (all pass — existing MeetingDetail tests stub fetch; `useMeetingSpeakers` adds a `/speakers` request that their catch-all stub returns *something* for, and `SpeakerNames` renders null when `detected` is absent/empty → no impact; confirm they still pass, and if a stub returns a non-`{detected}` shape, `detected ?? []` guards it).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/hooks/useApi.ts frontend/src/components/SpeakerNames.tsx frontend/src/pages/MeetingDetail.tsx frontend/src/__tests__/speakerNames.test.tsx
git commit -m "feat(ui): speaker rename panel (edit Falante N -> real names)"
```

---

## Self-Review

**Spec coverage:** §1 broaden sidecar gate → Task 1. §2 `speaker_names` (names I/O, detected, apply, regenerate_md idempotent) → Task 2. §3 GET/POST `/speakers` + `/words` applies map; re-summary uses the rewritten `.md` (no code, automatic) → Task 3. §4 frontend hooks + panel + wiring → Task 4. Out-of-scope (voice ID, pre-feature meetings, new-summary labels) untouched. ✓

**Placeholder scan:** none — every step has concrete code/commands.

**Type consistency:** `speaker_names.{read_names,write_names,detected_labels,apply_names,regenerate_md}` (Task 2) called by the endpoints (Task 3). `regenerate_md(config, meeting_dir, names)` reuses `NoteGenerator.paths_for_existing(...).raw_path` + `_write_raw_transcription` (verified signatures). The sidecar glob `Transcricao - *.words.json` matches Task 1's writer + the `/words` endpoint. `SpeakerInfo {detected, names}` (Task 4 types) == the GET `/speakers` shape (Task 3). `useMeetingSpeakers`/`useSetSpeakerNames(id)` (Task 4) used by `SpeakerNames`. The POST body `{names}` matches `api_set_speakers`. `MeetingDetail` already imports `TranscriptPlayer` + `source`/`words`; the `<>` fragment adds `SpeakerNames` above it. Names consistent throughout. ✓
