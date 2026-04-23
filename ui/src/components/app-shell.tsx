"use client";

import { createContext, useCallback, useContext, useEffect, useMemo } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import BoringAvatar from "boring-avatars";

const NAV_RAIL_BG = "#1e3a5c";

export type AppView = "home" | "tasks" | "leaderboard" | "settings" | "profile" | "other";

/** Known top-level routes that are NOT team/workspace slugs */
const RESERVED_ROUTES = new Set([
  "tasks", "leaderboard", "profile", "settings", "agents",
  "auth", "task", "me", "workspaces", "test-artifacts", "_not-found",
]);

function viewFromPathname(pathname: string): AppView {
  if (pathname === "/tasks" || pathname.startsWith("/tasks/")) return "tasks";
  if (pathname === "/leaderboard" || pathname.startsWith("/leaderboard/")) return "leaderboard";
  if (pathname === "/profile" || pathname.startsWith("/profile/")) return "profile";
  if (pathname === "/settings" || pathname.startsWith("/settings/")) return "settings";
  // Task pages, agent pages, etc. — nothing highlighted in top bar
  if (pathname.startsWith("/task/") || pathname.startsWith("/agents/") || pathname.startsWith("/workspaces/")) return "other";
  return "home";
}

const AppViewContext = createContext<{ view: AppView; setView: (v: AppView) => void }>({
  view: "home",
  setView: () => {},
});

export const useAppView = () => useContext(AppViewContext);

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, ready } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  const view = useMemo(() => viewFromPathname(pathname), [pathname]);

  const teamPath = user?.handle ? `/${user.handle}` : "/";

  const setView = useCallback((v: AppView) => {
    let target: string;
    switch (v) {
      case "tasks": target = "/tasks"; break;
      case "leaderboard": target = "/leaderboard"; break;
      case "profile": target = "/profile"; break;
      case "settings": target = "/settings"; break;
      case "home":
      default: target = teamPath;
    }
    if (pathname !== target) {
      router.push(target);
    }
  }, [pathname, router, teamPath]);

  const isPublicRoute = pathname === "/" || pathname === "/tasks" || pathname.startsWith("/task/") || pathname.startsWith("/auth/") || pathname === "/leaderboard" || pathname.startsWith("/agents/") || pathname.startsWith("/test-artifacts");

  useEffect(() => {
    if (ready && !user && !isPublicRoute) {
      router.replace("/");
    }
  }, [ready, user, isPublicRoute, router]);

  if (!ready) {
    return null;
  }

  if (!user) {
    if (!isPublicRoute) return null;
    return <>{children}</>;
  }

  return (
    <AppViewContext.Provider value={{ view, setView }}>
      <div className="flex flex-col w-full h-screen overflow-hidden" style={{ backgroundColor: NAV_RAIL_BG }}>
        {/* Top bar */}
        <div className="shrink-0 h-[50px] flex items-center px-4 gap-2">
          {/* Left: Team icon + add team */}
          <div className="flex items-center gap-2">
            <div
              className={`w-7 h-7 rounded-[30%] overflow-hidden border-2 cursor-pointer shrink-0 transition-colors ${
                view === "home" ? "border-white" : "border-transparent hover:border-white/50"
              }`}
              onClick={() => setView("home")}
            >
              {user.avatar_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={user.avatar_url} alt={user.handle ?? "user"} width={28} height={28} className="w-full h-full object-cover" />
              ) : (
                <BoringAvatar name={user.handle ?? "user"} variant="bauhaus" size={28} square colors={["#92A1C6","#146A7C","#F0AB3D","#C271B4","#C20D90"]} />
              )}
            </div>
            <button
              className="w-6 h-6 rounded-[30%] flex items-center justify-center text-white/40 hover:bg-white/10 hover:text-white/70 transition-colors cursor-pointer"
              title="Add a team"
            >
              <svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M10 4v12M4 10h12" />
              </svg>
            </button>
          </div>

          {/* Right: Public Tasks, Leaderboard, Profile */}
          <div className="ml-auto flex items-center gap-1">
            <button
              onClick={() => setView(view === "tasks" ? "home" : "tasks")}
              className={`px-3 py-1 text-[13px] font-medium rounded transition-colors ${
                view === "tasks" ? "text-white bg-white/15" : "text-white/60 hover:text-white hover:bg-white/10"
              }`}
            >
              Public Tasks
            </button>
            <button
              onClick={() => setView(view === "leaderboard" ? "home" : "leaderboard")}
              className={`px-3 py-1 text-[13px] font-medium rounded transition-colors ${
                view === "leaderboard" ? "text-white bg-white/15" : "text-white/60 hover:text-white hover:bg-white/10"
              }`}
            >
              Leaderboard
            </button>
            <button
              onClick={() => setView(view === "profile" ? "home" : "profile")}
              className={`ml-1 w-7 h-7 rounded-full overflow-hidden border-2 transition-colors cursor-pointer ${
                view === "profile" ? "border-white" : "border-transparent hover:border-white/50"
              }`}
            >
              {user.avatar_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={user.avatar_url} alt={user.handle ?? "user"} width={28} height={28} className="w-full h-full object-cover" />
              ) : (
                <BoringAvatar name={user.handle ?? "user"} variant="bauhaus" size={28} square colors={["#92A1C6","#146A7C","#F0AB3D","#C271B4","#C20D90"]} />
              )}
            </button>
          </div>
        </div>
        {/* Main content */}
        <main className="flex-1 min-h-0 overflow-hidden flex flex-col rounded-tl-2xl">
          {children}
        </main>
      </div>
    </AppViewContext.Provider>
  );
}
