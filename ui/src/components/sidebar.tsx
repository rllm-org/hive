"use client";

import { useState, useEffect } from "react";
import { useAuth } from "@/lib/auth";
import { LuHouse, LuLayoutGrid, LuUser, LuPanelLeftClose, LuPanelLeftOpen } from "react-icons/lu";

export type SidebarTab = "home" | "tasks" | "profile";

interface SidebarProps {
  activeTab: SidebarTab;
  onTabChange: (tab: SidebarTab) => void;
}

export function Sidebar({ activeTab, onTabChange }: SidebarProps) {
  const { user } = useAuth();
  const [isCollapsed, setIsCollapsed] = useState(false);

  if (!user) return null;

  const navItems = [
    { id: "home" as const, icon: LuHouse, label: "Home" },
    { id: "tasks" as const, icon: LuLayoutGrid, label: "Public Tasks" },
    { id: "profile" as const, icon: LuUser, label: "Account" },
  ];

  return (
    <aside className="flex h-screen flex-shrink-0">
      <div
        style={{
          width: isCollapsed ? "44px" : "180px",
          minWidth: isCollapsed ? "44px" : "180px",
          transition: "width 0.2s, min-width 0.2s",
        }}
        className="bg-[var(--color-surface)] border-r border-[var(--color-border)] flex flex-col flex-shrink-0"
      >
        {/* Header */}
        <div className={`h-14 flex items-center ${isCollapsed ? "justify-center px-1" : "justify-between pl-4 pr-2"}`}>
          {!isCollapsed && (
            <button onClick={() => onTabChange("home")} className="flex items-center gap-0">
              <img src="/hive-logo.svg" alt="Hive logo" width={32} height={32} />
              <span className="-ml-0.5 text-base font-bold tracking-tight text-[var(--color-text)]">Hive</span>
            </button>
          )}
          <button
            onClick={() => setIsCollapsed(!isCollapsed)}
            className="p-1.5 text-[var(--color-text-tertiary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-2)] transition-colors"
            title={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {isCollapsed ? <LuPanelLeftOpen size={18} /> : <LuPanelLeftClose size={18} />}
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 py-2 px-2">
          {navItems.map((item) => {
            const Icon = item.icon;
            const active = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onTabChange(item.id)}
                className={`
                  w-full flex items-center gap-3 px-3 py-2 text-sm font-medium
                  transition-colors duration-150
                  ${isCollapsed ? "justify-center" : ""}
                  ${active
                    ? "bg-[var(--color-accent-50)] text-[var(--color-accent)]"
                    : "text-[var(--color-text-secondary)] hover:bg-[var(--color-layer-1)] hover:text-[var(--color-text)]"
                  }
                `}
                title={isCollapsed ? item.label : undefined}
              >
                <Icon size={18} className="flex-shrink-0" />
                {!isCollapsed && <span>{item.label}</span>}
              </button>
            );
          })}
        </nav>

      </div>
    </aside>
  );
}
