import { useCallback, useEffect, useState } from "react";

import { ApiError, api, type Agent, type Interaction } from "./api";
import BusChat from "./BusChat";

type View = "bus" | "agents";

export default function App() {
  const [view, setView] = useState<View>("bus");
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [outputs, setOutputs] = useState<Interaction[]>([]);
  const [newAgentName, setNewAgentName] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshAgents = useCallback(async () => {
    try {
      setAgents(await api.listAgents());
    } catch (err) {
      setError(describe(err));
    }
  }, []);

  const refreshOutputs = useCallback(async (agentId: string) => {
    try {
      setOutputs(await api.getOutputs(agentId));
    } catch (err) {
      setError(describe(err));
    }
  }, []);

  useEffect(() => {
    void refreshAgents();
  }, [refreshAgents]);

  useEffect(() => {
    if (selectedId) void refreshOutputs(selectedId);
    else setOutputs([]);
  }, [selectedId, refreshOutputs]);

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
      setError(describe(err));
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
    try {
      await api.chat(selectedId, text);
      await refreshOutputs(selectedId); // replace optimistic copy with server truth
      await refreshAgents();
    } catch (err) {
      setError(describe(err));
      await refreshOutputs(selectedId);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-screen flex-col bg-slate-100 text-slate-900">
      <header className="flex items-center justify-between border-b border-slate-300 bg-white px-6 py-4">
        <div>
          <h1 className="text-xl font-semibold">Agent Platform</h1>
          <p className="text-sm text-slate-500">Multi-agent communication bus</p>
        </div>
        <nav className="flex gap-1 rounded-lg bg-slate-100 p-1 text-sm">
          {(["bus", "agents"] as const).map((value) => (
            <button
              key={value}
              onClick={() => setView(value)}
              className={`rounded-md px-3 py-1 font-medium capitalize ${
                view === value ? "bg-white text-slate-900 shadow" : "text-slate-500 hover:text-slate-700"
              }`}
            >
              {value === "bus" ? "Bus (live)" : "Agents"}
            </button>
          ))}
        </nav>
      </header>

      {view === "bus" && <BusChat />}

      {view === "agents" && (
      <div className="flex min-h-0 flex-1">
        {/* Sidebar: create + agent list */}
        <aside className="flex w-72 flex-col border-r border-slate-300 bg-white">
          <form onSubmit={handleCreateAgent} className="border-b border-slate-200 p-4">
            <label className="mb-1 block text-xs font-medium uppercase text-slate-500">
              New agent
            </label>
            <div className="flex gap-2">
              <input
                value={newAgentName}
                onChange={(e) => setNewAgentName(e.target.value)}
                placeholder="e.g. architect"
                className="min-w-0 flex-1 rounded border border-slate-300 px-2 py-1 text-sm"
              />
              <button
                type="submit"
                className="rounded bg-slate-900 px-3 py-1 text-sm font-medium text-white hover:bg-slate-700"
              >
                Add
              </button>
            </div>
          </form>

          <ul className="flex-1 overflow-y-auto">
            {agents.length === 0 && (
              <li className="p-4 text-sm text-slate-400">No agents yet.</li>
            )}
            {agents.map((agent) => (
              <li key={agent.id}>
                <button
                  onClick={() => setSelectedId(agent.id)}
                  className={`flex w-full flex-col items-start border-b border-slate-100 px-4 py-3 text-left hover:bg-slate-50 ${
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

        {/* Main: conversation */}
        <main className="flex min-w-0 flex-1 flex-col">
          {error && (
            <div className="border-b border-red-200 bg-red-50 px-6 py-2 text-sm text-red-700">
              {error}
            </div>
          )}

          {!selectedId ? (
            <div className="flex flex-1 items-center justify-center text-slate-400">
              Select or create an agent to start chatting.
            </div>
          ) : (
            <>
              <div className="flex-1 space-y-3 overflow-y-auto p-6">
                {outputs.length === 0 && (
                  <p className="text-sm text-slate-400">No messages yet. Say hello below.</p>
                )}
                {outputs.map((item) => (
                  <div
                    key={item.id}
                    className={`max-w-2xl rounded-lg px-4 py-2 text-sm ${
                      item.role === "user"
                        ? "ml-auto bg-slate-900 text-white"
                        : "mr-auto bg-white text-slate-900 shadow"
                    }`}
                  >
                    <div className="mb-1 text-xs uppercase opacity-60">{item.role}</div>
                    <div className="whitespace-pre-wrap">{item.content}</div>
                  </div>
                ))}
                {busy && (
                  <div className="mr-auto max-w-2xl rounded-lg bg-white px-4 py-2 text-sm text-slate-400 shadow">
                    <div className="mb-1 text-xs uppercase opacity-60">agent</div>
                    <div className="animate-pulse">…thinking</div>
                  </div>
                )}
              </div>

              <form onSubmit={handleSend} className="flex gap-2 border-t border-slate-300 bg-white p-4">
                <input
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder="Message the agent…"
                  disabled={busy}
                  className="flex-1 rounded border border-slate-300 px-3 py-2 text-sm disabled:opacity-50"
                />
                <button
                  type="submit"
                  disabled={busy || !message.trim()}
                  className="rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
                >
                  {busy ? "Sending…" : "Send"}
                </button>
              </form>
            </>
          )}
        </main>
      </div>
      )}
    </div>
  );
}

function describe(err: unknown): string {
  if (err instanceof ApiError) return `${err.code}: ${err.message}`;
  if (err instanceof Error) return err.message;
  return "Unknown error";
}
