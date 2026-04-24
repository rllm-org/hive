/**
 * Build-time agent-sdk base URL.
 *
 * Set via `NEXT_PUBLIC_AGENT_SDK_BASE_URL` in the UI's env (`.env.local` in
 * dev, CI/deploy config in prod). Next.js inlines `NEXT_PUBLIC_*` vars into
 * the client bundle, so this is a constant — no runtime lookup, no /config
 * fetch. Changing the URL requires a rebuild, which matches reality: the
 * agent-sdk deployment URL only changes with infrastructure work.
 *
 * Server-side hive code uses a separate env var (`AGENT_SDK_BASE_URL`) in
 * `hive/server/agent_sdk_client.py` — different value in dev (localhost)
 * vs prod, and must never leak to the browser.
 */
export const SDK_BASE =
  (process.env.NEXT_PUBLIC_AGENT_SDK_BASE_URL ?? "").replace(/\/+$/, "");

if (!SDK_BASE && typeof window !== "undefined") {
  // Visible in prod builds missing the env var — loud, single-line.
  console.warn(
    "[sdk] NEXT_PUBLIC_AGENT_SDK_BASE_URL not set; agent-sdk calls will fail"
  );
}

export function sdkUrl(path: string): string {
  return `${SDK_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}
