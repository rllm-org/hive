"use client";

import { useState, useRef, useCallback, useEffect, KeyboardEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const MOCK_MESSAGES: Array<{ role: string; content: string; streaming?: boolean; parts?: Array<{ type: string; content?: string; name?: string; status?: string; title?: string; input?: unknown; output?: unknown }> }> = [
  { role: "user", content: "Can you help me build a REST API?" },
  { role: "assistant", content: "Sure! What language and framework would you like to use?\n\n- **Python** (FastAPI, Flask, Django)\n- **TypeScript** (Express, Fastify, Hono)\n- **Go** (Gin, Echo, Chi)" },
  { role: "user", content: "Let's go with FastAPI" },
  {
    role: "assistant",
    content: "Let me set up the project structure.\n\nProject created. Should I add authentication?",
    parts: [
      { type: "thinking", content: "The user wants FastAPI. I'll create a basic project structure with app/main.py containing a simple FastAPI app with one route." },
      { type: "text", content: "Let me set up the project structure." },
      { type: "tool", name: "Bash", status: "done", title: "mkdir -p app && touch app/main.py", input: { command: "mkdir -p app && touch app/main.py" }, output: "" },
      { type: "tool", name: "Edit", status: "done", title: "Write app/main.py", input: { file_path: "app/main.py", content: "from fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get('/')\ndef root():\n    return {'message': 'Hello World'}" }, output: "File written successfully" },
      { type: "text", content: "Project created. Should I add authentication?" },
    ],
  },
  { role: "user", content: "Yes, add JWT auth and PostgreSQL" },
  {
    role: "assistant",
    content: "I'll set up the auth module.\n\nDone! JWT auth and PostgreSQL are configured.",
    parts: [
      { type: "thinking", content: "Need three things: JWT auth module with python-jose, database setup with asyncpg + SQLAlchemy, and install the dependencies. I'll create separate files for auth and database, then pip install." },
      { type: "text", content: "I'll set up the auth module." },
      { type: "tool", name: "Edit", status: "done", title: "Write app/auth.py — JWT token creation and verification" },
      { type: "tool", name: "Edit", status: "done", title: "Write app/database.py — SQLAlchemy + asyncpg setup" },
      { type: "tool", name: "Bash", status: "done", title: "pip install python-jose asyncpg sqlalchemy" },
      { type: "text", content: "Done! JWT auth and PostgreSQL are configured." },
    ],
  },
  { role: "user", content: "Sounds good, go ahead" },
];

const VALID_COMMAND_NAMES = new Set(["hive", "commit", "debug", "compact", "review-pr", "simplify", "help"]);

function HighlightSlash({ text, validCommands }: { text: string; validCommands?: Set<string> }) {
  const valid = validCommands ?? VALID_COMMAND_NAMES;
  return (
    <>
      {text.split(/((?:^|(?<=\s))\/[\w:-]+)/).map((part, i) =>
        /^\/[\w:-]+$/.test(part) && valid.has(part.slice(1))
          ? <span key={i} className="text-[var(--color-accent)]">{part}</span>
          : <span key={i}>{part}</span>
      )}
    </>
  );
}

function ToolCard({ part }: { part: { name?: string; title?: string; input?: unknown; output?: unknown } }) {
  const [open, setOpen] = useState(false);
  const name = part.name ?? "";
  const hasDetails = part.input != null || part.output != null;
  const fmt = (v: unknown) => {
    if (v == null) return "";
    if (typeof v === "string") return v;
    try { return JSON.stringify(v, null, 2); } catch { return String(v); }
  };
  return (
    <div className="border border-[var(--color-border)] bg-[var(--color-surface)] text-xs" style={{ borderRadius: 8 }}>
      <button
        type="button"
        onClick={() => hasDetails && setOpen(!open)}
        className={`group/tc w-full flex items-center gap-2 px-3 py-1.5 text-left ${hasDetails ? "cursor-pointer hover:bg-[var(--color-layer-1)]" : "cursor-default"}`}
        style={{ borderRadius: open ? "8px 8px 0 0" : 8 }}
      >
        <svg className="w-3.5 h-3.5 shrink-0 text-[var(--color-text-tertiary)]" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={1.5}>
          {name === "Bash" ? (
            <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 7.5l3 2.25-3 2.25m4.5 0h3m-9 8.25h13.5A2.25 2.25 0 0021 18V6a2.25 2.25 0 00-2.25-2.25H5.25A2.25 2.25 0 003 6v12a2.25 2.25 0 002.25 2.25z" />
          ) : (
            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
          )}
        </svg>
        <span className="truncate text-[var(--color-text-secondary)]">{part.title || name}</span>
        {hasDetails && (
          <svg className={`ml-auto w-3 h-3 shrink-0 text-[var(--color-text-tertiary)] transition-all ${open ? "rotate-180 opacity-100" : "opacity-0 group-hover/tc:opacity-100"}`} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        )}
      </button>
      {open && (
        <div className="border-t border-[var(--color-border)] px-3 py-2 space-y-2">
          {part.input != null && (
            <div>
              <div className="text-[10px] uppercase tracking-wide text-[var(--color-text-tertiary)] mb-0.5">input</div>
              <pre className="whitespace-pre-wrap break-all font-[family-name:var(--font-ibm-plex-mono)] text-[11px] leading-snug max-h-40 overflow-y-auto text-[var(--color-text)]">{fmt(part.input)}</pre>
            </div>
          )}
          {part.output != null && (
            <div>
              <div className="text-[10px] uppercase tracking-wide text-[var(--color-text-tertiary)] mb-0.5">output</div>
              <pre className="whitespace-pre-wrap break-all font-[family-name:var(--font-ibm-plex-mono)] text-[11px] leading-snug max-h-40 overflow-y-auto text-[var(--color-text)]">{fmt(part.output)}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function PreviewThinkingBlock({ content, active }: { content: string; active: boolean }) {
  const [manualToggle, setManualToggle] = useState<boolean | null>(null);
  const startRef = useRef<number | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (active && startRef.current === null) startRef.current = Date.now();
    if (!active && startRef.current !== null) {
      setElapsed(Math.round((Date.now() - startRef.current) / 1000));
      startRef.current = null;
    }
  }, [active]);

  useEffect(() => {
    if (!active) return;
    const interval = setInterval(() => {
      if (startRef.current) setElapsed(Math.round((Date.now() - startRef.current) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, [active]);

  // Auto-scroll thinking content to bottom while streaming
  useEffect(() => {
    if (active && contentRef.current) {
      contentRef.current.scrollTop = contentRef.current.scrollHeight;
    }
  }, [active, content]);

  const isOpen = manualToggle ?? active;
  const label = active ? "Thinking" : elapsed > 0 ? `Thought for ${elapsed}s` : "Thought";

  return (
    <div className="group/th">
      <button
        type="button"
        onClick={() => setManualToggle(isOpen ? false : true)}
        className="flex items-center gap-1.5 text-sm text-[var(--color-text-tertiary)] cursor-pointer hover:text-[var(--color-text-secondary)]"
      >
        <span className={active ? "shimmer-text" : ""}>{label}</span>
        <svg className={`w-3 h-3 transition-all opacity-0 group-hover/th:opacity-100 ${isOpen ? "rotate-180" : ""}`} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {isOpen && (
        <div ref={contentRef} className="mt-1 whitespace-pre-wrap text-sm leading-relaxed max-h-60 overflow-y-auto text-[var(--color-text-tertiary)]">
          {content}
        </div>
      )}
    </div>
  );
}

function MessageBubble({ msg }: { msg: typeof MOCK_MESSAGES[number] }) {
  if (msg.role === "user") {
    return (
      <div className="w-full px-3 py-2 bg-white dark:bg-[var(--color-layer-2)] shadow-sm text-[var(--color-text)]" style={{ borderRadius: 10 }}>
        <p className="text-sm whitespace-pre-wrap"><HighlightSlash text={msg.content} /></p>
      </div>
    );
  }
  if (msg.parts && msg.parts.length > 0) {
    return (
      <div className="w-full pl-4 space-y-1.5">
        {msg.parts.map((part, i) => {
          const isActiveThinking = part.type === "thinking" && !!msg.streaming && i === (msg.parts?.length ?? 0) - 1;
          return part.type === "text" ? (
            <div key={i} className="prose prose-sm max-w-none text-[var(--color-text)]">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{part.content ?? ""}</ReactMarkdown>
            </div>
          ) : part.type === "thinking" ? (
            <PreviewThinkingBlock key={i} content={part.content ?? ""} active={isActiveThinking} />
          ) : (
            <ToolCard key={i} part={part} />
          );
        })}
      </div>
    );
  }
  return (
    <div className="w-full pl-4 prose prose-sm max-w-none text-[var(--color-text)]">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
    </div>
  );
}

export default function ChatPreview() {
  const [messages, setMessages] = useState(MOCK_MESSAGES);
  const [input, setInput] = useState("");
  const [cmdIndex, setCmdIndex] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const latestUserRef = useRef<HTMLDivElement>(null);
  const spacerRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const prevCountRef = useRef(messages.length);
  const hasAnimatedInitial = useRef(false);

  const MOCK_COMMANDS = [
    { name: "hive", description: "Run the hive experiment loop — autonomous iteration on a shared task, with continuous chat-based collaboration and leaderboard tracking" },
    { name: "commit", description: "Stage and commit changes" },
    { name: "debug", description: "Run failing command and diagnose" },
    { name: "compact", description: "Compact conversation history" },
    { name: "review-pr", description: "Review a pull request" },
    { name: "simplify", description: "Review code for quality" },
    { name: "help", description: "Get help with commands" },
  ];

  // Detect "/" trigger anywhere in text — use the word being typed at cursor
  const getSlashWord = () => {
    const ta = textareaRef.current;
    if (!ta) return "";
    const pos = ta.selectionStart ?? input.length;
    const before = input.slice(0, pos);
    const match = before.match(/\/([^\s]*)$/);
    return match ? match[0] : "";
  };
  const slashWord = getSlashWord();
  const showCommands = slashWord.length > 0 && MOCK_COMMANDS.length > 0;
  const filteredCommands = showCommands
    ? MOCK_COMMANDS.filter((c) => `/${c.name}`.startsWith(slashWord.toLowerCase()))
    : [];

  const resizeTextarea = useCallback(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
    ta.style.overflowY = ta.scrollHeight > 200 ? "auto" : "hidden";
  }, []);

  useEffect(() => { resizeTextarea(); }, [input, resizeTextarea]);

  const lastUserIdx = messages.reduce((acc, msg, i) => msg.role === "user" ? i : acc, -1);

  const updateSpacer = useCallback(() => {
    const container = scrollRef.current;
    const userEl = latestUserRef.current;
    const spacer = spacerRef.current;
    const contentEl = contentRef.current;
    if (!container || !userEl || !spacer || !contentEl) return;
    spacer.style.height = "0px";
    const contentHeight = contentEl.scrollHeight;
    const userOffset = userEl.offsetTop - contentEl.offsetTop;
    const contentFromUser = contentHeight - userOffset;
    const containerPadding = parseFloat(getComputedStyle(container).paddingTop) + parseFloat(getComputedStyle(container).paddingBottom);
    const needed = Math.max(0, container.clientHeight - contentFromUser - containerPadding);
    spacer.style.height = needed + "px";
  }, []);


  const scrollToUser = useCallback(() => {
    updateSpacer();
    if (latestUserRef.current) {
      latestUserRef.current.scrollIntoView({ block: "start" });
    }
  }, [updateSpacer]);

  const prevLastUserIdxRef = useRef(lastUserIdx);
  useEffect(() => {
    updateSpacer();
    const isNewUserMsg = lastUserIdx !== prevLastUserIdxRef.current;
    prevLastUserIdxRef.current = lastUserIdx;
    if (isNewUserMsg) {
      requestAnimationFrame(() => {
        updateSpacer();
        scrollToUser();
      });
    }
  }, [messages, lastUserIdx, scrollToUser, updateSpacer]);

  useEffect(() => {
    const content = contentRef.current;
    if (!content) return;
    const observer = new ResizeObserver(() => updateSpacer());
    observer.observe(content);
    return () => observer.disconnect();
  }, [updateSpacer]);

  const handleSubmit = () => {
    if (!input.trim()) return;
    setMessages((prev) => [...prev, { role: "user", content: input.trim() }]);
    setInput("");
    setTimeout(() => {
      scrollToUser();
      requestAnimationFrame(scrollToUser);
    }, 0);
  };

  // Simulate agent response with streaming thinking
  const simPhaseRef = useRef<"idle" | "thinking" | "responding">("idle");
  const simIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Detect new user messages and kick off simulation
  const lastMsg = messages[messages.length - 1];
  const shouldStartSim = lastMsg?.role === "user" && !MOCK_MESSAGES.some(m => m === lastMsg) && simPhaseRef.current === "idle";

  useEffect(() => {
    if (!shouldStartSim) return;
    simPhaseRef.current = "thinking";
    const thinkingText = "Let me think about this carefully. The user wants to build a full-stack application. I should consider the best approach.\n\nFirst, I need to analyze the requirements. What kind of full-stack app? They haven't specified, so I'll propose a modern stack.\n\nFor the frontend, I could use:\n- React with Next.js for SSR\n- Vue with Nuxt\n- Svelte with SvelteKit\n\nFor the backend:\n- Node.js with Express or Fastify\n- Python with FastAPI\n- Go with Gin\n\nDatabase options:\n- PostgreSQL for relational data\n- MongoDB for document storage\n- Redis for caching\n\nLet me think about architecture decisions. A monorepo structure would be ideal for a full-stack app. We could use turborepo or nx for build orchestration.\n\nI should also consider:\n1. Authentication - JWT or session-based?\n2. API design - REST or GraphQL?\n3. Deployment - Docker, Vercel, Railway?\n4. Testing - unit tests, integration tests, e2e tests\n5. CI/CD pipeline setup\n6. Environment variable management\n7. Error handling and logging\n8. Rate limiting and security\n\nFor the database schema, I need to think about:\n- User management tables\n- Session storage\n- Application-specific data models\n- Indexes for performance\n- Migration strategy\n\nI think the best approach is to start with Next.js for the frontend (it handles both client and server-side rendering), FastAPI for the backend API, and PostgreSQL for the database. This gives us type safety, great DX, and production-ready performance.\n\nLet me plan the implementation steps carefully before proceeding.";
    let charIdx = 0;

    simIntervalRef.current = setInterval(() => {
      charIdx += 8;
      const chunk = thinkingText.slice(0, charIdx);
      setMessages((prev) => {
        const existing = prev[prev.length - 1];
        if (existing?.role === "assistant" && existing.streaming) {
          return [...prev.slice(0, -1), {
            ...existing,
            parts: [{ type: "thinking" as const, content: chunk }],
          }];
        }
        return [...prev, {
          role: "assistant" as const, content: "", streaming: true,
          parts: [{ type: "thinking" as const, content: chunk }],
        }];
      });
      if (charIdx >= thinkingText.length) {
        if (simIntervalRef.current) clearInterval(simIntervalRef.current);
        simIntervalRef.current = null;
        setTimeout(() => {
          simPhaseRef.current = "responding";
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last?.role === "assistant" && last.streaming) {
              return [...prev.slice(0, -1), {
                ...last,
                content: "Here's my plan:\n\n1. Set up the project\n2. Add core features\n3. Write tests",
                streaming: false,
                parts: [
                  ...(last.parts ?? []),
                  { type: "text" as const, content: "Here's my plan:\n\n1. Set up the project\n2. Add core features\n3. Write tests" },
                ],
              }];
            }
            return prev;
          });
          simPhaseRef.current = "idle";
        }, 500);
      }
    }, 100);

    return () => {
      if (simIntervalRef.current) {
        clearInterval(simIntervalRef.current);
        simIntervalRef.current = null;
      }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shouldStartSim]);

  useEffect(() => { setCmdIndex(0); }, [input]);

  const selectCommand = useCallback((cmd: string) => {
    const ta = textareaRef.current;
    if (!ta) { setInput(`/${cmd} `); return; }
    const pos = ta.selectionStart ?? input.length;
    const before = input.slice(0, pos);
    const after = input.slice(pos);
    const match = before.match(/\/([^\s]*)$/);
    if (match) {
      const start = before.length - match[0].length;
      setInput(before.slice(0, start) + `/${cmd} ` + after);
    } else {
      setInput(`/${cmd} `);
    }
    ta.focus();
  }, [input]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (filteredCommands.length > 0 && showCommands) {
      if (e.key === "ArrowDown") { e.preventDefault(); setCmdIndex((i) => Math.min(i + 1, filteredCommands.length - 1)); return; }
      if (e.key === "ArrowUp") { e.preventDefault(); setCmdIndex((i) => Math.max(i - 1, 0)); return; }
      if (e.key === "Tab" || (e.key === "Enter" && !e.shiftKey)) { e.preventDefault(); selectCommand(filteredCommands[cmdIndex].name); return; }
      if (e.key === "Escape") { setInput(""); return; }
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="h-screen flex flex-col bg-[#f5f5f5] dark:bg-[var(--color-bg)]" style={{ fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif' }}>
      <div className="h-14 px-4 border-b border-[var(--color-border)] bg-[var(--color-surface)] flex items-center">
        <span className="text-sm font-semibold text-[var(--color-text)]">Chat Preview</span>
      </div>
      <div ref={scrollRef} className="flex-1 overflow-y-auto py-4">
        <div ref={contentRef} className="max-w-4xl mx-auto px-6 space-y-3">
          {messages.map((msg, i) => (
            <div
              key={i}
              data-msg
              className="flex justify-start"
              ref={i === lastUserIdx ? latestUserRef : undefined}
            >
              <MessageBubble msg={msg} />
            </div>
          ))}
          <div ref={spacerRef} />
        </div>
      </div>
      <div className="shrink-0 px-3 pb-5 pt-2">
        <div className="max-w-4xl mx-auto relative">
          {showCommands && filteredCommands.length > 0 && (
            <div className="absolute bottom-full left-0 mb-1 flex items-end gap-1 z-50">
              <div className="bg-[var(--color-surface)] border border-[var(--color-border)] shadow-lg py-1 overflow-y-auto max-h-52 w-[300px]" style={{ borderRadius: 6 }}>
                <div className="px-3 py-1 text-[10px] uppercase tracking-wider text-[var(--color-text-tertiary)] font-medium">Skills</div>
                {filteredCommands.map((cmd, i) => (
                  <button
                    key={cmd.name}
                    onMouseDown={(e) => { e.preventDefault(); selectCommand(cmd.name); }}
                    onMouseEnter={() => setCmdIndex(i)}
                    className={`w-full text-left px-3 py-1.5 text-xs flex items-center gap-2 transition-colors ${
                      i === cmdIndex
                        ? "bg-[var(--color-layer-2)]"
                        : "hover:bg-[var(--color-layer-2)]"
                    }`}
                  >
                    <span className="font-medium text-[var(--color-text)] font-[family-name:var(--font-ibm-plex-mono)]">{cmd.name}</span>
                    <span className="text-[var(--color-text-tertiary)] truncate flex-1">{cmd.description}</span>
                  </button>
                ))}
              </div>
              {filteredCommands[cmdIndex]?.description.length > 40 && (
                <div className="bg-[var(--color-surface)] border border-[var(--color-border)] shadow-lg px-3 py-2.5 w-[220px] max-h-52 overflow-y-auto text-xs text-[var(--color-text-secondary)] leading-relaxed" style={{ borderRadius: 6 }}>
                  {filteredCommands[cmdIndex].description}
                </div>
              )}
            </div>
          )}
          <div className="relative bg-white dark:bg-[var(--color-surface)] shadow-sm px-4 py-2.5 flex items-end gap-2" style={{ borderRadius: 16, minHeight: 40 }}>
            {/* Highlight overlay */}
            <div
              aria-hidden
              className="absolute inset-x-4 top-2.5 bottom-2.5 right-12 text-sm whitespace-pre-wrap break-words pointer-events-none"
              style={{ lineHeight: "20px" }}
            >
              <span className="text-[var(--color-text)]"><HighlightSlash text={input} /></span>
            </div>
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask something..."
              rows={1}
              className="flex-1 resize-none text-sm bg-transparent placeholder:text-[var(--color-text-tertiary)]"
              style={{
                outline: "none", boxShadow: "none",
                color: "transparent",
                caretColor: "var(--color-text)",
                padding: 0, margin: 0, border: "none",
                lineHeight: "20px",
              }}
            />
            <button
              type="button"
              onClick={handleSubmit}
              disabled={!input.trim()}
              className="shrink-0 w-5 h-5 flex items-center justify-center rounded-full bg-[var(--color-text)] text-white disabled:bg-[var(--color-layer-2)] disabled:text-[var(--color-text-tertiary)] disabled:cursor-not-allowed transition-colors"
            >
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
