"use client";

import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { apiPost, apiFetch } from "@/lib/api";

interface CreateTaskModalProps {
  onClose: () => void;
  onCreated: () => void;
}

interface SubmitResult {
  id: string;
  name: string;
  repo_url: string;
  status: string;
}

function FieldError({ msg }: { msg: string | null }) {
  if (!msg) return null;
  return <p className="mt-1 text-xs text-red-500">{msg}</p>;
}

export function CreateTaskModal({ onClose, onCreated }: CreateTaskModalProps) {
  const [taskId, setTaskId] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [adminKey, setAdminKey] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitResult, setSubmitResult] = useState<SubmitResult | null>(null);
  const [showDiscard, setShowDiscard] = useState(false);
  const [errors, setErrors] = useState<Record<string, string | null>>({});
  const setFieldError = (field: string, msg: string | null) =>
    setErrors((prev) => ({ ...prev, [field]: msg }));

  const overlayRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const isDirty = useMemo(
    () => !!(taskId || name || description || file || adminKey),
    [taskId, name, description, file, adminKey],
  );

  const safeClose = useCallback(() => {
    if (submitResult) { onClose(); return; }
    if (isDirty) setShowDiscard(true);
    else onClose();
  }, [isDirty, onClose, submitResult]);

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (showDiscard) setShowDiscard(false);
        else safeClose();
      }
    };
    window.addEventListener("keydown", handleEsc);
    return () => window.removeEventListener("keydown", handleEsc);
  }, [safeClose, showDiscard]);

  const TASK_ID_RE = /^[a-z0-9]([a-z0-9-]*[a-z0-9])?$/;
  const validate = (): boolean => {
    const idErr = !taskId.trim() ? "Task ID is required." : !TASK_ID_RE.test(taskId.trim()) ? "Lowercase letters, digits, and hyphens only." : null;
    const nameErr = !name.trim() ? "Name is required." : null;
    const descErr = !description.trim() ? "Description is required." : null;
    const fileErr = !file ? "Upload a zip file containing the task." : null;
    const keyErr = !adminKey.trim() ? "Admin key is required." : null;
    setFieldError("taskId", idErr);
    setFieldError("name", nameErr);
    setFieldError("description", descErr);
    setFieldError("file", fileErr);
    setFieldError("adminKey", keyErr);
    return !idErr && !nameErr && !descErr && !fileErr && !keyErr;
  };

  const checkUniqueness = async (id: string) => {
    try {
      await apiFetch(`/tasks/${id}`);
      setFieldError("taskId", `Task ID "${id}" already exists.`);
    } catch {
      setErrors((prev) =>
        prev.taskId?.includes("already exists") ? { ...prev, taskId: null } : prev,
      );
    }
  };

  const handleTaskIdChange = (id: string) => {
    setTaskId(id);
    setFieldError("taskId", null);
    if (!name || name === titleFromId(taskId)) {
      setName(titleFromId(id));
    }
  };

  function titleFromId(id: string): string {
    return id.split("-").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
  }

  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (f && (f.name.endsWith(".zip") || f.name.endsWith(".tar.gz") || f.name.endsWith(".tgz"))) {
      setFile(f);
      setFieldError("file", null);
      if (!taskId) {
        const slug = f.name.replace(/\.(zip|tar\.gz|tgz)$/, "").toLowerCase().replace(/[^a-z0-9-]/g, "-");
        handleTaskIdChange(slug);
      }
    } else {
      setFieldError("file", "Please upload a .zip or .tar.gz file.");
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) {
      setFile(f);
      setFieldError("file", null);
      if (!taskId) {
        const slug = f.name.replace(/\.(zip|tar\.gz|tgz)$/, "").toLowerCase().replace(/[^a-z0-9-]/g, "-");
        handleTaskIdChange(slug);
      }
    }
  };

  const handleSubmit = async () => {
    if (!validate()) return;
    setSubmitError(null);
    setSubmitting(true);
    try {
      const formData = new FormData();
      formData.append("id", taskId.trim());
      formData.append("name", name.trim());
      formData.append("description", description.trim());
      formData.append("archive", file!);
      const result = await apiPost<SubmitResult>("/tasks", formData, { "X-Admin-Key": adminKey.trim() });
      setSubmitResult(result);
      onCreated();
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Failed to create task");
    } finally {
      setSubmitting(false);
    }
  };

  const inputCls = "w-full px-3 py-2 text-sm border rounded-lg bg-[var(--color-bg)] text-[var(--color-text)] placeholder:text-[var(--color-text-tertiary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] focus:border-transparent";
  const inputBorder = (field: string) => errors[field] ? "border-red-400" : "border-[var(--color-border)]";
  const labelCls = "block text-xs font-medium text-[var(--color-text-secondary)] mb-1.5";

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-[9999] flex justify-end bg-black/40 backdrop-blur-sm"
      onClick={(e) => { if (e.target === overlayRef.current) safeClose(); }}
    >
      <div className="bg-[var(--color-surface)] border-l border-[var(--color-border)] shadow-[var(--shadow-elevated)] w-full max-w-[540px] h-full flex flex-col animate-slide-in-right">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border)] shrink-0">
          <h2 className="text-base font-semibold text-[var(--color-text)]">
            {submitResult ? "Task Submitted" : "Create Task"}
          </h2>
          <button
            onClick={safeClose}
            className="w-7 h-7 rounded flex items-center justify-center text-[var(--color-text-tertiary)] hover:text-[var(--color-text)] hover:bg-[var(--color-layer-2)] transition-all"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M3 3l8 8M11 3l-8 8" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          {submitResult ? (
            /* ─── Success confirmation ─── */
            <div className="space-y-6 animate-fade-in">
              <div className="flex flex-col items-center text-center py-4">
                <div className="w-12 h-12 rounded-full bg-green-100 flex items-center justify-center mb-4">
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth="2">
                    <path d="M5 13l4 4L19 7" />
                  </svg>
                </div>
                <h3 className="text-lg font-semibold text-[var(--color-text)] mb-2">Draft created successfully</h3>
                <p className="text-sm text-[var(--color-text-secondary)]">
                  Your task has been uploaded as a draft. A reviewer will check it and make it live.
                </p>
              </div>

              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] divide-y divide-[var(--color-border)]">
                <div className="flex gap-3 px-4 py-3">
                  <span className="text-xs font-medium text-[var(--color-text-tertiary)] w-16 shrink-0 pt-0.5">Repo</span>
                  <a
                    href={submitResult.repo_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-[var(--color-accent)] hover:underline break-all font-[family-name:var(--font-ibm-plex-mono)]"
                  >
                    {submitResult.repo_url}
                  </a>
                </div>
                <div className="flex gap-3 px-4 py-3">
                  <span className="text-xs font-medium text-[var(--color-text-tertiary)] w-16 shrink-0 pt-0.5">Status</span>
                  <span className="inline-flex items-center gap-1.5 text-sm">
                    <span className="w-2 h-2 rounded-full bg-yellow-400" />
                    Draft — pending review
                  </span>
                </div>
                <div className="flex gap-3 px-4 py-3">
                  <span className="text-xs font-medium text-[var(--color-text-tertiary)] w-16 shrink-0 pt-0.5">Task ID</span>
                  <span className="text-sm font-[family-name:var(--font-ibm-plex-mono)]">{submitResult.id}</span>
                </div>
                <div className="flex gap-3 px-4 py-3">
                  <span className="text-xs font-medium text-[var(--color-text-tertiary)] w-16 shrink-0 pt-0.5">Name</span>
                  <span className="text-sm">{submitResult.name}</span>
                </div>
              </div>

              <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
                <p className="text-sm text-amber-800">
                  <span className="font-medium">Before review, please ensure your repo contains:</span>
                </p>
                <ul className="text-sm text-amber-700 mt-2 space-y-1 list-disc list-inside">
                  <li><code className="text-xs bg-amber-100 px-1 rounded">program.md</code> — agent instructions and experiment loop</li>
                  <li><code className="text-xs bg-amber-100 px-1 rounded">agent.py</code> — the artifact agents will evolve</li>
                  <li><code className="text-xs bg-amber-100 px-1 rounded">eval/eval.sh</code> — evaluation script</li>
                  <li><code className="text-xs bg-amber-100 px-1 rounded">prepare.sh</code> — data download script</li>
                </ul>
              </div>
            </div>
          ) : (
            /* ─── Form ─── */
            <div className="space-y-4">
              {/* File upload */}
              <div>
                <label className={labelCls}>Task Archive</label>
                <div
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={handleFileDrop}
                  onClick={() => fileInputRef.current?.click()}
                  className={`${inputCls} ${inputBorder("file")} cursor-pointer flex flex-col items-center justify-center py-6 text-center border-dashed border-2`}
                >
                  {file ? (
                    <div className="flex items-center gap-2">
                      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-green-500">
                        <path d="M3 8.5l3 3 7-7" />
                      </svg>
                      <span className="text-sm font-medium">{file.name}</span>
                      <span className="text-xs text-[var(--color-text-tertiary)]">({(file.size / 1024).toFixed(0)} KB)</span>
                    </div>
                  ) : (
                    <>
                      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-[var(--color-text-tertiary)] mb-2">
                        <path d="M12 16V8m0 0l-3 3m3-3l3 3M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2" />
                      </svg>
                      <span className="text-sm text-[var(--color-text-secondary)]">Drop a .zip or .tar.gz here, or click to browse</span>
                      <span className="text-xs text-[var(--color-text-tertiary)] mt-1">Must contain program.md, agent.py, eval/, prepare.sh</span>
                    </>
                  )}
                </div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".zip,.tar.gz,.tgz"
                  onChange={handleFileSelect}
                  className="hidden"
                />
                <FieldError msg={errors.file ?? null} />
              </div>

              <div>
                <label className={labelCls}>Task ID</label>
                <input
                  type="text"
                  value={taskId}
                  onChange={(e) => handleTaskIdChange(e.target.value)}
                  onBlur={() => {
                    const err = !taskId.trim() ? "Task ID is required." : !TASK_ID_RE.test(taskId.trim()) ? "Lowercase letters, digits, and hyphens only." : null;
                    setFieldError("taskId", err);
                    if (!err) checkUniqueness(taskId.trim());
                  }}
                  placeholder="e.g. my-benchmark"
                  className={`${inputCls} ${inputBorder("taskId")} font-[family-name:var(--font-ibm-plex-mono)]`}
                />
                <FieldError msg={errors.taskId ?? null} />
              </div>

              <div>
                <label className={labelCls}>Name</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => { setName(e.target.value); setFieldError("name", null); }}
                  onBlur={() => setFieldError("name", !name.trim() ? "Name is required." : null)}
                  placeholder="e.g. My Benchmark"
                  className={`${inputCls} ${inputBorder("name")}`}
                />
                <FieldError msg={errors.name ?? null} />
              </div>

              <div>
                <label className={labelCls}>Description</label>
                <textarea
                  value={description}
                  onChange={(e) => { setDescription(e.target.value); setFieldError("description", null); }}
                  onBlur={() => setFieldError("description", !description.trim() ? "Description is required." : null)}
                  placeholder="What should agents optimize? Describe the task and scoring."
                  rows={3}
                  className={`${inputCls} ${inputBorder("description")} resize-none`}
                />
                <FieldError msg={errors.description ?? null} />
              </div>

              <div>
                <label className={labelCls}>Admin Key</label>
                <input
                  type="password"
                  value={adminKey}
                  onChange={(e) => { setAdminKey(e.target.value); setFieldError("adminKey", null); }}
                  onBlur={() => setFieldError("adminKey", !adminKey.trim() ? "Admin key is required." : null)}
                  placeholder="Enter admin key"
                  className={`${inputCls} ${inputBorder("adminKey")}`}
                />
                <FieldError msg={errors.adminKey ?? null} />
              </div>

              {submitError && (
                <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                  {submitError}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-[var(--color-border)] shrink-0">
          {submitResult ? (
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] rounded-lg transition-colors"
            >
              Done
            </button>
          ) : (
            <>
              <button
                type="button"
                onClick={safeClose}
                className="px-4 py-2 text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={submitting}
                onClick={handleSubmit}
                className="px-4 py-2 text-sm font-medium text-white bg-[var(--color-accent)] hover:bg-[var(--color-accent-hover)] rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {submitting ? "Uploading..." : "Submit for Review"}
              </button>
            </>
          )}
        </div>
      </div>

      {/* Discard confirmation */}
      {showDiscard && (
        <div className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/50">
          <div className="bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] shadow-[var(--shadow-elevated)] p-6 max-w-sm mx-4 animate-fade-in">
            <h3 className="text-sm font-semibold text-[var(--color-text)] mb-2">Discard draft?</h3>
            <p className="text-sm text-[var(--color-text-secondary)] mb-4">You have unsaved changes that will be lost.</p>
            <div className="flex justify-end gap-3">
              <button onClick={() => setShowDiscard(false)} className="px-4 py-2 text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors">
                Keep editing
              </button>
              <button onClick={onClose} className="px-4 py-2 text-sm font-medium text-white bg-red-500 hover:bg-red-600 rounded-lg transition-colors">
                Discard
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
