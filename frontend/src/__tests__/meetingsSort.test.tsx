import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { Meetings } from "../pages/Meetings";
import { ToastProvider } from "../components/Toast";

const M = (over: Record<string, unknown>) => ({
  id: "x", title: "t", created: "", duration: "", task_count: 0,
  participants: "", source_file: "", meeting_type: "", purpose: "", has_summary: true, ...over,
});
const MEETINGS = [
  M({ id: "a", title: "Alpha", task_count: 1, purpose: "roadmap" }),
  M({ id: "b", title: "Bravo", task_count: 9, purpose: "orçamento" }),
  M({ id: "c", title: "Charlie", task_count: 3, purpose: "contratação" }),
];

function setup() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><ToastProvider><Meetings /></ToastProvider></MemoryRouter>
    </QueryClientProvider>,
  );
}

function rowTitles(): string[] {
  return screen.getAllByRole("link")
    .map((a) => a.textContent ?? "")
    .filter((t) => ["Alpha", "Bravo", "Charlie"].includes(t));
}

describe("Meetings sort + search", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      const body = String(url).includes("/api/history") ? [] : MEETINGS;
      return new Response(JSON.stringify(body), { status: 200 });
    }));
  });

  it("sorts by Tarefas on header click and toggles direction", async () => {
    setup();
    await screen.findByText("Alpha");
    fireEvent.click(screen.getByRole("button", { name: /Ordenar por Tarefas/i }));
    expect(rowTitles()).toEqual(["Bravo", "Charlie", "Alpha"]);
    fireEvent.click(screen.getByRole("button", { name: /Ordenar por Tarefas/i }));
    expect(rowTitles()).toEqual(["Alpha", "Charlie", "Bravo"]);
  });

  it("search matches purpose, not just title", async () => {
    setup();
    await screen.findByText("Bravo");
    fireEvent.change(screen.getByPlaceholderText("Buscar…"), { target: { value: "orçamento" } });
    expect(rowTitles()).toEqual(["Bravo"]);
  });
});
