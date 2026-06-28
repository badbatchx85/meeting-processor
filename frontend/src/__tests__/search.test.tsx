import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { Search } from "../pages/Search";

function setup() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Search />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function mockSearch(results: unknown[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify({ results }), { status: 200 })),
  );
}

describe("Search page", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders matching snippets linking to the meeting at its timestamp", async () => {
    mockSearch([
      { meeting_id: "2026-06-01 reu", text: "falamos do roadmap", start: 12.5, end: 18.0, score: 0.91 },
    ]);
    setup();
    fireEvent.change(screen.getByPlaceholderText(/buscar/i), { target: { value: "roadmap" } });
    fireEvent.submit(screen.getByRole("search"));

    expect(await screen.findByText(/falamos do roadmap/)).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /2026-06-01 reu/ }) as HTMLAnchorElement;
    expect(link.getAttribute("href")).toContain("/meetings/");
    expect(link.getAttribute("href")).toContain("t=12");
  });

  it("shows an empty-state message when nothing matches", async () => {
    mockSearch([]);
    setup();
    fireEvent.change(screen.getByPlaceholderText(/buscar/i), { target: { value: "xyz" } });
    fireEvent.submit(screen.getByRole("search"));
    await waitFor(() =>
      expect(screen.getByText(/nada encontrado/i)).toBeInTheDocument(),
    );
  });
});
