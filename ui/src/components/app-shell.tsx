"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { Sidebar, type SidebarTab } from "@/components/sidebar";

const TAB_ROUTES: Record<SidebarTab, string> = {
  home: "/",
  tasks: "/tasks",
  profile: "/me",
};

function pathToTab(pathname: string): SidebarTab {
  if (pathname === "/tasks" || pathname.startsWith("/tasks/")) return "tasks";
  if (pathname === "/me" || pathname.startsWith("/me/")) return "profile";
  return "home";
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, ready } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  const isPublicRoute = pathname === "/" || pathname === "/tasks" || pathname.startsWith("/task/") || pathname.startsWith("/auth/");

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

  const activeTab = pathToTab(pathname);

  const handleTabChange = (tab: SidebarTab) => {
    router.push(TAB_ROUTES[tab]);
  };

  return (
    <div className="flex w-full h-screen overflow-hidden">
      <Sidebar activeTab={activeTab} onTabChange={handleTabChange} />
      <main className="flex-1 overflow-auto bg-[var(--color-bg)]">
        {children}
      </main>
    </div>
  );
}
