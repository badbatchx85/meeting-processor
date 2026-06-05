import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
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

describe("Settings", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.includes("/api/config")) {
          return new Response(
            JSON.stringify({
              watch_dir: "/home/me/OBS",
              steps: { summary: true, note: false, kanban: true, wiki: false },
            }),
            { status: 200 },
          );
        }
        // /api/llm
        return new Response(
          JSON.stringify({
            provider: "gemini",
            label: "Gemini",
            valid_providers: ["anthropic", "gemini", "none"],
          }),
          { status: 200 },
        );
      }),
    );
  });

  it("reflects the backend's current steps and watch dir", async () => {
    setup();
    const watchInput = (await screen.findByPlaceholderText(
      /OBS/i,
    )) as HTMLInputElement;
    await waitFor(() => expect(watchInput.value).toBe("/home/me/OBS"));

    const summary = screen.getByLabelText("Resumo (IA)") as HTMLInputElement;
    const note = screen.getByLabelText("Nota Obsidian") as HTMLInputElement;
    const wiki = screen.getByLabelText("Wiki") as HTMLInputElement;
    expect(summary.checked).toBe(true);
    expect(note.checked).toBe(false);
    expect(wiki.checked).toBe(false);
  });
});
