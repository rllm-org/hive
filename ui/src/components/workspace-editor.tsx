"use client";

import { useEffect, useState } from "react";
import { LuX } from "react-icons/lu";
import CodeMirror, { Extension } from "@uiw/react-codemirror";
import { javascript } from "@codemirror/lang-javascript";
import { python } from "@codemirror/lang-python";
import { markdown } from "@codemirror/lang-markdown";
import { json } from "@codemirror/lang-json";
import { oneDark } from "@codemirror/theme-one-dark";

export interface OpenFile {
  path: string;
  name: string;
  content: string;
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
}

export function WorkspaceEditor({ openFiles, activePath, onSelectTab, onCloseTab, onChangeContent }: WorkspaceEditorProps) {
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    const check = () => setIsDark(document.documentElement.classList.contains("dark"));
    check();
    const observer = new MutationObserver(check);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);

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
        {activeFile && (
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
        )}
      </div>
    </div>
  );
}
