/**
 * Fetch a unified diff between two commits from GitHub's compare API.
 *
 * Parses owner/repo from the task's repo_url and uses base/head as
 * commit SHAs. Returns null if the repo isn't on GitHub or the
 * SHAs aren't valid hex hashes.
 */

export async function fetchGitHubDiff(
  base: string,
  head: string,
  repoUrl?: string,
): Promise<string | null> {
  if (!repoUrl) return null;

  const match = repoUrl.match(/github\.com\/([^/]+)\/([^/]+)/);
  if (!match) return null;

  const owner = match[1];
  const repo = match[2].replace(/\.git$/, "");

  const hexRe = /^[0-9a-f]{7,40}(~\d+)?$/i;
  if (!hexRe.test(base) || !hexRe.test(head)) return null;

  // Use short SHAs (12 chars) — GitHub's unauthenticated API sometimes 404s on full SHAs
  const shortBase = base.length > 12 && !base.includes("~") ? base.slice(0, 12) : base;
  const shortHead = head.length > 12 && !head.includes("~") ? head.slice(0, 12) : head;
  const url = `https://api.github.com/repos/${owner}/${repo}/compare/${shortBase}...${shortHead}`;

  try {
    const res = await fetch(url, {
      headers: {
        Accept: "application/vnd.github.v3.diff",
      },
    });
    if (!res.ok) return null;
    return await res.text();
  } catch {
    return null;
  }
}
