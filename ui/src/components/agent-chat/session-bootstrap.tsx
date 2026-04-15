"use client";

import { useState } from "react";

interface Props {
  onStart: (agentKind: string) => void;
  starting: boolean;
  error: string | null;
}

const AGENT_OPTIONS: { id: string; label: string; description: string }[] = [
  { id: "claude", label: "Claude Code", description: "claude-agent-sdk via ACP" },
  { id: "custom", label: "Custom ACP", description: "Bring your own ACP-compatible binary" },
];

export function SessionBootstrap({ onStart, starting, error }: Props) {
  const [agentKind, setAgentKind] = useState("claude");
  return (
    <div className="p-4 max-w-md">
      <h2 className="text-sm font-medium mb-1">Start an agent chat</h2>
      <p className="text-xs text-[var(--color-text-secondary)] mb-3">
        The agent runs in a dedicated sandbox and streams responses here.
      </p>

      <div className="space-y-2 mb-4">
        {AGENT_OPTIONS.map((opt) => (
          <label
            key={opt.id}
            className={`flex items-center gap-3 px-3 py-2 border cursor-pointer ${
              agentKind === opt.id
                ? "border-[var(--color-accent)] bg-[var(--color-layer-2)]"
                : "border-[var(--color-border)] hover:bg-[var(--color-layer-2)]"
            }`}
          >
            <input
              type="radio"
              name="agent-kind"
              value={opt.id}
              checked={agentKind === opt.id}
              onChange={() => setAgentKind(opt.id)}
              className="accent-[var(--color-accent)]"
            />
            <div>
              <div className="text-sm">{opt.label}</div>
              <div className="text-xs text-[var(--color-text-secondary)]">{opt.description}</div>
            </div>
          </label>
        ))}
      </div>

      <button
        disabled={starting}
        className="px-3 py-1.5 text-sm bg-[var(--color-accent)] text-white disabled:opacity-50"
        onClick={() => onStart(agentKind)}
      >
        {starting ? "Starting…" : "Start chat"}
      </button>

      {error && <div className="mt-3 text-xs text-red-500">{error}</div>}
    </div>
  );
}
