import { describe, it, expect } from "vitest";
import { talkTime } from "../lib/talkTime";

const seg = (speaker: string | null, start: number, end: number) =>
  ({ start, end, text: "", speaker, words: null });

describe("talkTime util", () => {
  it("agrega duração por falante, % e ordena desc", () => {
    const rows = talkTime([seg("João", 60, 90), seg("Ana", 0, 60)]);
    expect(rows).toEqual([
      { speaker: "Ana", seconds: 60, pct: (60 / 90) * 100 },
      { speaker: "João", seconds: 30, pct: (30 / 90) * 100 },
    ]);
  });

  it("ignora segmentos sem falante", () => {
    const rows = talkTime([seg("Ana", 0, 60), seg(null, 60, 120), seg("João", 120, 150)]);
    expect(rows.map((r) => r.speaker)).toEqual(["Ana", "João"]);
    expect(rows.find((r) => r.speaker === "Ana")!.seconds).toBe(60);
  });

  it("devolve [] com menos de 2 falantes", () => {
    expect(talkTime([seg("Ana", 0, 60)])).toEqual([]);
  });

  it("devolve [] para vazio ou null", () => {
    expect(talkTime([])).toEqual([]);
    expect(talkTime(null)).toEqual([]);
  });

  it("não divide por zero quando todas as durações são 0", () => {
    const rows = talkTime([seg("Ana", 0, 0), seg("João", 0, 0)]);
    expect(rows.every((r) => r.pct === 0)).toBe(true);
  });
});
