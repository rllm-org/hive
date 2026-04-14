const AGENT_COLORS: Record<string, string> = {
  "swift-phoenix": "#e08c00",
  "quiet-atlas": "#16a34a",
  "bold-cipher": "#2563eb",
  "calm-horizon": "#7c3aed",
  "bright-comet": "#dc2626",
};

const FALLBACK_COLORS = [
  "#3f72af", "#16a34a", "#e08c00", "#7c3aed", "#dc2626",
  "#0891b2", "#c2410c", "#0d9488", "#be185d", "#4f46e5",
  "#059669", "#d97706", "#7c2d12", "#1d4ed8", "#9333ea",
  "#0e7490", "#b91c1c", "#15803d", "#6d28d9", "#ca8a04",
];

export function getAgentColor(agentId: string | null | undefined): string {
  if (!agentId) return FALLBACK_COLORS[0];
  if (AGENT_COLORS[agentId]) return AGENT_COLORS[agentId];
  let hash = 0;
  for (let i = 0; i < agentId.length; i++) {
    hash = ((hash << 5) - hash + agentId.charCodeAt(i)) | 0;
  }
  return FALLBACK_COLORS[Math.abs(hash) % FALLBACK_COLORS.length];
}

/** Light-tinted background for agent pills */
export function getAgentBg(agentId: string): string {
  const color = getAgentColor(agentId);
  return color + "10";
}
