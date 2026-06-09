import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ConversionHistory } from "../components/ConversionHistory";
import type { HistoryEntry } from "../api/types";

const entries: HistoryEntry[] = [
  {
    file: "ok.mp4", status: "completed",
    started: "2026-06-04T09:00:00", completed: "2026-06-04T09:05:00",
    failed_stage: null, error: null, detail: "3 tarefas, 2 participantes",
  },
  {
    file: "bad.mp4", status: "error",
    started: "2026-06-04T10:00:00", completed: "2026-06-04T10:40:00",
    failed_stage: "Gerando resumo com LLM", error: "Gemini 429 Too Many Requests",
    detail: "",
  },
];

describe("ConversionHistory", () => {
  it("renders completed and error rows with their reason", () => {
    render(<ConversionHistory entries={entries} />);
    expect(screen.getByText("ok.mp4")).toBeInTheDocument();
    expect(screen.getByText("3 tarefas, 2 participantes")).toBeInTheDocument();
    expect(screen.getByText("bad.mp4")).toBeInTheDocument();
    expect(screen.getByText(/Gerando resumo com LLM/)).toBeInTheDocument();
    expect(screen.getByText(/429/)).toBeInTheDocument();
  });

  it("limits the number of rows when limit is given", () => {
    render(<ConversionHistory entries={entries} limit={1} />);
    expect(screen.getByText("ok.mp4")).toBeInTheDocument();
    expect(screen.queryByText("bad.mp4")).not.toBeInTheDocument();
  });

  it("shows an empty state when there are no entries", () => {
    render(<ConversionHistory entries={[]} />);
    expect(screen.getByText(/Nenhuma convers/i)).toBeInTheDocument();
  });

  it("does not crash when given a non-array (unexpected API shape)", () => {
    // @ts-expect-error — simula uma resposta inesperada da API
    render(<ConversionHistory entries={{}} />);
    expect(screen.getByText(/Nenhuma convers/i)).toBeInTheDocument();
  });
});
