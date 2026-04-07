"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { Sidebar, type SidebarTab } from "@/components/sidebar";

const TAB_ROUTES: Record<SidebarTab, string> = {
  home: "/",
  tasks: "/tasks",
  profile: "/me",
};

function pathToTab(pathname: string, userHandle: string | null): SidebarTab {
  if (pathname === "/tasks" || pathname.startsWith("/tasks/")) return "tasks";
  if (pathname === "/me" || pathname.startsWith("/me/")) return "profile";
  if (pathname.startsWith("/task/")) {
    // /task/{owner}/{slug} — if owner is the current user's handle, treat as profile (private task)
    const owner = pathname.split("/")[2];
    if (userHandle && owner === userHandle) return "profile";
    return "tasks";
  }
  return "home";
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, ready } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  const isPublicRoute = pathname === "/" || pathname === "/tasks" || pathname.startsWith("/task/") || pathname.startsWith("/auth/");
  const isTaskPage = pathname.startsWith("/task/");

  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  useEffect(() => {
    if (isTaskPage) setSidebarCollapsed(true);
  }, [isTaskPage]);

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

  const activeTab = pathToTab(pathname, user.handle ?? null);

  const handleTabChange = (tab: SidebarTab) => {
    router.push(TAB_ROUTES[tab]);
  };

  return (
    <div className="flex w-full h-screen overflow-hidden">
      <Sidebar
        activeTab={activeTab}
        onTabChange={handleTabChange}
        collapsed={sidebarCollapsed}
        onCollapsedChange={setSidebarCollapsed}
      />
      <main className="flex-1 overflow-auto bg-[var(--color-bg)]">
        {children}
      </main>
    </div>
  );
}
