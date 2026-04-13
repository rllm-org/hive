"use client";

import { useEffect, useRef, useState } from "react";

interface MermaidDiagramProps {
  code: string;
}

let mermaidPromise: Promise<typeof import("mermaid")> | null = null;
let idCounter = 0;

function getMermaid() {
  if (!mermaidPromise) {
    mermaidPromise = import("mermaid").then((mod) => {
      mod.default.initialize({
        startOnLoad: false,
        theme: "neutral",
        fontFamily: "var(--font-dm-sans)",
      });
      return mod;
    });
  }
  return mermaidPromise;
}

export function MermaidDiagram({ code }: MermaidDiagramProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const idRef = useRef(`mermaid-${idCounter++}`);

  useEffect(() => {
    let cancelled = false;
    getMermaid().then(async (mod) => {
      if (cancelled || !containerRef.current) return;
      try {
        const { svg } = await mod.default.render(idRef.current, code);
        if (!cancelled && containerRef.current) {
          containerRef.current.innerHTML = svg;
        }
      } catch (err) {
        if (!cancelled) setError(String(err));
      }
    });
    return () => { cancelled = true; };
  }, [code]);

  if (error) {
    return (
      <pre className="my-1 px-3 py-2 rounded-md bg-[var(--color-layer-2)] overflow-x-auto text-[12px] text-red-500 font-[family-name:var(--font-ibm-plex-mono)] whitespace-pre">
        {code}
      </pre>
    );
  }

  return (
    <div
      ref={containerRef}
      className="my-1 p-3 rounded-md bg-[var(--color-layer-2)] overflow-x-auto flex justify-center"
    />
  );
}
