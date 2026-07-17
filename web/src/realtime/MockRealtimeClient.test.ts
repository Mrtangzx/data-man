import { afterEach, describe, expect, it, vi } from "vitest";
import { MockRealtimeClient } from "./MockRealtimeClient";

describe("MockRealtimeClient", () => {
  afterEach(() => vi.restoreAllMocks());

  it("uses the stable realtime client contract", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/realtime/sessions")) {
        return new Response(JSON.stringify({ session_id: "rt_test", state: "connected" }), { status: 201 });
      }
      if (url.endsWith("/turns")) {
        return new Response(JSON.stringify({ turn_id: "turn_1", sequence: 1, user_text: "你好", assistant_text: "收到", state: "speaking" }), { status: 200 });
      }
      return new Response(JSON.stringify({ acknowledged: true }), { status: init?.method === "DELETE" ? 200 : 200 });
    });

    const client = new MockRealtimeClient();
    const session = await client.connect();
    expect(session.session_id).toBe("rt_test");
    const turn = await client.sendText("你好");
    expect(turn.assistant_text).toBe("收到");
    await client.interrupt();
    await client.disconnect();
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });
});
