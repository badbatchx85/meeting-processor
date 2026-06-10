import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { TranscriptPlayer, parseTranscript } from "../components/TranscriptPlayer";

describe("parseTranscript", () => {
  it("parses MM:SS and HH:MM:SS lines and skips the rest", () => {
    const md = "# Transcricao\n\n**[00:05]** oi\n**[01:09]** tchau\n**[01:02:03]** fim";
    expect(parseTranscript(md)).toEqual([
      { seconds: 5, label: "00:05", text: "oi" },
      { seconds: 69, label: "01:09", text: "tchau" },
      { seconds: 3723, label: "01:02:03", text: "fim" },
    ]);
    expect(parseTranscript("sem timestamps aqui")).toEqual([]);
  });
});

describe("TranscriptPlayer", () => {
  beforeEach(() => {
    let ct = 0;
    Object.defineProperty(HTMLMediaElement.prototype, "currentTime", {
      configurable: true, get: () => ct, set: (v) => { ct = v; },
    });
    Object.defineProperty(HTMLMediaElement.prototype, "play", {
      configurable: true, value: vi.fn(),
    });
  });

  it("renders a <video> + clickable timestamps and seeks on click", () => {
    const { container } = render(
      <TranscriptPlayer meetingId="m1" markdown={"**[00:05]** oi\n**[00:10]** tchau"} hasSource />,
    );
    const video = container.querySelector("video")!;
    expect(video).toBeTruthy();
    expect(video.getAttribute("src")).toContain("/api/meetings/m1/media");
    fireEvent.click(screen.getByRole("button", { name: /Ir para 00:10/ }));
    expect(video.currentTime).toBe(10);
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalled();
  });

  it("falls back to the plain transcript when there is no source", () => {
    const { container } = render(
      <TranscriptPlayer meetingId="m1" markdown={"**[00:05]** oi"} hasSource={false} />,
    );
    expect(container.querySelector("video")).toBeNull();
    expect(screen.getByText(/oi/)).toBeTruthy();
  });
});
