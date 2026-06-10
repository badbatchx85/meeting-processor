import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { MeetingDetail } from "../pages/MeetingDetail";
import { ToastProvider } from "../components/Toast";

const MEETING = {
  id: "abc", title: "abc", meta: { purpose: "", meeting_type: "" },
  resumo_md: "", tasks: [], transcricao_md: "",
};

function stub() {
  return vi.fn(async (url: string, opts?: RequestInit) => {
    const u = String(url);
    if (opts?.method === "POST") return new Response(JSON.stringify({ ok: true, queued: true }), { status: 200 });
    if (u.includes("/api/status")) return new Response(JSON.stringify({ watcher_alive: false, active: [] }), { status: 200 });
    if (u.includes("/source")) return new Response(JSON.stringify({ exists: false, name: "", path: "", size: null }), { status: 200 });
    if (u.includes("/log")) return new Response(JSON.stringify([]), { status: 200 });
    if (u.endsWith("/api/config")) return new Response(JSON.stringify({ watch_dir: "/x", steps: { summary: true, note: true, kanban: true, wiki: true }, meeting_context: "", summary_style: "timeline" }), { status: 200 });
    return new Response(JSON.stringify(MEETING), { status: 200 });
  });
}

function setup() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/meetings/abc"]}>
        <ToastProvider><Routes><Route path="/meetings/:id" element={<MeetingDetail />} /></Routes></ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("MeetingDetail — summary style", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("Gerar resumo POSTs the selected style", async () => {
    const f = stub();
    vi.stubGlobal("fetch", f);
    setup();
    const sel = await screen.findByRole("combobox", { name: /Estilo do resumo/i });
    fireEvent.change(sel, { target: { value: "plain" } });
    fireEvent.click(screen.getByRole("button", { name: /Gerar resumo/i }));
    await waitFor(() => {
      const call = f.mock.calls.find(([u, o]) =>
        String(u).endsWith("/api/meetings/abc/summarize") && (o as RequestInit)?.method === "POST");
      expect(call).toBeTruthy();
      expect(JSON.parse(String((call![1] as RequestInit).body))).toMatchObject({ style: "plain" });
    });
  });
});
