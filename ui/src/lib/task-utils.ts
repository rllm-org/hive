export type TaskCategory = "Math" | "Code" | "Knowledge" | "Agent" | "General";

const CATEGORY_MAP: { pattern: RegExp; label: TaskCategory }[] = [
  { pattern: /(gsm8k|math|aime|hmmt|polymath|countdown|gpqa|addition)/, label: "Math" },
  { pattern: /(humaneval|mbpp|livecodebench|code)/, label: "Code" },
  { pattern: /(hotpotqa|mmlu|ifeval)/, label: "Knowledge" },
  { pattern: /(reasoning|labbench|figqa|vision|baby)/, label: "Knowledge" },
  { pattern: /(adebench|dbt)/, label: "Code" },
  { pattern: /(tau|hello.world|arc|agent|terminal)/, label: "Agent" },
];

export function getTaskCategory(taskId: string): TaskCategory {
  const lower = taskId.toLowerCase();
  for (const { pattern, label } of CATEGORY_MAP) {
    if (pattern.test(lower)) return label;
  }
  return "General";
}

const CATEGORY_STYLES: Record<TaskCategory, { bg: string; text: string; border: string }> = {
  Math:      { bg: "bg-amber-50 dark:bg-amber-950/40",     text: "text-amber-700 dark:text-amber-400",    border: "border-amber-200 dark:border-amber-800" },
  Code:      { bg: "bg-purple-50 dark:bg-purple-950/40",   text: "text-purple-700 dark:text-purple-400",  border: "border-purple-200 dark:border-purple-800" },
  Knowledge: { bg: "bg-emerald-50 dark:bg-emerald-950/40", text: "text-emerald-700 dark:text-emerald-400", border: "border-emerald-200 dark:border-emerald-800" },
  Agent:     { bg: "bg-blue-50 dark:bg-blue-950/40",       text: "text-blue-600 dark:text-blue-400",      border: "border-blue-200 dark:border-blue-800" },
  General:   { bg: "bg-gray-100 dark:bg-gray-800/40",      text: "text-gray-600 dark:text-gray-400",      border: "border-gray-200 dark:border-gray-700" },
};

export function getCategoryStyle(category: TaskCategory) {
  return CATEGORY_STYLES[category];
}

const CATEGORY_GRADIENTS: Record<TaskCategory, string> = {
  Math:      "from-amber-500 to-orange-600",
  Code:      "from-purple-500 to-indigo-600",
  Knowledge: "from-emerald-500 to-teal-600",
  Agent:     "from-blue-500 to-cyan-600",
  General:   "from-slate-400 to-gray-600",
};

export function getCategoryGradient(category: TaskCategory): string {
  return CATEGORY_GRADIENTS[category];
}

const COVER_IMAGES: Record<string, string> = {
  aime2026: "/images/aime.jpg",
  aime: "/images/aime.jpg",
  adebench: "/images/ADEbench.jpg",
  babyvision: "/images/babyvision.png",
  "hmmt-nov": "/images/HMMT.png",
  hmmt: "/images/HMMT.png",
  ifeval: "/images/IFEval.png",
  "labbench-figqa": "/images/lab-bench-figqa.png",
  polymath: "/images/PolyMATH.png",
  "reasoning-gym": "/images/reasoninggym.png",
  tau2: "/images/tau2bench.svg",
  hotpotqa: "/images/hotpotqa.png",
  mmlu: "/images/mmlu-pro.png",
  "hello-world": "/images/hello-world.png",
  livecodebench: "/images/LiveCodeBench.png",
  math: "/images/math-500.png",
  terminalbench: "/images/terminalbench.png",
  "arc-agi-2": "/images/ARC-AGI-2.jpg",
  gpqa: "/images/GPQA.png",
  humaneval: "/images/HumanEval.webp",
  gsm8k: "/images/HumanEval.webp",
};

export function getCoverImage(taskId: string): string | null {
  return COVER_IMAGES[taskId] ?? null;
}
