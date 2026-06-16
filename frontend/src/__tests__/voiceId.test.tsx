import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SpeakerNames } from "../components/SpeakerNames";

function setup(data: { detected: string[]; names: Record<string,string>; suggestions: Record<string,string> }) {
  vi.stubGlobal("fetch", vi.fn());
  const qc = new QueryClient();
  qc.setQueryData(["meeting-speakers", "m1"], data);
  return render(<QueryClientProvider client={qc}><SpeakerNames meetingId="m1" /></QueryClientProvider>);
}

describe("SpeakerNames suggestions", () => {
  it("pre-fills a suggested name and shows the reconhecido badge", () => {
    setup({ detected: ["Falante 1", "Falante 2"], names: {}, suggestions: { "Falante 1": "Ana" } });
    const inputs = screen.getAllByRole("textbox") as HTMLInputElement[];
    expect(inputs[0].value).toBe("Ana");
    expect(inputs[1].value).toBe("");
    expect(screen.getByText(/reconhecido/i)).toBeTruthy();
  });

  it("confirmed names override suggestions (no badge)", () => {
    setup({ detected: ["Falante 1"], names: { "Falante 1": "Carlos" }, suggestions: { "Falante 1": "Ana" } });
    expect((screen.getByRole("textbox") as HTMLInputElement).value).toBe("Carlos");
    expect(screen.queryByText(/reconhecido/i)).toBeNull();
  });
});
