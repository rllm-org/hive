"use client";

import { useState, useRef, useEffect } from "react";
import { useAuth, getGithubOAuthUrl, fetchAuthConfig } from "@/lib/auth";
import { LuGithub } from "react-icons/lu";

interface AuthModalProps {
  onClose: () => void;
  initialMode?: "login" | "signup";
}

export function AuthModal({ onClose, initialMode = "login" }: AuthModalProps) {
  const { login, signup, verifyCode, resendCode, forgotPassword, resetPassword } = useAuth();
  const [mode, setMode] = useState<"login" | "signup" | "verify" | "forgot" | "reset">(initialMode);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [resent, setResent] = useState(false);
  const overlayRef = useRef<HTMLDivElement>(null);
  const [githubEnabled, setGithubEnabled] = useState(false);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handleEsc);
    return () => window.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  useEffect(() => {
    fetchAuthConfig().then((c) => setGithubEnabled(c.oauth_providers.includes("github")));
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (mode === "login") {
        await login(email, password);
        window.location.href = "/me";
      } else if (mode === "signup") {
        await signup(email, password);
        setMode("verify");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await verifyCode(email, code);
      window.location.href = "/me";
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Verification failed");
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    setError("");
    try {
      await resendCode(email);
      setResent(true);
      setTimeout(() => setResent(false), 3000);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to resend");
    }
  };

  const handleForgotPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await forgotPassword(email);
      setMode("reset");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await resetPassword(email, code, password);
      setMode("login");
      setPassword("");
      setCode("");
      setError("");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Password reset failed");
    } finally {
      setLoading(false);
    }
  };

  const handleResendReset = async () => {
    setError("");
    try {
      await forgotPassword(email);
      setResent(true);
      setTimeout(() => setResent(false), 3000);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to resend");
    }
  };

  const inputCls = "w-full px-3 py-2 text-sm border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] placeholder:text-[var(--color-text-tertiary)] outline-none";
  const labelCls = "block text-xs font-medium text-[var(--color-text-secondary)] mb-1.5";

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-[9999] flex items-center justify-center backdrop-blur-md bg-black/30"
      onClick={(e) => { if (e.target === overlayRef.current) onClose(); }}
    >
      <div className="bg-[var(--color-surface)] shadow-[var(--shadow-elevated)] w-full max-w-[380px] flex flex-col animate-fade-in">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border)]">
          <h2 className="text-base font-semibold text-[var(--color-text)]">
            {mode === "verify" ? "Verify your email" : mode === "forgot" ? "Forgot password" : mode === "reset" ? "Reset password" : mode === "login" ? "Log in" : "Sign up"}
          </h2>
          <button
            onClick={onClose}
            className="w-7 h-7 flex items-center justify-center text-[var(--color-text-tertiary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-2)] transition-all"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M3 3l8 8M11 3l-8 8" />
            </svg>
          </button>
        </div>

        {mode === "forgot" ? (
          /* ─── Forgot Password Screen ─── */
          <div className="px-6 py-5 space-y-4">
            <p className="text-sm text-[var(--color-text-secondary)]">
              Enter your email and we&apos;ll send a reset code.
            </p>
            <form onSubmit={handleForgotPassword} className="space-y-4">
              <div>
                <label className={labelCls}>Email</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  style={{ outline: "none", boxShadow: "none" }}
                  className={inputCls}
                  placeholder="you@example.com"
                  autoFocus
                />
              </div>

              {error && <p className="text-xs text-red-500">{error}</p>}

              <button
                type="submit"
                disabled={loading}
                className="w-full py-2 text-sm font-medium bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50 transition-colors"
              >
                {loading ? "..." : "Send reset code"}
              </button>
            </form>
            <p className="text-center text-xs text-[var(--color-text-tertiary)]">
              <button onClick={() => { setMode("login"); setError(""); }} className="text-[var(--color-accent)] hover:underline">
                Back to login
              </button>
            </p>
          </div>
        ) : mode === "reset" ? (
          /* ─── Reset Password Screen ─── */
          <div className="px-6 py-5 space-y-4">
            <p className="text-sm text-[var(--color-text-secondary)]">
              We sent a 6-digit code to <span className="font-medium text-[var(--color-text)]">{email}</span>
            </p>
            <form onSubmit={handleResetPassword} className="space-y-4">
              <div>
                <label className={labelCls}>Reset code</label>
                <input
                  type="text"
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  required
                  maxLength={6}
                  style={{ outline: "none", boxShadow: "none" }}
                  className={`${inputCls} text-center text-lg tracking-[0.3em] font-mono`}
                  placeholder="000000"
                  autoFocus
                />
              </div>
              <div>
                <label className={labelCls}>New password</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={8}
                  style={{ outline: "none", boxShadow: "none" }}
                  className={inputCls}
                  placeholder="At least 8 characters"
                />
              </div>

              {error && <p className="text-xs text-red-500">{error}</p>}

              <button
                type="submit"
                disabled={loading || code.length !== 6}
                className="w-full py-2 text-sm font-medium bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50 transition-colors"
              >
                {loading ? "..." : "Reset password"}
              </button>
            </form>
            <p className="text-center text-xs text-[var(--color-text-tertiary)]">
              Didn&apos;t receive it?{" "}
              <button
                onClick={handleResendReset}
                disabled={resent}
                className="text-[var(--color-accent)] hover:underline disabled:opacity-50"
              >
                {resent ? "Sent!" : "Resend code"}
              </button>
            </p>
          </div>
        ) : mode === "verify" ? (
          /* ─── Verify Code Screen ─── */
          <div className="px-6 py-5 space-y-4">
            <p className="text-sm text-[var(--color-text-secondary)]">
              We sent a 6-digit code to <span className="font-medium text-[var(--color-text)]">{email}</span>
            </p>
            <form onSubmit={handleVerify} className="space-y-4">
              <div>
                <label className={labelCls}>Verification code</label>
                <input
                  type="text"
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  required
                  maxLength={6}
                  style={{ outline: "none", boxShadow: "none" }}
                  className={`${inputCls} text-center text-lg tracking-[0.3em] font-mono`}
                  placeholder="000000"
                  autoFocus
                />
              </div>

              {error && <p className="text-xs text-red-500">{error}</p>}

              {error?.includes("too many attempts") ? (
                <button
                  type="button"
                  onClick={handleResend}
                  disabled={resent}
                  className="w-full py-2 text-sm font-medium bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50 transition-colors"
                >
                  {resent ? "Sent!" : "Resend new code"}
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={loading || code.length !== 6}
                  className="w-full py-2 text-sm font-medium bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50 transition-colors"
                >
                  {loading ? "..." : "Verify"}
                </button>
              )}
            </form>
            <p className="text-center text-xs text-[var(--color-text-tertiary)]">
              Didn&apos;t receive it?{" "}
              <button
                onClick={handleResend}
                disabled={resent}
                className="text-[var(--color-accent)] hover:underline disabled:opacity-50"
              >
                {resent ? "Sent!" : "Resend code"}
              </button>
            </p>
          </div>
        ) : (
          /* ─── Login / Signup Screen ─── */
          <>
            <div className="px-6 py-5 space-y-4">
              {githubEnabled && (
                <>
                  <button
                    type="button"
                    onClick={async () => { window.location.href = await getGithubOAuthUrl("login"); }}
                    className="w-full py-2 text-sm font-medium bg-[#24292f] text-white hover:bg-[#32383f] dark:bg-white dark:text-black dark:hover:bg-[#e0e0e0] transition-colors flex items-center justify-center gap-2"
                  >
                    <LuGithub size={16} />
                    Continue with GitHub
                  </button>
                  <div className="flex items-center gap-3">
                    <div className="flex-1 border-t border-[var(--color-border)]" />
                    <span className="text-[11px] text-[var(--color-text-tertiary)] uppercase tracking-wide">or</span>
                    <div className="flex-1 border-t border-[var(--color-border)]" />
                  </div>
                </>
              )}
              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label className={labelCls}>Email</label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    style={{ outline: "none", boxShadow: "none" }}
                    className={inputCls}
                    placeholder="you@example.com"
                  />
                </div>
                <div>
                  <label className={labelCls}>Password</label>
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    minLength={8}
                    style={{ outline: "none", boxShadow: "none" }}
                    className={inputCls}
                    placeholder={mode === "signup" ? "At least 8 characters" : ""}
                  />
                  {mode === "login" && (
                    <button
                      type="button"
                      onClick={() => { setMode("forgot"); setError(""); }}
                      className="mt-1 text-xs text-[var(--color-text-tertiary)] hover:text-[var(--color-accent)] hover:underline"
                    >
                      Forgot password?
                    </button>
                  )}
                </div>

                {error && <p className="text-xs text-red-500">{error}</p>}

                <button
                  type="submit"
                  disabled={loading}
                  className="w-full py-2 text-sm font-medium bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50 transition-colors"
                >
                  {loading ? "..." : mode === "login" ? "Log in" : "Sign up"}
                </button>
              </form>
            </div>

            {/* Footer */}
            <div className="px-6 pb-5">
              <p className="text-center text-xs text-[var(--color-text-tertiary)]">
                {mode === "login" ? (
                  <>
                    No account?{" "}
                    <button onClick={() => { setMode("signup"); setError(""); }} className="text-[var(--color-accent)] hover:underline">
                      Sign up
                    </button>
                  </>
                ) : (
                  <>
                    Already have an account?{" "}
                    <button onClick={() => { setMode("login"); setError(""); }} className="text-[var(--color-accent)] hover:underline">
                      Log in
                    </button>
                  </>
                )}
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
