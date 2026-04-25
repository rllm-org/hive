"use client";

import { useState, useCallback } from "react";
import { WorkspaceEditor, type OpenFile } from "@/components/workspace-editor";
import { FileTree, type FsTreeNode } from "@/components/shared/file-tree";

interface FileExplorerProps {
  tree: FsTreeNode[];
  onReadFile?: (path: string) => Promise<{ content: string } | undefined>;
  onEditFile?: (path: string, content: string) => Promise<void>;
  onDelete?: (path: string) => void;
  onRename?: (path: string) => void;
  onDownload?: (path: string) => void;
  onNewFile?: (directory: string) => void;
  onNewFolder?: (directory: string) => void;
  loading?: boolean;
  treeWidth?: number;
}

export function FileExplorer({
  tree,
  onReadFile,
  onEditFile,
  onDelete,
  onRename,
  onDownload,
  onNewFile,
  onNewFolder,
  loading,
  treeWidth = 240,
}: FileExplorerProps) {
  const [openFiles, setOpenFiles] = useState<OpenFile[]>([]);
  const [activePath, setActivePath] = useState<string | null>(null);
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(() => {
    const dirs = new Set<string>();
    const walk = (nodes: FsTreeNode[]) => {
      for (const n of nodes) {
        if (n.type === "directory") {
          dirs.add(n.path);
          if (n.children) walk(n.children);
        }
      }
    };
    walk(tree);
    return dirs;
  });

  const handleToggleDir = useCallback((path: string) => {
    setExpandedDirs((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path); else next.add(path);
      return next;
    });
  }, []);

  const handleFileClick = useCallback(async (node: FsTreeNode) => {
    if (node.type === "directory") return;

    if (openFiles.some((f) => f.path === node.path)) {
      setActivePath(node.path);
      return;
    }

    let content = "";
    if (onReadFile) {
      const result = await onReadFile(node.path);
      console.log("[FileExplorer] readFile result:", node.path, { contentLength: result?.content?.length, contentStart: result?.content?.substring(0, 80), keys: result ? Object.keys(result) : null });
      if (result) content = result.content;
    }

    setOpenFiles((prev) => [...prev, { path: node.path, name: node.name, content }]);
    setActivePath(node.path);
  }, [openFiles, onReadFile]);

  const handleCloseTab = useCallback((path: string) => {
    setOpenFiles((prev) => prev.filter((f) => f.path !== path));
    if (activePath === path) {
      const remaining = openFiles.filter((f) => f.path !== path);
      setActivePath(remaining.length > 0 ? remaining[remaining.length - 1].path : null);
    }
  }, [activePath, openFiles]);

  const handleChangeContent = useCallback((path: string, content: string) => {
    setOpenFiles((prev) => prev.map((f) => f.path === path ? { ...f, content } : f));
    if (onEditFile) onEditFile(path, content);
  }, [onEditFile]);

  return (
    <div className="flex-1 min-h-0 flex">
      <div
        className="shrink-0 border-r border-[var(--color-border)] bg-[var(--color-surface)] overflow-y-auto py-2 pl-5"
        style={{ width: treeWidth, minWidth: treeWidth }}
      >
        {loading ? (
          <div className="text-xs text-[var(--color-text-tertiary)] px-2 py-1">Loading...</div>
        ) : tree.length === 0 ? (
          <div className="text-xs text-[var(--color-text-tertiary)] px-2 py-1">No files</div>
        ) : (
          <FileTree
            nodes={tree}
            expandedDirs={expandedDirs}
            onToggleDir={handleToggleDir}
            onFileClick={handleFileClick}
            onDelete={onDelete}
            onRename={onRename}
            onDownload={onDownload}
            onNewFile={onNewFile}
            onNewFolder={onNewFolder}
          />
        )}
      </div>
      <div className="flex-1 min-w-0 flex flex-col bg-[var(--color-bg)] overflow-hidden">
        {openFiles.length > 0 ? (
          <WorkspaceEditor
            openFiles={openFiles}
            activePath={activePath}
            onSelectTab={setActivePath}
            onCloseTab={handleCloseTab}
            onChangeContent={handleChangeContent}
          />
        ) : (
          <div className="flex-1 flex items-center justify-center text-[13px] text-[var(--color-text-tertiary)]">
            Select a file to view
          </div>
        )}
      </div>
    </div>
  );
}
