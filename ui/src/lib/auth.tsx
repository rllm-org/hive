"use client";

import { createContext, useContext, useState, useEffect, ReactNode, useCallback } from "react";

interface User {
  id: number;
  email: string;
  role: string;
}

interface AuthState {
  token: string | null;
  user: User | null;
}

interface AuthContextType extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string) => Promise<void>;
  logout: () => void;
  isAdmin: boolean;
}

const AuthContext = createContext<AuthContextType | null>(null);

const API_BASE = process.env.NEXT_PUBLIC_HIVE_SERVER ?? "/api";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ token: null, user: null });

  useEffect(() => {
    const stored = localStorage.getItem("hive-auth");
    if (stored) {
      try {
        setState(JSON.parse(stored));
      } catch {
        localStorage.removeItem("hive-auth");
      }
    }
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
    const data = await res.json();
    persist({ token: data.token, user: data.user });
  }, []);

  const logout = useCallback(() => {
    persist({ token: null, user: null });
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, login, signup, logout, isAdmin: state.user?.role === "admin" }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
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
