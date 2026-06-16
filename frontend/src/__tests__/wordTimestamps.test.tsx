import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { TranscriptPlayer } from "../components/TranscriptPlayer";

const WORDS = [
  { start: 0, end: 1, text: "oi", speaker: null, words: [
    { start: 0, end: 0.5, text: "oi" }, { start: 0.5, end: 1, text: "mundo" },
  ] },
];

describe("TranscriptPlayer word-level", () => {
  beforeEach(() => {
    let ct = 0;
    Object.defineProperty(HTMLMediaElement.prototype, "currentTime", {
      configurable: true, get: () => ct, set: (v) => { ct = v; },
    });
    Object.defineProperty(HTMLMediaElement.prototype, "play", { configurable: true, value: vi.fn() });
  });

  it("renders word spans and seeks to a word on click", () => {
    const { container } = render(
      <TranscriptPlayer meetingId="m1" markdown={"**[00:00]** oi mundo"} hasSource words={WORDS} />,
    );
    const video = container.querySelector("video")!;
    fireEvent.click(screen.getByRole("button", { name: /Ir para palavra: mundo/i }));
    expect(video.currentTime).toBe(0.5);
  });

  it("falls back to segment-level when words is null", () => {
    const { container } = render(
      <TranscriptPlayer meetingId="m1" markdown={"**[00:05]** oi"} hasSource words={null} />,
    );
    expect(container.querySelector("video")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Ir para 00:05/i })).toBeTruthy();
  });
});
