"use client";

import { useState } from "react";

interface CsvTableProps {
  code: string;
  delimiter?: string;
}

const MAX_VISIBLE_ROWS = 100;

function parseCsv(text: string, delimiter: string): string[][] {
  const rows: string[][] = [];
  for (const line of text.split("\n")) {
    if (line.trim() === "") continue;
    const cells: string[] = [];
    let current = "";
    let inQuote = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (inQuote) {
        if (ch === '"' && line[i + 1] === '"') {
          current += '"';
          i++;
        } else if (ch === '"') {
          inQuote = false;
        } else {
          current += ch;
        }
      } else if (ch === '"') {
        inQuote = true;
      } else if (ch === delimiter) {
        cells.push(current.trim());
        current = "";
      } else {
        current += ch;
      }
    }
    cells.push(current.trim());
    rows.push(cells);
  }
  return rows;
}

export function CsvTable({ code, delimiter = "," }: CsvTableProps) {
  const [expanded, setExpanded] = useState(false);
  const rows = parseCsv(code, delimiter);
  if (rows.length === 0) return null;

  const header = rows[0];
  const body = rows.slice(1);
  const visible = expanded ? body : body.slice(0, MAX_VISIBLE_ROWS);
  const hasMore = body.length > MAX_VISIBLE_ROWS;

  return (
    <div className="my-1 rounded-md border border-[var(--color-border)] overflow-x-auto text-[12px]">
      <table className="w-full border-collapse">
        <thead>
          <tr className="bg-[var(--color-layer-2)]">
            {header.map((cell, i) => (
              <th
                key={i}
                className="px-3 py-1.5 text-left font-semibold text-[var(--color-text)] border-b border-[var(--color-border)] whitespace-nowrap"
              >
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {visible.map((row, ri) => (
            <tr
              key={ri}
              className={ri % 2 === 1 ? "bg-[var(--color-layer-1)]" : ""}
            >
              {row.map((cell, ci) => (
                <td
                  key={ci}
                  className="px-3 py-1 text-[var(--color-text)] border-b border-[var(--color-border-light)] whitespace-nowrap font-[family-name:var(--font-ibm-plex-mono)]"
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {hasMore && !expanded && (
        <button
          onClick={() => setExpanded(true)}
          className="w-full py-1.5 text-[11px] text-[var(--color-accent)] hover:underline cursor-pointer"
        >
          Show {body.length - MAX_VISIBLE_ROWS} more rows
        </button>
      )}
    </div>
  );
}
