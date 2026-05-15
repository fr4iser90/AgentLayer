/** Incremental text and optional usage from OpenAI-style ``chat.completion.chunk`` SSE (``data:`` lines). */

function deltaPiecesFromPayload(obj: unknown): string {
  if (!obj || typeof obj !== "object") return "";
  const d = obj as { choices?: Array<{ delta?: Record<string, unknown> }> };
  const delta = d.choices?.[0]?.delta;
  if (!delta || typeof delta !== "object") return "";
  let out = "";
  const c = delta.content;
  if (typeof c === "string" && c) out += c;
  for (const key of ["reasoning", "thinking"]) {
    const v = delta[key];
    if (typeof v === "string" && v) out += v;
  }
  return out;
}

function usageFromPayload(obj: unknown): unknown | undefined {
  if (!obj || typeof obj !== "object") return undefined;
  const raw = (obj as Record<string, unknown>).usage;
  if (raw == null || typeof raw !== "object") return undefined;
  return raw;
}

export type StreamChatChunk = { kind: "text"; text: string } | { kind: "usage"; usage: unknown };

/**
 * Read a streaming ``/v1/chat/completions`` response: text deltas and any ``usage`` objects
 * (often a single final chunk; some backends mirror OpenAI ``stream_options.include_usage``).
 */
export async function* streamOpenAiChatChunks(res: Response): AsyncGenerator<StreamChatChunk, void, void> {
  const reader = res.body?.getReader();
  if (!reader) return;
  const dec = new TextDecoder();
  let carry = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    carry += dec.decode(value, { stream: true });
    let sep: number;
    while ((sep = carry.indexOf("\n\n")) !== -1) {
      const block = carry.slice(0, sep).replace(/\r/g, "");
      carry = carry.slice(sep + 2);
      for (const line of block.split("\n")) {
        const m = line.match(/^data:\s*(.*)$/);
        if (!m) continue;
        const payload = m[1].trim();
        if (!payload || payload === "[DONE]") continue;
        try {
          const parsed = JSON.parse(payload) as unknown;
          const piece = deltaPiecesFromPayload(parsed);
          if (piece) yield { kind: "text", text: piece };
          const usage = usageFromPayload(parsed);
          if (usage !== undefined) yield { kind: "usage", usage };
        } catch {
          /* non-JSON line */
        }
      }
    }
  }
}

/** Text only (ignores usage). */
export async function* streamOpenAiDeltaText(res: Response): AsyncGenerator<string, void, void> {
  for await (const ch of streamOpenAiChatChunks(res)) {
    if (ch.kind === "text") yield ch.text;
  }
}
