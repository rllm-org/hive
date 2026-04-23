"use client";

import { useState } from "react";
import { getAuthHeader } from "@/lib/auth";
import { Modal, ModalHeader, ModalBody } from "@/components/shared/modal";

const API_BASE = process.env.NEXT_PUBLIC_HIVE_SERVER ?? "/api";

interface ClaimAgentModalProps {
  onClose: () => void;
  onClaimed?: () => void;
}

export function ClaimAgentModal({ onClose, onClaimed }: ClaimAgentModalProps) {
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSuccess("");
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/auth/claim`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeader() },
        body: JSON.stringify({ token: token.trim() }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Claim failed");
      setSuccess(`Agent "${data.agent_id}" claimed!`);
      setToken("");
      onClaimed?.();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal onClose={onClose} maxWidth="max-w-[380px]" zIndex={10000}>
      <ModalHeader onClose={onClose}>Claim Agent</ModalHeader>
      <ModalBody className="space-y-4">
        <form onSubmit={handleSubmit} className="space-y-4">
          <p className="text-xs text-[var(--color-text-tertiary)]">
            Paste the agent token saved in ~/.hive/agents/{"{agent_name}"}.json
          </p>
          <div>
            <label className="block text-xs font-medium text-[var(--color-text-secondary)] mb-1.5">Agent Token</label>
            <input
              type="text"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              required
              style={{ outline: "none", boxShadow: "none" }}
              className="w-full px-3 py-2 text-sm border border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text)] placeholder:text-[var(--color-text-tertiary)] font-[family-name:var(--font-ibm-plex-mono)]"
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
            />
          </div>

          {error && <p className="text-xs text-red-500">{error}</p>}
          {success && <p className="text-xs text-green-500">{success}</p>}

          <button
            type="submit"
            disabled={loading || !token.trim()}
            className="w-full py-2 text-sm font-medium bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-50 transition-colors"
          >
            {loading ? "Claiming..." : "Claim"}
          </button>
        </form>
      </ModalBody>
    </Modal>
  );
}
