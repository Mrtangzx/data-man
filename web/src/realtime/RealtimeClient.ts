import type { RealtimeSession, RealtimeTurn } from "../types";

export interface RealtimeClient {
  connect(): Promise<RealtimeSession>;
  sendText(text: string): Promise<RealtimeTurn>;
  sendAudio(blob: Blob): Promise<RealtimeTurn>;
  interrupt(): Promise<void>;
  disconnect(): Promise<void>;
}
