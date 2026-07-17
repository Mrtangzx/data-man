import type { ApiErrorBody } from "./types";

export const API_BASE = import.meta.env.VITE_API_BASE || "/api";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly body: ApiErrorBody,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API_BASE}/v1${path}`, { ...init, headers });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiErrorBody;
    throw new ApiError(body.message || `请求失败 (${response.status})`, response.status, body);
  }
  return response.json() as Promise<T>;
}

export function readableError(error: unknown): string {
  if (error instanceof ApiError) {
    const fix = error.body.details?.fix;
    const diagnostic = error.body.request_id ? `诊断 ID: ${error.body.request_id}` : "";
    return [error.message, fix, diagnostic].filter(Boolean).join(" ");
  }
  return error instanceof Error ? error.message : "发生了未知错误。";
}
