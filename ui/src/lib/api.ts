const API_BASE =
  process.env.NEXT_PUBLIC_HIVE_SERVER ?? "http://localhost:8000";

export async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "ngrok-skip-browser-warning": "true" },
  });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}
