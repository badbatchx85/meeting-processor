import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ToastProvider } from "../components/Toast";
import { Tasks } from "../pages/Tasks";

function setup() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider><Tasks /></ToastProvider>
    </QueryClientProvider>,
  );
}

describe("Tasks Kanban", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify([
      { task_id: "t1", meeting_id: "m1", column: "A Fazer", description: "Fazer X",
        done: false, assignee: "Ana", priority: "", due_date: "", timestamp: "" },
    ]), { status: 200 })));
  });

  it("renders columns and a task card", async () => {
    setup();
    expect(await screen.findByText("Fazer X")).toBeInTheDocument();
    expect(screen.getByText("A Fazer")).toBeInTheDocument();
    expect(screen.getByText("Concluído")).toBeInTheDocument();
  });
});
