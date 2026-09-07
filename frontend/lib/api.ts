import type { ApprovalPayload } from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export type ChatResponse = {
  reply: string;
  intent: string;
  tool_used?: string | null;
  requires_approval?: boolean;
  approval_payload?: ApprovalPayload;
};

export async function sendChat(userId: string, message: string): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      user_id: userId,
      message,
    }),
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(err);
  }

  return res.json();
}

export async function sendApproval(userId: string, approved: boolean): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat/approve`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      user_id: userId,
      approved,
    }),
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(err);
  }

  return res.json();
}

export function getGoogleAuthUrl(): string {
  return `${API_BASE}/auth/google/start`;
}

export type HistoryIndexResult = {
  status: string;
  messages_seen: number;
  messages_indexed: number;
  chunks_added: number;
  skipped_already_indexed: number;
};

/** POST /history/index — pull recent Gmail into the retrieval index. */
export async function indexHistory(userId: string): Promise<HistoryIndexResult> {
  const res = await fetch(`${API_BASE}/history/index`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId }),
  });
  if (!res.ok) {
    throw new Error(await res.text());
  }
  return res.json();
}

type StreamHandlers = {
  onToken: (t: string) => void;
  onFinal: (r: ChatResponse) => void;
  onError: (message: string) => void;
};

/** POST /chat/stream — streams the conversational reply token-by-token via SSE. */
export async function sendChatStream(
  userId: string,
  message: string,
  { onToken, onFinal, onError }: StreamHandlers,
): Promise<void> {
  const res = await fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, message }),
  });
  if (!res.ok || !res.body) {
    onError(await res.text());
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith("data:")) continue;
      const evt = JSON.parse(line.slice(5).trim());
      if (evt.type === "token") onToken(evt.content as string);
      else if (evt.type === "final") onFinal(evt as ChatResponse);
    }
  }
}