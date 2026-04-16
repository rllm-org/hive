"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/* ── Types matching the agent-sdk /sandboxes/{id}/files/* endpoints ── */

export interface FsTreeNode {
  name: string;
  path: string;
  type: "file" | "directory";
  size?: number;
  children?: FsTreeNode[];
}

export interface FileContent {
  name: string;
  path: string;
  size: number;
  content: string;
  binary?: boolean;
  image?: boolean;
  pdf?: boolean;
}

/* ── Hook ── */

const TREE_POLL_MS = 15_000;

export function useWorkspaceFiles(
  sdkBaseUrl: string | null,
  sessionId: string | null,
) {
  const [tree, setTree] = useState<FsTreeNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sandboxIdRef = useRef<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  /* Resolve sandbox_id from session status, then load tree */
  useEffect(() => {
    if (!sdkBaseUrl || !sessionId) return;

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    (async () => {
      setLoading(true);
      setError(null);
      try {
        // 1. Get sandbox_id from session status
        const statusResp = await fetch(
          `${sdkBaseUrl}/sessions/${sessionId}/status`,
          { signal: ctrl.signal },
        );
        if (!statusResp.ok)
          throw new Error(`status ${statusResp.status}`);
        const status = await statusResp.json();
        const sbxId = status.sandbox_id as string | undefined;
        if (!sbxId) throw new Error("no sandbox_id in session status");
        sandboxIdRef.current = sbxId;

        // 2. Load tree
        await fetchTree(sdkBaseUrl, sbxId, ctrl.signal);

        // 3. Start polling
        if (pollRef.current) clearInterval(pollRef.current);
        pollRef.current = setInterval(() => {
          if (sandboxIdRef.current) {
            fetchTree(sdkBaseUrl, sandboxIdRef.current).catch(() => {});
          }
        }, TREE_POLL_MS);
      } catch (e) {
        if (!ctrl.signal.aborted) {
          setError(e instanceof Error ? e.message : String(e));
        }
      } finally {
        if (!ctrl.signal.aborted) setLoading(false);
      }
    })();

    return () => {
      ctrl.abort();
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [sdkBaseUrl, sessionId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function fetchTree(
    base: string,
    sbxId: string,
    signal?: AbortSignal,
  ) {
    const resp = await fetch(`${base}/sandboxes/${sbxId}/files/tree`, {
      signal,
    });
    if (!resp.ok) throw new Error(`tree ${resp.status}`);
    const data: FsTreeNode[] = await resp.json();
    setTree(data);
  }

  /* Read a single file */
  const readFile = useCallback(
    async (path: string): Promise<FileContent | null> => {
      const sbxId = sandboxIdRef.current;
      if (!sdkBaseUrl || !sbxId) return null;
      const resp = await fetch(
        `${sdkBaseUrl}/sandboxes/${sbxId}/files/read?path=${encodeURIComponent(path)}`,
      );
      if (!resp.ok) throw new Error(`read ${resp.status}`);
      return (await resp.json()) as FileContent;
    },
    [sdkBaseUrl],
  );

  /* Force-refresh tree now */
  const refresh = useCallback(async () => {
    const sbxId = sandboxIdRef.current;
    if (!sdkBaseUrl || !sbxId) return;
    await fetchTree(sdkBaseUrl, sbxId);
  }, [sdkBaseUrl]); // eslint-disable-line react-hooks/exhaustive-deps

  return { tree, loading, error, readFile, refresh };
}
