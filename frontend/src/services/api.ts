const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const WS_URL = import.meta.env.VITE_WS_URL ?? "ws://localhost:8000";

export type Session = {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string | null;
};

export type Message = {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  agent?: string | null;
  timestamp: string;
};

export type SessionDocument = {
  id: string;
  session_id: string;
  filename: string;
  uploaded_at: string;
};

// ---------------------------------------------------------------------------
// REST endpoints (unchanged)
// ---------------------------------------------------------------------------

export async function createSession(): Promise<Session> {
  const res = await fetch(`${API_URL}/sessions`, { method: "POST" });
  if (!res.ok) {
    throw new Error("Failed to create session");
  }
  return res.json();
}

export async function listSessions(): Promise<Session[]> {
  const res = await fetch(`${API_URL}/sessions`);
  if (!res.ok) {
    throw new Error("Failed to load sessions");
  }
  return res.json();
}

export async function fetchMessages(sessionId: string): Promise<Message[]> {
  const res = await fetch(`${API_URL}/sessions/${sessionId}/messages`);
  if (!res.ok) {
    throw new Error("Failed to load messages");
  }
  return res.json();
}

export async function fetchDocuments(
  sessionId: string
): Promise<SessionDocument[]> {
  const res = await fetch(`${API_URL}/sessions/${sessionId}/documents`);
  if (!res.ok) {
    throw new Error("Failed to load documents");
  }
  return res.json();
}

export async function deleteSession(sessionId: string): Promise<void> {
  const res = await fetch(`${API_URL}/sessions/${sessionId}`, {
    method: "DELETE"
  });
  if (!res.ok) {
    throw new Error("Failed to delete session");
  }
}

export async function uploadRagDocuments(
  sessionId: string,
  files: FileList | File[]
): Promise<{
  status: string;
  skipped: string[];
  chunks: number;
}> {
  const formData = new FormData();
  formData.append("session_id", sessionId);
  Array.from(files).forEach((file) => {
    formData.append("files", file);
  });
  const res = await fetch(`${API_URL}/rag/upload`, {
    method: "POST",
    body: formData
  });
  if (!res.ok) {
    throw new Error("Failed to upload documents");
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// WebSocket
// ---------------------------------------------------------------------------

export function connectWebSocket(sessionId: string): WebSocket {
  return new WebSocket(`${WS_URL}/ws/chat/${sessionId}`);
}

export type WsEvent =
  | { type: "assistant_start" }
  | { type: "assistant_token"; content: string }
  | { type: "assistant_end"; agent: string };

export function sendMessage(ws: WebSocket, content: string): void {
  ws.send(JSON.stringify({ type: "user_message", content }));
}
