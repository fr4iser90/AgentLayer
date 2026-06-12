/** Shared WebSocket agent-turn utilities (ChatPage + dashboard embedded chat). */

import i18n from "../../i18n/config";
import {
  extractAssistantContentFromCompletion,
  extractAssistantReasoningFromCompletion,
  extractSpeechTextFromCompletion,
} from "./assistantCompletionExtract";
import { compactionEventToTimeline } from "./compactionActivity";
import { formatToolStepLabel } from "./toolStepLabel";
import type { LiveTurnStore } from "./useAgentLiveTurn";

export function agentChatWsUrl(token: string): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws/v1/chat?token=${encodeURIComponent(token)}`;
}

export function assistantFromAgentCompletion(data: unknown): string {
  return extractAssistantContentFromCompletion(data);
}

export function reasoningFromAgentCompletion(data: unknown): string {
  return extractAssistantReasoningFromCompletion(data);
}

export type AgentToolDoneEvent = {
  name: string;
  proposalSetId?: string;
  dashboardId?: string;
  ok?: boolean;
};

export type AgentWsTurnCallbacks = {
  onToolDone?: (ev: AgentToolDoneEvent) => void;
  /** Footer mini-player after successful ``media_enqueue`` with ``now_playing_id``. */
  onMediaPlay?: (payload: Record<string, unknown>) => void;
  streamEnabled?: boolean;
};

export type AgentWsTurnResult = {
  content: string;
  reasoningContent?: string;
  speechText?: string;
};

export type AgentWsTurnController = {
  resolve: (result: AgentWsTurnResult) => void;
  reject: (err: Error) => void;
  isFinished: () => boolean;
  markFinished: () => void;
};

type HandlerCtx = {
  liveTurn: LiveTurnStore;
  toolStartTimes: Map<string, number>;
  turn: AgentWsTurnController;
  callbacks: AgentWsTurnCallbacks;
  pausedStepLabel?: string;
};

function appendAgentLine(
  liveTurn: LiveTurnStore,
  kind: string,
  text: string,
  extras?: Record<string, unknown>
) {
  if (!liveTurn.isActive()) return;
  liveTurn.appendLogLine(kind, text, extras);
}

function assistantStreamOffset(liveTurn: LiveTurnStore): number {
  return Math.max(0, liveTurn.getStreamText().length);
}

export function llmSlotWaitMessage(msg: Record<string, unknown>): string {
  const waited = msg.waited_sec != null ? Number(msg.waited_sec) : 0;
  const max = msg.max_parallel != null ? Number(msg.max_parallel) : 1;
  const ahead = msg.queue_ahead != null ? Number(msg.queue_ahead) : 0;
  const size = msg.queue_size != null ? Number(msg.queue_size) : 0;
  const w = waited >= 10 ? Math.round(waited) : Math.round(waited * 10) / 10;
  if (ahead > 0 || size > 1) {
    const qClass = msg.queue_class != null ? String(msg.queue_class) : "";
    if (qClass === "benchmark") {
      return i18n.t("chat:llmSlotWaitBenchmarkQueued", {
        waited: w,
        max: Math.max(1, max),
        ahead: Math.max(0, ahead),
        size: Math.max(size, ahead + 1),
      });
    }
    return i18n.t("chat:llmSlotWaitQueued", {
      waited: w,
      max: Math.max(1, max),
      ahead: Math.max(0, ahead),
      size: Math.max(size, ahead + 1),
    });
  }
  return i18n.t("chat:llmSlotWait", { waited: w, max: Math.max(1, max) });
}

export function scanWaitMessage(msg: Record<string, unknown>): string {
  const waited = msg.waited_sec != null ? Number(msg.waited_sec) : 0;
  const est = msg.estimated_time_seconds != null ? Number(msg.estimated_time_seconds) : null;
  const remaining =
    msg.estimated_remaining_sec != null ? Number(msg.estimated_remaining_sec) : null;
  const phase = msg.phase != null ? String(msg.phase) : "";
  const w = waited >= 10 ? Math.round(waited) : Math.round(waited * 10) / 10;
  if (phase === "started") {
    return est != null && est > 0
      ? i18n.t("chat:scanWaitStarted", { est: Math.round(est) })
      : i18n.t("chat:scanWaitStartedUnknown");
  }
  if (remaining != null && remaining >= 0) {
    return i18n.t("chat:scanWaitProgress", { waited: w, remaining: Math.round(remaining) });
  }
  return i18n.t("chat:scanWaitProgressUnknown", { waited: w });
}

function handleLlmSlotWait(msg: Record<string, unknown>, liveTurn: LiveTurnStore): void {
  if (!liveTurn.isActive()) return;
  const text = llmSlotWaitMessage(msg);
  liveTurn.setWaitHint(text);
  const waited = msg.waited_sec != null ? Number(msg.waited_sec) : 0;
  const ahead = msg.queue_ahead != null ? Number(msg.queue_ahead) : undefined;
  const size = msg.queue_size != null ? Number(msg.queue_size) : undefined;
  if (waited < 0.5) {
    liveTurn.appendLogLine("llm_queue", text, {
      queueAhead: ahead,
      queueSize: size,
    });
  }
}

function handleScanWait(msg: Record<string, unknown>, liveTurn: LiveTurnStore): void {
  if (!liveTurn.isActive()) return;
  const text = scanWaitMessage(msg);
  liveTurn.setWaitHint(text);
  const phase = msg.phase != null ? String(msg.phase) : "";
  const est =
    msg.estimated_time_seconds != null ? Number(msg.estimated_time_seconds) : undefined;
  if (phase === "started" || phase === "waiting") {
    liveTurn.appendLogLine("scan_queue", text, {
      estimatedTimeSeconds: est,
    });
  }
  if (phase === "ended") {
    liveTurn.setWaitHint(null);
  }
}

/** Dispatch one parsed WebSocket agent event (shared between Chat and dashboard). */
export function handleAgentWsMessage(msg: Record<string, unknown>, ctx: HandlerCtx): void {
  const { liveTurn, toolStartTimes, turn, callbacks } = ctx;
  const typ = typeof msg.type === "string" ? msg.type : String(msg.type ?? "");
  const streamEnabled = callbacks.streamEnabled !== false;

  if (typ === "pong") return;

  if (typ === "error") {
    turn.reject(
      new Error(typeof msg.detail === "string" ? msg.detail : "Agent error")
    );
    return;
  }

  if (typ === "chat.completion") {
    if (msg.error) {
      turn.reject(
        new Error(typeof msg.detail === "string" ? msg.detail : "Agent turn failed")
      );
      return;
    }
    const acc = liveTurn.getStreamText().trim();
    const fromApi = assistantFromAgentCompletion(msg.data);
    const content = streamEnabled && acc.length > 0 ? acc : fromApi;
    const accReasoning = liveTurn.getStreamReasoningText().trim();
    const fromApiReasoning = reasoningFromAgentCompletion(msg.data);
    const reasoningContent =
      streamEnabled && accReasoning.length > 0 ? accReasoning : fromApiReasoning;
    const speechText = extractSpeechTextFromCompletion(msg.data);
    turn.resolve({
      content: content.trim() || fromApi.trim() || "(empty)",
      ...(reasoningContent.trim() ? { reasoningContent: reasoningContent.trim() } : {}),
      ...(speechText ? { speechText } : {}),
    });
    return;
  }

  if (typ === "agent.session") {
    const em = msg.effective_model != null ? String(msg.effective_model) : "";
    const mr = msg.model_resolution != null ? String(msg.model_resolution) : "";
    appendAgentLine(
      liveTurn,
      "session",
      [em && `model: ${em}`, mr && `(${mr})`].filter(Boolean).join(" ")
    );
    if (msg.context && typeof msg.context === "object") {
      const ctxMeta = msg.context as Record<string, unknown>;
      if (ctxMeta.compaction_applied && ctxMeta.summary_active) {
        const { kind, text, extras } = compactionEventToTimeline({
          phase: "history",
          context_window_tokens:
            ctxMeta.context_window_tokens != null
              ? Number(ctxMeta.context_window_tokens)
              : undefined,
          budget_source:
            ctxMeta.budget_source != null ? String(ctxMeta.budget_source) : undefined,
          messages_dropped:
            ctxMeta.messages_dropped != null ? Number(ctxMeta.messages_dropped) : undefined,
          messages_compacted_this_run:
            ctxMeta.messages_compacted_this_run != null
              ? Number(ctxMeta.messages_compacted_this_run)
              : undefined,
          summary_covers_messages:
            ctxMeta.summary_covers_messages != null
              ? Number(ctxMeta.summary_covers_messages)
              : undefined,
        });
        appendAgentLine(liveTurn, kind, text, {
          ...extras,
          streamOffset: assistantStreamOffset(liveTurn),
        });
      }
    }
    return;
  }

  if (typ === "agent.context_compacted") {
    const { kind, text, extras } = compactionEventToTimeline({
      phase: msg.phase != null ? String(msg.phase) : "loop",
      reason: msg.reason != null ? String(msg.reason) : undefined,
      round: msg.round != null ? Number(msg.round) : undefined,
      provider_prompt_tokens:
        msg.provider_prompt_tokens != null ? Number(msg.provider_prompt_tokens) : undefined,
      soft_limit_tokens:
        msg.soft_limit_tokens != null ? Number(msg.soft_limit_tokens) : undefined,
      context_window_tokens:
        msg.context_window_tokens != null ? Number(msg.context_window_tokens) : undefined,
      tool_rounds_dropped:
        msg.tool_rounds_dropped != null ? Number(msg.tool_rounds_dropped) : undefined,
      budget_source: msg.budget_source != null ? String(msg.budget_source) : undefined,
    });
    appendAgentLine(liveTurn, kind, text, {
      ...extras,
      streamOffset: assistantStreamOffset(liveTurn),
    });
    return;
  }

  if (typ === "agent.llm_round_start") {
    liveTurn.setWaitHint(null);
    const r = msg.round != null ? Number(msg.round) : 0;
    if (streamEnabled && r > 1) {
      liveTurn.appendStreamSeparator();
    }
    const rLabel = msg.round != null ? `round ${msg.round}` : "round";
    appendAgentLine(liveTurn, "llm", `${rLabel} (start)`);
    return;
  }

  if (typ === "agent.llm_delta") {
    if (!streamEnabled) return;
    liveTurn.setWaitHint(null);
    const channel = msg.channel != null ? String(msg.channel) : "";
    const reasoningDelta =
      msg.reasoning_delta != null ? String(msg.reasoning_delta) : "";
    if (channel === "reasoning" || reasoningDelta) {
      const d = reasoningDelta || (msg.delta != null ? String(msg.delta) : "");
      if (!d) return;
      liveTurn.appendReasoningStreamDelta(d);
      return;
    }
    const d = msg.delta != null ? String(msg.delta) : "";
    if (!d) return;
    liveTurn.appendStreamDelta(d);
    return;
  }

  if (typ === "agent.llm_round") {
    const r = msg.round != null ? `round ${msg.round}` : "round";
    const ex = msg.content_excerpt != null ? String(msg.content_excerpt).slice(0, 200) : "";
    appendAgentLine(liveTurn, "llm", `${r}${ex ? ` — ${ex}` : ""}`);
    return;
  }

  if (typ === "agent.media_play") {
    callbacks.onMediaPlay?.(msg);
    return;
  }

  if (typ === "agent.tool_start") {
    const toolName = String(msg.name ?? "tool");
    const summary = typeof msg.summary === "string" ? msg.summary.trim() : undefined;
    const toolLabel = typeof msg.label === "string" ? msg.label.trim() : undefined;
    const stepLabel = typeof msg.step_label === "string" ? msg.step_label.trim() : undefined;
    toolStartTimes.set(toolName, Date.now());
    appendAgentLine(
      liveTurn,
      "tool_start",
      formatToolStepLabel(toolName, summary, toolLabel, stepLabel) || `→ ${toolName}`,
      {
        toolName,
        toolSummary: summary,
        streamOffset: assistantStreamOffset(liveTurn),
      }
    );
    return;
  }

  if (typ === "agent.tool_done") {
    const n = msg.name != null ? String(msg.name) : "tool";
    const ch = msg.result_chars != null ? Number(msg.result_chars) : undefined;
    const toolOk =
      msg.result_ok === false ? false : msg.result_ok === true ? true : undefined;
    const toolError =
      typeof msg.result_error === "string" && msg.result_error.trim()
        ? msg.result_error.trim().slice(0, 500)
        : undefined;
    let durationMs = msg.duration_ms != null ? Number(msg.duration_ms) : null;
    if (durationMs == null || durationMs < 0) {
      const startTime = toolStartTimes.get(n);
      if (startTime != null) {
        durationMs = Date.now() - startTime;
        toolStartTimes.delete(n);
      }
    }
    const parts: string[] = [];
    if (toolOk === false) {
      parts.push(toolError ? `failed: ${toolError}` : "failed");
    }
    if (ch != null && ch > 0) parts.push(`${ch} chars`);
    if (durationMs != null && durationMs >= 0) {
      parts.push(
        durationMs < 1000
          ? `${durationMs} ms`
          : durationMs < 60000
            ? `${(durationMs / 1000).toFixed(1)} s`
            : `${(durationMs / 60000).toFixed(1)} min`
      );
    }
    appendAgentLine(liveTurn, "tool_done", `${n}${parts.length ? ` (${parts.join(", ")})` : ""}`, {
      toolName: n,
      toolOk,
      toolError,
      durationMs: durationMs ?? undefined,
      resultChars: ch,
    });
    const proposalSetId =
      typeof msg.proposal_set_id === "string" ? msg.proposal_set_id : undefined;
    const dashId = typeof msg.dashboard_id === "string" ? msg.dashboard_id : undefined;
    callbacks.onToolDone?.({
      name: n,
      proposalSetId,
      dashboardId: dashId,
      ok: toolOk,
    });
    if (n === "media_enqueue" && toolOk !== false && msg.media_play) {
      callbacks.onMediaPlay?.(msg.media_play as Record<string, unknown>);
    }
    return;
  }

  if (typ === "agent.llm_slot_wait") {
    handleLlmSlotWait(msg, liveTurn);
    return;
  }

  if (typ === "agent.scan_wait") {
    handleScanWait(msg, liveTurn);
    return;
  }

  if (typ === "agent.step_wait") {
    appendAgentLine(liveTurn, "wait", ctx.pausedStepLabel ?? "Paused (step mode)");
    return;
  }

  if (typ === "agent.aborted" || typ === "agent.cancelled") {
    appendAgentLine(liveTurn, typ, String(msg.detail ?? ""));
    turn.reject(new Error(typeof msg.detail === "string" ? msg.detail : "Agent cancelled"));
    return;
  }

  if (typ === "agent.done") {
    appendAgentLine(liveTurn, "agent.done", String(msg.detail ?? ""));
    return;
  }
}
