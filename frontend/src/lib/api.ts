import type { ChatRequestBody, Artifact, Meeting, Stats, Topic, Me, Member, Role, Conversation } from "./types";

export const API_BASE =
  typeof window !== "undefined" && window.location.hostname === "localhost"
    ? "http://localhost:8000"
    : "";

function authHeaders(token: string): Record<string, string> {
  return { "x-firebase-auth": token };
}

export async function fetchMeetings(token: string): Promise<Meeting[]> {
  const res = await fetch(`${API_BASE}/api/meetings`, { headers: authHeaders(token) });
  if (!res.ok) return [];
  const data = await res.json();
  return (data.meetings || []) as Meeting[];
}

export async function fetchStats(token: string): Promise<Stats | null> {
  const res = await fetch(`${API_BASE}/api/stats`, { headers: authHeaders(token) });
  if (!res.ok) return null;
  return (await res.json()) as Stats;
}

export async function fetchTopics(token: string): Promise<Topic[]> {
  const res = await fetch(`${API_BASE}/api/topics`, { headers: authHeaders(token) });
  if (!res.ok) return [];
  const data = await res.json();
  return (data.topics || []) as Topic[];
}

export async function fetchMe(token: string): Promise<Me | null> {
  const res = await fetch(`${API_BASE}/api/me`, { headers: authHeaders(token) });
  if (!res.ok) return null;
  return (await res.json()) as Me;
}

export async function fetchMembers(token: string): Promise<Member[]> {
  const res = await fetch(`${API_BASE}/api/admin/members`, { headers: authHeaders(token) });
  if (!res.ok) throw new Error(`Failed to load members (${res.status}).`);
  const data = await res.json();
  return (data.members || []) as Member[];
}

export async function addMember(token: string, email: string, role: Role): Promise<void> {
  const res = await fetch(`${API_BASE}/api/admin/members`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ email, role }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `Failed to add member (${res.status}).`);
  }
}

export async function removeMember(token: string, email: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/admin/members/${encodeURIComponent(email)}`, {
    method: "DELETE",
    headers: authHeaders(token),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `Failed to remove member (${res.status}).`);
  }
}

// --- Conversations ---
export async function createConversation(token: string, title?: string): Promise<string> {
  const res = await fetch(`${API_BASE}/api/conversations`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ title: title ?? null }),
  });
  if (!res.ok) throw new Error(`Failed to create conversation (${res.status}).`);
  const data = await res.json();
  return data.id as string;
}

export async function listConversations(token: string): Promise<Conversation[]> {
  const res = await fetch(`${API_BASE}/api/conversations`, { headers: authHeaders(token) });
  if (!res.ok) return [];
  const data = await res.json();
  return (data.conversations || []) as Conversation[];
}

export async function deleteConversation(token: string, id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/conversations/${encodeURIComponent(id)}`, {
    method: "DELETE",
    headers: authHeaders(token),
  });
  if (!res.ok) throw new Error(`Failed to delete conversation (${res.status}).`);
}

export async function shareConversation(token: string, id: string, email: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/conversations/${encodeURIComponent(id)}/share`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ email }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `Failed to share (${res.status}).`);
  }
}

export async function unshareConversation(token: string, id: string, email: string): Promise<void> {
  const res = await fetch(
    `${API_BASE}/api/conversations/${encodeURIComponent(id)}/share/${encodeURIComponent(email)}`,
    { method: "DELETE", headers: authHeaders(token) },
  );
  if (!res.ok) throw new Error(`Failed to unshare (${res.status}).`);
}

export interface StreamHandlers {
  onToken: (delta: string) => void;
  onArtifact: (payload: Artifact) => void;
  onError: (message: string) => void;
}

/**
 * POST /api/chat and consume the SSE stream. Frames are separated by a blank line;
 * each carries a single `data:` JSON event (token / artifact / error / done).
 * Uses an idle timeout (aborts only if the stream stalls for 45s) rather than a hard cap,
 * so long-but-healthy responses are not cut off.
 */
export async function streamChat(
  token: string,
  body: ChatRequestBody,
  handlers: StreamHandlers,
): Promise<void> {
  const controller = new AbortController();
  let idleTimer: ReturnType<typeof setTimeout> = setTimeout(() => controller.abort(), 45000);
  const resetIdle = () => {
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => controller.abort(), 45000);
  };

  try {
    const response = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-firebase-auth": token },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    if (!response.ok || !response.body) {
      throw new Error(`API request failed (${response.status}).`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let streamErr: string | null = null;

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      resetIdle();
      buffer += decoder.decode(value, { stream: true });

      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        const dataLine = frame.split("\n").find((l) => l.startsWith("data:"));
        if (!dataLine) continue;
        let evt: { type?: string; text?: string; payload?: Artifact; message?: string };
        try {
          evt = JSON.parse(dataLine.slice(5).trim());
        } catch {
          continue;
        }
        if (evt.type === "token") {
          handlers.onToken(evt.text || "");
        } else if (evt.type === "artifact" && evt.payload) {
          handlers.onArtifact(evt.payload);
        } else if (evt.type === "error") {
          streamErr = evt.message || "The assistant hit an error.";
        }
      }
    }

    if (streamErr) handlers.onError(streamErr);
  } catch (err: unknown) {
    if (err instanceof Error && err.name === "AbortError") {
      handlers.onError("The request timed out. Please try again.");
    } else {
      console.error("Chat error:", err);
      handlers.onError("Couldn't reach the assistant. Check your connection and try again.");
    }
  } finally {
    clearTimeout(idleTimer);
  }
}
