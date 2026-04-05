"use client";

import { createContext, useContext, useState, useEffect, ReactNode, useCallback } from "react";

interface User {
  id: number;
  email: string;
  role: string;
  github_username?: string | null;
  avatar_url?: string | null;
}

interface AuthState {
  token: string | null;
  user: User | null;
}

interface AuthContextType extends AuthState {
  ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string) => Promise<void>;
  verifyCode: (email: string, code: string) => Promise<void>;
  resendCode: (email: string) => Promise<void>;
  forgotPassword: (email: string) => Promise<void>;
  resetPassword: (email: string, code: string, password: string) => Promise<void>;
  loginWithGithub: (code: string, state?: string) => Promise<void>;
  connectGithub: (code: string, state?: string) => Promise<void>;
  disconnectGithub: () => Promise<void>;
  logout: () => void;
  isAdmin: boolean;
}

const AuthContext = createContext<AuthContextType | null>(null);

const API_BASE = process.env.NEXT_PUBLIC_HIVE_SERVER ?? "/api";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ token: null, user: null });
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("hive-auth");
    if (stored) {
      try {
        const parsed = JSON.parse(stored);
        // Check JWT expiry
        if (parsed.token) {
          try {
            const payload = JSON.parse(atob(parsed.token.split(".")[1]));
            if (payload.exp && payload.exp * 1000 < Date.now()) {
              localStorage.removeItem("hive-auth");
              return;
            }
          } catch {
            localStorage.removeItem("hive-auth");
            return;
          }
        }
        setState(parsed);
      } catch {
        localStorage.removeItem("hive-auth");
      }
    }
    setReady(true);
  }, []);

  const persist = (s: AuthState) => {
    setState(s);
    if (s.token) {
      localStorage.setItem("hive-auth", JSON.stringify(s));
    } else {
      localStorage.removeItem("hive-auth");
    }
  };

  const login = useCallback(async (email: string, password: string) => {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new Error(data?.detail ?? "Login failed");
    }
    const data = await res.json();
    persist({ token: data.token, user: data.user });
  }, []);

  const signup = useCallback(async (email: string, password: string) => {
    const res = await fetch(`${API_BASE}/auth/signup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new Error(data?.detail ?? "Signup failed");
    }
    // No token returned — user must verify email first
  }, []);

  const verifyCode = useCallback(async (email: string, code: string) => {
    const res = await fetch(`${API_BASE}/auth/verify-code`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, code }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new Error(data?.detail ?? "Verification failed");
    }
    const data = await res.json();
    persist({ token: data.token, user: data.user });
  }, []);

  const resendCode = useCallback(async (email: string) => {
    const res = await fetch(`${API_BASE}/auth/resend-code`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new Error(data?.detail ?? "Failed to resend code");
    }
  }, []);

  const forgotPassword = useCallback(async (email: string) => {
    const res = await fetch(`${API_BASE}/auth/forgot-password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new Error(data?.detail ?? "Failed to send reset code");
    }
  }, []);

  const resetPassword = useCallback(async (email: string, code: string, password: string) => {
    const res = await fetch(`${API_BASE}/auth/reset-password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, code, password }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new Error(data?.detail ?? "Password reset failed");
    }
  }, []);

  const loginWithGithub = useCallback(async (code: string, state?: string) => {
    const res = await fetch(`${API_BASE}/auth/github`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, state }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new Error(data?.detail ?? "GitHub login failed");
    }
    const data = await res.json();
    persist({ token: data.token, user: data.user });
  }, []);

  const connectGithub = useCallback(async (code: string, state?: string) => {
    const res = await fetch(`${API_BASE}/auth/github/connect`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...getAuthHeader() },
      body: JSON.stringify({ code, state }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new Error(data?.detail ?? "GitHub connect failed");
    }
    const data = await res.json();
    setState((prev) => {
      if (!prev.user) return prev;
      const next = { ...prev, user: { ...prev.user, github_username: data.github_username, avatar_url: data.avatar_url } };
      localStorage.setItem("hive-auth", JSON.stringify(next));
      return next;
    });
  }, []);

  const disconnectGithub = useCallback(async () => {
    const res = await fetch(`${API_BASE}/auth/github`, {
      method: "DELETE",
      headers: getAuthHeader(),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new Error(data?.detail ?? "GitHub disconnect failed");
    }
    setState((prev) => {
      if (!prev.user) return prev;
      const next = { ...prev, user: { ...prev.user, github_username: null } };
      localStorage.setItem("hive-auth", JSON.stringify(next));
      return next;
    });
  }, []);

  const logout = useCallback(() => {
    persist({ token: null, user: null });
    window.location.href = "/";
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, ready, login, signup, verifyCode, resendCode, forgotPassword, resetPassword, loginWithGithub, connectGithub, disconnectGithub, logout, isAdmin: state.user?.role === "admin" }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

export async function getGithubOAuthUrl(mode: "login" | "connect" = "login"): Promise<string> {
  const redirectUri = `${window.location.origin}/auth/github/callback`;
  const res = await fetch(`${API_BASE}/auth/github/authorize?mode=${mode}&redirect_uri=${encodeURIComponent(redirectUri)}`);
  if (!res.ok) throw new Error("GitHub OAuth not available");
  const data = await res.json();
  return data.url;
}

export async function fetchAuthConfig(): Promise<{ oauth_providers: string[]; github_app_install_url?: string; github_agent_app_install_url?: string }> {
  const res = await fetch(`${API_BASE}/auth/config`);
  if (!res.ok) return { oauth_providers: [] };
  return res.json();
}

export function getAuthHeader(): Record<string, string> {
  try {
    const stored = localStorage.getItem("hive-auth");
    if (stored) {
      const { token } = JSON.parse(stored);
      if (token) return { Authorization: `Bearer ${token}` };
    }
  } catch {}
  return {};
}
