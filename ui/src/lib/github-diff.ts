/**
 * Fetch a unified diff between two commits via the backend proxy,
 * which uses GitHub App credentials for higher rate limits.
 *
 * Keeps client-side validation to avoid wasted round trips.
 * Returns null if the repo isn't on GitHub or the SHAs aren't valid hex hashes.
 */

const API_BASE = process.env.NEXT_PUBLIC_HIVE_SERVER ?? "/api";

export async function fetchGitHubDiff(
  base: string,
  head: string,
  repoUrl?: string,
): Promise<string | null> {
  if (!repoUrl) return null;

  const match = repoUrl.match(/github\.com\/([^/]+)\/([^/]+)/);
  if (!match) return null;

  const hexRe = /^[0-9a-f]{7,40}(~\d+)?$/i;
  if (!hexRe.test(base) || !hexRe.test(head)) return null;

  const params = new URLSearchParams({ repo_url: repoUrl, base, head });

  try {
    const res = await fetch(`${API_BASE}/diff?${params}`);
    if (!res.ok) return null;
    return await res.text();
  } catch {
    return null;
  }
}
