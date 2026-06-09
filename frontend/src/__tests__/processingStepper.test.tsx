import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ProcessingStepper } from "../components/ProcessingStepper";
import type { JobProgress } from "../api/types";

const job: JobProgress = {
  file: "reuniao.mp4",
  started: "2026-06-08T12:00:00",
  status: "processing",
  stage_number: 2,
  stage_total: 6,
  stage_label: "Transcrevendo com Whisper",
  stage_percent: 50,
  percent: 25,
  detail: "120 segmentos",
  stages: [
    { key: "audio", label: "Extraindo audio", state: "done", percent: 100, detail: "" },
    { key: "transcription", label: "Transcrevendo com Whisper", state: "active", percent: 50, detail: "120 segmentos" },
    { key: "summary", label: "Gerando resumo com LLM", state: "pending", percent: 0, detail: "" },
    { key: "kanban", label: "Criando quadro Kanban", state: "skipped", percent: 0, detail: "" },
  ],
};

describe("ProcessingStepper", () => {
  it("renders the file, overall percent, and a row per phase with states", () => {
    render(<ProcessingStepper job={job} />);
    expect(screen.getByText("reuniao.mp4")).toBeInTheDocument();
    expect(screen.getByText("25%")).toBeInTheDocument();           // overall

    // every phase label renders
    expect(screen.getByText("Extraindo audio")).toBeInTheDocument();        // done
    expect(screen.getByText("Transcrevendo com Whisper")).toBeInTheDocument(); // active
    expect(screen.getByText("Gerando resumo com LLM")).toBeInTheDocument();  // pending
    expect(screen.getByText(/Criando quadro Kanban/)).toBeInTheDocument();   // skipped (+ "(desativada)")

    // active phase shows its sub-percent + detail
    expect(screen.getByText(/50%/)).toBeInTheDocument();
    expect(screen.getByText(/120 segmentos/)).toBeInTheDocument();
  });
});
