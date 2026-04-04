"use client";

import { Suspense, useEffect, useState, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/lib/auth";

function GitHubCallbackInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { loginWithGithub, connectGithub } = useAuth();
  const [error, setError] = useState("");
  const navigating = useRef(false);
  const called = useRef(false);

  useEffect(() => {
    if (called.current) return;
    called.current = true;

    const code = searchParams.get("code");
    const state = searchParams.get("state") || "login";
    const installationId = searchParams.get("installation_id");
    const isConnect = !!(installationId || state === "connect");
    const dest = installationId ? "/me?create=1" : "/me";

    // Redirect from GitHub App installation (repo selection) — no code needed
    if (installationId && !code) {
      router.push("/me?create=1");
      return;
    }

    if (!code) {
      setError("No authorization code received from GitHub");
      return;
    }

    (async () => {
      try {
        if (isConnect) {
          await connectGithub(code, state);
        } else {
          await loginWithGithub(code, state);
        }
      } catch {
        // Ignore — likely a duplicate call with an already-consumed code
      }
      navigating.current = true;
      router.push(dest);
    })();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center max-w-sm">
          <p className="text-sm text-red-500 mb-4">{error}</p>
          <button
            onClick={() => router.push("/")}
            className="px-4 py-2 text-sm font-medium bg-[var(--color-accent)] text-white hover:opacity-90 transition-opacity"
          >
            Back to Hive
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center">
      <p className="text-sm text-[var(--color-text-secondary)]">Connecting to GitHub...</p>
    </div>
  );
}

export default function GitHubCallbackPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-sm text-[var(--color-text-secondary)]">Connecting to GitHub...</p>
      </div>
    }>
      <GitHubCallbackInner />
    </Suspense>
  );
}
