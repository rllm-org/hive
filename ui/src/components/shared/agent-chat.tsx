"use client";

import { useState, useRef, useEffect, useMemo, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ThinkingBlock } from "@/components/shared/thinking-block";
import { ToolCallCard } from "@/components/shared/tool-call-card";
import { AskUserWidget, type AskUserData } from "@/components/chat/ask-user-widget";
import type { ChatMessage, MessagePart, SlashCommand } from "@/hooks/use-workspace-agent";
import { getAuthHeader } from "@/lib/auth";

const API_BASE = process.env.NEXT_PUBLIC_HIVE_SERVER ?? "/api";

interface ModelInfo {
  id: string;
  display_name: string;
  provider: string;
}

interface AgentChatProps {
  messages: ChatMessage[];
  commands?: SlashCommand[];
  onSend?: (text: string) => void;
  onCancel?: () => void;
  onModelChange?: (model: string) => Promise<void>;
  agentId: string;
  currentModel?: string;
  loading?: boolean;
  cancelling?: boolean;
  streaming?: boolean;
  headerSlot?: React.ReactNode;
}

export function AgentChat({
  messages, commands = [], onSend, onCancel, onModelChange, agentId,
  currentModel = "claude-sonnet-4-6", loading, cancelling, streaming, headerSlot,
}: AgentChatProps) {
  // Debug: log commands received from parent
  useEffect(() => {
    if (commands.length > 0) console.log("[AgentChat] commands received:", commands.length, commands.map(c => c.name));
  }, [commands]);

  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Model selector state
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [modelOpen, setModelOpen] = useState(false);
  const [modelChanging, setModelChanging] = useState(false);
  const [activeModel, setActiveModel] = useState(currentModel);
  const [modelError, setModelError] = useState<string | null>(null);
  const modelRef = useRef<HTMLDivElement>(null);

  // Slash command state
  const [cmdIndex, setCmdIndex] = useState(0);
  const [cmdDismissed, setCmdDismissed] = useState(false);

  // ask_user state
  const [answeredToolIds, setAnsweredToolIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (currentModel) setActiveModel(currentModel);
  }, [currentModel]);

  useEffect(() => {
    fetch(`${API_BASE}/models`, { headers: getAuthHeader() })
      .then((r) => r.ok ? r.json() : null)
      .then((d) => { if (d?.models) setModels(d.models); })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!modelOpen) return;
    const handler = (e: MouseEvent) => {
      if (modelRef.current && !modelRef.current.contains(e.target as Node)) setModelOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [modelOpen]);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    requestAnimationFrame(() => {
      if (scrollRef.current) {
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
      }
    });
  }, [messages]);

  // Slash command detection
  const getSlashWord = useCallback(() => {
    const ta = textareaRef.current;
    if (!ta) return "";
    const pos = ta.selectionStart ?? input.length;
    const before = input.slice(0, pos);
    const match = before.match(/\/([^\s]*)$/);
    return match ? match[0] : "";
  }, [input]);

  const slashWord = getSlashWord();
  const showCommands = slashWord.length > 0 && commands.length > 0 && !cmdDismissed;
  const filteredCommands = showCommands
    ? commands.filter((c) => `/${c.name}`.startsWith(slashWord.toLowerCase()))
    : [];

  useEffect(() => {
    setCmdIndex(0);
    if (slashWord) setCmdDismissed(false);
  }, [input, slashWord]);

  const selectCommand = useCallback((cmd: string) => {
    setCmdDismissed(true);
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

  // Pending ask_user questions
  const pendingQuestions = useMemo(() => {
    const questions: { data: AskUserData; id: string }[] = [];
    for (const msg of messages) {
      if (msg.parts) {
        for (const part of msg.parts) {
          if (part.type === "tool" && part.name.endsWith("ask_user") && part.input && !answeredToolIds.has(part.id)) {
            let inp: Record<string, unknown>;
            if (typeof part.input === "string") {
              try { inp = JSON.parse(part.input); } catch { inp = {}; }
            } else {
              inp = part.input as Record<string, unknown>;
            }
            const args = inp;
            const questionsArr = args.questions as Array<Record<string, unknown>> | undefined;
            if (Array.isArray(questionsArr)) {
              for (const q of questionsArr) {
                const question = (q.question as string) ?? "";
                if (!question) continue;
                questions.push({
                  id: part.id,
                  data: {
                    question,
                    options: q.options as string[] | undefined,
                    mode: (q.mode as AskUserData["mode"]) ?? "select",
                  },
                });
              }
            } else {
              // Fallback: single question format
              const question = (args.question as string) ?? "";
              if (!question) continue;
              questions.push({
                id: part.id,
                data: {
                  question,
                  options: args.options as string[] | undefined,
                  mode: (args.mode as AskUserData["mode"]) ?? "select",
                },
              });
            }
          }
        }
      }
    }
    return questions;
  }, [messages, answeredToolIds]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || !onSend) return;
    onSend(text);
    setInput("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    // Slash command keyboard navigation
    if (filteredCommands.length > 0 && showCommands) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setCmdIndex((i) => Math.min(i + 1, filteredCommands.length - 1));
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setCmdIndex((i) => Math.max(i - 1, 0));
        return;
      }
      if (e.key === "Tab" || (e.key === "Enter" && !e.shiftKey)) {
        e.preventDefault();
        selectCommand(filteredCommands[cmdIndex].name);
        return;
      }
      if (e.key === "Escape") {
        setCmdDismissed(true);
        return;
      }
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }, [filteredCommands, showCommands, cmdIndex, selectCommand, handleSend]);

  const handleInput = () => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 200) + "px";
    }
  };

  const handleModelSelect = async (modelId: string) => {
    if (!onModelChange) return;
    setModelChanging(true);
    setModelOpen(false);
    setModelError(null);
    try {
      await onModelChange(modelId);
      setActiveModel(modelId);
    } catch (err) {
      setModelError(err instanceof Error ? err.message : "Failed to switch model");
    }
    setModelChanging(false);
  };

  const modelDisplayName = models.find((m) => m.id === activeModel)?.display_name ?? activeModel;

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

      {/* ask_user widget — above the input */}
      {pendingQuestions.length > 0 && (
        <div className="shrink-0 px-3 pb-2 bg-[var(--color-layer-1)]">
          <div className="max-w-4xl mx-auto">
            <AskUserWidget
              questions={pendingQuestions.map((q) => q.data)}
              onSubmitAll={(answers) => {
                setAnsweredToolIds((prev) => {
                  const next = new Set(prev);
                  for (const q of pendingQuestions) next.add(q.id);
                  return next;
                });
                const text = answers.map((a, i) => {
                  const q = pendingQuestions[i]?.data.question ?? "";
                  const ans = Array.isArray(a) ? a.join(", ") : a;
                  return pendingQuestions.length === 1 ? ans : `${q}: ${ans}`;
                }).join("\n");
                onSend?.(text);
              }}
            />
          </div>
        </div>
      )}

      {/* Input */}
      <div className="shrink-0 px-3 pb-5 pt-2 bg-[var(--color-layer-1)]">
        <div className="max-w-4xl mx-auto relative">
          {/* Slash command dropdown */}
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
          {/* Model dropdown */}
          {modelOpen && models.length > 0 && (
            <div className="absolute bottom-full mb-2 left-0 z-50 bg-[var(--color-surface)] border border-[var(--color-border)] shadow-lg py-1 min-w-[220px]" style={{ borderRadius: 8 }}>
              {models.map((m) => {
                const isCurrent = m.id === activeModel;
                return (
                  <button
                    key={m.id}
                    onClick={() => handleModelSelect(m.id)}
                    className={`w-full text-left px-3 py-2 text-[12px] transition-colors ${
                      isCurrent
                        ? "bg-[var(--color-layer-1)] text-[var(--color-text)] font-medium"
                        : "text-[var(--color-text-secondary)] hover:bg-[var(--color-layer-1)]"
                    }`}
                  >
                    <div>{m.display_name}</div>
                    <div className="text-[10px] text-[var(--color-text-tertiary)]">{m.provider}</div>
                  </button>
                );
              })}
            </div>
          )}
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
              <div className="flex items-center gap-2">
                <div ref={modelRef}>
                  <button
                    type="button"
                    onClick={() => { setModelOpen((v) => !v); setModelError(null); }}
                    disabled={modelChanging || !onModelChange}
                    className="flex items-center gap-1 text-[11px] text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)] transition-colors disabled:opacity-50"
                  >
                    {modelChanging && <span className="w-3 h-3 border border-current border-t-transparent rounded-full animate-spin" />}
                    {modelDisplayName}
                    <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="opacity-40">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>
                </div>
                {modelError && <span className="text-[10px] text-red-500">{modelError}</span>}
              </div>
              {cancelling ? (
                <div className="shrink-0 w-7 h-7 flex items-center justify-center" title="Stopping...">
                  <div className="w-5 h-5 border-2 border-[var(--color-border)] border-t-[var(--color-text-tertiary)] rounded-full animate-spin" />
                </div>
              ) : loading ? (
                <button
                  type="button"
                  onClick={onCancel}
                  className="shrink-0 w-7 h-7 flex items-center justify-center rounded-full bg-[var(--color-text)] text-white hover:opacity-80 transition-colors"
                  title="Stop generating"
                >
                  <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 24 24">
                    <rect x="6" y="6" width="12" height="12" rx="1" />
                  </svg>
                </button>
              ) : (
                <button
                  type="button"
                  onClick={handleSend}
                  disabled={!onSend || !input.trim()}
                  className={`shrink-0 w-7 h-7 flex items-center justify-center rounded-full transition-colors ${
                    onSend && input.trim()
                      ? "bg-[var(--color-text)] text-white cursor-pointer hover:opacity-80"
                      : "bg-[var(--color-layer-2)] text-[var(--color-text-tertiary)] cursor-not-allowed"
                  }`}
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M12 5l7 7-7 7" />
                  </svg>
                </button>
              )}
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
