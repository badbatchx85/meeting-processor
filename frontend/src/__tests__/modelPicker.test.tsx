import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { Settings } from "../pages/Settings";
import { ToastProvider } from "../components/Toast";

function setup() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ToastProvider>
          <Settings />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function stubFetch() {
  return vi.fn(async (url: string, opts?: RequestInit) => {
    if (opts?.method === "POST") {
      return new Response(JSON.stringify({ ok: true, llm: {} }), { status: 200 });
    }
    if (url.includes("/api/config")) {
      return new Response(
        JSON.stringify({ watch_dir: "", steps: { summary: true, note: true, kanban: true, wiki: true } }),
        { status: 200 },
      );
    }
    return new Response(
      JSON.stringify({
        provider: "gemini", label: "Gemini",
        anthropic_model: "claude-sonnet-4-20250514", openai_model: "gpt-4o",
        gemini_model: "gemini-2.0-flash", ollama_model: "qwen2.5:14b",
        anthropic_key_set: false,
        valid_providers: ["anthropic", "openai", "gemini", "local", "none"],
      }),
      { status: 200 },
    );
  });
}

describe("Settings — model picker", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("shows the current model and POSTs a chosen curated model", async () => {
    const fetchMock = stubFetch();
    vi.stubGlobal("fetch", fetchMock);
    setup();

    const select = (await screen.findByLabelText("Modelo")) as HTMLSelectElement;
    await waitFor(() => expect(select.value).toBe("gemini-2.0-flash"));
    expect(screen.getByRole("option", { name: "gemini-1.5-pro" })).toBeInTheDocument();

    fireEvent.change(select, { target: { value: "gemini-1.5-pro" } });
    fireEvent.click(screen.getByRole("button", { name: /Salvar modelo/i }));

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([url, opts]) => String(url).endsWith("/api/llm/model") && opts?.method === "POST",
      );
      expect(call).toBeTruthy();
      expect(JSON.parse(String(call![1]!.body))).toEqual({ provider: "gemini", model: "gemini-1.5-pro" });
    });
  });
});
