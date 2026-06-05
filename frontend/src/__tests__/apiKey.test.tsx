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

function stubFetch(provider: string) {
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
        provider, label: provider,
        anthropic_model: "claude-sonnet-4-20250514", openai_model: "gpt-4o",
        gemini_model: "gemini-2.0-flash", ollama_model: "qwen2.5:7b",
        anthropic_key_set: false, openai_key_set: false, gemini_key_set: false,
        valid_providers: ["anthropic", "openai", "gemini", "local", "none"],
      }),
      { status: 200 },
    );
  });
}

describe("Settings — API key entry", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("saves an API key for the active provider (write-only, masked)", async () => {
    const fetchMock = stubFetch("openai");
    vi.stubGlobal("fetch", fetchMock);
    setup();

    const input = (await screen.findByLabelText("Chave de API")) as HTMLInputElement;
    expect(input.type).toBe("password");                 // masked
    fireEvent.change(input, { target: { value: "sk-test" } });
    fireEvent.click(screen.getByRole("button", { name: /Salvar chave/i }));

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([url, opts]) => String(url).endsWith("/api/llm/key") && opts?.method === "POST",
      );
      expect(call).toBeTruthy();
      expect(JSON.parse(String(call![1]!.body))).toEqual({ provider: "openai", key: "sk-test" });
    });
  });

  it("lists qwen2.5:7b in the local model dropdown", async () => {
    vi.stubGlobal("fetch", stubFetch("local"));
    setup();
    await screen.findByLabelText("Modelo");
    expect(screen.getByRole("option", { name: "qwen2.5:7b" })).toBeInTheDocument();
  });
});
