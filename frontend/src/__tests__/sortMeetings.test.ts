import { describe, it, expect } from "vitest";
import { sortMeetings } from "../lib/sortMeetings";
import type { MeetingSummary } from "../api/types";

const M = (over: Partial<MeetingSummary>): MeetingSummary => ({
  id: "x", title: "t", created: "", duration: "", task_count: 0,
  participants: "", source_file: "", meeting_type: "", purpose: "", has_summary: false,
  ...over,
});

const items = [
  M({ id: "a", title: "Banana", created: "2026-06-05", duration: "00:45:03", task_count: 2 }),
  M({ id: "b", title: "Abacaxi", created: "2026-06-09", duration: "01:02:00", task_count: 5 }),
  M({ id: "c", title: "Caju", created: "2026-06-01", duration: "00:10:00", task_count: 0 }),
];

describe("sortMeetings", () => {
  it("sorts by task_count desc and asc", () => {
    expect(sortMeetings(items, "task_count", "desc").map((m) => m.id)).toEqual(["b", "a", "c"]);
    expect(sortMeetings(items, "task_count", "asc").map((m) => m.id)).toEqual(["c", "a", "b"]);
  });
  it("sorts by created asc (oldest first)", () => {
    expect(sortMeetings(items, "created", "asc").map((m) => m.id)).toEqual(["c", "a", "b"]);
  });
  it("sorts by duration desc (longest first)", () => {
    expect(sortMeetings(items, "duration", "desc").map((m) => m.id)).toEqual(["b", "a", "c"]);
  });
  it("sorts by title asc (A-Z)", () => {
    expect(sortMeetings(items, "title", "asc").map((m) => m.title)).toEqual(["Abacaxi", "Banana", "Caju"]);
  });
  it("does not mutate the input array", () => {
    const before = items.map((m) => m.id);
    sortMeetings(items, "title", "asc");
    expect(items.map((m) => m.id)).toEqual(before);
  });
});
