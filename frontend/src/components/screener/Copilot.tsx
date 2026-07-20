"use client";
import React, { useEffect, useRef, useState } from "react";
import { askCopilot, ChatMessage } from "@/lib/api";

const SUGGESTIONS = [
  "What are the top 3 buys right now?",
  "Why is NVDA scoring the way it is?",
  "Which stocks are under the radar?",
  "What does AAPL's sentiment history look like?",
];

export default function Copilot() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [notConfigured, setNotConfigured] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || loading) return;
    const next = [...messages, { role: "user" as const, content: trimmed }];
    setMessages(next);
    setInput("");
    setLoading(true);
    try {
      const r = await askCopilot(next);
      if (!r.reply) {
        setNotConfigured(r.message ?? "AI Copilot is not configured.");
      } else {
        setMessages([...next, { role: "assistant", content: r.reply }]);
      }
    } catch {
      setMessages([
        ...next,
        { role: "assistant", content: "Something went wrong reaching the AI Copilot. Check the API is running." },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-white/[0.03]">
      <div className="border-b border-gray-100 p-4 dark:border-gray-800">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-white/90">
          AI Copilot
        </h2>
        <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
          Answers are grounded only in this screener&apos;s own data: computed scores,
          Yahoo Finance fundamentals, and Alpha Vantage / free news sentiment history.
        </p>
      </div>

      {notConfigured && (
        <div className="m-4 rounded-lg border border-warning-500/40 bg-warning-50 p-3 text-xs text-gray-700 dark:bg-warning-500/10 dark:text-gray-200">
          {notConfigured}
        </div>
      )}

      <div className="max-h-96 space-y-3 overflow-y-auto p-4">
        {messages.length === 0 && !notConfigured && (
          <div className="flex flex-wrap gap-2">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                onClick={() => send(s)}
                className="rounded-lg border border-gray-200 px-3 py-1.5 text-left text-xs text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-white/5"
              >
                {s}
              </button>
            ))}
          </div>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`max-w-[85%] rounded-lg px-3 py-2 text-sm leading-6 ${
              m.role === "user"
                ? "ml-auto bg-gray-900 text-white dark:bg-white dark:text-gray-900"
                : "bg-gray-100 text-gray-800 dark:bg-white/10 dark:text-gray-200"
            }`}
          >
            {m.content}
          </div>
        ))}
        {loading && (
          <div className="max-w-[85%] rounded-lg bg-gray-100 px-3 py-2 text-sm text-gray-500 dark:bg-white/10 dark:text-gray-400">
            Analysing...
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="flex items-center gap-2 border-t border-gray-100 p-3 dark:border-gray-800"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about any stock, e.g. why is NVDA scoring high?"
          disabled={!!notConfigured}
          className="flex-1 rounded-lg border border-gray-200 bg-transparent px-3 py-2 text-sm text-gray-700 placeholder:text-gray-400 disabled:opacity-50 dark:border-gray-700 dark:text-gray-200"
        />
        <button
          type="submit"
          disabled={loading || !!notConfigured}
          className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40 dark:bg-white dark:text-gray-900"
        >
          Send
        </button>
        {messages.length > 0 && (
          <button
            type="button"
            onClick={() => setMessages([])}
            className="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
          >
            Clear
          </button>
        )}
      </form>
    </div>
  );
}
