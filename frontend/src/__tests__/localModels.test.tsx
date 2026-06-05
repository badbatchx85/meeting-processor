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

function stub(
  local: { ollama_running: boolean; installed: string[]; suggested: string[] },
  pullStatus: Record<string, unknown> = {},
) {
  return vi.fn(async (url: string, opts?: RequestInit) => {
    if (opts?.method === "POST") return new Response(JSON.stringify({ ok: true, queued: true, model: "x" }), { status: 200 });
    if (url.includes("/api/llm/local-models/pull/status")) return new Response(JSON.stringify(pullStatus), { status: 200 });
    if (url.includes("/api/llm/local-models")) return new Response(JSON.stringify(local), { status: 200 });
    if (url.includes("/api/config")) return new Response(JSON.stringify({ watch_dir: "", steps: { summary: true, note: true, kanban: true, wiki: true } }), { status: 200 });
    return new Response(JSON.stringify({
      provider: "local", label: "local",
      anthropic_model: "", openai_model: "", gemini_model: "", ollama_model: "qwen2.5:7b",
      anthropic_key_set: false, openai_key_set: false, gemini_key_set: false,
      valid_providers: ["anthropic", "openai", "gemini", "local", "none"],
    }), { status: 200 });
  });
}

describe("Settings — local Ollama models", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("lists installed models in the dropdown", async () => {
    vi.stubGlobal("fetch", stub({ ollama_running: true, installed: ["qwen2.5:7b", "llama3.1:8b"], suggested: [] }));
    setup();
    await screen.findByLabelText("Modelo");
    expect(screen.getByRole("option", { name: "llama3.1:8b" })).toBeInTheDocument();
  });

  it("offers a Baixar button when none installed and POSTs the pull", async () => {
    const fetchMock = stub({ ollama_running: true, installed: [], suggested: ["qwen2.5:7b", "llama3.1:8b"] });
    vi.stubGlobal("fetch", fetchMock);
    setup();
    const btn = await screen.findByRole("button", { name: "Baixar qwen2.5:7b" });
    fireEvent.click(btn);
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([u, o]) => String(u).endsWith("/api/llm/local-models/pull") && o?.method === "POST");
      expect(call).toBeTruthy();
      expect(JSON.parse(String(call![1]!.body))).toEqual({ model: "qwen2.5:7b" });
    });
  });

  it("shows a % bar while a local model is downloading", async () => {
    vi.stubGlobal("fetch", stub(
      { ollama_running: true, installed: [], suggested: ["qwen2.5:7b"] },
      { model: "qwen2.5:7b", percent: 42, status: "downloading", done: false },
    ));
    setup();
    expect(await screen.findByText(/42%/)).toBeInTheDocument();
  });

  it("shows a notice when Ollama is not running", async () => {
    vi.stubGlobal("fetch", stub({ ollama_running: false, installed: [], suggested: ["qwen2.5:7b"] }));
    setup();
    expect(await screen.findByText(/não está rodando/i)).toBeInTheDocument();
  });
});
