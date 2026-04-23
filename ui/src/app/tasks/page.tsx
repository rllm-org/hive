"use client";

import { useAuth } from "@/lib/auth";
import { TasksPage } from "@/components/task-explorer";

export default function TasksRoute() {
  const { user } = useAuth();

  if (!user) {
    return <TasksPage />;
  }

  return (
    <div className="h-full overflow-auto bg-[var(--color-bg)] rounded-tl-2xl">
      <TasksPage />
    </div>
  );
}
