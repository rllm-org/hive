// SSE parsing helpers — TypeScript port of rllm-org/agent-sdk/src/api/sse.py.
// Shapes and classifications are kept compatible so the browser reducer
// matches the server's own parsing.

export const UT_MESSAGE_DELTA = "agent_message_delta";
export const UT_MESSAGE_CHUNK = "agent_message_chunk";
export const UT_MESSAGE_CREATED = "agent_message_created";
export const UT_THOUGHT_CHUNK = "agent_thought_chunk";
export const UT_TOOL_STARTED = "execute_tool_started";
export const UT_TOOL_COMPLETED = "execute_tool_completed";
export const UT_TOOL_CALL = "tool_call";
export const UT_TOOL_CALL_UPDATE = "tool_call_update";
export const UT_USAGE_UPDATED = "usage_updated";
export const UT_USAGE_UPDATE = "usage_update";
export const UT_COMMANDS_UPDATE = "available_commands_update";

export type AcpKind = "done_result" | "error" | "update" | "skip";

export interface AcpClassified {
  kind: AcpKind;
  data: Record<string, unknown> | null;
}

/** Split an incoming fetch response body into SSE blocks (separated by \n\n). */
export async function* iterSseBlocks(
  response: Response,
  signal?: AbortSignal,
): AsyncGenerator<string, void, void> {
  if (!response.body) return;
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  try {
    while (true) {
      if (signal?.aborted) return;
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n|\r/g, "\n");
      let idx: number;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        yield block;
      }
    }
    if (buffer.length > 0) {
      const tail = buffer;
      buffer = "";
      yield tail;
    }
  } finally {
    try { reader.releaseLock(); } catch { /* noop */ }
  }
}

/** Join multi-line `data:` fields in an SSE block and JSON.parse the result. */
export function parseSseData(block: string): Record<string, unknown> | null {
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("data: ")) dataLines.push(line.slice(6));
    else if (line.startsWith("data:")) dataLines.push(line.slice(5));
  }
  if (dataLines.length === 0) return null;
  try {
    return JSON.parse(dataLines.join("\n"));
  } catch {
    return null;
  }
}

/** Pull the server-side `event: rpc:<rpc_id>` tag, if present. */
export function extractSseTag(block: string): string | null {
  for (const line of block.split("\n")) {
    if (line.startsWith("event: rpc:")) return line.slice("event: rpc:".length).trim();
  }
  return null;
}

/** Classify an ACP JSON-RPC payload as done_result / error / update / skip. */
export function parseAcpPayload(
  payload: Record<string, unknown>,
  rpcId: string | null,
): AcpClassified {
  if ("id" in payload && "result" in payload) {
    const result = payload.result as Record<string, unknown> | null;
    if (result && typeof result === "object" && "stopReason" in result) {
      if (rpcId === null || payload.id === rpcId) {
        return { kind: "done_result", data: result };
      }
    }
    return { kind: "skip", data: null };
  }

  if ("id" in payload && "error" in payload) {
    if (rpcId !== null && payload.id !== rpcId) {
      return { kind: "skip", data: null };
    }
    const err = payload.error as Record<string, unknown>;
    if (err && err.code === -32601) return { kind: "skip", data: null };
    return { kind: "error", data: err };
  }

  if (payload.method !== "session/update") {
    return { kind: "skip", data: null };
  }

  const params = (payload.params ?? {}) as Record<string, unknown>;
  const update = (params.update ?? {}) as Record<string, unknown>;
  return { kind: "update", data: update };
}

type Content = Record<string, unknown>;

export function classifyMessageContent(
  content: unknown,
): { kind: "text" | "reasoning"; value: string } | null {
  if (!content || typeof content !== "object") return null;
  const c = content as Content;
  const thinking = c.thinking;
  if (typeof thinking === "string" && thinking) {
    return { kind: "reasoning", value: thinking };
  }
  const text = c.text;
  if (typeof text !== "string" || !text) return null;
  const ctype = c.type;
  if (ctype === "thinking") return { kind: "reasoning", value: text };
  if (ctype === undefined || ctype === "text") return { kind: "text", value: text };
  return null;
}

export function extractToolCallId(update: Record<string, unknown>): string | null {
  const top = ["toolCallId", "toolUseId", "tool_call_id", "tool_use_id", "id"];
  for (const k of top) {
    const v = update[k];
    if (typeof v === "string" && v) return v;
  }
  const meta = update._meta as Record<string, unknown> | undefined;
  const cc = meta && (meta.claudeCode as Record<string, unknown> | undefined);
  if (cc) {
    for (const k of ["toolUseId", "toolCallId", "tool_use_id", "tool_call_id", "id"]) {
      const v = cc[k];
      if (typeof v === "string" && v) return v;
    }
  }
  const raw = update.rawInput as Record<string, unknown> | undefined;
  if (raw) {
    for (const k of ["toolUseId", "tool_use_id", "id"]) {
      const v = raw[k];
      if (typeof v === "string" && v.startsWith("toolu_")) return v;
    }
  }
  return null;
}

export function extractToolName(update: Record<string, unknown>): string {
  const meta = update._meta as Record<string, unknown> | undefined;
  const cc = meta && (meta.claudeCode as Record<string, unknown> | undefined);
  const name = cc && cc.toolName;
  if (typeof name === "string" && name) return name;
  for (const k of ["toolName", "tool", "name", "kind"]) {
    const v = update[k];
    if (typeof v === "string" && v) return v;
  }
  return "tool";
}

export function extractToolResponse(update: Record<string, unknown>): unknown {
  const meta = update._meta as Record<string, unknown> | undefined;
  const cc = meta && (meta.claudeCode as Record<string, unknown> | undefined);
  if (cc) {
    for (const k of ["toolResponse", "toolResult", "tool_response", "tool_result"]) {
      const v = cc[k];
      if (v !== undefined && v !== null) return v;
    }
  }
  for (const k of [
    "toolResponse", "toolResult", "tool_response", "tool_result",
    "output", "result", "content",
  ]) {
    const v = update[k];
    if (v !== undefined && v !== null) return v;
  }
  return null;
}
