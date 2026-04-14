"use client";

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import { LuSend } from "react-icons/lu";
import { useEditor, useEditorState, EditorContent, ReactRenderer, type Editor } from "@tiptap/react";
import { splitBlock } from "@tiptap/pm/commands";
import StarterKit from "@tiptap/starter-kit";
import Placeholder from "@tiptap/extension-placeholder";
import Mention from "@tiptap/extension-mention";
import Link from "@tiptap/extension-link";
import { Markdown } from "tiptap-markdown";
import type { SuggestionProps, SuggestionKeyDownProps } from "@tiptap/suggestion";
import { LuBold, LuItalic, LuCode, LuList, LuListOrdered, LuQuote, LuLink } from "react-icons/lu";

import { useAuth } from "@/lib/auth";
import { apiFetch, apiPostJson } from "@/lib/api";
import { getAgentColor } from "@/lib/agent-colors";
import { type AgentSummary } from "@/hooks/use-chat";

/* ─────────────── Drafts ─────────────── */

// Per-channel/thread draft storage (session-only, survives view switches)
const messageDrafts = new Map<string, string>();
function draftKey(taskPath: string, channelName: string, threadTs?: string): string {
  return threadTs
    ? `${taskPath}::${channelName}::thread::${threadTs}`
    : `${taskPath}::${channelName}`;
}

/* ─────────────── Mention suggestion list (React component) ─────────────── */

interface MentionListHandle {
  onKeyDown: (props: SuggestionKeyDownProps) => boolean;
}

interface MentionListProps {
  items: AgentSummary[];
  command: (item: { id: string; label: string }) => void;
}

const MentionList = forwardRef<MentionListHandle, MentionListProps>(function MentionList(
  { items, command },
  ref,
) {
  // Reset highlight when the items list changes (new query)
  // Pattern: store prev state, compare, reset if different — React's documented "derive from props" approach
  const [prevItems, setPrevItems] = useState(items);
  const [selectedIndex, setSelectedIndex] = useState(0);
  if (prevItems !== items) {
    setPrevItems(items);
    setSelectedIndex(0);
  }

  const select = (index: number) => {
    const item = items[index];
    if (item) command({ id: item.id, label: item.id });
  };

  useImperativeHandle(ref, () => ({
    onKeyDown: ({ event }) => {
      if (items.length === 0) return false;
      if (event.key === "ArrowUp") {
        setSelectedIndex((i) => (i - 1 + items.length) % items.length);
        return true;
      }
      if (event.key === "ArrowDown") {
        setSelectedIndex((i) => (i + 1) % items.length);
        return true;
      }
      if (event.key === "Enter" || event.key === "Tab") {
        select(selectedIndex);
        return true;
      }
      return false;
    },
  }));

  if (items.length === 0) {
    return (
      <div className="w-[280px] rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] shadow-xl px-3 py-2 text-[12px] text-[var(--color-text-tertiary)]">
        No matching agents
      </div>
    );
  }

  return (
    <div className="w-[300px] max-h-[260px] overflow-y-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] shadow-xl">
      <div className="px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-[var(--color-text-tertiary)] border-b border-[var(--color-border)]">
        Agents
      </div>
      {items.map((item, index) => {
        const color = getAgentColor(item.id);
        const initials = item.id.slice(0, 2).toUpperCase();
        const active = index === selectedIndex;
        return (
          <button
            key={item.id}
            onMouseDown={(e) => {
              e.preventDefault();
              select(index);
            }}
            onMouseEnter={() => setSelectedIndex(index)}
            className={`flex w-full items-center gap-2.5 px-3 py-2 text-left text-[14px] transition-colors ${
              active
                ? "bg-[var(--color-accent)] text-white"
                : "text-[var(--color-text)] hover:bg-[var(--color-layer-1)]"
            }`}
          >
            <div
              className="w-6 h-6 rounded text-white text-[10px] font-bold flex items-center justify-center shrink-0"
              style={{ backgroundColor: color }}
            >
              {initials}
            </div>
            <div className="flex-1 min-w-0 truncate">
              <span className="font-medium">{item.id}</span>
              {item.owner_handle && (
                <span
                  className={`ml-2 text-[12px] ${
                    active ? "text-white/80" : "text-[var(--color-text-secondary)]"
                  }`}
                >
                  @{item.owner_handle}
                </span>
              )}
            </div>
            <span
              className={`text-[11px] tabular-nums ${
                active ? "text-white/80" : "text-[var(--color-text-tertiary)]"
              }`}
            >
              {item.total_runs} runs
            </span>
          </button>
        );
      })}
    </div>
  );
});

/* ─────────────── Suggestion render lifecycle (Tiptap → React) ─────────────── */

function makeMentionRender() {
  return () => {
    let component: ReactRenderer<MentionListHandle, MentionListProps> | null = null;
    let container: HTMLDivElement | null = null;

    const mount = (props: SuggestionProps<AgentSummary>) => {
      component = new ReactRenderer(MentionList, {
        props: {
          items: props.items,
          command: (item: { id: string; label: string }) => props.command(item),
        },
        editor: props.editor,
      });
      container = document.createElement("div");
      container.style.position = "fixed";
      container.style.zIndex = "100";
      container.style.pointerEvents = "auto";
      document.body.appendChild(container);
      container.appendChild(component.element as HTMLElement);
      position(props);
    };

    const position = (props: SuggestionProps<AgentSummary>) => {
      if (!container) return;
      const rect = props.clientRect?.();
      if (!rect) return;
      // Position above the cursor with a small gap
      const popupHeight = container.offsetHeight || 200;
      container.style.left = `${rect.left}px`;
      container.style.top = `${rect.top - popupHeight - 8}px`;
    };

    return {
      onStart: (props: SuggestionProps<AgentSummary>) => {
        mount(props);
      },
      onUpdate: (props: SuggestionProps<AgentSummary>) => {
        component?.updateProps({
          items: props.items,
          command: (item: { id: string; label: string }) => props.command(item),
        });
        position(props);
      },
      onKeyDown: (props: SuggestionKeyDownProps) => {
        if (props.event.key === "Escape") {
          return true;
        }
        return component?.ref?.onKeyDown(props) ?? false;
      },
      onExit: () => {
        component?.destroy();
        if (container && container.parentNode) {
          container.parentNode.removeChild(container);
        }
        component = null;
        container = null;
      },
    };
  };
}

/* ─────────────── Mention extension (configured) ─────────────── */

function makeMentionExtension(fetchAgents: (query: string) => Promise<AgentSummary[]>) {
  // Extend Mention to (1) soft-delete on backspace and (2) teach tiptap-markdown
  // how to serialize the node — without this, tiptap-markdown's fallback writes
  // a literal "[mention]" placeholder into the markdown, which then renders as
  // plain text on the receiving side instead of as an @-pill.
  const SoftBackspaceMention = Mention.extend({
    addStorage() {
      return {
        ...this.parent?.(),
        markdown: {
          serialize(state: { write: (text: string) => void }, node: { attrs: { id?: string; label?: string } }) {
            const id = node.attrs.id ?? node.attrs.label ?? "";
            state.write(`@${id}`);
          },
          parse: {},
        },
      };
    },
    addKeyboardShortcuts() {
      return {
        Backspace: () => {
          const { selection } = this.editor.state;
          const { $from, empty } = selection;
          if (!empty) return false;
          const before = $from.nodeBefore;
          if (!before || before.type.name !== this.name) return false;
          const id = (before.attrs.id ?? before.attrs.label ?? "") as string;
          const fullText = `@${id}`;
          // First backspace converts the pill to its text minus the last char
          const newText = fullText.slice(0, -1);
          const start = $from.pos - before.nodeSize;
          const end = $from.pos;
          this.editor
            .chain()
            .focus()
            .insertContentAt({ from: start, to: end }, newText)
            .run();
          return true;
        },
      };
    },
  });
  return SoftBackspaceMention.configure({
    HTMLAttributes: { class: "hive-mention-pill" },
    renderText({ node }) {
      return `@${node.attrs.label ?? node.attrs.id}`;
    },
    suggestion: {
      char: "@",
      allowSpaces: false,
      items: async ({ query }) => {
        try {
          return await fetchAgents(query);
        } catch {
          return [];
        }
      },
      render: makeMentionRender(),
    },
  });
}

/* ─────────────── Editor toolbar ─────────────── */

interface ToolbarButtonProps {
  onClick: () => void;
  active?: boolean;
  title: string;
  children: React.ReactNode;
}

function ToolbarButton({ onClick, active, title, children }: ToolbarButtonProps) {
  return (
    <button
      type="button"
      onMouseDown={(e) => {
        // Run the command directly on mousedown — by the time `click` fires the
        // editor's selection has already been collapsed/lost, which causes
        // block transforms (bullet/ordered/quote/codeBlock) to apply to the
        // line above the user's selection. preventDefault keeps focus in the
        // editor so the chain's `.focus()` lands on the original selection.
        e.preventDefault();
        onClick();
      }}
      title={title}
      onClick={(e) => e.preventDefault()}
      className={`w-7 h-7 flex items-center justify-center rounded transition-colors ${
        active
          ? "bg-[var(--color-layer-2)] text-[var(--color-text)]"
          : "text-[var(--color-text-secondary)] hover:bg-[var(--color-layer-1)] hover:text-[var(--color-text)]"
      }`}
    >
      {children}
    </button>
  );
}

function CodeBlockIcon({ size = 14 }: { size?: number }) {
  // Lucide doesn't ship a clean code-block icon, so use a small composite
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M9 9l-2 3 2 3" />
      <path d="M15 9l2 3-2 3" />
    </svg>
  );
}

function EditorToolbar({ editor }: { editor: Editor | null }) {
  // Tiptap v3's useEditor does not re-render on transactions; we must subscribe
  // to the slice of state we care about (active marks/nodes) via useEditorState.
  const state = useEditorState({
    editor,
    selector: ({ editor: e }) => {
      if (!e) return null;
      return {
        bold: e.isActive("bold"),
        italic: e.isActive("italic"),
        code: e.isActive("code"),
        codeBlock: e.isActive("codeBlock"),
        bulletList: e.isActive("bulletList"),
        orderedList: e.isActive("orderedList"),
        blockquote: e.isActive("blockquote"),
        link: e.isActive("link"),
      };
    },
  });
  // Link modal state — we open a small in-app modal instead of window.prompt.
  // We must capture the editor's selection at the moment the button is clicked
  // (in mousedown, before focus moves to the modal), so we can restore it on save.
  const [linkModalOpen, setLinkModalOpen] = useState(false);
  const [linkUrl, setLinkUrl] = useState("");
  const savedRangeRef = useRef<{ from: number; to: number } | null>(null);

  if (!editor || !state) return null;

  const openLinkModal = () => {
    const { from, to } = editor.state.selection;
    savedRangeRef.current = { from, to };
    const previous = editor.getAttributes("link").href as string | undefined;
    setLinkUrl(previous ?? "");
    setLinkModalOpen(true);
  };

  const closeLinkModal = () => {
    setLinkModalOpen(false);
    setLinkUrl("");
    savedRangeRef.current = null;
  };

  const saveLink = () => {
    const range = savedRangeRef.current;
    if (!range) {
      closeLinkModal();
      return;
    }
    const url = linkUrl.trim();
    const chain = editor.chain().focus().setTextSelection(range).extendMarkRange("link");
    if (url === "") {
      chain.unsetLink().run();
    } else {
      // If browser would normally consider this missing a scheme, prepend https://.
      const normalized = /^[a-z][a-z0-9+\-.]*:\/\//i.test(url) ? url : `https://${url}`;
      chain.setLink({ href: normalized }).run();
    }
    closeLinkModal();
  };
  return (
    <div className="flex items-center gap-0.5 px-1.5 py-1 border-b border-[var(--color-border)]">
      <ToolbarButton
        title="Bold (Cmd+B)"
        active={state.bold}
        onClick={() => editor.chain().focus().toggleBold().run()}
      >
        <LuBold size={14} />
      </ToolbarButton>
      <ToolbarButton
        title="Italic (Cmd+I)"
        active={state.italic}
        onClick={() => editor.chain().focus().toggleItalic().run()}
      >
        <LuItalic size={14} />
      </ToolbarButton>
      <ToolbarButton
        title="Inline code (Cmd+E)"
        active={state.code}
        onClick={() => editor.chain().focus().toggleCode().run()}
      >
        <LuCode size={14} />
      </ToolbarButton>
      <ToolbarButton
        title="Code block"
        active={state.codeBlock}
        onClick={() => editor.chain().focus().toggleCodeBlock().run()}
      >
        <CodeBlockIcon />
      </ToolbarButton>
      <span className="w-px h-4 bg-[var(--color-border)] mx-1" />
      <ToolbarButton
        title="Bullet list"
        active={state.bulletList}
        onClick={() => editor.chain().focus().toggleBulletList().run()}
      >
        <LuList size={14} />
      </ToolbarButton>
      <ToolbarButton
        title="Numbered list"
        active={state.orderedList}
        onClick={() => editor.chain().focus().toggleOrderedList().run()}
      >
        <LuListOrdered size={14} />
      </ToolbarButton>
      <ToolbarButton
        title="Quote"
        active={state.blockquote}
        onClick={() => editor.chain().focus().toggleBlockquote().run()}
      >
        <LuQuote size={14} />
      </ToolbarButton>
      <span className="w-px h-4 bg-[var(--color-border)] mx-1" />
      <ToolbarButton
        title="Link"
        active={state.link}
        onClick={openLinkModal}
      >
        <LuLink size={14} />
      </ToolbarButton>
      {linkModalOpen && (
        <LinkModal
          url={linkUrl}
          onUrlChange={setLinkUrl}
          onSave={saveLink}
          onClose={closeLinkModal}
          hasExisting={state.link}
        />
      )}
    </div>
  );
}

/* ─────────────── Link modal ─────────────── */

interface LinkModalProps {
  url: string;
  onUrlChange: (url: string) => void;
  onSave: () => void;
  onClose: () => void;
  hasExisting: boolean;
}

function LinkModal({ url, onUrlChange, onSave, onClose, hasExisting }: LinkModalProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const t = setTimeout(() => inputRef.current?.focus(), 30);
    return () => clearTimeout(t);
  }, []);
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      onSave();
    } else if (e.key === "Escape") {
      e.preventDefault();
      onClose();
    }
  };
  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="absolute inset-0 bg-black/40" />
      <div className="relative z-10 w-[420px] rounded-xl bg-[var(--color-surface)] shadow-2xl border border-[var(--color-border)]">
        <div className="px-5 pt-4 pb-3 border-b border-[var(--color-border)]">
          <h2 className="text-[15px] font-semibold text-[var(--color-text)]">
            {hasExisting ? "Edit link" : "Add link"}
          </h2>
        </div>
        <div className="px-5 py-4">
          <label className="block text-[12px] font-semibold text-[var(--color-text-secondary)] mb-1.5">
            URL
          </label>
          <input
            ref={inputRef}
            type="url"
            value={url}
            onChange={(e) => onUrlChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="https://example.com"
            style={{ outline: "none" }}
            className="h-9 w-full rounded-md border border-[var(--color-border)] px-3 text-[14px] text-[var(--color-text)] bg-[var(--color-surface)] placeholder:text-[var(--color-text-tertiary)] focus:outline-none"
          />
          {hasExisting && (
            <p className="mt-2 text-[11px] text-[var(--color-text-tertiary)]">
              Leave empty and save to remove the link.
            </p>
          )}
        </div>
        <div className="flex items-center justify-end gap-2 px-5 py-3 border-t border-[var(--color-border)]">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 text-[13px] font-medium text-[var(--color-text-secondary)] hover:bg-[var(--color-layer-1)] rounded"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onSave}
            disabled={!hasExisting && !url.trim()}
            className="px-3 py-1.5 text-[13px] font-medium rounded bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─────────────── Editor helpers ─────────────── */

function getEditorMarkdown(editor: Editor | null): string {
  if (!editor) return "";
  // tiptap-markdown adds storage.markdown.getMarkdown(); fall back to plain text
  const storage = editor.storage as { markdown?: { getMarkdown?: () => string } };
  return storage.markdown?.getMarkdown?.() ?? editor.getText();
}

/* ─────────────── Shared chat editor hook ─────────────── */

async function fetchAgentsForMention(query: string): Promise<AgentSummary[]> {
  const params = new URLSearchParams({ limit: "10" });
  if (query) params.set("q", query);
  const data = await apiFetch<{ agents: AgentSummary[] }>(`/agents?${params.toString()}`);
  return data.agents;
}

interface UseChatEditorOptions {
  placeholder: string;
  initialContent?: string;
  onSubmit: () => void;
  onChange?: (text: string) => void;
}

function useChatEditor({ placeholder, initialContent = "", onSubmit, onChange }: UseChatEditorOptions) {
  const submitRef = useRef(onSubmit);
  const changeRef = useRef(onChange);
  useEffect(() => {
    submitRef.current = onSubmit;
    changeRef.current = onChange;
  });

  // Placeholder is read once at editor creation. Parent components must remount
  // MessageInput (via React key) when the placeholder needs to change.
  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: false,
        horizontalRule: false,
        bulletList: { HTMLAttributes: { class: "list-disc pl-5 my-1" } },
        orderedList: { HTMLAttributes: { class: "list-decimal pl-5 my-1" } },
        listItem: { HTMLAttributes: { class: "leading-snug" } },
        blockquote: {
          HTMLAttributes: {
            class: "border-l-2 border-[var(--color-border)] pl-3 my-1 text-[var(--color-text-secondary)]",
          },
        },
        codeBlock: {
          HTMLAttributes: {
            class: "my-1 px-3 py-2 rounded-md bg-[var(--color-layer-2)] overflow-x-auto text-[12px] font-[family-name:var(--font-ibm-plex-mono)] leading-snug whitespace-pre",
          },
        },
        code: {
          HTMLAttributes: {
            class: "px-1 py-px rounded bg-[var(--color-layer-2)] text-[12px] font-[family-name:var(--font-ibm-plex-mono)]",
          },
        },
      }),
      Placeholder.configure({ placeholder }),
      Link.configure({
        openOnClick: false,
        HTMLAttributes: { class: "text-[var(--color-accent)] underline" },
      }),
      Markdown.configure({
        html: false,
        breaks: true,
        linkify: true,
        transformPastedText: true,
        transformCopiedText: true,
      }),
      makeMentionExtension(fetchAgentsForMention),
    ],
    content: initialContent,
    immediatelyRender: false,
    editorProps: {
      attributes: {
        class:
          "tiptap-input block w-full px-3.5 pt-2.5 pb-1 text-[14px] leading-[20px] text-[var(--color-text)] bg-transparent focus:outline-none min-h-[24px] max-h-[240px] overflow-y-auto",
      },
      handleKeyDown(view, event) {
        // The mention suggestion plugin intercepts Enter when active and returns true,
        // so this only fires when the suggestion popup is closed.
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault();
          submitRef.current();
          return true;
        }
        // Shift+Enter: split into a new paragraph instead of inserting a hard break.
        // Without this, two "lines" live inside the same <p>, which means
        // bullet/quote/codeBlock would wrap BOTH lines instead of just the
        // line containing the cursor.
        if (event.key === "Enter" && event.shiftKey) {
          event.preventDefault();
          splitBlock(view.state, view.dispatch);
          return true;
        }
        return false;
      },
    },
    onUpdate({ editor }) {
      changeRef.current?.(getEditorMarkdown(editor));
    },
  });

  return editor;
}

/* ─────────────── MessageInput component ─────────────── */

interface MessageInputProps {
  taskPath: string;
  channelName: string;
  threadTs?: string;
  placeholder: string;
  onSent: () => void;
}

export function MessageInput({
  taskPath,
  channelName,
  threadTs,
  placeholder,
  onSent,
}: MessageInputProps) {
  const { user } = useAuth();
  const key = draftKey(taskPath, channelName, threadTs);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sendingRef = useRef(false);

  const sendRef = useRef<() => void>(() => {});

  const editor = useChatEditor({
    placeholder,
    initialContent: messageDrafts.get(key) ?? "",
    onSubmit: () => sendRef.current(),
    onChange: (text) => {
      if (text) {
        messageDrafts.set(key, text);
      } else {
        messageDrafts.delete(key);
      }
    },
  });

  const handleSend = useCallback(async () => {
    if (!editor) return;
    const text = getEditorMarkdown(editor).trim();
    if (!text || sendingRef.current) return;
    sendingRef.current = true;
    setSending(true);
    setError(null);
    try {
      const body: { text: string; thread_ts?: string } = { text };
      if (threadTs) body.thread_ts = threadTs;
      await apiPostJson(`/tasks/${taskPath}/channels/${channelName}/messages`, body);
      editor.commands.clearContent();
      messageDrafts.delete(key);
      onSent();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to send");
    } finally {
      sendingRef.current = false;
      setSending(false);
    }
  }, [editor, taskPath, channelName, threadTs, key, onSent]);
  sendRef.current = handleSend;

  // Subscribe to editor "is empty?" via useEditorState. MUST be called before
  // any early return so React's hook order stays stable across renders
  // (e.g. when the user logs in/out and the early-return path toggles).
  const hasContent = useEditorState({
    editor,
    selector: ({ editor: e }) => (e?.getText().trim().length ?? 0) > 0,
  }) ?? false;

  if (!user) {
    return (
      <div className="shrink-0 px-5 pb-5 pt-2 bg-[var(--color-layer-1)]">
        <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] cursor-not-allowed select-none">
          <div className="block w-full px-3.5 pt-2.5 pb-1 text-[14px] leading-[20px] text-[var(--color-text-tertiary)] min-h-[24px]">
            Log in to send messages
          </div>
          <div className="flex items-center justify-end px-2 pb-1.5 pt-1">
            <div className="flex h-7 w-7 items-center justify-center rounded text-[var(--color-text-tertiary)]">
              <LuSend size={14} />
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="shrink-0 px-5 pb-5 pt-2 bg-[var(--color-layer-1)]">
      <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] focus-within:border-[var(--color-text-tertiary)] transition-colors shadow-sm overflow-hidden">
        <EditorToolbar editor={editor} />
        <EditorContent editor={editor} />
        <div className="flex items-center justify-end px-2 pb-1.5 pt-1">
          <button
            onClick={handleSend}
            disabled={sending || !hasContent}
            aria-label="Send message"
            title="Send message (Enter)"
            className={`flex h-7 w-7 items-center justify-center rounded transition-colors ${
              hasContent && !sending
                ? "bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)]"
                : "text-[var(--color-text-tertiary)] bg-transparent"
            }`}
          >
            <LuSend size={14} />
          </button>
        </div>
      </div>
      {error && <div className="mt-1.5 px-1 text-[11px] text-red-500">{error}</div>}
    </div>
  );
}

/* ─────────────── EditMessageInline component ─────────────── */

interface EditMessageInlineProps {
  initialText: string;
  initialMentions: string[];
  onSave: (newText: string) => Promise<void>;
  onCancel: () => void;
}

export function EditMessageInline({ initialText, initialMentions, onSave, onCancel }: EditMessageInlineProps) {
  // initialMentions is intentionally unused — tiptap-markdown's parser handles
  // bold/italic/code/lists/quotes/links from the raw markdown, but mentions
  // will appear as plain @<name> text in the edit view (not as pills). On save
  // the text round-trips correctly via the markdown serializer, so functionality
  // is preserved; only the in-edit visual differs from the rendered message.
  void initialMentions;
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const savingRef = useRef(false);

  const saveRef = useRef<() => void>(() => {});

  const editor = useChatEditor({
    placeholder: "Edit message...",
    initialContent: initialText,
    onSubmit: () => saveRef.current(),
  });

  // Focus the editor when it mounts so users can immediately type
  useEffect(() => {
    if (editor) editor.commands.focus("end");
  }, [editor]);

  const handleSave = useCallback(async () => {
    if (!editor) return;
    const text = getEditorMarkdown(editor).trim();
    if (!text || savingRef.current) return;
    if (text === initialText.trim()) {
      onCancel();
      return;
    }
    savingRef.current = true;
    setSaving(true);
    setError(null);
    try {
      await onSave(text);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  }, [editor, initialText, onSave, onCancel]);
  saveRef.current = handleSave;

  // Esc cancels
  useEffect(() => {
    if (!editor) return;
    const dom = editor.view.dom as HTMLElement;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onCancel();
      }
    };
    dom.addEventListener("keydown", handler);
    return () => dom.removeEventListener("keydown", handler);
  }, [editor, onCancel]);

  const hasContent = useEditorState({
    editor,
    selector: ({ editor: e }) => (e?.getText().trim().length ?? 0) > 0,
  }) ?? false;

  return (
    <div className="mt-1">
      <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] focus-within:border-[var(--color-text-tertiary)] transition-colors pb-2 overflow-hidden">
        <EditorToolbar editor={editor} />
        <EditorContent editor={editor} />
      </div>
      <div className="mt-1 flex items-center gap-2 text-[12px]">
        <button onClick={onCancel} className="text-[var(--color-text-secondary)] hover:underline">
          Cancel
        </button>
        <button
          onClick={handleSave}
          disabled={saving || !hasContent}
          className="px-3 py-1 rounded font-medium bg-[var(--color-accent)] text-white hover:bg-[var(--color-accent-hover)] disabled:opacity-40"
        >
          {saving ? "Saving…" : "Save"}
        </button>
        {error && <span className="text-red-500">{error}</span>}
      </div>
    </div>
  );
}
