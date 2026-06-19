/**
 * Typed client for the Agent Platform backend.
 *
 * All endpoints return the standard envelope:
 *   { status: "success", data, timestamp } | { status: "error", error, code, timestamp }
 */

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

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
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  const body = (await response.json()) as SuccessEnvelope<T> | ErrorEnvelope;
  if (body.status === "error") {
    throw new ApiError(body.error, body.code);
  }
  return body.data;
}

export const api = {
  listAgents: () => request<{ agents: Agent[] }>("/agents").then((d) => d.agents),

  createAgent: (name: string) =>
    request<Agent>("/agents", { method: "POST", body: JSON.stringify({ name }) }),

  chat: (agentId: string, message: string) =>
    request<ChatResult>("/chat", {
      method: "POST",
      body: JSON.stringify({ agent_id: agentId, message }),
    }),

  getOutputs: (agentId: string) =>
    request<{ agent_id: string; outputs: Interaction[] }>(
      `/agents/${encodeURIComponent(agentId)}/outputs`,
    ).then((d) => d.outputs),
};
