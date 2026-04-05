"use client";

import { useState, useEffect, useCallback } from "react";
import { getAuthHeader } from "@/lib/auth";
import { LuGithub, LuLock, LuGlobe, LuSearch, LuLoader } from "react-icons/lu";

const API_BASE = process.env.NEXT_PUBLIC_HIVE_SERVER ?? "/api";

interface Repo {
  full_name: string;
  name: string;
  private: boolean;
  description: string | null;
  url: string;
  default_branch: string;
  updated_at: string;
}

interface GitHubRepoPickerProps {
  onSelect: (repo: Repo) => void;
  selected?: string | null;
}

export function GitHubRepoPicker({ onSelect, selected }: GitHubRepoPickerProps) {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [installed, setInstalled] = useState(true);
  const [installUrl, setInstallUrl] = useState<string | null>(null);
  const [addRepoUrl, setAddRepoUrl] = useState<string | null>(null);

  const fetchRepos = useCallback(async (p: number) => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${API_BASE}/auth/github/repos?page=${p}&per_page=50`, {
        headers: getAuthHeader(),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error(data?.detail ?? "Failed to fetch repos");
      }
      const data = await res.json();
      setInstalled(data.installed !== false);
      if (p === 1) setRepos(data.repos);
      else setRepos((prev) => [...prev, ...data.repos]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch repos");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchRepos(1); }, [fetchRepos]);

  useEffect(() => {
    fetch(`${API_BASE}/auth/config`).then(r => r.json()).then(d => {
      if (d.github_app_install_url) setAddRepoUrl(d.github_app_install_url);
      if (d.github_agent_app_install_url) setInstallUrl(d.github_agent_app_install_url);
    }).catch(() => {});
  }, []);

  const filtered = search
    ? repos.filter((r) =>
        r.full_name.toLowerCase().includes(search.toLowerCase()) ||
        (r.description ?? "").toLowerCase().includes(search.toLowerCase())
      )
    : repos;

  if (!loading && !installed && (addRepoUrl || installUrl)) {
    return (
      <div className="text-center py-8 border border-dashed border-[var(--color-border)]">
        <LuGithub size={24} className="mx-auto mb-3 text-[var(--color-text-tertiary)]" />
        <p className="text-sm text-[var(--color-text-tertiary)] mb-4">Select which repositories Hive can access</p>
        <a
          href={addRepoUrl || installUrl!}
          className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium bg-[#24292f] text-white hover:bg-[#32383f] dark:bg-white dark:text-black dark:hover:bg-[#e0e0e0] transition-colors"
        >
          <LuGithub size={16} />
          Add repo
        </a>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Search + Add repo */}
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <LuSearch size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-tertiary)]" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search repositories..."
            className="w-full pl-9 pr-3 py-2 text-sm border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] placeholder:text-[var(--color-text-tertiary)] outline-none"
          />
        </div>
        {addRepoUrl && (
          <a
            href={addRepoUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-1)] transition-colors whitespace-nowrap"
          >
            <LuGithub size={12} />
            Add repo
          </a>
        )}
      </div>

      {/* Error */}
      {error && (
        <p className="text-xs text-red-500">{error}</p>
      )}

      {/* Repo list */}
      <div className="max-h-[280px] overflow-y-auto border border-[var(--color-border)] divide-y divide-[var(--color-border)]">
        {loading && repos.length === 0 ? (
          <div className="flex items-center justify-center py-8">
            <LuLoader size={16} className="animate-spin text-[var(--color-text-tertiary)]" />
            <span className="ml-2 text-xs text-[var(--color-text-tertiary)]">Loading repos...</span>
          </div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-8">
            <LuGithub size={20} className="mx-auto mb-2 text-[var(--color-text-tertiary)]" />
            <p className="text-xs text-[var(--color-text-tertiary)]">
              {search ? "No repos match your search" : "No repos found"}
            </p>
          </div>
        ) : (
          filtered.map((repo) => (
            <button
              key={repo.full_name}
              type="button"
              onClick={() => onSelect(repo)}
              className={`w-full text-left px-3 py-2.5 hover:bg-[var(--color-layer-1)] transition-colors ${
                selected === repo.full_name ? "bg-[var(--color-accent)]/10 border-l-2 border-l-[var(--color-accent)]" : ""
              }`}
            >
              <div className="flex items-center gap-2">
                {repo.private ? (
                  <LuLock size={12} className="text-[var(--color-text-tertiary)] shrink-0" />
                ) : (
                  <LuGlobe size={12} className="text-[var(--color-text-tertiary)] shrink-0" />
                )}
                <span className="text-sm font-medium text-[var(--color-text)] truncate">
                  {repo.full_name}
                </span>
              </div>
              {repo.description && (
                <p className="text-xs text-[var(--color-text-tertiary)] mt-0.5 truncate ml-5">
                  {repo.description}
                </p>
              )}
            </button>
          ))
        )}
      </div>

      {/* Load more */}
      {!loading && repos.length >= page * 50 && (
        <button
          type="button"
          onClick={() => { setPage((p) => p + 1); fetchRepos(page + 1); }}
          className="w-full py-1.5 text-xs text-[var(--color-accent)] hover:underline"
        >
          Load more repos
        </button>
      )}

      {/* Agent authorization hint */}
      {installUrl && (
        <p className="text-xs text-[var(--color-text-tertiary)] mt-1">
          To connect your agents, <a
            href={installUrl.replace("select_target", "new")}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[var(--color-accent)] hover:underline"
          >install the Hive App</a> on your repo.
        </p>
      )}
    </div>
  );
}
