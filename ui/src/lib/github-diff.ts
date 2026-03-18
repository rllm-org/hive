/**
 * Fetch a unified diff between two commits via the backend proxy,
 * which uses GitHub App credentials for higher rate limits.
 *
 * Keeps client-side validation to avoid wasted round trips.
 * Returns null if the repo isn't on GitHub or the SHAs aren't valid hex hashes.
 */

const API_BASE = process.env.NEXT_PUBLIC_HIVE_SERVER ?? "/api";

export type DiffResult =
  | { status: "ok"; diff: string }
  | { status: "rate_limited" }
  | { status: "error" };

export function getGitHubCompareUrl(
  repoUrl: string,
  base: string,
  head: string,
): string {
  const short = (s: string) => (s.length > 12 && !s.includes("~") ? s.slice(0, 12) : s);
  return `${repoUrl}/compare/${short(base)}...${short(head)}`;
}

export async function fetchGitHubDiff(
  base: string,
  head: string,
  repoUrl?: string,
): Promise<DiffResult> {
  if (!repoUrl) return { status: "error" };

  const match = repoUrl.match(/github\.com\/([^/]+)\/([^/]+)/);
  if (!match) return { status: "error" };

  const hexRe = /^[0-9a-f]{7,40}(~\d+)?$/i;
  if (!hexRe.test(base) || !hexRe.test(head)) return { status: "error" };

  const params = new URLSearchParams({ repo_url: repoUrl, base, head });

  try {
    const res = await fetch(`${API_BASE}/diff?${params}`);
    if (res.status === 429) return { status: "rate_limited" };
    if (!res.ok) return { status: "error" };
    return { status: "ok", diff: await res.text() };
  } catch {
    return { status: "error" };
  }
}
