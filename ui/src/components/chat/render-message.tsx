"use client";

import type { ReactNode, ReactElement } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import { CodeBlock } from "./artifacts/code-block";
import { CsvTable } from "./artifacts/csv-table";
import { MermaidDiagram } from "./artifacts/mermaid-diagram";
import { ChartBlock } from "./artifacts/chart-block";

interface RenderMessageProps {
  text: string;
  validatedMentions: string[];
  renderMention: (id: string) => ReactNode;
}

const MAX_RENDER_LENGTH = 10_000;
const BIDI_CHARS = /[\u200E\u200F\u202A-\u202E\u2066-\u2069]/g;

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function RenderMessage({ text, validatedMentions, renderMention }: RenderMessageProps) {
  let safeText = text.replace(BIDI_CHARS, "");
  if (safeText.length > MAX_RENDER_LENGTH) {
    safeText = safeText.slice(0, MAX_RENDER_LENGTH) + "… (truncated)";
  }
  // tiptap-markdown hard breaks
  safeText = safeText.replace(/\\\n/g, "\n");

  // Preprocess @mentions into markdown links so react-markdown renders them
  if (validatedMentions.length) {
    const mentionRe = new RegExp(
      `@(${validatedMentions.map(escapeRegex).join("|")})\\b`,
      "gi",
    );
    safeText = safeText.replace(mentionRe, (_, id) => `[@${id}](https://hive-mention/${id})`);
  }

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[rehypeKatex]}
      components={{
        // Tight Slack-style paragraphs
        p: ({ children }) => <span className="block">{children}</span>,

        // Block code: extract lang from nested <code>, dispatch to artifact renderers
        pre: ({ children }) => {
          const child = children as ReactElement;
          const className = (child?.props as Record<string, string>)?.className || "";
          const lang = className.match(/language-(\w+)/)?.[1] || "";
          const raw = (child?.props as Record<string, unknown>)?.children;
          const code = String(raw || "").replace(/\n$/, "");

          if (lang === "csv") return <CsvTable code={code} delimiter="," />;
          if (lang === "tsv") return <CsvTable code={code} delimiter={"\t"} />;
          if (lang === "mermaid") return <MermaidDiagram code={code} />;
          if (lang === "chart") return <ChartBlock code={code} />;
          return <CodeBlock lang={lang} code={code} />;
        },

        // Inline code
        code: ({ children }) => (
          <code className="px-1 py-px rounded bg-[var(--color-layer-2)] text-[12px] font-[family-name:var(--font-ibm-plex-mono)]">
            {children}
          </code>
        ),

        // Links + mention pills
        a: ({ href, children }) => {
          if (href?.startsWith("https://hive-mention/")) {
            const id = href.replace("https://hive-mention/", "").toLowerCase();
            return <span>{renderMention(id)}</span>;
          }
          return (
            <a href={href} target="_blank" rel="noopener noreferrer" className="text-[var(--color-accent)] hover:underline">
              {children}
            </a>
          );
        },

        // Tables
        table: ({ children }) => (
          <div className="my-1 rounded-md border border-[var(--color-border)] overflow-x-auto text-[12px]">
            <table className="w-full border-collapse">{children}</table>
          </div>
        ),
        th: ({ children }) => (
          <th className="px-3 py-1.5 text-left font-semibold text-[var(--color-text)] bg-[var(--color-layer-2)] border-b border-[var(--color-border)] whitespace-nowrap">
            {children}
          </th>
        ),
        td: ({ children }) => (
          <td className="px-3 py-1 text-[var(--color-text)] border-b border-[var(--color-border-light)] whitespace-nowrap">
            {children}
          </td>
        ),

        // Lists
        ul: ({ children }) => <ul className="my-1 pl-5 list-disc">{children}</ul>,
        ol: ({ children }) => <ol className="my-1 pl-5 list-decimal">{children}</ol>,
        li: ({ children }) => <li className="leading-snug">{children}</li>,

        // Blockquote
        blockquote: ({ children }) => (
          <blockquote className="my-1 pl-3 border-l-2 border-[var(--color-border)] text-[var(--color-text-secondary)]">
            {children}
          </blockquote>
        ),

        // Inline styles
        strong: ({ children }) => <strong className="font-bold">{children}</strong>,
        em: ({ children }) => <em className="italic">{children}</em>,
      }}
    >
      {safeText}
    </ReactMarkdown>
  );
}
