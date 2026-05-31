import type { AgentTimelineEntry, SecretPromptPayload } from "./chatThreadStorage";
import {
  buildRunCardsFromTimeline,
  type RunCard,
} from "./buildRunCards";

export type TurnSegment =
  | { type: "text"; text: string }
  | { type: "card"; card: RunCard }
  | { type: "secret_prompt"; prompt: SecretPromptPayload };

const INDEX_TOOL = "coding_index";
const DELEGATE_TOOL = "agent_delegate";

/** When stream offsets were not recorded, keep a short leading assistant intro before tool cards. */
function leadingTextSplitIndex(content: string): number {
  const t = content.trimStart();
  const lead = content.length - t.length;
  const para = t.indexOf("\n\n");
  if (para > 0) return lead + para + 2;
  const sentence = t.search(/[.!?]\s+/);
  if (sentence > 0) {
    const m = t.slice(sentence).match(/^\S+\s*/);
    return lead + sentence + (m ? m[0].length : 1);
  }
  return 0;
}

function isSecretPromptAnchor(e: AgentTimelineEntry): boolean {
  return e.kind === "secret_prompt" && !!e.secretPrompt;
}

function isCardAnchorEntry(e: AgentTimelineEntry): boolean {
  if (e.kind === "compaction_done") return true;
  if (e.kind === "subagent_start" || e.kind === "index_start") return true;
  if (e.kind !== "tool_start" || !e.toolName) return false;
  const tool = e.toolName;
  if (tool === DELEGATE_TOOL) return false;
  if (tool === INDEX_TOOL) return true;
  return (
    tool.startsWith("coding_") ||
    tool === "retrieve_context" ||
    tool.startsWith("security_scan")
  );
}

/**
 * Interleave streamed assistant text with tool/subagent cards in timeline order.
 * Uses ``streamOffset`` on anchor entries (set when the tool/subagent starts).
 */
export function buildInterleavedTurnSegments(
  content: string,
  entries: AgentTimelineEntry[]
): TurnSegment[] {
  const cards = buildRunCardsFromTimeline(entries);
  const secretAnchors = entries.filter(isSecretPromptAnchor);
  if (cards.length === 0 && secretAnchors.length === 0) {
    const trimmed = (content ?? "").trim();
    return trimmed ? [{ type: "text", text: content }] : [];
  }

  const cardById = new Map(cards.map((c) => [c.id, c]));
  const anchors = entries.filter((e) => isCardAnchorEntry(e) || isSecretPromptAnchor(e));
  const withOffset = anchors.filter(
    (a) => typeof a.streamOffset === "number" && a.streamOffset >= 0
  );

  const pushSecretPrompts = (segments: TurnSegment[]) => {
    for (const e of secretAnchors) {
      if (e.secretPrompt) segments.push({ type: "secret_prompt", prompt: e.secretPrompt });
    }
  };

  if (withOffset.length === 0) {
    const segments: TurnSegment[] = [];
    const trimmed = (content ?? "").trim();
    if (trimmed && (cards.length > 0 || secretAnchors.length > 0)) {
      const leadEnd = leadingTextSplitIndex(content);
      if (leadEnd > 0 && leadEnd < content.length) {
        segments.push({ type: "text", text: content.slice(0, leadEnd) });
        for (const c of cards) segments.push({ type: "card", card: c });
        pushSecretPrompts(segments);
        const tail = content.slice(leadEnd);
        if (tail.trim()) segments.push({ type: "text", text: tail });
        return segments;
      }
    }
    if (trimmed) segments.push({ type: "text", text: content });
    for (const c of cards) segments.push({ type: "card", card: c });
    pushSecretPrompts(segments);
    return segments;
  }

  const sorted = [...withOffset].sort(
    (a, b) => (a.streamOffset ?? 0) - (b.streamOffset ?? 0)
  );
  const segments: TurnSegment[] = [];
  const len = content.length;
  let pos = 0;
  const placed = new Set<string>();

  const placedSecrets = new Set<string>();

  for (const a of sorted) {
    const off = Math.min(a.streamOffset ?? 0, len);
    if (off > pos) {
      const chunk = content.slice(pos, off);
      if (chunk.length > 0) segments.push({ type: "text", text: chunk });
    }
    if (isSecretPromptAnchor(a) && a.secretPrompt && !placedSecrets.has(a.secretPrompt.promptId)) {
      segments.push({ type: "secret_prompt", prompt: a.secretPrompt });
      placedSecrets.add(a.secretPrompt.promptId);
    }
    const card = cardById.get(a.id);
    if (card && !placed.has(card.id)) {
      segments.push({ type: "card", card });
      placed.add(card.id);
    }
    pos = Math.max(pos, off);
  }

  if (pos < len) {
    const tail = content.slice(pos);
    if (tail.length > 0) segments.push({ type: "text", text: tail });
  }

  for (const c of cards) {
    if (!placed.has(c.id)) segments.push({ type: "card", card: c });
  }
  for (const e of secretAnchors) {
    if (e.secretPrompt && !placedSecrets.has(e.secretPrompt.promptId)) {
      segments.push({ type: "secret_prompt", prompt: e.secretPrompt });
    }
  }

  return segments;
}
