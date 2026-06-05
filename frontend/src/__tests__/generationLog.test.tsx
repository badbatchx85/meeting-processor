import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { MeetingDetail } from "../pages/MeetingDetail";
import { ToastProvider } from "../components/Toast";

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

function stub({ exists = true, log = [] as unknown[] } = {}) {
  return vi.fn(async (url: string, opts?: RequestInit) => {
    const u = String(url);
    if (opts?.method === "POST" || opts?.method === "DELETE") {
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    }
    if (u.includes("/source"))
      return new Response(JSON.stringify({ exists, name: "reuniao.mp4", path: "/u/reuniao.mp4", size: 1048576 }), { status: 200 });
    if (u.includes("/log"))
      return new Response(JSON.stringify(log), { status: 200 });
    return new Response(JSON.stringify({ id: "abc", title: "abc", meta: {}, resumo_md: "# Resumo", tasks: [], transcricao_md: "linha" }), { status: 200 });
  });
}

describe("MeetingDetail — generation actions", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("POSTs to transcribe when 'Gerar transcrição' is clicked", async () => {
    const f = stub();
    vi.stubGlobal("fetch", f);
    setup();
    fireEvent.click(await screen.findByRole("button", { name: /Gerar transcrição/i }));
    await waitFor(() =>
      expect(f.mock.calls.some(([url, o]) =>
        String(url).endsWith("/api/meetings/abc/transcribe") && o?.method === "POST")).toBe(true));
  });

  it("disables 'Gerar transcrição' when the source is gone", async () => {
    vi.stubGlobal("fetch", stub({ exists: false }));
    setup();
    await screen.findByRole("button", { name: /^Resumo$/ });
    const btn = await screen.findByRole("button", { name: /Gerar transcrição/i });
    expect(btn).toBeDisabled();
    expect(screen.getByText(/indisponível/i)).toBeInTheDocument();
  });

  it("renders log entries (ok detail + error reason)", async () => {
    vi.stubGlobal("fetch", stub({ log: [
      { action: "transcript", status: "error", error: "Arquivo de origem não encontrado: x", detail: "", started: "2026-06-05T10:00:00", completed: "2026-06-05T10:00:01" },
      { action: "summary", status: "ok", error: null, detail: "12 tarefas", started: "2026-06-05T09:00:00", completed: "2026-06-05T09:01:00" },
    ] }));
    setup();
    expect(await screen.findByText(/Arquivo de origem não encontrado: x/)).toBeInTheDocument();
    expect(screen.getByText(/12 tarefas/)).toBeInTheDocument();
  });
});
