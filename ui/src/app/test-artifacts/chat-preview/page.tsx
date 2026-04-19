"use client";

import { useState, useRef, useCallback, useEffect, KeyboardEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const MOCK_MESSAGES: Array<{ role: string; content: string; parts?: Array<{ type: string; content?: string; name?: string; status?: string; title?: string; input?: unknown; output?: unknown }> }> = [
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
      <div className="w-full pl-4 space-y-2">
        {msg.parts.map((part, i) =>
          part.type === "text" ? (
            <div key={i} className="prose prose-sm max-w-none text-[var(--color-text)]">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{part.content ?? ""}</ReactMarkdown>
            </div>
          ) : part.type === "thinking" ? (
            <div key={i} className="group/th">
              <button
                type="button"
                onClick={(e) => {
                  const el = e.currentTarget.nextElementSibling;
                  if (el) el.classList.toggle("hidden");
                  e.currentTarget.querySelector("svg")?.classList.toggle("rotate-180");
                  e.currentTarget.querySelector("svg")?.classList.toggle("opacity-100");
                }}
                className="flex items-center gap-1.5 text-xs text-[var(--color-text-tertiary)] cursor-pointer hover:text-[var(--color-text-secondary)]"
              >
                <span>Thought</span>
                <svg className="w-3 h-3 transition-all opacity-0 group-hover/th:opacity-100" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              <div className="hidden mt-1 whitespace-pre-wrap text-[11px] leading-relaxed max-h-40 overflow-y-auto text-[var(--color-text-tertiary)]">
                {part.content}
              </div>
            </div>
          ) : (
            <ToolCard key={i} part={part} />
          )
        )}
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

  useEffect(() => {
    // Triple RAF to ensure spacer + layout + animation are all settled
    const run = () => { updateSpacer(); scrollToUser(); };
    run();
    requestAnimationFrame(() => {
      run();
      requestAnimationFrame(run);
    });
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

  // Simulate agent response
  useEffect(() => {
    const lastMsg = messages[messages.length - 1];
    if (lastMsg?.role === "user" && !MOCK_MESSAGES.some(m => m === lastMsg)) {
      const timer = setTimeout(() => {
        setMessages((prev) => [...prev, {
          role: "assistant",
          content: "Got it! I'll work on that. Here's what I'm thinking:\n\n1. First, I'll set up the project structure\n2. Then add the core functionality\n3. Finally, write some tests\n\nLet me get started...",
        }]);
      }, 1000);
      return () => clearTimeout(timer);
    }
  }, [messages]);

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
            <div className="absolute bottom-full left-0 mb-1 flex items-start gap-1 z-50">
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
          <div className="relative bg-white dark:bg-[var(--color-surface)] shadow-sm px-4 flex items-center gap-2" style={{ borderRadius: 16, height: 40 }}>
            {/* Highlight overlay */}
            <div
              aria-hidden
              className="absolute top-0 left-4 right-12 text-sm whitespace-pre-wrap break-words pointer-events-none flex items-center"
              style={{ height: 40 }}
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
                overflowY: "hidden", outline: "none", boxShadow: "none",
                color: "transparent",
                caretColor: "var(--color-text)",
                padding: 0, margin: 0, border: "none",
                height: 20, lineHeight: "20px",
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
