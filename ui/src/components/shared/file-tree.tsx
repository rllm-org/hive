"use client";

import { useState, useEffect, useRef } from "react";
import type { FsTreeNode } from "@/hooks/use-workspace-files";

export type { FsTreeNode };

export function FsPromptModal({ title, label, defaultValue, onClose, onSubmit }: {
  title: string;
  label: string;
  defaultValue: string;
  onClose: () => void;
  onSubmit: (value: string) => void | Promise<void>;
}) {
  const [value, setValue] = useState(defaultValue);
  const [submitting, setSubmitting] = useState(false);
  const overlayRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handleEsc);
    return () => window.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  useEffect(() => {
    if (inputRef.current) {
      const dot = defaultValue.lastIndexOf(".");
      if (dot > 0) {
        inputRef.current.setSelectionRange(0, dot);
      } else {
        inputRef.current.select();
      }
    }
  }, [defaultValue]);

  const submit = async () => {
    if (!value.trim()) return;
    setSubmitting(true);
    try { await onSubmit(value.trim()); } finally { setSubmitting(false); }
  };

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-[10000] flex items-center justify-center backdrop-blur-md bg-black/30"
      onClick={(e) => { if (e.target === overlayRef.current) onClose(); }}
    >
      <div className="bg-[var(--color-surface)] shadow-[var(--shadow-elevated)] w-full max-w-[340px] flex flex-col animate-fade-in" style={{ borderRadius: 6 }}>
        <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--color-border)]">
          <h2 className="text-sm font-semibold text-[var(--color-text)]">{title}</h2>
          <button
            onClick={onClose}
            className="w-6 h-6 flex items-center justify-center text-[var(--color-text-tertiary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-2)] transition-all"
          >
            <svg width="12" height="12" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M3 3l8 8M11 3l-8 8" />
            </svg>
          </button>
        </div>
        <div className="px-5 py-4 space-y-3">
          <div>
            <label className="block text-xs font-medium text-[var(--color-text-secondary)] mb-1.5">{label}</label>
            <input
              ref={inputRef}
              type="text"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); submit(); } }}
              className="w-full px-3 py-2 text-sm border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] font-[family-name:var(--font-ibm-plex-mono)]"
              style={{ outline: "none", boxShadow: "none" }}
              autoFocus
            />
          </div>
          <div className="flex items-center justify-end gap-2">
            <button
              onClick={onClose}
              disabled={submitting}
              className="px-3 py-1.5 text-sm font-medium border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-1)] disabled:opacity-50 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={submit}
              disabled={submitting || !value.trim()}
              className="px-3 py-1.5 text-sm font-medium text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] disabled:opacity-50 transition-colors"
            >
              {submitting ? "..." : title === "Rename" ? "Rename" : "Create"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export function FileTree({
  nodes,
  expandedDirs,
  onToggleDir,
  onFileClick,
  onDelete,
  onRename,
  onDownload,
  onNewFile,
  onNewFolder,
}: {
  nodes: FsTreeNode[];
  expandedDirs: Set<string>;
  onToggleDir: (path: string) => void;
  onFileClick: (node: FsTreeNode) => void;
  onDelete?: (path: string) => void;
  onRename?: (path: string) => void;
  onDownload?: (path: string) => void;
  onNewFile?: (directory: string) => void;
  onNewFolder?: (directory: string) => void;
}) {
  return (
    <>
      {nodes.map((node) => (
        <FileTreeNode
          key={node.path}
          node={node}
          expandedDirs={expandedDirs}
          onToggleDir={onToggleDir}
          onFileClick={onFileClick}
          onDelete={onDelete}
          onRename={onRename}
          onDownload={onDownload}
          onNewFile={onNewFile}
          onNewFolder={onNewFolder}
          depth={0}
        />
      ))}
    </>
  );
}

function FileTreeNode({
  node,
  expandedDirs,
  onToggleDir,
  onFileClick,
  onDelete,
  onRename,
  onDownload,
  onNewFile,
  onNewFolder,
  depth = 0,
}: {
  node: FsTreeNode;
  expandedDirs: Set<string>;
  onToggleDir: (path: string) => void;
  onFileClick: (node: FsTreeNode) => void;
  onDelete?: (path: string) => void;
  onRename?: (path: string) => void;
  onDownload?: (path: string) => void;
  onNewFile?: (directory: string) => void;
  onNewFolder?: (directory: string) => void;
  depth?: number;
}) {
  const [menuPos, setMenuPos] = useState<{ x: number; y: number } | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const isDir = node.type === "directory";
  const isExpanded = expandedDirs.has(node.path);

  useEffect(() => {
    if (!menuPos) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuPos(null);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [menuPos]);

  const handleContextMenu = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setMenuPos({ x: e.clientX, y: e.clientY });
  };

  const uploadDir = isDir ? node.path : node.path.includes("/") ? node.path.slice(0, node.path.lastIndexOf("/")) : "";

  const contextMenu = menuPos && (
    <div
      ref={menuRef}
      className="fixed bg-[var(--color-surface)] border border-[var(--color-border)] shadow-lg py-1 min-w-[120px] z-[9999]"
      style={{ borderRadius: 6, left: menuPos.x, top: menuPos.y }}
    >
      {onNewFile && (
        <button onClick={() => { setMenuPos(null); onNewFile(uploadDir); }} className="w-full text-left px-3 py-2 text-sm text-[var(--color-text)] hover:bg-[var(--color-layer-1)]">
          New File
        </button>
      )}
      {onNewFolder && (
        <button onClick={() => { setMenuPos(null); onNewFolder(uploadDir); }} className="w-full text-left px-3 py-2 text-sm text-[var(--color-text)] hover:bg-[var(--color-layer-1)]">
          New Folder
        </button>
      )}
      {(onNewFile || onNewFolder) && (onRename || onDownload || onDelete) && (
        <div className="my-1 border-t border-[var(--color-border)]" />
      )}
      {onRename && (
        <button onClick={() => { setMenuPos(null); onRename(node.path); }} className="w-full text-left px-3 py-2 text-sm text-[var(--color-text)] hover:bg-[var(--color-layer-1)]">
          Rename
        </button>
      )}
      {onDownload && !isDir && (
        <button onClick={() => { setMenuPos(null); onDownload(node.path); }} className="w-full text-left px-3 py-2 text-sm text-[var(--color-text)] hover:bg-[var(--color-layer-1)]">
          Download
        </button>
      )}
      {onDelete && (
        <button onClick={() => { setMenuPos(null); onDelete(node.path); }} className="w-full text-left px-3 py-2 text-sm text-red-500 hover:bg-red-500/10">
          Delete
        </button>
      )}
    </div>
  );

  if (isDir) {
    return (
      <div>
        <button
          onClick={() => onToggleDir(node.path)}
          onContextMenu={handleContextMenu}
          className="group flex items-center gap-1.5 py-0.5 text-xs text-[var(--color-text)] hover:text-[var(--color-accent)] transition-colors text-left w-full min-w-0"
          style={{ paddingLeft: `${depth * 14}px` }}
        >
          <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor" className="shrink-0 opacity-50">
            <path fillRule="evenodd" d="M1.75 1A1.75 1.75 0 000 2.75v10.5C0 14.216.784 15 1.75 15h12.5A1.75 1.75 0 0016 13.25v-8.5A1.75 1.75 0 0014.25 3H7.5a.25.25 0 01-.2-.1l-.9-1.2C6.07 1.26 5.55 1 5 1H1.75z" />
          </svg>
          <span className="font-[family-name:var(--font-ibm-plex-mono)] truncate font-medium">{node.name}</span>
        </button>
        {contextMenu}
        {isExpanded && node.children && (
          <div>
            {node.children.map((child) => (
              <FileTreeNode
                key={child.path}
                node={child}
                expandedDirs={expandedDirs}
                onToggleDir={onToggleDir}
                onFileClick={onFileClick}
                onDelete={onDelete}
                onRename={onRename}
                onDownload={onDownload}
                onNewFile={onNewFile}
                onNewFolder={onNewFolder}
                depth={depth + 1}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <>
      <button
        onClick={() => onFileClick(node)}
        onContextMenu={handleContextMenu}
        className="flex items-center gap-1.5 text-xs text-[var(--color-text)] hover:text-[var(--color-accent)] py-0.5 transition-colors w-full text-left"
        style={{ paddingLeft: `${depth * 14}px` }}
      >
        <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor" className="shrink-0 opacity-50">
          <path fillRule="evenodd" d="M3.75 1.5a.25.25 0 00-.25.25v12.5c0 .138.112.25.25.25h8.5a.25.25 0 00.25-.25V4.664a.25.25 0 00-.073-.177l-2.914-2.914a.25.25 0 00-.177-.073H3.75zM2 1.75C2 .784 2.784 0 3.75 0h5.586c.464 0 .909.184 1.237.513l2.914 2.914c.329.328.513.773.513 1.237v9.586A1.75 1.75 0 0112.25 16h-8.5A1.75 1.75 0 012 14.25V1.75z" />
        </svg>
        <span className="font-[family-name:var(--font-ibm-plex-mono)] truncate">{node.name}</span>
      </button>
      {contextMenu}
    </>
  );
}
