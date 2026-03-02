const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export type Session = {
  id: string;
  title: string | null;
  created_at: string;
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

type StreamHandlers = {
  onToken: (token: string) => void;
  onDone: () => void;
  onError: (error: Error) => void;
  onAgent?: (agent: string) => void;
};

export async function streamChat(
  sessionId: string,
  message: string,
  handlers: StreamHandlers
) {
  try {
    const res = await fetch(`${API_URL}/chat/${sessionId}/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ message })
    });

    if (!res.ok || !res.body) {
      throw new Error("Failed to start stream");
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop() ?? "";

      for (const event of events) {
        const line = event.split("\n").find((item) => item.startsWith("data: "));
        if (!line) continue;
        const data = line.replace("data: ", "").trim();
        if (data === "[DONE]") {
          handlers.onDone();
          return;
        }
        try {
          const payload = JSON.parse(data) as { token?: string; agent?: string };
          if (payload.agent && handlers.onAgent) {
            handlers.onAgent(payload.agent);
          }
          if (payload.token) {
            handlers.onToken(payload.token);
          }
        } catch (err) {
          handlers.onError(new Error("Invalid stream payload"));
        }
      }
    }

    handlers.onDone();
  } catch (err) {
    handlers.onError(err as Error);
  }
}
