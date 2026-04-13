const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export type ChatResponse = {
  reply: string;
  intent: string;
  tool_used?: string | null;
  requires_approval?: boolean;
  approval_payload?: any;
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