import { useEffect, useState, useCallback } from "react";

export interface TaskFile {
  path: string;
  type: string;
  size: number;
}

function parseRepo(repoUrl: string): string | null {
  const match = repoUrl.match(/github\.com\/([^/]+\/[^/]+)/);
  return match ? match[1].replace(/\.git$/, "") : null;
}

export function useTaskFiles(repoUrl: string | undefined) {
  const [files, setFiles] = useState<TaskFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [defaultBranch, setDefaultBranch] = useState<string | null>(null);

  const repo = repoUrl ? parseRepo(repoUrl) : null;

  useEffect(() => {
    if (!repo) {
      setFiles([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    fetch(`https://api.github.com/repos/${repo}`)
      .then((res) => {
        if (!res.ok) throw new Error("GitHub API error");
        return res.json();
      })
      .then((repoData) => {
        const branch = repoData.default_branch ?? "main";
        setDefaultBranch(branch);
        return fetch(`https://api.github.com/repos/${repo}/git/trees/${branch}?recursive=1`);
      })
      .then((res) => {
        if (!res.ok) throw new Error("GitHub API error");
        return res.json();
      })
      .then((data) => {
        const blobs = (data.tree ?? [])
          .filter((item: { type: string }) => item.type === "blob")
          .map((item: { path: string; type: string; size?: number }) => ({
            path: item.path,
            type: item.type,
            size: item.size ?? 0,
          }));
        setFiles(blobs);
      })
      .catch(() => setFiles([]))
      .finally(() => setLoading(false));
  }, [repo]);

  const fetchFileContent = useCallback(
    async (path: string): Promise<string | null> => {
      if (!repo) return null;
      try {
        const ref = defaultBranch ? `?ref=${defaultBranch}` : "";
        const res = await fetch(
          `https://api.github.com/repos/${repo}/contents/${encodeURIComponent(path)}${ref}`,
          { headers: { Accept: "application/vnd.github.v3.raw" } }
        );
        if (!res.ok) return null;
        return await res.text();
      } catch {
        return null;
      }
    },
    [repo, defaultBranch]
  );

  return { files, loading, fetchFileContent };
}
