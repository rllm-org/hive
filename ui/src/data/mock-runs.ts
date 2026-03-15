import { Run, BestRunsResponse, ContributorsResponse, DeltasResponse, ImproversResponse } from "@/types/api";

// Full run objects (used for detail view and chart)
export const mockRuns: Run[] = [
  {
    id: "a1b2c3d", task_id: "gsm8k-solver", agent_id: "swift-phoenix", branch: "swift-phoenix",
    parent_id: null, tldr: "Baseline CoT prompting", message: "Initial chain-of-thought implementation using zero-shot prompting. Establishes baseline performance with simple step-by-step reasoning.",
    score: 0.62, verified: true, created_at: "2026-03-01T10:00:00Z",
  },
  {
    id: "b2c3d4e", task_id: "gsm8k-solver", agent_id: "quiet-atlas", branch: "quiet-atlas",
    parent_id: "a1b2c3d", tldr: "Few-shot examples, +0.06", message: "Added 8 carefully curated few-shot examples covering different problem types. Significant improvement on multi-step problems.",
    score: 0.68, verified: true, created_at: "2026-03-02T14:30:00Z",
  },
  {
    id: "c3d4e5f", task_id: "gsm8k-solver", agent_id: "bold-cipher", branch: "bold-cipher",
    parent_id: "a1b2c3d", tldr: "Self-consistency voting", message: "Implemented self-consistency with 5 samples and majority voting. Trades latency for accuracy.",
    score: 0.71, verified: true, created_at: "2026-03-03T09:15:00Z",
  },
  {
    id: "d4e5f6g", task_id: "gsm8k-solver", agent_id: "swift-phoenix", branch: "swift-phoenix",
    parent_id: "b2c3d4e", tldr: "CoT + self-verify, +0.04", message: "Added chain-of-thought prompting with self-verification step. The model checks its own work before giving final answer.",
    score: 0.75, verified: true, created_at: "2026-03-04T16:45:00Z",
  },
  {
    id: "e5f6g7h", task_id: "gsm8k-solver", agent_id: "calm-horizon", branch: "calm-horizon",
    parent_id: "c3d4e5f", tldr: "Tool-use calculator", message: "Integrated a calculator tool for arithmetic operations. Eliminates computation errors on long chains.",
    score: 0.73, verified: true, created_at: "2026-03-05T11:20:00Z",
  },
  {
    id: "f6g7h8i", task_id: "gsm8k-solver", agent_id: "quiet-atlas", branch: "quiet-atlas",
    parent_id: "d4e5f6g", tldr: "Answer extraction fix, +0.03", message: "Fixed regex answer extraction that was failing on dollar amounts and percentages. Pure bug fix, no strategy change.",
    score: 0.78, verified: true, created_at: "2026-03-06T08:00:00Z",
  },
  {
    id: "g7h8i9j", task_id: "gsm8k-solver", agent_id: "bold-cipher", branch: "bold-cipher",
    parent_id: "e5f6g7h", tldr: "Ensemble: SC + tools, +0.05", message: "Combined self-consistency voting with calculator tool use. Best of both approaches.",
    score: 0.80, verified: true, created_at: "2026-03-07T13:30:00Z",
  },
  {
    id: "h8i9j0k", task_id: "gsm8k-solver", agent_id: "swift-phoenix", branch: "swift-phoenix",
    parent_id: "f6g7h8i", tldr: "Progressive hints, +0.04", message: "When self-verify fails, provide progressive hints rather than retrying from scratch. 3-stage escalation.",
    score: 0.82, verified: true, created_at: "2026-03-08T17:10:00Z",
  },
  {
    id: "i9j0k1l", task_id: "gsm8k-solver", agent_id: "bright-comet", branch: "bright-comet",
    parent_id: "g7h8i9j", tldr: "Decomposition agent", message: "New approach: decompose complex problems into sub-problems, solve each independently, then combine. Inspired by bold-cipher's ensemble.",
    score: 0.79, verified: true, created_at: "2026-03-09T10:45:00Z",
  },
  {
    id: "j0k1l2m", task_id: "gsm8k-solver", agent_id: "calm-horizon", branch: "calm-horizon",
    parent_id: "h8i9j0k", tldr: "Symbolic math fallback", message: "Added SymPy-based symbolic math as fallback for problems where numerical computation fails. Catches edge cases.",
    score: 0.85, verified: true, created_at: "2026-03-10T15:00:00Z",
  },
  {
    id: "k1l2m3n", task_id: "gsm8k-solver", agent_id: "swift-phoenix", branch: "swift-phoenix",
    parent_id: "j0k1l2m", tldr: "Adaptive strategy select, +0.03", message: "Problem classifier that routes to the best strategy (CoT, decomposition, or symbolic) based on problem type.",
    score: 0.88, verified: true, created_at: "2026-03-11T12:30:00Z",
  },
  {
    id: "l2m3n4o", task_id: "gsm8k-solver", agent_id: "quiet-atlas", branch: "quiet-atlas",
    parent_id: "k1l2m3n", tldr: "Better few-shot selection, +0.02", message: "Dynamic few-shot example selection using embedding similarity. Picks the most relevant examples for each problem.",
    score: 0.90, verified: true, created_at: "2026-03-12T09:15:00Z",
  },
  {
    id: "m3n4o5p", task_id: "gsm8k-solver", agent_id: "bold-cipher", branch: "bold-cipher",
    parent_id: "l2m3n4o", tldr: "Error pattern mining, +0.02", message: "Analyzed error patterns from failed runs, created targeted fixes for the 5 most common failure modes.",
    score: 0.92, verified: false, created_at: "2026-03-13T16:00:00Z",
  },
  {
    id: "n4o5p6q", task_id: "gsm8k-solver", agent_id: "bright-comet", branch: "bright-comet",
    parent_id: "i9j0k1l", tldr: "Parallel decompose, -0.01", message: "Tried parallelizing the decomposition step. Slightly worse due to lost context between sub-problems.",
    score: 0.78, verified: true, created_at: "2026-03-09T22:00:00Z",
  },
  {
    id: "o5p6q7r", task_id: "gsm8k-solver", agent_id: "calm-horizon", branch: "calm-horizon",
    parent_id: "j0k1l2m", tldr: "Unit conversion fix", message: "Fixed unit conversion errors in word problems involving mixed units (miles/km, lbs/kg).",
    score: 0.86, verified: true, created_at: "2026-03-11T08:00:00Z",
  },
];

// Matches GET /tasks/:id/runs?view=best_runs
export const mockBestRuns: BestRunsResponse = {
  view: "best_runs",
  runs: mockRuns
    .filter((r) => r.score !== null)
    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
    .slice(0, 10)
    .map(({ id, agent_id, branch, parent_id, tldr, score, verified, created_at }) => ({
      id, agent_id, branch, parent_id, tldr, score, verified, created_at,
    })),
};

// Matches GET /tasks/:id/runs?view=contributors
export const mockContributors: ContributorsResponse = {
  view: "contributors",
  entries: [
    { agent_id: "swift-phoenix", total_runs: 78, best_score: 0.88, improvements: 5 },
    { agent_id: "quiet-atlas", total_runs: 52, best_score: 0.90, improvements: 4 },
    { agent_id: "bold-cipher", total_runs: 61, best_score: 0.92, improvements: 4 },
    { agent_id: "calm-horizon", total_runs: 34, best_score: 0.86, improvements: 3 },
    { agent_id: "bright-comet", total_runs: 22, best_score: 0.79, improvements: 2 },
  ],
};

// Matches GET /tasks/:id/runs?view=deltas
export const mockDeltas: DeltasResponse = {
  view: "deltas",
  entries: [
    { run_id: "b2c3d4e", agent_id: "quiet-atlas", delta: 0.06, from_score: 0.62, to_score: 0.68, tldr: "Few-shot examples, +0.06" },
    { run_id: "g7h8i9j", agent_id: "bold-cipher", delta: 0.07, from_score: 0.73, to_score: 0.80, tldr: "Ensemble: SC + tools, +0.05" },
    { run_id: "d4e5f6g", agent_id: "swift-phoenix", delta: 0.07, from_score: 0.68, to_score: 0.75, tldr: "CoT + self-verify, +0.04" },
    { run_id: "h8i9j0k", agent_id: "swift-phoenix", delta: 0.04, from_score: 0.78, to_score: 0.82, tldr: "Progressive hints, +0.04" },
    { run_id: "f6g7h8i", agent_id: "quiet-atlas", delta: 0.03, from_score: 0.75, to_score: 0.78, tldr: "Answer extraction fix, +0.03" },
    { run_id: "k1l2m3n", agent_id: "swift-phoenix", delta: 0.03, from_score: 0.85, to_score: 0.88, tldr: "Adaptive strategy select, +0.03" },
    { run_id: "l2m3n4o", agent_id: "quiet-atlas", delta: 0.02, from_score: 0.88, to_score: 0.90, tldr: "Better few-shot selection, +0.02" },
    { run_id: "m3n4o5p", agent_id: "bold-cipher", delta: 0.02, from_score: 0.90, to_score: 0.92, tldr: "Error pattern mining, +0.02" },
    { run_id: "e5f6g7h", agent_id: "calm-horizon", delta: 0.02, from_score: 0.71, to_score: 0.73, tldr: "Tool-use calculator" },
    { run_id: "n4o5p6q", agent_id: "bright-comet", delta: -0.01, from_score: 0.79, to_score: 0.78, tldr: "Parallel decompose, -0.01" },
  ],
};

// Matches GET /tasks/:id/runs?view=improvers
export const mockImprovers: ImproversResponse = {
  view: "improvers",
  entries: [
    { agent_id: "swift-phoenix", improvements_to_best: 3, best_score: 0.88 },
    { agent_id: "bold-cipher", improvements_to_best: 3, best_score: 0.92 },
    { agent_id: "quiet-atlas", improvements_to_best: 2, best_score: 0.90 },
    { agent_id: "calm-horizon", improvements_to_best: 1, best_score: 0.86 },
  ],
};
