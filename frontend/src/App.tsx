import { useCallback, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import {
  ApiError,
  api,
  clearApiKey,
  getApiKey,
  setApiKey,
  type Agent,
  type AgentMode,
  type Interaction,
} from "./api";

const APP_VERSION = "v5 · markdown";

const MODE_HINTS: Record<AgentMode, string> = {
  plan: "propose only, no changes",
  default: "full access (files + shell)",
};

export default function App() {
  const [apiKey, setKey] = useState(getApiKey());
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [outputs, setOutputs] = useState<Interaction[]>([]);
  const [newAgentName, setNewAgentName] = useState("");
  const [message, setMessage] = useState("");
  const [mode, setMode] = useState<AgentMode>("default");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState<{ text: string; tools: string[] } | null>(null);

  const logout = useCallback(() => {
    clearApiKey();
    setKey("");
    setAgents([]);
    setSelectedId(null);
    setOutputs([]);
  }, []);

  // Centralised error handling: a bad/expired key sends the user back to login.
  const handleError = useCallback(
    (err: unknown) => {
      if (err instanceof ApiError && err.code === "UNAUTHORIZED") {
        logout();
        setError("Invalid API key — please sign in again.");
      } else {
        setError(describe(err));
      }
    },
    [logout],
  );

  const refreshAgents = useCallback(async () => {
    try {
      setAgents(await api.listAgents());
    } catch (err) {
      handleError(err);
    }
  }, [handleError]);

  const refreshOutputs = useCallback(
    async (agentId: string) => {
      try {
        setOutputs(await api.getOutputs(agentId));
      } catch (err) {
        handleError(err);
      }
    },
    [handleError],
  );

  useEffect(() => {
    if (apiKey) void refreshAgents();
  }, [apiKey, refreshAgents]);

  useEffect(() => {
    if (selectedId) void refreshOutputs(selectedId);
    else setOutputs([]);
  }, [selectedId, refreshOutputs]);

  // Login gate — after all hooks, so hook order stays stable across renders.
  if (!apiKey) {
    return (
      <Login
        onSubmit={(k) => {
          setApiKey(k);
          setKey(getApiKey());
          setError(null);
        }}
      />
    );
  }

  async function handleCreateAgent(event: React.FormEvent) {
    event.preventDefault();
    if (!newAgentName.trim()) return;
    setError(null);
    try {
      const agent = await api.createAgent(newAgentName.trim());
      setNewAgentName("");
      await refreshAgents();
      setSelectedId(agent.id);
    } catch (err) {
      handleError(err);
    }
  }

  async function handleSend(event: React.FormEvent) {
    event.preventDefault();
    const text = message.trim();
    if (!selectedId || !text) return;

    // Optimistic: show the user's message immediately, before the round-trip.
    const optimistic: Interaction = {
      id: `local-${Date.now()}`,
      timestamp: new Date().toISOString(),
      role: "user",
      content: text,
      usage: null,
    };
    setOutputs((prev) => [...prev, optimistic]);
    setMessage("");
    setBusy(true);
    setError(null);
    setLive({ text: "", tools: [] });
    const chunks: string[] = [];
    let resultText = "";
    try {
      for await (const ev of api.chatStream(selectedId, text, mode)) {
        if (ev.type === "text") {
          chunks.push(ev.text ?? "");
          setLive((l) => (l ? { ...l, text: l.text ? `${l.text}\n${ev.text ?? ""}` : ev.text ?? "" } : l));
        } else if (ev.type === "tool") {
          const label = `${ev.name ?? "tool"}${ev.input ? ` ${ev.input}` : ""}`;
          setLive((l) => (l ? { ...l, tools: [...l.tools, label] } : l));
        } else if (ev.type === "result") {
          resultText = ev.text ?? "";
        } else if (ev.type === "error") {
          throw new ApiError(ev.error ?? "stream error", ev.code ?? "BACKEND_ERROR");
        }
      }
      // Append the agent reply straight from the stream — no refresh round-trip
      // (which raced the server's persistence and made the reply disappear).
      const answer = (resultText || chunks.join("\n")).trim();
      if (answer) {
        setOutputs((prev) => [
          ...prev,
          {
            id: `agent-${Date.now()}`,
            timestamp: new Date().toISOString(),
            role: "agent",
            content: answer,
            usage: null,
          },
        ]);
      }
      void refreshAgents(); // refresh sidebar counts; does not touch the transcript
    } catch (err) {
      handleError(err);
    } finally {
      setBusy(false);
      setLive(null);
    }
  }

  return (
    <div className="flex h-[100dvh] flex-col bg-slate-100 text-slate-900">
      <header className="flex items-center justify-between gap-2 border-b border-slate-300 bg-white px-4 py-3 md:px-6 md:py-4">
        <div className="flex min-w-0 items-center gap-1">
          {selectedId && (
            <button
              onClick={() => setSelectedId(null)}
              aria-label="Back to agents"
              className="-ml-1 rounded p-2 text-lg leading-none text-slate-600 hover:bg-slate-100 md:hidden"
            >
              ←
            </button>
          )}
          <div className="min-w-0">
            <h1 className="truncate text-lg font-semibold md:text-xl">Agent Platform</h1>
            <p className="hidden text-sm text-slate-500 sm:block">
            Claude Code session gateway · {APP_VERSION}
          </p>
          </div>
        </div>
        <button
          onClick={logout}
          className="shrink-0 rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100"
        >
          Sign out
        </button>
      </header>

      <div className="flex min-h-0 flex-1">
        {/* Sidebar: create + agent list. Full-width on mobile, hidden once a chat is open. */}
        <aside
          className={`${selectedId ? "hidden md:flex" : "flex"} w-full flex-col border-r border-slate-300 bg-white md:w-72`}
        >
          <form onSubmit={handleCreateAgent} className="border-b border-slate-200 p-4">
            <label className="mb-1 block text-xs font-medium uppercase text-slate-500">
              New agent
            </label>
            <div className="flex gap-2">
              <input
                value={newAgentName}
                onChange={(e) => setNewAgentName(e.target.value)}
                placeholder="e.g. architect"
                className="min-w-0 flex-1 rounded border border-slate-300 px-3 py-2 text-base md:text-sm"
              />
              <button
                type="submit"
                className="shrink-0 rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
              >
                Add
              </button>
            </div>
          </form>

          <ul className="flex-1 overflow-y-auto">
            {agents.length === 0 && <li className="p-4 text-sm text-slate-400">No agents yet.</li>}
            {agents.map((agent) => (
              <li key={agent.id}>
                <button
                  onClick={() => setSelectedId(agent.id)}
                  className={`flex w-full flex-col items-start border-b border-slate-100 px-4 py-4 text-left hover:bg-slate-50 md:py-3 ${
                    selectedId === agent.id ? "bg-slate-100" : ""
                  }`}
                >
                  <span className="font-medium">{agent.name}</span>
                  <span className="text-xs text-slate-500">
                    {agent.status} · {agent.output_count} msgs
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        {/* Main: conversation. Hidden on mobile until an agent is selected. */}
        <main
          className={`${selectedId ? "flex" : "hidden md:flex"} min-w-0 flex-1 flex-col`}
        >
          {error && (
            <div className="border-b border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700 md:px-6">
              {error}
            </div>
          )}

          {!selectedId ? (
            <div className="flex flex-1 items-center justify-center p-6 text-center text-slate-400">
              Select or create an agent to start chatting.
            </div>
          ) : (
            <>
              <div className="flex-1 space-y-3 overflow-y-auto p-4 md:p-6">
                {outputs.length === 0 && (
                  <p className="text-sm text-slate-400">No messages yet. Say hello below.</p>
                )}
                {outputs.map((item) => (
                  <div
                    key={item.id}
                    className={`max-w-[85%] rounded-lg px-4 py-2 text-sm md:max-w-2xl ${
                      item.role === "user"
                        ? "ml-auto bg-slate-900 text-white"
                        : "mr-auto bg-white text-slate-900 shadow"
                    }`}
                  >
                    <div className="mb-1 text-xs uppercase opacity-60">{item.role}</div>
                    {item.role === "agent" ? (
                      <div className="prose prose-sm prose-slate max-w-none overflow-x-auto break-words prose-pre:bg-slate-800 prose-pre:text-slate-100">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{item.content}</ReactMarkdown>
                      </div>
                    ) : (
                      <div className="whitespace-pre-wrap break-words">{item.content}</div>
                    )}
                  </div>
                ))}
                {live && (
                  <div className="mr-auto max-w-[85%] rounded-lg bg-white px-4 py-2 text-sm text-slate-900 shadow md:max-w-2xl">
                    <div className="mb-1 text-xs uppercase opacity-60">agent</div>
                    {live.tools.map((t, i) => (
                      <div key={i} className="font-mono text-xs text-slate-500">
                        🔧 {t}
                      </div>
                    ))}
                    {live.text && (
                      <div className="mt-1 whitespace-pre-wrap break-words">{live.text}</div>
                    )}
                    {!live.text && live.tools.length === 0 && (
                      <div className="animate-pulse text-slate-400">…thinking</div>
                    )}
                  </div>
                )}
              </div>

              <form
                onSubmit={handleSend}
                className="flex flex-col gap-2 border-t border-slate-300 bg-white p-3 pb-[calc(env(safe-area-inset-bottom)+0.75rem)] md:p-4"
              >
                <div className="flex items-center gap-2 text-xs">
                  <span className="text-slate-400">Mode</span>
                  <div className="inline-flex overflow-hidden rounded border border-slate-300">
                    {(["plan", "default"] as AgentMode[]).map((m) => (
                      <button
                        key={m}
                        type="button"
                        onClick={() => setMode(m)}
                        className={`px-3 py-1 font-medium capitalize ${
                          mode === m ? "bg-slate-900 text-white" : "bg-white text-slate-600 hover:bg-slate-50"
                        }`}
                      >
                        {m}
                      </button>
                    ))}
                  </div>
                  <span className="text-slate-400">{MODE_HINTS[mode]}</span>
                </div>
                <div className="flex gap-2">
                  <input
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    placeholder={mode === "plan" ? "Ask for a plan…" : "Message the agent…"}
                    disabled={busy}
                    className="min-w-0 flex-1 rounded border border-slate-300 px-3 py-2.5 text-base disabled:opacity-50"
                  />
                  <button
                    type="submit"
                    disabled={busy || !message.trim()}
                    className="shrink-0 rounded bg-slate-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
                  >
                    {busy ? "…" : "Send"}
                  </button>
                </div>
              </form>
            </>
          )}
        </main>
      </div>
    </div>
  );
}

function describe(err: unknown): string {
  if (err instanceof ApiError) return `${err.code}: ${err.message}`;
  if (err instanceof Error) return err.message;
  return "Unknown error";
}

/** Sign-in screen: enter the gateway API key. */
function Login({ onSubmit }: { onSubmit: (key: string) => void }) {
  const [value, setValue] = useState("");
  return (
    <div className="flex h-[100dvh] items-center justify-center bg-slate-100 p-4">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (value.trim()) onSubmit(value.trim());
        }}
        className="w-full max-w-sm rounded-lg bg-white p-6 shadow"
      >
        <h1 className="text-lg font-semibold text-slate-900">Agent Platform</h1>
        <p className="mb-4 text-sm text-slate-500">Enter your API key to continue.</p>
        <input
          type="password"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="API key"
          autoFocus
          autoCapitalize="off"
          autoCorrect="off"
          className="mb-3 w-full rounded border border-slate-300 px-3 py-2.5 text-base"
        />
        <button
          type="submit"
          disabled={!value.trim()}
          className="w-full rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
        >
          Sign in
        </button>
      </form>
    </div>
  );
}
