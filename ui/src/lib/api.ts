import { getAuthHeader } from "@/lib/auth";

const API_BASE =
  process.env.NEXT_PUBLIC_HIVE_SERVER ?? "/api";

function authHeaders(): Record<string, string> {
  try { return getAuthHeader(); } catch { return {}; }
}

export async function apiFetch<T>(path: string, headers?: Record<string, string>): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { headers: { ...authHeaders(), ...headers } });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export async function apiPost<T>(path: string, body: FormData, headers?: Record<string, string>): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { method: "POST", body, headers: { ...authHeaders(), ...headers } });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    const detail = data?.detail;
    const msg = typeof detail === "string" ? detail : detail ? JSON.stringify(detail) : `API ${res.status}: ${res.statusText}`;
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

export async function apiPatch<T>(path: string, body: unknown, headers?: Record<string, string>): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders(), ...headers },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(data?.detail ?? `API ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export async function apiPostJson<T>(path: string, body: unknown, headers?: Record<string, string>): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(), ...headers },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(data?.detail ?? `API ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export async function apiDelete<T>(path: string, headers?: Record<string, string>): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "DELETE",
    headers: { ...authHeaders(), ...headers },
  });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(data?.detail ?? `API ${res.status}`);
  }
  return res.json() as Promise<T>;
}
