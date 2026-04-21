# Model Selector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a model selector pill to the agent tabs row that lets users switch the active Claude model mid-session.

**Architecture:** Two file changes only — add `setModel` to the `useWorkspaceAgents` hook, then add the pill + dropdown UI to `AgentTabs` in the workspace page. Local React state tracks the current model (not the DB, since the agent-sdk config endpoint doesn't write back to Hive's database).

**Tech Stack:** Next.js 15, React 19, TypeScript, Tailwind v4, agent-sdk REST API (`POST /sessions/{id}/config`)

---

### Task 1: Add `setModel` to `useWorkspaceAgents`

**Files:**
- Modify: `hive/ui/src/hooks/use-workspace-agent.ts`

- [ ] **Step 1: Add `setModel` to the hook body**

In `use-workspace-agent.ts`, add this `useCallback` right after the `cancel` callback (around line 460):

```ts
const setModel = useCallback(async (agentId: string, model: string) => {
  const conn = connectionsRef.current[agentId];
  if (!conn) return;
  const res = await fetch(`${conn.sdkBase}/sessions/${conn.sdkSid}/config`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model }),
  });
  if (!res.ok) throw new Error(`set_model failed: ${res.status}`);
}, []);
```

- [ ] **Step 2: Expose `setModel` in the return value**

Change the `return` statement at the bottom of `useWorkspaceAgents` from:
```ts
return { states, sendMessage, cancel };
```
to:
```ts
return { states, sendMessage, cancel, setModel };
```

- [ ] **Step 3: Type-check**

```bash
cd hive/ui && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add hive/ui/src/hooks/use-workspace-agent.ts
git commit -m "feat: add setModel to useWorkspaceAgents hook"
```

---

### Task 2: Add model constants and pill UI to `AgentTabs`

**Files:**
- Modify: `hive/ui/src/app/workspaces/[id]/page.tsx`

- [ ] **Step 1: Add `MODELS` constant before `AgentTabs`**

Insert this block immediately before `function AgentTabs(` (line 158):

```ts
const MODELS = [
  { id: "claude-haiku-4-5-20251001", label: "Haiku",  tier: "Fast",     short: "haiku" },
  { id: "claude-sonnet-4-6",         label: "Sonnet", tier: "Balanced",  short: "sonnet-4-6" },
  { id: "claude-opus-4-6",           label: "Opus",   tier: "Powerful",  short: "opus-4-6" },
] as const;

type ModelId = (typeof MODELS)[number]["id"];
```

- [ ] **Step 2: Extend `AgentTabs` props**

Replace the current `AgentTabs` signature:
```ts
function AgentTabs({
  agents,
  activeAgentId,
  onSelect,
  onDelete,
}: {
  agents: WorkspaceAgent[];
  activeAgentId: string | null;
  onSelect: (id: string) => void;
  onDelete: (id: string) => Promise<void>;
}) {
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
```

With:
```ts
function AgentTabs({
  agents,
  activeAgentId,
  onSelect,
  onDelete,
  activeModel,
  onModelChange,
}: {
  agents: WorkspaceAgent[];
  activeAgentId: string | null;
  onSelect: (id: string) => void;
  onDelete: (id: string) => Promise<void>;
  activeModel: string | null;
  onModelChange: (model: string) => Promise<void>;
}) {
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const [modelOpen, setModelOpen] = useState(false);
  const [modelChanging, setModelChanging] = useState(false);
  const modelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!modelOpen) return;
    const handler = (e: MouseEvent) => {
      if (modelRef.current && !modelRef.current.contains(e.target as Node)) {
        setModelOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [modelOpen]);
```

- [ ] **Step 3: Add model pill + dropdown to the tabs row JSX**

The current tabs row JSX in `AgentTabs` is:
```tsx
<div className="shrink-0 flex items-end gap-0 px-3 pt-2 relative overflow-x-auto" style={{ marginBottom: -1 }}>
  {agents.map((a) => { ... })}
</div>
```

Replace it with (keeps all existing tab markup, appends the pill on the right):
```tsx
<div className="shrink-0 flex items-end gap-0 px-3 pt-2 relative" style={{ marginBottom: -1 }}>
  <div className="flex items-end gap-0 flex-1 overflow-x-auto min-w-0">
    {agents.map((a) => {
      const active = a.id === activeAgentId;
      return (
        <div
          key={a.id}
          onClick={() => onSelect(a.id)}
          className={`group flex items-center gap-1.5 pl-2.5 pr-1.5 py-1.5 text-[12px] font-medium cursor-pointer transition-colors ${
            active
              ? "bg-[var(--color-layer-1)] text-[var(--color-text)] border border-[var(--color-border)] border-b-transparent z-10"
              : "text-[var(--color-text-secondary)] hover:text-[var(--color-text)] opacity-60 hover:opacity-100 border border-transparent"
          }`}
          style={{ borderRadius: "6px 6px 0 0" }}
        >
          <AgentAvatar seed={a.avatar_seed} id={a.id} size={16} />
          <span className="truncate max-w-[120px]">{a.id}</span>
          <button
            onClick={(e) => { e.stopPropagation(); setPendingDelete(a.id); }}
            className={`w-4 h-4 ml-0.5 flex items-center justify-center text-[var(--color-text-tertiary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-2)] transition-all ${
              active ? "opacity-100" : "opacity-0 group-hover:opacity-100"
            }`}
            style={{ borderRadius: 3 }}
            aria-label={`Close ${a.id}`}
          >
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M2 2l6 6M8 2l-6 6" />
            </svg>
          </button>
        </div>
      );
    })}
  </div>
  {activeModel != null && (
    <div ref={modelRef} className="flex items-center pb-1.5 pl-2 flex-shrink-0 relative">
      <button
        onClick={() => setModelOpen((v) => !v)}
        disabled={modelChanging}
        className={`flex items-center gap-1 px-2 py-1 text-[11px] border rounded font-mono transition-colors ${
          modelOpen
            ? "border-[var(--color-accent)] text-[var(--color-text)] bg-[var(--color-surface)]"
            : "border-[var(--color-border)] text-[var(--color-text-secondary)] hover:border-[#444] hover:text-[var(--color-text)] bg-[var(--color-surface)]"
        } disabled:opacity-50`}
      >
        {modelChanging ? (
          <span className="w-3 h-3 border border-current border-t-transparent rounded-full animate-spin" />
        ) : null}
        {MODELS.find((m) => m.id === activeModel)?.short ?? activeModel}
        <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="opacity-50">
          {modelOpen
            ? <path d="M18 15l-6-6-6 6" />
            : <path d="M6 9l6 6 6-6" />}
        </svg>
      </button>
      {modelOpen && (
        <div className="absolute top-full right-0 mt-1 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-md shadow-lg min-w-[196px] z-50 overflow-hidden">
          {MODELS.map((m) => {
            const isCurrent = m.id === activeModel;
            const tierStyle: Record<string, React.CSSProperties> = {
              Fast:     { background: "#1a3d2b", color: "#3ecf8e" },
              Balanced: { background: "#1f2e4a", color: "#60a5fa" },
              Powerful: { background: "#2d1f4a", color: "#c084fc" },
            };
            return (
              <button
                key={m.id}
                onClick={async () => {
                  if (isCurrent) { setModelOpen(false); return; }
                  setModelOpen(false);
                  setModelChanging(true);
                  try { await onModelChange(m.id); } finally { setModelChanging(false); }
                }}
                className={`w-full text-left px-3 py-2 flex flex-col gap-0.5 hover:bg-[var(--color-layer-2)] transition-colors ${isCurrent ? "bg-[#1a1535]" : ""}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[12px] font-semibold text-[var(--color-text)] font-mono">{m.label}</span>
                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wide" style={tierStyle[m.tier]}>
                    {m.tier}
                  </span>
                  {isCurrent && (
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--color-accent)" strokeWidth="2.5">
                      <path d="M20 6L9 17l-5-5" />
                    </svg>
                  )}
                </div>
                <span className="text-[11px] text-[var(--color-text-tertiary)]">{m.id}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  )}
</div>
```

- [ ] **Step 4: Type-check**

```bash
cd hive/ui && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add hive/ui/src/app/workspaces/\[id\]/page.tsx
git commit -m "feat: add model selector pill to AgentTabs"
```

---

### Task 3: Wire `setModel` and model state in the workspace page

**Files:**
- Modify: `hive/ui/src/app/workspaces/[id]/page.tsx`

- [ ] **Step 1: Destructure `setModel` from the hook**

Find the line (around 736):
```ts
const { states: agentStates, sendMessage: sendAgentMessage, cancel: cancelAgent } = useWorkspaceAgents(
```

Replace with:
```ts
const { states: agentStates, sendMessage: sendAgentMessage, cancel: cancelAgent, setModel: setAgentModel } = useWorkspaceAgents(
```

- [ ] **Step 2: Add `currentModel` state**

After the line `const [activeAgentId, setActiveAgentId] = useState<string | null>(null);` (around line 632), add:

```ts
const [currentModel, setCurrentModel] = useState<string>("claude-sonnet-4-6");
const [modelError, setModelError] = useState<string | null>(null);
```

- [ ] **Step 3: Sync `currentModel` when active agent changes**

After the existing auto-select effect (around line 697), add:

```ts
useEffect(() => {
  setCurrentModel(activeAgent?.model ?? "claude-sonnet-4-6");
  setModelError(null);
}, [activeAgent?.id]);
```

- [ ] **Step 4: Add `handleModelChange` callback**

After the `cancel` callback (around line 744), add:

```ts
const handleModelChange = useCallback(async (model: string) => {
  if (!activeAgent) return;
  setModelError(null);
  try {
    await setAgentModel(activeAgent.id, model);
    setCurrentModel(model);
  } catch {
    setModelError("Failed to switch model");
  }
}, [activeAgent, setAgentModel]);
```

- [ ] **Step 5: Pass new props to `AgentTabs` and show error**

Find the `<AgentTabs` usage (around line 1159):
```tsx
<AgentTabs
  agents={agents}
  activeAgentId={activeAgent?.id ?? null}
  onSelect={setActiveAgentId}
  onDelete={handleDeleteAgent}
/>
```

Replace with:
```tsx
<AgentTabs
  agents={agents}
  activeAgentId={activeAgent?.id ?? null}
  onSelect={setActiveAgentId}
  onDelete={handleDeleteAgent}
  activeModel={activeAgent ? currentModel : null}
  onModelChange={handleModelChange}
/>
{modelError && (
  <div className="shrink-0 px-3 py-1 text-[11px] text-red-400 bg-red-500/5 border-b border-[var(--color-border)]">
    {modelError}
  </div>
)}
```

- [ ] **Step 6: Type-check and lint**

```bash
cd hive/ui && npx tsc --noEmit && npx eslint src/app/workspaces/\[id\]/page.tsx --max-warnings 0
```
Expected: no errors, no warnings.

- [ ] **Step 7: Smoke test in dev server**

```bash
cd hive/ui && npm run dev
```

Open the workspace page. Verify:
1. Pill shows current model name (e.g. `sonnet-4-6`) in the tabs row, right-aligned
2. Clicking the pill opens the dropdown with Haiku / Sonnet / Opus
3. Current model has a checkmark
4. Selecting a different model closes the dropdown, briefly shows spinner, then updates the pill label
5. Switching agents resets the pill to that agent's model
6. If no agent is active, no pill is shown

- [ ] **Step 8: Commit**

```bash
git add hive/ui/src/app/workspaces/\[id\]/page.tsx
git commit -m "feat: wire model selector into workspace page"
```
