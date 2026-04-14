"use client";

import type { ReactNode } from "react";

/**
 * Hand-rolled tight markdown renderer for chat messages.
 *
 * Supports a Slack/CommonMark-flavored subset:
 *   block:  ```code block```, > blockquote, - bullet list, 1. numbered list, paragraph
 *   inline: **bold**, *italic*, `inline code`, [text](url), bare URL, @mention
 *
 * Why hand-rolled instead of react-markdown:
 *   - Tight by default — no `<p>` wrapping for normal lines, no nested-margin spec fights
 *   - Single source of styling, no Tailwind utility specificity issues
 *   - We control the exact subset (no headings, no tables, no nested lists)
 *
 * Mentions are rendered inline as colored pills using the `validatedMentions`
 * array (only validated agent IDs become pills; typos stay as plain text).
 */

interface RenderMessageProps {
  text: string;
  validatedMentions: string[];
  renderMention: (id: string) => ReactNode;
}

const MAX_RENDER_LENGTH = 10_000;
const BIDI_CHARS = /[\u200E\u200F\u202A-\u202E\u2066-\u2069]/g;

export function RenderMessage({ text, validatedMentions, renderMention }: RenderMessageProps) {
  let safeText = text.replace(BIDI_CHARS, "");
  if (safeText.length > MAX_RENDER_LENGTH) {
    safeText = safeText.slice(0, MAX_RENDER_LENGTH) + "… (truncated)";
  }
  // CommonMark hard line breaks: tiptap-markdown serializes a newline-within-paragraph
  // as `\<newline>`. Treat that as a regular line break for display.
  safeText = safeText.replace(/\\\n/g, "\n");
  const blocks = parseBlocks(safeText, validatedMentions, renderMention);
  return <>{blocks}</>;
}

/* ─────────────── Block-level parser ─────────────── */

function parseBlocks(
  text: string,
  validMentions: string[],
  renderMention: (id: string) => ReactNode,
): ReactNode[] {
  const out: ReactNode[] = [];
  let key = 0;
  // First split out fenced code blocks (``` ... ```), preserving everything else
  const CODE_FENCE = /```([a-zA-Z0-9_+-]*)\n?([\s\S]*?)```/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = CODE_FENCE.exec(text)) !== null) {
    if (m.index > last) {
      out.push(...parseLines(text.slice(last, m.index), key, validMentions, renderMention));
      key += 100;
    }
    const code = m[2].replace(/\n$/, "");
    out.push(
      <pre
        key={`pre-${key++}`}
        className="my-1 px-3 py-2 rounded-md bg-[var(--color-layer-2)] overflow-x-auto text-[12px] font-[family-name:var(--font-ibm-plex-mono)] leading-snug whitespace-pre"
      >
        <code>{code}</code>
      </pre>,
    );
    last = m.index + m[0].length;
  }
  if (last < text.length) {
    out.push(...parseLines(text.slice(last), key, validMentions, renderMention));
  }
  return out;
}

function parseLines(
  text: string,
  keyOffset: number,
  validMentions: string[],
  renderMention: (id: string) => ReactNode,
): ReactNode[] {
  const out: ReactNode[] = [];
  const lines = text.split("\n");
  let i = 0;
  let key = keyOffset;

  // Helper: render a run of normal text lines (joined with line breaks)
  const flushParagraph = (paraLines: string[]) => {
    if (paraLines.length === 0) return;
    const inline: ReactNode[] = [];
    paraLines.forEach((line, idx) => {
      if (idx > 0) inline.push(<br key={`br-${key++}`} />);
      inline.push(...parseInline(line, key, validMentions, renderMention));
      key += 100;
    });
    out.push(
      <span key={`p-${key++}`} className="block">
        {inline}
      </span>,
    );
  };

  while (i < lines.length) {
    const line = lines[i];
    // Skip blank lines (they're absorbed as paragraph separators)
    if (line.trim() === "") {
      i++;
      continue;
    }
    // Blockquote: consecutive `> ` lines
    if (line.startsWith("> ") || line === ">") {
      const quoteLines: string[] = [];
      while (i < lines.length && (lines[i].startsWith("> ") || lines[i] === ">")) {
        quoteLines.push(lines[i].replace(/^> ?/, ""));
        i++;
      }
      const inline: ReactNode[] = [];
      quoteLines.forEach((qline, idx) => {
        if (idx > 0) inline.push(<br key={`qbr-${key++}`} />);
        inline.push(...parseInline(qline, key, validMentions, renderMention));
        key += 100;
      });
      out.push(
        <blockquote
          key={`bq-${key++}`}
          className="my-1 pl-3 border-l-2 border-[var(--color-border)] text-[var(--color-text-secondary)]"
        >
          {inline}
        </blockquote>,
      );
      continue;
    }
    // Bullet list: consecutive `- ` or `* ` lines
    if (/^[-*] /.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*] /.test(lines[i])) {
        items.push(lines[i].slice(2));
        i++;
      }
      out.push(
        <ul key={`ul-${key++}`} className="my-1 pl-5 list-disc">
          {items.map((item, idx) => (
            <li key={`li-${idx}`} className="leading-snug">
              {parseInline(item, key + idx, validMentions, renderMention)}
            </li>
          ))}
        </ul>,
      );
      key += items.length;
      continue;
    }
    // Numbered list: consecutive `1. ` lines
    if (/^\d+\.\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s/.test(lines[i])) {
        items.push(lines[i].replace(/^\d+\.\s/, ""));
        i++;
      }
      out.push(
        <ol key={`ol-${key++}`} className="my-1 pl-5 list-decimal">
          {items.map((item, idx) => (
            <li key={`li-${idx}`} className="leading-snug">
              {parseInline(item, key + idx, validMentions, renderMention)}
            </li>
          ))}
        </ol>,
      );
      key += items.length;
      continue;
    }
    // Normal paragraph: consume consecutive non-blank, non-special lines
    const paraLines: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !lines[i].startsWith("> ") &&
      lines[i] !== ">" &&
      !/^[-*] /.test(lines[i]) &&
      !/^\d+\.\s/.test(lines[i])
    ) {
      paraLines.push(lines[i]);
      i++;
    }
    flushParagraph(paraLines);
  }

  return out;
}

/* ─────────────── Inline parser ─────────────── */

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Parses one line of inline markdown:
 *   **bold**, *italic*, `code`, [text](url), bare URL, @mention
 */
function parseInline(
  text: string,
  keyOffset: number,
  validMentions: string[],
  renderMention: (id: string) => ReactNode,
): ReactNode[] {
  const nodes: ReactNode[] = [];
  let key = keyOffset;

  // Build a single combined regex. Order matters:
  //   1. **bold**
  //   2. `code`
  //   3. [text](url)
  //   4. bare URL
  //   5. @mention (only if name is in validMentions, case-insensitive)
  //   6. *italic*
  // We can't capture mentions via the regex alone — we filter them after
  // matching against validMentions.
  const mentionAlt = validMentions.length
    ? `|@(${validMentions.map(escapeRegex).join("|")})\\b`
    : "";
  const RE = new RegExp(
    `(\\*\\*([^*\\n]+?)\\*\\*)` +
      `|(\`([^\`\\n]+?)\`)` +
      `|(\\[([^\\]]+)\\]\\((https?:\\/\\/[^\\s)]+)\\))` +
      `|(https?:\\/\\/[^\\s<>"'\\])]+)` +
      mentionAlt +
      `|(\\*([^*\\n]+?)\\*)`,
    "gi",
  );

  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = RE.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    if (m[1]) {
      // **bold**
      nodes.push(
        <strong key={`b-${key++}`} className="font-bold">
          {m[2]}
        </strong>,
      );
    } else if (m[3]) {
      // `code`
      nodes.push(
        <code
          key={`c-${key++}`}
          className="px-1 py-px rounded bg-[var(--color-layer-2)] text-[12px] font-[family-name:var(--font-ibm-plex-mono)]"
        >
          {m[4]}
        </code>,
      );
    } else if (m[5]) {
      // [text](url)
      nodes.push(
        <a
          key={`l-${key++}`}
          href={m[7]}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[var(--color-accent)] hover:underline"
        >
          {m[6]}
        </a>,
      );
    } else if (m[8]) {
      // bare URL
      nodes.push(
        <a
          key={`u-${key++}`}
          href={m[8]}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[var(--color-accent)] hover:underline"
        >
          {m[8]}
        </a>,
      );
    } else if (validMentions.length && m[9]) {
      // @mention (validated)
      const id = m[9].toLowerCase();
      nodes.push(<span key={`m-${key++}`}>{renderMention(id)}</span>);
    } else {
      // The italic group's index depends on whether mentionAlt was included
      const italicGroup = validMentions.length ? 10 : 9;
      const italicText = validMentions.length ? m[11] : m[10];
      if (m[italicGroup]) {
        nodes.push(
          <em key={`i-${key++}`} className="italic">
            {italicText}
          </em>,
        );
      }
    }
    last = m.index + m[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}
