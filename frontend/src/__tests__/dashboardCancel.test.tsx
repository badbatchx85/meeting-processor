import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { Dashboard } from "../pages/Dashboard";
import { ToastProvider } from "../components/Toast";

function setup() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ToastProvider><Dashboard /></ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const ACTIVE_JOB = {
  file: "reuniao.mp4",
  started: "2026-06-08T12:00:00",
  status: "processing",
  stage_number: 1,
  stage_total: 6,
  stage_label: "Extraindo áudio",
  stage_percent: 10,
  percent: 5,
  detail: "",
  stages: [],
};

describe("Dashboard — clear stuck job", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("shows a Limpar button on an active job and POSTs the cancel with file + started", async () => {
    const f = vi.fn(async (url: string, opts?: RequestInit) => {
      if (opts?.method === "POST")
        return new Response(JSON.stringify({ ok: true }), { status: 200 });
      if (url.includes("/api/status"))
        return new Response(JSON.stringify({ watcher_alive: false, active: [ACTIVE_JOB] }), { status: 200 });
      return new Response(JSON.stringify({}), { status: 200 });
    });
    vi.stubGlobal("fetch", f);
    setup();

    const btn = await screen.findByRole("button", { name: /Limpar/i });
    fireEvent.click(btn);

    await waitFor(() => {
      const call = f.mock.calls.find(([u, o]) =>
        String(u).endsWith("/api/process/cancel") && o?.method === "POST");
      expect(call).toBeTruthy();
      expect(JSON.parse(String(call![1]!.body))).toMatchObject({
        file: "reuniao.mp4",
        started: "2026-06-08T12:00:00",
      });
    });
  });
});
