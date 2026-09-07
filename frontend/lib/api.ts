import type { ApprovalPayload } from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

/** Every call carries the session cookie. */
const withCreds: RequestInit = { credentials: "include" };

export type ChatResponse = {
  reply: string;
  intent: string;
  tool_used?: string | null;
  requires_approval?: boolean;
  approval_payload?: ApprovalPayload;
};

export type Me = {
  id: string;
  email: string | null;
  name: string | null;
  is_guest: boolean;
  google_connected: boolean;
};

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(await res.text());
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------- auth

export async function getMe(): Promise<Me | null> {
  const res = await fetch(`${API_BASE}/auth/me`, withCreds);
  if (!res.ok) return null;
  const body = (await res.json()) as { user: Me | null };
  return body.user;
}

export async function startGuest(): Promise<Me> {
  const res = await fetch(`${API_BASE}/auth/guest`, { method: "POST", ...withCreds });
  return jsonOrThrow<Me>(res);
}

export async function logout(): Promise<void> {
  await fetch(`${API_BASE}/auth/logout`, { method: "POST", ...withCreds });
}

export function getGoogleAuthUrl(): string {
  return `${API_BASE}/auth/google/start`;
}

// ---------------------------------------------------------------- chat

export async function sendChat(conversationId: string, message: string): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    ...withCreds,
    body: JSON.stringify({ user_id: conversationId, message }),
  });
  return jsonOrThrow<ChatResponse>(res);
}

export async function sendApproval(
  conversationId: string,
  approved: boolean,
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    ...withCreds,
    body: JSON.stringify({ user_id: conversationId, approved }),
  });
  return jsonOrThrow<ChatResponse>(res);
}

export type HistoryIndexResult = {
  status: string;
  messages_seen: number;
  messages_indexed: number;
  chunks_added: number;
  skipped_already_indexed: number;
};

/** POST /history/index — pull recent Gmail into the retrieval index. */
export async function indexHistory(): Promise<HistoryIndexResult> {
  const res = await fetch(`${API_BASE}/history/index`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    ...withCreds,
    body: "{}",
  });
  return jsonOrThrow<HistoryIndexResult>(res);
}

type StreamHandlers = {
  onToken: (t: string) => void;
  onFinal: (r: ChatResponse) => void;
  onError: (message: string) => void;
};

/** POST /chat/stream — streams the conversational reply token-by-token via SSE. */
export async function sendChatStream(
  conversationId: string,
  message: string,
  { onToken, onFinal, onError }: StreamHandlers,
): Promise<void> {
  const res = await fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    ...withCreds,
    body: JSON.stringify({ user_id: conversationId, message }),
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
