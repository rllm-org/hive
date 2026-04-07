"use client";

import { useEffect, useRef, useState } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { ClipboardAddon } from "@xterm/addon-clipboard";
import { WebglAddon } from "@xterm/addon-webgl";
import { WebLinksAddon } from "@xterm/addon-web-links";
import "@xterm/xterm/css/xterm.css";
import { LuX } from "react-icons/lu";
import * as store from "@/lib/terminal-store";

interface XtermPaneProps {
  storeKey: string;
  active: boolean;
  onDisconnected: () => void;
}

const ANSI_RE = /\x1b\[[0-9;]*[a-zA-Z]|\x1b\][^\x07]*\x07|\x1b[()][0-9A-B]/g;
const URL_RE = /https?:\/\/[^\s<>"']+/g;

function decodeOutput(base64: string): string {
  const raw = atob(base64);
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
  return new TextDecoder().decode(bytes);
}

function utf8ToB64(s: string): string {
  const bytes = new TextEncoder().encode(s);
  let bin = "";
  bytes.forEach((b) => { bin += String.fromCharCode(b); });
  return btoa(bin);
}

export function XtermPane({ storeKey, active, onDisconnected }: XtermPaneProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);
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
      /* WebGL not available */
    }
    termRef.current = term;
    fitRef.current = fit;

    // Batch incoming writes — collect chunks and flush once per animation frame
    let writeBuf = "";
    let writeRaf: number | null = null;

    const flushWrites = () => {
      writeRaf = null;
      if (writeBuf) {
        term.write(writeBuf);
        detectUrls(writeBuf);
        writeBuf = "";
      }
    };

    const queueWrite = (text: string) => {
      writeBuf += text;
      if (!writeRaf) writeRaf = requestAnimationFrame(flushWrites);
    };

    // URL detection — only keep last 2KB, run regex after 500ms idle
    let urlBuf = "";
    let urlBufTimer: ReturnType<typeof setTimeout> | null = null;

    const detectUrls = (text: string) => {
      urlBuf += text;
      if (urlBuf.length > 2000) urlBuf = urlBuf.slice(-2000);
      if (urlBufTimer) clearTimeout(urlBufTimer);
      urlBufTimer = setTimeout(() => {
        const clean = urlBuf.replace(ANSI_RE, "").replace(/[\r\n\t]/g, "").replace(/\s+/g, "");
        const matches = clean.match(URL_RE);
        if (matches) {
          const longest = matches.reduce((a, b) => (a.length > b.length ? a : b));
          if (longest.length > 60) setDetectedUrl(longest);
        }
        urlBuf = urlBuf.slice(-500);
      }, 500);
    };

    const writeLiveMsg = (msg: store.TerminalMessage) => {
      if (msg.type === "output" && "data" in msg) {
        queueWrite(decodeOutput(msg.data));
      } else if (msg.type === "error" && "message" in msg) {
        queueWrite(`\r\n\x1b[31m${msg.message}\x1b[0m\r\n`);
      } else if (msg.type === "exit") {
        queueWrite(`\r\n\x1b[90m[Session ended]\x1b[0m\r\n`);
        onDisconnectedRef.current();
      }
    };

    // Replay buffered output in one shot (pre-decoded text), then attach for live messages
    const replayText = store.attach(storeKey, writeLiveMsg, () => {
      onDisconnectedRef.current();
    });
    if (replayText) {
      term.write(replayText);
    }

    // Send initial resize
    fit.fit();
    store.sendResize(storeKey, term.cols, term.rows);

    // Input handling
    const d = term.onData((data) => {
      store.sendInput(storeKey, utf8ToB64(data));
    });

    // Resize handling
    const onResize = () => {
      if (!activeRef.current) return;
      try { fit.fit(); } catch { /* ignore */ }
      if (term.cols && term.rows) {
        store.sendResize(storeKey, term.cols, term.rows);
      }
    };

    const ro = new ResizeObserver(() => onResize());
    ro.observe(el);
    window.addEventListener("resize", onResize);

    term.onResize(({ cols, rows }) => {
      if (!activeRef.current) return;
      store.sendResize(storeKey, cols, rows);
    });

    return () => {
      if (writeRaf) cancelAnimationFrame(writeRaf);
      if (urlBufTimer) clearTimeout(urlBufTimer);
      ro.disconnect();
      window.removeEventListener("resize", onResize);
      d.dispose();
      // Detach but don't close — WS stays alive in the store
      store.detach(storeKey);
      term.dispose();
      termRef.current = null;
      fitRef.current = null;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storeKey]);

  useEffect(() => {
    if (active && termRef.current && fitRef.current && containerRef.current) {
      try { fitRef.current.fit(); } catch { /* ignore */ }
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
