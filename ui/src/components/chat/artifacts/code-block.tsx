"use client";

import { useEffect, useState, useRef } from "react";

interface CodeBlockProps {
  lang: string;
  code: string;
}

let highlighterPromise: Promise<import("shiki").Highlighter> | null = null;

function getHighlighter() {
  if (!highlighterPromise) {
    highlighterPromise = import("shiki").then((mod) =>
      mod.createHighlighter({
        themes: ["github-light", "github-dark"],
        langs: [
          "python", "javascript", "typescript", "bash", "shell", "json",
          "yaml", "toml", "sql", "html", "css", "rust", "go", "java",
          "c", "cpp", "ruby", "php", "swift", "kotlin", "r", "lua",
          "dockerfile", "graphql", "xml", "markdown", "diff",
        ],
      }),
    );
  }
  return highlighterPromise;
}

export function CodeBlock({ lang, code }: CodeBlockProps) {
  const [html, setHtml] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => {
    let cancelled = false;
    getHighlighter().then((highlighter) => {
      if (cancelled) return;
      const loaded = highlighter.getLoadedLanguages();
      const language = lang && loaded.includes(lang as never) ? lang : "text";
      const result = highlighter.codeToHtml(code, {
        lang: language,
        themes: { light: "github-light", dark: "github-dark" },
        defaultColor: false,
      });
      setHtml(result.replace(/background-color:[^;"]+;?/g, ""));
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [lang, code]);

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => setCopied(false), 1500);
  };

  const label = lang && lang !== "text" ? lang : null;

  if (!html) {
    return (
      <pre className="my-1 px-3 py-2 rounded-md bg-[var(--color-layer-2)] overflow-x-auto text-[12px] font-[family-name:var(--font-ibm-plex-mono)] leading-snug whitespace-pre relative group">
        {label && (
          <span className="absolute top-1.5 left-3 text-[10px] text-[var(--color-text-tertiary)] select-none">
            {label}
          </span>
        )}
        <code className={label ? "block pt-4" : ""}>{code}</code>
        <button
          onClick={handleCopy}
          className="absolute top-1.5 right-2 text-[11px] text-[var(--color-text-tertiary)] hover:text-[var(--color-text)] opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer"
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </pre>
    );
  }

  return (
    <div className="my-1 rounded-md bg-[var(--color-layer-2)] overflow-x-auto relative group">
      {label && (
        <span className="absolute top-1.5 left-3 text-[10px] text-[var(--color-text-tertiary)] select-none z-10">
          {label}
        </span>
      )}
      <button
        onClick={handleCopy}
        className="absolute top-1.5 right-2 text-[11px] text-[var(--color-text-tertiary)] hover:text-[var(--color-text)] opacity-0 group-hover:opacity-100 transition-opacity z-10 cursor-pointer"
      >
        {copied ? "Copied" : "Copy"}
      </button>
      <div
        className={`shiki-code text-[12px] leading-snug ${label ? "pt-5" : ""}`}
        dangerouslySetInnerHTML={{ __html: html }}
      />
    </div>
  );
}
