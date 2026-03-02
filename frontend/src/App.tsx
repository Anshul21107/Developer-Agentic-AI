import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import {
  createSession,
  deleteSession,
  fetchMessages,
  fetchDocuments,
  listSessions,
  uploadRagDocuments,
  streamChat,
  Message,
  Session,
  SessionDocument
} from "./services/api";

type StreamState = "idle" | "streaming";

type CodeProps = {
  inline?: boolean;
  className?: string;
  children?: ReactNode;
};

function CodeBlock({ inline, className, children }: CodeProps) {
  const code = String(children ?? "").replace(/\n$/, "");
  const languageMatch = /language-([\w-]+)/.exec(className ?? "");
  const language = languageMatch?.[1] ?? "text";
  const [copied, setCopied] = useState(false);

  if (inline) {
    return (
      <code className="rounded bg-slate-800/70 px-1.5 py-0.5 font-mono text-[0.85em] text-slate-100">
        {children}
      </code>
    );
  }

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="my-4 overflow-hidden rounded-xl border border-slate-800 bg-slate-950">
      <div className="flex items-center justify-between border-b border-slate-800 bg-slate-900/70 px-3 py-2 text-xs uppercase tracking-wide text-slate-300">
        <span className="font-semibold">{language}</span>
        <button
          type="button"
          onClick={handleCopy}
          className="rounded-md border border-slate-700 px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-slate-200 transition hover:border-slate-500 hover:text-white"
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <SyntaxHighlighter
        language={language}
        style={oneDark}
        customStyle={{
          margin: 0,
          background: "transparent",
          padding: "1rem"
        }}
        codeTagProps={{
          style: {
            background: "transparent"
          }
        }}
        wrapLongLines
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}

const markdownComponents = {
  code: CodeBlock,
  pre: ({ children }: { children?: ReactNode }) => <>{children}</>,
  h1: ({ children }: { children?: ReactNode }) => (
    <h1 className="mb-3 mt-4 text-2xl font-semibold text-slate-100">
      {children}
    </h1>
  ),
  h2: ({ children }: { children?: ReactNode }) => (
    <h2 className="mb-3 mt-4 text-xl font-semibold text-slate-100">
      {children}
    </h2>
  ),
  h3: ({ children }: { children?: ReactNode }) => (
    <h3 className="mb-2 mt-3 text-lg font-semibold text-slate-100">
      {children}
    </h3>
  ),
  p: ({ children }: { children?: ReactNode }) => (
    <p className="my-3 leading-relaxed text-slate-100">{children}</p>
  ),
  ul: ({ children }: { children?: ReactNode }) => (
    <ul className="my-3 list-disc space-y-2 pl-5 text-slate-100">
      {children}
    </ul>
  ),
  ol: ({ children }: { children?: ReactNode }) => (
    <ol className="my-3 list-decimal space-y-2 pl-5 text-slate-100">
      {children}
    </ol>
  ),
  li: ({ children }: { children?: ReactNode }) => (
    <li className="leading-relaxed">{children}</li>
  ),
  a: ({ children, href }: { children?: ReactNode; href?: string }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="text-cyan-300 underline decoration-cyan-400/60 underline-offset-4 transition hover:text-cyan-200"
    >
      {children}
    </a>
  )
};

export default function App() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [documents, setDocuments] = useState<SessionDocument[]>([]);
  const [input, setInput] = useState("");
  const [streamState, setStreamState] = useState<StreamState>("idle");
  const [streamBuffer, setStreamBuffer] = useState("");
  const [streamAgent, setStreamAgent] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);
  const [showDocuments, setShowDocuments] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [greeting, setGreeting] = useState("day");
  const [deleteTarget, setDeleteTarget] = useState<Session | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const streamBufferRef = useRef("");
  const streamAgentRef = useRef<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const istFormatter = useMemo(
    () =>
      new Intl.DateTimeFormat("en-IN", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: "Asia/Kolkata"
      }),
    []
  );

  const activeSession = useMemo(
    () => sessions.find((session) => session.id === activeSessionId) ?? null,
    [sessions, activeSessionId]
  );

  useEffect(() => {
    listSessions()
      .then((data) => {
        setSessions(data);
        if (data.length > 0) {
          setActiveSessionId(data[0].id);
        }
      })
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    if (!activeSessionId) {
      setMessages([]);
      setDocuments([]);
      return;
    }
    fetchMessages(activeSessionId)
      .then(setMessages)
      .catch((err) => setError(err.message));
    fetchDocuments(activeSessionId)
      .then(setDocuments)
      .catch((err) => setError(err.message));
  }, [activeSessionId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamBuffer]);

  useEffect(() => {
    const formatter = new Intl.DateTimeFormat("en-US", {
      hour: "numeric",
      hour12: false,
      timeZone: "Asia/Kolkata"
    });
    const hour = Number(formatter.format(new Date()));
    if (hour >= 5 && hour < 12) {
      setGreeting("Morning");
    } else if (hour >= 12 && hour < 17) {
      setGreeting("Afternoon");
    } else {
      setGreeting("Evening");
    }
  }, []);
  const handleNewChat = async () => {
    setError(null);
    setActiveSessionId(null);
    setMessages([]);
    setDocuments([]);
    setStreamBuffer("");
    setStreamAgent(null);
    setShowDocuments(false);
    streamBufferRef.current = "";
    streamAgentRef.current = null;
  };

  const handleSelectSession = (sessionId: string) => {
    if (streamState === "streaming") return;
    setActiveSessionId(sessionId);
    setStreamBuffer("");
  };

  const handleDeleteClick = (
    event: React.MouseEvent<HTMLButtonElement>,
    session: Session
  ) => {
    event.stopPropagation();
    if (streamState === "streaming") return;
    setDeleteTarget(session);
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    setIsDeleting(true);
    try {
      await deleteSession(deleteTarget.id);
      setSessions((prev) => prev.filter((item) => item.id !== deleteTarget.id));
      if (activeSessionId === deleteTarget.id) {
        setActiveSessionId(null);
        setMessages([]);
      }
      setDeleteTarget(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIsDeleting(false);
    }
  };
  const handleSend = async () => {
    if (!input.trim() || streamState === "streaming") return;
    const content = input.trim();
    setInput("");
    setError(null);
    setStreamBuffer("");
    setStreamAgent(null);
    streamBufferRef.current = "";
    streamAgentRef.current = null;
    setStreamState("streaming");

    let sessionId = activeSessionId;
    if (!sessionId) {
      try {
        const session = await createSession();
        sessionId = session.id;
        setSessions((prev) => [session, ...prev]);
        setActiveSessionId(session.id);
      } catch (err) {
        setStreamState("idle");
        setError((err as Error).message);
        return;
      }
    }
    if (!sessionId) {
      setStreamState("idle");
      setError("No session available.");
      return;
    }
    const finalSessionId = sessionId;

    const tempMessage: Message = {
      id: crypto.randomUUID(),
      session_id: finalSessionId,
      role: "user",
      content,
      timestamp: new Date().toISOString()
    };
    setMessages((prev) => [...prev, tempMessage]);

    await streamChat(finalSessionId, content, {
      onAgent: (agent) => {
        setStreamAgent(agent);
        streamAgentRef.current = agent;
      },
      onToken: (token) => {
        streamBufferRef.current += token;
        setStreamBuffer(streamBufferRef.current);
      },
      onDone: () => {
        setStreamState("idle");
        if (streamBufferRef.current.trim().length > 0) {
          const assistantMessage: Message = {
            id: crypto.randomUUID(),
            session_id: finalSessionId,
            role: "assistant",
            content: streamBufferRef.current,
            agent: streamAgentRef.current ?? null,
            timestamp: new Date().toISOString()
          };
          setMessages((prev) => [...prev, assistantMessage]);
          setStreamBuffer("");
          setStreamAgent(null);
          streamBufferRef.current = "";
          streamAgentRef.current = null;
        }
        listSessions()
          .then(setSessions)
          .catch((err) => setError(err.message));
      },
      onError: (err) => {
        setStreamState("idle");
        setError(err.message);
      }
    });
  };

  const handleUploadClick = () => {
    if (isUploading || streamState === "streaming") return;
    fileInputRef.current?.click();
  };

  const handleUploadChange = async (
    event: React.ChangeEvent<HTMLInputElement>
  ) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;
    setIsUploading(true);
    setUploadStatus(null);
    try {
      let sessionId = activeSessionId;
      if (!sessionId) {
        const session = await createSession();
        sessionId = session.id;
        setSessions((prev) => [session, ...prev]);
        setActiveSessionId(session.id);
      }
      if (!sessionId) {
        throw new Error("No session available for upload.");
      }
      const fileNames = Array.from(files).map((file) => file.name);
      const result = await uploadRagDocuments(sessionId, files);
      if (result.status === "ok") {
        const refreshed = await fetchDocuments(sessionId);
        setDocuments(refreshed);
      }
    } catch (err) {
      setUploadStatus((err as Error).message);
    } finally {
      setIsUploading(false);
      event.target.value = "";
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void handleSend();
    }
  };

  return (
    <div className="h-screen w-full">
      <div className="flex h-full">
        <aside className="flex h-full w-80 flex-col border-r border-slate-800 bg-slate-950/80 p-6 backdrop-blur">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="font-display text-xl font-semibold text-slate-100">
                Agentic Chatbot
              </h1>
            </div>
          </div>
          <button
            onClick={handleNewChat}
            className="mt-4 flex items-center justify-center gap-2 rounded-full border border-slate-700 bg-slate-900 px-3 py-2 text-xs font-semibold uppercase tracking-widest text-slate-200 transition hover:border-slate-500 hover:text-white"
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="h-4 w-4"
            >
              <path d="M12 5v14" />
              <path d="M5 12h14" />
            </svg>
            New Chat
          </button>
          <p className="mt-4 text-xs uppercase tracking-[0.2em] text-slate-400">
            Your chats
          </p>
          <div className="mt-3 flex-1 overflow-y-auto pr-1">
            <div className="space-y-2 pb-4">
              {sessions.map((session) => {
                const isActive = session.id === activeSessionId;
                return (
                  <button
                    key={session.id}
                    onClick={() => handleSelectSession(session.id)}
                    className={`w-full rounded-xl border px-4 py-3 text-left transition ${
                      isActive
                        ? "border-cyan-400/60 bg-cyan-500/10 text-cyan-100"
                        : "border-slate-800 bg-slate-900/40 text-slate-300 hover:border-slate-700 hover:text-white"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold">
                          {session.title || "Untitled Chat"}
                        </p>
                        <p className="mt-1 text-xs text-slate-400">
                          {istFormatter.format(new Date(session.created_at))}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={(event) => handleDeleteClick(event, session)}
                        className="rounded-full border border-transparent p-1 text-rose-300 transition hover:border-rose-500/60 hover:bg-rose-500/10 hover:text-rose-200"
                        aria-label="Delete chat"
                      >
                        <svg
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          className="h-4 w-4"
                        >
                          <path d="M3 6h18" />
                          <path d="M8 6V4h8v2" />
                          <path d="m19 6-1 14H6L5 6" />
                          <path d="M10 11v6" />
                          <path d="M14 11v6" />
                        </svg>
                      </button>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
          <div className="pt-6 ml-8 text-xs italic text-slate-400">
            <span className="inline-flex items-center gap-2">
              Made with
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="h-4 w-4 text-rose-400"
                aria-hidden="true"
              >
                <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
              </svg>
              by Anshul
            </span>
          </div>
        </aside>

        <main className="flex flex-1 flex-col">
          <header className="border-b border-slate-800 px-8 py-4" />

          <section className="flex-1 overflow-y-auto px-6 py-6">
            {messages.length === 0 && streamBuffer.length === 0 ? (
              <div className="mx-auto mt-12 max-w-3xl p-10 text-slate-300">
                <h3 className="text-center font-display text-4xl font-semibold text-slate-100">
                  Good {greeting}! Ask anything
                </h3>
              </div>
            ) : (
              <div className="mx-auto max-w-3xl space-y-6">
                {messages.map((message) => (
                  <div
                    key={message.id}
                    className={`flex w-full ${
                      message.role === "user" ? "justify-end" : "justify-start"
                    }`}
                  >
                    <div className="max-w-[80%]">
                      {message.role === "assistant" && message.agent && message.agent !== "orchestrator" && (
                        <div className="mb-2 inline-flex items-center rounded-full border border-cyan-500/30 bg-cyan-500/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-widest text-cyan-200">
                          {message.agent.replace(/_/g, " ")}
                        </div>
                      )}
                      <div
                        className={`rounded-2xl border px-6 py-4 text-sm leading-relaxed ${
                          message.role === "user"
                            ? "border-cyan-500/40 bg-cyan-500/10 text-cyan-50"
                            : "border-slate-800 bg-slate-900/50 text-slate-200"
                        }`}
                      >
                        {message.role === "assistant" ? (
                          <ReactMarkdown
                            className="markdown"
                            components={markdownComponents}
                          >
                            {message.content}
                          </ReactMarkdown>
                        ) : (
                          <p className="whitespace-pre-wrap">{message.content}</p>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
                {streamBuffer && (
                  <div className="flex w-full justify-start">
                    <div className="max-w-[80%]">
                      {streamAgent && streamAgent !== "orchestrator" && (
                        <div className="mb-2 inline-flex items-center rounded-full border border-cyan-500/30 bg-cyan-500/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-widest text-cyan-200">
                          {streamAgent.replace(/_/g, " ")}
                        </div>
                      )}
                      <div className="rounded-2xl border border-slate-800 bg-slate-900/50 px-6 py-4 text-sm leading-relaxed text-slate-200">
                      <ReactMarkdown
                        className="markdown"
                        components={markdownComponents}
                      >
                        {streamBuffer}
                      </ReactMarkdown>
                      <span className="ml-1 inline-block h-4 w-2 animate-pulse rounded bg-cyan-400 align-middle" />
                      </div>
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>
            )}
          </section>

          <footer className="border-t border-slate-800 px-6 py-6">
            {error && (
              <div className="mb-3 rounded-xl border border-rose-500/40 bg-rose-500/10 px-4 py-2 text-xs text-rose-200">
                {error}
              </div>
            )}
            {documents.length > 0 && (
              <div className="mb-3 inline-block rounded-xl border border-slate-800 bg-slate-900/40 px-4 py-2 text-xs text-slate-300">
                <button
                  type="button"
                  onClick={() => setShowDocuments((prev) => !prev)}
                  className="flex w-full items-center justify-between text-[11px] font-semibold uppercase tracking-widest text-slate-300"
                  aria-label={showDocuments ? "Hide documents" : "Show documents"}
                  title={showDocuments ? "Hide documents" : "Show documents"}
                >
                  <span>Documents ({documents.length})</span>
                  <span className="ml-3 text-slate-400">
                    {showDocuments ? (
                      <svg
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        className="h-4 w-4"
                      >
                        <path d="M17.94 17.94A10.94 10.94 0 0 1 12 20c-5 0-9.27-3.11-11-8a11.04 11.04 0 0 1 5.06-5.94" />
                        <path d="M1 1l22 22" />
                        <path d="M9.9 4.24A10.94 10.94 0 0 1 12 4c5 0 9.27 3.11 11 8a11.04 11.04 0 0 1-4.2 5.37" />
                        <path d="M9.88 9.88a3 3 0 1 0 4.24 4.24" />
                      </svg>
                    ) : (
                      <svg
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        className="h-4 w-4"
                      >
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                        <circle cx="12" cy="12" r="3" />
                      </svg>
                    )}
                  </span>
                </button>
                {showDocuments && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {documents.map((doc) => (
                      <span
                        key={doc.id}
                        className="rounded-full border border-slate-700 bg-slate-900/70 px-3 py-1 text-[11px] text-slate-200"
                      >
                        {doc.filename}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}
            <div className="mx-auto w-full max-w-3xl">
              <div className="relative">
                <button
                  type="button"
                  onClick={handleUploadClick} 
                  className="absolute left-2 top-1/2 flex h-8 w-8 -translate-y-5 items-center justify-center rounded-full border border-slate-800 bg-slate-900/70 text-slate-300 transition hover:border-slate-600 hover:text-white"
                  aria-label="Attach documents"
                  title="Attach documents"
                  disabled={isUploading}
                >
                  {isUploading ? (
                    <span className="h-2 w-2 animate-pulse rounded-full bg-cyan-300" />
                  ) : (
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      className="h-4 w-4"
                    >
                      <path d="M12 5v14" />
                      <path d="M5 12h14" />
                    </svg>
                  )}
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".txt,.md,.pdf"
                  multiple
                  onChange={handleUploadChange}
                  className="hidden"
                />
                <textarea
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Send a message..."
                  rows={1}
                  className="w-full resize-none rounded-2xl border border-slate-800 bg-slate-900/70 px-14 py-3 pr-12 text-sm text-slate-100 shadow-lg shadow-slate-950/40 outline-none transition focus:border-cyan-500/60 min-h-12"
                />
                <button
                  onClick={handleSend}
                  disabled={streamState === "streaming"}
                  aria-label="Send message"
                  className="absolute right-2 top-1/2 flex h-8 w-8 -translate-y-5 items-center justify-center rounded-full border border-cyan-500/60 bg-cyan-500/20 text-cyan-100 transition hover:bg-cyan-500/30 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {streamState === "streaming" ? (
                    <span className="h-2 w-2 animate-pulse rounded-full bg-cyan-300" />
                  ) : (
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      className="h-5 w-5"
                    >
                      <path d="M5 12h14" />
                      <path d="m12 5 7 7-7 7" />
                    </svg>
                  )}
                </button>
              </div>
            </div>
          </footer>
        </main>
      </div>
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 px-6 backdrop-blur">
          <div className="w-full max-w-md rounded-2xl border border-rose-500/30 bg-slate-900/90 p-6 text-slate-100 shadow-xl">
            <h3 className="text-lg font-semibold">Delete this chat?</h3>
            <p className="mt-2 text-sm text-slate-300">
              This will permanently delete all messages in this session. This
              action cannot be undone.
            </p>
            <div className="mt-6 flex items-center justify-end gap-3">
              <button
                onClick={() => setDeleteTarget(null)}
                className="rounded-full border border-slate-700 px-4 py-2 text-xs font-semibold uppercase tracking-widest text-slate-300 transition hover:border-slate-500 hover:text-white"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmDelete}
                disabled={isDeleting}
                className="rounded-full border border-rose-500/60 bg-rose-500/15 px-4 py-2 text-xs font-semibold uppercase tracking-widest text-rose-200 transition hover:bg-rose-500/25 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isDeleting ? "Deleting" : "Ok"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
