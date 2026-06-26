import { useEffect, useMemo, useRef, useState } from "react";

import { ApiError, api, busStreamUrl, type BusMessage } from "./api";

/**
 * Bus chat — the human participates on the inter-agent bus like any agent.
 *
 * It opens the SSE stream (the server replays the conversation then pushes new
 * messages live) and posts via /bus/post. Every message is shown, whoever sent it,
 * so the human sees the whole exchange (transparency) and can play "the other agent".
 */
export default function BusChat() {
  const [messages, setMessages] = useState<BusMessage[]>([]);
  const [content, setContent] = useState("");
  const [sender, setSender] = useState("human");
  const [recipient, setRecipient] = useState("agentA");
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Subscribe to the SSE stream. It seeds the full history on connect and pushes
  // new messages; we de-duplicate by id (reconnects replay everything).
  useEffect(() => {
    const source = new EventSource(busStreamUrl());
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false); // EventSource auto-reconnects
    source.onmessage = (event) => {
      const incoming = JSON.parse(event.data) as BusMessage;
      setMessages((prev) =>
        prev.some((m) => m.id === incoming.id) ? prev : [...prev, incoming],
      );
    };
    return () => source.close();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const participants = useMemo(() => {
    const ids = new Set<string>();
    for (const m of messages) {
      ids.add(m.sender);
      if (m.recipient) ids.add(m.recipient);
    }
    return [...ids].sort();
  }, [messages]);

  async function handleSend(event: React.FormEvent) {
    event.preventDefault();
    const text = content.trim();
    if (!text) return;
    setError(null);
    try {
      await api.postBusMessage({
        content: text,
        sender: sender.trim() || "human",
        recipient: recipient.trim() || null,
      });
      setContent(""); // the stream will echo our message back, so we don't append it here
    } catch (err) {
      setError(err instanceof ApiError ? `${err.code}: ${err.message}` : "Failed to send");
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-3 border-b border-slate-200 bg-white px-6 py-2 text-sm">
        <span
          className={`inline-flex items-center gap-1.5 ${connected ? "text-emerald-600" : "text-slate-400"}`}
        >
          <span
            className={`h-2 w-2 rounded-full ${connected ? "bg-emerald-500" : "bg-slate-300"}`}
          />
          {connected ? "live" : "connecting…"}
        </span>
        <span className="text-slate-400">·</span>
        <span className="text-slate-500">
          {messages.length} message{messages.length === 1 ? "" : "s"}
        </span>
        {participants.length > 0 && (
          <>
            <span className="text-slate-400">·</span>
            <span className="text-slate-500">participants: {participants.join(", ")}</span>
          </>
        )}
      </div>

      {error && (
        <div className="border-b border-red-200 bg-red-50 px-6 py-2 text-sm text-red-700">{error}</div>
      )}

      <div className="flex-1 space-y-3 overflow-y-auto p-6">
        {messages.length === 0 && (
          <p className="text-sm text-slate-400">
            No messages on the bus yet. Send one below — you are a participant just like an agent.
          </p>
        )}
        {messages.map((message) => {
          const mine = message.sender === sender;
          return (
            <div
              key={message.id}
              className={`max-w-2xl rounded-lg px-4 py-2 text-sm ${
                mine ? "ml-auto bg-slate-900 text-white" : "mr-auto bg-white text-slate-900 shadow"
              }`}
            >
              <div className="mb-1 flex items-center gap-2 text-xs uppercase opacity-60">
                <span className="font-semibold">{message.sender}</span>
                <span>→ {message.recipient ?? "all"}</span>
                {message.message_type !== "text" && (
                  <span className="rounded bg-amber-200 px-1 text-amber-900">{message.message_type}</span>
                )}
              </div>
              <div className="whitespace-pre-wrap">{message.content}</div>
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={handleSend} className="border-t border-slate-300 bg-white p-4">
        <div className="mb-2 flex gap-2 text-xs">
          <label className="flex items-center gap-1 text-slate-500">
            as
            <input
              value={sender}
              onChange={(e) => setSender(e.target.value)}
              className="w-24 rounded border border-slate-300 px-2 py-1"
            />
          </label>
          <label className="flex items-center gap-1 text-slate-500">
            to
            <input
              value={recipient}
              onChange={(e) => setRecipient(e.target.value)}
              placeholder="agent id or topic"
              className="w-40 rounded border border-slate-300 px-2 py-1"
            />
          </label>
        </div>
        <div className="flex gap-2">
          <input
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="Post a message to the bus…"
            className="flex-1 rounded border border-slate-300 px-3 py-2 text-sm"
          />
          <button
            type="submit"
            disabled={!content.trim()}
            className="rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
          >
            Send
          </button>
        </div>
      </form>
    </div>
  );
}
