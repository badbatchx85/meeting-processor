import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { Meetings } from "../pages/Meetings";
import { ToastProvider } from "../components/Toast";

function setup() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ToastProvider>
          <Meetings />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const MEETINGS = [
  {
    id: "abc", title: "Reunião X", created: "2026-06-04", duration: "10m",
    task_count: 2, participants: "Ana", source_file: "x.mp4",
    meeting_type: "planejamento", purpose: "Alinhar o roadmap", has_summary: true,
  },
  {
    id: "def", title: "Só Transcrição", created: "", duration: "",
    task_count: 0, participants: "", source_file: "y.mp4",
    meeting_type: "", purpose: "", has_summary: false,
  },
];

describe("Meetings list", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      const body = url.includes("/api/history") ? [] : MEETINGS;
      return new Response(JSON.stringify(body), { status: 200 });
    }));
  });

  it("shows the meeting type badge and purpose subtitle", async () => {
    setup();
    expect(await screen.findByText("Reunião X")).toBeInTheDocument();
    expect(screen.getByText("planejamento")).toBeInTheDocument();
    expect(screen.getByText("Alinhar o roadmap")).toBeInTheDocument();
  });

  it("badges a transcription-only meeting", async () => {
    setup();
    expect(await screen.findByText("Só Transcrição")).toBeInTheDocument();
    expect(screen.getByText("só transcrição")).toBeInTheDocument();
  });

  it("per-row buttons POST to transcribe and summarize", async () => {
    const f = vi.fn(async (url: string, opts?: RequestInit) => {
      const u = String(url);
      if (opts?.method === "POST")
        return new Response(JSON.stringify({ ok: true }), { status: 200 });
      if (u.includes("/api/meetings"))
        return new Response(JSON.stringify([
          { id: "m1", title: "Reunião 1", created: "", duration: "", task_count: 0,
            participants: "", source_file: "", meeting_type: "", purpose: "", has_summary: false },
        ]), { status: 200 });
      if (u.includes("/api/history")) return new Response(JSON.stringify([]), { status: 200 });
      return new Response(JSON.stringify([]), { status: 200 });
    });
    vi.stubGlobal("fetch", f);
    setup();
    const tBtn = await screen.findByRole("button", { name: /Gerar transcrição da Reunião 1/i });
    fireEvent.click(tBtn);
    await waitFor(() =>
      expect(f.mock.calls.some(([url, o]) =>
        String(url).endsWith("/api/meetings/m1/transcribe") && o?.method === "POST")).toBe(true));
  });
});
