"use client";

import { useParams } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { ChatPanel } from "@/components/chat/chat-panel";

export default function WorkspaceRoutePage() {
  const { team, workspace } = useParams<{ team: string; workspace: string }>();
  const { user } = useAuth();

  if (!user) {
    return (
      <div className="flex items-center justify-center h-screen text-[var(--color-text-secondary)]">
        Loading...
      </div>
    );
  }

  return <ChatPanel taskPath="hive/demo-chat" embedded team={team} activeWorkspace={workspace} />;
}
