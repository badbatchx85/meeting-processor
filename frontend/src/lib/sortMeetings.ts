import type { MeetingSummary } from "../api/types";

export type SortKey = "created" | "duration" | "task_count" | "title";

export function sortMeetings(
  items: MeetingSummary[],
  key: SortKey,
  dir: "asc" | "desc",
): MeetingSummary[] {
  const sign = dir === "asc" ? 1 : -1;
  return [...items].sort((a, b) => {
    const cmp =
      key === "task_count"
        ? a.task_count - b.task_count
        : String(a[key]).localeCompare(String(b[key]));
    return cmp * sign;
  });
}
