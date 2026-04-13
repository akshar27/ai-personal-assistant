"use client";

import { useEffect, useRef, useState } from "react";
import MessageList, { Message } from "./MessageList";
import { sendApproval, sendChat, getGoogleAuthUrl } from "../lib/api";

const samplePrompts = [
  "summarize my unread emails",
  "what is on my calendar today",
  "remember I prefer concise emails",
  "Write a polite follow-up email to akshargothi70@gmail.com about my interview",
  "create event tomorrow at 2pm called Project Sync",
];

function getOrCreateThreadId(): string {
  if (typeof window === "undefined") return "default-thread";

  const existing = sessionStorage.getItem("assistant_thread_id");
  if (existing) return existing;

  const newId = `thread_${crypto.randomUUID()}`;
  sessionStorage.setItem("assistant_thread_id", newId);
  return newId;
}

export default function ChatBox() {
  const [input, setInput] = useState("");
  const [googleConnected, setGoogleConnected] = useState(false);
  const [threadId, setThreadId] = useState("default-thread");
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      text: "Hi Akshar — I’m your AI personal assistant. I can summarize emails, check your calendar, remember preferences, draft emails, reply to unread emails, and create calendar events with approval.",
    },
  ]);
  const [loading, setLoading] = useState(false);
  const [approvalLoading, setApprovalLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setThreadId(getOrCreateThreadId());

    const params = new URLSearchParams(window.location.search);
    const connected = params.get("google_connected") === "true";

    if (connected) {
      setGoogleConnected(true);

      const timer = setTimeout(() => {
        window.history.replaceState({}, "", "/");
        setGoogleConnected(false);
      }, 2500);

      return () => clearTimeout(timer);
    }
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading, approvalLoading]);

  function startNewChat() {
    const newId = `thread_${crypto.randomUUID()}`;
    sessionStorage.setItem("assistant_thread_id", newId);
    setThreadId(newId);
    setMessages([
      {
        role: "assistant",
        text: "Started a new chat. I can summarize emails, check your calendar, remember preferences, draft emails, reply to unread emails, and create calendar events with approval.",
      },
    ]);
  }

  async function handleSend(customMessage?: string) {
    const finalMessage = (customMessage ?? input).trim();
    if (!finalMessage) return;

    const userMessage: Message = {
      role: "user",
      text: finalMessage,
    };

    setMessages((prev) => [...prev, userMessage]);
    if (!customMessage) setInput("");
    setLoading(true);

    try {
      const res = await sendChat(threadId, finalMessage);

      const assistantMessage: Message = {
        role: "assistant",
        text: res.reply,
        requiresApproval: res.requires_approval,
        approvalPayload: res.approval_payload,
        approvalResolved: false,
        approvalStatus: null,
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error: any) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: `Error: ${error.message}`,
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  async function handleApprove() {
    setApprovalLoading(true);

    try {
      const res = await sendApproval(threadId, true);

      setMessages((prev) => {
        const updated = [...prev];
        for (let i = updated.length - 1; i >= 0; i--) {
          if (
            updated[i].role === "assistant" &&
            updated[i].requiresApproval &&
            !updated[i].approvalResolved
          ) {
            updated[i] = {
              ...updated[i],
              approvalResolved: true,
              approvalStatus: "approved",
            };
            break;
          }
        }

        updated.push({
          role: "assistant",
          text: res.reply,
        });

        return updated;
      });
    } catch (error: any) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: `Approval error: ${error.message}`,
        },
      ]);
    } finally {
      setApprovalLoading(false);
    }
  }

  async function handleReject() {
    setApprovalLoading(true);

    try {
      const res = await sendApproval(threadId, false);

      setMessages((prev) => {
        const updated = [...prev];
        for (let i = updated.length - 1; i >= 0; i--) {
          if (
            updated[i].role === "assistant" &&
            updated[i].requiresApproval &&
            !updated[i].approvalResolved
          ) {
            updated[i] = {
              ...updated[i],
              approvalResolved: true,
              approvalStatus: "rejected",
            };
            break;
          }
        }

        updated.push({
          role: "assistant",
          text: res.reply,
        });

        return updated;
      });
    } catch (error: any) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: `Reject error: ${error.message}`,
        },
      ]);
    } finally {
      setApprovalLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-100">
      <div className="mx-auto max-w-6xl px-4 py-8">
        <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
          <aside className="rounded-3xl border border-white/60 bg-white/70 p-6 shadow-xl backdrop-blur">
            <div className="mb-6">
              <div className="mb-3 inline-flex rounded-full bg-indigo-100 px-3 py-1 text-xs font-semibold text-indigo-700">
                AI Agent Demo
              </div>
              <h1 className="text-3xl font-bold tracking-tight text-slate-900">
                AI Personal Assistant
              </h1>
              <p className="mt-3 text-sm leading-6 text-slate-600">
                A LangGraph-powered assistant with Gmail, Google Calendar, memory,
                and human approval for sensitive actions.
              </p>
            </div>

            <a
              href={getGoogleAuthUrl()}
              className="mb-4 block rounded-2xl bg-slate-900 px-4 py-3 text-center font-medium text-white transition hover:bg-slate-800"
            >
              Connect Google
            </a>

            <button
              onClick={startNewChat}
              className="mb-6 w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 text-center font-medium text-slate-800 transition hover:bg-slate-50"
            >
              New Chat
            </button>

            {googleConnected && (
              <div className="mb-6 rounded-2xl bg-green-100 px-4 py-3 text-sm font-medium text-green-800">
                Google connected successfully.
              </div>
            )}

            <div className="rounded-2xl bg-slate-50 p-4">
              <h2 className="mb-3 text-sm font-semibold text-slate-800">
                Try these prompts
              </h2>
              <div className="flex flex-wrap gap-2">
                {samplePrompts.map((prompt) => (
                  <button
                    key={prompt}
                    onClick={() => handleSend(prompt)}
                    className="rounded-full border border-slate-200 bg-white px-3 py-2 text-left text-xs text-slate-700 transition hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-700"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>

            <div className="mt-6 rounded-2xl bg-gradient-to-r from-indigo-600 to-blue-600 p-4 text-white shadow-lg">
              <h3 className="text-sm font-semibold">What this shows</h3>
              <ul className="mt-3 space-y-2 text-sm text-white/90">
                <li>• Tool use with Gmail and Calendar</li>
                <li>• Preference memory</li>
                <li>• Human-in-the-loop approvals</li>
                <li>• Real-world AI assistant workflow</li>
              </ul>
            </div>
          </aside>

          <section className="rounded-3xl border border-white/60 bg-white/80 shadow-2xl backdrop-blur">
            <div className="border-b border-slate-200/70 px-6 py-5">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-semibold text-slate-900">
                    Assistant Chat
                  </h2>
                  <p className="mt-1 text-sm text-slate-500">
                    Ask the assistant to summarize, remember, draft, reply, or schedule.
                  </p>
                </div>
                <div className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-medium text-emerald-700">
                  Live Backend Connected
                </div>
              </div>
            </div>

            <div className="flex h-[70vh] flex-col">
              <div className="flex-1 overflow-y-auto px-6 py-6">
                <MessageList
                  messages={messages}
                  onApprove={handleApprove}
                  onReject={handleReject}
                  approvalLoading={approvalLoading}
                />

                {(loading || approvalLoading) && (
                  <div className="mt-4 flex justify-start">
                    <div className="rounded-3xl border border-slate-200 bg-slate-50 px-5 py-3 text-sm text-slate-500 shadow-sm">
                      Assistant is thinking...
                    </div>
                  </div>
                )}

                <div ref={bottomRef} />
              </div>

              <div className="border-t border-slate-200/70 bg-white/70 px-6 py-4">
                <div className="flex gap-3">
                  <input
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !loading) handleSend();
                    }}
                    placeholder="Type your request..."
                    className="flex-1 rounded-2xl border border-slate-300 bg-white px-4 py-3 text-slate-900 outline-none transition focus:border-indigo-500 focus:ring-4 focus:ring-indigo-100"
                  />
                  <button
                    onClick={() => handleSend()}
                    disabled={loading}
                    className="rounded-2xl bg-indigo-600 px-6 py-3 font-medium text-white shadow-lg transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {loading ? "Sending..." : "Send"}
                  </button>
                </div>
              </div>
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}