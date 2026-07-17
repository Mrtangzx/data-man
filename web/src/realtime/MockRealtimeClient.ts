import { api } from "../api";
import type { RealtimeSession, RealtimeTurn } from "../types";
import type { RealtimeClient } from "./RealtimeClient";

export class MockRealtimeClient implements RealtimeClient {
  private session: RealtimeSession | null = null;

  async connect(): Promise<RealtimeSession> {
    this.session = await api<RealtimeSession>("/realtime/sessions", {
      method: "POST",
      body: JSON.stringify({ deployment_id: "mock-realtime" }),
    });
    return this.session;
  }

  async sendText(text: string): Promise<RealtimeTurn> {
    if (!this.session) throw new Error("实时会话尚未连接。");
    return api<RealtimeTurn>(`/realtime/sessions/${this.session.session_id}/turns`, {
      method: "POST",
      body: JSON.stringify({ text }),
    });
  }

  async sendAudio(_: Blob): Promise<RealtimeTurn> {
    return this.sendText("已收到一段麦克风测试音频");
  }

  async interrupt(): Promise<void> {
    if (!this.session) return;
    await api(`/realtime/sessions/${this.session.session_id}/interrupt`, { method: "POST" });
  }

  async disconnect(): Promise<void> {
    if (!this.session) return;
    await api(`/realtime/sessions/${this.session.session_id}`, { method: "DELETE" });
    this.session = null;
  }
}
