/**
 * Typed client for the Agent Platform backend.
 *
 * All endpoints return the standard envelope:
 *   { status: "success", data, timestamp } | { status: "error", error, code, timestamp }
 */

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

// --- API key (our gateway auth) -------------------------------------------
// Stored in localStorage and sent as X-API-Key on every request. The backend
// requires it (except /health). A 401 clears it so the UI returns to login.
const KEY_STORAGE = "agent_api_key";

export function getApiKey(): string {
  return localStorage.getItem(KEY_STORAGE) ?? "";
}

export function setApiKey(key: string): void {
  localStorage.setItem(KEY_STORAGE, key.trim());
}

export function clearApiKey(): void {
  localStorage.removeItem(KEY_STORAGE);
}

/** Per-message agent mode: plan (propose only), default (edit files, no shell), auto (full). */
export type AgentMode = "plan" | "default" | "auto";

export interface Agent {
  id: string;
  name: string;
  status: string;
  claude_session_id: string | null;
  created_at: string;
  updated_at: string;
  output_count: number;
}

export interface Interaction {
  id: string;
  timestamp: string;
  role: "user" | "agent";
  content: string;
  usage: Record<string, unknown> | null;
}

export interface ChatResult {
  agent_id: string;
  response: string;
  session_id: string | null;
  usage: Record<string, unknown>;
}

interface SuccessEnvelope<T> {
  status: "success";
  data: T;
  timestamp: string;
}

interface ErrorEnvelope {
  status: "error";
  error: string;
  code: string;
  timestamp: string;
}

/** Error carrying the backend's error code, thrown on non-success responses. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly code: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", "X-API-Key": getApiKey(), ...init?.headers },
  });
  const body = (await response.json()) as SuccessEnvelope<T> | ErrorEnvelope;
  if (body.status === "error") {
    throw new ApiError(body.error, body.code);
  }
  return body.data;
}

/** A live event from /chat/stream. */
export interface StreamEvent {
  type: "text" | "tool" | "result" | "error";
  text?: string;
  name?: string;
  input?: string;
  session_id?: string | null;
  usage?: Record<string, unknown>;
  error?: string;
  code?: string;
}

/** Stream an agent's progress (NDJSON over fetch — EventSource can't send headers). */
async function* chatStream(
  agentId: string,
  message: string,
  mode?: AgentMode,
): AsyncGenerator<StreamEvent> {
  const response = await fetch(`${API_BASE_URL}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Key": getApiKey() },
    body: JSON.stringify({ agent_id: agentId, message, mode }),
  });
  if (!response.ok || !response.body) {
    let err: ErrorEnvelope | null = null;
    try {
      err = (await response.json()) as ErrorEnvelope;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(err?.error ?? `HTTP ${response.status}`, err?.code ?? "BACKEND_ERROR");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let nl: number;
    while ((nl = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, nl).trim();
      buffer = buffer.slice(nl + 1);
      if (line) yield JSON.parse(line) as StreamEvent;
    }
  }
  const tail = buffer.trim();
  if (tail) yield JSON.parse(tail) as StreamEvent;
}

export const api = {
  chatStream,

  listAgents: () => request<{ agents: Agent[] }>("/agents").then((d) => d.agents),

  createAgent: (name: string) =>
    request<Agent>("/agents", { method: "POST", body: JSON.stringify({ name }) }),

  chat: (agentId: string, message: string, mode?: AgentMode) =>
    request<ChatResult>("/chat", {
      method: "POST",
      body: JSON.stringify({ agent_id: agentId, message, mode }),
    }),

  getOutputs: (agentId: string) =>
    request<{ agent_id: string; outputs: Interaction[] }>(
      `/agents/${encodeURIComponent(agentId)}/outputs`,
    ).then((d) => d.outputs),
};
