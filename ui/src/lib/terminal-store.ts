/**
 * Singleton store that keeps WebSocket connections and output buffers alive
 * across React component mount/unmount cycles (i.e. page navigations).
 */

import { hiveTerminalWebSocketUrl } from "./ws";

export type TerminalMessage =
  | { type: "output"; data: string }
  | { type: "error"; message: string }
  | { type: "exit"; code?: number }
  | { type: "pong" };

export type OutputListener = (msg: TerminalMessage) => void;

interface SessionEntry {
  ws: WebSocket;
  buffer: TerminalMessage[];
  listener: OutputListener | null;
  closed: boolean;
  onClose: (() => void) | null;
  pingInterval: ReturnType<typeof setInterval> | null;
}

const sessions = new Map<string, SessionEntry>();

function key(taskPath: string, ticket: string) {
  return `${taskPath}::${ticket}`;
}

/** Open (or return existing) WebSocket for a session. */
export function openSession(taskPath: string, ticket: string): string {
  const k = key(taskPath, ticket);
  if (sessions.has(k)) return k;

  const wsUrl = hiveTerminalWebSocketUrl(taskPath, ticket);
  const ws = new WebSocket(wsUrl);

  const entry: SessionEntry = {
    ws,
    buffer: [],
    listener: null,
    closed: false,
    onClose: null,
    pingInterval: null,
  };

  const dispatch = (msg: TerminalMessage) => {
    entry.buffer.push(msg);
    // Cap buffer at ~5000 messages to avoid unbounded memory
    if (entry.buffer.length > 5000) {
      entry.buffer = entry.buffer.slice(-4000);
    }
    if (entry.listener) entry.listener(msg);
  };

  ws.onopen = () => {
    // Keep-alive pings
    entry.pingInterval = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "ping" }));
      }
    }, 30_000);
  };

  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data as string) as TerminalMessage & { data?: string; message?: string };
      if (msg.type === "output" || msg.type === "error" || msg.type === "exit") {
        dispatch(msg);
      }
      // pong is ignored
    } catch {
      /* ignore */
    }
  };

  ws.onerror = () => {
    dispatch({ type: "error", message: "[WebSocket error]" });
  };

  ws.onclose = () => {
    entry.closed = true;
    if (entry.pingInterval) clearInterval(entry.pingInterval);
    if (entry.onClose) entry.onClose();
  };

  sessions.set(k, entry);
  return k;
}

/** Attach a listener to receive live messages. Returns the buffered history. */
export function attach(
  sessionKey: string,
  listener: OutputListener,
  onClose?: () => void,
): TerminalMessage[] {
  const entry = sessions.get(sessionKey);
  if (!entry) return [];
  entry.listener = listener;
  entry.onClose = onClose ?? null;
  return [...entry.buffer];
}

/** Detach the listener (component unmounting) — WS stays alive. */
export function detach(sessionKey: string) {
  const entry = sessions.get(sessionKey);
  if (!entry) return;
  entry.listener = null;
  entry.onClose = null;
}

/** Send input data to the session. */
export function sendInput(sessionKey: string, base64Data: string) {
  const entry = sessions.get(sessionKey);
  if (!entry || entry.ws.readyState !== WebSocket.OPEN) return;
  entry.ws.send(JSON.stringify({ type: "input", data: base64Data }));
}

/** Send a resize event. */
export function sendResize(sessionKey: string, cols: number, rows: number) {
  const entry = sessions.get(sessionKey);
  if (!entry || entry.ws.readyState !== WebSocket.OPEN) return;
  entry.ws.send(JSON.stringify({ type: "resize", cols, rows }));
}

/** Fully close and remove a session (user explicitly closes the tab). */
export function closeSession(sessionKey: string) {
  const entry = sessions.get(sessionKey);
  if (!entry) return;
  if (entry.pingInterval) clearInterval(entry.pingInterval);
  entry.listener = null;
  entry.onClose = null;
  try {
    entry.ws.onclose = null;
    entry.ws.onerror = null;
    entry.ws.close();
  } catch {
    /* ignore */
  }
  sessions.delete(sessionKey);
}

/** Check if a session's WS is still open. */
export function isOpen(sessionKey: string): boolean {
  const entry = sessions.get(sessionKey);
  return !!entry && !entry.closed && entry.ws.readyState === WebSocket.OPEN;
}
