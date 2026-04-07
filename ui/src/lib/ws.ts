/** WebSocket origin for Hive API (direct backend URL avoids Next HTTP-only rewrites for WS). */

export function getHiveWsOrigin(): string {
  if (typeof window === "undefined") {
    return "";
  }
  const base = process.env.NEXT_PUBLIC_HIVE_SERVER;
  if (base) {
    const u = new URL(base);
    u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
    return u.origin;
  }
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}`;
}

export function hiveTerminalWebSocketUrl(taskId: string, ticket: string): string {
  const q = new URLSearchParams({ ticket });
  const path = `/api/tasks/${encodeURIComponent(taskId)}/sandbox/terminal/ws?${q.toString()}`;
  return `${getHiveWsOrigin()}${path}`;
}
