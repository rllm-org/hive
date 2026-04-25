"use client";

import { useEffect, useMemo, useState } from "react";
import { LuX } from "react-icons/lu";
import CodeMirror, { Extension } from "@uiw/react-codemirror";
import { javascript } from "@codemirror/lang-javascript";
import { python } from "@codemirror/lang-python";
import { markdown } from "@codemirror/lang-markdown";
import { json } from "@codemirror/lang-json";
import { oneDark } from "@codemirror/theme-one-dark";
import DocViewer, { DocViewerRenderers } from "react-doc-viewer";

export interface OpenFile {
  path: string;
  name: string;
  content: string;
  image?: boolean;
  pdf?: boolean;
  binary?: boolean;
}

function getLanguageExtension(filename: string): Extension[] {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  if (["js", "jsx", "ts", "tsx", "mjs", "cjs"].includes(ext)) {
    return [javascript({ jsx: ext.endsWith("x"), typescript: ext.startsWith("t") })];
  }
  if (ext === "py") return [python()];
  if (["md", "markdown"].includes(ext)) return [markdown()];
  if (ext === "json") return [json()];
  return [];
}

interface WorkspaceEditorProps {
  openFiles: OpenFile[];
  activePath: string | null;
  onSelectTab: (path: string) => void;
  onCloseTab: (path: string) => void;
  onChangeContent: (path: string, content: string) => void;
  onSave?: (path: string, content: string) => Promise<void>;
}

export function WorkspaceEditor({ openFiles, activePath, onSelectTab, onCloseTab, onChangeContent, onSave }: WorkspaceEditorProps) {
  const [isDark, setIsDark] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const check = () => setIsDark(document.documentElement.classList.contains("dark"));
    check();
    const observer = new MutationObserver(check);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);

  // Cmd+S / Ctrl+S save handler
  useEffect(() => {
    if (!onSave) return;
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "s") {
        e.preventDefault();
        const file = openFiles.find((f) => f.path === activePath);
        if (file && !saving) {
          setSaving(true);
          onSave(file.path, file.content).finally(() => setSaving(false));
        }
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onSave, openFiles, activePath, saving]);

  const activeFile = openFiles.find((f) => f.path === activePath) ?? null;

  if (openFiles.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center">
        <svg className="w-8 h-8 text-[var(--color-text-tertiary)] mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
        <p className="text-sm text-[var(--color-text-tertiary)]">Click a file to open it</p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {/* Tab bar */}
      <div className="shrink-0 flex items-stretch border-b border-[var(--color-border)] bg-[var(--color-layer-1)] overflow-x-auto">
        {saving && (
          <div className="flex items-center px-2 text-[10px] text-[var(--color-text-tertiary)]">Saving…</div>
        )}
        {openFiles.map((f) => {
          const isActive = f.path === activePath;
          return (
            <div
              key={f.path}
              onClick={() => onSelectTab(f.path)}
              className={`group flex items-center gap-2 pl-3 pr-1.5 py-2 text-xs cursor-pointer border-r border-[var(--color-border)] transition-colors min-w-0 ${
                isActive
                  ? "bg-[var(--color-surface)] text-[var(--color-text)]"
                  : "text-[var(--color-text-secondary)] hover:bg-[var(--color-layer-2)]"
              }`}
            >
              <span className="font-[family-name:var(--font-ibm-plex-mono)] truncate">{f.name}</span>
              <button
                onClick={(e) => { e.stopPropagation(); onCloseTab(f.path); }}
                className={`w-4 h-4 flex items-center justify-center rounded text-[var(--color-text-tertiary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-2)] transition-opacity ${
                  isActive ? "opacity-100" : "opacity-0 group-hover:opacity-100"
                }`}
              >
                <LuX size={11} />
              </button>
            </div>
          );
        })}
      </div>

      {/* Editor */}
      <div className="flex-1 min-h-0 overflow-auto">
        {activeFile && (activeFile.image || activeFile.pdf || activeFile.binary) ? (
          <DocViewerPane file={activeFile} />
        ) : activeFile ? (
          <CodeMirror
            key={activeFile.path}
            value={activeFile.content}
            onChange={(value) => onChangeContent(activeFile.path, value)}
            extensions={getLanguageExtension(activeFile.name)}
            theme={isDark ? oneDark : "light"}
            height="100%"
            style={{ height: "100%", fontSize: 13 }}
            basicSetup={{
              lineNumbers: true,
              foldGutter: true,
              highlightActiveLine: true,
              highlightActiveLineGutter: true,
            }}
          />
        ) : null}
      </div>
    </div>
  );
}

function mimeFromName(name: string): string {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  const map: Record<string, string> = {
    png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", gif: "image/gif",
    bmp: "image/bmp", svg: "image/svg+xml", webp: "image/webp", tiff: "image/tiff",
    pdf: "application/pdf", csv: "text/csv",
  };
  return map[ext] ?? "application/octet-stream";
}

function DocViewerPane({ file }: { file: OpenFile }) {
  const docs = useMemo(() => {
    const mime = mimeFromName(file.name);
    const uri = `data:${mime};base64,${file.content}`;
    const ext = file.name.split(".").pop()?.toLowerCase();
    return [{ uri, fileType: ext, fileName: file.name }];
  }, [file.name, file.content]);

  return (
    <DocViewer
      documents={docs}
      pluginRenderers={DocViewerRenderers}
      config={{ header: { disableHeader: true } }}
      style={{ height: "100%" }}
    />
  );
}
