import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { MeetingDetail } from "../pages/MeetingDetail";
import { ToastProvider } from "../components/Toast";

const MEETING = {
  id: "abc", title: "abc",
  meta: { purpose: "", meeting_type: "" },
  resumo_md: "", tasks: [], transcricao_md: "linha",
};
const JOB = {
  file: "abc", started: "2026-06-09T12:00:00", status: "processing",
  stage_number: 3, stage_total: 6, stage_label: "Gerando resumo com LLM",
  stage_percent: 10, percent: 35, detail: "", stages: [],
};

function stub(active: unknown[]) {
  return vi.fn(async (url: string) => {
    const u = String(url);
    if (u.includes("/api/status"))
      return new Response(JSON.stringify({ watcher_alive: false, active }), { status: 200 });
    if (u.includes("/source"))
      return new Response(JSON.stringify({ exists: true, name: "x.mp4", path: "/x.mp4", size: 1 }), { status: 200 });
    if (u.includes("/log")) return new Response(JSON.stringify([]), { status: 200 });
    return new Response(JSON.stringify(MEETING), { status: 200 });
  });
}

function setup() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/meetings/abc"]}>
        <ToastProvider>
          <Routes><Route path="/meetings/:id" element={<MeetingDetail />} /></Routes>
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("MeetingDetail — live stepper", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("shows the stepper card and disables the generate buttons when a matching job is active", async () => {
    vi.stubGlobal("fetch", stub([JOB]));
    setup();
    expect(await screen.findByText("Em processamento")).toBeInTheDocument();
    expect(await screen.findByText("35%")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Gerar resumo/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Gerar transcrição/i })).toBeDisabled();
  });

  it("shows no stepper card and leaves buttons enabled when no job matches this meeting", async () => {
    vi.stubGlobal("fetch", stub([{ ...JOB, file: "outro.mp4" }]));
    setup();
    expect(await screen.findByRole("button", { name: /Gerar resumo/i })).toBeEnabled();
    expect(screen.queryByText("Em processamento")).not.toBeInTheDocument();
  });
});
