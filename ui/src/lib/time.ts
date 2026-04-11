const MINUTE = 60;
const HOUR = 3600;
const DAY = 86400;
const WEEK = 604800;
const MONTH = 2592000;
const YEAR = 31536000;

const ONLINE_THRESHOLD_MS = 5 * 60 * 1000; // 5 minutes

/** Returns true if the timestamp is within the online threshold (5 min). */
export function isOnline(dateString: string | null | undefined): boolean {
  if (!dateString) return false;
  return Date.now() - new Date(dateString).getTime() < ONLINE_THRESHOLD_MS;
}

/** Full relative time: "just now", "5m ago", "3h ago", "2d ago", etc. */
export function timeAgo(dateString: string): string {
  const seconds = Math.floor(
    (Date.now() - new Date(dateString).getTime()) / 1000
  );

  if (seconds < MINUTE) return "just now";
  if (seconds < HOUR) {
    const m = Math.floor(seconds / MINUTE);
    return `${m}m ago`;
  }
  if (seconds < DAY) {
    const h = Math.floor(seconds / HOUR);
    return `${h}h ago`;
  }
  if (seconds < WEEK) {
    const d = Math.floor(seconds / DAY);
    return `${d}d ago`;
  }
  if (seconds < MONTH) {
    const w = Math.floor(seconds / WEEK);
    return `${w}w ago`;
  }
  if (seconds < YEAR) {
    const mo = Math.floor(seconds / MONTH);
    return `${mo}mo ago`;
  }
  const y = Math.floor(seconds / YEAR);
  return `${y}y ago`;
}

/** Compact relative time without "ago": "5m", "3h", "2d" */
export function relativeTime(dateString: string): string {
  const diff = Date.now() - new Date(dateString).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

export function timeRemaining(expiresAt: string): string {
  const diff = new Date(expiresAt).getTime() - Date.now();
  if (diff <= 0) return "expired";
  return `${Math.floor(diff / 60000)}m left`;
}
