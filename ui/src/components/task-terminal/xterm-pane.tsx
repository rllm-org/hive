"use client";

import { useEffect, useRef, useState } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { ClipboardAddon } from "@xterm/addon-clipboard";
import { WebglAddon } from "@xterm/addon-webgl";
import { WebLinksAddon } from "@xterm/addon-web-links";
import "@xterm/xterm/css/xterm.css";
import { LuX } from "react-icons/lu";
import { hiveTerminalWebSocketUrl } from "@/lib/ws";

interface XtermPaneProps {
  taskPath: string;
  ticket: string;
  active: boolean;
  onDisconnected: () => void;
}

// Strip ANSI escape sequences, then extract URLs
const ANSI_RE = /\x1b\[[0-9;]*[a-zA-Z]|\x1b\][^\x07]*\x07|\x1b[()][0-9A-B]/g;
const URL_RE = /https?:\/\/[^\s<>"']+/g;

export function XtermPane({ taskPath, ticket, active, onDisconnected }: XtermPaneProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const onDisconnectedRef = useRef(onDisconnected);
  onDisconnectedRef.current = onDisconnected;
  const activeRef = useRef(active);
  activeRef.current = active;
  const [detectedUrl, setDetectedUrl] = useState<string | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const term = new Terminal({
      cursorBlink: true,
      fontSize: 14,
      lineHeight: 1.25,
      fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
      scrollback: 10000,
      allowProposedApi: true,
      theme: {
        background: "#1a1b26",
        foreground: "#c0caf5",
        cursor: "#c0caf5",
        cursorAccent: "#1a1b26",
        selectionBackground: "#33467c",
        selectionForeground: "#c0caf5",
        black: "#15161e",
        red: "#f7768e",
        green: "#9ece6a",
        yellow: "#e0af68",
        blue: "#7aa2f7",
        magenta: "#bb9af7",
        cyan: "#7dcfff",
        white: "#a9b1d6",
        brightBlack: "#414868",
        brightRed: "#f7768e",
        brightGreen: "#9ece6a",
        brightYellow: "#e0af68",
        brightBlue: "#7aa2f7",
        brightMagenta: "#bb9af7",
        brightCyan: "#7dcfff",
        brightWhite: "#c0caf5",
      },
    });
    const fit = new FitAddon();
    const clipboard = new ClipboardAddon();
    term.loadAddon(fit);
    term.loadAddon(clipboard);
    term.loadAddon(new WebLinksAddon((_event, uri) => {
      window.open(uri, "_blank");
    }));
    term.open(el);
    try {
      term.loadAddon(new WebglAddon());
    } catch {
      /* WebGL not available — falls back to canvas */
    }
    termRef.current = term;
    fitRef.current = fit;

    // Buffer raw output to detect URLs that arrive across multiple chunks
    let urlBuf = "";
    let urlBufTimer: ReturnType<typeof setTimeout> | null = null;

    const detectUrls = (text: string) => {
      urlBuf += text;
      if (urlBufTimer) clearTimeout(urlBufTimer);
      urlBufTimer = setTimeout(() => {
        // Strip all ANSI codes and control chars, collapse whitespace
        const clean = urlBuf.replace(ANSI_RE, "").replace(/[\r\n\t]/g, "").replace(/\s+/g, "");
        const matches = clean.match(URL_RE);
        if (matches) {
          const longest = matches.reduce((a, b) => (a.length > b.length ? a : b));
          if (longest.length > 60) {
            setDetectedUrl(longest);
          }
        }
        // Keep tail in case a URL spans the next batch
        urlBuf = urlBuf.slice(-500);
      }, 500);
    };

    const wsUrl = hiveTerminalWebSocketUrl(taskPath, ticket);
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      fit.fit();
      const { cols, rows } = term;
      ws.send(JSON.stringify({ type: "resize", cols, rows }));
    };

    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data as string) as { type?: string; data?: string; message?: string; code?: number };
        if (msg.type === "output" && msg.data) {
          const raw = atob(msg.data);
          const bytes = new Uint8Array(raw.length);
          for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
          const text = new TextDecoder().decode(bytes);
          term.write(text);
          detectUrls(text);
        } else if (msg.type === "error" && msg.message) {
          term.write(`\r\n\x1b[31m${msg.message}\x1b[0m\r\n`);
        } else if (msg.type === "exit") {
          term.write(`\r\n\x1b[90m[Session ended]\x1b[0m\r\n`);
          onDisconnectedRef.current();
        } else if (msg.type === "pong") {
          /* ignore */
        }
      } catch {
        /* ignore */
      }
    };

    ws.onerror = () => {
      term.write("\r\n\x1b[31m[WebSocket error]\x1b[0m\r\n");
    };

    ws.onclose = () => {
      onDisconnectedRef.current();
    };

    const utf8ToB64 = (s: string) => {
      const bytes = new TextEncoder().encode(s);
      let bin = "";
      bytes.forEach((b) => {
        bin += String.fromCharCode(b);
      });
      return btoa(bin);
    };

    const d = term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "input", data: utf8ToB64(data) }));
      }
    });

    const onResize = () => {
      if (!activeRef.current) return;
      try {
        fit.fit();
      } catch {
        /* ignore */
      }
      if (ws.readyState === WebSocket.OPEN && term.cols && term.rows) {
        ws.send(JSON.stringify({ type: "resize", cols: term.cols, rows: term.rows }));
      }
    };

    const ro = new ResizeObserver(() => {
      onResize();
    });
    ro.observe(el);
    window.addEventListener("resize", onResize);

    term.onResize(({ cols, rows }) => {
      if (!activeRef.current) return;
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "resize", cols, rows }));
      }
    });

    return () => {
      if (urlBufTimer) clearTimeout(urlBufTimer);
      ro.disconnect();
      window.removeEventListener("resize", onResize);
      d.dispose();
      ws.onclose = null;
      ws.onerror = null;
      try {
        ws.close();
      } catch {
        /* ignore */
      }
      term.dispose();
      termRef.current = null;
      wsRef.current = null;
      fitRef.current = null;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskPath, ticket]);

  useEffect(() => {
    if (active && termRef.current && fitRef.current && containerRef.current) {
      try {
        fitRef.current.fit();
      } catch {
        /* ignore */
      }
      termRef.current.focus();
    }
  }, [active]);

  return (
    <div className="h-full flex flex-col">
      {detectedUrl && (
        <div className="flex items-center gap-2 px-3 py-1.5 bg-[#24283b] border-b border-[#33467c] shrink-0">
          <span className="text-xs text-[#7aa2f7]">URL detected:</span>
          <a
            href={detectedUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-[#7dcfff] hover:underline truncate flex-1"
          >
            {detectedUrl}
          </a>
          <button
            type="button"
            onClick={() => { void navigator.clipboard.writeText(detectedUrl); }}
            className="text-xs text-[#a9b1d6] hover:text-white px-1.5 py-0.5 border border-[#414868] rounded"
          >
            Copy
          </button>
          <button
            type="button"
            onClick={() => setDetectedUrl(null)}
            className="text-[#414868] hover:text-[#a9b1d6] px-1 flex items-center"
            aria-label="Dismiss"
          >
            <LuX size={14} />
          </button>
        </div>
      )}
      <div
        ref={containerRef}
        className="flex-1 min-h-0 w-full overflow-hidden rounded border border-[#1a1b26] bg-[#1a1b26] p-1"
      />
    </div>
  );
}
