"use client";

import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ThinkingBlock } from "@/components/shared/thinking-block";
import { ToolCallCard } from "@/components/shared/tool-call-card";
import type { ChatMessage, MessagePart } from "@/hooks/use-workspace-agent";

interface AgentChatProps {
  messages: ChatMessage[];
  onSend?: (text: string) => void;
  agentId: string;
  modelLabel?: string;
  loading?: boolean;
  streaming?: boolean;
  headerSlot?: React.ReactNode;
}

export function AgentChat({ messages, onSend, agentId, modelLabel = "claude-sonnet-4-6", loading, streaming, headerSlot }: AgentChatProps) {
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || !onSend) return;
    onSend(text);
    setInput("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = () => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 200) + "px";
    }
  };

  return (
    <div className="flex-1 min-h-0 flex flex-col" style={{ fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif' }}>
      {/* Messages */}
      <div className="flex-1 min-h-0 relative">
        {headerSlot && (
          <div className="absolute top-2 left-3 z-10 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg" style={{ fontFamily: "var(--font-dm-sans), sans-serif" }}>
            {headerSlot}
          </div>
        )}
        <div ref={scrollRef} className="h-full overflow-y-auto py-4">
        <div className="max-w-4xl mx-auto px-6 space-y-3">
          {messages.map((msg, i) => {
            if (msg.role === "user") {
              return (
                <div key={i} className="flex justify-start pt-4">
                  <div className="w-full px-3 py-2 bg-white dark:bg-[var(--color-layer-2)] shadow-sm text-[var(--color-text)]" style={{ borderRadius: 10 }}>
                    <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                  </div>
                </div>
              );
            }
            if (msg.role === "error") {
              return (
                <div key={i} className="text-sm text-red-500 px-4">{msg.content}</div>
              );
            }
            const isLastMsg = i === messages.length - 1;
            return (
              <div key={i} className="flex justify-start">
                <div className="w-full pl-4 space-y-1.5">
                  {msg.parts?.map((part, pi) => {
                    const isLastPart = isLastMsg && pi === (msg.parts?.length ?? 0) - 1;
                    return <PartRenderer key={pi} part={part} active={!!msg.streaming && isLastPart} />;
                  })}
                  {msg.content && !msg.parts?.length && (
                    <div className="prose prose-sm max-w-none text-[var(--color-text)]">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
          {loading && messages.length === 0 && (
            <div className="text-sm text-[var(--color-text-tertiary)] px-4">Connecting...</div>
          )}
        </div>
      </div>
      </div>

      {/* Input */}
      <div className="shrink-0 px-3 pb-5 pt-2 bg-[var(--color-layer-1)]">
        <div className="max-w-4xl mx-auto relative">
          <div className="relative bg-white dark:bg-[var(--color-surface)] shadow-sm flex flex-col" style={{ borderRadius: 16, minHeight: 40 }}>
            <div className="flex items-end gap-2 px-4 py-2.5">
              <textarea
                ref={textareaRef}
                rows={1}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onInput={handleInput}
                onKeyDown={handleKeyDown}
                placeholder={`Ask ${agentId} something...`}
                className="flex-1 resize-none text-sm bg-transparent text-[var(--color-text)] placeholder:text-[var(--color-text-tertiary)]"
                style={{ outline: "none", boxShadow: "none", padding: 0, margin: 0, border: "none", lineHeight: "20px" }}
                disabled={!onSend || loading || streaming}
              />
            </div>
            <div className="flex items-center justify-between px-4 pb-2">
              <button type="button" className="flex items-center gap-1 text-[11px] text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)] transition-colors">
                {modelLabel}
                <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="opacity-40">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              <button
                type="button"
                onClick={handleSend}
                disabled={!onSend || !input.trim() || loading || streaming}
                className={`shrink-0 w-7 h-7 flex items-center justify-center rounded-full transition-colors ${
                  onSend && input.trim() && !loading && !streaming
                    ? "bg-[var(--color-accent)] text-white cursor-pointer hover:bg-[var(--color-accent-hover)]"
                    : "bg-[var(--color-layer-2)] text-[var(--color-text-tertiary)] cursor-not-allowed"
                }`}
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M12 5l7 7-7 7" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function PartRenderer({ part, active }: { part: MessagePart; active: boolean }) {
  if (part.type === "thinking") {
    return <ThinkingBlock content={part.content} active={active} />;
  }
  if (part.type === "tool") {
    return <ToolCallCard part={part} active={active} />;
  }
  return (
    <div className="prose prose-sm max-w-none text-[var(--color-text)]">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{part.content}</ReactMarkdown>
    </div>
  );
}
