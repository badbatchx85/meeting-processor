# Click-to-Seek Transcript Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the web transcript tab's `[MM:SS]` markers clickable to seek an inline media player, served by a range-streaming endpoint.

**Architecture:** A `GET /api/meetings/{id}/media` endpoint returns `FileResponse(source)` (Starlette FileResponse is range-aware → 206 seeking for free). A `TranscriptPlayer` component parses the existing `**[MM:SS]**` lines client-side and renders a `<video>` + clickable seek buttons, falling back to the plain `MarkdownView` when the source is gone.

**Tech Stack:** FastAPI/Starlette, pytest + TestClient; React/Vite/TypeScript, Vitest.

Run Python tests with `.venv/bin/python -m pytest`; frontend from `frontend/` with `npx vitest run <file>` and `npx tsc --noEmit`. The pre-existing `test_summarizer_mock.py::test_factory_selects_anthropic` failure (no `ANTHROPIC_API_KEY`) is unrelated.

---

## File Structure
- **Modify** `meeting_processor/web/app.py` — add `FileResponse` import + `/api/meetings/{id}/media`.
- **Create** `frontend/src/components/TranscriptPlayer.tsx` — `parseTranscript` + the component.
- **Modify** `frontend/src/pages/MeetingDetail.tsx` — use it in the transcript tab.
- **Create** `tests/test_media_endpoint.py`, `frontend/src/__tests__/transcriptPlayer.test.tsx`.

---

### Task 1: Media-streaming endpoint

**Files:** Modify `meeting_processor/web/app.py`; Create `tests/test_media_endpoint.py`.

- [ ] **Step 1: Write the failing tests** — create `tests/test_media_endpoint.py`:

```python
"""Endpoint de mídia (range streaming) para o player de transcrição."""
from pathlib import Path


def _seed(config, meeting_id, stem, data=b"0123456789"):
    (config.reunioes_path / meeting_id).mkdir(parents=True, exist_ok=True)
    uploads = Path(config.project_root) / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    (uploads / f"{stem}.mp4").write_bytes(data)


def test_media_serves_source_bytes(client, config):
    mid = "2026-01-01 10h00 - reuniao"
    _seed(config, mid, "reuniao", b"VIDEOBYTES")
    r = client.get(f"/api/meetings/{mid}/media")
    assert r.status_code == 200
    assert r.content == b"VIDEOBYTES"


def test_media_supports_range(client, config):
    mid = "2026-01-02 10h00 - r2"
    _seed(config, mid, "r2", b"0123456789")
    r = client.get(f"/api/meetings/{mid}/media", headers={"Range": "bytes=0-3"})
    assert r.status_code == 206
    assert r.content == b"0123"
    assert r.headers.get("content-range") == "bytes 0-3/10"


def test_media_404_when_no_source(client, config):
    mid = "2026-01-03 10h00 - nope"
    (config.reunioes_path / mid).mkdir(parents=True, exist_ok=True)   # meeting exists, source doesn't
    r = client.get(f"/api/meetings/{mid}/media")
    assert r.status_code == 404
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_media_endpoint.py -q`
Expected: FAIL — the route doesn't exist (404 for all, so the 200/206 tests fail).

- [ ] **Step 3: Add the `FileResponse` import.** In `meeting_processor/web/app.py`, change the responses import line:

```python
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
```

to:

```python
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
```

- [ ] **Step 4: Add the endpoint.** In `meeting_processor/web/app.py`, immediately after the `api_meeting_source` handler (the `@app.get("/api/meetings/{meeting_id}/source")` block), add:

```python
    @app.get("/api/meetings/{meeting_id}/media")
    async def api_meeting_media(meeting_id: str):
        """Serve o arquivo de origem (vídeo/áudio) com suporte a Range.

        FileResponse do Starlette honra ``Range`` (206), então o player do
        navegador faz seek sem baixar o arquivo inteiro.
        """
        meeting_dir = _reunioes_dir(config.vault_path, meeting_id)
        if meeting_dir is None or not meeting_dir.is_dir():
            raise HTTPException(status_code=404, detail="Reunião não encontrada")
        from ..pipeline import locate_source_file

        src = locate_source_file(config, meeting_dir)
        if src is None or not src.is_file():
            raise HTTPException(status_code=404, detail="Arquivo de origem indisponível")
        return FileResponse(src)
```

- [ ] **Step 5: Run tests + regression**

Run: `.venv/bin/python -m pytest tests/test_media_endpoint.py -q`
Expected: PASS (3 tests). Then `.venv/bin/python -c "import meeting_processor.web.app"` imports cleanly.

- [ ] **Step 6: Commit**

```bash
git add meeting_processor/web/app.py tests/test_media_endpoint.py
git commit -m "feat(web): range-streaming media endpoint for the transcript player"
```

---

### Task 2: `TranscriptPlayer` component + wiring

**Files:** Create `frontend/src/components/TranscriptPlayer.tsx`; Modify `frontend/src/pages/MeetingDetail.tsx`; Create `frontend/src/__tests__/transcriptPlayer.test.tsx`.

- [ ] **Step 1: Write the failing tests** — create `frontend/src/__tests__/transcriptPlayer.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { TranscriptPlayer, parseTranscript } from "../components/TranscriptPlayer";

describe("parseTranscript", () => {
  it("parses MM:SS and HH:MM:SS lines and skips the rest", () => {
    const md = "# Transcricao\n\n**[00:05]** oi\n**[01:09]** tchau\n**[01:02:03]** fim";
    expect(parseTranscript(md)).toEqual([
      { seconds: 5, label: "00:05", text: "oi" },
      { seconds: 69, label: "01:09", text: "tchau" },
      { seconds: 3723, label: "01:02:03", text: "fim" },
    ]);
    expect(parseTranscript("sem timestamps aqui")).toEqual([]);
  });
});

describe("TranscriptPlayer", () => {
  beforeEach(() => {
    // jsdom doesn't implement media playback; back currentTime/play with stubs.
    let ct = 0;
    Object.defineProperty(HTMLMediaElement.prototype, "currentTime", {
      configurable: true, get: () => ct, set: (v) => { ct = v; },
    });
    Object.defineProperty(HTMLMediaElement.prototype, "play", {
      configurable: true, value: vi.fn(),
    });
  });

  it("renders a <video> + clickable timestamps and seeks on click", () => {
    const { container } = render(
      <TranscriptPlayer meetingId="m1" markdown={"**[00:05]** oi\n**[00:10]** tchau"} hasSource />,
    );
    const video = container.querySelector("video")!;
    expect(video).toBeTruthy();
    expect(video.getAttribute("src")).toContain("/api/meetings/m1/media");
    fireEvent.click(screen.getByRole("button", { name: /Ir para 00:10/ }));
    expect(video.currentTime).toBe(10);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalled();
  });

  it("falls back to the plain transcript when there is no source", () => {
    const { container } = render(
      <TranscriptPlayer meetingId="m1" markdown={"**[00:05]** oi"} hasSource={false} />,
    );
    expect(container.querySelector("video")).toBeNull();
    expect(screen.getByText(/oi/)).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run to verify they fail**

Run (from `frontend/`): `npx vitest run src/__tests__/transcriptPlayer.test.tsx`
Expected: FAIL — cannot resolve `../components/TranscriptPlayer`.

- [ ] **Step 3: Create `frontend/src/components/TranscriptPlayer.tsx`:**

```tsx
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
```

- [ ] **Step 4: Run the component tests**

Run (from `frontend/`): `npx vitest run src/__tests__/transcriptPlayer.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Wire `MeetingDetail.tsx`.**
  - Add the import after the `ActiveJob` import: `import { TranscriptPlayer } from "../components/TranscriptPlayer";`
  - Replace the transcript-tab line:
    ```tsx
        {tab === "transcript" && <MarkdownView>{d.transcricao_md}</MarkdownView>}
    ```
    with:
    ```tsx
        {tab === "transcript" && (
          <TranscriptPlayer meetingId={id} markdown={d.transcricao_md} hasSource={source.data?.exists ?? false} />
        )}
    ```
    (`source` is already `useMeetingSource(id)` in this component; `MarkdownView` stays imported — `TranscriptPlayer` uses it for the fallback, and the summary tab still uses it.)

- [ ] **Step 6: Typecheck + full frontend suite**

Run (from `frontend/`): `npx tsc --noEmit` (exit 0), then `npx vitest run` (all test files pass — including the existing `meetingDetail.test.tsx` and `meetingDetailStepper.test.tsx`, whose `/source` stub returns `{exists:true,...}` so the transcript tab now renders a `<video>`; confirm those still pass, and if a transcript assertion there breaks because the plain text moved into the player, it still renders the text via the segment rows — verify).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/TranscriptPlayer.tsx frontend/src/pages/MeetingDetail.tsx frontend/src/__tests__/transcriptPlayer.test.tsx
git commit -m "feat(ui): click-to-seek transcript player"
```

---

## Self-Review

**Spec coverage:**
- Range-streaming `/api/meetings/{id}/media` via `FileResponse` (validate dir, `locate_source_file`, 404 if absent) → Task 1. ✓
- `parseTranscript` (`MM:SS`/`HH:MM:SS`, skip non-timestamp lines) → Task 2 Step 3. ✓
- `TranscriptPlayer`: `<video controls preload="metadata">`, clickable seek buttons (`aria-label "Ir para {label}"`), active-segment highlight via `timeupdate`, fallback to `MarkdownView` when `!hasSource` or no segments → Task 2 Step 3. ✓
- Wire into `MeetingDetail` transcript tab with `hasSource={source.data?.exists}` → Task 2 Step 5. ✓
- Tests: media 200/206-range/404 (Task 1); `parseTranscript`, click-seeks, no-source fallback (Task 2). ✓
- Out of scope (word highlighting, Obsidian-side, custom scrubber, transcript-format change) → untouched. ✓

**Placeholder scan:** none — every step has concrete code/commands.

**Type consistency:** `FileResponse` imported (Task 1) used in the endpoint. `_reunioes_dir`/`locate_source_file` are existing helpers (matched to `api_meeting_source`). `parseTranscript(md) -> TranscriptSegment[]` and `TranscriptPlayer({meetingId, markdown, hasSource})` (Task 2 Step 3) used by the test (Step 1) and `MeetingDetail` (Step 5) with the same prop names/types. The media URL `/api/meetings/${encodeURIComponent(meetingId)}/media` matches the backend route. `source.data?.exists` is the existing `useMeetingSource` shape. Names consistent throughout. ✓
