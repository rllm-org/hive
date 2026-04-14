"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function Markdown({ children, className = "" }: { children: string; className?: string }) {
  return (
    <div className={`break-words [&>*:first-child]:mt-0 [&>*:last-child]:mb-0 ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          table: ({ children }) => <div className="my-2 overflow-x-auto"><table className="text-xs border-collapse w-full">{children}</table></div>,
          th: ({ children }) => <th className="border border-[var(--color-border)] px-2 py-1 bg-[var(--color-layer-1)] font-semibold text-left">{children}</th>,
          td: ({ children }) => <td className="border border-[var(--color-border)] px-2 py-1">{children}</td>,
          p: ({ children }) => <p className="my-0 leading-snug [&:not(:first-child)]:mt-1">{children}</p>,
          pre: ({ children }) => <pre className="my-2 p-3 rounded-lg bg-[var(--color-layer-1)] overflow-x-auto text-xs leading-relaxed">{children}</pre>,
          code: ({ children, className: cn }) =>
            cn ? (
              <code className={cn}>{children}</code>
            ) : (
              <code className="px-1 py-0.5 rounded bg-[var(--color-layer-1)] text-xs font-[family-name:var(--font-ibm-plex-mono)]">{children}</code>
            ),
          a: ({ href, children }) => (
            <span
              role="link"
              className="text-[var(--color-accent)] hover:underline cursor-pointer"
              onClick={(e) => { e.preventDefault(); e.stopPropagation(); if (href) window.open(href, "_blank", "noopener,noreferrer"); }}
            >{children}</span>
          ),
          ul: ({ children }) => <ul className="my-1 pl-5 list-disc">{children}</ul>,
          ol: ({ children }) => <ol className="my-1 pl-5 list-decimal">{children}</ol>,
          li: ({ children }) => <li className="leading-snug [&>p]:my-0">{children}</li>,
          h1: ({ children }) => <h1 className="text-base font-bold mt-3 mb-1.5">{children}</h1>,
          h2: ({ children }) => <h2 className="text-sm font-bold mt-3 mb-1">{children}</h2>,
          h3: ({ children }) => <h3 className="text-sm font-semibold mt-2 mb-1">{children}</h3>,
          blockquote: ({ children }) => <blockquote className="border-l-2 border-[var(--color-border)] pl-3 my-2 text-[var(--color-text-secondary)]">{children}</blockquote>,
          strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
