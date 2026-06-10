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
      <MemoryRouter><ToastProvider><Settings /></ToastProvider></MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Settings — meeting context", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async (url: string, opts?: RequestInit) => {
      const u = String(url);
      if (opts?.method === "POST") return new Response(JSON.stringify({ ok: true }), { status: 200 });
      if (u.includes("/api/llm")) return new Response(JSON.stringify({ provider: "local" }), { status: 200 });
      if (u.includes("/api/config"))
        return new Response(JSON.stringify({
          watch_dir: "/x", steps: { summary: true, note: true, kanban: true, wiki: true },
          meeting_context: "Projeto X",
        }), { status: 200 });
      return new Response(JSON.stringify({}), { status: 200 });
    }));
  });

  it("renders the context textarea seeded from config and POSTs on save", async () => {
    const f = global.fetch as ReturnType<typeof vi.fn>;
    setup();
    const ta = await screen.findByRole("textbox", { name: /Contexto da reuni/i });
    expect((ta as HTMLTextAreaElement).value).toContain("Projeto X");
    fireEvent.change(ta, { target: { value: "Projeto Y | Ana" } });
    fireEvent.click(screen.getByRole("button", { name: /Salvar contexto/i }));
    await waitFor(() => {
      const call = f.mock.calls.find(([u, o]) =>
        String(u).endsWith("/api/config/meeting-context") && (o as RequestInit)?.method === "POST");
      expect(call).toBeTruthy();
      expect(JSON.parse(String((call![1] as RequestInit).body))).toMatchObject({ context: "Projeto Y | Ana" });
    });
  });
});
