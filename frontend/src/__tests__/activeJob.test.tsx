import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ActiveJob } from "../components/ActiveJob";
import { ToastProvider } from "../components/Toast";
import type { JobProgress } from "../api/types";

const JOB: JobProgress = {
  file: "reuniao.mp4", started: "2026-06-09T12:00:00", status: "processing",
  stage_number: 1, stage_total: 6, stage_label: "Extraindo áudio",
  stage_percent: 10, percent: 5, detail: "", stages: [],
};

function setup(job: JobProgress) {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider><ActiveJob job={job} /></ToastProvider>
    </QueryClientProvider>,
  );
}

describe("ActiveJob", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders the stepper (file + percent) and a Limpar button", () => {
    setup(JOB);
    expect(screen.getByText("reuniao.mp4")).toBeInTheDocument();
    expect(screen.getByText("5%")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Limpar/i })).toBeInTheDocument();
  });

  it("POSTs cancel with file + started when Limpar is clicked", async () => {
    const f = vi.fn<typeof fetch>(async () => new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", f);
    setup(JOB);
    fireEvent.click(screen.getByRole("button", { name: /Limpar/i }));
    await waitFor(() => {
      const call = f.mock.calls.find(([u, o]) =>
        String(u).endsWith("/api/process/cancel") && (o as RequestInit)?.method === "POST");
      expect(call).toBeTruthy();
      expect(JSON.parse(String((call![1] as RequestInit).body))).toMatchObject({
        file: "reuniao.mp4", started: "2026-06-09T12:00:00",
      });
    });
  });
});
