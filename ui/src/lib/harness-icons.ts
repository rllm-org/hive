/** Maps agent harness names to their logo icon paths in /public/. */

const HARNESS_ICONS: Record<string, string> = {
  "claude-code": "/claude-icon.png",
  "claude": "/claude-icon.png",
  "cursor": "/openai-icon.png",    // Cursor uses OpenAI models primarily
  "codex": "/openai-icon.png",
  "gemini-cli": "/gemini-icon.png",
  "gemini": "/gemini-icon.png",
  "opencode": "/openai-icon.png",
};

/** Model prefix → icon path (used when harness doesn't match but model does). */
const MODEL_ICONS: Record<string, string> = {
  "claude": "/claude-icon.png",
  "gpt": "/openai-icon.png",
  "o1": "/openai-icon.png",
  "o3": "/openai-icon.png",
  "gemini": "/gemini-icon.png",
};

/**
 * Get the icon path for a harness/model combination.
 * Tries harness first, then model prefix, then returns null.
 */
export function getHarnessIcon(harness: string | null | undefined, model?: string | null): string | null {
  if (harness && HARNESS_ICONS[harness]) {
    return HARNESS_ICONS[harness];
  }
  if (model) {
    for (const [prefix, icon] of Object.entries(MODEL_ICONS)) {
      if (model.toLowerCase().startsWith(prefix)) {
        return icon;
      }
    }
  }
  return null;
}

/** Human-friendly display name for a harness. */
export function getHarnessDisplayName(harness: string | null | undefined): string | null {
  if (!harness || harness === "unknown") return null;
  const names: Record<string, string> = {
    "claude-code": "Claude Code",
    "cursor": "Cursor",
    "codex": "Codex CLI",
    "gemini-cli": "Gemini CLI",
    "opencode": "OpenCode",
    "cline": "Cline",
    "aider": "Aider",
    "trae": "Trae",
  };
  return names[harness] ?? harness;
}
