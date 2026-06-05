import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { Meetings } from "../pages/Meetings";
import { ToastProvider } from "../components/Toast";

function setup() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ToastProvider>
          <Meetings />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Meetings list", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify([
      {
        id: "abc", title: "Reunião X", created: "2026-06-04", duration: "10m",
        task_count: 2, participants: "Ana", source_file: "x.mp4",
        meeting_type: "planejamento", purpose: "Alinhar o roadmap",
      },
    ]), { status: 200 })));
  });

  it("shows the meeting type badge and purpose subtitle", async () => {
    setup();
    expect(await screen.findByText("Reunião X")).toBeInTheDocument();
    expect(screen.getByText("planejamento")).toBeInTheDocument();
    expect(screen.getByText("Alinhar o roadmap")).toBeInTheDocument();
  });
});
