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
          <Routes>
            <Route path="/meetings/:id" element={<MeetingDetail />} />
          </Routes>
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function stubFetch(resumo_md: string) {
  return vi.fn(async (_url: string, opts?: RequestInit) => {
    if (opts?.method === "POST") {
      return new Response(JSON.stringify({ ok: true, queued: true, meeting_id: "abc" }), { status: 200 });
    }
    return new Response(
      JSON.stringify({ id: "abc", title: "abc", meta: {}, resumo_md, tasks: [], transcricao_md: "linha" }),
      { status: 200 },
    );
  });
}

describe("MeetingDetail — generate summary", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("shows 'Gerar resumo' with no summary and POSTs to the summarize endpoint", async () => {
    const fetchMock = stubFetch("");
    vi.stubGlobal("fetch", fetchMock);
    setup();

    const btn = await screen.findByRole("button", { name: /Gerar resumo/i });
    fireEvent.click(btn);

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([url, opts]) =>
            String(url).endsWith("/api/meetings/abc/summarize") && opts?.method === "POST",
        ),
      ).toBe(true),
    );
  });

  it("hides the button when a summary already exists", async () => {
    vi.stubGlobal("fetch", stubFetch("# Resumo aqui"));
    setup();
    expect(await screen.findByText("Resumo aqui")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Gerar resumo/i })).not.toBeInTheDocument();
  });
});
