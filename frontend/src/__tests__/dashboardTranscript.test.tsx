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

describe("Dashboard — transcript-only", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("sends mode=transcript when 'Apenas transcrição' is checked", async () => {
    const f = vi.fn(async (_url: string, opts?: RequestInit) => {
      if (opts?.method === "POST")
        return new Response(JSON.stringify({ ok: true, queued: true }), { status: 200 });
      return new Response(JSON.stringify({}), { status: 200 });
    });
    vi.stubGlobal("fetch", f);
    setup();

    fireEvent.click(screen.getByLabelText(/Apenas transcrição/i));
    const input = screen.getByPlaceholderText(/reuniao\.mp4/i);
    fireEvent.change(input, { target: { value: "/v/x.mp4" } });
    fireEvent.click(screen.getByRole("button", { name: /Processar caminho/i }));

    await waitFor(() => {
      const call = f.mock.calls.find(([u, o]) =>
        String(u).endsWith("/api/process") && o?.method === "POST");
      expect(call).toBeTruthy();
      expect(JSON.parse(String(call![1]!.body))).toMatchObject({ file: "/v/x.mp4", mode: "transcript" });
    });
  });
});
