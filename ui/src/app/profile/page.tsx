"use client";

import { useAuth } from "@/lib/auth";
import { ProfilePanel } from "@/components/profile-panel";

export default function ProfileRoute() {
  const { user } = useAuth();

  if (!user) return null;

  return (
    <div className="h-full overflow-auto bg-[var(--color-bg)] rounded-tl-2xl">
      <ProfilePanel />
    </div>
  );
}
