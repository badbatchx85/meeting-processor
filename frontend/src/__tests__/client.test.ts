import { describe, it, expect, vi, beforeEach } from "vitest";
import { api, ApiError } from "../api/client";

describe("api client", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("returns parsed JSON on 200", async () => {
    vi.stubGlobal("fetch", vi.fn(async () =>
      new Response(JSON.stringify({ status: "ok" }), { status: 200 })));
    const data = await api.get<{ status: string }>("/api/health");
    expect(data.status).toBe("ok");
  });

  it("throws ApiError with message on non-2xx", async () => {
    vi.stubGlobal("fetch", vi.fn(async () =>
      new Response(JSON.stringify({ error: "bad" }), { status: 400 })));
    await expect(api.post("/api/llm/provider", { provider: "x" }))
      .rejects.toMatchObject({ status: 400, message: "bad" } satisfies Partial<ApiError>);
  });
});
