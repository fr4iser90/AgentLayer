import type { AgentTimelineEntry, IndexRunMode } from "./chatThreadStorage";
import { activityForTurn } from "./agentLogStorage";
import type { ChatThread, UiMessage } from "./chatThreadStorage";

export type RunCardKind = "subagent" | "index" | "tool";
export type RunCardStatus = "running" | "done" | "failed";

export type RunCard = {
  id: string;
  kind: RunCardKind;
  status: RunCardStatus;
  title: string;
  subtitle?: string;
  agentId?: string;
  toolName?: string;
  indexMode?: IndexRunMode;
  durationMs?: number;
  resultChars?: number;
  indexPhase?: string;
  filesDone?: number;
  filesTotal?: number;
  details: AgentTimelineEntry[];
};

const INDEX_TOOL = "coding_index";
const DELEGATE_TOOL = "agent_delegate";

const AGENT_TITLES: Record<string, string> = {
  coding: "Coding agent",
  coding_plan: "Plan agent",
  security_auditor: "Security auditor",
};

const INDEX_MODE_LABEL: Record<IndexRunMode, string> = {
  full: "Full reindex",
  code: "Code index",
  docs: "Docs index",
  incremental: "Incremental index",
};

export function agentRunCardTitle(agentId: string | undefined): string {
  const id = (agentId || "").trim();
  if (!id) return "Agent run";
  return AGENT_TITLES[id] ?? id;
}

export function indexRunCardTitle(mode: IndexRunMode | undefined): string {
  if (!mode) return "Index run";
  return INDEX_MODE_LABEL[mode] ?? mode;
}

function isFailedText(text: string): boolean {
  const t = text.toLowerCase();
  return t.includes("failed") || t.includes("error") || t.startsWith("failed:");
}

function completeSubagentCard(card: RunCard, done: AgentTimelineEntry): void {
  card.status = isFailedText(done.text) ? "failed" : "done";
  card.durationMs = done.durationMs ?? card.durationMs;
  card.resultChars = done.resultChars ?? card.resultChars;
  if (!card.details.includes(done)) card.details.push(done);
  if (done.text.trim()) card.subtitle = done.text.trim();
}

function completeIndexCard(card: RunCard, done: AgentTimelineEntry): void {
  card.status =
    done.runStatus === "failed" || isFailedText(done.text) ? "failed" : "done";
  card.durationMs = done.durationMs ?? card.durationMs;
  card.indexPhase = done.indexPhase ?? card.indexPhase;
  card.filesDone = done.filesDone ?? card.filesDone;
  card.filesTotal = done.filesTotal ?? card.filesTotal;
  if (!card.details.includes(done)) card.details.push(done);
  if (done.text.trim()) card.subtitle = done.text.trim();
}

function findLastRunningCard(cards: RunCard[], kind: RunCardKind, match?: (c: RunCard) => boolean): RunCard | null {
  for (let i = cards.length - 1; i >= 0; i--) {
    const c = cards[i];
    if (c.kind === kind && c.status === "running" && (!match || match(c))) return c;
  }
  return null;
}

/** Build structured run cards from a flat agent activity timeline. */
export function buildRunCardsFromTimeline(entries: AgentTimelineEntry[]): RunCard[] {
  const cards: RunCard[] = [];
  const openTools = new Map<string, RunCard>();

  for (const e of entries) {
    if (e.kind === "subagent_start") {
      cards.push({
        id: e.id,
        kind: "subagent",
        status: "running",
        title: agentRunCardTitle(e.subagentAgentId),
        subtitle: e.text.trim() || undefined,
        agentId: e.subagentAgentId,
        details: [e],
      });
      continue;
    }

    if (e.kind === "subagent_done") {
      const card = findLastRunningCard(
        cards,
        "subagent",
        (c) => !e.subagentAgentId || c.agentId === e.subagentAgentId
      );
      if (card) completeSubagentCard(card, e);
      else {
        cards.push({
          id: e.id,
          kind: "subagent",
          status: isFailedText(e.text) ? "failed" : "done",
          title: agentRunCardTitle(e.subagentAgentId),
          subtitle: e.text.trim() || undefined,
          agentId: e.subagentAgentId,
          durationMs: e.durationMs,
          resultChars: e.resultChars,
          details: [e],
        });
      }
      continue;
    }

    if (e.kind === "index_start") {
      cards.push({
        id: e.id,
        kind: "index",
        status: "running",
        title: indexRunCardTitle(e.indexMode),
        subtitle: e.text.trim() || undefined,
        indexMode: e.indexMode,
        indexPhase: e.indexPhase,
        filesDone: e.filesDone,
        filesTotal: e.filesTotal,
        details: [e],
      });
      continue;
    }

    if (e.kind === "index_done") {
      const card = findLastRunningCard(
        cards,
        "index",
        (c) => !e.indexMode || c.indexMode === e.indexMode
      );
      if (card) completeIndexCard(card, e);
      else {
        cards.push({
          id: e.id,
          kind: "index",
          status: e.runStatus === "failed" || isFailedText(e.text) ? "failed" : "done",
          title: indexRunCardTitle(e.indexMode),
          subtitle: e.text.trim() || undefined,
          indexMode: e.indexMode,
          durationMs: e.durationMs,
          indexPhase: e.indexPhase,
          filesDone: e.filesDone,
          filesTotal: e.filesTotal,
          details: [e],
        });
      }
      continue;
    }

    if (e.kind === "tool_start" && e.toolName) {
      const tool = e.toolName;
      if (tool === INDEX_TOOL) {
        const card: RunCard = {
          id: e.id,
          kind: "index",
          status: "running",
          title: indexRunCardTitle("code"),
          subtitle: e.text.trim() || undefined,
          toolName: tool,
          indexMode: "code",
          details: [e],
        };
        cards.push(card);
        openTools.set(tool, card);
        continue;
      }
      if (tool === DELEGATE_TOOL) {
        continue;
      }
      const notable = tool.startsWith("coding_") || tool === "retrieve_context" || tool.startsWith("security_scan");
      if (notable) {
        const card: RunCard = {
          id: e.id,
          kind: "tool",
          status: "running",
          title: tool,
          subtitle: e.text.trim() || undefined,
          toolName: tool,
          details: [e],
        };
        cards.push(card);
        openTools.set(tool, card);
      }
      continue;
    }

    if (e.kind === "tool_done" && e.toolName) {
      const tool = e.toolName;
      const open = openTools.get(tool);
      if (open) {
        open.status = isFailedText(e.text) ? "failed" : "done";
        open.durationMs = e.durationMs ?? open.durationMs;
        open.resultChars = e.resultChars ?? open.resultChars;
        if (!open.details.includes(e)) open.details.push(e);
        openTools.delete(tool);
      }
    }
  }

  return cards;
}

export type TranscriptItem =
  | { type: "message"; message: UiMessage }
  | { type: "run_cards"; cards: RunCard[]; turnId: string };

/**
 * Per turn: user message → run cards (tools/subagents) → assistant reply.
 * Cards sit in the stream between the prompt and the answer, not above the user line
 * and not below the finished/streaming assistant text.
 */
export function buildTranscriptWithRunCards(
  messages: UiMessage[],
  thread: Pick<ChatThread, "messages" | "agentLog" | "turnLogs">
): TranscriptItem[] {
  const items: TranscriptItem[] = [];
  let i = 0;
  while (i < messages.length) {
    const m = messages[i];
    if (m.role === "user" && m.id) {
      const turnId = m.id;
      items.push({ type: "message", message: m });
      i += 1;
      const activity = activityForTurn(thread, turnId);
      const cards = buildRunCardsFromTimeline(activity);
      if (cards.length > 0) {
        items.push({ type: "run_cards", cards, turnId });
      }
      while (i < messages.length && messages[i].role === "assistant") {
        items.push({ type: "message", message: messages[i] });
        i += 1;
      }
      continue;
    }
    items.push({ type: "message", message: m });
    i += 1;
  }
  return items;
}
