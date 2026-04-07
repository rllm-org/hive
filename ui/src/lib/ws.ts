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

export function hiveTerminalWebSocketUrl(taskPath: string, ticket: string): string {
  // taskPath is "owner/slug" — encode each segment but not the separator slash.
  const q = new URLSearchParams({ ticket });
  const [owner, slug] = taskPath.split("/", 2);
  const path = `/api/tasks/${encodeURIComponent(owner)}/${encodeURIComponent(slug)}/sandbox/terminal/ws?${q.toString()}`;
  return `${getHiveWsOrigin()}${path}`;
}
