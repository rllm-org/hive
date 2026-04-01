"use client";

interface DiffViewerProps {
  diff: string;
}

interface DiffLine {
  type: "add" | "remove" | "context" | "header" | "hunk" | "file";
  content: string;
  oldNum: number | null;
  newNum: number | null;
}

function parseDiff(diff: string): DiffLine[] {
  const lines = diff.split("\n");
  const result: DiffLine[] = [];
  let oldLine = 0;
  let newLine = 0;

  for (const line of lines) {
    if (line.startsWith("diff --git")) {
      const fileMatch = line.match(/b\/(.+)$/);
      const fileName = fileMatch ? fileMatch[1] : line;
      result.push({ type: "file", content: fileName, oldNum: null, newNum: null });
    } else if (line.startsWith("index ") || line.startsWith("---") || line.startsWith("+++")) {
      // Skip these raw header lines — the file name is shown by the "file" line
    } else if (line.startsWith("@@")) {
      const match = line.match(/@@ -(\d+)/);
      if (match) {
        oldLine = parseInt(match[1], 10);
        const newMatch = line.match(/\+(\d+)/);
        newLine = newMatch ? parseInt(newMatch[1], 10) : oldLine;
      }
      result.push({ type: "hunk", content: line, oldNum: null, newNum: null });
    } else if (line.startsWith("+")) {
      result.push({ type: "add", content: line.slice(1), oldNum: null, newNum: newLine });
      newLine++;
    } else if (line.startsWith("-")) {
      result.push({ type: "remove", content: line.slice(1), oldNum: oldLine, newNum: null });
      oldLine++;
    } else {
      result.push({ type: "context", content: line.startsWith(" ") ? line.slice(1) : line, oldNum: oldLine, newNum: newLine });
      oldLine++;
      newLine++;
    }
  }

  return result;
}

const lineStyles: Record<DiffLine["type"], string> = {
  add: "bg-green-500/10 text-green-700 dark:text-green-400",
  remove: "bg-red-500/10 text-red-700 dark:text-red-400",
  context: "text-[var(--color-text)]",
  header: "bg-[var(--color-layer-2)] text-[var(--color-text-secondary)] font-semibold",
  hunk: "bg-blue-500/8 text-blue-600 dark:text-blue-400",
  file: "bg-[var(--color-layer-2)] border-b border-[var(--color-border)]",
};

const gutterStyles: Record<DiffLine["type"], string> = {
  add: "bg-green-500/15 text-green-600/60 dark:text-green-400/60",
  remove: "bg-red-500/15 text-red-600/60 dark:text-red-400/60",
  context: "text-[var(--color-text-tertiary)]",
  header: "bg-[var(--color-layer-2)]",
  hunk: "bg-blue-500/10 text-blue-500/60 dark:text-blue-400/60",
  file: "",
};

export function DiffViewer({ diff }: DiffViewerProps) {
  const lines = parseDiff(diff);

  return (
    <div className="rounded-lg border border-[var(--color-border)] overflow-hidden text-xs font-[family-name:var(--font-ibm-plex-mono)] leading-5">
      <div className="overflow-auto max-h-[400px]">
        <table className="w-full border-collapse">
          <tbody>
            {lines.map((line, i) => (
              <tr key={i} className={lineStyles[line.type]}>
                {line.type === "file" ? (
                  <td colSpan={3} className="px-3 py-1.5">
                    <span className="text-[var(--color-text)] font-semibold">{line.content}</span>
                  </td>
                ) : line.type === "header" || line.type === "hunk" ? (
                  <td colSpan={3} className="px-3 py-0.5 whitespace-pre select-all">
                    {line.content}
                  </td>
                ) : (
                  <>
                    <td className={`w-[1px] whitespace-nowrap px-2 py-0 text-right select-none border-r border-[var(--color-border)] ${gutterStyles[line.type]}`}>
                      {line.oldNum ?? ""}
                    </td>
                    <td className={`w-[1px] whitespace-nowrap px-2 py-0 text-right select-none border-r border-[var(--color-border)] ${gutterStyles[line.type]}`}>
                      {line.newNum ?? ""}
                    </td>
                    <td className="px-3 py-0 whitespace-pre select-all">
                      <span className="inline-block w-4 select-none opacity-50">
                        {line.type === "add" ? "+" : line.type === "remove" ? "-" : " "}
                      </span>
                      {line.content}
                    </td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
