"use client";

import { useState, useRef, useCallback, useEffect, KeyboardEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const MOCK_MESSAGES = [
  { role: "user", content: "Can you help me build a REST API?" },
  { role: "assistant", content: "Sure! What language and framework would you like to use?\n\n- **Python** (FastAPI, Flask, Django)\n- **TypeScript** (Express, Fastify, Hono)\n- **Go** (Gin, Echo, Chi)" },
  { role: "user", content: "Let's go with FastAPI" },
  { role: "assistant", content: "Great choice. Let me set up a basic FastAPI project structure.\n\n```python\nfrom fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get(\"/\")\ndef root():\n    return {\"message\": \"Hello World\"}\n```\n\nShould I add authentication and database support?" },
  { role: "user", content: "Yes, add JWT auth and PostgreSQL" },
  { role: "assistant", content: "I'll add:\n1. JWT authentication with `python-jose`\n2. PostgreSQL via `asyncpg` + `SQLAlchemy`\n3. User registration and login endpoints\n\nLet me start with the database models..." },
  { role: "user", content: "Sounds good, go ahead" },
];

export default function ChatPreview() {
  const [messages, setMessages] = useState(MOCK_MESSAGES);
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const resizeTextarea = useCallback(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
    ta.style.overflowY = ta.scrollHeight > 200 ? "auto" : "hidden";
  }, []);

  useEffect(() => { resizeTextarea(); }, [input, resizeTextarea]);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages]);

  const handleSubmit = () => {
    if (!input.trim()) return;
    setMessages((prev) => [...prev, { role: "user", content: input.trim() }]);
    setInput("");
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
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
        <div className="max-w-4xl mx-auto px-6 space-y-3">
          {messages.map((msg, i) => (
            <div key={i} className="flex justify-start">
              {msg.role === "user" ? (
                <div className="w-full px-3 py-2 bg-white dark:bg-[var(--color-layer-2)] shadow-sm text-[var(--color-text)]" style={{ borderRadius: 10 }}>
                  <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                </div>
              ) : (
                <div className="w-full pl-4 prose prose-sm max-w-none text-[var(--color-text)]">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
      <div className="shrink-0 px-3 pb-3 pt-2">
        <div className="max-w-4xl mx-auto">
          <div className="flex items-end gap-2 bg-white dark:bg-[var(--color-surface)] shadow-sm px-4 py-2" style={{ borderRadius: 16 }}>
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask something..."
              rows={1}
              className="flex-1 resize-none text-sm bg-transparent text-[var(--color-text)] placeholder:text-[var(--color-text-tertiary)] py-1"
              style={{ overflowY: "hidden", outline: "none", boxShadow: "none" }}
            />
            <button
              type="button"
              onClick={handleSubmit}
              disabled={!input.trim()}
              className="shrink-0 p-1.5 rounded-full bg-[var(--color-text)] text-white disabled:bg-[var(--color-layer-2)] disabled:text-[var(--color-text-tertiary)] disabled:cursor-not-allowed transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
