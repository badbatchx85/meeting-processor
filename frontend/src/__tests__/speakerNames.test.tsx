import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SpeakerNames } from "../components/SpeakerNames";

function setup(detected: string[], names: Record<string, string>, fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  const qc = new QueryClient();
  qc.setQueryData(["meeting-speakers", "m1"], { detected, names });
  return render(
    <QueryClientProvider client={qc}><SpeakerNames meetingId="m1" /></QueryClientProvider>,
  );
}

describe("SpeakerNames", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders a row per detected label and POSTs edited names", async () => {
    const f = vi.fn(async () => new Response(JSON.stringify({ ok: true }), { status: 200 }));
    setup(["Falante 1", "Falante 2"], { "Falante 1": "Ana" }, f);
    const inputs = screen.getAllByRole("textbox");
    expect(inputs).toHaveLength(2);
    expect((inputs[0] as HTMLInputElement).value).toBe("Ana");
    fireEvent.change(inputs[1], { target: { value: "Bruno" } });
    fireEvent.click(screen.getByRole("button", { name: /Salvar nomes/i }));
    await waitFor(() => {
      const call = (f.mock.calls as unknown as [string, RequestInit][]).find(([u, o]) =>
        String(u).endsWith("/api/meetings/m1/speakers") && o?.method === "POST");
      expect(call).toBeTruthy();
      expect(JSON.parse(String(call![1].body)).names).toMatchObject(
        { "Falante 1": "Ana", "Falante 2": "Bruno" });
    });
  });

  it("renders nothing when no speakers detected", () => {
    const f = vi.fn();
    const { container } = setup([], {}, f);
    expect(container.textContent).toBe("");
  });
});
