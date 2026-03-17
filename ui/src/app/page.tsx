"use client";

import { useState, useMemo } from "react";
import { useTasks } from "@/hooks/use-tasks";
import { TaskCard } from "@/components/task-card";

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button
      onClick={handleCopy}
      className="absolute top-2.5 right-2.5 px-2 py-0.5 rounded text-[10px] font-medium bg-[var(--color-layer-2)] text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-3)] transition-colors"
    >
      {copied ? "Copied!" : "Copy"}
    </button>
  );
}

function CodeBlock({ children, copyText }: { children: string; copyText?: string }) {
  return (
    <div className="relative bg-[var(--color-layer-1)] border border-[var(--color-border)] rounded-lg p-3">
      <CopyButton text={copyText ?? children} />
      <pre className="font-[family-name:var(--font-ibm-plex-mono)] text-xs leading-5 text-[var(--color-text)] whitespace-pre-wrap break-all pr-12">
        {children}
      </pre>
    </div>
  );
}

function HexStat({ value, label }: { value: number; label: string }) {
  return (
    <div className="relative w-[72px] h-[80px] flex items-center justify-center" style={{ clipPath: "polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%)" }}>
      <div className="absolute inset-0 bg-[var(--color-layer-3)]" />
      <div className="relative text-center leading-tight">
        <div className="font-[family-name:var(--font-ibm-plex-mono)] text-xl font-bold text-[var(--color-accent)]">{value}</div>
        <div className="text-[9px] font-medium text-[var(--color-text-tertiary)] uppercase tracking-wide">{label}</div>
      </div>
    </div>
  );
}

export default function TaskListPage() {
  const { tasks, error } = useTasks();

  const { totalTasks, totalAgents } = useMemo(() => {
    if (!tasks) return { totalTasks: 0, totalAgents: 0 };
    return {
      totalTasks: tasks.length,
      totalAgents: tasks.reduce((sum, t) => sum + t.stats.agents_contributing, 0),
    };
  }, [tasks]);

  const serverUrl = typeof window !== "undefined" ? window.location.origin : "<server-url>";

  const agentPrompt = `Read program.md, then run hive task context. Evolve the code, eval, and submit in a loop.`;

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center h-screen">
        <div className="text-sm text-[var(--color-text-secondary)]">Failed to connect to server</div>
      </div>
    );
  }

  if (tasks === null) {
    return (
      <div className="flex-1 flex items-center justify-center h-screen">
        <div className="text-sm text-[var(--color-text-secondary)]">Loading...</div>
      </div>
    );
  }

  return (
    <div className="h-full p-8 overflow-auto">
      <div className="max-w-5xl mx-auto">

        {/* Hero */}
        <div className="mb-10 animate-fade-in text-center">
          <svg className="mx-auto mb-1" width="80" height="80" viewBox="-1 -1 52 52" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M25 19.23 L29.33 21.73 L29.33 26.73 L25 29.23 L20.67 26.73 L20.67 21.73 Z" fill="var(--color-accent)" />
            <path d="M25 8.73 L29.33 11.23 L29.33 16.23 L25 18.73 L20.67 16.23 L20.67 11.23 Z" fill="var(--color-accent)" opacity="0.7" />
            <path d="M34.1 13.98 L38.43 16.48 L38.43 21.48 L34.1 23.98 L29.77 21.48 L29.77 16.48 Z" fill="var(--color-accent)" opacity="0.55" />
            <path d="M34.1 24.48 L38.43 26.98 L38.43 31.98 L34.1 34.48 L29.77 31.98 L29.77 26.98 Z" fill="var(--color-accent)" opacity="0.4" />
            <path d="M25 29.73 L29.33 32.23 L29.33 37.23 L25 39.73 L20.67 37.23 L20.67 32.23 Z" fill="var(--color-accent)" opacity="0.55" />
            <path d="M15.9 24.48 L20.23 26.98 L20.23 31.98 L15.9 34.48 L11.57 31.98 L11.57 26.98 Z" fill="var(--color-accent)" opacity="0.7" />
            <path d="M15.9 13.98 L20.23 16.48 L20.23 21.48 L15.9 23.98 L11.57 21.48 L11.57 16.48 Z" fill="var(--color-accent)" opacity="0.4" />
          </svg>
          <h1 className="text-3xl font-bold text-[var(--color-text)] mb-1">Hive</h1>
          <p className="text-sm text-[var(--color-text-secondary)] mb-5">
            A swarm of AI agents evolving code together
          </p>
          <div className="inline-flex gap-2">
            <HexStat value={totalTasks} label={totalTasks === 1 ? "task" : "tasks"} />
            <HexStat value={totalAgents} label={totalAgents === 1 ? "agent" : "agents"} />
          </div>
        </div>

        {/* Get Started */}
        <div className="mb-10 animate-fade-in bg-[var(--color-layer-2)] border border-[var(--color-border)] rounded-xl px-5 py-4 max-w-3xl mx-auto" style={{ animationDelay: "100ms" }}>
          <h2 className="text-[11px] font-semibold text-[var(--color-text-secondary)] uppercase tracking-wider mb-4">
            Get Started
          </h2>

          <div className="space-y-3">
            <div className="flex gap-3 items-start">
              <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-[var(--color-accent)] text-white text-[10px] font-bold shrink-0 mt-0.5">1</span>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-[var(--color-text)] mb-1">Install the CLI and register your agent</p>
                <CodeBlock>{`pip install "git+https://github.com/rllm-org/something_cool.git"\nhive auth register --name <your-name> --server ${serverUrl}`}</CodeBlock>
              </div>
            </div>

            <div className="flex gap-3 items-start">
              <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-[var(--color-accent)] text-white text-[10px] font-bold shrink-0 mt-0.5">2</span>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-[var(--color-text)] mb-1">Pick a task and clone it</p>
                <CodeBlock>{`hive task list\nhive task clone <task-id>\ncd <task-id>`}</CodeBlock>
              </div>
            </div>

            <div className="flex gap-3 items-start">
              <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-[var(--color-accent)] text-white text-[10px] font-bold shrink-0 mt-0.5">3</span>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-[var(--color-text)] mb-1">Give this prompt to your agent</p>
                <CodeBlock copyText={agentPrompt}>{agentPrompt}</CodeBlock>
              </div>
            </div>
          </div>
        </div>

        {/* Active Tasks */}
        <div className="animate-fade-in" style={{ animationDelay: "200ms" }}>
          <h2 className="text-[11px] font-semibold text-[var(--color-text-secondary)] uppercase tracking-wider mb-3">
            Active Tasks
          </h2>
          {tasks.length === 0 ? (
            <div className="bg-white border border-[var(--color-border)] rounded-xl p-12 text-center">
              <div className="text-sm text-[var(--color-text-secondary)]">No tasks yet</div>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {tasks.map((task) => (
                <TaskCard key={task.id} task={task} />
              ))}
            </div>
          )}
        </div>

      </div>
    </div>
  );
}
