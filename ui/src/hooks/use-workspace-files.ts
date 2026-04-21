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
  sandboxId: string | null,
) {
  const [tree, setTree] = useState<FsTreeNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sandboxIdRef = useRef<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  /* Load tree for the workspace-scoped sandbox. Keyed on sandboxId so
     switching agents (which share the sandbox) is a no-op. */
  useEffect(() => {
    if (!sdkBaseUrl || !sandboxId) return;
    sandboxIdRef.current = sandboxId;

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    (async () => {
      setLoading(true);
      setError(null);
      try {
        await fetchTree(sdkBaseUrl, sandboxId, ctrl.signal);

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
  }, [sdkBaseUrl, sandboxId]); // eslint-disable-line react-hooks/exhaustive-deps

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

  /* Edit a file (string replacement or write) */
  const editFile = useCallback(
    async (
      path: string,
      oldString: string,
      newString: string,
      replaceAll?: boolean,
    ): Promise<{ ok: boolean; error?: string }> => {
      const sbxId = sandboxIdRef.current;
      if (!sdkBaseUrl || !sbxId) return { ok: false, error: "not connected" };
      const body: Record<string, unknown> = {
        path,
        old_string: oldString,
        new_string: newString,
      };
      if (replaceAll) body.replace_all = true;
      const resp = await fetch(
        `${sdkBaseUrl}/sandboxes/${sbxId}/files/edit`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
      );
      const data = await resp.json();
      if (!resp.ok) return { ok: false, error: data.error ?? `HTTP ${resp.status}` };
      return { ok: true };
    },
    [sdkBaseUrl],
  );

  /* Upload files (base64-encoded) */
  const uploadFiles = useCallback(
    async (files: File[], directory?: string): Promise<{ ok: boolean; error?: string }> => {
      const sbxId = sandboxIdRef.current;
      if (!sdkBaseUrl || !sbxId) return { ok: false, error: "not connected" };
      for (const file of files) {
        const buf = await file.arrayBuffer();
        const bytes = new Uint8Array(buf);
        let binary = "";
        for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
        const base64 = btoa(binary);
        const filePath = directory ? `${directory}/${file.name}` : file.name;
        const resp = await fetch(
          `${sdkBaseUrl}/sandboxes/${sbxId}/files/upload`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ path: filePath, content: base64 }),
          },
        );
        if (!resp.ok) {
          const data = await resp.json().catch(() => ({}));
          return { ok: false, error: data.error ?? `HTTP ${resp.status}` };
        }
      }
      return { ok: true };
    },
    [sdkBaseUrl],
  );

  /* Delete a file or directory */
  const deleteFile = useCallback(
    async (filePath: string): Promise<{ ok: boolean; error?: string }> => {
      const sbxId = sandboxIdRef.current;
      if (!sdkBaseUrl || !sbxId) return { ok: false, error: "not connected" };
      const resp = await fetch(
        `${sdkBaseUrl}/sandboxes/${sbxId}/files/delete`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: filePath }),
        },
      );
      const data = await resp.json();
      if (!resp.ok) return { ok: false, error: data.error ?? `HTTP ${resp.status}` };
      return { ok: true };
    },
    [sdkBaseUrl],
  );

  /* Rename / move a file or directory */
  const renameFile = useCallback(
    async (filePath: string, newPath: string): Promise<{ ok: boolean; error?: string }> => {
      const sbxId = sandboxIdRef.current;
      if (!sdkBaseUrl || !sbxId) return { ok: false, error: "not connected" };
      const resp = await fetch(
        `${sdkBaseUrl}/sandboxes/${sbxId}/files/rename`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: filePath, new_path: newPath }),
        },
      );
      const data = await resp.json();
      if (!resp.ok) return { ok: false, error: data.error ?? `HTTP ${resp.status}` };
      return { ok: true };
    },
    [sdkBaseUrl],
  );

  /* Download a file (triggers browser save) */
  const downloadFile = useCallback(
    async (filePath: string): Promise<void> => {
      const sbxId = sandboxIdRef.current;
      if (!sdkBaseUrl || !sbxId) return;
      const resp = await fetch(
        `${sdkBaseUrl}/sandboxes/${sbxId}/files/download?path=${encodeURIComponent(filePath)}`,
      );
      if (!resp.ok) return;
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filePath.split("/").pop() || "download";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    },
    [sdkBaseUrl],
  );

  /* Force-refresh tree now */
  const refresh = useCallback(async () => {
    const sbxId = sandboxIdRef.current;
    if (!sdkBaseUrl || !sbxId) return;
    await fetchTree(sdkBaseUrl, sbxId);
  }, [sdkBaseUrl]); // eslint-disable-line react-hooks/exhaustive-deps

  return { tree, loading, error, readFile, editFile, uploadFiles, deleteFile, renameFile, downloadFile, refresh };
}
