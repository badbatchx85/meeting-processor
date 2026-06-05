import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { MeetingDetail } from "../pages/MeetingDetail";

function setup() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/meetings/abc"]}>
        <Routes><Route path="/meetings/:id" element={<MeetingDetail />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("MeetingDetail", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      id: "abc", title: "abc",
      meta: { purpose: "Alinhar o roadmap", meeting_type: "planejamento" },
      resumo_md: "# Resumo aqui",
      tasks: [{ done: false, description: "Tarefa 1" }],
      transcricao_md: "linha de transcrição",
    }), { status: 200 })));
  });

  it("shows summary by default and switches to transcript tab", async () => {
    setup();
    expect(await screen.findByText("Resumo aqui")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^Transcrição$/ }));
    expect(await screen.findByText(/linha de transcrição/)).toBeInTheDocument();
  });

  it("renders purpose, a type badge, and export links", async () => {
    setup();
    expect(await screen.findByText("Alinhar o roadmap")).toBeInTheDocument();
    expect(screen.getByText("planejamento")).toBeInTheDocument();
    const md = screen.getByRole("link", { name: /Markdown/i });
    const docx = screen.getByRole("link", { name: /Word/i });
    expect(md).toHaveAttribute("href", "/api/meetings/abc/export.md");
    expect(docx).toHaveAttribute("href", "/api/meetings/abc/export.docx");
  });
});
